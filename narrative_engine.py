# narrative_engine.py
# 该文件实现了叙事引擎，负责处理用户与小说的交互。

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
import utils
import prompts # 确保 prompts 模块被导入
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

        if saved_state:
            self._load_state(saved_state)
        else:
            self.session_memory = []
            self.current_narrative_chapter_index = 0
            self.conversation_history = []

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
        print(f"叙事引擎状态已从存档加载。当前章节索引: {self.current_narrative_chapter_index}, 模型: {self.model_name}")

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
        return self.current_narrative_chapter_index + 1

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
            for char_data in characters_info[:3]: # 简单取前几个
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
                f"警告: current_narrative_chapter_index ({self.current_narrative_chapter_index}) 超出范围 [0, {len(self.chapters_data) - 1}]。将尝试使用最后/第一个可用章节。")
            self.current_narrative_chapter_index = max(0, min(self.current_narrative_chapter_index,
                                                              len(self.chapters_data) - 1))
        # 简化窗口逻辑，主要聚焦当前章节，可按需扩展
        window_before = 1 # 可配置
        window_after = 1  # 可配置
        start_idx = max(0, self.current_narrative_chapter_index - window_before)
        end_idx = min(len(self.chapters_data), self.current_narrative_chapter_index + window_after + 1)
        segment_chapters_data = self.chapters_data[start_idx:end_idx]
        if not segment_chapters_data:
            if self.chapters_data: # 至少有一个章节
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
            "turn_id": 0,
            "user_input_signal": "SESSION_START",
            "user_free_text": "开始“穿书”之旅",
            "generated_narrative_segment": initial_narrative_text,
            **initial_metadata
        }]
        utils.write_json_file(self.session_memory, self.session_memory_path)
        print(f"初始会话记忆已创建并保存于: {self.session_memory_path}")

    # 修改参数名称以匹配 app.py 中的调用
    def initialize_narrative_session(self, initial_context_chapters: int,
                                     window_before: int, window_after: int,
                                     divergence_threshold: float, model_params: Dict[str, Any]) -> Optional[str]:
        """
        初始化叙事会话。

        Args:
            initial_context_chapters: 用于确定初始上下文范围的章节数 (来自配置)。
            window_before: (当前未使用，_get_current_chapter_segment_text 中有自己的窗口逻辑)
            window_after: (当前未使用，同上)
            divergence_threshold: (当前未使用，用于剧情偏离判断的阈值)
            model_params: 包含temperature, top_p等的模型参数字典。

        Returns:
            初始叙事文本，如果初始化失败则返回None。
        """
        self.last_error = None
        try:
            print("开始初始化叙事会话...")
            if not self.chapters_data or not self.analysis:
                self.last_error = "错误：小说章节数据或分析结果未加载，无法初始化叙事。"
                print(self.last_error)
                return None

            novel_title = self.analysis.get("title", "未知小说")
            self.current_narrative_chapter_index = 0
            initial_chapter_data = self.chapters_data[0]
            actual_initial_chapter_num = initial_chapter_data.get("chapter_number", 1)

            protagonist_name = "你"
            if self.analysis.get("characters") and len(self.analysis["characters"]) > 0:
                main_char_name_candidate = self.analysis["characters"][0].get("name")
                if main_char_name_candidate:
                    protagonist_name = main_char_name_candidate

            initial_location = f"原著第 {actual_initial_chapter_num} 章的开端场景附近"
            protagonist_initial_state_info = {
                "name": protagonist_name,
                "location": initial_location,
                "time": f"第 {actual_initial_chapter_num} 章，故事的开端"
            }

            initial_chapters_text_for_llm = self._get_current_chapter_segment_text()
            relevant_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"故事从《{novel_title}》第 {actual_initial_chapter_num} 章的开端场景展开。主角 {protagonist_name} 刚进入这个世界。"
            )

            # 使用传入的 initial_context_chapters (原 initial_context_chapters_config_val)
            initial_prompt_for_llm = prompts.get_initial_narrative_prompt(
                novel_title=novel_title,
                initial_chapters_text=initial_chapters_text_for_llm,
                relevant_core_settings_summary=relevant_settings_summary_for_llm,
                protagonist_initial_state=json.dumps(protagonist_initial_state_info, ensure_ascii=False),
                current_chapter_number_for_context=actual_initial_chapter_num,
                initial_context_chapters=initial_context_chapters # <--- 使用正确的参数名
            )

            print(f"发送给LLM的初始叙事提示 (部分):\n{initial_prompt_for_llm[:500]}...")

            initial_narrative_text = self._call_llm_for_narrative(initial_prompt_for_llm, model_params)

            if not initial_narrative_text:
                self.last_error = self.last_error or "LLM未能生成初始叙事文本。"
                print(f"生成初始叙事失败。{self.last_error}")
                return None

            print(f"LLM生成的初始叙事 (部分):\n{initial_narrative_text[:300]}...")
            self._initialize_session_memory(protagonist_initial_state_info, initial_narrative_text)
            self.conversation_history = []
            self.conversation_history.append({
                "role": "system",
                "content": initial_narrative_text,
                "timestamp": time.time()
            })
            return initial_narrative_text
        except Exception as e:
            self.last_error = f"初始化叙事会话时发生严重异常: {str(e)}"
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
                model=self.llm_client.default_model,
                messages=messages,
                options=model_params
            )
            if response_dict and response_dict.get("message") and response_dict.get("message").get("content"):
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
            self.conversation_history.append({
                "role": "user",
                "content": user_action,
                "timestamp": time.time()
            })
            current_chapter_segment_for_llm = self._get_current_chapter_segment_text()
            plot_memory_summary_for_llm = self._get_plot_memory_summary()
            core_settings_summary_for_llm = self._get_relevant_core_settings_summary(
                current_event_context=f"主角({self.session_memory[-1].get('character_state_changes', {}).get('主角', {}).get('name', '未知') if self.session_memory else '未知'})的最新行动是: '{user_action[:50]}...'"
            )
            actual_current_chapter_num_display = self._get_current_chapter_number()
            planned_reconvergence_info_for_llm = None # 可按需实现
            user_prompt_content = prompts.get_narrative_continuation_user_prompt_content(
                current_chapter_segment_text=current_chapter_segment_for_llm,
                plot_memory_archive_summary=plot_memory_summary_for_llm,
                core_settings_summary_for_current_context=core_settings_summary_for_llm,
                user_action=user_action,
                current_chapter_number_for_context=actual_current_chapter_num_display,
                planned_reconvergence_info=planned_reconvergence_info_for_llm
            )
            llm_messages = [
                {"role": "system", "content": prompts.NARRATIVE_ENGINE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt_content}
            ]
            print(f"发送给LLM的叙事继续用户提示内容 (部分):\n{user_prompt_content[:500]}...")
            if not self.llm_client:
                self.last_error = "LLM客户端未初始化。"
                print(self.last_error)
                return None
            llm_response_dict = self.llm_client.generate_chat_completion(
                model=self.llm_client.default_model,
                messages=llm_messages,
                options=model_params
            )
            if not llm_response_dict or not llm_response_dict.get("message") or not llm_response_dict.get(
                    "message").get("content"):
                self.last_error = self.last_error or f"LLM未能生成有效的叙事响应。响应: {llm_response_dict}"
                print(self.last_error)
                return None
            raw_llm_output = llm_response_dict["message"]["content"]
            narrative_text, metadata_json = self._extract_narrative_and_metadata(raw_llm_output)
            if narrative_text is None: # 如果无法分离，则认为整个输出都是叙事
                narrative_text = raw_llm_output
                print("警告: 未能从LLM输出中分离元数据JSON，将整个输出视为叙事文本。")
            print(f"LLM生成的叙事文本 (部分):\n{narrative_text[:300]}...")
            if metadata_json:
                print(
                    f"LLM生成的元数据JSON (部分):\n{json.dumps(metadata_json, ensure_ascii=False, indent=2)[:300]}...")
            self._update_session_memory(user_action, narrative_text, metadata_json)
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
            return None

    def _extract_narrative_and_metadata(self, raw_output: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """从LLM的原始输出中分离叙事文本和元数据JSON。"""
        narrative_text = raw_output
        metadata_json = None
        try:
            start_marker = "[NARRATIVE_METADATA_JSON_START]"
            end_marker = "[NARRATIVE_METADATA_JSON_END]"
            start_index = raw_output.rfind(start_marker)
            if start_index != -1:
                end_index = raw_output.rfind(end_marker, start_index + len(start_marker))
                if end_index != -1:
                    json_str = raw_output[start_index + len(start_marker):end_index].strip()
                    narrative_text_before_marker = raw_output[:start_index].strip()
                    narrative_text_after_marker = raw_output[end_index + len(end_marker):].strip()
                    narrative_text = narrative_text_before_marker
                    if narrative_text_after_marker:
                        print(f"警告: 在元数据标记之后发现额外文本: '{narrative_text_after_marker[:50]}...'")
                    try:
                        metadata_json = json.loads(json_str)
                    except json.JSONDecodeError as je:
                        print(f"解析从LLM提取的元数据JSON失败: {je}")
                        print(f"原始JSON字符串: {json_str}")
                        metadata_json = None
                else:
                    print("警告: 找到了元数据JSON开始标记但未找到结束标记。")
        except Exception as e:
            print(f"提取叙事和元数据时出错: {e}")
            return raw_output, None # 保守返回原始输出
        return narrative_text if narrative_text.strip() else None, metadata_json

    def _get_plot_memory_summary(self) -> str:
        """从 session_memory 构建剧情记忆档案摘要，供LLM参考。"""
        if not self.session_memory:
            return "剧情刚刚开始，尚无重要记忆。"
        memories_to_summarize = self.session_memory[-3:] # 取最近3轮
        summary_entries = []
        for i, mem_entry in enumerate(memories_to_summarize):
            turn_id = mem_entry.get("turn_id", "未知回合")
            user_action = mem_entry.get("user_free_text", "无用户行动记录")
            # action_summary = mem_entry.get("protagonist_action_summary", "行动摘要缺失") # LLM自己生成的，可能重复
            narrative_segment = mem_entry.get("generated_narrative_segment", "叙事片段缺失")
            consequences = mem_entry.get("immediate_consequences_and_observations", [])
            time_context = mem_entry.get("event_time_readable_context", "时间未知")
            entry_str = f"回合 {turn_id} ({time_context}):\n"
            if user_action != "开始“穿书”之旅" and user_action != "开始穿越体验": # 避免冗余
                entry_str += f"  主角行动: {user_action[:100]}...\n"
            entry_str += f"  剧情发展/AI叙述: {narrative_segment[:150]}...\n"
            if consequences:
                entry_str += f"  主要后果/观察: {'; '.join(consequences)[:150]}...\n"
            summary_entries.append(entry_str)
        if not summary_entries:
            return "最近无重要剧情发展。"
        return "最近的剧情记忆回顾：\n" + "\n---\n".join(summary_entries)

    def _update_session_memory(self, user_action: str, generated_narrative: str,
                               llm_metadata: Optional[Dict[str, Any]] = None) -> None:
        """更新会话记忆。"""
        turn_id = len(self.session_memory)
        if not llm_metadata or not isinstance(llm_metadata, dict):
            print("警告: LLM未提供有效的元数据，将生成基础元数据。")
            actual_current_chapter_num_display = self._get_current_chapter_number()
            prev_time_context = f"第 {actual_current_chapter_num_display} 章内某时"
            if self.session_memory:
                prev_time_context = self.session_memory[-1].get("event_time_readable_context", prev_time_context)
            llm_metadata = {
                "protagonist_action_summary": user_action[:80] + "..." if len(user_action) > 80 else user_action,
                "event_time_readable_context": f"{prev_time_context}之后不久",
                "immediate_consequences_and_observations": [generated_narrative[:100] + "..."],
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
            "user_input_signal": "USER_ACTION",
            "user_free_text": user_action,
            "generated_narrative_segment": generated_narrative,
            **llm_metadata
        }
        self.session_memory.append(memory_entry)
        if not utils.write_json_file(self.session_memory, self.session_memory_path):
            print(f"警告: 更新并保存会话记忆到 {self.session_memory_path} 失败。")

    def _check_and_advance_chapter(self, llm_metadata: Optional[Dict[str, Any]]):
        """根据LLM元数据中的章节进展提示来尝试推进章节索引。"""
        if not llm_metadata: return
        progression_hint = llm_metadata.get("current_chapter_progression_hint", "").lower()
        advance_chapter = False
        if "下一章" in progression_hint or "next chapter" in progression_hint:
            advance_chapter = True
        num_match = re.search(r'第\s*(\d+)\s*章', progression_hint)
        if num_match:
            try:
                hinted_chapter_num = int(num_match.group(1))
                current_actual_chapter_num = self._get_current_chapter_number()
                if hinted_chapter_num > current_actual_chapter_num:
                    advance_chapter = True
                    for idx, chap_data in enumerate(self.chapters_data):
                        if chap_data.get("chapter_number") == hinted_chapter_num:
                            if idx < len(self.chapters_data) - 1: # 确保不是最后一章之后
                                self.current_narrative_chapter_index = idx
                                print(f"根据LLM元数据，章节已推进到第 {hinted_chapter_num} 章 (索引 {idx})。")
                                return # 已更新索引，直接返回
                            else: # 如果是最后一章或者LLM提示的章节不存在
                                print(f"LLM提示章节 {hinted_chapter_num}, 但已是最后一章或无法找到该章节。")
                                advance_chapter = False # 不要错误地推进
                                break
            except ValueError: pass # 无法从提示中解析出数字
        if advance_chapter:
            if self.current_narrative_chapter_index < len(self.chapters_data) - 1:
                self.current_narrative_chapter_index += 1
                new_actual_chap_num = self._get_current_chapter_number()
                print(
                    f"章节已推进。当前叙事焦点章节索引: {self.current_narrative_chapter_index} (实际章节号: {new_actual_chap_num})")
            else:
                print("已是最后一章，无法再推进章节。")

    def save_state_to_file(self) -> Optional[str]:
        """将引擎状态保存到文件。"""
        try:
            save_dir = os.path.join(self.novel_data_dir, 'saves')
            os.makedirs(save_dir, exist_ok=True)
            timestamp_str = time.strftime('%Y%m%d_%H%M%S')
            novel_title_part = "untitled"
            if self.analysis and self.analysis.get("title"):
                novel_title_part = utils.sanitize_filename(self.analysis.get("title")[:20])
            save_filename = f'storysave_{novel_title_part}_{timestamp_str}.json'
            save_path = os.path.join(save_dir, save_filename)
            current_state_data = self.get_state_for_saving()
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
