# main.py
# 这是应用程序的主入口点，使用Streamlit构建用户界面。
# 它整合了所有模块，提供完整的用户体验，并实现了保存/加载功能。

import streamlit as st
import os
import sys  # 通常用于系统路径等，此处可能未直接使用，但保持引用
import json
import time
from datetime import datetime

import config  # 导入配置
import utils  # 导入工具函数
from typing import Optional, Dict, Any, List, Tuple  # 增加了Tuple

from llm_client_interface import LLMClientInterface  # 导入LLM客户端接口
from ollama_client import OllamaClient  # 导入Ollama客户端实现
from generic_online_api_client import GenericOnlineAPIClient  # 导入通用在线API客户端实现
from narrative_engine import NarrativeEngine  # 导入叙事引擎
from novel_processor import NovelProcessor  # 导入小说处理器

# --- 常量 ---
# 从config.py中获取故事保存状态文件名
STORY_SAVE_STATE_FILENAME: str = config.STORY_SAVE_STATE_FILENAME
# API配置保存文件名
API_CONFIG_FILENAME: str = "api_config.json"
# 历史对话保存目录
HISTORY_DIR: str = "history"

# --- Streamlit 页面配置 ---
st.set_page_config(
    page_title="交互式\"穿书\"小说体验",
    layout="wide",
    initial_sidebar_state="expanded"
)  # 设置页面标题和布局

# 自定义CSS，采用Claude/Manus/ChatGPT混合风格，以米色为主色调
st.markdown("""
<style>
    /* 全局字体和颜色 */
    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #141414;
        background-color: #f5f5f0; /* 米色背景 */
    }

    /* 滚动条样式 */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: #f1f1e6; /* 米色轨道 */
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb {
        background: #d1cfc0; /* 深米色滑块 */
        border-radius: 10px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #b8b5a1; /* 悬停时更深的米色 */
    }

    /* 标题样式 */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 600;
        color: #141414;
    }

    /* 主标题 */
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 1rem;
        color: #141414;
        padding: 1rem 0;
        border-bottom: 1px solid #e6e6d8; /* 米色边框 */
    }

    /* 副标题 */
    .sub-title {
        font-size: 1.5rem;
        font-weight: 600;
        margin-bottom: 0.8rem;
        color: #141414;
    }

    /* 侧边栏样式 */
    .css-1d391kg, .css-12oz5g7, .css-1cypcdb, .css-1oe6wy4 {
        background-color: #f0f0e6 !important; /* 米色侧边栏 */
    }

    /* 侧边栏标题 */
    .sidebar-title {
        font-size: 1.2rem;
        font-weight: 600;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        color: #141414;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e6e6d8; /* 米色边框 */
    }

    /* 按钮样式 */
    .stButton>button {
        background-color: #f0f0e6; /* 米色按钮 */
        color: #141414;
        border-radius: 8px;
        border: 1px solid #d9d9c6; /* 深米色边框 */
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }

    .stButton>button:hover {
        background-color: #e6e6d8; /* 悬停时更深的米色 */
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    /* 主要操作按钮 */
    .primary-button>button {
        background-color: #5046e4;
        color: white;
        border: none;
    }

    .primary-button>button:hover {
        background-color: #3f37b3;
    }

    /* 输入框样式 */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 8px;
        border: 1px solid #e6e6d8; /* 米色边框 */
        background-color: #fafaf5; /* 浅米色背景 */
        padding: 0.75rem;
        transition: all 0.2s;
    }

    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #d1cfc0; /* 聚焦时深米色边框 */
        box-shadow: 0 0 0 2px rgba(209, 207, 192, 0.3); /* 聚焦时米色阴影 */
    }

    /* 选择框样式 */
    .stSelectbox>div>div>div {
        border-radius: 8px;
        border: 1px solid #e6e6d8; /* 米色边框 */
        background-color: #fafaf5; /* 浅米色背景 */
    }

    /* 消息容器 */
    .message-container {
        padding: 1.25rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        transition: all 0.3s ease;
        animation: fadeIn 0.5s ease-out;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .user-message {
        background-color: #f0f0e6; /* 米色用户消息 */
        border-left: 4px solid #d1cfc0; /* 深米色边框 */
    }

    .ai-message {
        background-color: #fafaf5; /* 浅米色AI消息 */
        border-left: 4px solid #5046e4; /* 紫色边框，Claude风格 */
    }

    /* 分隔线 */
    hr {
        margin: 1.5rem 0;
        border: none;
        border-top: 1px solid #e6e6d8; /* 米色分隔线 */
    }

    /* 卡片样式 */
    .card {
        padding: 1.5rem;
        border-radius: 12px;
        background-color: #fafaf5; /* 浅米色背景 */
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        margin-bottom: 1rem;
        border: 1px solid #f0f0e6; /* 米色边框 */
        transition: all 0.2s;
    }

    .card:hover {
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.08);
    }

    /* 标签页样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background-color: #f5f5f0; /* 米色背景 */
    }

    .stTabs [data-baseweb="tab"] {
        height: 60px; 
        white-space: pre-wrap;
        background-color: #f0f0e6; /* 米色标签 */
        border-radius: 8px 8px 0 0;
        gap: 1px;
        padding: 8px 12px; 
        display: flex; /* 添加flex布局 */
        align-items: center; /* 使内容垂直居中 */
        justify-content: center; /* 使内容水平居中 */
        text-align: center; /* 确保换行文本也居中显示 */
    }

    .stTabs [aria-selected="true"] {
        background-color: #fafaf5; /* 浅米色选中标签 */
        border-bottom: 2px solid #5046e4; /* 紫色底边 */
    }

    /* 进度条样式 */
    .stProgress > div > div > div > div {
        background-color: #5046e4; /* 紫色进度条 */
    }

    /* 提示框样式 */
    .info-box {
        background-color: #f0f0e6; /* 米色背景 */
        border-left: 4px solid #5046e4; /* 紫色边框 */
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
    }

    .success-box {
        background-color: #f0f5f0; /* 浅绿色背景 */
        border-left: 4px solid #10a37f; /* 绿色边框 */
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
    }

    .warning-box {
        background-color: #fffaf0; /* 浅黄色背景 */
        border-left: 4px solid #f0b429;
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
    }

    .error-box {
        background-color: #fff5f5; /* 浅红色背景 */
        border-left: 4px solid #e53e3e;
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
    }

    /* 历史对话列表样式 */
    .history-list {
        max-height: 400px;
        overflow-y: auto;
        margin-bottom: 1.5rem;
    }

    .history-item {
        padding: 1rem;
        border-radius: 8px;
        background-color: #f0f0e6; /* 米色背景 */
        margin-bottom: 0.75rem;
        cursor: pointer;
        transition: all 0.2s;
        border: 1px solid #e6e6d8; /* 米色边框 */
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .history-item:hover {
        background-color: #e6e6d8; /* 悬停时更深的米色 */
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .history-item-title {
        font-weight: 500;
        color: #141414;
        flex-grow: 1;
    }

    .history-item-date {
        font-size: 0.85rem;
        color: #666;
        margin-left: 1rem;
    }

    .history-item-delete {
        color: #e53e3e;
        margin-left: 0.5rem;
        opacity: 0.6;
        transition: opacity 0.2s;
    }

    .history-item-delete:hover {
        opacity: 1;
    }

    /* 主内容区样式 */
    .main-content {
        background-color: #fafaf5; /* 浅米色背景 */
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        margin-bottom: 1.5rem;
    }

    /* 输入区域样式 */
    .input-area {
        background-color: #fafaf5; /* 浅米色背景 */
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        margin-top: 1rem;
        border: 1px solid #f0f0e6; /* 米色边框 */
    }

    /* 动画效果 */
    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 1; }
        100% { opacity: 0.6; }
    }

    .loading-animation {
        animation: pulse 1.5s infinite;
    }

    /* 响应式调整 */
    @media (max-width: 768px) {
        .main-title {
            font-size: 1.8rem;
        }

        .sub-title {
            font-size: 1.3rem;
        }

        .message-container {
            padding: 1rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# 页面标题和介绍
st.markdown('<h1 class="main-title">📚 交互式"穿书"小说体验程序</h1>', unsafe_allow_html=True)
st.markdown('<div class="info-box">上传您喜爱的TXT格式小说，选择模型进行分析和续写，开始您的"穿书"之旅吧！</div>',
            unsafe_allow_html=True)


# --- 初始化 Session State ---
def initialize_session_state() -> None:
    """初始化Streamlit的session_state，用于存储应用状态。"""
    defaults: Dict[str, Any] = {
        "app_stage": "config_novel",  # 应用当前阶段: config_novel, processing, initializing_narrative, narrating
        "analysis_llm_client": None,  # 分析用LLM客户端实例
        "writing_llm_client": None,  # 写作用LLM客户端实例
        "novel_processor": None,  # 小说处理器实例
        "narrative_engine": None,  # 叙事引擎实例
        "narrative_history_display": [],  # 用于UI显示的叙事历史 (List[Tuple[str, str]])
        "selected_analysis_model": config.DEFAULT_ANALYSIS_OLLAMA_MODEL,  # 当前选择的分析模型
        "selected_writing_model_local": config.DEFAULT_WRITING_OLLAMA_MODEL,  # 当前选择的本地写作模型
        "analysis_model_source": "Local Ollama",  # 分析模型来源: "Local Ollama" 或 "Online API"
        "analysis_api_url": "",  # 分析用在线API的URL
        "analysis_api_model_name": "",  # 分析用在线API的模型名称
        "analysis_api_key": "",  # 分析用在线API的密钥 (仅存于会话状态)
        "writing_model_source": "Local Ollama",  # 写作模型来源: "Local Ollama" 或 "Online API"
        "writing_api_url": "",  # 在线API的URL
        "writing_api_model_name": "",  # 在线API的模型名称
        "writing_api_key": "",  # 在线API的密钥 (仅存于会话状态)
        "novel_specific_data_dir_ui": None,  # 当前处理的小说对应的数据子目录
        "ollama_api_url_config": config.OLLAMA_API_BASE_URL,  # Ollama API的URL (来自配置)
        "chapters_data_path_ui": None,  # 章节数据文件路径
        "final_analysis_path_ui": None,  # 最终分析文件路径
        "current_novel_path": None,  # 当前上传的小说文件路径
        "engine_state_to_load": None,  # 用于加载已保存游戏时，叙事引擎的待加载状态 (Dict[str, Any])
        "potential_save_file_path": None,  # 检测到的当前小说的潜在存档文件路径
        "uploaded_novel_name": None,  # 当前上传的小说文件名，用于跟踪小说是否变化
        "history_conversations": [],  # 历史对话列表
        "show_history_panel": False,  # 是否显示历史对话面板
        # 叙事引擎配置参数 (从config.py同步)
        "initial_context_chapters": config.INITIAL_CONTEXT_CHAPTERS,
        "narrative_window_chapter_before": config.NARRATIVE_WINDOW_CHAPTER_BEFORE,
        "narrative_window_chapter_after": config.NARRATIVE_WINDOW_CHAPTER_AFTER,
        "divergence_threshold": config.DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE,
        # 小说处理配置参数 (从config.py同步)
        "chapter_split_regex": config.CHAPTER_SPLIT_REGEX,
        "analysis_batch_size": config.ANALYSIS_BATCH_SIZE,
        # 模型参数
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 1024,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        # 动画和交互
        "show_typing_animation": True,  # 是否显示打字动画
        "typing_speed": 30,  # 打字速度 (字符/秒)
        "enable_keyboard_shortcuts": True,  # 是否启用键盘快捷键
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()  # 执行初始化


# --- 辅助函数：重置部分会话状态，用于开始新旅程或重置 ---
def reset_for_new_journey() -> None:
    """重置应用状态以开始新的旅程。会保留LLM和服务配置。"""
    keys_to_clear: List[str] = [
        "app_stage", "novel_processor", "narrative_engine", "narrative_history_display",
        "chapters_data_path_ui", "final_analysis_path_ui", "novel_specific_data_dir_ui",
        "current_novel_path",  # 保留LLM客户端实例，因为它们的配置可能不希望被重置
        # "analysis_llm_client", "writing_llm_client", # 客户端如果与特定小说无关，可以不清
        "engine_state_to_load", "potential_save_file_path", "uploaded_novel_name"
    ]
    # 需要重置为初始值的配置（如果用户修改过）
    config_keys_to_reset_to_defaults: Dict[str, Any] = {
        "initial_context_chapters": config.INITIAL_CONTEXT_CHAPTERS,
        "narrative_window_chapter_before": config.NARRATIVE_WINDOW_CHAPTER_BEFORE,
        "narrative_window_chapter_after": config.NARRATIVE_WINDOW_CHAPTER_AFTER,
        "divergence_threshold": config.DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE,
        "chapter_split_regex": config.CHAPTER_SPLIT_REGEX,
        "analysis_batch_size": config.ANALYSIS_BATCH_SIZE,
        "temperature": 0.7,  # 或者也从config.py读取默认值
        "top_p": 0.9,
        "max_tokens": 1024,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]  # 删除，以便initialize_session_state重新创建为默认值

    # 重新初始化，这样会用上 defaults 字典中的值
    initialize_session_state()

    # 对于用户可能在UI中更改的配置，显式重置回 config.py 的默认值
    for key, default_value in config_keys_to_reset_to_defaults.items():
        st.session_state[key] = default_value

    st.markdown('<div class="success-box">已重置应用状态。您可以开始新的旅程或上传不同的小说。LLM和服务配置已保留。</div>',
                unsafe_allow_html=True)


# --- 历史对话管理函数 ---
def load_history_conversations() -> List[Dict[str, Any]]:
    """加载所有历史对话"""
    history_dir = os.path.join(config.DATA_DIR, HISTORY_DIR)
    if not os.path.exists(history_dir):
        os.makedirs(history_dir, exist_ok=True)
        return []

    history_files = [f for f in os.listdir(history_dir) if f.endswith('.json')]
    history_list = []

    for file in history_files:
        try:
            file_path = os.path.join(history_dir, file)
            history_data = utils.read_json_file(file_path)
            if history_data and "metadata" in history_data:
                # 添加文件路径以便后续操作
                history_data["file_path"] = file_path
                history_list.append(history_data)
        except Exception as e:
            st.error(f"加载历史对话文件 {file} 失败: {e}")

    # 按时间倒序排序
    history_list.sort(key=lambda x: x["metadata"].get("timestamp", 0), reverse=True)
    return history_list


def save_current_conversation() -> Optional[str]:
    """保存当前对话到历史记录"""
    if not st.session_state.narrative_engine or not st.session_state.uploaded_novel_name:
        return None

    try:
        # 确保历史目录存在
        history_dir = os.path.join(config.DATA_DIR, HISTORY_DIR)
        os.makedirs(history_dir, exist_ok=True)

        # 获取叙事引擎的当前状态
        engine_state = st.session_state.narrative_engine.get_state_for_saving()

        # 创建应用配置快照
        app_config = {
            "selected_analysis_model": st.session_state.selected_analysis_model,
            "selected_writing_model_local": st.session_state.selected_writing_model_local,
            "writing_model_source": st.session_state.writing_model_source,
            "writing_api_url": st.session_state.writing_api_url,
            "writing_api_model_name": st.session_state.writing_api_model_name,
            "ollama_api_url_config": st.session_state.ollama_api_url_config,
            "novel_specific_data_dir_ui": st.session_state.novel_specific_data_dir_ui,
            "chapters_data_path_ui": st.session_state.chapters_data_path_ui,
            "final_analysis_path_ui": st.session_state.final_analysis_path_ui,
            "current_novel_path": st.session_state.current_novel_path,
            # 保存叙事引擎配置
            "initial_context_chapters": st.session_state.initial_context_chapters,
            "narrative_window_chapter_before": st.session_state.narrative_window_chapter_before,
            "narrative_window_chapter_after": st.session_state.narrative_window_chapter_after,
            "divergence_threshold": st.session_state.divergence_threshold,
            # 保存模型参数
            "temperature": st.session_state.temperature,
            "top_p": st.session_state.top_p,
            "max_tokens": st.session_state.max_tokens,
            "frequency_penalty": st.session_state.frequency_penalty,
            "presence_penalty": st.session_state.presence_penalty,
        }

        # 提取对话内容的摘要作为标题
        conversation_summary = "无对话内容"
        if st.session_state.narrative_history_display:
            # 使用最后一条AI消息作为摘要
            for role, content in reversed(st.session_state.narrative_history_display):
                if role == "AI":
                    # 截取前30个字符作为摘要
                    conversation_summary = content[:30] + ("..." if len(content) > 30 else "")
                    break

        # 创建元数据
        timestamp = int(time.time())
        formatted_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        metadata = {
            "novel_name": st.session_state.uploaded_novel_name,
            "title": conversation_summary,
            "timestamp": timestamp,
            "formatted_time": formatted_time,
            "message_count": len(st.session_state.narrative_history_display)
        }

        # 组合完整的存档数据
        history_data = {
            "metadata": metadata,
            "app_config": app_config,
            "engine_state": engine_state
        }

        # 生成文件名
        filename = f"history_{timestamp}_{utils.sanitize_filename(st.session_state.uploaded_novel_name)}.json"
        file_path = os.path.join(history_dir, filename)

        # 保存到文件
        utils.write_json_file(history_data, file_path)

        # 刷新历史对话列表
        st.session_state.history_conversations = load_history_conversations()

        return file_path

    except Exception as e:
        st.error(f"保存历史对话失败: {e}")
        return None


def delete_history_conversation(file_path: str) -> bool:
    """删除指定的历史对话"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            # 刷新历史对话列表
            st.session_state.history_conversations = load_history_conversations()
            return True
        return False
    except Exception as e:
        st.error(f"删除历史对话失败: {e}")
        return False


def load_conversation_from_history(history_item: Dict[str, Any]) -> bool:
    """从历史记录加载对话"""
    try:
        if "app_config" not in history_item or "engine_state" not in history_item:
            st.error("历史对话数据格式不正确")
            return False

        # 从历史记录恢复应用配置
        app_conf = history_item["app_config"]
        st.session_state.selected_analysis_model = app_conf.get("selected_analysis_model",
                                                                config.DEFAULT_ANALYSIS_OLLAMA_MODEL)
        st.session_state.selected_writing_model_local = app_conf.get("selected_writing_model_local",
                                                                     config.DEFAULT_WRITING_OLLAMA_MODEL)
        st.session_state.writing_model_source = app_conf.get("writing_model_source", "Local Ollama")
        st.session_state.writing_api_url = app_conf.get("writing_api_url", "")
        st.session_state.writing_api_model_name = app_conf.get("writing_api_model_name", "")
        # API Key 不从存档恢复，用户必须确保它在会话中或在使用在线API时重新输入
        st.session_state.ollama_api_url_config = app_conf.get("ollama_api_url_config", config.OLLAMA_API_BASE_URL)

        st.session_state.novel_specific_data_dir_ui = app_conf["novel_specific_data_dir_ui"]
        st.session_state.chapters_data_path_ui = app_conf["chapters_data_path_ui"]
        st.session_state.final_analysis_path_ui = app_conf["final_analysis_path_ui"]
        st.session_state.current_novel_path = app_conf["current_novel_path"]

        # 恢复叙事引擎配置
        st.session_state.initial_context_chapters = app_conf.get("initial_context_chapters",
                                                                 config.INITIAL_CONTEXT_CHAPTERS)
        st.session_state.narrative_window_chapter_before = app_conf.get("narrative_window_chapter_before",
                                                                        config.NARRATIVE_WINDOW_CHAPTER_BEFORE)
        st.session_state.narrative_window_chapter_after = app_conf.get("narrative_window_chapter_after",
                                                                       config.NARRATIVE_WINDOW_CHAPTER_AFTER)
        st.session_state.divergence_threshold = app_conf.get("divergence_threshold",
                                                             config.DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE)

        # 恢复模型参数
        st.session_state.temperature = app_conf.get("temperature", 0.7)
        st.session_state.top_p = app_conf.get("top_p", 0.9)
        st.session_state.max_tokens = app_conf.get("max_tokens", 1024)
        st.session_state.frequency_penalty = app_conf.get("frequency_penalty", 0.0)
        st.session_state.presence_penalty = app_conf.get("presence_penalty", 0.0)

        # 将叙事引擎的内部状态存入session_state，供后续初始化使用
        st.session_state.engine_state_to_load = history_item["engine_state"]
        st.session_state.app_stage = "initializing_narrative"  # 跳过Stage 1处理，直接进入叙事引擎初始化

        # 隐藏历史面板
        st.session_state.show_history_panel = False

        return True
    except Exception as e:
        st.error(f"加载历史对话失败: {e}")
        return False


# --- API 配置加载与保存 ---
def load_api_configs() -> bool:
    """从本地文件加载API配置 (URL和模型名，不含Key)"""
    config_path = os.path.join(config.DATA_DIR, API_CONFIG_FILENAME)
    if os.path.exists(config_path):
        try:
            saved_configs = utils.read_json_file(config_path)
            if not saved_configs: return False  # 文件为空或无效JSON

            if "analysis_api_configs" in saved_configs:
                analysis_config = saved_configs["analysis_api_configs"]
                st.session_state.analysis_api_url = analysis_config.get("url", st.session_state.analysis_api_url)
                st.session_state.analysis_api_model_name = analysis_config.get("model",
                                                                               st.session_state.analysis_api_model_name)

            if "writing_api_configs" in saved_configs:
                writing_config = saved_configs["writing_api_configs"]
                st.session_state.writing_api_url = writing_config.get("url", st.session_state.writing_api_url)
                st.session_state.writing_api_model_name = writing_config.get("model",
                                                                             st.session_state.writing_api_model_name)
            return True
        except Exception as e:
            st.sidebar.error(f"加载API配置失败: {e}")
    return False


def save_api_configs() -> bool:
    """将API配置保存到本地文件 (URL和模型名，不含Key)"""
    config_path = os.path.join(config.DATA_DIR, API_CONFIG_FILENAME)
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        configs_to_save: Dict[str, Any] = {
            "analysis_api_configs": {
                "url": st.session_state.analysis_api_url,
                "model": st.session_state.analysis_api_model_name,
            },
            "writing_api_configs": {
                "url": st.session_state.writing_api_url,
                "model": st.session_state.writing_api_model_name,
            }
        }
        return utils.write_json_file(configs_to_save, config_path)
    except Exception as e:
        st.sidebar.error(f"保存API配置失败: {e}")
        return False


if "api_configs_loaded" not in st.session_state:  # 仅在首次运行时加载
    load_api_configs()
    st.session_state.api_configs_loaded = True

# 加载历史对话列表
if "history_conversations" not in st.session_state or not st.session_state.history_conversations:
    st.session_state.history_conversations = load_history_conversations()


# --- 辅助函数：验证在线API连接 ---
def _verify_online_api(api_url: str, api_key: str, model_name: str, purpose: str) -> Optional[GenericOnlineAPIClient]:
    """测试在线API连接并返回客户端实例（如果成功）。"""
    if not all([api_url, api_key, model_name]):
        st.error(f"请为 {purpose} 填写完整的在线API配置信息 (URL, 模型名称, API Key)。")
        return None
    try:
        with st.spinner(f"正在验证 {purpose} 的API连接..."):
            test_client = GenericOnlineAPIClient(api_url=api_url, api_key=api_key, model_name=model_name)
            test_messages = [{"role": "system", "content": "You are a test assistant."},
                             {"role": "user", "content": "Ping."}]
            response = test_client.generate_chat_completion(model=model_name, messages=test_messages, stream=False,
                                                            timeout=30)  # 短超时测试
            if response and response.get("message"):
                st.markdown('<div class="success-box">API连接成功！</div>', unsafe_allow_html=True)
                return test_client
            else:
                st.markdown('<div class="error-box">API连接失败：未能获取有效响应。请检查URL、模型名称和API Key。</div>',
                            unsafe_allow_html=True)
                return None
    except Exception as e:
        st.markdown(f'<div class="error-box">API连接失败：{e}</div>', unsafe_allow_html=True)
        return None


# --- 侧边栏配置 ---
st.sidebar.markdown('<h2 class="sidebar-title">⚙️ 系统配置</h2>', unsafe_allow_html=True)

# 创建侧边栏标签页
config_tabs = st.sidebar.tabs(["基础配置", "模型参数", "叙事引擎", "小说处理", "界面设置"])

with config_tabs[0]:  # 基础配置标签页
    # Ollama API URL 输入
    ollama_api_url_ui = st.text_input(
        "Ollama API 地址 (用于本地模型)",
        st.session_state.ollama_api_url_config,
        key="ollama_api_url_input",
        help="用于本地Ollama模型的API基础URL，例如 http://127.0.0.1:11434"
    )
    # 如果用户修改了Ollama API URL，则更新session_state并重置相关客户端
    if ollama_api_url_ui != st.session_state.ollama_api_url_config:
        st.session_state.ollama_api_url_config = ollama_api_url_ui
        st.session_state.analysis_llm_client = None  # 重置分析客户端
        st.session_state.writing_llm_client = None  # 重置写作客户端 (如果来源是本地)
        st.rerun()  # 重新运行Streamlit应用以应用更改

    # 初始化分析用Ollama客户端
    if st.session_state.analysis_llm_client is None and st.session_state.ollama_api_url_config and st.session_state.analysis_model_source == "Local Ollama":
        try:
            st.session_state.analysis_llm_client = OllamaClient(base_url=st.session_state.ollama_api_url_config)
            st.success(f"Ollama客户端已连接到: {st.session_state.ollama_api_url_config}")
        except Exception as e:
            st.error(f"连接Ollama客户端失败: {e}")
            st.session_state.analysis_llm_client = None

    # 获取可用的Ollama模型列表
    model_names = []
    if st.session_state.analysis_llm_client and isinstance(st.session_state.analysis_llm_client, OllamaClient):
        try:
            available_models_data = st.session_state.analysis_llm_client.list_local_models()
            if available_models_data:
                model_names = [m["name"] for m in available_models_data]
            if not model_names:
                st.warning("未能获取Ollama模型列表。请确保Ollama服务运行正常且已拉取模型。将允许手动输入。")
        except Exception as e:
            st.error(f"获取Ollama模型列表时出错: {e}")

    st.markdown("---")
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">小说分析模型</h3>', unsafe_allow_html=True)

    # 分析模型来源选择 (单选按钮)
    st.session_state.analysis_model_source = st.radio(
        "选择分析模型来源",
        ["Local Ollama", "Online API"],
        index=0 if st.session_state.analysis_model_source == "Local Ollama" else 1,
        key="analysis_source_radio",
        horizontal=True  # 水平排列选项
    )

    if st.session_state.analysis_model_source == "Local Ollama":  # 如果选择本地Ollama
        current_analysis_model = st.session_state.selected_analysis_model
        if model_names:  # 如果成功获取到模型列表
            # 设置默认选中的分析模型
            default_analysis_idx = model_names.index(
                current_analysis_model) if current_analysis_model in model_names else \
                (model_names.index(
                    config.DEFAULT_ANALYSIS_OLLAMA_MODEL) if config.DEFAULT_ANALYSIS_OLLAMA_MODEL in model_names else 0)
            if not (current_analysis_model in model_names) and model_names:  # 如果当前选中模型不在列表中，则重置为默认
                st.session_state.selected_analysis_model = model_names[default_analysis_idx]

            selected_analysis_model_ui = st.selectbox(
                "选择分析用Ollama模型", model_names, index=default_analysis_idx, key="analysis_model_select"
            )
        else:  # 如果未能获取模型列表，允许用户手动输入
            selected_analysis_model_ui = st.text_input(
                "手动输入分析用Ollama模型名", current_analysis_model or config.DEFAULT_ANALYSIS_OLLAMA_MODEL,
                key="analysis_model_manual_input"
            )
        # 更新session_state中的分析模型选择
        if selected_analysis_model_ui != st.session_state.selected_analysis_model:
            st.session_state.selected_analysis_model = selected_analysis_model_ui
            # st.rerun() # 避免在其他配置更改时立即重跑
    elif st.session_state.analysis_model_source == "Online API":  # 如果选择在线API
        st.text_input(  # MODIFIED LINE
            "Online API URL", value=st.session_state.analysis_api_url, key="analysis_api_url",
            placeholder="例如: https://api.openai.com/v1/chat/completions"
        )
        st.text_input(  # MODIFIED LINE
            "Online API 模型名称", value=st.session_state.analysis_api_model_name, key="analysis_api_model_name",
            placeholder="例如: gpt-3.5-turbo"
        )
        st.text_input(  # MODIFIED LINE
            "Online API Key", value=st.session_state.analysis_api_key, type="password", key="analysis_api_key"
        )
        st.caption("API Key 仅储存于当前会话，不会永久保存。")  # 提示信息

        # 验证API连接按钮
        if st.button("验证API连接", key="verify_analysis_api_btn"):
            if not st.session_state.analysis_api_url or not st.session_state.analysis_api_model_name or not st.session_state.analysis_api_key:
                st.error("请填写完整的API配置信息")
            else:
                # 尝试创建API客户端并进行简单测试
                test_client = _verify_online_api(
                    st.session_state.analysis_api_url,
                    st.session_state.analysis_api_key,
                    st.session_state.analysis_api_model_name,
                    "分析模型"
                )
                if test_client:
                    # 创建分析用LLM客户端
                    st.session_state.analysis_llm_client = test_client
                    # 保存API配置
                    save_api_configs()

    st.markdown("---")
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">故事写作模型</h3>', unsafe_allow_html=True)

    # 写作模型来源选择 (单选按钮)
    st.session_state.writing_model_source = st.radio(
        "选择写作模型来源",
        ["Local Ollama", "Online API"],
        index=0 if st.session_state.writing_model_source == "Local Ollama" else 1,
        key="writing_source_radio",
        horizontal=True  # 水平排列选项
    )

    if st.session_state.writing_model_source == "Local Ollama":  # 如果选择本地Ollama
        current_writing_model_local = st.session_state.selected_writing_model_local
        if model_names:  # 如果有模型列表
            default_writing_idx = model_names.index(
                current_writing_model_local) if current_writing_model_local in model_names else \
                (model_names.index(
                    config.DEFAULT_WRITING_OLLAMA_MODEL) if config.DEFAULT_WRITING_OLLAMA_MODEL in model_names else 0)
            if not (current_writing_model_local in model_names) and model_names:
                st.session_state.selected_writing_model_local = model_names[default_writing_idx]
            selected_writing_model_ui_local = st.selectbox(
                "选择写作用Ollama模型 (本地)", model_names, index=default_writing_idx, key="writing_model_select_local"
            )
        else:  # 无模型列表则手动输入
            selected_writing_model_ui_local = st.text_input(
                "手动输入写作用Ollama模型名 (本地)", current_writing_model_local or config.DEFAULT_WRITING_OLLAMA_MODEL,
                key="writing_model_manual_input_local"
            )
        if selected_writing_model_ui_local != st.session_state.selected_writing_model_local:
            st.session_state.selected_writing_model_local = selected_writing_model_ui_local
            # st.rerun()
    elif st.session_state.writing_model_source == "Online API":  # 如果选择在线API
        st.text_input(  # MODIFIED LINE
            "Online API URL", value=st.session_state.writing_api_url, key="online_api_url",
            placeholder="例如: https://api.openai.com/v1/chat/completions"
        )
        st.text_input(  # MODIFIED LINE
            "Online API 模型名称", value=st.session_state.writing_api_model_name, key="online_api_model_name",
            placeholder="例如: gpt-3.5-turbo"
        )
        st.text_input(  # MODIFIED LINE
            "Online API Key", value=st.session_state.writing_api_key, type="password", key="online_api_key"
        )
        st.caption("API Key 仅储存于当前会话，不会永久保存。")  # 提示信息

        # 验证API连接按钮
        if st.button("验证API连接", key="verify_writing_api_btn"):
            if not st.session_state.writing_api_url or not st.session_state.writing_api_model_name or not st.session_state.writing_api_key:
                st.error("请填写完整的API配置信息")
            else:
                # 尝试创建API客户端并进行简单测试
                test_client = _verify_online_api(
                    st.session_state.writing_api_url,
                    st.session_state.writing_api_key,
                    st.session_state.writing_api_model_name,
                    "写作模型"
                )
                if test_client:
                    # 保存API配置
                    save_api_configs()

with config_tabs[1]:  # 模型参数标签页
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">模型生成参数</h3>', unsafe_allow_html=True)

    # 温度参数
    st.session_state.temperature = st.slider(
        "Temperature (创造性)",
        min_value=0.0,
        max_value=2.0,
        value=st.session_state.temperature,
        step=0.1,
        format="%.1f",
        help="控制生成文本的随机性。较低的值使输出更确定，较高的值使输出更多样化。"
    )

    # Top-p参数
    st.session_state.top_p = st.slider(
        "Top-p (核采样)",
        min_value=0.1,
        max_value=1.0,
        value=st.session_state.top_p,
        step=0.1,
        format="%.1f",
        help="控制模型考虑的词汇范围。较低的值使输出更聚焦，较高的值使输出更多样化。"
    )

    # 最大生成长度
    st.session_state.max_tokens = st.slider(
        "最大生成长度",
        min_value=256,
        max_value=4096,
        value=st.session_state.max_tokens,
        step=128,
        help="控制模型生成的最大token数量。"
    )

    # 频率惩罚
    st.session_state.frequency_penalty = st.slider(
        "频率惩罚",
        min_value=-2.0,
        max_value=2.0,
        value=st.session_state.frequency_penalty,
        step=0.1,
        format="%.1f",
        help="减少模型重复使用相同词汇的倾向。正值降低重复，负值增加重复。"
    )

    # 存在惩罚
    st.session_state.presence_penalty = st.slider(
        "存在惩罚",
        min_value=-2.0,
        max_value=2.0,
        value=st.session_state.presence_penalty,
        step=0.1,
        format="%.1f",
        help="减少模型讨论已出现过的主题的倾向。正值鼓励讨论新主题，负值鼓励重复已讨论的主题。"
    )

with config_tabs[2]:  # 叙事引擎标签页
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">叙事引擎配置</h3>', unsafe_allow_html=True)

    # 初始上下文章节数
    st.session_state.initial_context_chapters = st.number_input(
        "初始上下文章节数",
        min_value=1,
        max_value=10,
        value=st.session_state.initial_context_chapters,
        help="叙事引擎初始化时，提供给LLM作为初始上下文的章节数量。"
    )

    # 当前章节之前的窗口大小
    st.session_state.narrative_window_chapter_before = st.number_input(
        "当前章节之前的窗口大小",
        min_value=0,
        max_value=5,
        value=st.session_state.narrative_window_chapter_before,
        help="叙事时，LLM参考的当前章节之前的章节数量。设为0可避免回顾过多已发生剧情。"
    )

    # 当前章节之后的窗口大小
    st.session_state.narrative_window_chapter_after = st.number_input(
        "当前章节之后的窗口大小",
        min_value=0,
        max_value=5,
        value=st.session_state.narrative_window_chapter_after,
        help="叙事时，LLM参考的当前章节之后的章节数量。设为0或1可减少未来信息泄露。"
    )

    # 偏离阈值
    divergence_options = ["轻微", "中度", "显著"]
    divergence_index = divergence_options.index(
        st.session_state.divergence_threshold) if st.session_state.divergence_threshold in divergence_options else 1
    st.session_state.divergence_threshold = st.selectbox(
        "偏离阈值",
        divergence_options,
        index=divergence_index,
        help="当剧情与原著的偏离程度达到此阈值时，尝试引导剧情回归。"
    )

with config_tabs[3]:  # 小说处理标签页
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">小说处理配置</h3>', unsafe_allow_html=True)

    # 章节分割正则表达式
    st.session_state.chapter_split_regex = st.text_input(
        "章节分割正则表达式",
        value=st.session_state.chapter_split_regex,
        help="用于将小说文本分割成章节的正则表达式。"
    )

    # 分析批次大小
    st.session_state.analysis_batch_size = st.number_input(
        "分析批次大小",
        min_value=1,
        max_value=10,
        value=st.session_state.analysis_batch_size,
        help="LLM分析小说时，每批处理的章节数量。推荐设为1以实现逐章分析，提高章节定位准确性。"
    )

with config_tabs[4]:  # 界面设置标签页
    st.markdown('<h3 class="sidebar-title" style="font-size: 1rem;">界面与交互设置</h3>', unsafe_allow_html=True)

    # 打字动画设置
    st.session_state.show_typing_animation = st.checkbox(
        "启用打字动画",
        value=st.session_state.show_typing_animation,
        help="启用后，AI回复将以打字效果逐字显示。"
    )

    if st.session_state.show_typing_animation:
        st.session_state.typing_speed = st.slider(
            "打字速度",
            min_value=10,
            max_value=100,
            value=st.session_state.typing_speed,
            step=5,
            help="控制AI回复的打字速度，单位为字符/秒。"
        )

    # 键盘快捷键设置
    st.session_state.enable_keyboard_shortcuts = st.checkbox(
        "启用键盘快捷键",
        value=st.session_state.enable_keyboard_shortcuts,
        help="启用后，可以使用Enter键发送消息，Ctrl+Enter换行。"
    )

# 保存配置按钮
if st.sidebar.button("💾 保存API配置", key="save_api_config_btn"):
    if save_api_configs():
        st.sidebar.success("API配置已保存")

# 历史对话按钮
if st.sidebar.button("📜 历史对话", key="show_history_btn"):
    st.session_state.show_history_panel = not st.session_state.show_history_panel

# 重置按钮
if st.sidebar.button("🔄 重置应用", key="reset_app_btn"):
    reset_for_new_journey()
    st.rerun()


def get_analysis_llm_client() -> Optional[LLMClientInterface]:
    """根据session_state中的配置获取分析LLM客户端实例。"""
    if st.session_state.analysis_model_source == "Local Ollama":
        if st.session_state.analysis_llm_client and isinstance(st.session_state.analysis_llm_client, OllamaClient):
            return st.session_state.analysis_llm_client
        elif st.session_state.ollama_api_url_config:
            try:
                return OllamaClient(base_url=st.session_state.ollama_api_url_config)
            except Exception as e:
                st.sidebar.error(f"创建本地分析Ollama客户端失败: {e}"); return None
        else:
            st.sidebar.error("Ollama API URL 未配置，无法使用本地分析模型。"); return None
    elif st.session_state.analysis_model_source == "Online API":
        if st.session_state.analysis_api_url and st.session_state.analysis_api_model_name and st.session_state.analysis_api_key:
            try:
                return GenericOnlineAPIClient(
                    api_url=st.session_state.analysis_api_url,
                    api_key=st.session_state.analysis_api_key,
                    model_name=st.session_state.analysis_api_model_name
                )
            except Exception as e:
                st.sidebar.error(f"创建在线API客户端失败: {e}"); return None
        else:
            st.sidebar.warning("请填写完整的在线API配置信息 (URL, 模型名称, API Key)。"); return None
    return None


def get_writing_llm_client() -> Optional[LLMClientInterface]:
    """根据session_state中的配置获取写作LLM客户端实例。"""
    if st.session_state.writing_model_source == "Local Ollama":
        # 如果分析客户端是OllamaClient且已初始化，则复用
        if st.session_state.analysis_llm_client and isinstance(st.session_state.analysis_llm_client, OllamaClient):
            return st.session_state.analysis_llm_client
        elif st.session_state.ollama_api_url_config:  # 否则尝试新建一个
            try:
                return OllamaClient(base_url=st.session_state.ollama_api_url_config)
            except Exception as e:
                st.sidebar.error(f"创建本地写作Ollama客户端失败: {e}"); return None
        else:
            st.sidebar.error("Ollama API URL 未配置，无法使用本地写作模型。"); return None
    elif st.session_state.writing_model_source == "Online API":
        # 确保在线API的URL、模型名和Key都已填写
        if st.session_state.writing_api_url and st.session_state.writing_api_model_name and st.session_state.writing_api_key:
            try:
                return GenericOnlineAPIClient(
                    api_url=st.session_state.writing_api_url,
                    api_key=st.session_state.writing_api_key,
                    model_name=st.session_state.writing_api_model_name
                )
            except Exception as e:
                st.sidebar.error(f"创建在线API客户端失败: {e}"); return None
        else:
            st.sidebar.warning("请填写完整的在线API配置信息 (URL, 模型名称, API Key)。"); return None
    return None


# --- 历史对话面板 ---
if st.session_state.show_history_panel:
    st.markdown('<h2 class="sub-title">📜 历史对话</h2>', unsafe_allow_html=True)

    if not st.session_state.history_conversations:
        st.markdown('<div class="info-box">暂无历史对话记录</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="history-list">', unsafe_allow_html=True)

        for idx, history_item in enumerate(st.session_state.history_conversations):
            metadata = history_item.get("metadata", {})
            novel_name = metadata.get("novel_name", "未知小说")
            title = metadata.get("title", "无标题对话")
            formatted_time = metadata.get("formatted_time", "未知时间")
            message_count = metadata.get("message_count", 0)

            col1, col2, col3 = st.columns([5, 3, 1])

            with col1:
                if st.button(f"{novel_name}: {title}", key=f"history_item_{idx}"):
                    if load_conversation_from_history(history_item):
                        st.rerun()

            with col2:
                st.markdown(
                    f"<div style='text-align: right; color: #666; font-size: 0.85rem;'>{formatted_time} ({message_count}条消息)</div>",
                    unsafe_allow_html=True)

            with col3:
                if st.button("🗑️", key=f"delete_history_{idx}"):
                    if delete_history_conversation(history_item.get("file_path", "")):
                        st.success("已删除历史对话")
                        st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("关闭历史面板", key="close_history_btn"):
        st.session_state.show_history_panel = False
        st.rerun()

# --- 小说文件上传与处理 ---
st.sidebar.markdown("---")  # 分隔线
uploaded_file = st.sidebar.file_uploader("上传TXT小说文件", type=["txt"], key="novel_uploader")  # 文件上传控件

if uploaded_file:
    novel_filename = uploaded_file.name
    # 如果上传了新的小说文件，重置潜在的存档文件路径
    if novel_filename != st.session_state.get("uploaded_novel_name"):
        st.session_state.uploaded_novel_name = novel_filename
        st.session_state.potential_save_file_path = None  # 重置以重新检查

    # 确定潜在的存档文件路径（仅在初次上传或小说更改后执行一次）
    if st.session_state.app_stage == "config_novel" and not st.session_state.potential_save_file_path:
        # 根据小说文件名（去除扩展名并处理特殊字符）构建小说专属数据目录
        potential_novel_specific_dir = os.path.join(config.DATA_DIR,
                                                    utils.sanitize_filename(os.path.splitext(novel_filename)[0]))
        # 拼接存档文件路径
        st.session_state.potential_save_file_path = os.path.join(potential_novel_specific_dir,
                                                                 STORY_SAVE_STATE_FILENAME)

    # 如果检测到当前上传小说的存档文件，则提供加载或开始新游戏的选项
    if st.session_state.app_stage == "config_novel" and \
            st.session_state.potential_save_file_path and \
            os.path.exists(st.session_state.potential_save_file_path):
        st.sidebar.markdown(f'<div class="info-box">检测到《{novel_filename}》的已存进度。</div>', unsafe_allow_html=True)
        col_load, col_new = st.sidebar.columns(2)  # 两列布局按钮

        if col_load.button("🔄 加载上次进度", key="load_game_btn", help="加载上次保存的故事进度"):  # 加载游戏按钮
            try:
                full_save_data = utils.read_json_file(st.session_state.potential_save_file_path)
                # 校验存档文件格式
                if not full_save_data or "app_config_snapshot" not in full_save_data or "narrative_engine_internal_state" not in full_save_data:
                    st.sidebar.error("存档文件格式不正确或已损坏。")
                else:
                    # 从存档中恢复应用配置
                    app_conf = full_save_data["app_config_snapshot"]
                    st.session_state.selected_analysis_model = app_conf.get("selected_analysis_model",
                                                                            config.DEFAULT_ANALYSIS_OLLAMA_MODEL)
                    st.session_state.selected_writing_model_local = app_conf.get("selected_writing_model_local",
                                                                                 config.DEFAULT_WRITING_OLLAMA_MODEL)
                    st.session_state.writing_model_source = app_conf.get("writing_model_source", "Local Ollama")
                    st.session_state.writing_api_url = app_conf.get("writing_api_url", "")
                    st.session_state.writing_api_model_name = app_conf.get("writing_api_model_name", "")
                    # API Key 不从存档恢复，用户必须确保它在会话中或在使用在线API时重新输入
                    st.session_state.ollama_api_url_config = app_conf.get("ollama_api_url_config",
                                                                          config.OLLAMA_API_BASE_URL)

                    st.session_state.novel_specific_data_dir_ui = app_conf["novel_specific_data_dir_ui"]
                    st.session_state.chapters_data_path_ui = app_conf["chapters_data_path_ui"]
                    st.session_state.final_analysis_path_ui = app_conf["final_analysis_path_ui"]
                    st.session_state.current_novel_path = app_conf["current_novel_path"]

                    # 将叙事引擎的内部状态存入session_state，供后续初始化使用
                    st.session_state.engine_state_to_load = full_save_data["narrative_engine_internal_state"]
                    st.session_state.app_stage = "initializing_narrative"  # 跳过Stage 1处理，直接进入叙事引擎初始化
                    st.sidebar.success(f"存档已加载。正在初始化叙事引擎...")
                    st.rerun()  # 重跑应用以应用加载的状态
            except Exception as e:
                st.sidebar.error(f"加载存档失败: {e}")

        if col_new.button("🚀 开始新故事", key="new_game_after_load_detect_btn",
                          help="忽略已有存档，开始全新的故事"):  # 开始新故事按钮 (在检测到存档后)
            st.session_state.engine_state_to_load = None  # 确保不加载旧状态
            st.session_state.app_stage = "processing"  # 进入正常的Stage 1处理流程
            # 保存上传的文件以供处理
            os.makedirs(config.DATA_DIR, exist_ok=True)
            temp_novel_path = os.path.join(config.DATA_DIR, f"temp_{utils.sanitize_filename(novel_filename)}")
            with open(temp_novel_path, "wb") as f: f.write(uploaded_file.getvalue())
            st.session_state.current_novel_path = temp_novel_path
            st.rerun()
    elif st.session_state.app_stage == "config_novel":  # 没有检测到存档文件，或用户选择开始新游戏
        st.sidebar.markdown('<div class="primary-button">', unsafe_allow_html=True)
        if st.sidebar.button("🚀 开始处理小说并初始化世界", key="start_processing_btn",
                             help="开始处理小说并初始化故事世界"):
            # 获取分析LLM客户端
            st.session_state.analysis_llm_client = get_analysis_llm_client()

            if st.session_state.analysis_model_source == "Local Ollama" and not st.session_state.selected_analysis_model:
                st.sidebar.error("请选择分析模型！")
                st.stop()
            elif st.session_state.analysis_model_source == "Online API" and (
                    not st.session_state.analysis_api_url or not st.session_state.analysis_api_model_name or not st.session_state.analysis_api_key):
                st.sidebar.error("请填写完整的在线API配置信息！")
                st.stop()

            if not st.session_state.analysis_llm_client:
                st.sidebar.error("分析用LLM客户端未连接。")
                st.stop()

            st.session_state.engine_state_to_load = None  # 确保是新游戏
            st.session_state.app_stage = "processing"  # 进入Stage 1
            os.makedirs(config.DATA_DIR, exist_ok=True)
            temp_novel_path = os.path.join(config.DATA_DIR, f"temp_{utils.sanitize_filename(novel_filename)}")
            with open(temp_novel_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            st.session_state.current_novel_path = temp_novel_path
            st.rerun()
        st.sidebar.markdown('</div>', unsafe_allow_html=True)

# --- 阶段 1: 小说处理 ---
if st.session_state.app_stage == "processing":
    # 确定分析模型名称
    analysis_model_name = st.session_state.selected_analysis_model if st.session_state.analysis_model_source == "Local Ollama" else st.session_state.analysis_api_model_name

    # 显示加载动画，提示用户正在进行小说预处理和初始分析
    with st.spinner(
            f"⏳ 阶段1：小说预处理与初始分析中 (分析模型: {analysis_model_name} via {st.session_state.analysis_model_source})..."):
        try:
            if not st.session_state.analysis_llm_client:
                st.error("分析用LLM客户端未初始化。")
                st.session_state.app_stage = "config_novel"
                st.stop()

            # 初始化小说处理器
            st.session_state.novel_processor = NovelProcessor(
                st.session_state.analysis_llm_client,  # novel_processor现在只接受一个ollama_client参数，这里传递的是analysis_llm_client
                # 下面两个参数在 NovelProcessor 的 __init__ 中不再需要了，因为它们在 run_stage1 时会基于 novel_txt_path 推断
                # chapter_split_regex=st.session_state.chapter_split_regex,
                # analysis_batch_size=st.session_state.analysis_batch_size
            )

            # NovelProcessor的run_stage1现在需要的是ollama_model的名称，而不是客户端实例
            # 以及需要novel_txt_path
            # NovelProcessor内部会处理chapter_split_regex和analysis_batch_size（如果它需要的话，目前似乎直接用了config）
            stage1_results = st.session_state.novel_processor.run_stage1(
                st.session_state.current_novel_path,
                analysis_model_name  # 传递的是模型名称
            )

            if not stage1_results:
                st.error("小说预处理或初始分析失败。")
                st.session_state.app_stage = "config_novel"
            else:
                # 获取Stage 1的结果：章节数据路径、最终分析路径、小说专属数据目录
                cs_path, fa_path, nsdd = stage1_results
                st.session_state.chapters_data_path_ui = cs_path
                st.session_state.final_analysis_path_ui = fa_path
                st.session_state.novel_specific_data_dir_ui = nsdd
                st.success(f"✅ 小说分析完成！数据存储在: {nsdd}")
                st.session_state.app_stage = "initializing_narrative"  # 进入下一阶段：初始化叙事引擎
                st.rerun()
        except Exception as e:
            st.error(f"处理小说时发生错误: {e}")
            import traceback

            st.error(f"{traceback.format_exc()}")
            st.session_state.app_stage = "config_novel"

# --- 阶段 2: 初始化叙事引擎 ---
if st.session_state.app_stage == "initializing_narrative":
    # 获取写作LLM客户端
    st.session_state.writing_llm_client = get_writing_llm_client()
    # 确定用于UI显示的写作模型名称
    writing_model_display_name = st.session_state.selected_writing_model_local if st.session_state.writing_model_source == "Local Ollama" else st.session_state.writing_api_model_name

    with st.spinner(
            f"⏳ 阶段2：初始化互动叙事会话 (写作模型: {writing_model_display_name} via {st.session_state.writing_model_source})..."):
        if not st.session_state.writing_llm_client:
            st.error("写作LLM客户端未能初始化。")
            st.session_state.app_stage = "config_novel"
            st.stop()

        try:
            # 确定实际用于叙事引擎的写作模型名称
            actual_writing_model_name = st.session_state.selected_writing_model_local if st.session_state.writing_model_source == "Local Ollama" else st.session_state.writing_api_model_name
            if not actual_writing_model_name:
                st.error("未指定有效的写作模型名称。")
                st.session_state.app_stage = "config_novel"
                st.stop()

            # 获取叙事引擎的待加载状态（如果有的话，来自存档）
            engine_initial_state_data = st.session_state.get("engine_state_to_load")

            # 初始化叙事引擎
            # NarrativeEngine 的 __init__ 签名需要更新以匹配 config.py 中的叙事引擎配置
            st.session_state.narrative_engine = NarrativeEngine(
                llm_writer_client=st.session_state.writing_llm_client,
                novel_specific_data_dir=st.session_state.novel_specific_data_dir_ui,
                chapters_data_path=st.session_state.chapters_data_path_ui,
                novel_analysis_path=st.session_state.final_analysis_path_ui,
                writing_model_name=actual_writing_model_name,
                initial_state=engine_initial_state_data,  # 如果是加载游戏，则传入初始状态
                # 直接从 st.session_state 获取叙事引擎相关配置参数
                initial_context_chapters=st.session_state.initial_context_chapters,
                narrative_window_chapter_before=st.session_state.narrative_window_chapter_before,
                narrative_window_chapter_after=st.session_state.narrative_window_chapter_after,
                divergence_threshold=st.session_state.divergence_threshold,
                model_params={  # 添加模型参数
                    "temperature": st.session_state.temperature,
                    "top_p": st.session_state.top_p,
                    "max_tokens": st.session_state.max_tokens,
                    "frequency_penalty": st.session_state.frequency_penalty,
                    "presence_penalty": st.session_state.presence_penalty
                }
            )

            if engine_initial_state_data:  # 如果是从存档加载
                st.session_state.narrative_history_display = []  # 清空UI显示历史
                # 如果叙事引擎的对话历史不为空，则重建UI显示历史
                if st.session_state.narrative_engine.conversation_history:
                    for msg in st.session_state.narrative_engine.conversation_history:
                        role_map = {"assistant": "AI", "user": "User"}  # 角色映射
                        ui_role = role_map.get(msg["role"])
                        if ui_role:
                            text_to_display = msg["content"]
                            if msg["role"] == "assistant":  # AI的回复可能包含JSON元数据块
                                narrative_only, _ = utils.extract_narrative_and_metadata(msg["content"])
                                text_to_display = narrative_only if narrative_only else msg["content"]
                            st.session_state.narrative_history_display.append((ui_role, text_to_display))
                st.success("✅ 故事进度已成功加载！")
            else:  # 如果是新游戏
                initial_narrative = st.session_state.narrative_engine.start_session()  # 启动叙事会话
                if not initial_narrative or initial_narrative.startswith("系统错误"):
                    st.error(f"互动叙事会话初始化失败: {initial_narrative}")
                    st.session_state.app_stage = "config_novel"
                    st.stop()
                else:
                    st.session_state.narrative_history_display = [("AI", initial_narrative)]  # 将开篇叙事加入UI历史
                    st.success("✅ 叙事引擎初始化完毕，欢迎进入故事世界！")

            st.session_state.app_stage = "narrating"  # 进入叙事阶段
            st.session_state.engine_state_to_load = None  # 使用后清除待加载状态
            st.rerun()
        except Exception as e:
            st.error(f"初始化叙事引擎时发生错误: {e}")
            import traceback

            st.error(f"{traceback.format_exc()}")
            st.session_state.app_stage = "config_novel"

# --- 阶段 3: 叙事 ---
if st.session_state.app_stage == "narrating":
    st.markdown('<h2 class="sub-title">📖 故事时间</h2>', unsafe_allow_html=True)

    # 在叙事阶段的顶部提供操作按钮
    col_save, col_history, col_reset = st.columns([1, 1, 1])

    with col_save:
        if st.button("💾 保存当前进度", key="save_game_narrating_btn", help="保存当前故事进度"):
            if st.session_state.narrative_engine and st.session_state.novel_specific_data_dir_ui:
                try:
                    # 获取叙事引擎的当前状态以供保存
                    engine_state_to_save = st.session_state.narrative_engine.get_state_for_saving()
                    # 创建应用配置快照
                    app_config_snapshot = {
                        "selected_analysis_model": st.session_state.selected_analysis_model,
                        "selected_writing_model_local": st.session_state.selected_writing_model_local,
                        "writing_model_source": st.session_state.writing_model_source,
                        "writing_api_url": st.session_state.writing_api_url,
                        "writing_api_model_name": st.session_state.writing_api_model_name,
                        "ollama_api_url_config": st.session_state.ollama_api_url_config,
                        "novel_specific_data_dir_ui": st.session_state.novel_specific_data_dir_ui,
                        "chapters_data_path_ui": st.session_state.chapters_data_path_ui,
                        "final_analysis_path_ui": st.session_state.final_analysis_path_ui,
                        "current_novel_path": st.session_state.current_novel_path,
                        # 保存叙事引擎配置
                        "initial_context_chapters": st.session_state.initial_context_chapters,
                        "narrative_window_chapter_before": st.session_state.narrative_window_chapter_before,
                        "narrative_window_chapter_after": st.session_state.narrative_window_chapter_after,
                        "divergence_threshold": st.session_state.divergence_threshold,
                        # 保存模型参数
                        "temperature": st.session_state.temperature,
                        "top_p": st.session_state.top_p,
                        "max_tokens": st.session_state.max_tokens,
                        "frequency_penalty": st.session_state.frequency_penalty,
                        "presence_penalty": st.session_state.presence_penalty,
                    }
                    # 组合完整的存档数据
                    full_save_data = {
                        "app_config_snapshot": app_config_snapshot,
                        "narrative_engine_internal_state": engine_state_to_save
                    }
                    # 确定存档文件路径
                    save_file_path = os.path.join(st.session_state.novel_specific_data_dir_ui,
                                                  STORY_SAVE_STATE_FILENAME)
                    utils.write_json_file(full_save_data, save_file_path)  # 写入存档文件

                    # 同时保存到历史对话
                    history_path = save_current_conversation()

                    st.success(f"故事进度已保存！")
                except Exception as e:
                    st.error(f"保存故事进度失败: {e}")

    with col_history:
        if st.button("📜 历史对话", key="show_history_narrating_btn", help="查看历史对话记录"):
            st.session_state.show_history_panel = not st.session_state.show_history_panel
            st.rerun()

    with col_reset:
        if st.button("🔄 重新开始", key="reset_narrating_btn", help="重置当前故事，返回配置页面"):
            reset_for_new_journey()
            st.rerun()

    # 主聊天区域
    chat_container = st.container()  # 用于聊天消息的容器

    with chat_container:
        # 确保叙事历史已填充 (例如，在加载后没有完全刷新UI时)
        if not st.session_state.narrative_history_display and \
                st.session_state.narrative_engine and \
                st.session_state.narrative_engine.conversation_history:
            # 尝试从引擎的对话历史中重新填充UI显示历史
            for msg in st.session_state.narrative_engine.conversation_history:
                role_map = {"assistant": "AI", "user": "User"}
                ui_role = role_map.get(msg["role"])
                if ui_role:
                    text_to_display = msg["content"]
                    if msg["role"] == "assistant":
                        narrative_only, _ = utils.extract_narrative_and_metadata(msg["content"])
                        text_to_display = narrative_only if narrative_only else msg["content"]
                    st.session_state.narrative_history_display.append((ui_role, text_to_display))

        # 显示叙事历史
        for source, text in st.session_state.narrative_history_display:
            avatar = "🤖" if source == "AI" else "🧑‍💻"  # 根据来源选择头像

            # 使用自定义样式的消息容器
            message_class = "ai-message" if source == "AI" else "user-message"
            st.markdown(
                f'<div class="message-container {message_class}"><strong>{avatar} {source}:</strong><br>{text}</div>',
                unsafe_allow_html=True)

    # 用户输入区域
    with st.container():
        st.markdown('<div class="input-area">', unsafe_allow_html=True)

        # 添加键盘快捷键支持的JavaScript
        if st.session_state.enable_keyboard_shortcuts:
            st.markdown("""
            <script>
            // 等待页面加载完成
            document.addEventListener('DOMContentLoaded', function() {
                // 监听键盘事件
                document.addEventListener('keydown', function(e) {
                    // 获取文本区域元素
                    const textareas = document.querySelectorAll('textarea');
                    const userInputTextarea = Array.from(textareas).find(t => t.placeholder && t.placeholder.includes('输入您想在故事中的行动或对话'));

                    if (userInputTextarea && userInputTextarea === document.activeElement) {
                        // Enter键发送消息
                        if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                            e.preventDefault();
                            // 查找发送按钮并点击
                            const buttons = document.querySelectorAll('button');
                            const sendButton = Array.from(buttons).find(b => b.innerText === '发送');
                            if (sendButton) {
                                sendButton.click();
                            }
                        }
                        // Ctrl+Enter或Shift+Enter换行
                        else if (e.key === 'Enter' && (e.ctrlKey || e.shiftKey)) {
                            // 默认行为是换行，不需要额外处理
                        }
                    }
                });
            });
            </script>
            """, unsafe_allow_html=True)

        user_input = st.text_area("您的行动或对话:", key="user_input", height=100,
                                  placeholder="输入您想在故事中的行动或对话...")

        col1, col2 = st.columns([1, 5])

        with col1:
            st.markdown('<div class="primary-button">', unsafe_allow_html=True)
            send_button = st.button("发送", key="send_btn")
            st.markdown('</div>', unsafe_allow_html=True)

        if send_button:
            if user_input and st.session_state.narrative_engine:
                # 添加用户输入到UI历史
                st.session_state.narrative_history_display.append(("User", user_input))

                # 获取AI响应
                with st.spinner("AI正在思考..."):
                    ai_response = st.session_state.narrative_engine.process_user_input(
                        user_input)  # process_user_input in narrative_engine

                # 从AI响应中提取纯叙事部分（去除可能的JSON元数据）
                narrative_only, _ = utils.extract_narrative_and_metadata(ai_response)
                display_text = narrative_only if narrative_only else ai_response

                # 如果启用了打字动画，则使用动画效果显示
                if st.session_state.show_typing_animation:
                    # 创建一个临时容器用于动画
                    typing_container = st.empty()

                    # 计算每个字符的显示时间
                    char_delay = 1.0 / st.session_state.typing_speed

                    # 逐字显示文本
                    for i in range(1, len(display_text) + 1):
                        partial_text = display_text[:i]
                        typing_container.markdown(
                            f'<div class="message-container ai-message"><strong>🤖 AI:</strong><br>{partial_text}</div>',
                            unsafe_allow_html=True
                        )
                        time.sleep(char_delay)

                    # 清空临时容器
                    typing_container.empty()

                # 添加AI响应到UI历史
                st.session_state.narrative_history_display.append(("AI", display_text))

                # 清空输入框并重新运行以更新UI
                st.session_state.user_input = ""  # This will clear the text_area
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    # 主程序入口点
    pass