# novel_processor.py
# 该文件处理小说的分析和处理。

import os
import json
import time  # 虽然在此修改版本中 time 未直接使用，但保留以防未来扩展或其他方法可能需要
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple  # Tuple 未直接使用，但保留以防未来扩展
import utils
import prompts  # <--- 确保 prompts 模块被导入


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
        self.processed_event_ids = set()  # 用于确保事件ID的唯一性

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
                title_match = re.search(r'^(第[一二三四五六七八九十百千万零\d]+章.*?)$|^(Chapter\s+\d+.*?)$',
                                        chapter_text_content.splitlines()[0] if chapter_text_content else "",
                                        re.MULTILINE)
                chapter_number_from_title = i + 1
                title_from_text = f"第{chapter_number_from_title}章"

                if title_match:
                    extracted_title = title_match.group(1) or title_match.group(2)
                    if extracted_title:
                        title_from_text = extracted_title.strip()
                        num_match = re.search(r'(\d+)', title_from_text)
                        if num_match:
                            try:
                                chapter_number_from_title = int(num_match.group(1))
                            except ValueError:
                                print(
                                    f"警告: 章节 '{title_from_text[:30]}...' 的章节号提取异常 (非数字)，使用默认值 {i + 1}")
                                chapter_number_from_title = i + 1

                if not isinstance(chapter_number_from_title, int) or chapter_number_from_title < 0:
                    print(f"警告: 章节 '{title_from_text[:30]}...' 的章节号提取异常，使用默认值 {i + 1}")
                    chapter_number_from_title = i + 1

                chapter_filename = utils.sanitize_filename(
                    f'chapter_{chapter_number_from_title:03d}_{title_from_text[:20]}.txt')
                chapter_path = os.path.join(self.chapters_dir, chapter_filename)

                if not chapter_path or not self.chapters_dir:
                    print(
                        f"错误: 无效的 chapter_path ('{chapter_path}') 或 self.chapters_dir ('{self.chapters_dir}') 用于章节 {chapter_number_from_title}")
                    continue

                success_write_chapter = utils.write_text_file(chapter_path, chapter_text_content)
                if not success_write_chapter:
                    print(f"写入章节 {chapter_number_from_title} 到 {chapter_path} 失败。")

                chapter_data_entry = {
                    "chapter_number": chapter_number_from_title,
                    "title": title_from_text,
                    "content": chapter_text_content,
                    "path": chapter_path
                }
                chapters_data.append(chapter_data_entry)

            chapters_data_path = os.path.join(self.output_dir, 'chapters_data.json')
            utils.write_json_file(chapters_data, chapters_data_path)
            print(f"章节数据已保存到: {chapters_data_path}")

            analysis_result_doc = self._analyze_novel(chapters_data, novel_md5, novel_title)

            if analysis_result_doc:
                final_output_for_frontend = self._extract_final_analysis(analysis_result_doc, chapters_data)
                success_writing_final = utils.write_json_file(final_output_for_frontend, self.final_analysis_path)
                if success_writing_final:
                    print(f"最终分析结果已成功写入文件: {self.final_analysis_path}")
                    # 清理临时的 analysis_in_progress.json 文件
                    if os.path.exists(self.analysis_in_progress_path):
                        try:
                            os.remove(self.analysis_in_progress_path)
                            print(f"已删除临时分析文件: {self.analysis_in_progress_path}")
                        except OSError as e:
                            print(f"删除临时分析文件失败 {self.analysis_in_progress_path}: {e}")
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
            traceback.print_exc()
            return False

    def _split_into_chapters(self, content: str) -> List[str]:
        """
        将小说内容分割为章节。此版本返回每个章节的完整文本（包括标题行）。
        Args:
            content: 小说内容。
        Returns:
            章节内容字符串列表。
        """
        chapter_pattern = r"^\s*(?:第[一二三四五六七八九十百千万零\d]+章(?:[^\n]*)|Chapter\s+\d+(?:[^\n]*))"
        parts = re.split(f'({chapter_pattern})', content, flags=re.MULTILINE)
        chapters_content = []
        current_content_buffer = ""

        if parts and parts[0].strip():
            if not re.match(chapter_pattern, parts[0].strip(), re.MULTILINE):
                current_content_buffer = "序言\n" + parts[0].strip()
            else:
                current_content_buffer = parts[0].strip()

        idx = 1
        while idx < len(parts):
            title_part = parts[idx].strip()
            content_part = ""
            if idx + 1 < len(parts):
                content_part = parts[idx + 1]

            if current_content_buffer and not title_part.startswith(current_content_buffer.splitlines()[0]):
                chapters_content.append(current_content_buffer.strip())
                current_content_buffer = ""

            if title_part:
                if current_content_buffer:
                    chapters_content.append(current_content_buffer.strip())
                current_content_buffer = title_part + "\n" + content_part
            else:
                current_content_buffer += content_part
            idx += 2

        if current_content_buffer.strip():
            chapters_content.append(current_content_buffer.strip())

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

            for chapter_info in chapters_data:
                current_chapter_content = chapter_info["content"]
                current_chapter_number = chapter_info["chapter_number"]
                print(f"正在分析章节 {current_chapter_number}: {chapter_info['title'][:30]}...")

                prompt_for_llm = self._build_analysis_prompt(
                    current_chapter_content,
                    current_analysis_doc,
                    current_chapter_number
                )

                incremental_analysis_json_str = self._call_llm_for_analysis_raw_json(prompt_for_llm)  # 获取原始JSON字符串

                if incremental_analysis_json_str:
                    try:
                        # 尝试解析 LLM 返回的 JSON 字符串
                        # 清理可能的 Markdown 代码块标记
                        if incremental_analysis_json_str.startswith("```json"):
                            incremental_analysis_json_str = incremental_analysis_json_str[len("```json"):]
                        if incremental_analysis_json_str.endswith("```"):
                            incremental_analysis_json_str = incremental_analysis_json_str[:-len("```")]
                        incremental_analysis_json_str = incremental_analysis_json_str.strip()

                        incremental_analysis = json.loads(incremental_analysis_json_str)
                        if isinstance(incremental_analysis, dict):
                            current_analysis_doc = self._merge_incremental_analysis(
                                current_analysis_doc, incremental_analysis, current_chapter_number
                            )
                            current_analysis_doc = self._ensure_unique_event_ids(current_analysis_doc)
                            utils.write_json_file(current_analysis_doc, self.analysis_in_progress_path)
                            print(f"已完成章节 {current_chapter_number} 的分析并合并结果。")
                        else:
                            print(
                                f"LLM为分析章节 {current_chapter_number} 返回了有效的JSON但不是一个对象: {type(incremental_analysis)}")
                            print(f"原始响应: {incremental_analysis_json_str[:500]}...")

                    except json.JSONDecodeError as e:
                        print(f"解析LLM为章节 {current_chapter_number} 的分析响应JSON失败: {e}")
                        print(f"LLM原始响应 (或提取的JSON部分): {incremental_analysis_json_str[:500]}...")
                        # 这里可以选择是否继续，或者标记此章节分析失败
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
        现在将使用 prompts.py 中的函数。
        """
        previous_analysis_json_str = json.dumps(previous_analysis_doc, ensure_ascii=False, indent=2)

        # 使用 prompts.py 中的 get_novel_analysis_prompt 函数
        return prompts.get_novel_analysis_prompt(
            previous_analysis_summary_json_str=previous_analysis_json_str,
            current_chapter_text=chapter_text_for_analysis,
            current_chapter_number=chapter_number_for_context
        )

    def _call_llm_for_analysis_raw_json(self, prompt: str) -> Optional[str]:
        """
        调用LLM进行分析，并期望返回原始JSON字符串。
        该方法适配 LLMClientInterface 的 generate_chat_completion。
        """
        if not self.llm_client:
            print("LLM客户端未初始化，无法进行分析。")
            return None

        try:
            messages = [
                {"role": "system", "content": "你是一个小说分析助手，请严格按照用户要求的格式输出JSON对象。"},
                {"role": "user", "content": prompt}
            ]

            # 假设 llm_client 是 LLMClientInterface 的一个实例
            model_to_use = self.llm_client.default_model if hasattr(self.llm_client,
                                                                    'default_model') else "default-model"
            if not model_to_use and hasattr(self.llm_client, 'model_name'):  # 兼容旧版 LLMClient
                model_to_use = self.llm_client.model_name

            response_dict = self.llm_client.generate_chat_completion(
                model=model_to_use,
                messages=messages,
                expect_json_in_content=True  # 明确要求LLM返回JSON格式
            )

            if response_dict and "message" in response_dict and "content" in response_dict["message"]:
                raw_response_content = response_dict["message"]["content"]
                return raw_response_content
            elif response_dict and isinstance(response_dict.get("content"), str):  # 兼容直接返回content的API
                raw_response_content = response_dict.get("content")
                return raw_response_content
            else:
                print(f"LLM为分析调用返回了意外的响应格式: {response_dict}")
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

        # 使用一个临时的集合来跟踪本轮 _ensure_unique_event_ids 调用中已分配的ID，
        # 以防止在单次调用内生成重复ID（如果UUID生成恰好重复，虽然概率极低）。
        # self.processed_event_ids 仍然作为全局（跨章节）的已处理ID集合。
        current_run_ids = set()

        for event in analysis_doc["detailed_timeline_and_key_events"]:
            if not isinstance(event, dict):
                new_event_list.append(event)  # 保留非字典项（尽管不应出现）
                continue

            original_event_id = event.get("event_id")
            final_id = original_event_id

            is_final_format_candidate = (
                    isinstance(original_event_id, str) and
                    original_event_id.startswith("E") and
                    len(original_event_id) == 7 and
                    original_event_id[1:].isalnum()  # 确保E后面是6位字母数字
            )

            # 如果ID不是期望的最终格式，或者虽然是最终格式但已在全局或本次运行中处理过，则生成新的ID
            if not is_final_format_candidate or original_event_id in self.processed_event_ids or original_event_id in current_run_ids:
                new_uuid_part = uuid.uuid4().hex[:6].upper()
                final_id = f"E{new_uuid_part}"
                while final_id in self.processed_event_ids or final_id in current_run_ids:  # 确保新ID的全局和本次运行唯一性
                    new_uuid_part = uuid.uuid4().hex[:6].upper()
                    final_id = f"E{new_uuid_part}"

            event["event_id"] = final_id
            self.processed_event_ids.add(final_id)
            current_run_ids.add(final_id)

            # 如果原始ID是临时ID (非E开头) 并且发生了更改，则记录映射关系
            if original_event_id and original_event_id != final_id and not (
                    isinstance(original_event_id, str) and original_event_id.startswith("E")):
                temp_id_to_final_id_map[original_event_id] = final_id

            new_event_list.append(event)

        analysis_doc["detailed_timeline_and_key_events"] = new_event_list

        # 更新角色发展中的事件引用ID
        if temp_id_to_final_id_map and "character_profiles" in analysis_doc:
            for char_name, profile in analysis_doc.get("character_profiles", {}).items():
                if isinstance(profile, dict) and "key_developments" in profile and isinstance(
                        profile["key_developments"], list):
                    for dev_event in profile["key_developments"]:
                        if isinstance(dev_event, dict):
                            ref_id = dev_event.get("event_ref_id")
                            if ref_id in temp_id_to_final_id_map:
                                dev_event["event_ref_id"] = temp_id_to_final_id_map[ref_id]
        return analysis_doc

    def _merge_incremental_analysis(self, previous_doc: Dict[str, Any], incremental_output: Dict[str, Any],
                                    current_chapter_number_context: int) -> Dict[str, Any]:
        """
        将LLM返回的增量分析结果合并到主分析文档中。
        """
        merged_doc = json.loads(json.dumps(previous_doc))  # 深拷贝

        # 合并 world_setting
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
                    # 转换为可哈希类型以进行集合操作，适用于简单类型和字典/列表（通过JSON字符串）
                    existing_items_set = set()
                    for item in base_list:
                        if isinstance(item, (dict, list)):
                            existing_items_set.add(json.dumps(item, sort_keys=True, ensure_ascii=False))
                        else:
                            existing_items_set.add(item)

                    for new_item in inc_ws[list_field]:
                        new_item_repr = json.dumps(new_item, sort_keys=True, ensure_ascii=False) if isinstance(new_item,
                                                                                                               (dict,
                                                                                                                list)) else new_item
                        if new_item_repr not in existing_items_set:
                            base_list.append(new_item)
                            existing_items_set.add(new_item_repr)

        # 合并 main_plotline_summary
        inc_plot_summary = incremental_output.get("main_plotline_summary")
        if inc_plot_summary and isinstance(inc_plot_summary, str):
            current_base_summary = merged_doc.get("main_plotline_summary", "")
            chapter_contribution = f"(来自第 {current_chapter_number_context} 章分析): {inc_plot_summary}"
            merged_doc["main_plotline_summary"] = (
                        current_base_summary + "\n---\n" + chapter_contribution).strip() if current_base_summary else chapter_contribution

        # 合并 detailed_timeline_and_key_events
        inc_events = incremental_output.get("detailed_timeline_and_key_events")
        if isinstance(inc_events, list):
            base_events = merged_doc.setdefault("detailed_timeline_and_key_events", [])
            for new_event_data in inc_events:
                if isinstance(new_event_data, dict):
                    new_event_data["chapter_approx"] = current_chapter_number_context
                    # 避免重复添加完全相同的事件 (基于内容，ID会在之后处理)
                    is_duplicate_event = False
                    # 更宽松的重复检查：如果描述和章节近似相同，则认为是重复（不考虑ID）
                    for existing_event in base_events:
                        if (existing_event.get("description") == new_event_data.get("description") and
                                existing_event.get("chapter_approx") == new_event_data.get("chapter_approx") and
                                existing_event.get("event_time_readable") == new_event_data.get("event_time_readable")):
                            is_duplicate_event = True
                            break
                    if not is_duplicate_event:
                        base_events.append(new_event_data)

        # 合并 character_profiles
        inc_profiles = incremental_output.get("character_profiles")
        if isinstance(inc_profiles, dict):
            base_profiles = merged_doc.setdefault("character_profiles", {})
            for char_name, inc_profile_data in inc_profiles.items():
                if not isinstance(inc_profile_data, dict): continue

                char_profile_to_update = base_profiles.setdefault(char_name, {})

                # 如果是新角色，或LLM提供了first_appearance_chapter
                if "first_appearance_chapter" not in char_profile_to_update or inc_profile_data.get(
                        "first_appearance_chapter"):
                    char_profile_to_update["first_appearance_chapter"] = inc_profile_data.get(
                        "first_appearance_chapter", current_chapter_number_context)

                if inc_profile_data.get("description") and isinstance(inc_profile_data["description"], str):
                    char_profile_to_update["description"] = inc_profile_data["description"]  # 通常是覆盖或补充更新

                for list_attr in ["personality_traits", "motivations"]:
                    if inc_profile_data.get(list_attr) and isinstance(inc_profile_data[list_attr], list):
                        base_attr_list = char_profile_to_update.setdefault(list_attr, [])
                        for item in inc_profile_data[list_attr]:
                            if item not in base_attr_list: base_attr_list.append(item)

                if inc_profile_data.get("relationships") and isinstance(inc_profile_data["relationships"], dict):
                    char_profile_to_update.setdefault("relationships", {}).update(inc_profile_data["relationships"])

                if inc_profile_data.get("key_developments") and isinstance(inc_profile_data["key_developments"], list):
                    base_dev_list = char_profile_to_update.setdefault("key_developments", [])
                    for dev_item in inc_profile_data["key_developments"]:
                        if isinstance(dev_item, dict):
                            dev_item["chapter"] = dev_item.get("chapter", current_chapter_number_context)
                            # 避免重复的关键发展条目
                            is_duplicate_dev = any(
                                existing_dev.get("chapter") == dev_item.get("chapter") and
                                existing_dev.get("event_ref_id") == dev_item.get(
                                    "event_ref_id") and  # 假设 event_ref_id 此时是LLM给的临时ID
                                existing_dev.get("development_summary") == dev_item.get("development_summary")
                                for existing_dev in base_dev_list
                            )
                            if not is_duplicate_dev: base_dev_list.append(dev_item)

        # 合并 unresolved_questions_or_themes_from_original
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
        """
        final_output = {
            "title": analysis_doc.get("novel_title", "未知小说"),
            "chapters_count": len(chapters_data),
            "word_count": sum(len(ch.get("content", "")) for ch in chapters_data),
            "characters": [],
            "world_building": [],  # 改为列表以支持多条世界观条目
            "plot_summary": analysis_doc.get("main_plotline_summary", "暂无主要剧情概要。"),
            "themes": analysis_doc.get("unresolved_questions_or_themes_from_original", []),
            "excerpts": []  # 用于展示关键事件或引人入胜的片段
        }

        # 提取角色信息
        for char_name, profile_data in analysis_doc.get("character_profiles", {}).items():
            if isinstance(profile_data, dict):
                desc = profile_data.get("description", "暂无描述。")
                final_output["characters"].append({
                    "name": char_name,
                    "description": desc[:200] + "..." if len(desc) > 200 else desc  # 截断描述
                })

        # 提取世界观信息
        ws_data = analysis_doc.get("world_setting", {})
        if isinstance(ws_data, dict):
            if ws_data.get("overview"):
                final_output["world_building"].append({
                    "name": "世界背景概述",
                    "description": ws_data["overview"]
                })
            if ws_data.get("rules_and_systems"):
                final_output["world_building"].append({
                    "name": "规则与体系",
                    "description": "; ".join(ws_data["rules_and_systems"]) if isinstance(ws_data["rules_and_systems"],
                                                                                         list) else str(
                        ws_data["rules_and_systems"])
                })
            if ws_data.get("key_locations"):
                final_output["world_building"].append({
                    "name": "关键地点",
                    "description": "; ".join(loc.get("name", loc) if isinstance(loc, dict) else loc for loc in
                                             ws_data["key_locations"]) if isinstance(ws_data["key_locations"],
                                                                                     list) else str(
                        ws_data["key_locations"])
                })
            if ws_data.get("major_factions"):
                final_output["world_building"].append({
                    "name": "主要势力",
                    "description": "; ".join(fac.get("name", fac) if isinstance(fac, dict) else fac for fac in
                                             ws_data["major_factions"]) if isinstance(ws_data["major_factions"],
                                                                                      list) else str(
                        ws_data["major_factions"])
                })

        # 提取一些锚点事件作为精选片段
        anchor_events = [
            event for event in analysis_doc.get("detailed_timeline_and_key_events", [])
            if isinstance(event, dict) and event.get("is_anchor_event")
        ]
        # 按章节号排序，然后取前几个
        anchor_events.sort(key=lambda x: x.get("chapter_approx", float('inf')))

        for anchor_event in anchor_events[:3]:  # 最多展示3个精选片段
            desc = anchor_event.get("description", "锚点事件描述。")
            final_output["excerpts"].append({
                "chapter": anchor_event.get("chapter_approx", "未知"),
                "text": desc[:150] + "..." if len(desc) > 150 else desc,  # 截断描述
                "source_snippet": anchor_event.get("original_text_snippet_ref", "")  # 可以考虑加入原文片段
            })

        # 如果没有锚点事件，可以尝试从主剧情概要中提取片段，或从章节开头提取
        if not final_output["excerpts"] and chapters_data:
            first_chapter_content = chapters_data[0].get("content", "")
            # 简单地取第一章的前150个字符作为备用摘录
            excerpt_text = re.sub(r'^\s*(?:第[一二三四五六七八九十百千万零\d]+章.*?|Chapter\s+\d+.*?)\s*\n', '',
                                  first_chapter_content, count=1)  # 移除可能的标题行
            excerpt_text = excerpt_text.strip()[:150]
            if excerpt_text:
                final_output["excerpts"].append({
                    "chapter": chapters_data[0].get("chapter_number", 1),
                    "text": excerpt_text + "..." if len(excerpt_text) >= 150 else excerpt_text
                })

        return final_output