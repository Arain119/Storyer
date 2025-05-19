# config.py
# 该文件定义了应用程序的所有配置参数。

import os

# Ollama API 配置
# OLLAMA_API_BASE_URL: Ollama API的基础URL，默认为本地服务地址。
OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434")
# DEFAULT_OLLAMA_MODEL: 默认的Ollama模型，可被特定任务的模型覆盖。
DEFAULT_OLLAMA_MODEL = os.getenv("DEFAULT_OLLAMA_MODEL", "gemma3:12b-it-q8_0") # 通用默认模型，可以被覆盖

# 特定任务的模型配置
# DEFAULT_ANALYSIS_OLLAMA_MODEL: 默认用于分析任务的Ollama模型。
DEFAULT_ANALYSIS_OLLAMA_MODEL = os.getenv("DEFAULT_ANALYSIS_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
# DEFAULT_WRITING_OLLAMA_MODEL: 默认用于写作任务的Ollama模型。
DEFAULT_WRITING_OLLAMA_MODEL = os.getenv("DEFAULT_WRITING_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)

# 文件路径配置
# DATA_DIR: 存储所有数据文件的主目录。
DATA_DIR = "data"
# CHAPTERS_DATA_FILENAME: 存储小说章节数据的JSON文件名。
CHAPTERS_DATA_FILENAME = "chapters_data.json"
# NOVEL_ANALYSIS_IN_PROGRESS_FILENAME: 存储小说分析中间结果的JSON文件名。
NOVEL_ANALYSIS_IN_PROGRESS_FILENAME = "novel_analysis_in_progress.json"
# NOVEL_ANALYSIS_FILENAME: 存储小说最终分析结果的JSON文件名。
NOVEL_ANALYSIS_FILENAME = "novel_analysis.json"
# SESSION_MEMORY_FILENAME: 存储叙事会话记忆的JSON文件名。
SESSION_MEMORY_FILENAME = "session_memory.json"
# STORY_SAVE_STATE_FILENAME: 用于保存和恢复故事进度的文件名。
STORY_SAVE_STATE_FILENAME = "story_save_state.json"

# 小说处理配置
# CHAPTER_SPLIT_REGEX: 用于将小说文本分割成章节的正则表达式。
CHAPTER_SPLIT_REGEX = r"^\s*第[一二三四五六七八九十百千万零\d]+章.*$|^Chapter\s+\w+.*|^\s*章节标题示例\s*\d+.*"
# ANALYSIS_BATCH_SIZE: LLM分析小说时，每批处理的章节数量。推荐设为1以实现逐章分析，提高章节定位准确性。
ANALYSIS_BATCH_SIZE = 1

# 叙事引擎配置
# INITIAL_CONTEXT_CHAPTERS: 叙事引擎初始化时，提供给LLM作为初始上下文的章节数量。
INITIAL_CONTEXT_CHAPTERS = 2
# NARRATIVE_WINDOW_CHAPTER_BEFORE: 叙事时，LLM参考的当前章节之前的章节数量。设为0可避免回顾过多已发生剧情。
NARRATIVE_WINDOW_CHAPTER_BEFORE = 0
# NARRATIVE_WINDOW_CHAPTER_AFTER: 叙事时，LLM参考的当前章节之后的章节数量。设为0或1可减少未来信息泄露。
NARRATIVE_WINDOW_CHAPTER_AFTER = 1 # 可以考虑设为0，更严格控制未来信息
# DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE: 当剧情与原著的偏离程度达到此阈值时，尝试引导剧情回归。
DIVERGENCE_THRESHOLD_FOR_RECONVERGENCE = "中度" # 可选值："轻微", "中度", "显著"

# 日志配置 (可选，但有助于调试)
# LOG_LEVEL: 日志级别。
LOG_LEVEL = "INFO"
# LOG_FILE: 日志文件名。
LOG_FILE = "app.log"

# 确保数据目录存在
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
        print(f"主数据目录已创建: {DATA_DIR}")
    except OSError as e:
        print(f"错误：无法创建主数据目录 {DATA_DIR}: {e}")

# 辅助函数，用于获取特定小说数据目录下的完整文件路径
def get_novel_data_path(novel_specific_dir: str, filename: str) -> str:
    """
    拼接并返回特定小说数据目录下的文件完整路径。

    Args:
        novel_specific_dir: 特定于小说的子目录路径。
        filename: 数据文件名。

    Returns:
        完整的文件路径字符串。
    """
    return os.path.join(novel_specific_dir, filename)