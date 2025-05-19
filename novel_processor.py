# novel_processor.py
# 该文件定义了小说处理器类，负责小说的预处理和初始全局分析。

import os
import json
from typing import Dict, List, Any, Optional, Tuple
import uuid  # 用于生成唯一的事件ID

import config  # 导入配置
import utils  # 导入工具函数
from ollama_client import OllamaClient  # 导入Ollama客户端
import prompts  # 导入提示工程模块


class NovelProcessor:
    """
    小说处理器类，负责小说的预处理（如分章）和使用LLM进行全局分析。
    分析过程采用增量合并方式。
    """

    def __init__(self, ollama_client: OllamaClient, novel_file_path: Optional[str] = None):
        self.ollama_client = ollama_client
        self.novel_file_path = novel_file_path
        self.project_data_dir = config.DATA_DIR
        self.novel_specific_data_dir: str
        if self.novel_file_path:
            novel_name = os.path.splitext(os.path.basename(self.novel_file_path))[0]
            self.novel_specific_data_dir = os.path.join(self.project_data_dir, utils.sanitize_filename(novel_name))
        else:
            self.novel_specific_data_dir = os.path.join(self.project_data_dir, "default_novel_project")
        self.chapters_data_path = ""
        self.analysis_in_progress_path = ""
        self.final_analysis_path = ""
        self.processed_event_ids = set()

    def _initialize_analysis_document(self, novel_title: str, novel_md5: str) -> Dict[str, Any]:
        return {
            "novel_title": novel_title,
            "source_text_md5": novel_md5,
            "world_setting": {"overview": "", "rules_and_systems": [], "key_locations": [], "major_factions": [],
                              "culture_and_customs": ""},  # 添加 culture_and_customs
            "main_plotline_summary": "",
            "detailed_timeline_and_key_events": [],
            "character_profiles": {},
            "unresolved_questions_or_themes_from_original": []
        }

    def _ensure_unique_event_ids(self, analysis_doc: Dict[str, Any]) -> Dict[str, Any]:
        if "detailed_timeline_and_key_events" not in analysis_doc or \
                not isinstance(analysis_doc["detailed_timeline_and_key_events"], list):
            analysis_doc["detailed_timeline_and_key_events"] = []
            return analysis_doc

        # 重新生成所有事件ID，以确保previous_doc和incremental_output中没有重复的临时ID冲突
        # 并且在最终合并后所有ID都是唯一的。
        # 也可以只处理新增事件的ID，但全局重新生成更简单。
        # 如果事件有稳定的用户定义ID，则不应重新生成。目前我们依赖LLM的临时ID。

        temp_id_to_final_id_map = {}  # 用于更新角色发展中的event_ref_id
        all_event_descriptions_for_id_gen = set()  # 用于避免基于描述生成重复ID（如果采用这种策略）

        new_event_list = []
        existing_ids_in_run = set()  # 本次运行中已分配的ID

        for event in analysis_doc["detailed_timeline_and_key_events"]:
            if not isinstance(event, dict): continue

            original_event_id = event.get("event_id")
            # 为所有事件生成新的唯一ID，除非它看起来已经是一个最终格式的ID (例如 E******)
            # 并且不在本轮已分配的ID中
            is_final_format_id = isinstance(original_event_id, str) and \
                                 original_event_id.startswith("E") and \
                                 len(original_event_id) == 7 and \
                                 original_event_id[1:].isalnum()

            if is_final_format_id and original_event_id not in existing_ids_in_run:
                final_id = original_event_id
            else:
                final_id = f"E{uuid.uuid4().hex[:6].upper()}"
                while final_id in existing_ids_in_run:
                    final_id = f"E{uuid.uuid4().hex[:6].upper()}"

            event["event_id"] = final_id
            existing_ids_in_run.add(final_id)
            if original_event_id and original_event_id != final_id:  # 记录临时ID到最终ID的映射
                temp_id_to_final_id_map[original_event_id] = final_id
            new_event_list.append(event)

        analysis_doc["detailed_timeline_and_key_events"] = new_event_list
        self.processed_event_ids.update(existing_ids_in_run)  # 更新全局已处理ID集合

        # 更新角色档案中 key_developments 的 event_ref_id
        if temp_id_to_final_id_map and "character_profiles" in analysis_doc:
            for char_name, profile in analysis_doc["character_profiles"].items():
                if isinstance(profile, dict) and "key_developments" in profile and isinstance(
                        profile["key_developments"], list):
                    for dev_event in profile["key_developments"]:
                        if isinstance(dev_event, dict) and dev_event.get("event_ref_id") in temp_id_to_final_id_map:
                            dev_event["event_ref_id"] = temp_id_to_final_id_map[dev_event["event_ref_id"]]
        return analysis_doc

    def _merge_incremental_analysis(self, previous_doc: Dict[str, Any], incremental_llm_output: Dict[str, Any],
                                    current_chapter_number: int) -> Dict[str, Any]:
        """
        将LLM返回的增量分析结果合并到先前的分析文档中。
        """
        merged_doc = json.loads(json.dumps(previous_doc))  # 深拷贝

        # 1. 合并 world_setting
        inc_ws = incremental_llm_output.get("world_setting")
        if isinstance(inc_ws, dict):
            if "overview" in inc_ws and inc_ws["overview"]:
                merged_doc["world_setting"]["overview"] = (
                            merged_doc["world_setting"].get("overview", "") + "\n" + inc_ws["overview"]).strip()

            # culture_and_customs 也是字符串，追加处理
            if "culture_and_customs" in inc_ws and inc_ws["culture_and_customs"]:
                merged_doc["world_setting"]["culture_and_customs"] = (
                            merged_doc["world_setting"].get("culture_and_customs", "") + "\n" + inc_ws[
                        "culture_and_customs"]).strip()

            for key in ["rules_and_systems", "key_locations", "major_factions"]:
                if key in inc_ws and isinstance(inc_ws[key], list):
                    merged_doc["world_setting"].setdefault(key, [])
                    existing_items_str = {json.dumps(item, sort_keys=True) for item in merged_doc["world_setting"][key]}
                    for new_item in inc_ws[key]:
                        if json.dumps(new_item, sort_keys=True) not in existing_items_str:
                            merged_doc["world_setting"][key].append(new_item)

        # 2. 合并 main_plotline_summary (追加)
        if "main_plotline_summary" in incremental_llm_output and incremental_llm_output["main_plotline_summary"]:
            merged_doc["main_plotline_summary"] = (merged_doc.get("main_plotline_summary",
                                                                  "") + "\n---\n" + f"(第{current_chapter_number}章补充): {incremental_llm_output['main_plotline_summary']}").strip()

        # 3. 合并 detailed_timeline_and_key_events (追加新事件，并设置chapter_approx)
        inc_events = incremental_llm_output.get("detailed_timeline_and_key_events")
        if isinstance(inc_events, list):
            merged_doc.setdefault("detailed_timeline_and_key_events", [])
            for new_event in inc_events:
                if isinstance(new_event, dict):
                    new_event["chapter_approx"] = current_chapter_number  # 程序设置章节号
                    # event_id 将在 _ensure_unique_event_ids 中统一处理
                    merged_doc["detailed_timeline_and_key_events"].append(new_event)

        # 4. 合并 character_profiles
        inc_profiles = incremental_llm_output.get("character_profiles")
        if isinstance(inc_profiles, dict):
            merged_doc.setdefault("character_profiles", {})
            for char_name, incremental_profile_update in inc_profiles.items():
                if not isinstance(incremental_profile_update, dict): continue

                if char_name not in merged_doc["character_profiles"]:  # 新角色
                    merged_doc["character_profiles"][char_name] = incremental_profile_update
                    # 确保新角色有 first_appearance_chapter
                    if "first_appearance_chapter" not in merged_doc["character_profiles"][char_name] or \
                            merged_doc["character_profiles"][char_name].get(
                                "first_appearance_chapter") is None:  # LLM 可能不提供或提供null
                        merged_doc["character_profiles"][char_name]["first_appearance_chapter"] = current_chapter_number
                else:  # 更新现有角色
                    existing_profile = merged_doc["character_profiles"][char_name]
                    # 更新描述 (假设LLM提供完整的新描述)
                    if "description" in incremental_profile_update and incremental_profile_update["description"]:
                        existing_profile["description"] = incremental_profile_update["description"]

                    # 合并列表型字段 (personality_traits, motivations)
                    for list_key in ["personality_traits", "motivations"]:
                        if list_key in incremental_profile_update and isinstance(incremental_profile_update[list_key],
                                                                                 list):
                            existing_profile.setdefault(list_key, [])
                            existing_items_str = {str(item) for item in existing_profile[list_key]}
                            for item in incremental_profile_update[list_key]:
                                if str(item) not in existing_items_str: existing_profile[list_key].append(item)

                    # 更新 relationships (简单覆盖或更新)
                    if "relationships" in incremental_profile_update and isinstance(
                            incremental_profile_update["relationships"], dict):
                        existing_profile.setdefault("relationships", {}).update(
                            incremental_profile_update["relationships"])

                    # 追加 key_developments
                    if "key_developments" in incremental_profile_update and isinstance(
                            incremental_profile_update["key_developments"], list):
                        existing_profile.setdefault("key_developments", [])
                        for dev in incremental_profile_update["key_developments"]:
                            if isinstance(dev, dict) and dev.get("chapter") == current_chapter_number:  # 确保是本章发展
                                # 避免重复添加完全相同的发展记录 (简单检查描述和事件ID)
                                is_duplicate_dev = False
                                for existing_dev in existing_profile["key_developments"]:
                                    if existing_dev.get("chapter") == dev.get("chapter") and \
                                            existing_dev.get("event_ref_id") == dev.get("event_ref_id") and \
                                            existing_dev.get("development_summary") == dev.get("development_summary"):
                                        is_duplicate_dev = True
                                        break
                                if not is_duplicate_dev:
                                    existing_profile["key_developments"].append(dev)

        # 5. 合并 unresolved_questions_or_themes_from_original (追加新项)
        inc_unresolved = incremental_llm_output.get("unresolved_questions_or_themes_from_original")
        if isinstance(inc_unresolved, list):
            merged_doc.setdefault("unresolved_questions_or_themes_from_original", [])
            existing_items_str = {str(item) for item in merged_doc["unresolved_questions_or_themes_from_original"]}
            for new_item in inc_unresolved:
                if str(new_item) not in existing_items_str:
                    merged_doc["unresolved_questions_or_themes_from_original"].append(new_item)

        return merged_doc

    def preprocess_novel(self, novel_txt_path: str) -> Optional[Tuple[str, str]]:
        self.novel_file_path = novel_txt_path
        novel_name_for_dir = utils.sanitize_filename(os.path.splitext(os.path.basename(novel_txt_path))[0])
        self.novel_specific_data_dir = os.path.join(self.project_data_dir, novel_name_for_dir)
        os.makedirs(self.novel_specific_data_dir, exist_ok=True)

        self.chapters_data_path = config.get_novel_data_path(self.novel_specific_data_dir,
                                                             config.CHAPTERS_DATA_FILENAME)
        self.analysis_in_progress_path = config.get_novel_data_path(self.novel_specific_data_dir,
                                                                    config.NOVEL_ANALYSIS_IN_PROGRESS_FILENAME)
        self.final_analysis_path = config.get_novel_data_path(self.novel_specific_data_dir,
                                                              config.NOVEL_ANALYSIS_FILENAME)
        self.processed_event_ids = set()

        print(f"开始预处理: {novel_txt_path}")
        novel_content = utils.read_file_content(novel_txt_path)
        if not novel_content: return None
        novel_md5 = utils.calculate_md5(novel_txt_path)
        if not novel_md5:
            print("无法计算小说的MD5哈希值。")
            return None
        print(f"小说MD5: {novel_md5}")
        chapters = utils.split_text_into_chapters(novel_content, config.CHAPTER_SPLIT_REGEX)
        if not chapters:
            print("无法将小说分割成章节。请检查正则表达式或小说格式。")
            return None
        utils.write_json_file(chapters, self.chapters_data_path)
        print(f"小说章节已保存到: {self.chapters_data_path}")
        return self.chapters_data_path, novel_md5

    def perform_global_analysis(self, chapters_data_path: str, novel_md5: str, novel_title: str, ollama_model: str) -> \
            Optional[str]:
        print(f"开始对小说进行全局分析: {novel_title} (模型: {ollama_model})")
        chapters_data = utils.read_json_file(chapters_data_path)
        if not chapters_data:
            print(f"无法从 {chapters_data_path} 读取章节数据")
            return None

        current_analysis_doc = self._initialize_analysis_document(novel_title, novel_md5)
        utils.write_json_file(current_analysis_doc, self.analysis_in_progress_path)  # 初始空文档
        print(f"已初始化分析文档于: {self.analysis_in_progress_path}")

        num_chapters_in_data = len(chapters_data)
        max_retries_per_batch = 2
        current_chapter_data_index = 0
        batch_iteration_count = 0

        while current_chapter_data_index < num_chapters_in_data:
            batch_iteration_count += 1
            current_chapter_text_for_llm = ""
            representative_chapter_number_for_llm_prompt = -1
            chapters_processed_in_this_batch_objects = []
            num_chapters_to_advance_data_index = 0

            is_first_iteration_for_analysis = (batch_iteration_count == 1)

            if is_first_iteration_for_analysis and num_chapters_in_data >= 2:
                chap_0_data = chapters_data[0]
                chap_1_data = chapters_data[1]
                is_chap_0_prologue = (chap_0_data.get("chapter_number") == 0 or \
                                      any(kw in chap_0_data.get("title", "").lower() for kw in
                                          ["序", "前言", "prologue", "foreword"]))
                is_chap_1_first_chapter = (chap_1_data.get("chapter_number") == 1)

                if is_chap_0_prologue and is_chap_1_first_chapter:
                    print(
                        f"初始分析批次：合并 序章 (实际章节号 {chap_0_data['chapter_number']}) 和 第1章 (实际章节号 {chap_1_data['chapter_number']})。")
                    prologue_text = f"【原文参考：第 {chap_0_data['chapter_number']} 章 - {chap_0_data.get('title', '无标题')}】\n{chap_0_data['content']}"
                    first_chapter_text = f"【原文参考：第 {chap_1_data['chapter_number']} 章 - {chap_1_data.get('title', '无标题')}】\n{chap_1_data['content']}"
                    current_chapter_text_for_llm = f"{prologue_text}\n\n---\n\n{first_chapter_text}"
                    representative_chapter_number_for_llm_prompt = chap_1_data['chapter_number']
                    chapters_processed_in_this_batch_objects.extend([chap_0_data, chap_1_data])
                    num_chapters_to_advance_data_index = 2
                else:
                    current_chapter_info = chapters_data[current_chapter_data_index]
                    print(
                        f"初始分析批次：单独处理章节索引 {current_chapter_data_index} (实际章节号 {current_chapter_info['chapter_number']})。")
                    current_chapter_text_for_llm = current_chapter_info["content"]
                    representative_chapter_number_for_llm_prompt = current_chapter_info["chapter_number"]
                    chapters_processed_in_this_batch_objects.append(current_chapter_info)
                    num_chapters_to_advance_data_index = 1
            else:
                if current_chapter_data_index < num_chapters_in_data:
                    current_chapter_info = chapters_data[current_chapter_data_index]
                    current_chapter_text_for_llm = current_chapter_info["content"]
                    representative_chapter_number_for_llm_prompt = current_chapter_info["chapter_number"]
                    chapters_processed_in_this_batch_objects.append(current_chapter_info)
                    num_chapters_to_advance_data_index = 1
                else:
                    break

            if not current_chapter_text_for_llm.strip() and not chapters_processed_in_this_batch_objects[0].get("title",
                                                                                                                "").strip():
                print(f"跳过处理空的章节/批次 (代表章节号: {representative_chapter_number_for_llm_prompt})")
                current_chapter_data_index += num_chapters_to_advance_data_index
                continue

            print(f"处理分析批次 {batch_iteration_count} (代表章节号: {representative_chapter_number_for_llm_prompt}, "
                  f"包含实际章节号(s): {[ch['chapter_number'] for ch in chapters_processed_in_this_batch_objects]})")

            batch_processed_successfully = False
            # 读取上一次的分析文档，作为本次增量合并的基础
            # 注意：current_analysis_doc 在循环外初始化，并在循环内被 _merge_incremental_analysis 更新
            # 所以这里传递给 prompt 的应该是 current_analysis_doc 的当前状态
            previous_doc_for_prompt = json.loads(json.dumps(current_analysis_doc))  # 深拷贝以防意外修改

            for attempt in range(max_retries_per_batch + 1):
                analysis_prompt_text = prompts.get_novel_analysis_prompt(
                    json.dumps(previous_doc_for_prompt, ensure_ascii=False, indent=2),
                    current_chapter_text_for_llm,
                    representative_chapter_number_for_llm_prompt
                )
                messages = [{"role": "user", "content": analysis_prompt_text}]

                print(
                    f"请求Ollama分析 (代表章节 {representative_chapter_number_for_llm_prompt}, 尝试 {attempt + 1}/{max_retries_per_batch + 1})...")
                llm_response_data = self.ollama_client.generate_chat_completion(
                    model=ollama_model, messages=messages, stream=False, expect_json_in_content=True
                )

                if llm_response_data and llm_response_data.get("message") and isinstance(
                        llm_response_data["message"].get("content"), dict):
                    incremental_llm_output = llm_response_data["message"]["content"]

                    current_analysis_doc = self._merge_incremental_analysis(  # 更新 current_analysis_doc
                        previous_doc_for_prompt,  # 基于上一个稳定版本进行合并
                        incremental_llm_output,
                        representative_chapter_number_for_llm_prompt
                    )

                    utils.write_json_file(current_analysis_doc, self.analysis_in_progress_path)
                    print(
                        f"成功合并并保存了代表章节 {representative_chapter_number_for_llm_prompt} 后的分析 (尝试 {attempt + 1})")
                    batch_processed_successfully = True
                    break
                else:
                    print(
                        f"LLM未返回有效的增量分析字典或API出错（代表章节 {representative_chapter_number_for_llm_prompt}，尝试 {attempt + 1}）。LLM 响应: {llm_response_data}")
                    if attempt < max_retries_per_batch:
                        print("正在重试...")
                    else:
                        print(
                            f"代表章节 {representative_chapter_number_for_llm_prompt} 在 {max_retries_per_batch + 1} 次尝试后仍失败。")
                        batch_processed_successfully = False;
                        break

            if not batch_processed_successfully:
                print(f"批次 (代表章节 {representative_chapter_number_for_llm_prompt}) 未能成功处理并被跳过。")

            current_chapter_data_index += num_chapters_to_advance_data_index

        # 在所有章节处理完毕后，最后对整个文档的事件ID进行一次最终的唯一性确保
        current_analysis_doc = self._ensure_unique_event_ids(current_analysis_doc)
        utils.write_json_file(current_analysis_doc, self.final_analysis_path)
        print(f"全局小说分析完成。最终分析已保存到: {self.final_analysis_path}")
        return self.final_analysis_path

    def run_stage1(self, novel_txt_path: str, ollama_model: str) -> Optional[Tuple[str, str, str]]:
        print("--- 阶段 1：小说预处理与初始分析 ---")
        preprocess_result = self.preprocess_novel(novel_txt_path)
        if not preprocess_result:
            print("小说预处理失败。")
            return None
        chapters_path, novel_md5 = preprocess_result
        novel_title_for_analysis = utils.sanitize_filename(os.path.splitext(os.path.basename(novel_txt_path))[0])
        final_analysis_file_path = self.perform_global_analysis(chapters_path, novel_md5, novel_title_for_analysis,
                                                                ollama_model)
        if not final_analysis_file_path:
            print("小说全局分析失败。")
            return None
        print("--- 阶段 1 成功完成 ---")
        return chapters_path, final_analysis_file_path, self.novel_specific_data_dir


if __name__ == "__main__":
    print("测试 NovelProcessor (阶段 1)... 需要运行中的Ollama实例和示例小说。")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    test_novel_basename = "sample_novel_for_processor_incremental_v2"  # 更新测试名
    sample_novel_path = os.path.join(config.DATA_DIR, f"{test_novel_basename}.txt")
    sample_novel_content = """
序章：世界的起源
这是小说的序章部分，描述了世界的背景和一些古老的传说。例如，远古的神祇。 还提到了一个关键地点：失落之城。
第一章 冒险的召唤
这是第一章的内容。主角李四登场。他发现了一个神秘的卷轴。
李四在一个偏远的小村庄长大，对外面的世界充满向往。他的性格特点是勇敢但有些鲁莽。
一天，一位神秘的旅者来到了村庄，带来了一个改变李四命运的消息。这是事件 Chap1_Traveler_Arrives。旅者名叫艾尔。艾尔看起来经验丰富。

第二章 踏上征途
李四决定跟随旅者艾尔离开村庄，开始了他的冒险。他们的目的地是寻找失落之城。
旅途中充满了未知与危险。事件 Chap2_Journey_Begins。他们遇到了狼群。
艾尔展现了他的魔法能力，击退了狼群。李四对此感到非常惊讶。这是李四的关键发展：初识魔法。
    """
    with open(sample_novel_path, "w", encoding="utf-8") as f:
        f.write(sample_novel_content)

    ollama_client_instance = OllamaClient(default_model=config.DEFAULT_OLLAMA_MODEL)  # 使用config中的默认模型
    # ollama_client_instance.default_model = "qwen2:7b-instruct-q8_0" # 或者在这里指定一个测试模型

    print(f"将使用Ollama模型: {ollama_client_instance.default_model} (如果 select_model 返回 None 或被跳过)")
    # 为了自动化测试，可以注释掉交互式选择，直接使用默认模型或特定模型
    # selected_model = ollama_client_instance.select_model()
    selected_model = ollama_client_instance.default_model  # 直接使用默认或上面指定的模型

    if not selected_model:
        print(
            f"警告：未选择或指定Ollama模型，将尝试使用客户端默认模型 {ollama_client_instance.default_model} (如果已设置)。")
        selected_model = ollama_client_instance.default_model

    if not selected_model:
        print("错误：无可用Ollama模型。中止测试。")
    else:
        print(f"最终使用Ollama模型: {selected_model} 进行测试。")
        processor = NovelProcessor(ollama_client_instance)
        stage1_output = processor.run_stage1(sample_novel_path, selected_model)
        if stage1_output:
            ch_path, analysis_file, novel_data_dir_output = stage1_output
            print(f"阶段1测试成功。")
            print(f"  章节文件: {ch_path}")
            print(f"  分析文件: {analysis_file}")
            print(f"  小说数据目录: {novel_data_dir_output}")

            analysis_content_test = utils.read_json_file(analysis_file)
            assert analysis_content_test is not None, "未能读取分析文件"
            print("\n最终分析内容概览:")
            print(f"  小说标题: {analysis_content_test.get('novel_title')}")
            print(f"  世界观概述长度: {len(analysis_content_test.get('world_setting', {}).get('overview', ''))}")
            print(f"  主线总结长度: {len(analysis_content_test.get('main_plotline_summary', ''))}")
            print(f"  事件数量: {len(analysis_content_test.get('detailed_timeline_and_key_events', []))}")
            print(f"  角色数量: {len(analysis_content_test.get('character_profiles', {}))}")

            events = analysis_content_test.get("detailed_timeline_and_key_events", [])
            characters = analysis_content_test.get("character_profiles", {})

            print("\n部分事件验证:")
            chap1_event_found = False
            chap2_event_found = False
            for event in events:
                print(
                    f"  - Event ID: {event.get('event_id')}, Desc: {event.get('description', '')[:40]}..., Chapter: {event.get('chapter_approx')}")
                if event.get("chapter_approx") == 1 and "Chap1_Traveler_Arrives" in event.get("description", ""):
                    chap1_event_found = True
                if event.get("chapter_approx") == 2 and "Chap2_Journey_Begins" in event.get("description", ""):
                    chap2_event_found = True

            assert chap1_event_found, "测试失败：未能在分析结果中找到标记为第1章的 'Chap1_Traveler_Arrives' 事件。"
            assert chap2_event_found, "测试失败：未能在分析结果中找到标记为第2章的 'Chap2_Journey_Begins' 事件。"
            print("事件章节归属初步验证通过。")

            print("\n部分角色验证:")
            assert "李四" in characters, "测试失败：角色 '李四' 未被提取。"
            print(f"  角色 '李四': {characters.get('李四', {}).get('description', '')[:50]}...")
            assert "艾尔" in characters, "测试失败：角色 '艾尔' 未被提取。"
            print(
                f"  角色 '艾尔': {characters.get('艾尔', {}).get('description', '')[:50]}..., 首次出现章节: {characters.get('艾尔', {}).get('first_appearance_chapter')}")

            if "艾尔" in characters:
                assert characters["艾尔"].get("first_appearance_chapter") == 1, \
                    f"角色 '艾尔' 的首次出现章节应为1, 实际为: {characters['艾尔'].get('first_appearance_chapter')}"
            print("角色提取及首次出现章节初步验证通过。")

        else:
            print("阶段1测试失败。")
    # if os.path.exists(sample_novel_path): # 保留测试文件以供检查
    #     pass
    print(f"\nNovelProcessor 测试完成。请检查 '{os.path.join(config.DATA_DIR, test_novel_basename)}' 目录下的输出文件。")