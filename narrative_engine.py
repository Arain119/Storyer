# narrative_engine.py
# 该文件实现了叙事引擎，负责处理用户与小说的交互。

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple
import utils
import prompts

class NarrativeEngine:
    """叙事引擎类，负责处理用户与小说的交互。"""

    def __init__(self, llm_client, novel_data_dir: str, chapters_dir: str, analysis_path: str, model_name: str, saved_state: Optional[Dict[str, Any]] = None):
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

        # 加载分析结果
        self.analysis = utils.read_json_file(analysis_path) or {}
        self.chapters_data = self._load_chapters_data()
        
        # 初始化状态
        if saved_state:
            self._load_state(saved_state)
        else:
            self.session_memory = []
            self.current_narrative_chapter_index = 0
            self.conversation_history = []

    def _load_chapters_data(self) -> List[Dict[str, Any]]:
        """加载章节数据"""
        chapters_data_path = os.path.join(self.novel_data_dir, 'chapters_data.json')
        if os.path.exists(chapters_data_path):
            return utils.read_json_file(chapters_data_path) or []
        
        # 如果没有找到chapters_data.json，尝试从chapters目录构建
        chapters_data = []
        if os.path.exists(self.chapters_dir):
            chapter_files = sorted([f for f in os.listdir(self.chapters_dir) if f.startswith('chapter_') and f.endswith('.txt')])
            for i, file_name in enumerate(chapter_files):
                chapter_path = os.path.join(self.chapters_dir, file_name)
                chapter_content = utils.read_text_file(chapter_path)
                if chapter_content:
                    # 提取章节号和标题
                    chapter_number = i + 1
                    title_match = re.search(r'第[一二三四五六七八九十百千万\d]+章\s*(.+)?|Chapter\s+\d+\s*:?\s*(.+)?', chapter_content)
                    title = title_match.group(1) if title_match and title_match.group(1) else f"第{chapter_number}章"
                    
                    chapters_data.append({
                        "chapter_number": chapter_number,
                        "title": title,
                        "content": chapter_content,
                        "path": chapter_path
                    })
        
        # 保存构建的章节数据
        if chapters_data:
            utils.write_json_file(chapters_data, chapters_data_path)
        
        return chapters_data

    def _load_state(self, state: Dict[str, Any]) -> None:
        """从保存的状态加载引擎状态"""
        self.session_memory = state.get("session_memory", [])
        self.current_narrative_chapter_index = state.get("current_narrative_chapter_index", 0)
        self.conversation_history = state.get("conversation_history", [])

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
        """获取当前叙事索引对应的实际章节号"""
        if self.chapters_data and 0 <= self.current_narrative_chapter_index < len(self.chapters_data):
            return self.chapters_data[self.current_narrative_chapter_index].get("chapter_number", self.current_narrative_chapter_index + 1)
        return self.current_narrative_chapter_index + 1

    def _get_relevant_core_settings_summary(self, current_event_context: Optional[str] = None) -> str:
        """获取与当前情境相关的核心设定摘要"""
        if not self.analysis or not self.chapters_data:
            return "错误：小说分析或章节数据未加载。"
        
        summary_parts = []
        current_actual_chapter_num = self._get_current_chapter_number()
        is_initial_phase_restricted = current_actual_chapter_num <= 1
        
        if is_initial_phase_restricted:
            summary_parts.append(
                f"- 当前故事阶段: 第 {current_actual_chapter_num} 章开端。你对这个世界的了解非常有限，仅限于你当前所经历和观察到的。请严格根据当前章节的直接信息和你的直接观察行动。不要假设任何当前章节未提及的背景信息或未来事件。")
            # 在初始阶段，可以提供非常概括的世界观
            if "world_building" in self.analysis and len(self.analysis["world_building"]) > 0:
                ws_overview = self.analysis["world_building"][0].get("description", "")
                if ws_overview:
                    summary_parts.append(f"- 世界观初步印象: {ws_overview[:150]}...")
        else:
            summary_parts.append(f"- 当前故事进展至: 第 {current_actual_chapter_num} 章附近。")
            if "world_building" in self.analysis and len(self.analysis["world_building"]) > 0:
                ws_overview = self.analysis["world_building"][0].get("description", "")
                summary_parts.append(f"- 世界观概览: {ws_overview}")
            
            # 主剧情线摘要
            if "plot_summary" in self.analysis:
                summary_parts.append(f"- 主剧情线概要（截至目前）: {self.analysis.get('plot_summary', '未定义')}")
            
            # 主题
            if "themes" in self.analysis and self.analysis["themes"]:
                themes_str = ", ".join(self.analysis["themes"][:5])  # 限制主题数量
                summary_parts.append(f"- 主要主题: {themes_str}")
            
            # 角色信息
            if "characters" in self.analysis and self.analysis["characters"]:
                characters_summary = []
                for char in self.analysis["characters"][:3]:  # 限制角色数量
                    characters_summary.append(f"{char['name']}: {char['description'][:100]}...")
                summary_parts.append(f"- 主要角色: {'; '.join(characters_summary)}")
        
        if current_event_context:
            summary_parts.append(f"- 当前情境具体提示: {current_event_context}")
        
        return "\n".join(summary_parts)

    def _get_current_chapter_segment_text(self) -> str:
        """获取当前叙事点附近的原文章节片段文本"""
        if not self.chapters_data:
            return "错误：章节数据未加载。"
        
        # 设置窗口大小
        window_before = 2  # 当前章节前的窗口大小
        window_after = 2   # 当前章节后的窗口大小
        
        start_idx = max(0, self.current_narrative_chapter_index - window_before)
        end_idx = min(len(self.chapters_data), self.current_narrative_chapter_index + window_after + 1)
        
        segment_chapters = []
        if start_idx < end_idx:
            segment_chapters = self.chapters_data[start_idx:end_idx]
        elif 0 <= self.current_narrative_chapter_index < len(self.chapters_data):
            segment_chapters = [self.chapters_data[self.current_narrative_chapter_index]]
        elif self.chapters_data:
            segment_chapters = [self.chapters_data[-1]]
        
        if not segment_chapters:
            return "错误：无法获取当前章节片段。"
        
        return "\n\n---\n\n".join(
            [f"【原文参考：第 {ch['chapter_number']} 章 - {ch.get('title', '无标题')}】\n{ch['content']}" for ch in segment_chapters]
        )

    def _initialize_session_memory(self, protagonist_initial_state: Dict[str, Any], initial_narrative_text: str):
        """初始化会话记忆"""
        current_actual_chapter_num = self._get_current_chapter_number()
        initial_event_time = protagonist_initial_state.get("time", f"第 {current_actual_chapter_num} 章开端")
        
        initial_metadata = {
            "protagonist_action_summary": "故事开始，主角进入小说世界。",
            "event_time_readable_context": initial_event_time,
            "immediate_consequences_and_observations": [
                f"主角身份: {protagonist_initial_state.get('name', '未知')}",
                f"初始地点: {protagonist_initial_state.get('location', '未知')}",
                "故事正式拉开序幕。"
            ],
            "character_state_changes": {
                protagonist_initial_state.get("name", "主角"): {
                    "mood": "初始",
                    "location": protagonist_initial_state.get("location", "未知")
                }
            },
            "item_changes": {},
            "world_state_changes": ["互动叙事已初始化。"],
            "divergence_from_original_plot": {
                "level": "无",
                "original_timeline_event_ref": None,
                "description_of_divergence": "尚未开始与原著剧情的显著交互。"
            },
            "current_chapter_progression_hint": f"已进入第 {current_actual_chapter_num} 章开端附近"
        }
        
        self.session_memory = [{
            "turn_id": 0,
            "user_input_signal": "SESSION_START",
            "user_free_text": "开始穿越体验",
            "generated_narrative_segment": initial_narrative_text,
            **initial_metadata
        }]
        
        utils.write_json_file(self.session_memory, self.session_memory_path)
        print(f"初始会话记忆已创建于 {self.session_memory_path}")

    def initialize_narrative_session(self, initial_context_chapters: int, window_before: int, window_after: int, divergence_threshold: float, model_params: Dict[str, Any]) -> Optional[str]:
        """
        初始化叙事会话。

        Args:
            initial_context_chapters: 初始上下文章节数。
            window_before: 当前章节前的窗口大小。
            window_after: 当前章节后的窗口大小。
            divergence_threshold: 分歧阈值。
            model_params: 模型参数。

        Returns:
            初始叙事文本，如果初始化失败则返回None。
        """
        try:
            print("开始初始化叙事会话...")
            
            # 确保核心数据已加载
            if not self.chapters_data or not self.analysis:
                print("错误：核心数据未加载")
                return None
            
            # 获取小说标题
            novel_title = self.analysis.get("title", "未知小说")
            
            # 确定初始章节和相关信息
            protagonist_name = "主角"
            first_event_location = "故事开始的地方"
            
            # 默认从第一章开始
            initial_chapter_data = self.chapters_data[0] if self.chapters_data else {"chapter_number": 1, "title": "未知开端"}
            initial_chapter_number = initial_chapter_data.get("chapter_number", 1)
            first_event_time = f"第 {initial_chapter_number} 章开端"
            
            # 尝试从分析结果中获取更精确的初始信息
            if "characters" in self.analysis and len(self.analysis["characters"]) > 0:
                protagonist_name = self.analysis["characters"][0]["name"]
            
            if "excerpts" in self.analysis and len(self.analysis["excerpts"]) > 0:
                first_event_location = self.analysis["excerpts"][0]["text"][:100]
            
            # 设置当前叙事章节索引
            self.current_narrative_chapter_index = 0
            
            # 获取用于LLM提示的初始章节文本
            initial_chapters_text = self._get_current_chapter_segment_text()
            
            # 构建主角初始状态
            protagonist_initial_state = {
                "name": protagonist_name,
                "location": first_event_location,
                "time": first_event_time
            }
            
            # 获取相关设定摘要
            relevant_settings_summary = self._get_relevant_core_settings_summary(
                current_event_context=f"故事从 {first_event_time} 开始，初始事件大致为：{first_event_location}"
            )
            
            # 构建初始叙事提示
            initial_prompt = f"""你是一个交互式小说的叙事引擎。请基于以下信息生成一段引人入胜的初始叙事，描述主角刚刚穿越进入小说世界的场景。

小说标题：{novel_title}

原文参考：
{initial_chapters_text}

世界设定摘要：
{relevant_settings_summary}

主角初始状态：
{protagonist_initial_state}

请生成一段生动、详细的叙事，描述主角刚刚穿越到小说世界的体验。包括环境描述、感官体验和初始情境。不要包含任何选项或提示，这是一个开放式的叙事。叙述应该是第二人称（"你"），让读者感觉自己就是主角。叙述应该在500-800字之间。"""
            
            # 调用LLM生成初始叙事
            initial_narrative = self._call_llm_for_narrative(initial_prompt, model_params)
            
            if not initial_narrative:
                print("生成初始叙事失败")
                return None
            
            # 初始化会话记忆
            self._initialize_session_memory(protagonist_initial_state, initial_narrative)
            
            # 记录到对话历史
            self.conversation_history.append({
                "role": "system",
                "content": initial_narrative,
                "timestamp": time.time()
            })
            
            return initial_narrative
            
        except Exception as e:
            print(f"初始化叙事会话时出错: {str(e)}")
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
        try:
            # 记录用户行动到对话历史
            self.conversation_history.append({
                "role": "user",
                "content": user_action,
                "timestamp": time.time()
            })
            
            # 获取当前章节文本和设定摘要
            current_chapter_text = self._get_current_chapter_segment_text()
            relevant_settings = self._get_relevant_core_settings_summary()
            
            # 构建对话历史上下文
            conversation_context = self._build_conversation_context()
            
            # 构建提示
            prompt = f"""你是一个交互式小说的叙事引擎。请基于以下信息，对用户的行动生成一个合适的响应。

原文参考：
{current_chapter_text}

世界设定摘要：
{relevant_settings}

对话历史：
{conversation_context}

用户行动：
{user_action}

请生成一段生动、详细的叙事，描述用户行动的结果和后果。包括环境变化、角色反应和情节发展。不要包含任何选项或提示，这是一个开放式的叙事。叙述应该是第二人称（"你"），让读者感觉自己就是主角。叙述应该在500-800字之间。"""
            
            # 调用LLM生成响应
            response = self._call_llm_for_narrative(prompt, model_params)
            
            if not response:
                print("生成响应失败")
                return None
            
            # 更新会话记忆
            self._update_session_memory(user_action, response)
            
            # 记录到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": time.time()
            })
            
            return response
            
        except Exception as e:
            print(f"处理用户行动时出错: {str(e)}")
            return None

    def _call_llm_for_narrative(self, prompt: str, model_params: Dict[str, Any]) -> Optional[str]:
        """调用LLM生成叙事"""
        if not self.llm_client:
            print("LLM客户端未初始化")
            return None
        
        try:
            # 构建消息
            messages = [
                {"role": "system", "content": "你是一个交互式小说的叙事引擎，擅长生成生动、引人入胜的叙事。"},
                {"role": "user", "content": prompt}
            ]
            
            # 设置模型参数
            params = {
                "temperature": model_params.get("temperature", 0.7),
                "top_p": model_params.get("top_p", 0.9),
                "max_tokens": model_params.get("max_tokens", 1024),
                "frequency_penalty": model_params.get("frequency_penalty", 0.0),
                "presence_penalty": model_params.get("presence_penalty", 0.0)
            }
            
            # 调用LLM
            response = self.llm_client.chat_completion(messages, **params)
            
            if not response:
                print("LLM返回空响应")
                return None
            
            return response
                
        except Exception as e:
            print(f"调用LLM生成叙事时出错: {str(e)}")
            return None

    def _build_conversation_context(self) -> str:
        """构建对话历史上下文"""
        # 限制对话历史长度，只取最近的几轮
        recent_history = self.conversation_history[-6:] if len(self.conversation_history) > 6 else self.conversation_history
        
        context_parts = []
        for msg in recent_history:
            role = "系统" if msg["role"] == "system" else ("用户" if msg["role"] == "user" else "AI")
            context_parts.append(f"{role}: {msg['content'][:200]}...")
        
        return "\n\n".join(context_parts)

    def _update_session_memory(self, user_action: str, response: str) -> None:
        """更新会话记忆"""
        # 获取当前回合ID
        turn_id = len(self.session_memory)
        
        # 获取当前章节号
        current_chapter_num = self._get_current_chapter_number()
        
        # 构建元数据
        metadata = {
            "protagonist_action_summary": user_action[:100],
            "event_time_readable_context": f"第 {current_chapter_num} 章",
            "immediate_consequences_and_observations": [response[:200]],
            "character_state_changes": {},
            "item_changes": {},
            "world_state_changes": [],
            "divergence_from_original_plot": {
                "level": "低",
                "original_timeline_event_ref": None,
                "description_of_divergence": "用户行动可能导致与原著剧情的轻微偏离。"
            },
            "current_chapter_progression_hint": f"继续在第 {current_chapter_num} 章"
        }
        
        # 添加新的会话记忆
        memory_entry = {
            "turn_id": turn_id,
            "user_input_signal": "USER_ACTION",
            "user_free_text": user_action,
            "generated_narrative_segment": response,
            **metadata
        }
        
        self.session_memory.append(memory_entry)
        
        # 保存会话记忆
        utils.write_json_file(self.session_memory, self.session_memory_path)

    def save_state_to_file(self) -> Optional[str]:
        """
        将引擎状态保存到文件。

        Returns:
            保存文件的路径，如果保存失败则返回None。
        """
        try:
            # 创建保存目录
            save_dir = os.path.join(self.novel_data_dir, 'saves')
            os.makedirs(save_dir, exist_ok=True)

            # 生成保存文件名
            timestamp = time.strftime('%Y%m%d%H%M%S')
            save_path = os.path.join(save_dir, f'save_{timestamp}.json')

            # 获取当前状态
            state = self.get_state_for_saving()
            
            # 添加应用配置
            state["app_config"] = {
                "initial_context_chapters": 3,
                "window_before": 2,
                "window_after": 2,
                "divergence_threshold": 0.7,
                "model_params": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 1024,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0
                }
            }

            # 保存状态
            utils.write_json_file(state, save_path)

            return save_path

        except Exception as e:
            print(f"保存引擎状态时出错: {str(e)}")
            return None
