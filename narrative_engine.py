# narrative_engine.py
# 该文件实现了叙事引擎，负责处理用户与小说的交互。

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
import utils
import prompts  # 确保 prompts 模块被导入
import traceback  # 引入 traceback


class NarrativeEngine:
    """叙事引擎类，负责处理用户与小说的交互。"""

    def __init__(self, llm_client, novel_data_dir: str, chapters_dir: str, analysis_path: str, model_name: str,
                 saved_state: Optional[Dict[str, Any]] = None):
        """
        初始化叙事引擎。

        Args:
            llm_client: LLM客户端实例。
            novel_data_dir: 小说数据目录路径。
            chapters_dir: 章节目录路径。
            analysis_path: 分析结果文件路径。
            model_name: 使用的模型名称。
            saved_state: 可选的保存状态，用于恢复引擎状态。
        """
        self.llm_client = llm_client
        self.novel_data_dir = novel_data_dir
        self.chapters_dir = chapters_dir
        self.analysis_path = analysis_path
        self.model_name = model_name
        self.session_memory_path = os.path.join(novel_data_dir, 'session_memory.json')
        self.last_error = None

        self.analysis = utils.read_json_file(analysis_path) or {}
        self.chapters_data = self._load_chapters_data()

        # 默认值
        self.session_memory = []
        self.current_narrative_chapter_index = 0
        self.conversation_history = []

        if saved_state:
            self._load_state(saved_state)
        # else: # 这些默认值已在上面设置
        # self.session_memory = []
        # self.current_narrative_chapter_index = 0
        # self.conversation_history = []

    def _load_chapters_data(self) -> List[Dict[str, Any]]:
        """加载章节数据"""
        chapters_data_path = os.path.join(self.novel_data_dir, 'chapters_data.json')
        loaded_data = utils.read_json_file(chapters_data_path)
        if loaded_data and isinstance(loaded_data, list):
            return loaded_data

        print(f"警告: 未找到或无法加载 {chapters_data_path}。尝试从目录结构构建。")
        chapters_data = []
        if os.path.exists(self.chapters_dir):
            try:
                chapter_files = sorted(
                    [f for f in os.listdir(self.chapters_dir) if f.startswith('chapter_') and f.endswith('.txt')])
                for i, file_name in enumerate(chapter_files):
                    chapter_path = os.path.join(self.chapters_dir, file_name)
                    chapter_content = utils.read_text_file(chapter_path)
                    if chapter_content:
                        num_match = re.search(r'chapter_(\d+)', file_name)
                        chapter_number_from_file = int(num_match.group(1)) if num_match else i + 1
                        title_from_content_match = re.search(
                            r'^(第[一二三四五六七八九十百千万零\d]+章.*?)$|^(Chapter\s+\d+.*?)$',
                            chapter_content.splitlines()[0] if chapter_content else "", re.MULTILINE)
                        title = title_from_content_match.group(
                            0).strip() if title_from_content_match else f"第{chapter_number_from_file}章"
                        chapters_data.append({
                            "chapter_number": chapter_number_from_file,
                            "title": title,
                            "content": chapter_content,
                            "path": chapter_path
                        })
            except Exception as e:
                print(f"从目录构建章节数据时出错: {e}")
        if chapters_data:
            utils.write_json_file(chapters_data, chapters_data_path)
            print(f"已从目录结构构建并保存章节数据到 {chapters_data_path}")
        return chapters_data

    def _load_state(self, state: Dict[str, Any]) -> None:
        """从保存的状态加载引擎状态"""
        self.session_memory = state.get("session_memory", [])
        self.current_narrative_chapter_index = state.get("current_narrative_chapter_index", 0)
        self.conversation_history = state.get("conversation_history", [])
        self.model_name = state.get("model_name", self.model_name)
        # 确保加载的章节索引在有效范围内
        if not (0 <= self.current_narrative_chapter_index < len(self.chapters_data)) and self.chapters_data:
            print(f"警告: 从存档加载的章节索引 {self.current_narrative_chapter_index} 无效，重置为0。")
            self.current_narrative_chapter_index = 0
        elif not self.chapters_data:  # 如果章节数据为空，也无法定位章节
            self.current_narrative_chapter_index = 0

        print(f"叙事引擎状态已从存档加载。当前章节索引: {self.current_narrative_chapter_index}, 模型: {self.model_name}")
        print(f"加载的 session_memory 条目数: {len(self.session_memory)}")
        print(f"加载的 conversation_history 条目数: {len(self.conversation_history)}")

    def get_state_for_saving(self) -> Dict[str, Any]:
        """获取当前状态用于保存"""
        return {
            "session_memory": self.session_memory,
            "current_narrative_chapter_index": self.current_narrative_chapter_index,
            "conversation_history": self.conversation_history,
            "novel_data_dir": self.novel_data_dir,
            "chapters_dir": self.chapters_dir,
            "analysis_path": self.analysis_path,
            "model_name": self.model_name
        }

    def _get_current_chapter_number(self) -> int:
        """获取当前叙事索引对应的实际章节号 (通常用于显示)"""
        if self.chapters_data and 0 <= self.current_narrative_chapter_index < len(self.chapters_data):
            return self.chapters_data[self.current_narrative_chapter_index].get("chapter_number",
                                                                                self.current_narrative_chapter_index + 1)
        return self.current_narrative_chapter_index + 1  # Fallback

    def _get_relevant_core_settings_summary(self, current_event_context: Optional[str] = None) -> str:
        """获取与当前情境相关的核心设定摘要"""
        if not self.analysis:
            return "错误：小说分析数据未加载。"
        summary_parts = []
        actual_chapter_num_display = self._get_current_chapter_number()
        summary_parts.append(f"当前故事焦点章节: 第 {actual_chapter_num_display} 章附近。")
        world_overview = self.analysis.get("world_building", [])
        if world_overview and isinstance(world_overview, list) and len(world_overview) > 0:
            overview_desc = world_overview[0].get("description", "")
            if overview_desc:
                summary_parts.append(f"- 世界观概览: {overview_desc[:300]}...")
        plot_summary_text = self.analysis.get("plot_summary", "")
        if plot_summary_text:
            summary_parts.append(f"- 已发生的原著主线概要（节选）: {plot_summary_text[:300]}...")
        characters_info = self.analysis.get("characters", [])
        if characters_info:
            char_summaries = []
            for char_data in characters_info[:3]:  # 简单取前几个
                char_summaries.append(
                    f"{char_data.get('name', '未知角色')}: {char_data.get('description', '暂无描述')[:100]}...")
            if char_summaries:
                summary_parts.append(f"- 主要相关角色信息: {'; '.join(char_summaries)}")
        if self.session_memory:
            last_mem = self.session_memory[-1]
            last_observations = last_mem.get("immediate_consequences_and_observations", [])
            if last_observations:
                summary_parts.append(f"- 主角最近的观察/经历: {'; '.join(last_observations)[:200]}...")
        if current_event_context:
            summary_parts.append(f"- 当前主角面临的情境/决策点: {current_event_context}")
        return "\n".join(summary_parts)

    def _get_current_chapter_segment_text(self) -> str:
        """获取当前叙事点附近的原文章节片段文本。"""
        if not self.chapters_data:
            return "错误：章节数据未加载或为空。"
        if not (0 <= self.current_narrative_chapter_index < len(self.chapters_data)):
            print(
                f"警告: _get_current_chapter_segment_text 中 current_narrative_chapter_index ({self.current_narrative_chapter_index}) 超出范围 [0, {len(self.chapters_data) - 1}]。将尝试使用最后/第一个可用章节。")
            self.current_narrative_chapter_index = max(0, min(self.current_narrative_chapter_index,
                                                              len(self.chapters_data) - 1 if self.chapters_data else 0))

        if not self.chapters_data:  # 再次检查，如果修复后仍然为空
            return "错误：章节数据为空，无法获取任何章节片段。"

        # 简化窗口逻辑，主要聚焦当前章节，可按需扩展
        window_before = 1  # 可配置
        window_after = 1  # 可配置
        start_idx = max(0, self.current_narrative_chapter_index - window_before)
        end_idx = min(len(self.chapters_data), self.current_narrative_chapter_index + window_after + 1)
        segment_chapters_data = self.chapters_data[start_idx:end_idx]

        if not segment_chapters_data:
            if self.chapters_data:  # 至少有一个章节
                current_chapter_data = self.chapters_data[self.current_narrative_chapter_index]
                return f"【原文参考：第 {current_chapter_data.get('chapter_number')} 章 - {current_chapter_data.get('title', '无标题')}】\n{current_chapter_data.get('content', '章节内容缺失')}"
            return "错误：无法获取任何章节片段。"

        formatted_segments = []
        for chapter_data in segment_chapters_data:
            is_current_focus = (chapter_data == self.chapters_data[self.current_narrative_chapter_index])
            prefix = "【当前故事焦点章节原文】" if is_current_focus else "【上下文参考章节原文】"
            formatted_segments.append(
                f"{prefix} (第 {chapter_data.get('chapter_number')} 章: {chapter_data.get('title', '无标题')})\n"
                f"{chapter_data.get('content', '章节内容缺失')}"
            )
        return "\n\n---\n\n".join(formatted_segments)

    def _initialize_session_memory(self, protagonist_initial_state: Dict[str, Any], initial_narrative_text: str):
        """初始化会话记忆。这是叙事开始时的第一条记忆。"""
        actual_chapter_num_display = self._get_current_chapter_number()
        initial_metadata = {
            "protagonist_action_summary": "主角开始了他的“穿书”冒险。",
            "event_time_readable_context": protagonist_initial_state.get("time",
                                                                         f"第 {actual_chapter_num_display} 章开端"),
            "immediate_consequences_and_observations": [
                f"主角身份: {protagonist_initial_state.get('name', '你')}",
                f"初始地点: {protagonist_initial_state.get('location', '一个未知的地方')}",
                "故事正式拉开序幕，你发现自己身处一个新的世界...",
                initial_narrative_text[:100] + "..."
            ],
            "character_state_changes": {
                protagonist_initial_state.get("name", "主角"): {
                    "mood": "惊奇/困惑 (初始状态)",
                    "location": protagonist_initial_state.get('location', '未知地点'),
                    "status_effect": "刚刚穿越"
                }
            },
            "item_changes": {"主角": {"acquired": ["新的记忆"], "lost": []}},
            "world_state_changes": ["交互式叙事已启动。", f"原著故事线在第 {actual_chapter_num_display} 章附近展开。"],
            "divergence_from_original_plot": {
                "level": "无",
                "original_timeline_event_ref": None,
                "description_of_divergence": "故事刚刚开始，尚未与原著剧情发生显著交互或偏离。"
            },
            "current_chapter_progression_hint": f"已进入原著第 {actual_chapter_num_display} 章的开端部分。"
        }
        self.session_memory = [{
            "turn_id": 0,  # 对于新的会话，turn_id 从0开始
            "user_input_signal": "SESSION_START",
            "user_free_text": "开始“穿书”之旅",
            "generated_narrative_segment": initial_narrative_text,
            **initial_metadata
        }]
        # utils.write_json_file(self.session_memory, self.session_memory_path) # 存档时统一保存
        print(f"初始会话记忆已创建。")

    def initialize_narrative_session(self, initial_context_chapters: int,
                                     window_before: int, window_after: int,
                                     divergence_threshold: float, model_params: Dict[str, Any],
                                     is_resuming: bool = False) -> Optional[str]:
        """
        初始化或恢复叙事会话。

        Args:
            initial_context_chapters: 用于确定初始上下文范围的章节数 (来自配置)。
            window_before: (当前未使用，_get_current_chapter_segment_text 中有自己的窗口逻辑)
            window_after: (当前未使用，同上)
            divergence_threshold: (当前未使用，用于剧情偏离判断的阈值)
            model_params: 包含temperature, top_p等的模型参数字典。
            is_resuming: 如果为True，则尝试从已加载的状态恢复，否则开始新的叙事。

        Returns:
            初始或最后已知的叙事文本，如果操作失败则返回None。
        """
        self.last_error = None
        try:
            if not self.chapters_data or not self.analysis:
                self.last_error = "错误：小说章节数据或分析结果未加载，无法开始/恢复叙事。"
                print(self.last_error)
                return None

            if is_resuming:
                print("尝试恢复叙事会话...")
                if self.session_memory and self.conversation_history:
                    # 状态已由 __init__ 中的 _load_state 加载。
                    # 我们需要返回最后一条 AI 的消息给 UI。
                    last_ai_message = None
                    for entry in reversed(self.conversation_history):  # 从后往前找最后一条AI的回复
                        if entry.get("role") == "assistant" or entry.get("role") == "system":  # system 用于最初的系统消息
                            last_ai_message = entry.get("content")
                            break

                    if last_ai_message is not None:  # 即使是空字符串也算找到
                        print(f"成功恢复。最后 AI 消息 (部分): {last_ai_message[:100]}...")
                        # 引擎已处于正确的加载状态，直接返回最后的消息即可。
                        return last_ai_message
                    else:
                        # 这种情况表示 _load_state 可能正确加载了 session_memory，
                        # 但 conversation_history 为空或没有 AI/系统消息。
                        # 这在存档正确的情况下不太可能发生。
                        print(
                            "警告: 正在恢复，但在已加载的 conversation_history 中未找到先前的 AI 消息。将尝试重新初始化当前章节。")
                        # 此处将退回到重新初始化当前章节的逻辑。
                else:
                    # is_resuming 为 true，但状态未正确加载（例如，存档文件损坏或不完整）。
                    print("警告: 尝试恢复，但 session_memory 或 conversation_history 为空。将尝试重新初始化当前章节。")
                    # 此处将退回到重新初始化当前章节的逻辑。

            # 如果不是恢复模式，或者恢复模式未能找到有效的继续点，则进行初始化。
            # current_narrative_chapter_index 应该是 __init__ 时或 _load_state 时设置的。
            print(f"为章节索引 {self.current_narrative_chapter_index} 初始化新的叙事会话。")
            novel_title = self.analysis.get("title", "未知小说")

            # 确保 current_narrative_chapter_index 在有效范围内
            if not (0 <= self.current_narrative_chapter_index < len(self.chapters_data)):
                print(
                    f"警告: current_narrative_chapter_index ({self.current_narrative_chapter_index}) 超出范围。重置为 0。")
                self.current_narrative_chapter_index = 0
                if not self.chapters_data:  # 如果章节数据本身就为空
                    self.last_error = "错误：章节数据为空，无法初始化叙事。"
                    print(self.last_error)
                    return None

            current_chapter_data = self.chapters_data[self.current_narrative_chapter_index]
            actual_chapter_num_for_prompt = current_chapter_data.get("chapter_number",
                                                                     self.current_narrative_chapter_index + 1)

            protagonist_name = "你"  # 默认名
            if self.analysis.get("characters") and len(self.analysis["characters"]) > 0:
                main_char_name_candidate = self.analysis["characters"][0].get("name")
                if main_char_name_candidate: protagonist_name = main_char_name_candidate

            protagonist_initial_state_info = {  # 用于生成提示
                "name": protagonist_name,
                "location": f"原著第 {actual_chapter_num_for_prompt} 章的场景附近",
                "time": f"第 {actual_chapter_num_for_prompt} 章"  # 简化时间表示
            }

            initial_chapters_text_for_llm = self._get_current_chapter_segment_text()
            relevant_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"故事从《{novel_title}》第 {actual_chapter_num_for_prompt} 章的场景展开。"  # 动态上下文
            )

            initial_prompt_for_llm = prompts.get_initial_narrative_prompt(
                novel_title=novel_title,
                initial_chapters_text=initial_chapters_text_for_llm,
                relevant_core_settings_summary=relevant_settings_summary_for_llm,
                protagonist_initial_state=json.dumps(protagonist_initial_state_info, ensure_ascii=False),
                current_chapter_number_for_context=actual_chapter_num_for_prompt,
                initial_context_chapters=initial_context_chapters
            )

            print(f"发送给LLM的初始叙事提示 (部分):\n{initial_prompt_for_llm[:500]}...")
            initial_narrative_text = self._call_llm_for_narrative(initial_prompt_for_llm, model_params)

            if not initial_narrative_text:  # 如果LLM调用失败
                self.last_error = self.last_error or "LLM未能生成初始叙事文本。"
                print(f"生成初始叙事失败。{self.last_error}")
                return None

            print(f"LLM生成的初始叙事 (部分):\n{initial_narrative_text[:300]}...")

            # 既然是（重新）初始化，就需要设置 session_memory 和 conversation_history
            self._initialize_session_memory(protagonist_initial_state_info, initial_narrative_text)
            self.conversation_history = [{  # 重置对话历史，以新生成的叙事开始
                "role": "system",  # 或 "assistant"
                "content": initial_narrative_text,
                "timestamp": time.time()
            }]

            return initial_narrative_text

        except Exception as e:
            self.last_error = f"初始化/恢复叙事会话时发生严重异常: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            return None

    def _call_llm_for_narrative(self, prompt_text: str, model_params: Dict[str, Any]) -> Optional[str]:
        """辅助方法，调用LLM生成初始叙事文本。"""
        if not self.llm_client:
            self.last_error = "LLM客户端未初始化。"
            print(self.last_error)
            return None
        messages = [{"role": "user", "content": prompt_text}]
        try:
            response_dict = self.llm_client.generate_chat_completion(
                model=self.llm_client.default_model,  # 使用客户端的默认模型
                messages=messages,
                options=model_params
            )
            if response_dict and response_dict.get("message") and response_dict.get("message").get(
                    "content") is not None:
                return response_dict["message"]["content"]
            else:
                self.last_error = f"LLM叙事调用返回空或无效响应: {response_dict}"
                print(self.last_error)
                return None
        except Exception as e:
            self.last_error = f"LLM叙事调用时出错: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            return None

    def process_user_action(self, user_action: str, model_params: Dict[str, Any]) -> Optional[str]:
        """处理用户行动。"""
        self.last_error = None
        try:
            if not user_action.strip():
                self.last_error = "用户行动不能为空。"
                print(self.last_error)
                return None

            # 将用户行动加入对话历史 (在调用LLM之前)
            self.conversation_history.append({
                "role": "user",
                "content": user_action,
                "timestamp": time.time()
            })

            current_chapter_segment_for_llm = self._get_current_chapter_segment_text()
            plot_memory_summary_for_llm = self._get_plot_memory_summary()

            protagonist_name_for_context = "主角"
            if self.session_memory:
                last_char_states = self.session_memory[-1].get("character_state_changes", {})
                # 尝试获取主角名，如果用 "主角" 作为键
                if "主角" in last_char_states and "name" in last_char_states["主角"]:
                    protagonist_name_for_context = last_char_states["主角"]["name"]
                # 或者，如果键是实际角色名
                elif self.analysis and self.analysis.get("characters"):
                    first_char_name = self.analysis["characters"][0].get("name") if self.analysis[
                        "characters"] else None
                    if first_char_name and first_char_name in last_char_states:
                        protagonist_name_for_context = first_char_name

            core_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"主角({protagonist_name_for_context})的最新行动是: '{user_action[:50]}...'"
            )

            actual_current_chapter_num_display = self._get_current_chapter_number()
            planned_reconvergence_info_for_llm = None  # 可按需实现

            # 构建LLM的messages，包含系统提示和用户提示内容
            # 注意：Ollama API 通常期望 messages 列表交替出现 user 和 assistant 角色。
            # 如果 conversation_history 已经包含了之前的交互，我们可能需要用它来构建 messages。
            # 简化：暂时只用最新的系统提示 + 当前用户行动构成的用户提示。
            # 更完善的做法是传递最近几轮的 self.conversation_history (格式化为LLM期望的列表)

            llm_messages_for_continuation = []
            llm_messages_for_continuation.append({"role": "system", "content": prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT})

            # 添加部分历史对话作为上下文 (如果存在)
            # 取最近 N 条消息，确保 user/assistant 交替
            history_context_count = 4  # 例如取最近4条 (2轮对话)
            relevant_history = self.conversation_history[-(history_context_count + 1):-1]  # 不包括当前用户输入
            for hist_entry in relevant_history:
                if hist_entry.get("role") in ["user", "assistant", "system"]:  # system 可能是开篇
                    llm_messages_for_continuation.append({"role": hist_entry["role"], "content": hist_entry["content"]})

            user_prompt_content = prompts.get_narrative_continuation_user_prompt_content(
                current_chapter_segment_text=current_chapter_segment_for_llm,
                plot_memory_archive_summary=plot_memory_summary_for_llm,
                core_settings_summary_for_current_context=core_settings_summary_for_llm,
                user_action=user_action,  # 用户最新的行动已通过上面加入到 conversation_history
                current_chapter_number_for_context=actual_current_chapter_num_display,
                planned_reconvergence_info=planned_reconvergence_info_for_llm
            )
            llm_messages_for_continuation.append({"role": "user", "content": user_prompt_content})

            print(f"发送给LLM的叙事继续用户提示内容 (部分):\n{user_prompt_content[:500]}...")

            if not self.llm_client:
                self.last_error = "LLM客户端未初始化。"
                print(self.last_error)
                return None

            llm_response_dict = self.llm_client.generate_chat_completion(
                model=self.llm_client.default_model,  # 使用客户端的默认模型
                messages=llm_messages_for_continuation,  # 传递构建好的消息列表
                options=model_params
            )

            if not llm_response_dict or not llm_response_dict.get("message") or llm_response_dict.get("message").get(
                    "content") is None:
                self.last_error = self.last_error or f"LLM未能生成有效的叙事响应。响应: {llm_response_dict}"
                print(self.last_error)
                # 从 conversation_history 中移除刚才添加的用户行动，因为处理失败了
                if self.conversation_history and self.conversation_history[-1].get("role") == "user":
                    self.conversation_history.pop()
                return None

            raw_llm_output = llm_response_dict["message"]["content"]
            narrative_text, metadata_json = self._extract_narrative_and_metadata(raw_llm_output)

            if narrative_text is None and metadata_json is None:  # 如果提取完全失败
                narrative_text = raw_llm_output  # 将整个输出视为叙事
                print("警告: 未能从LLM输出中分离元数据JSON，将整个输出视为叙事文本。")
            elif narrative_text is None and metadata_json is not None:  # 只有元数据，没有叙事
                self.last_error = "LLM仅返回元数据，没有叙事文本。"
                print(self.last_error)
                if self.conversation_history and self.conversation_history[-1].get("role") == "user":
                    self.conversation_history.pop()
                return None

            print(f"LLM生成的叙事文本 (部分):\n{narrative_text[:300] if narrative_text else '无叙事文本'}...")
            if metadata_json:
                print(
                    f"LLM生成的元数据JSON (部分):\n{json.dumps(metadata_json, ensure_ascii=False, indent=2)[:300]}...")

            self._update_session_memory(user_action, narrative_text, metadata_json)

            # 将AI的回复加入对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": narrative_text,
                "timestamp": time.time()
            })

            self._check_and_advance_chapter(metadata_json)

            return narrative_text
        except Exception as e:
            self.last_error = f"处理用户行动时发生严重错误: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            # 尝试从 conversation_history 中移除刚才添加的用户行动
            if self.conversation_history and self.conversation_history[-1].get("role") == "user":
                try:
                    self.conversation_history.pop()
                except IndexError:
                    pass  # 如果列表已空
            return None

    def _extract_narrative_and_metadata(self, raw_output: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """从LLM的原始输出中分离叙事文本和元数据JSON。"""
        narrative_text = raw_output
        metadata_json = None
        try:
            start_marker = "[NARRATIVE_METADATA_JSON_START]"
            end_marker = "[NARRATIVE_METADATA_JSON_END]"

            # 尝试找到最后一个标记对，以应对LLM可能重复输出标记的情况
            start_index = raw_output.rfind(start_marker)

            if start_index != -1:
                # 从start_index之后开始查找end_marker
                end_index = raw_output.find(end_marker, start_index + len(start_marker))

                if end_index != -1 and end_index > start_index:
                    json_str = raw_output[start_index + len(start_marker):end_index].strip()
                    narrative_text_before_marker = raw_output[:start_index].strip()

                    # 检查标记之后是否还有文本，这通常不应该发生
                    narrative_text_after_marker = raw_output[end_index + len(end_marker):].strip()
                    if narrative_text_after_marker:
                        print(f"警告: 在元数据结束标记之后发现额外文本: '{narrative_text_after_marker[:50]}...'")
                        # 决定如何处理：可以附加到叙事文本，或忽略
                        # 为简单起见，我们主要关注标记之前的部分作为叙事

                    narrative_text = narrative_text_before_marker

                    try:
                        metadata_json = json.loads(json_str)
                    except json.JSONDecodeError as je:
                        print(f"解析从LLM提取的元数据JSON失败: {je}")
                        print(f"原始JSON字符串块: {json_str}")
                        metadata_json = None  # 解析失败，则元数据为None
                        # 此时 narrative_text 仍然是标记之前的部分
                else:
                    # 找到了开始标记但未找到有效的结束标记
                    print("警告: 找到了元数据JSON开始标记但未找到有效的结束标记。整个输出可能都是叙事。")
                    narrative_text = raw_output  # 保守地将整个输出视为叙事
                    metadata_json = None
            else:
                # 没有找到开始标记，整个输出被视为叙事
                narrative_text = raw_output
                metadata_json = None

        except Exception as e:
            print(f"提取叙事和元数据时出错: {e}")
            # 发生未知错误，保守返回原始输出作为叙事，元数据为None
            return raw_output, None

        return narrative_text if narrative_text and narrative_text.strip() else None, metadata_json

    def _get_plot_memory_summary(self) -> str:
        """从 session_memory 构建剧情记忆档案摘要，供LLM参考。"""
        if not self.session_memory:
            return "剧情刚刚开始，尚无重要记忆。"

        memories_to_summarize = self.session_memory[-3:]  # 取最近3轮的“记忆点”
        summary_entries = []

        for i, mem_entry in enumerate(memories_to_summarize):
            turn_id = mem_entry.get("turn_id", "未知回合")
            # user_action = mem_entry.get("user_free_text", "无用户行动记录") # 这是原始输入
            action_summary = mem_entry.get("protagonist_action_summary", "行动摘要缺失")  # 这是LLM理解的行动
            narrative_segment = mem_entry.get("generated_narrative_segment", "叙事片段缺失")
            consequences = mem_entry.get("immediate_consequences_and_observations", [])
            time_context = mem_entry.get("event_time_readable_context", "时间未知")

            entry_str = f"记忆点 {turn_id} ({time_context}):\n"
            # if user_action != "开始“穿书”之旅" and user_action != "开始穿越体验": # 避免冗余
            entry_str += f"  主角行动概要: {action_summary[:100]}...\n"
            entry_str += f"  剧情发展/AI叙述: {narrative_segment[:150]}...\n"
            if consequences:
                entry_str += f"  主要后果/观察: {'; '.join(map(str, consequences))[:150]}...\n"  # 确保是字符串
            summary_entries.append(entry_str)

        if not summary_entries:
            return "最近无重要剧情发展。"  # 如果筛选后为空

        return "最近的剧情记忆回顾：\n" + "\n---\n".join(summary_entries)

    def _update_session_memory(self, user_action: str, generated_narrative: str,
                               llm_metadata: Optional[Dict[str, Any]] = None) -> None:
        """更新会话记忆。"""
        turn_id = len(self.session_memory)  # 新的记忆点ID

        if not llm_metadata or not isinstance(llm_metadata, dict):
            print("警告: LLM未提供有效的元数据，将生成基础元数据。")
            actual_current_chapter_num_display = self._get_current_chapter_number()
            prev_time_context = f"第 {actual_current_chapter_num_display} 章内某时"
            if self.session_memory:  # 如果已有记忆，尝试获取上一条的时间
                prev_time_context = self.session_memory[-1].get("event_time_readable_context", prev_time_context)

            llm_metadata = {  # 构造一个默认的元数据结构
                "protagonist_action_summary": user_action[:80] + "..." if len(user_action) > 80 else user_action,
                "event_time_readable_context": f"{prev_time_context}之后不久",
                "immediate_consequences_and_observations": [
                    generated_narrative[:100] + "..."] if generated_narrative else ["叙事为空"],
                "character_state_changes": {}, "item_changes": {},
                "world_state_changes": ["剧情因主角行动而推进。"],
                "divergence_from_original_plot": {
                    "level": "未知", "original_timeline_event_ref": None,
                    "description_of_divergence": "由于缺少LLM元数据，偏离情况未知。"
                },
                "current_chapter_progression_hint": f"在第 {actual_current_chapter_num_display} 章中继续探索。"
            }

        memory_entry = {
            "turn_id": turn_id,
            "user_input_signal": "USER_ACTION",  # 标记这是用户行动触发的记忆点
            "user_free_text": user_action,  # 保存用户的原始输入
            "generated_narrative_segment": generated_narrative if generated_narrative else "",  # 保存AI生成的叙事
            **llm_metadata  # 合并LLM提供的（或我们生成的默认）元数据
        }
        self.session_memory.append(memory_entry)

        # 会话记忆通常在游戏存档时一起保存，而不是每一步都写盘，以提高性能
        # if not utils.write_json_file(self.session_memory, self.session_memory_path):
        #     print(f"警告: 更新并保存会话记忆到 {self.session_memory_path} 失败。")
        print(f"会话记忆已更新，当前共 {len(self.session_memory)} 条记忆点。")

    def _check_and_advance_chapter(self, llm_metadata: Optional[Dict[str, Any]]):
        """根据LLM元数据中的章节进展提示来尝试推进章节索引。"""
        if not llm_metadata or not isinstance(llm_metadata, dict): return  # 没有元数据无法判断

        progression_hint = llm_metadata.get("current_chapter_progression_hint", "").lower()
        advance_chapter_flag = False  # 是否应该尝试推进章节的标志
        target_chapter_num_from_hint = -1  # 从提示中解析出的目标章节号

        # 检查是否明确提及“下一章”或类似词语
        if "下一章" in progression_hint or "next chapter" in progression_hint or "进入新章节" in progression_hint:
            advance_chapter_flag = True

        # 尝试从提示中解析具体的章节号，例如 "已进入第 5 章"
        num_match = re.search(r'(?:进入|到达|完成|开始).*(?:第|chapter)\s*(\d+)\s*(?:章|节)', progression_hint,
                              re.IGNORECASE)
        if num_match:
            try:
                hinted_chapter_num = int(num_match.group(1))
                current_actual_chapter_num = self._get_current_chapter_number()  # 获取当前章节的“真实”编号
                if hinted_chapter_num > current_actual_chapter_num:  # 只有当提示的章节号大于当前才认为是推进
                    advance_chapter_flag = True
                    target_chapter_num_from_hint = hinted_chapter_num
                elif hinted_chapter_num == current_actual_chapter_num and "完成" in progression_hint:  # 如果是说“完成当前章”
                    advance_chapter_flag = True  # 也尝试推进
                elif hinted_chapter_num < current_actual_chapter_num:
                    print(
                        f"LLM提示章节 {hinted_chapter_num}, 但小于当前章节 {current_actual_chapter_num}。不执行章节回退。")
            except ValueError:
                print(f"无法从章节进展提示中解析数字: '{progression_hint}'")

        if advance_chapter_flag:
            if self.current_narrative_chapter_index < len(self.chapters_data) - 1:
                # 如果有具体的目标章节号，并且能找到它
                if target_chapter_num_from_hint > 0:
                    found_target_index = -1
                    for idx, chap_data in enumerate(self.chapters_data):
                        if chap_data.get("chapter_number") == target_chapter_num_from_hint:
                            found_target_index = idx
                            break
                    if found_target_index != -1 and found_target_index > self.current_narrative_chapter_index:
                        self.current_narrative_chapter_index = found_target_index
                        new_actual_chap_num = self._get_current_chapter_number()
                        print(
                            f"根据LLM元数据，章节已精确推进到第 {new_actual_chap_num} 章 (索引 {self.current_narrative_chapter_index})。")
                    elif found_target_index != -1 and found_target_index <= self.current_narrative_chapter_index:
                        print(
                            f"LLM提示章节 {target_chapter_num_from_hint} (索引 {found_target_index}), 不大于当前索引 {self.current_narrative_chapter_index}。仅推进一章。")
                        self.current_narrative_chapter_index += 1  # 默认推进一章
                        new_actual_chap_num = self._get_current_chapter_number()
                        print(
                            f"章节已推进。当前叙事焦点章节索引: {self.current_narrative_chapter_index} (实际章节号: {new_actual_chap_num})")
                    else:  # 没找到目标章节，默认推进一章
                        print(f"LLM提示目标章节 {target_chapter_num_from_hint} 但未在数据中找到。默认推进一章。")
                        self.current_narrative_chapter_index += 1
                        new_actual_chap_num = self._get_current_chapter_number()
                        print(
                            f"章节已推进。当前叙事焦点章节索引: {self.current_narrative_chapter_index} (实际章节号: {new_actual_chap_num})")
                else:  # 没有具体目标章节号，但有推进信号，则默认推进一章
                    self.current_narrative_chapter_index += 1
                    new_actual_chap_num = self._get_current_chapter_number()
                    print(
                        f"章节已推进。当前叙事焦点章节索引: {self.current_narrative_chapter_index} (实际章节号: {new_actual_chap_num})")
            else:
                print("已是最后一章，无法再根据提示推进章节。")

    def save_state_to_file(self) -> Optional[str]:
        """将引擎状态保存到文件。"""
        try:
            save_dir = os.path.join(self.novel_data_dir, 'saves')
            os.makedirs(save_dir, exist_ok=True)

            timestamp_str = time.strftime('%Y%m%d_%H%M%S')
            novel_title_part = "untitled"
            if self.analysis and self.analysis.get("title"):  # 从已加载的分析数据中获取标题
                novel_title_part = utils.sanitize_filename(self.analysis.get("title")[:20])
            elif self.analysis and self.analysis.get("novel_title"):  # 兼容旧的分析结构
                novel_title_part = utils.sanitize_filename(self.analysis.get("novel_title")[:20])

            save_filename = f'storysave_{novel_title_part}_{timestamp_str}.json'
            save_path = os.path.join(save_dir, save_filename)

            current_state_data = self.get_state_for_saving()  # 获取包含 session_memory 和 conversation_history 的完整状态

            if utils.write_json_file(current_state_data, save_path):
                print(f"叙事引擎状态已保存到: {save_path}")
                # 同时更新会话记忆的持久化存储（如果之前不是每步都存盘）
                if not utils.write_json_file(self.session_memory, self.session_memory_path):
                    print(
                        f"警告: 保存 session_memory 到 {self.session_memory_path} 失败。存档文件仍包含最新 session_memory。")
                return save_path
            else:
                self.last_error = f"写入存档文件 {save_path} 失败。"
                print(self.last_error)
                return None
        except Exception as e:
            self.last_error = f"保存引擎状态时发生严重错误: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            return None