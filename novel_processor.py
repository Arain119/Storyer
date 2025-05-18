# novel_processor.py
# 该文件处理小说的分析和处理。

import os
import json
import time  # Ensure time is imported for retry delays
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple  # Tuple 未直接使用，但保留以防未来扩展
import utils
import prompts  # <--- 确保 prompts 模块被导入


class NovelProcessor:
    """小说处理器类，负责分析和处理上传的小说。"""

    def __init__(self, llm_client, novel_file_path: str, output_dir: str,
                 analysis_model_override: Optional[str] = None):  # MODIFIED LINE
        """
        初始化小说处理器。

        Args:
            llm_client: LLM客户端实例。
            novel_file_path: 小说文件路径。
            output_dir: 输出目录路径。
            analysis_model_override: 可选参数，用于覆盖LLM客户端的默认模型，专用于本处理器分析阶段。
        """
        self.llm_client = llm_client
        self.novel_file_path = novel_file_path
        self.output_dir = output_dir
        self.analysis_model_override = analysis_model_override  # MODIFIED LINE: Store the override
        self.last_error_detail = None  # MODIFIED LINE: Add for more specific error tracking

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
        self.last_error_detail = None  # Reset error detail at the start of processing
        try:
            # 读取小说内容
            novel_content = utils.read_text_file(self.novel_file_path)
            if not novel_content:
                print(f"无法读取小说文件: {self.novel_file_path}")
                self.last_error_detail = f"无法读取小说文件: {self.novel_file_path}"
                return False

            # 计算MD5
            novel_md5 = utils.calculate_md5(self.novel_file_path)
            if not novel_md5:
                print("无法计算小说的MD5哈希值。")
                self.last_error_detail = "无法计算小说的MD5哈希值"
                return False

            # 提取小说标题
            novel_title = os.path.splitext(os.path.basename(self.novel_file_path))[0]

            # 分割章节
            chapters_content_list = self._split_into_chapters(novel_content)
            if not chapters_content_list:
                print("无法将小说分割成章节。")
                self.last_error_detail = "无法将小说分割成章节"
                return False

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

                if not chapter_path or not self.chapters_dir:  # Should not happen if dirs are created
                    print(
                        f"错误: 无效的 chapter_path ('{chapter_path}') 或 self.chapters_dir ('{self.chapters_dir}') 用于章节 {chapter_number_from_title}")
                    self.last_error_detail = f"章节路径无效: 章节 {chapter_number_from_title}"
                    continue  # Skip this chapter

                success_write_chapter = utils.write_text_file(chapter_path, chapter_text_content)
                if not success_write_chapter:
                    print(f"写入章节 {chapter_number_from_title} 到 {chapter_path} 失败。")
                    # Optionally, set self.last_error_detail or decide if this is a critical failure

                chapter_data_entry = {
                    "chapter_number": chapter_number_from_title,
                    "title": title_from_text,
                    "content": chapter_text_content,  # Full chapter text
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
                    if os.path.exists(self.analysis_in_progress_path):
                        try:
                            os.remove(self.analysis_in_progress_path)
                            print(f"已删除临时分析文件: {self.analysis_in_progress_path}")
                        except OSError as e:
                            print(f"删除临时分析文件失败 {self.analysis_in_progress_path}: {e}")
                    return True
                else:
                    print(f"最终分析结果写入文件 {self.final_analysis_path} 失败。")
                    self.last_error_detail = f"写入最终分析文件 {self.final_analysis_path} 失败"
                    return False
            else:
                print("小说分析未能生成结果。")
                # self.last_error_detail might have been set by _analyze_novel
                if not self.last_error_detail:
                    self.last_error_detail = "小说分析未能生成有效结果文档"
                return False

        except Exception as e:
            print(f"处理小说时出错: {str(e)}")
            self.last_error_detail = f"处理小说时异常: {str(e)}"
            import traceback
            traceback.print_exc()
            return False

    def _split_into_chapters(self, content: str) -> List[str]:
        chapter_pattern = r"^\s*(?:第[一二三四五六七八九十百千万零\d]+章(?:[^\n]*)|Chapter\s+\d+(?:[^\n]*))"
        parts = re.split(f'({chapter_pattern})', content, flags=re.MULTILINE)
        chapters_content = []
        current_content_buffer = ""

        if parts and parts[0].strip():
            if not re.match(chapter_pattern, parts[0].strip(), re.MULTILINE):
                current_content_buffer = "序言\n" + parts[0].strip()
            else:  # First part is already a chapter title
                current_content_buffer = parts[0].strip()

        idx = 1
        while idx < len(parts):
            title_part = parts[idx].strip()  # This is the chapter title line
            content_part_after_title = ""
            if idx + 1 < len(parts):
                content_part_after_title = parts[idx + 1]  # This is the content after the title line

            if current_content_buffer and title_part and not current_content_buffer.startswith(title_part):
                # This means current_content_buffer holds the previous chapter (title + content)
                # And title_part is a new chapter title.
                # So, finalize the previous chapter.
                if current_content_buffer.strip():
                    chapters_content.append(current_content_buffer.strip())
                current_content_buffer = title_part  # Start new buffer with new title
                if content_part_after_title:
                    current_content_buffer += "\n" + content_part_after_title  # Add its content
            elif title_part:  # This is likely the first chapter, or buffer was just reset
                if current_content_buffer and current_content_buffer.strip() and not current_content_buffer.startswith(
                        title_part):  # if buffer had content from previous non-chapter part
                    chapters_content.append(current_content_buffer.strip())

                current_content_buffer = title_part
                if content_part_after_title:
                    current_content_buffer += "\n" + content_part_after_title
            else:  # No title part, means content_part_after_title belongs to current_content_buffer
                if content_part_after_title:
                    current_content_buffer += content_part_after_title
            idx += 2

        if current_content_buffer.strip():
            chapters_content.append(current_content_buffer.strip())

        if not chapters_content and content.strip():
            print("警告：未使用章节模式分割文本，将整个内容视为单一章节。")
            chapters_content.append("第1章\n" + content.strip())  # Add a default title

        return [ch_content for ch_content in chapters_content if ch_content.strip()]

    def _analyze_novel(self, chapters_data: List[Dict[str, Any]], novel_md5: str, novel_title: str) -> Optional[
        Dict[str, Any]]:
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

                incremental_analysis_json_str = self._call_llm_for_analysis_raw_json(prompt_for_llm)

                if incremental_analysis_json_str:
                    try:
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
                            # Potentially set self.last_error_detail here

                    except json.JSONDecodeError as e:
                        print(f"解析LLM为章节 {current_chapter_number} 的分析响应JSON失败: {e}")
                        print(f"LLM原始响应 (或提取的JSON部分): {incremental_analysis_json_str[:500]}...")
                        self.last_error_detail = f"章节 {current_chapter_number} JSON解析失败: {e}"
                        # Decide whether to continue or fail the whole analysis
                else:
                    print(f"分析章节 {current_chapter_number} 时LLM未能返回有效增量数据，跳过此章节的合并。")
                    # self.last_error_detail might have been set by _call_llm_for_analysis_raw_json
                    if not self.last_error_detail:
                        self.last_error_detail = f"章节 {current_chapter_number} LLM无有效返回"

            print(f"所有章节分析迭代完成。最终分析文档（内部格式）保存在: {self.analysis_in_progress_path}")
            return current_analysis_doc

        except Exception as e:
            print(f"分析小说过程中发生严重错误: {str(e)}")
            self.last_error_detail = f"分析小说异常: {str(e)}"
            import traceback
            traceback.print_exc()
            return None

    def _initialize_analysis_document(self, novel_title: str, novel_md5: str) -> Dict[str, Any]:
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
        previous_analysis_json_str = json.dumps(previous_analysis_doc, ensure_ascii=False, indent=2)
        return prompts.get_novel_analysis_prompt(
            previous_analysis_summary_json_str=previous_analysis_json_str,
            current_chapter_text=chapter_text_for_analysis,
            current_chapter_number=chapter_number_for_context
        )

    def _call_llm_for_analysis_raw_json(self, prompt: str) -> Optional[str]:
        if not self.llm_client:
            print("LLM客户端未初始化，无法进行分析。")
            self.last_error_detail = "LLM客户端未初始化"
            return None

        messages = [
            {"role": "system", "content": "你是一个小说分析助手，请严格按照用户要求的格式输出JSON对象。"},
            {"role": "user", "content": prompt}
        ]

        model_to_use = self.llm_client.default_model
        if self.analysis_model_override:
            model_to_use = self.analysis_model_override
            print(f"NovelProcessor 使用覆盖的分析模型: {model_to_use}")
        elif not model_to_use and hasattr(self.llm_client, 'model_name'):  # Fallback for older client style
            model_to_use = self.llm_client.model_name

        if not model_to_use:
            print("错误: NovelProcessor 无法确定LLM分析模型。")
            self.last_error_detail = "NovelProcessor 无法确定LLM分析模型"
            return None

        max_attempts = 3
        timeout_seconds = 150

        for attempt in range(max_attempts):
            try:
                print(
                    f"LLM分析调用尝试 {attempt + 1}/{max_attempts} (模型: {model_to_use}, 超时: {timeout_seconds}s)...")
                response_dict = self.llm_client.generate_chat_completion(
                    model=model_to_use,
                    messages=messages,
                    expect_json_in_content=True,
                    timeout=timeout_seconds
                )

                raw_response_content = None
                if response_dict and "message" in response_dict and "content" in response_dict["message"]:
                    raw_response_content = response_dict["message"]["content"]
                elif response_dict and isinstance(response_dict.get("content"), str):  # Compatibility
                    raw_response_content = response_dict.get("content")

                if raw_response_content:
                    stripped_content = raw_response_content.strip()
                    # Basic check, not full validation here
                    if stripped_content.startswith("{") and stripped_content.endswith("}"):
                        print(f"LLM分析调用尝试 {attempt + 1} 成功获取类JSON响应。")
                        return raw_response_content
                    else:
                        print(
                            f"LLM分析调用尝试 {attempt + 1} 返回了非JSON格式或空内容: {raw_response_content[:100]}...")
                        self.last_error_detail = f"LLM响应非JSON: {raw_response_content[:100]}..."
                else:
                    api_error_msg = "未知API错误"
                    if hasattr(self.llm_client,
                               'last_error') and self.llm_client.last_error:  # if client logs its own errors
                        api_error_msg = self.llm_client.last_error
                    elif response_dict and "error" in response_dict:
                        api_error_msg = response_dict["error"]
                    print(
                        f"LLM为分析调用尝试 {attempt + 1} 返回了意外或空响应格式: {response_dict}. API层错误: {api_error_msg}")
                    self.last_error_detail = f"LLM空响应或API错误: {api_error_msg}"


            except Exception as e:
                print(f"LLM分析调用尝试 {attempt + 1} 发生错误: {str(e)}")
                self.last_error_detail = f"LLM调用异常: {str(e)}"
                # import traceback
                # traceback.print_exc()

            if attempt < max_attempts - 1:
                print(f"等待2秒后重试...")
                time.sleep(2)
            else:
                print(f"LLM分析调用在 {max_attempts} 次尝试后失败。")
                if not self.last_error_detail:  # Ensure an error detail is set if all attempts fail
                    self.last_error_detail = f"LLM调用 {max_attempts} 次尝试后失败。"
        return None

    def _ensure_unique_event_ids(self, analysis_doc: Dict[str, Any]) -> Dict[str, Any]:
        if "detailed_timeline_and_key_events" not in analysis_doc or \
                not isinstance(analysis_doc["detailed_timeline_and_key_events"], list):
            analysis_doc["detailed_timeline_and_key_events"] = []  # Ensure it's a list
            return analysis_doc

        temp_id_to_final_id_map = {}
        new_event_list = []
        current_run_ids = set()  # IDs generated in this specific merge operation

        for event in analysis_doc["detailed_timeline_and_key_events"]:
            if not isinstance(event, dict):  # Skip non-dict items
                new_event_list.append(event)
                continue

            original_event_id = event.get("event_id")
            final_id = original_event_id

            # Check if ID is already in our permanent set of processed IDs or this run's set,
            # or if it's not in the desired final format (E + 6 hex chars)
            is_final_format_candidate = (
                    isinstance(original_event_id, str) and
                    original_event_id.startswith("E") and
                    len(original_event_id) == 7 and
                    original_event_id[1:].isalnum()  # Checks for hex, but isalnum is broader. hex is better.
                # Consider using: all(c in "0123456789abcdefABCDEF" for c in original_event_id[1:])
            )
            # Regenerate ID if:
            # 1. It's not a candidate for final format (e.g. temp_event_...)
            # 2. It's a duplicate within self.processed_event_ids (globally processed)
            # 3. It's a duplicate within current_run_ids (IDs just generated in this call to _ensure_unique_event_ids)
            if not is_final_format_candidate or \
                    original_event_id in self.processed_event_ids or \
                    original_event_id in current_run_ids:

                new_uuid_part = uuid.uuid4().hex[:6].upper()
                final_id = f"E{new_uuid_part}"
                while final_id in self.processed_event_ids or final_id in current_run_ids:  # Ensure new ID is also unique
                    new_uuid_part = uuid.uuid4().hex[:6].upper()
                    final_id = f"E{new_uuid_part}"

            event["event_id"] = final_id
            self.processed_event_ids.add(final_id)  # Add to global set of processed IDs
            current_run_ids.add(final_id)  # Add to this run's set

            # If a temporary ID was replaced, map it for updating references
            if original_event_id and original_event_id != final_id and not is_final_format_candidate:  # original_event_id.startswith("temp_event_")
                temp_id_to_final_id_map[original_event_id] = final_id

            new_event_list.append(event)

        analysis_doc["detailed_timeline_and_key_events"] = new_event_list

        # Update character development event references if temp IDs were changed
        if temp_id_to_final_id_map and "character_profiles" in analysis_doc:
            for char_name, profile in analysis_doc.get("character_profiles", {}).items():
                if isinstance(profile, dict) and "key_developments" in profile and isinstance(
                        profile["key_developments"], list):
                    for dev_event in profile["key_developments"]:
                        if isinstance(dev_event, dict):
                            ref_id = dev_event.get("event_ref_id")  # This should be 'event_ref_id' based on prompt
                            if ref_id in temp_id_to_final_id_map:
                                dev_event["event_ref_id"] = temp_id_to_final_id_map[ref_id]
        return analysis_doc

    def _merge_incremental_analysis(self, previous_doc: Dict[str, Any], incremental_output: Dict[str, Any],
                                    current_chapter_number_context: int) -> Dict[str, Any]:
        merged_doc = json.loads(json.dumps(previous_doc))  # Deep copy

        # World Setting
        inc_ws = incremental_output.get("world_setting")
        if isinstance(inc_ws, dict):
            base_ws = merged_doc.setdefault("world_setting", {})
            for text_field in ["overview", "culture_and_customs"]:
                if inc_ws.get(text_field) and isinstance(inc_ws[text_field], str) and inc_ws[text_field].strip():
                    current_base_text = base_ws.get(text_field, "")
                    new_text = inc_ws[text_field].strip()
                    if new_text not in current_base_text:  # Avoid simple duplicates
                        base_ws[text_field] = (
                                    current_base_text + "\n" + new_text).strip() if current_base_text else new_text

            for list_field in ["rules_and_systems", "key_locations", "major_factions"]:
                if inc_ws.get(list_field) and isinstance(inc_ws[list_field], list):
                    base_list = base_ws.setdefault(list_field, [])
                    # Create a set of existing items for quick lookup (handling dicts by converting to JSON string)
                    existing_items_set = set()
                    for item in base_list:
                        if isinstance(item, (dict, list)):  # Complex items
                            existing_items_set.add(json.dumps(item, sort_keys=True, ensure_ascii=False))
                        else:  # Simple items (strings, numbers)
                            existing_items_set.add(str(item))  # Convert to string for consistency

                    for new_item in inc_ws[list_field]:
                        if isinstance(new_item, (dict, list)):
                            new_item_repr = json.dumps(new_item, sort_keys=True, ensure_ascii=False)
                        else:
                            new_item_repr = str(new_item).strip()  # Strip strings before adding

                        if new_item_repr and new_item_repr not in existing_items_set:  # Check if not empty and not duplicate
                            base_list.append(new_item)
                            existing_items_set.add(new_item_repr)

        # Main Plotline Summary
        inc_plot_summary = incremental_output.get("main_plotline_summary")
        if inc_plot_summary and isinstance(inc_plot_summary, str) and inc_plot_summary.strip():
            current_base_summary = merged_doc.get("main_plotline_summary", "")
            chapter_contribution = f"(来自第 {current_chapter_number_context} 章分析): {inc_plot_summary.strip()}"
            if chapter_contribution not in current_base_summary:  # Avoid simple duplicates
                merged_doc["main_plotline_summary"] = (
                            current_base_summary + "\n---\n" + chapter_contribution).strip() if current_base_summary else chapter_contribution

        # Detailed Timeline and Key Events
        inc_events = incremental_output.get("detailed_timeline_and_key_events")
        if isinstance(inc_events, list):
            base_events = merged_doc.setdefault("detailed_timeline_and_key_events", [])
            existing_event_descs_for_chapter = {
                evt.get("description", "").strip() for evt in base_events
                if
                evt.get("chapter_approx") == current_chapter_number_context and isinstance(evt.get("description"), str)
            }
            for new_event_data in inc_events:
                if isinstance(new_event_data, dict):
                    new_event_data["chapter_approx"] = current_chapter_number_context  # Assign chapter number
                    desc = new_event_data.get("description", "").strip()
                    # Simple check for duplication based on description within the same chapter analysis
                    if desc and desc not in existing_event_descs_for_chapter:
                        base_events.append(new_event_data)
                        existing_event_descs_for_chapter.add(desc)

        # Character Profiles
        inc_profiles = incremental_output.get("character_profiles")
        if isinstance(inc_profiles, dict):
            base_profiles = merged_doc.setdefault("character_profiles", {})
            for char_name, inc_profile_data in inc_profiles.items():
                if not isinstance(inc_profile_data, dict): continue

                char_profile_to_update = base_profiles.setdefault(char_name, {})

                # First appearance - only set if not present or if explicitly provided by LLM
                if "first_appearance_chapter" not in char_profile_to_update or inc_profile_data.get(
                        "first_appearance_chapter"):
                    char_profile_to_update["first_appearance_chapter"] = inc_profile_data.get(
                        "first_appearance_chapter", current_chapter_number_context)

                # Description - overwrite if new one is provided and different
                new_desc = inc_profile_data.get("description")
                if new_desc and isinstance(new_desc,
                                           str) and new_desc.strip() and new_desc.strip() != char_profile_to_update.get(
                        "description", "").strip():
                    char_profile_to_update["description"] = new_desc.strip()

                # List attributes (personality_traits, motivations) - append unique items
                for list_attr in ["personality_traits", "motivations"]:
                    if inc_profile_data.get(list_attr) and isinstance(inc_profile_data[list_attr], list):
                        base_attr_list = char_profile_to_update.setdefault(list_attr, [])
                        for item in inc_profile_data[list_attr]:
                            if isinstance(item, str) and item.strip() and item.strip() not in base_attr_list:
                                base_attr_list.append(item.strip())

                # Relationships - update/add
                if inc_profile_data.get("relationships") and isinstance(inc_profile_data["relationships"], dict):
                    char_profile_to_update.setdefault("relationships", {}).update(inc_profile_data["relationships"])

                # Key Developments - append new, unique developments
                if inc_profile_data.get("key_developments") and isinstance(inc_profile_data["key_developments"], list):
                    base_dev_list = char_profile_to_update.setdefault("key_developments", [])
                    existing_dev_descs_for_chapter_char = {
                        dev.get("development_summary", "").strip() for dev in base_dev_list
                        if dev.get("chapter") == current_chapter_number_context and isinstance(
                            dev.get("development_summary"), str)
                    }
                    for dev_item in inc_profile_data["key_developments"]:
                        if isinstance(dev_item, dict):
                            dev_item["chapter"] = dev_item.get("chapter",
                                                               current_chapter_number_context)  # Assign chapter
                            dev_summary = dev_item.get("development_summary", "").strip()
                            if dev_summary and dev_summary not in existing_dev_descs_for_chapter_char:
                                base_dev_list.append(dev_item)
                                existing_dev_descs_for_chapter_char.add(dev_summary)

        # Unresolved Questions or Themes
        inc_unresolved = incremental_output.get("unresolved_questions_or_themes_from_original")
        if isinstance(inc_unresolved, list):
            base_unresolved_list = merged_doc.setdefault("unresolved_questions_or_themes_from_original", [])
            for item in inc_unresolved:
                if isinstance(item, str) and item.strip() and item.strip() not in base_unresolved_list:
                    base_unresolved_list.append(item.strip())

        return merged_doc

    def _extract_final_analysis(self, analysis_doc: Dict[str, Any], chapters_data: List[Dict[str, Any]]) -> Dict[
        str, Any]:
        final_output = {
            "title": analysis_doc.get("novel_title", "未知小说"),
            "chapters_count": len(chapters_data),
            "word_count": sum(len(ch.get("content", "")) for ch in chapters_data),
            "characters": [],
            "world_building": [],  # This will be a list of dicts like {"name": "Category", "description": "Details"}
            "plot_summary": analysis_doc.get("main_plotline_summary", "暂无主要剧情概要。"),
            "themes": analysis_doc.get("unresolved_questions_or_themes_from_original", []),
            "excerpts": []  # List of dicts like {"chapter": X, "text": "...", "source_snippet": "..."}
        }

        # Characters
        for char_name, profile_data in analysis_doc.get("character_profiles", {}).items():
            if isinstance(profile_data, dict):
                desc = profile_data.get("description", "暂无描述。")
                final_output["characters"].append({
                    "name": char_name,
                    "description": desc[:200] + "..." if len(desc) > 200 else desc  # Truncate for UI
                })

        # World Building
        ws_data = analysis_doc.get("world_setting", {})
        if isinstance(ws_data, dict):
            if ws_data.get("overview"):
                final_output["world_building"].append({
                    "name": "世界背景概述",
                    "description": ws_data["overview"]
                })
            if ws_data.get("rules_and_systems"):
                desc_text = "; ".join(map(str, ws_data["rules_and_systems"])) if isinstance(
                    ws_data["rules_and_systems"], list) else str(ws_data["rules_and_systems"])
                final_output["world_building"].append({"name": "规则与体系", "description": desc_text})

            if ws_data.get("key_locations"):
                loc_names = []
                if isinstance(ws_data["key_locations"], list):
                    for loc in ws_data["key_locations"]:
                        if isinstance(loc, dict):
                            loc_names.append(loc.get("name", str(loc)))
                        else:
                            loc_names.append(str(loc))
                desc_text = "; ".join(loc_names) if loc_names else str(ws_data["key_locations"])
                final_output["world_building"].append({"name": "关键地点", "description": desc_text})

            if ws_data.get("major_factions"):
                fac_names = []
                if isinstance(ws_data["major_factions"], list):
                    for fac in ws_data["major_factions"]:
                        if isinstance(fac, dict):
                            fac_names.append(fac.get("name", str(fac)))
                        else:
                            fac_names.append(str(fac))
                desc_text = "; ".join(fac_names) if fac_names else str(ws_data["major_factions"])
                final_output["world_building"].append({"name": "主要势力", "description": desc_text})

            if ws_data.get("culture_and_customs"):
                final_output["world_building"].append({
                    "name": "文化与习俗",
                    "description": ws_data["culture_and_customs"]
                })

        # Excerpts (from anchor events)
        anchor_events = [
            event for event in analysis_doc.get("detailed_timeline_and_key_events", [])
            if isinstance(event, dict) and event.get("is_anchor_event")  # is_anchor_event should be boolean true
        ]
        anchor_events.sort(key=lambda x: x.get("chapter_approx", float('inf')))  # Sort by chapter

        for anchor_event in anchor_events[:3]:  # Take top 3 anchor events as excerpts
            desc = anchor_event.get("description", "锚点事件描述。")
            final_output["excerpts"].append({
                "chapter": anchor_event.get("chapter_approx", "未知"),
                "text": desc[:150] + "..." if len(desc) > 150 else desc,  # Truncate description for excerpt
                "source_snippet": anchor_event.get("original_text_snippet_ref", "")  # Original text snippet
            })

        # Fallback excerpt if no anchor events
        if not final_output["excerpts"] and chapters_data:
            first_chapter_content = chapters_data[0].get("content", "")
            # Remove potential chapter title from the beginning of the content for the excerpt
            excerpt_text = re.sub(r'^\s*(?:第[一二三四五六七八九十百千万零\d]+章.*?|Chapter\s+\d+.*?)\s*\n', '',
                                  first_chapter_content, count=1)
            excerpt_text = excerpt_text.strip()[:150]  # Take first 150 chars of content
            if excerpt_text:
                final_output["excerpts"].append({
                    "chapter": chapters_data[0].get("chapter_number", 1),
                    "text": excerpt_text + "..." if len(excerpt_text) >= 150 else excerpt_text,
                    "source_snippet": ""  # No specific source snippet for this fallback
                })
        return final_output