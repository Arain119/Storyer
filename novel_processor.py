# novel_processor.py
# 该文件处理小说的分析和处理。

import os
import json
import time
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple
import utils

class NovelProcessor:
    """小说处理器类，负责分析和处理上传的小说。"""

    def __init__(self, llm_client, novel_file_path: str, output_dir: str):
        """
        初始化小说处理器。

        Args:
            llm_client: LLM客户端实例。
            novel_file_path: 小说文件路径。
            output_dir: 输出目录路径。
        """
        self.llm_client = llm_client
        self.novel_file_path = novel_file_path
        self.output_dir = output_dir
        self.chapters_dir = os.path.join(output_dir, 'chapters')
        self.final_analysis_path = os.path.join(output_dir, 'final_analysis.json')
        self.analysis_in_progress_path = os.path.join(output_dir, 'analysis_in_progress.json')
        self.processed_event_ids = set()

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.chapters_dir, exist_ok=True)

    def process_novel(self) -> bool:
        """
        处理小说文件。

        Returns:
            如果处理成功则返回True，否则返回False。
        """
        try:
            # 读取小说内容
            novel_content = utils.read_text_file(self.novel_file_path)
            if not novel_content:
                print(f"无法读取小说文件: {self.novel_file_path}")
                return False

            # 计算MD5
            novel_md5 = utils.calculate_md5(self.novel_file_path)
            if not novel_md5:
                print("无法计算小说的MD5哈希值。")
                return False

            # 提取小说标题
            novel_title = os.path.splitext(os.path.basename(self.novel_file_path))[0]

            # 分割章节
            chapters_content_list = self._split_into_chapters(novel_content)  # 返回章节内容字符串列表
            if not chapters_content_list:
                print("无法将小说分割成章节。")
                return False

            # 保存章节并构建章节数据列表
            chapters_data = []
            for i, chapter_text_content in enumerate(chapters_content_list):
                # 尝试从章节文本内容中提取实际章节号和标题
                # 这假设 _split_into_chapters 返回的每个元素都包含了章节标题行
                title_match = re.search(r'^(第[一二三四五六七八九十百千万\d]+章.*?)$|^(Chapter\s+\d+.*?)$',
                                        chapter_text_content.splitlines()[0] if chapter_text_content else "",
                                        re.MULTILINE)
                chapter_number_from_title = i + 1  # 默认章节号
                title_from_text = f"第{chapter_number_from_title}章"

                if title_match:
                    extracted_title = title_match.group(1) or title_match.group(2)
                    if extracted_title:
                        title_from_text = extracted_title.strip()
                        # 尝试从标题提取数字章节号 (更鲁棒的提取方式可能需要)
                        num_match = re.search(r'(\d+)', title_from_text)
                        if num_match:
                            chapter_number_from_title = int(num_match.group(1))

                # 确保 chapter_number_from_title 是一个有效的数字，以防万一
                if not isinstance(chapter_number_from_title, int) or chapter_number_from_title < 0:
                    print(f"警告: 章节 '{title_from_text[:30]}...' 的章节号提取异常，使用默认值 {i + 1}")
                    chapter_number_from_title = i + 1

                chapter_path = os.path.join(self.chapters_dir, f'chapter_{chapter_number_from_title:03d}.txt')

                # --- 调试信息 ---
                # print(f"DEBUG: 准备写入章节。章节号: {chapter_number_from_title}, 路径: '{chapter_path}'")
                # print(f"DEBUG: 章节内容 (前100字符): {chapter_text_content[:100]}")
                if not chapter_path or not self.chapters_dir:
                    print(
                        f"错误: 无效的 chapter_path ('{chapter_path}') 或 self.chapters_dir ('{self.chapters_dir}') 用于章节 {chapter_number_from_title}")
                    continue  # 跳过此章节的写入

                # *** 修正参数顺序 ***
                success_write_chapter = utils.write_text_file(chapter_path, chapter_text_content)
                if not success_write_chapter:
                    print(f"写入章节 {chapter_number_from_title} 到 {chapter_path} 失败。")
                    # 根据需求决定是否要因为单章节写入失败而中止整个过程
                    # return False

                chapter_data_entry = {
                    "chapter_number": chapter_number_from_title,
                    "title": title_from_text,
                    "content": chapter_text_content,  # 存储包含标题的完整章节文本
                    "path": chapter_path
                }
                chapters_data.append(chapter_data_entry)

            # 保存章节数据 (包含章节号、标题、原始内容、路径的列表)
            chapters_data_path = os.path.join(self.output_dir, 'chapters_data.json')
            utils.write_json_file(chapters_data, chapters_data_path)
            print(f"章节数据已保存到: {chapters_data_path}")

            # 分析小说
            # _analyze_novel 现在接收 chapters_data (字典列表)
            analysis_result_doc = self._analyze_novel(chapters_data, novel_md5, novel_title)

            if analysis_result_doc:
                # _extract_final_analysis 将内部的分析文档转换为前端期望的格式
                final_output_for_frontend = self._extract_final_analysis(analysis_result_doc, chapters_data)

                # 保存最终格式化的分析结果
                success_writing_final = utils.write_json_file(final_output_for_frontend, self.final_analysis_path)
                if success_writing_final:
                    print(f"最终分析结果已成功写入文件: {self.final_analysis_path}")
                    return True
                else:
                    print(f"最终分析结果写入文件 {self.final_analysis_path} 失败。")
                    return False
            else:
                print("小说分析未能生成结果。")
                return False

        except Exception as e:
            print(f"处理小说时出错: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印更详细的堆栈信息
            return False

    def _split_into_chapters(self, content: str) -> List[str]:
        """
        将小说内容分割为章节。此版本返回每个章节的完整文本（包括标题行）。
        Args:
            content: 小说内容。
        Returns:
            章节内容字符串列表。
        """
        # 正则表达式查找章节标题行
        # 匹配 "第X章" (X可以是中文数字或阿拉伯数字) 或 "Chapter X"
        # 确保它匹配行首（可能前面有空格）
        chapter_pattern = r"^\s*(?:第[一二三四五六七八九十百千万零\d]+章(?:[^\n]*)|Chapter\s+\d+(?:[^\n]*))"

        parts = re.split(f'({chapter_pattern})', content, flags=re.MULTILINE)
        chapters_content = []

        current_content_buffer = ""
        if parts and parts[0].strip():
            # 如果第一部分不是章节标题，则视为序言或前置内容
            if not re.match(chapter_pattern, parts[0].strip(), re.MULTILINE):
                current_content_buffer = "序言\n" + parts[0].strip()
            else:  # 如果第一部分就是章节标题（不太可能，因为split会把它单独列出）
                current_content_buffer = parts[0].strip()

        idx = 1
        while idx < len(parts):
            title_part = parts[idx].strip()  # 这是章节标题
            content_part = ""
            if idx + 1 < len(parts):
                content_part = parts[idx + 1]  # 保留原始的空白符，strip()在后面处理

            if current_content_buffer and not title_part.startswith(current_content_buffer.splitlines()[0]):
                # 如果buffer中有内容，且当前title不是buffer的开头（意味着buffer是独立的章节）
                chapters_content.append(current_content_buffer.strip())
                current_content_buffer = ""

            if title_part:  # 这是一个新的章节的开始
                if current_content_buffer:  # 将之前累积的非标题内容作为一章
                    chapters_content.append(current_content_buffer.strip())
                current_content_buffer = title_part + "\n" + content_part
            else:  # title_part为空，content_part应该追加到current_content_buffer
                current_content_buffer += content_part

            idx += 2

        # 添加最后一个累积的章节
        if current_content_buffer.strip():
            chapters_content.append(current_content_buffer.strip())

        # 如果完全没有分割，则将整个文本视为一个章节
        if not chapters_content and content.strip():
            print("警告：未使用章节模式分割文本，将整个内容视为单一章节。")
            chapters_content.append(content.strip())

        return [ch_content for ch_content in chapters_content if ch_content.strip()]

    def _analyze_novel(self, chapters_data: List[Dict[str, Any]], novel_md5: str, novel_title: str) -> Optional[
        Dict[str, Any]]:
        """
        使用LLM分析小说内容。
        Args:
            chapters_data: 章节数据字典列表。
            novel_md5: 小说文件的MD5哈希值。
            novel_title: 小说标题。
        Returns:
            包含完整分析结果的字典，如果分析失败则返回None。
        """
        try:
            print(f"开始对小说进行全局分析: {novel_title}")

            current_analysis_doc = self._initialize_analysis_document(novel_title, novel_md5)
            utils.write_json_file(current_analysis_doc, self.analysis_in_progress_path)
            print(f"已初始化分析文档于: {self.analysis_in_progress_path}")

            # num_chapters = len(chapters_data) # 未使用

            for chapter_info in chapters_data:
                current_chapter_content = chapter_info["content"]  # 包含标题的完整章节内容
                current_chapter_number = chapter_info["chapter_number"]

                print(f"正在分析章节 {current_chapter_number}: {chapter_info['title'][:30]}...")

                prompt_for_llm = self._build_analysis_prompt(
                    current_chapter_content,
                    current_analysis_doc,
                    current_chapter_number
                )

                incremental_analysis = self._call_llm_for_analysis(prompt_for_llm)

                if incremental_analysis:
                    current_analysis_doc = self._merge_incremental_analysis(
                        current_analysis_doc, incremental_analysis, current_chapter_number
                    )
                    current_analysis_doc = self._ensure_unique_event_ids(current_analysis_doc)
                    utils.write_json_file(current_analysis_doc, self.analysis_in_progress_path)
                    print(f"已完成章节 {current_chapter_number} 的分析并合并结果。")
                else:
                    print(f"分析章节 {current_chapter_number} 时LLM未能返回有效增量数据，跳过此章节的合并。")

            print(f"所有章节分析迭代完成。最终分析文档（内部格式）保存在: {self.analysis_in_progress_path}")
            return current_analysis_doc

        except Exception as e:
            print(f"分析小说过程中发生严重错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _initialize_analysis_document(self, novel_title: str, novel_md5: str) -> Dict[str, Any]:
        """初始化内部使用的分析文档结构"""
        return {
            "novel_title": novel_title,
            "source_text_md5": novel_md5,
            "world_setting": {"overview": "", "rules_and_systems": [], "key_locations": [], "major_factions": [],
                              "culture_and_customs": ""},
            "main_plotline_summary": "",
            "detailed_timeline_and_key_events": [],
            "character_profiles": {},
            "unresolved_questions_or_themes_from_original": []
        }

    def _build_analysis_prompt(self, chapter_text_for_analysis: str, previous_analysis_doc: Dict[str, Any],
                               chapter_number_for_context: int) -> str:
        """
        构建用于LLM分析单个章节的提示。
        """
        previous_analysis_json_str = json.dumps(previous_analysis_doc, ensure_ascii=False, indent=2)
        # 提示词内容与之前版本相同，此处省略以减少重复。
        # 实际项目中应确保这里调用 prompts.get_novel_analysis_prompt 或保持一致的提示逻辑。
        # 为了简洁，我们假设提示词不变。
        # from prompts import get_novel_analysis_prompt
        # return get_novel_analysis_prompt(previous_analysis_json_str, chapter_text_for_analysis, chapter_number_for_context)

        # 使用内部定义的简化版提示（与您之前版本类似）
        prompt = f"""你是一位专业的小说分析师。请分析以下小说章节内容（代表章节号：{chapter_number_for_context}），并在之前分析的基础上进行增量更新。

之前的分析摘要 (JSON格式):
{previous_analysis_json_str}

当前章节文本:
{chapter_text_for_analysis}

请严格根据【当前章节文本】分析，并输出一个JSON对象，仅包含从当前章节新提取或需要更新的信息。
字段结构应与上述 "之前的分析摘要" 中的各部分（如 world_setting, main_plotline_summary, detailed_timeline_and_key_events, character_profiles, unresolved_questions_or_themes_from_original）保持一致。
对于列表型字段（如 key_locations, detailed_timeline_and_key_events, personality_traits），只输出新增项。
对于文本型字段（如 overview, main_plotline_summary, description），如果当前章节有补充，请提供补充文本。
对于 character_profiles，如果出现新角色，请创建完整档案；如果现有角色有更新，只提供更新的字段。
事件ID请使用 "temp_event_描述" 格式。程序会自动处理章节号和最终ID。
"""
        return prompt

    def _call_llm_for_analysis(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用LLM进行分析，并期望返回JSON"""
        if not self.llm_client:
            print("LLM客户端未初始化，无法进行分析。")
            return None

        try:
            messages = [
                {"role": "system", "content": "你是一个小说分析助手，请严格按照用户要求的格式输出JSON对象。"},
                {"role": "user", "content": prompt}
            ]
            # 假设 self.llm_client.chat_completion 能够处理期望JSON的逻辑
            # 例如，通过内部参数或提示词本身。
            # 如果使用的是 OllamaClient, 它有一个 expect_json_in_content 参数
            # 如果是 GenericOnlineAPIClient, 它也有类似的参数
            # 我们需要确保 LLMClient 实例正确配置或调用时传递该参数

            # 尝试获取原始客户端（如果是LLMClient的包装器）或直接调用
            # 这里的调用方式取决于 LLMClient 的具体实现
            raw_response_content = None
            if hasattr(self.llm_client, 'generate_chat_completion'):  # 检查是否是LLMClientInterface的实现
                # 假设模型名称是从 self.llm_client.default_model 或其他地方获取
                model_to_use = self.llm_client.default_model if hasattr(self.llm_client,
                                                                        'default_model') else "default"  # 需要确认模型名来源

                response_dict = self.llm_client.generate_chat_completion(
                    model=model_to_use,  # 需要提供模型名称
                    messages=messages,
                    expect_json_in_content=True  # 明确要求JSON
                )
                if response_dict and "message" in response_dict and "content" in response_dict["message"]:
                    raw_response_content = response_dict["message"]["content"]
                elif response_dict and isinstance(response_dict.get("content"), str):  # 有些API直接返回content
                    raw_response_content = response_dict.get("content")

            elif hasattr(self.llm_client, 'chat_completion'):  # 如果是旧版的LLMClient
                raw_response_content = self.llm_client.chat_completion(
                    messages,
                    # 确保旧版 chat_completion 也能处理 JSON 格式要求，可能需要修改 LLMClient
                    # 或者依赖提示词强制JSON输出
                )
            else:
                print("错误: LLM客户端没有可识别的聊天完成方法。")
                return None

            if not raw_response_content:
                print("LLM为分析调用返回了空响应。")
                return None

            json_str_from_llm = raw_response_content
            match_code_block = re.search(r"```json\s*([\s\S]+?)\s*```", raw_response_content)
            if match_code_block:
                json_str_from_llm = match_code_block.group(1)

            try:
                analysis_result = json.loads(json_str_from_llm)
                if isinstance(analysis_result, dict):
                    return analysis_result
                else:
                    print(f"LLM为分析调用返回了有效的JSON但不是一个对象: {type(analysis_result)}")
                    return None
            except json.JSONDecodeError as e:
                print(f"解析LLM的分析响应JSON失败: {e}")
                print(f"LLM原始响应 (或提取的JSON部分): {json_str_from_llm[:500]}...")
                return None

        except Exception as e:
            print(f"调用LLM进行分析时发生严重错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _ensure_unique_event_ids(self, analysis_doc: Dict[str, Any]) -> Dict[str, Any]:
        """确保分析文档中的所有事件ID都是唯一的。"""
        if "detailed_timeline_and_key_events" not in analysis_doc or \
                not isinstance(analysis_doc["detailed_timeline_and_key_events"], list):
            analysis_doc["detailed_timeline_and_key_events"] = []
            return analysis_doc

        temp_id_to_final_id_map = {}
        new_event_list = []
        # self.processed_event_ids 在 __init__ 中初始化

        for event in analysis_doc["detailed_timeline_and_key_events"]:
            if not isinstance(event, dict):
                continue

            original_event_id = event.get("event_id")
            final_id = original_event_id

            # 检查ID是否已经是最终格式且在本轮运行中唯一
            is_final_format = (
                    isinstance(original_event_id, str) and
                    original_event_id.startswith("E") and
                    len(original_event_id) == 7 and
                    original_event_id[1:].isalnum()
            )

            if not is_final_format or original_event_id in self.processed_event_ids:
                # 如果不是最终格式，或者是最终格式但已存在（可能来自不同章节的相同临时ID），则生成新的
                new_uuid_part = uuid.uuid4().hex[:6].upper()
                final_id = f"E{new_uuid_part}"
                while final_id in self.processed_event_ids:
                    new_uuid_part = uuid.uuid4().hex[:6].upper()
                    final_id = f"E{new_uuid_part}"

            event["event_id"] = final_id
            self.processed_event_ids.add(final_id)

            if original_event_id and original_event_id != final_id and not original_event_id.startswith("E"):
                temp_id_to_final_id_map[original_event_id] = final_id

            new_event_list.append(event)

        analysis_doc["detailed_timeline_and_key_events"] = new_event_list

        if temp_id_to_final_id_map and "character_profiles" in analysis_doc:
            for char_name, profile in analysis_doc.get("character_profiles", {}).items():
                if isinstance(profile, dict) and "key_developments" in profile and isinstance(
                        profile["key_developments"], list):
                    for dev_event in profile["key_developments"]:
                        if isinstance(dev_event, dict) and dev_event.get("event_ref_id") in temp_id_to_final_id_map:
                            dev_event["event_ref_id"] = temp_id_to_final_id_map[dev_event["event_ref_id"]]
        return analysis_doc

    def _merge_incremental_analysis(self, previous_doc: Dict[str, Any], incremental_output: Dict[str, Any],
                                    current_chapter_number_context: int) -> Dict[str, Any]:
        """
        将LLM返回的增量分析结果合并到主分析文档中。
        Args:
            previous_doc: 当前累积的完整分析文档。
            incremental_output: LLM针对当前章节返回的增量JSON对象。
            current_chapter_number_context: 当前处理章节的代表性章节号。
        """
        merged_doc = json.loads(json.dumps(previous_doc))

        inc_ws = incremental_output.get("world_setting")
        if isinstance(inc_ws, dict):
            base_ws = merged_doc.setdefault("world_setting", {})
            for text_field in ["overview", "culture_and_customs"]:
                if inc_ws.get(text_field) and isinstance(inc_ws[text_field], str):
                    current_base_text = base_ws.get(text_field, "")
                    base_ws[text_field] = (
                                current_base_text + "\n" + inc_ws[text_field]).strip() if current_base_text else inc_ws[
                        text_field]
            for list_field in ["rules_and_systems", "key_locations", "major_factions"]:
                if inc_ws.get(list_field) and isinstance(inc_ws[list_field], list):
                    base_list = base_ws.setdefault(list_field, [])
                    existing_items_json = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in base_list if
                                           isinstance(item, (dict, list))}
                    existing_simple_items = {item for item in base_list if not isinstance(item, (dict, list))}

                    for new_item in inc_ws[list_field]:
                        if isinstance(new_item, (dict, list)):
                            new_item_json = json.dumps(new_item, sort_keys=True, ensure_ascii=False)
                            if new_item_json not in existing_items_json:
                                base_list.append(new_item)
                                existing_items_json.add(new_item_json)
                        elif new_item not in existing_simple_items:
                            base_list.append(new_item)
                            existing_simple_items.add(new_item)

        inc_plot_summary = incremental_output.get("main_plotline_summary")
        if inc_plot_summary and isinstance(inc_plot_summary, str):
            current_base_summary = merged_doc.get("main_plotline_summary", "")
            chapter_contribution = f"(来自第 {current_chapter_number_context} 章分析): {inc_plot_summary}"
            merged_doc["main_plotline_summary"] = (
                        current_base_summary + "\n---\n" + chapter_contribution).strip() if current_base_summary else chapter_contribution

        inc_events = incremental_output.get("detailed_timeline_and_key_events")
        if isinstance(inc_events, list):
            base_events = merged_doc.setdefault("detailed_timeline_and_key_events", [])
            for new_event_data in inc_events:
                if isinstance(new_event_data, dict):
                    new_event_data["chapter_approx"] = current_chapter_number_context
                    base_events.append(new_event_data)  # event_id 在 _ensure_unique_event_ids 中处理

        inc_profiles = incremental_output.get("character_profiles")
        if isinstance(inc_profiles, dict):
            base_profiles = merged_doc.setdefault("character_profiles", {})
            for char_name, inc_profile_data in inc_profiles.items():
                if not isinstance(inc_profile_data, dict): continue
                if char_name not in base_profiles:
                    inc_profile_data["first_appearance_chapter"] = inc_profile_data.get("first_appearance_chapter",
                                                                                        current_chapter_number_context)
                    base_profiles[char_name] = inc_profile_data
                else:
                    char_profile_to_update = base_profiles[char_name]
                    if inc_profile_data.get("description") and isinstance(inc_profile_data["description"], str):
                        char_profile_to_update["description"] = inc_profile_data["description"]
                    for list_attr in ["personality_traits", "motivations"]:
                        if inc_profile_data.get(list_attr) and isinstance(inc_profile_data[list_attr], list):
                            base_attr_list = char_profile_to_update.setdefault(list_attr, [])
                            for item in inc_profile_data[list_attr]:
                                if item not in base_attr_list: base_attr_list.append(item)
                    if inc_profile_data.get("relationships") and isinstance(inc_profile_data["relationships"], dict):
                        char_profile_to_update.setdefault("relationships", {}).update(inc_profile_data["relationships"])
                    if inc_profile_data.get("key_developments") and isinstance(inc_profile_data["key_developments"],
                                                                               list):
                        base_dev_list = char_profile_to_update.setdefault("key_developments", [])
                        for dev_item in inc_profile_data["key_developments"]:
                            if isinstance(dev_item, dict):
                                dev_item["chapter"] = dev_item.get("chapter", current_chapter_number_context)
                                is_duplicate = any(
                                    existing_dev.get("chapter") == dev_item["chapter"] and
                                    existing_dev.get("event_ref_id") == dev_item.get("event_ref_id") and
                                    existing_dev.get("development_summary") == dev_item.get("development_summary")
                                    for existing_dev in base_dev_list
                                )
                                if not is_duplicate: base_dev_list.append(dev_item)

        inc_unresolved = incremental_output.get("unresolved_questions_or_themes_from_original")
        if isinstance(inc_unresolved, list):
            base_unresolved_list = merged_doc.setdefault("unresolved_questions_or_themes_from_original", [])
            for item in inc_unresolved:
                if item not in base_unresolved_list: base_unresolved_list.append(item)
        return merged_doc

    def _extract_final_analysis(self, analysis_doc: Dict[str, Any], chapters_data: List[Dict[str, Any]]) -> Dict[
        str, Any]:
        """
        将内部使用的完整分析文档转换为前端展示所需的简化/格式化版本。
        Args:
            analysis_doc: 内部完整的分析文档。
            chapters_data: 原始的章节数据列表，用于计算章节数和字数。
        Returns:
            一个适合前端展示的分析结果字典。
        """
        final_output = {
            "title": analysis_doc.get("novel_title", "未知小说"),
            "chapters_count": len(chapters_data),
            "word_count": sum(len(ch.get("content", "")) for ch in chapters_data),
            "characters": [],
            "world_building": [],
            "plot_summary": analysis_doc.get("main_plotline_summary", "暂无主要剧情概要。"),
            "themes": analysis_doc.get("unresolved_questions_or_themes_from_original", []),
            "excerpts": []
        }

        for char_name, profile_data in analysis_doc.get("character_profiles", {}).items():
            if isinstance(profile_data, dict):
                final_output["characters"].append({
                    "name": char_name,
                    "description": profile_data.get("description", "暂无描述。")[:200] + "..."
                })

        ws_data = analysis_doc.get("world_setting", {})
        if isinstance(ws_data, dict) and ws_data.get("overview"):
            final_output["world_building"].append({
                "name": "世界背景概述",
                "description": ws_data["overview"]
            })

        anchor_events = [
            event for event in analysis_doc.get("detailed_timeline_and_key_events", [])
            if isinstance(event, dict) and event.get("is_anchor_event")
        ]
        for anchor_event in anchor_events[:3]:
            final_output["excerpts"].append({
                "chapter": anchor_event.get("chapter_approx", "未知"),
                "text": anchor_event.get("description", "锚点事件描述。")[:150] + "..."
            })
        return final_output
