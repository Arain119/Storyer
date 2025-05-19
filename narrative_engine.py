# narrative_engine.py
# 该文件定义了叙事引擎类，负责驱动交互式故事的进展。

import os
import json
import re  # 正则表达式库
from typing import Dict, List, Any, Optional, Tuple

import config  # 导入配置
import utils  # 导入工具函数
from llm_client_interface import LLMClientInterface  # 导入LLM客户端接口
import prompts  # 导入提示工程模块


class NarrativeEngine:
    """
    叙事引擎类，管理故事的逻辑、与LLM的交互以及会话状态。
    """

    def __init__(self,
                 llm_writer_client: LLMClientInterface,  # 用于写作的LLM客户端
                 novel_specific_data_dir: str,  # 特定小说的数据目录
                 chapters_data_path: str,  # 章节数据文件路径
                 novel_analysis_path: str,  # 小说分析文件路径
                 writing_model_name: str,  # 写作模型名称
                 initial_state: Optional[Dict[str, Any]] = None):  # 用于加载的初始状态
        self.llm_writer_client = llm_writer_client
        self.novel_specific_data_dir = novel_specific_data_dir
        self.chapters_data_path = chapters_data_path
        self.novel_analysis_path = novel_analysis_path
        self.writing_model_name = writing_model_name

        self.session_memory_path = os.path.join(self.novel_specific_data_dir, config.SESSION_MEMORY_FILENAME)

        self.chapters_data: Optional[List[Dict[str, Any]]] = None
        self.novel_analysis: Optional[Dict[str, Any]] = None
        self.session_memory: List[Dict[str, Any]] = []
        self.current_narrative_chapter_index = 0  # 当前叙事所在的章节索引 (0-indexed)
        self.conversation_history: List[Dict[str, str]] = []

        if initial_state:
            self._load_state(initial_state)
            print(f"叙事引擎从已保存状态初始化，数据目录: {novel_specific_data_dir}")
        else:
            print(f"叙事引擎全新初始化，数据目录: {novel_specific_data_dir}")

    def _load_core_data(self) -> bool:
        """加载核心数据：章节数据和小说分析数据。"""
        self.chapters_data = utils.read_json_file(self.chapters_data_path)
        self.novel_analysis = utils.read_json_file(self.novel_analysis_path)

        if not self.chapters_data:
            print(f"错误：无法从 {self.chapters_data_path} 加载章节数据")
            return False
        if not self.novel_analysis:
            print(f"错误：无法从 {self.novel_analysis_path} 加载小说分析")
            return False

        for key, default_value in [
            ("world_setting", {"overview": "", "rules_and_systems": [], "key_locations": [], "major_factions": []}),
            ("main_plotline_summary", ""),
            ("detailed_timeline_and_key_events", []),
            ("character_profiles", {}),
            ("unresolved_questions_or_themes_from_original", [])
        ]:
            if key not in self.novel_analysis:
                self.novel_analysis[key] = default_value
        print("核心数据（章节和小说分析）加载成功。")
        return True

    def _get_current_chapter_number(self) -> int:
        """获取当前叙事索引对应的实际章节号 (chapter_number)"""
        if self.chapters_data and 0 <= self.current_narrative_chapter_index < len(self.chapters_data):
            return self.chapters_data[self.current_narrative_chapter_index].get("chapter_number",
                                                                                self.current_narrative_chapter_index + 1)  # 回退到索引+1
        return self.current_narrative_chapter_index + 1  # 默认回退

    def _get_relevant_core_settings_summary(self, current_event_context: Optional[str] = None) -> str:
        """
        获取与当前情境相关的核心设定摘要，用于提供给LLM。
        会限制未来信息的泄露。
        """
        if not self.novel_analysis or not self.chapters_data:
            return "错误：小说分析或章节数据未加载。"
        summary_parts = []

        current_actual_chapter_num = self._get_current_chapter_number()
        is_initial_phase_restricted = current_actual_chapter_num <= 1  # 假设第0章（序章）和第1章信息受限

        if is_initial_phase_restricted:
            summary_parts.append(
                f"- 当前故事阶段: 第 {current_actual_chapter_num} 章开端。你对这个世界的了解非常有限，仅限于你当前所经历和观察到的。请严格根据当前章节的直接信息和你的直接观察行动。不要假设任何当前章节未提及的背景信息或未来事件。")
            # 在初始阶段，可以提供非常概括的世界观，如果分析中有的话
            ws_overview = self.novel_analysis.get("world_setting", {}).get("overview", "")
            if ws_overview:
                summary_parts.append(f"- 世界观初步印象: {ws_overview[:150]}...")  # 截断以避免过多细节
        else:
            summary_parts.append(f"- 当前故事进展至: 第 {current_actual_chapter_num} 章附近。")
            ws = self.novel_analysis.get("world_setting", {})
            summary_parts.append(f"- 世界观概览: {ws.get("overview", "未定义")}")
            if ws.get("rules_and_systems"):
                summary_parts.append(
                    f"- 核心规则/系统: {json.dumps(ws.get("rules_and_systems"), ensure_ascii=False, indent=2)}")

            # 主剧情线摘要（可以考虑是否也需要根据进度逐步提供，目前是全局的）
            summary_parts.append(
                f"- 主剧情线概要（截至目前）: {self.novel_analysis.get("main_plotline_summary", "未定义")}")

            # 已发生的和即将发生的锚点事件提示
            # 只显示已发生的事件摘要和非常临近的1-2个未来锚点事件作为模糊提示
            # TODO: 这里的逻辑可以进一步细化，比如“已发生事件”是否需要全部列出，还是只列出近期的。

            timeline = self.novel_analysis.get("detailed_timeline_and_key_events", [])
            passed_event_ids_from_memory = {
                turn.get("divergence_from_original_plot", {}).get("original_timeline_event_ref")
                for turn in self.session_memory
                if turn.get("divergence_from_original_plot", {}).get("original_timeline_event_ref")}

            # 筛选已发生的事件 (chapter_approx <= current_actual_chapter_num)
            # 为了简洁，可能不需要在此处列出所有已发生的事件，LLM应从剧情记忆档案中获取更直接的上下文。
            # 此处主要关注未来的锚点。

            upcoming_anchors_prompt = []
            anchor_count = 0
            for event in timeline:
                if isinstance(event, dict) and event.get("is_anchor_event"):
                    event_chapter_approx = event.get("chapter_approx")
                    event_id = event.get("event_id")
                    if event_chapter_approx is not None and event_id:
                        # 只考虑略微超前于当前章节的锚点事件作为“即将发生”的提示
                        # 例如，只提示接下来1-2章内的锚点，或者只提示下一个未发生的锚点
                        if event_chapter_approx > current_actual_chapter_num and \
                                event_id not in passed_event_ids_from_memory and \
                                event_chapter_approx <= current_actual_chapter_num + config.NARRATIVE_WINDOW_CHAPTER_AFTER + 1:  # 限制在窗口内
                            upcoming_anchors_prompt.append(
                                f"{event_id}: {event.get("description", "未知描述")[:30]}... (原著约第 {event_chapter_approx} 章)")
                            anchor_count += 1
                            if anchor_count >= 1:  # 最多提示1个非常临近的未来锚点
                                break

            if upcoming_anchors_prompt:
                summary_parts.append(
                    f"- （模糊提示）原著中接下来可能的重要节点参考: {"; ".join(upcoming_anchors_prompt)}")
            else:
                summary_parts.append(
                    "- （模糊提示）原著中接下来可能的重要节点参考: (当前无立即相关的、未发生的近未来锚点事件提示，或已过关键节点)")

        # 角色信息：可以考虑只提供当前已出场或即将出场的角色信息
        # 这需要 character_profiles 中的角色有 first_appearance_chapter 字段，并且NovelProcessor能正确填充
        # 为简化，此处暂时不动态筛选角色列表，但这是一个重要的优化方向。
        # relevant_characters = {}
        # for char_name, profile in self.novel_analysis.get("character_profiles", {}).items():
        #     if profile.get("first_appearance_chapter", float('inf')) <= current_actual_chapter_num + 1: # 出现章节 <= 当前+1
        #         relevant_characters[char_name] = profile # 只取部分profile信息避免过长
        # if relevant_characters:
        #     summary_parts.append(f"- 相关人物档案摘要: {json.dumps(relevant_characters, ensure_ascii=False, indent=2, default=lambda o: '<not serializable>')}")

        if current_event_context: summary_parts.append(f"- 当前情境具体提示: {current_event_context}")
        return "\n".join(summary_parts)

    def _get_current_chapter_segment_text(self) -> str:
        """获取当前叙事点附近的原文章节片段文本。"""
        if not self.chapters_data: return "错误：章节数据未加载。"
        start_idx = max(0, self.current_narrative_chapter_index - config.NARRATIVE_WINDOW_CHAPTER_BEFORE)
        end_idx = min(len(self.chapters_data),
                      self.current_narrative_chapter_index + config.NARRATIVE_WINDOW_CHAPTER_AFTER + 1)

        segment_chapters = []
        if start_idx < end_idx:  # 确保索引有效
            segment_chapters = self.chapters_data[start_idx:end_idx]
        elif 0 <= self.current_narrative_chapter_index < len(self.chapters_data):  # 如果窗口为0，则取当前章
            segment_chapters = [self.chapters_data[self.current_narrative_chapter_index]]
        elif self.chapters_data:  # 极端情况，取最后一章
            segment_chapters = [self.chapters_data[-1]]

        if not segment_chapters: return "错误：无法获取当前章节片段。"
        return "\n\n---\n\n".join(
            [f"【原文参考：第 {ch["chapter_number"]} 章 - {ch.get("title", "无标题")}】\n{ch["content"]}" for ch in
             segment_chapters])

    def _initialize_session_memory(self, protagonist_initial_state: Dict[str, Any], initial_narrative_text: str):
        """
        初始化会话记忆 (session_memory.json)。
        """
        current_actual_chapter_num = self._get_current_chapter_number()
        initial_event_time = protagonist_initial_state.get("time", f"第 {current_actual_chapter_num} 章开端")
        initial_metadata = {
            "protagonist_action_summary": "故事开始，主角进入小说世界。",
            "event_time_readable_context": initial_event_time,
            "immediate_consequences_and_observations": [f"主角身份: {protagonist_initial_state.get("name", "未知")}",
                                                        f"初始地点: {protagonist_initial_state.get("location", "未知")}",
                                                        "故事正式拉开序幕。"],
            "character_state_changes": {protagonist_initial_state.get("name", "主角"): {"mood": "初始",
                                                                                        "location": protagonist_initial_state.get(
                                                                                            "location", "未知")}},
            "item_changes": {}, "world_state_changes": ["互动叙事已初始化。"],
            "divergence_from_original_plot": {"level": "无", "original_timeline_event_ref": None,
                                              "description_of_divergence": "尚未开始与原著剧情的显著交互。"},
            "current_chapter_progression_hint": f"已进入第 {current_actual_chapter_num} 章开端附近"
        }
        self.session_memory = [{"turn_id": 0, "user_input_signal": "SESSION_START", "user_free_text": "开始穿越体验",
                                "generated_narrative_segment": initial_narrative_text, **initial_metadata}]
        utils.write_json_file(self.session_memory, self.session_memory_path)
        print(f"初始会话记忆已创建于 {self.session_memory_path}")

    def start_session(self) -> Optional[str]:
        """
        开始一个新的叙事会话。
        """
        print("--- 阶段 2：互动叙事会话初始化 ---")
        if not self._load_core_data() or not self.novel_analysis or not self.chapters_data:
            return "系统错误：核心数据加载失败。"

        novel_title = self.novel_analysis.get("novel_title", "未知小说")

        # 确定初始章节号和相关信息
        protagonist_name = "主角"
        first_event_location = "故事开始的地方"
        # 默认从 chapters_data 的第一条记录（可能是序章或第一章）开始
        initial_chapter_data = self.chapters_data[0] if self.chapters_data else {"chapter_number": 1,
                                                                                 "title": "未知开端"}
        initial_chapter_approx_from_data = initial_chapter_data.get("chapter_number", 1)
        first_event_time = f"第 {initial_chapter_approx_from_data} 章开端"

        # 尝试从小说分析的时间线的第一个事件获取更精确的初始信息
        # 但要确保这个事件的章节号是有效的
        if self.novel_analysis.get("detailed_timeline_and_key_events") and \
                isinstance(self.novel_analysis["detailed_timeline_and_key_events"], list) and \
                len(self.novel_analysis["detailed_timeline_and_key_events"]) > 0:
            first_event_from_analysis = self.novel_analysis["detailed_timeline_and_key_events"][0]
            if isinstance(first_event_from_analysis, dict):
                analyzed_chap_approx = first_event_from_analysis.get("chapter_approx")

                # 校验分析得到的章节号是否在 chapters_data 中有效
                # 章节号到索引的转换：如果章节号从1开始，索引=号-1；如果从0开始，索引=号。
                # 我们需要找到 chapters_data 中 chapter_number 等于 analyzed_chap_approx 的那条记录
                target_event_chapter_data = next(
                    (ch for ch in self.chapters_data if ch.get("chapter_number") == analyzed_chap_approx), None)

                if target_event_chapter_data:  # 如果分析的章节号有效
                    initial_chapter_approx_from_data = analyzed_chap_approx
                    if first_event_from_analysis.get("key_characters_involved") and \
                            first_event_from_analysis["key_characters_involved"][0]:
                        protagonist_name = first_event_from_analysis["key_characters_involved"][0]
                    first_event_location = first_event_from_analysis.get("description", first_event_location)

                    event_time_from_analysis_readable = first_event_from_analysis.get("event_time_readable")
                    if event_time_from_analysis_readable and \
                            not str(event_time_from_analysis_readable).lower().startswith("第") and \
                            not str(event_time_from_analysis_readable).lower().startswith("chapter") and \
                            not str(event_time_from_analysis_readable).lower().startswith("本章"):  # 避免只是重复章节号
                        first_event_time = event_time_from_analysis_readable
                    else:  # 如果分析的时间只是章节号或“本章”，则用“开端”
                        first_event_time = f"第 {initial_chapter_approx_from_data} 章开端"
                else:
                    print(
                        f"警告：小说分析中的第一个事件指定的章节号 ({analyzed_chap_approx}) 在章节数据中未找到或无效。将从实际的第一章开始。")
                    # 回退到使用 chapters_data 的第一章
                    initial_chapter_approx_from_data = self.chapters_data[0].get("chapter_number",
                                                                                 1) if self.chapters_data else 1
                    first_event_time = f"第 {initial_chapter_approx_from_data} 章开端"
                    # first_event_location 和 protagonist_name 保持默认或从 self.chapters_data[0] 推断（如果可能）

        # 根据确定的 initial_chapter_approx_from_data 设置 current_narrative_chapter_index
        # 找到 initial_chapter_approx_from_data 在 self.chapters_data 中的索引
        self.current_narrative_chapter_index = 0  # 默认从0开始
        if self.chapters_data:
            for idx, ch_data in enumerate(self.chapters_data):
                if ch_data.get("chapter_number") == initial_chapter_approx_from_data:
                    self.current_narrative_chapter_index = idx
                    break

        # 获取用于LLM提示的初始章节文本，基于修正后的 current_narrative_chapter_index
        # initial_chapters_for_prompt 将由 _get_current_chapter_segment_text 动态获取，所以这里不需要单独准备
        # 我们需要的是 _get_current_chapter_segment_text 能够正确使用 current_narrative_chapter_index
        # 以及 config.INITIAL_CONTEXT_CHAPTERS 的概念融入到 NARRATIVE_WINDOW_CHAPTER_AFTER/BEFORE
        # 为了简化，初始叙事将使用由 _get_current_chapter_segment_text 决定的上下文窗口
        initial_chapters_text_for_llm_prompt = self._get_current_chapter_segment_text()

        protagonist_initial_state_for_prompt = f"主角: {protagonist_name}, 地点: {first_event_location}, 时间: {first_event_time}"

        # 获取当前实际章节号，用于提示
        current_actual_chapter_num_for_context = self._get_current_chapter_number()

        relevant_settings_summary = self._get_relevant_core_settings_summary(
            current_event_context=f"故事从 {first_event_time} (即第 {current_actual_chapter_num_for_context} 章开端) 开始，初始事件大致为：{first_event_location}"
        )
        initial_llm_user_prompt_content = prompts.get_initial_narrative_prompt(
            novel_title=novel_title,
            initial_chapters_text=initial_chapters_text_for_llm_prompt,  # 使用窗口文本
            relevant_core_settings_summary=relevant_settings_summary,
            protagonist_initial_state=protagonist_initial_state_for_prompt,
            current_chapter_number_for_context=current_actual_chapter_num_for_context
        )
        initial_narrative_messages = [{"role": "user", "content": initial_llm_user_prompt_content}]

        print(
            f"请求LLM ({self.llm_writer_client.client_type} - {self.writing_model_name}) 生成初始纯叙事文本 (基于第 {current_actual_chapter_num_for_context} 章上下文)...")
        llm_response = self.llm_writer_client.generate_chat_completion(
            self.writing_model_name, initial_narrative_messages, stream=False, expect_json_in_content=False
        )
        initial_narrative_text = None
        if llm_response and llm_response.get("message") and isinstance(llm_response["message"].get("content"), str):
            raw_text_from_llm = llm_response["message"]["content"].strip()
            initial_narrative_text, _ = utils.extract_narrative_and_metadata(raw_text_from_llm)
            if not initial_narrative_text: initial_narrative_text = raw_text_from_llm

        if initial_narrative_text:
            print("LLM已生成初始叙事文本。")
            protagonist_state_for_memory = {"name": protagonist_name, "location": first_event_location,
                                            "time": first_event_time}
            self._initialize_session_memory(protagonist_state_for_memory, initial_narrative_text)
            self.conversation_history = [
                {"role": "system", "content": prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT},
                {"role": "assistant", "content": initial_narrative_text}
            ]
            print("--- 阶段 2 成功完成 ---")
            return initial_narrative_text
        else:
            error_msg = f"系统错误：无法从LLM ({self.writing_model_name}) 获取初始叙事文本。响应: {llm_response}"
            print(error_msg)
            return error_msg

    def _update_session_memory_entry(self, turn_id: int, user_action: str, narrative_text: str,
                                     metadata: Dict[str, Any]):
        """
        更新会话记忆 (session_memory.json) 中的条目。
        """
        current_actual_chapter_num = self._get_current_chapter_number()
        if not self.session_memory:
            self._initialize_session_memory(
                {"name": "主角", "location": "未知", "time": f"第 {current_actual_chapter_num} 章"},
                "错误：会话记忆未初始化前的叙事。")

        default_divergence = {"level": "未知", "original_timeline_event_ref": None,
                              "description_of_divergence": "AI未提供分析"}
        event_time = metadata.get("event_time_readable_context", f"第 {current_actual_chapter_num} 章附近")
        if not event_time or event_time.lower() in ["未知时间", "时间推移 (ai未明确)"]:
            event_time = f"第 {current_actual_chapter_num} 章附近 (AI未明确具体时间)"

        new_turn = {
            "turn_id": turn_id,
            "user_input_signal": "USER_ACTION",
            "user_free_text": user_action,
            "protagonist_action_summary": metadata.get("protagonist_action_summary",
                                                       f"主角执行: {user_action[:30]}..."),
            "event_time_readable_context": event_time,
            "generated_narrative_segment": narrative_text,
            "immediate_consequences_and_observations": metadata.get("immediate_consequences_and_observations", []),
            "character_state_changes": metadata.get("character_state_changes", {}),
            "item_changes": metadata.get("item_changes", {}),
            "world_state_changes": metadata.get("world_state_changes", []),
            "divergence_from_original_plot": metadata.get("divergence_from_original_plot", default_divergence),
            "planned_reconvergence_point_id_if_any": metadata.get("planned_reconvergence_point_id_if_any"),
            "current_chapter_progression_hint": metadata.get("current_chapter_progression_hint")
        }
        self.session_memory.append(new_turn)
        utils.write_json_file(self.session_memory, self.session_memory_path)

    def _update_current_narrative_chapter_index(self, chapter_prog_hint: Optional[str]):
        """
        根据LLM元数据中的章节进展提示，更新当前叙事章节索引。
        """
        if not chapter_prog_hint or not self.chapters_data: return

        # 优先匹配 "进入第 X 章" 或 "已到第 X 章"
        next_chapter_match = re.search(r"(?:进入|已到|已是|开始)\s*第\s*(\d+|[一二三四五六七八九十百千万零]+)\s*章",
                                       chapter_prog_hint, re.IGNORECASE) or \
                             re.search(r"Chapter\s*(\d+)\s*(?:start|begin|entered)", chapter_prog_hint, re.IGNORECASE)
        if next_chapter_match:
            try:
                target_chapter_num_str = next_chapter_match.group(1)
                target_chapter_num = utils.chinese_to_arabic_number(target_chapter_num_str)
                if target_chapter_num is None and target_chapter_num_str.isdigit():
                    target_chapter_num = int(target_chapter_num_str)

                if target_chapter_num is not None and target_chapter_num > 0:
                    # 找到该章节号在 chapters_data 中的索引
                    new_target_idx = -1
                    for idx, ch_data in enumerate(self.chapters_data):
                        if ch_data.get("chapter_number") == target_chapter_num:
                            new_target_idx = idx
                            break

                    if new_target_idx != -1 and new_target_idx > self.current_narrative_chapter_index:
                        self.current_narrative_chapter_index = new_target_idx
                        print(
                            f"叙事章节索引更新为: {self.current_narrative_chapter_index} (对应第 {target_chapter_num} 章)")
                        return
            except ValueError:
                pass

        # 其次匹配事件ID提示，如果事件ID对应的章节大于当前章节
        event_match = re.search(r"事件\s*([Ee][\w\d-]+)", chapter_prog_hint)  # 允许ID包含字母数字和短横线
        if event_match and self.novel_analysis and self.novel_analysis.get("detailed_timeline_and_key_events"):
            event_id_hint = event_match.group(1).upper()
            for event_details in self.novel_analysis["detailed_timeline_and_key_events"]:
                if isinstance(event_details, dict) and event_details.get("event_id", "").upper() == event_id_hint:
                    event_chapter_approx = event_details.get("chapter_approx")
                    if event_chapter_approx is not None and event_chapter_approx > 0:
                        event_target_idx = -1
                        for idx, ch_data in enumerate(self.chapters_data):
                            if ch_data.get("chapter_number") == event_chapter_approx:
                                event_target_idx = idx
                                break
                        if event_target_idx != -1 and event_target_idx > self.current_narrative_chapter_index:
                            self.current_narrative_chapter_index = event_target_idx
                            print(
                                f"叙事章节索引据事件 {event_id_hint} 更新为: {self.current_narrative_chapter_index} (原著约第 {event_chapter_approx} 章)")
                            return
                    break

        # 如果没有明确的章节跳转，但提示“接近本章末尾”或“本章已结束”，并且后面还有章节，则可以尝试推进一章
        # 这个逻辑比较tricky，需要小心处理，暂时不加，避免意外跳章。
        # current_actual_chapter_num = self._get_current_chapter_number()
        # if ("末尾" in chapter_prog_hint or "结束" in chapter_prog_hint or "结尾" in chapter_prog_hint) and \
        #    self.current_narrative_chapter_index < len(self.chapters_data) - 1:
        #    # 检查是否真的在当前章节的末尾（比如通过与原文比较，但这很难）
        #    # 简单处理：如果LLM说末尾，就尝试进一章，但这可能不准
        #    pass

        print(
            f"未能从提示 '{chapter_prog_hint}' 中明确更新章节索引。保持当前索引 {self.current_narrative_chapter_index} (第 {self._get_current_chapter_number()} 章)。")

    def _determine_reconvergence_plan(self) -> Optional[str]:
        """
        判断当前剧情是否需要向原著主线重聚，并确定下一个重聚点。
        只考虑非常临近的未来锚点。
        """
        if not self.session_memory or not self.novel_analysis or not self.novel_analysis.get(
                "detailed_timeline_and_key_events"):
            return None

        last_turn = self.session_memory[-1]
        divergence_level = last_turn.get("divergence_from_original_plot", {}).get("level", "无")
        trigger_levels = [config.DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE.lower()]
        if config.DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE.lower() == "中度":
            trigger_levels.append("显著")

        if divergence_level.lower() in trigger_levels:
            timeline = self.novel_analysis.get("detailed_timeline_and_key_events", [])
            processed_refs = {t.get("divergence_from_original_plot", {}).get("original_timeline_event_ref")
                              for t in self.session_memory
                              if t.get("divergence_from_original_plot", {}).get("original_timeline_event_ref")}

            current_actual_chapter_num = self._get_current_chapter_number()

            # 寻找最近的、未发生的、且在合理范围内的锚点事件
            potential_targets = []
            for event in timeline:
                if not isinstance(event, dict): continue
                event_id, event_chapter = event.get("event_id"), event.get("chapter_approx")
                if event.get("is_anchor_event") and event_id and event_id not in processed_refs and \
                        event_chapter is not None and event_chapter > current_actual_chapter_num:
                    potential_targets.append(event)

            if not potential_targets:
                return None

            # 对潜在目标按章节号排序，选择最近的
            potential_targets.sort(key=lambda e: e.get("chapter_approx", float('inf')))

            next_anchor_event = potential_targets[0]
            target_event_chapter = next_anchor_event.get("chapter_approx")

            # 确保这个锚点事件不是太遥远 (例如，不超过接下来2-3章)
            if target_event_chapter <= current_actual_chapter_num + 3:  # 可配置的范围
                target_info = f"{next_anchor_event.get('event_id')}: {next_anchor_event.get('description', '未知锚点事件')[:50]}... (原著第 {target_event_chapter} 章)"
                self.session_memory[-1]["planned_reconvergence_point_id_if_any"] = next_anchor_event.get('event_id')
                utils.write_json_file(self.session_memory, self.session_memory_path)
                print(
                    f"检测到偏离，计划向锚点事件 {next_anchor_event.get('event_id')} (第 {target_event_chapter} 章) 重聚。")
                return target_info
            else:
                print(
                    f"检测到偏离，但最近的锚点事件 {next_anchor_event.get('event_id')} (第 {target_event_chapter} 章) 距离较远，暂不强制重聚。")

        return None

    def process_user_action(self, user_action: str) -> Optional[str]:
        """
        处理用户的行动输入，生成后续叙事。
        """
        if not self.novel_analysis or not self.chapters_data or not self.session_memory:
            return "系统错误：数据未初始化。"

        current_chapter_text_segment = self._get_current_chapter_segment_text()
        plot_memory_summary = json.dumps(self.session_memory[-3:], ensure_ascii=False, indent=2)

        last_event_time = self.session_memory[-1].get("event_time_readable_context",
                                                      f"第 {self._get_current_chapter_number()} 章")
        last_event_desc = self.session_memory[-1].get("protagonist_action_summary", "先前行动")

        current_actual_chapter_num_for_context = self._get_current_chapter_number()

        core_settings_context = self._get_relevant_core_settings_summary(
            current_event_context=f"当前时间点约在 {last_event_time} (第 {current_actual_chapter_num_for_context} 章内)，主角刚完成：{last_event_desc}"
        )
        reconvergence_plan_info = self._determine_reconvergence_plan()

        user_prompt_content = prompts.get_narrative_continuation_user_prompt_content(
            current_chapter_segment_text=current_chapter_text_segment,
            plot_memory_archive_summary=plot_memory_summary,
            core_settings_summary_for_current_context=core_settings_context,
            user_action=user_action,
            current_chapter_number_for_context=current_actual_chapter_num_for_context,
            planned_reconvergence_info=reconvergence_plan_info
        )

        self.conversation_history.append({"role": "user", "content": user_prompt_content})
        if len(self.conversation_history) > (1 + 5 * 2):
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-(5 * 2):]

        print(
            f"请求LLM ({self.llm_writer_client.client_type} - {self.writing_model_name}) 生成叙事后续 (基于第 {current_actual_chapter_num_for_context} 章上下文)...")
        llm_response = self.llm_writer_client.generate_chat_completion(
            self.writing_model_name, self.conversation_history, stream=False, expect_json_in_content=True
        )

        if llm_response and llm_response.get("message") and isinstance(llm_response["message"].get("content"), str):
            full_output = llm_response["message"]["content"]
            narrative_text, metadata = utils.extract_narrative_and_metadata(full_output)

            if metadata is None:
                print(f"警告：未能从LLM输出中解析元数据。LLM原始输出: {full_output[:300]}...")
                metadata = {
                    "protagonist_action_summary": f"主角执行了: {user_action[:50]}...",
                    "event_time_readable_context": f"第 {self._get_current_chapter_number()} 章附近 (AI未提供时间)",
                    "immediate_consequences_and_observations": ["剧情继续发展。"],
                    "character_state_changes": {}, "item_changes": {}, "world_state_changes": [],
                    "divergence_from_original_plot": {"level": "未知", "original_timeline_event_ref": None,
                                                      "description_of_divergence": "AI未提供分析"},
                    "current_chapter_progression_hint": None
                }
                if not narrative_text.strip(): narrative_text = "（AI未能生成有效的后续剧情和元数据。）"

            turn_id = self.session_memory[-1]["turn_id"] + 1
            self._update_session_memory_entry(turn_id=turn_id, user_action=user_action, narrative_text=narrative_text,
                                              metadata=metadata)
            self._update_current_narrative_chapter_index(metadata.get("current_chapter_progression_hint"))
            self.conversation_history.append({"role": "assistant", "content": full_output})  # 存储包含元数据标记的完整回复
            return narrative_text
        else:
            error_msg = f"错误：未能从LLM ({self.writing_model_name}) 获取叙事后续。响应: {llm_response}"
            print(error_msg)
            return error_msg

    def end_session(self) -> str:
        """结束当前的叙事会话。"""
        print("--- 阶段 4：结束叙事会话 ---")
        if utils.write_json_file(self.session_memory, self.session_memory_path):
            message = f"互动会话结束。会话记忆已保存到: {self.session_memory_path}"
        else:
            message = f"互动会话结束。保存会话记忆到 {self.session_memory_path} 时出错。"
        self.conversation_history = []
        return message

    def get_state_for_saving(self) -> Dict[str, Any]:
        """返回叙事引擎的当前状态，用于保存游戏。"""
        if self.session_memory:
            utils.write_json_file(self.session_memory, self.session_memory_path)
        return {
            "current_narrative_chapter_index": self.current_narrative_chapter_index,
            "conversation_history": self.conversation_history,
            "session_memory_path": self.session_memory_path,
        }

    def _load_state(self, saved_state: Dict[str, Any]):
        """从字典加载叙事引擎的状态。"""
        if not self._load_core_data():
            raise ValueError("恢复叙事引擎状态时加载核心数据 (章节/分析) 失败。")

        self.current_narrative_chapter_index = saved_state.get("current_narrative_chapter_index", 0)
        # 确保加载的 chapter_index 在 chapters_data 的有效范围内
        if not (self.chapters_data and 0 <= self.current_narrative_chapter_index < len(self.chapters_data)):
            print(f"警告：加载的 current_narrative_chapter_index ({self.current_narrative_chapter_index}) "
                  f"超出了章节数据范围 (0-{len(self.chapters_data) - 1 if self.chapters_data else -1})。将重置为0。")
            self.current_narrative_chapter_index = 0

        self.conversation_history = saved_state.get("conversation_history", [])

        session_memory_file_path = saved_state.get("session_memory_path", self.session_memory_path)
        if os.path.exists(session_memory_file_path):
            self.session_memory = utils.read_json_file(session_memory_file_path) or []
            print(f"会话记忆已从 {session_memory_file_path} 加载")
        else:
            print(f"警告: 会话记忆文件 {session_memory_file_path} 在状态加载期间未找到。将以空会话记忆开始。")
            self.session_memory = []

        # 如果对话历史为空但会话记忆有内容，尝试从 session_memory 重建最后一次AI的完整回复
        if not self.conversation_history and self.session_memory:
            print("尝试从最后一个会话记忆回合重建部分对话历史。")
            self.conversation_history = [{"role": "system", "content": prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT}]
            last_turn = self.session_memory[-1]

            # 尝试重建包含元数据标记的 assistant 消息
            reconstructed_assistant_message = last_turn.get("generated_narrative_segment", "")
            # 从 session_memory 的 last_turn 中提取元数据字段来重建元数据JSON块
            # 这需要确保 session_memory 中存储了所有必要的元数据字段
            # (我们已经在 _update_session_memory_entry 中这样做了)
            metadata_for_reconstruction = {
                "protagonist_action_summary": last_turn.get("protagonist_action_summary"),
                "event_time_readable_context": last_turn.get("event_time_readable_context"),
                "immediate_consequences_and_observations": last_turn.get("immediate_consequences_and_observations", []),
                "character_state_changes": last_turn.get("character_state_changes", {}),
                "item_changes": last_turn.get("item_changes", {}),
                "world_state_changes": last_turn.get("world_state_changes", []),
                "divergence_from_original_plot": last_turn.get("divergence_from_original_plot", {}),
                "current_chapter_progression_hint": last_turn.get("current_chapter_progression_hint")
            }
            # 移除值为None的键，以匹配LLM通常不输出空键的行为
            metadata_for_reconstruction = {k: v for k, v in metadata_for_reconstruction.items() if v is not None}

            if metadata_for_reconstruction:  # 仅当有实际元数据时才添加块
                metadata_json_str = json.dumps(metadata_for_reconstruction, ensure_ascii=False, indent=2)
                reconstructed_assistant_message += f"\n[NARRATIVE_METADATA_JSON_START]\n{metadata_json_str}\n[NARRATIVE_METADATA_JSON_END]"

            if reconstructed_assistant_message.strip():
                self.conversation_history.append({"role": "assistant", "content": reconstructed_assistant_message})

        print(
            f"叙事引擎状态已加载: 章节索引 {self.current_narrative_chapter_index} (第 {self._get_current_chapter_number()} 章), "
            f"对话历史长度 {len(self.conversation_history)}, 会话记忆长度 {len(self.session_memory)}")


if __name__ == "__main__":
    print("叙事引擎请通过主应用运行测试。")