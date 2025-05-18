# narrative_engine.py
# 该文件实现了叙事引擎，负责处理用户与小说的交互。

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
import utils
import prompts
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
        self.model_name = model_name  # 记录引擎初始化时使用的模型名
        self.session_memory_path = os.path.join(novel_data_dir, 'session_memory.json')
        self.last_error = None  # 用于存储上一个错误信息

        # 加载分析结果
        self.analysis = utils.read_json_file(analysis_path) or {}
        self.chapters_data = self._load_chapters_data()

        # 初始化状态
        if saved_state:
            self._load_state(saved_state)
        else:
            self.session_memory = []
            self.current_narrative_chapter_index = 0  # 应该是基于0的索引
            self.conversation_history = []  # 用于存储用户和AI的对话，给LLM上下文

    def _load_chapters_data(self) -> List[Dict[str, Any]]:
        """加载章节数据"""
        chapters_data_path = os.path.join(self.novel_data_dir, 'chapters_data.json')
        loaded_data = utils.read_json_file(chapters_data_path)
        if loaded_data and isinstance(loaded_data, list):
            return loaded_data

        print(f"警告: 未找到或无法加载 {chapters_data_path}。尝试从目录结构构建。")
        # 如果没有找到chapters_data.json，尝试从chapters目录构建 (这部分逻辑可以保留作为后备)
        chapters_data = []
        if os.path.exists(self.chapters_dir):
            try:
                chapter_files = sorted(
                    [f for f in os.listdir(self.chapters_dir) if f.startswith('chapter_') and f.endswith('.txt')])
                for i, file_name in enumerate(chapter_files):
                    chapter_path = os.path.join(self.chapters_dir, file_name)
                    chapter_content = utils.read_text_file(chapter_path)
                    if chapter_content:
                        # 尝试从文件名或内容提取章节号和标题 (这部分逻辑需要健壮)
                        num_match = re.search(r'chapter_(\d+)', file_name)
                        chapter_number_from_file = int(num_match.group(1)) if num_match else i + 1

                        title_from_content_match = re.search(
                            r'^(第[一二三四五六七八九十百千万零\d]+章.*?)$|^(Chapter\s+\d+.*?)$',
                            chapter_content.splitlines()[0] if chapter_content else "", re.MULTILINE)
                        title = title_from_content_match.group(
                            0).strip() if title_from_content_match else f"第{chapter_number_from_file}章"

                        chapters_data.append({
                            "chapter_number": chapter_number_from_file,  # 实际章节号
                            "title": title,
                            "content": chapter_content,
                            "path": chapter_path
                        })
            except Exception as e:
                print(f"从目录构建章节数据时出错: {e}")

        if chapters_data:
            utils.write_json_file(chapters_data, chapters_data_path)  # 保存构建的数据
            print(f"已从目录结构构建并保存章节数据到 {chapters_data_path}")
        return chapters_data

    def _load_state(self, state: Dict[str, Any]) -> None:
        """从保存的状态加载引擎状态"""
        self.session_memory = state.get("session_memory", [])
        # current_narrative_chapter_index 应该对应 self.chapters_data 的索引
        self.current_narrative_chapter_index = state.get("current_narrative_chapter_index", 0)
        self.conversation_history = state.get("conversation_history", [])
        # model_name 也应该从存档中恢复，如果它在存档中被保存的话
        self.model_name = state.get("model_name", self.model_name)
        print(f"叙事引擎状态已从存档加载。当前章节索引: {self.current_narrative_chapter_index}, 模型: {self.model_name}")

    def get_state_for_saving(self) -> Dict[str, Any]:
        """获取当前状态用于保存"""
        return {
            "session_memory": self.session_memory,
            "current_narrative_chapter_index": self.current_narrative_chapter_index,
            "conversation_history": self.conversation_history,
            "novel_data_dir": self.novel_data_dir,  # 这些路径对于恢复很重要
            "chapters_dir": self.chapters_dir,
            "analysis_path": self.analysis_path,
            "model_name": self.model_name  # 保存当前使用的模型名
        }

    def _get_current_chapter_number(self) -> int:
        """获取当前叙事索引对应的实际章节号 (通常用于显示)"""
        if self.chapters_data and 0 <= self.current_narrative_chapter_index < len(self.chapters_data):
            # "chapter_number" 是存储在 chapters_data.json 中的实际章节号
            return self.chapters_data[self.current_narrative_chapter_index].get("chapter_number",
                                                                                self.current_narrative_chapter_index + 1)
        # 如果 chapters_data 为空或索引无效，返回基于索引的估算值（从1开始）
        return self.current_narrative_chapter_index + 1

    def _get_relevant_core_settings_summary(self, current_event_context: Optional[str] = None) -> str:
        """获取与当前情境相关的核心设定摘要"""
        if not self.analysis:  # chapters_data 的检查在 _get_current_chapter_segment_text 中
            return "错误：小说分析数据未加载。"

        summary_parts = []
        # current_narrative_chapter_index 是Python列表索引 (0-based)
        # _get_current_chapter_number() 返回的是实际章节号 (1-based)
        actual_chapter_num_display = self._get_current_chapter_number()

        # 假设 "核心设定摘要" 是为LLM准备的，使用LLM易于理解的表达
        # "小说核心设定摘要" (来自prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT)
        summary_parts.append(f"当前故事焦点章节: 第 {actual_chapter_num_display} 章附近。")

        # 从 self.analysis (final_analysis.json的内容) 提取信息
        # 这个摘要的目的是给LLM提供当前最相关的背景，而不是给用户看

        world_overview = self.analysis.get("world_building", [])
        if world_overview and isinstance(world_overview, list) and len(world_overview) > 0:
            # 通常第一个是概览
            overview_desc = world_overview[0].get("description", "")
            if overview_desc:
                summary_parts.append(f"- 世界观概览: {overview_desc[:300]}...")  # 截断以保持简洁

        plot_summary_text = self.analysis.get("plot_summary", "")
        if plot_summary_text:
            summary_parts.append(f"- 已发生的原著主线概要（节选）: {plot_summary_text[:300]}...")

        characters_info = self.analysis.get("characters", [])
        if characters_info:
            char_summaries = []
            # 挑选几个与当前章节可能相关的角色 (这需要更复杂的逻辑，暂时简化)
            # 比如，可以基于角色在 timeline_and_key_events 中最后出现的章节
            for char_data in characters_info[:3]:  # 简单取前几个
                char_summaries.append(
                    f"{char_data.get('name', '未知角色')}: {char_data.get('description', '暂无描述')[:100]}...")
            if char_summaries:
                summary_parts.append(f"- 主要相关角色信息: {'; '.join(char_summaries)}")

        # 也可以加入来自 session_memory 的最新状态作为补充
        if self.session_memory:
            last_mem = self.session_memory[-1]
            last_observations = last_mem.get("immediate_consequences_and_observations", [])
            if last_observations:
                summary_parts.append(f"- 主角最近的观察/经历: {'; '.join(last_observations)[:200]}...")

        if current_event_context:  # 用户操作的上下文
            summary_parts.append(f"- 当前主角面临的情境/决策点: {current_event_context}")

        return "\n".join(summary_parts)

    def _get_current_chapter_segment_text(self) -> str:
        """获取当前叙事点附近的原文章节片段文本。
           这是LLM的"当前章节原文片段"参考。
        """
        if not self.chapters_data:
            return "错误：章节数据未加载或为空。"

        if not (0 <= self.current_narrative_chapter_index < len(self.chapters_data)):
            print(
                f"警告: current_narrative_chapter_index ({self.current_narrative_chapter_index}) 超出范围 [0, {len(self.chapters_data) - 1}]。将尝试使用最后/第一个可用章节。")
            # 修正索引到有效范围
            self.current_narrative_chapter_index = max(0, min(self.current_narrative_chapter_index,
                                                              len(self.chapters_data) - 1))

        # 动态窗口，但确保至少包含当前章节
        # window_before 和 window_after 可以从配置中读取，如果需要的话
        # 这里我们简化，主要聚焦当前章节，并可能包含前后少量章节作为上下文
        # 来自 app_state 或 config_manager

        # TODO: 这些窗口参数应该从配置中获取，而不是硬编码或依赖外部状态
        # 暂时使用固定值或从 self.analysis (如果保存了这些参数)
        # config = config_manager.load_api_configs(DATA_DIR) # 不太好在引擎内部频繁加载
        window_before = 1  # config.get("window_before", 1)
        window_after = 1  # config.get("window_after", 1)

        start_idx = max(0, self.current_narrative_chapter_index - window_before)
        end_idx = min(len(self.chapters_data), self.current_narrative_chapter_index + window_after + 1)

        segment_chapters_data = self.chapters_data[start_idx:end_idx]

        if not segment_chapters_data:
            # 如果出现极端情况，例如chapters_data为空但代码执行到这里
            if self.chapters_data:  # 至少有一个章节
                current_chapter_data = self.chapters_data[self.current_narrative_chapter_index]
                return f"【原文参考：第 {current_chapter_data.get('chapter_number')} 章 - {current_chapter_data.get('title', '无标题')}】\n{current_chapter_data.get('content', '章节内容缺失')}"
            return "错误：无法获取任何章节片段。"

        # 格式化输出，使其对LLM更友好
        # 强调哪个是当前焦点章节
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

        # 从 prompts.py 获取NARRATIVE_ENGINE_SYSTEM_PROMPT中的JSON元数据结构作为模板
        # 这里手动构造一个初始版本
        initial_metadata = {
            "protagonist_action_summary": "主角开始了他的“穿书”冒险。",
            "event_time_readable_context": protagonist_initial_state.get("time",
                                                                         f"第 {actual_chapter_num_display} 章开端"),
            "immediate_consequences_and_observations": [
                f"主角身份: {protagonist_initial_state.get('name', '你')}",  # 使用“你”如果名字未知
                f"初始地点: {protagonist_initial_state.get('location', '一个未知的地方')}",
                "故事正式拉开序幕，你发现自己身处一个新的世界...",  # 更具代入感的描述
                initial_narrative_text[:100] + "..."  # 初始叙事本身的摘要
            ],
            "character_state_changes": {
                protagonist_initial_state.get("name", "主角"): {  # 使用 "主角" 作为通用键
                    "mood": "惊奇/困惑 (初始状态)",
                    "location": protagonist_initial_state.get('location', '未知地点'),
                    "status_effect": "刚刚穿越"
                }
            },
            "item_changes": {"主角": {"acquired": ["新的记忆"], "lost": []}},  # 象征性的物品变化
            "world_state_changes": ["交互式叙事已启动。", f"原著故事线在第 {actual_chapter_num_display} 章附近展开。"],
            "divergence_from_original_plot": {
                "level": "无",  # 初始时尚未偏离
                "original_timeline_event_ref": None,  # 参考的原著事件ID (如果有)
                "description_of_divergence": "故事刚刚开始，尚未与原著剧情发生显著交互或偏离。"
            },
            "current_chapter_progression_hint": f"已进入原著第 {actual_chapter_num_display} 章的开端部分。"
        }

        self.session_memory = [{
            "turn_id": 0,  # 第一轮，系统生成初始场景
            "user_input_signal": "SESSION_START",  # 标记会话开始
            "user_free_text": "开始“穿书”之旅",  # 代表用户的初始意图
            "generated_narrative_segment": initial_narrative_text,  # LLM生成的初始叙事
            **initial_metadata  # 合并元数据
        }]

        utils.write_json_file(self.session_memory, self.session_memory_path)
        print(f"初始会话记忆已创建并保存于: {self.session_memory_path}")

    def initialize_narrative_session(self, initial_context_chapters: int, window_before: int, window_after: int,
                                     divergence_threshold: float, model_params: Dict[str, Any]) -> Optional[str]:
        """
        初始化叙事会话。

        Args:
            initial_context_chapters: (当前未使用，可考虑用于控制初始摘要的范围)
            window_before: (当前未使用，_get_current_chapter_segment_text 中有自己的窗口逻辑)
            window_after: (当前未使用，同上)
            divergence_threshold: (当前未使用，用于剧情偏离判断的阈值)
            model_params: 包含temperature, top_p等的模型参数字典。

        Returns:
            初始叙事文本，如果初始化失败则返回None。
        """
        self.last_error = None  # 清除之前的错误
        try:
            print("开始初始化叙事会话...")

            if not self.chapters_data or not self.analysis:
                self.last_error = "错误：小说章节数据或分析结果未加载，无法初始化叙事。"
                print(self.last_error)
                return None

            novel_title = self.analysis.get("title", "未知小说")

            # 默认从第一章（索引0）开始
            self.current_narrative_chapter_index = 0  # 确保从头开始
            initial_chapter_data = self.chapters_data[0]
            actual_initial_chapter_num = initial_chapter_data.get("chapter_number", 1)

            # 主角初始状态 (可以从分析数据中提取，或使用通用设定)
            protagonist_name = "你"  # 使用第二人称代词作为默认主角名
            if self.analysis.get("characters") and len(self.analysis["characters"]) > 0:
                # 假设第一个角色是主角，或者可以有更明确的标记
                main_char_name_candidate = self.analysis["characters"][0].get("name")
                if main_char_name_candidate:
                    protagonist_name = main_char_name_candidate

            initial_location = f"原著第 {actual_initial_chapter_num} 章的开端场景附近"
            # 尝试从分析的 "excerpts" 或 timeline 中获取更具体的初始地点/事件描述
            # 这里简化处理

            protagonist_initial_state_info = {
                "name": protagonist_name,
                "location": initial_location,
                "time": f"第 {actual_initial_chapter_num} 章，故事的开端"
                # 可以补充更多如 "初始心情: 迷茫而警惕" 等
            }

            initial_chapters_text_for_llm = self._get_current_chapter_segment_text()  # 获取第一章及其上下文
            relevant_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"故事从《{novel_title}》第 {actual_initial_chapter_num} 章的开端场景展开。主角 {protagonist_name} 刚进入这个世界。"
            )

            # 使用 prompts.py 中的 get_initial_narrative_prompt
            initial_prompt_for_llm = prompts.get_initial_narrative_prompt(
                novel_title=novel_title,
                initial_chapters_text=initial_chapters_text_for_llm,
                relevant_core_settings_summary=relevant_settings_summary_for_llm,
                protagonist_initial_state=json.dumps(protagonist_initial_state_info, ensure_ascii=False),  # 确保是JSON字符串
                current_chapter_number_for_context=actual_initial_chapter_num
            )

            print(f"发送给LLM的初始叙事提示 (部分):\n{initial_prompt_for_llm[:500]}...")

            initial_narrative_text = self._call_llm_for_narrative(initial_prompt_for_llm, model_params)

            if not initial_narrative_text:
                self.last_error = self.last_error or "LLM未能生成初始叙事文本。"
                print(f"生成初始叙事失败。{self.last_error}")
                return None

            print(f"LLM生成的初始叙事 (部分):\n{initial_narrative_text[:300]}...")

            # 初始化会话记忆和对话历史
            self._initialize_session_memory(protagonist_initial_state_info, initial_narrative_text)

            self.conversation_history = []  # 清空之前的对话历史
            self.conversation_history.append({  # 添加系统消息代表初始场景
                "role": "system",  # 或 "assistant" 代表旁白
                "content": initial_narrative_text,
                "timestamp": time.time()
            })

            return initial_narrative_text

        except Exception as e:
            self.last_error = f"初始化叙事会话时发生严重异常: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            return None

    def process_user_action(self, user_action: str, model_params: Dict[str, Any]) -> Optional[str]:
        """
        处理用户行动。

        Args:
            user_action: 用户行动文本。
            model_params: 模型参数。

        Returns:
            响应文本，如果处理失败则返回None。
        """
        self.last_error = None  # 清除旧错误
        try:
            if not user_action.strip():
                self.last_error = "用户行动不能为空。"
                print(self.last_error)
                return None

            # 记录用户行动到对话历史 (用于LLM上下文)
            self.conversation_history.append({
                "role": "user",
                "content": user_action,
                "timestamp": time.time()
            })

            # 准备LLM的上下文信息
            current_chapter_segment_for_llm = self._get_current_chapter_segment_text()

            # 构建剧情记忆档案摘要 (从 session_memory 中提取)
            plot_memory_summary_for_llm = self._get_plot_memory_summary()

            # 获取当前情境的核心设定 (可能比初始的更具体)
            core_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"主角({self.session_memory[-1].get('character_state_changes', {}).get('主角', {}).get('name', '未知') if self.session_memory else '未知'})的最新行动是: '{user_action[:50]}...'"
            )

            actual_current_chapter_num_display = self._get_current_chapter_number()

            # TODO: 实现 planned_reconvergence_info 的逻辑 (如果需要剧情纠偏)
            planned_reconvergence_info_for_llm = None

            # 使用 prompts.py 中的 get_narrative_continuation_user_prompt_content
            # 注意：这个函数返回的是 user prompt 的 *内容*，需要包装在 messages 列表中
            user_prompt_content = prompts.get_narrative_continuation_user_prompt_content(
                current_chapter_segment_text=current_chapter_segment_for_llm,
                plot_memory_archive_summary=plot_memory_summary_for_llm,
                core_settings_summary_for_current_context=core_settings_summary_for_llm,
                user_action=user_action,  # 用户输入的原始行动
                current_chapter_number_for_context=actual_current_chapter_num_display,
                planned_reconvergence_info=planned_reconvergence_info_for_llm
            )

            # 构建完整的 messages 列表给LLM
            # NARRATIVE_ENGINE_SYSTEM_PROMPT 应该作为 system message
            llm_messages = [
                {"role": "system", "content": prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT},
                # 可以考虑加入之前的几轮对话历史作为 assistant/user message
                # 例如，从 self.conversation_history 中取最后N条
                # 但 get_narrative_continuation_user_prompt_content 已经包含了 plot_memory_archive_summary
                {"role": "user", "content": user_prompt_content}
            ]

            print(f"发送给LLM的叙事继续用户提示内容 (部分):\n{user_prompt_content[:500]}...")

            # 调用LLM生成响应 (这里不直接用 _call_llm_for_narrative, 因为 messages 结构不同)
            if not self.llm_client:
                self.last_error = "LLM客户端未初始化。"
                print(self.last_error)
                return None

            # model_params 包含 temperature, top_p 等
            llm_response_dict = self.llm_client.generate_chat_completion(
                model=self.llm_client.default_model,  # 或特定的写作模型
                messages=llm_messages,
                options=model_params
                # stream=False, expect_json_in_content=False (叙事部分不需要强制JSON)
                # timeout 可以考虑加入 model_params 如果需要单独控制
            )

            if not llm_response_dict or not llm_response_dict.get("message") or not llm_response_dict.get(
                    "message").get("content"):
                self.last_error = self.last_error or f"LLM未能生成有效的叙事响应。响应: {llm_response_dict}"
                print(self.last_error)
                return None

            raw_llm_output = llm_response_dict["message"]["content"]

            # 从LLM输出中分离叙事文本和元数据JSON
            narrative_text, metadata_json = self._extract_narrative_and_metadata(raw_llm_output)

            if narrative_text is None:  # 如果无法分离，则认为整个输出都是叙事
                narrative_text = raw_llm_output
                print("警告: 未能从LLM输出中分离元数据JSON，将整个输出视为叙事文本。")

            print(f"LLM生成的叙事文本 (部分):\n{narrative_text[:300]}...")
            if metadata_json:
                print(
                    f"LLM生成的元数据JSON (部分):\n{json.dumps(metadata_json, ensure_ascii=False, indent=2)[:300]}...")

            # 更新会话记忆 (使用提取出的元数据，如果可用)
            self._update_session_memory(user_action, narrative_text, metadata_json)

            # 记录AI响应到对话历史 (仅叙事文本部分)
            self.conversation_history.append({
                "role": "assistant",  # 代表AI旁白
                "content": narrative_text,
                "timestamp": time.time()
            })

            # 检查是否需要推进章节 (基于元数据中的 current_chapter_progression_hint)
            self._check_and_advance_chapter(metadata_json)

            return narrative_text  # 返回纯叙事文本给前端

        except Exception as e:
            self.last_error = f"处理用户行动时发生严重错误: {str(e)}"
            print(self.last_error)
            traceback.print_exc()
            return None

    def _extract_narrative_and_metadata(self, raw_output: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        从LLM的原始输出中分离叙事文本和元数据JSON。
        元数据JSON应该被 [NARRATIVE_METADATA_JSON_START] 和 [NARRATIVE_METADATA_JSON_END] 包围。
        """
        narrative_text = raw_output
        metadata_json = None

        try:
            start_marker = "[NARRATIVE_METADATA_JSON_START]"
            end_marker = "[NARRATIVE_METADATA_JSON_END]"

            start_index = raw_output.rfind(start_marker)  # 从后往前找，以处理可能的多个标记

            if start_index != -1:
                end_index = raw_output.rfind(end_marker, start_index + len(start_marker))
                if end_index != -1:
                    # 提取JSON字符串
                    json_str = raw_output[start_index + len(start_marker):end_index].strip()

                    # 从叙事文本中移除标记和JSON部分
                    # 保留标记前的内容，以及标记后的内容（如果有的话，但不应该有）
                    narrative_text_before_marker = raw_output[:start_index].strip()
                    narrative_text_after_marker = raw_output[end_index + len(end_marker):].strip()

                    narrative_text = narrative_text_before_marker
                    if narrative_text_after_marker:  # 如果标记后还有文本，说明格式可能略有问题
                        print(f"警告: 在元数据标记之后发现额外文本: '{narrative_text_after_marker[:50]}...'")
                        # 可以选择性地追加回去，或者忽略
                        # narrative_text += "\n" + narrative_text_after_marker

                    try:
                        metadata_json = json.loads(json_str)
                    except json.JSONDecodeError as je:
                        print(f"解析从LLM提取的元数据JSON失败: {je}")
                        print(f"原始JSON字符串: {json_str}")
                        # 保留叙事文本，但元数据解析失败
                        metadata_json = None  # 确保返回None如果解析失败
                else:
                    print("警告: 找到了元数据JSON开始标记但未找到结束标记。")
            # else: 没有找到开始标记，整个输出被视为叙事文本

        except Exception as e:
            print(f"提取叙事和元数据时出错: {e}")
            # 发生错误时，保守地将整个输出视为叙事文本
            return raw_output, None

        return narrative_text if narrative_text.strip() else None, metadata_json

    def _get_plot_memory_summary(self) -> str:
        """从 session_memory 构建剧情记忆档案摘要，供LLM参考。"""
        if not self.session_memory:
            return "剧情刚刚开始，尚无重要记忆。"

        # 选择最近的几条记忆进行总结，避免过长的上下文
        # NARRATIVE_ENGINE_SYSTEM_PROMPT 要求LLM处理这个摘要
        # "【剧情记忆档案】: 这份档案记录了用户（主角）到目前为止的所有选择、行动、以及这些行动所产生的直接后果和剧情发展。"

        memories_to_summarize = self.session_memory[-3:]  # 例如，取最近3轮的记忆

        summary_entries = []
        for i, mem_entry in enumerate(memories_to_summarize):
            turn_id = mem_entry.get("turn_id", "未知回合")
            user_action = mem_entry.get("user_free_text", "无用户行动记录")
            action_summary = mem_entry.get("protagonist_action_summary", "行动摘要缺失")
            narrative_segment = mem_entry.get("generated_narrative_segment", "叙事片段缺失")
            consequences = mem_entry.get("immediate_consequences_and_observations", [])
            time_context = mem_entry.get("event_time_readable_context", "时间未知")

            entry_str = f"回合 {turn_id} ({time_context}):\n"
            if user_action != "开始“穿书”之旅" and user_action != "开始穿越体验":  # 避免冗余的初始行动
                entry_str += f"  主角行动: {user_action[:100]}...\n"  # 用户原始输入
            # entry_str += f"  行动概要: {action_summary}\n" # LLM自己生成的概要，可能与用户输入重复
            entry_str += f"  剧情发展/AI叙述: {narrative_segment[:150]}...\n"
            if consequences:
                entry_str += f"  主要后果/观察: {'; '.join(consequences)[:150]}...\n"

            summary_entries.append(entry_str)

        if not summary_entries:  # 如果筛选后为空（不太可能，除非session_memory为空）
            return "最近无重要剧情发展。"

        return "最近的剧情记忆回顾：\n" + "\n---\n".join(summary_entries)

    def _update_session_memory(self, user_action: str, generated_narrative: str,
                               llm_metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        更新会话记忆。
        Args:
            user_action: 用户的原始自由文本输入。
            generated_narrative: LLM生成的纯叙事文本。
            llm_metadata: 从LLM响应中提取的结构化元数据字典 (如果可用)。
        """
        turn_id = len(self.session_memory)  # 下一个回合的ID

        # 如果LLM没有提供元数据，我们需要自己构建一个基本的元数据结构
        if not llm_metadata or not isinstance(llm_metadata, dict):
            print("警告: LLM未提供有效的元数据，将生成基础元数据。")
            actual_current_chapter_num_display = self._get_current_chapter_number()
            # 从上一条记忆获取时间上下文作为参考，或使用当前章节信息
            prev_time_context = f"第 {actual_current_chapter_num_display} 章内某时"
            if self.session_memory:
                prev_time_context = self.session_memory[-1].get("event_time_readable_context", prev_time_context)

            llm_metadata = {
                "protagonist_action_summary": user_action[:80] + "..." if len(user_action) > 80 else user_action,
                # 简洁的用户行动摘要
                "event_time_readable_context": f"{prev_time_context}之后不久",  # 估算的时间
                "immediate_consequences_and_observations": [generated_narrative[:100] + "..."],  # 从叙事中提取摘要
                "character_state_changes": {},  # 基础版本无法准确推断
                "item_changes": {},
                "world_state_changes": ["剧情因主角行动而推进。"],
                "divergence_from_original_plot": {
                    "level": "未知",  # 无法判断偏离程度
                    "original_timeline_event_ref": None,
                    "description_of_divergence": "由于缺少LLM元数据，偏离情况未知。"
                },
                "current_chapter_progression_hint": f"在第 {actual_current_chapter_num_display} 章中继续探索。"
            }

        memory_entry = {
            "turn_id": turn_id,
            "user_input_signal": "USER_ACTION",  # 或其他类型，如 "SYSTEM_EVENT"
            "user_free_text": user_action,  # 保存用户的原始输入
            "generated_narrative_segment": generated_narrative,  # LLM生成的纯叙事
            **llm_metadata  # 合并从LLM获取（或基础生成的）元数据
        }

        self.session_memory.append(memory_entry)

        # 保存到文件 (可以选择在这里做，或者在应用层面批量保存)
        if not utils.write_json_file(self.session_memory, self.session_memory_path):
            print(f"警告: 更新并保存会话记忆到 {self.session_memory_path} 失败。")

    def _check_and_advance_chapter(self, llm_metadata: Optional[Dict[str, Any]]):
        """根据LLM元数据中的章节进展提示来尝试推进章节索引。"""
        if not llm_metadata:
            return

        progression_hint = llm_metadata.get("current_chapter_progression_hint", "").lower()

        # 简单的关键词检测来判断是否进入下一章
        # 例如："已进入下一章开端", "完成本章", "下一章内容开始"
        # 或者LLM直接提示章节号变化，例如 "已进入第 N 章"

        advance_chapter = False
        if "下一章" in progression_hint or "next chapter" in progression_hint:
            advance_chapter = True

        # 更精确的检查，如果LLM能明确指出新的章节号
        num_match = re.search(r'第\s*(\d+)\s*章', progression_hint)
        if num_match:
            try:
                hinted_chapter_num = int(num_match.group(1))
                current_actual_chapter_num = self._get_current_chapter_number()
                if hinted_chapter_num > current_actual_chapter_num:
                    advance_chapter = True
                    # 如果LLM能准确提供新章节号，我们甚至可以尝试直接跳到对应索引
                    # 但这需要 chapters_data 中的 chapter_number 与 hinted_chapter_num 匹配
                    for idx, chap_data in enumerate(self.chapters_data):
                        if chap_data.get("chapter_number") == hinted_chapter_num:
                            if idx < len(self.chapters_data) - 1:  # 确保不是最后一章之后
                                self.current_narrative_chapter_index = idx
                                print(f"根据LLM元数据，章节已推进到第 {hinted_chapter_num} 章 (索引 {idx})。")
                                return  # 已更新索引，直接返回
                            else:  # 如果是最后一章或者LLM提示的章节不存在
                                print(f"LLM提示章节 {hinted_chapter_num}, 但已是最后一章或无法找到该章节。")
                                advance_chapter = False  # 不要错误地推进
                                break


            except ValueError:
                pass  # 无法从提示中解析出数字

        if advance_chapter:
            if self.current_narrative_chapter_index < len(self.chapters_data) - 1:
                self.current_narrative_chapter_index += 1
                new_actual_chap_num = self._get_current_chapter_number()
                print(
                    f"章节已推进。当前叙事焦点章节索引: {self.current_narrative_chapter_index} (实际章节号: {new_actual_chap_num})")
            else:
                print("已是最后一章，无法再推进章节。")

    def save_state_to_file(self) -> Optional[str]:
        """
        将引擎状态保存到文件。使用 save_manager.py 中的逻辑太耦合，引擎应能自行保存。
        实际保存路径等管理应由外部（如app.py）处理，这里只负责准备状态数据。
        此方法现在直接在引擎内部执行保存，以简化。

        Returns:
            保存文件的路径，如果保存失败则返回None。
        """
        try:
            # 使用小说自身的data目录下的saves子目录
            save_dir = os.path.join(self.novel_data_dir, 'saves')
            os.makedirs(save_dir, exist_ok=True)

            timestamp_str = time.strftime('%Y%m%d_%H%M%S')
            # 使用小说标题（如果可用）使文件名更具可读性
            novel_title_part = "untitled"
            if self.analysis and self.analysis.get("title"):
                novel_title_part = utils.sanitize_filename(self.analysis.get("title")[:20])  # 取前20字符并清理

            save_filename = f'storysave_{novel_title_part}_{timestamp_str}.json'
            save_path = os.path.join(save_dir, save_filename)

            current_state_data = self.get_state_for_saving()
            # get_state_for_saving 已经包含了 model_name
            # 如果还需要保存当时的LLM参数 (temperature等)，可以从 config_manager 加载并加入
            # current_api_config = config_manager.load_api_configs(DATA_DIR) # DATA_DIR可能引擎不知道
            # current_state_data["llm_params_at_save"] = config_manager.get_model_params(current_api_config)
            # ^^^ 上述行需要DATA_DIR，如果引擎不应知道全局DATA_DIR，则此参数应由app.py注入

            if utils.write_json_file(current_state_data, save_path):
                print(f"叙事引擎状态已保存到: {save_path}")
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