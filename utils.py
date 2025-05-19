# utils.py
# 该文件包含项目中通用的辅助函数。

import json
import hashlib # 用于MD5哈希计算
import re # 正则表达式库
import os
from typing import Any, List, Dict, Optional, Tuple


# --- 文件操作 ---
def read_file_content(file_path: str) -> Optional[str]:
    """
    读取文本文件的全部内容。

    Args:
        file_path: 文件路径。

    Returns:
        文件内容字符串，如果文件未找到或读取错误则返回None。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"错误：文件未找到 {file_path}")
        return None
    except Exception as e:
        print(f"读取文件错误 {file_path}: {e}")
        return None


def write_json_file(data: Any, file_path: str) -> bool:
    """
    将Python数据写入JSON文件。

    Args:
        data: 要写入的Python数据 (例如字典或列表)。
        file_path: 目标JSON文件路径。

    Returns:
        如果写入成功返回True，否则返回False。
    """
    try:
        # 确保目标目录存在
        dir_name = os.path.dirname(file_path)
        if dir_name:  # 检查目录名是否为空 (例如，对于当前目录下的文件)
            os.makedirs(dir_name, exist_ok=True) # exist_ok=True 表示如果目录已存在则不报错

        with open(file_path, "w", encoding="utf-8") as f:
            # ensure_ascii=False 确保中文字符能正确写入，indent=2 使JSON文件可读性更好
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"成功将JSON写入 {file_path}")
        return True
    except Exception as e:
        print(f"写入JSON错误 {file_path}: {e}")
        return False


def read_json_file(file_path: str) -> Optional[Any]:
    """
    从JSON文件读取数据。

    Args:
        file_path: JSON文件路径。

    Returns:
        解析后的Python数据，如果文件未找到、解码错误或读取错误则返回None。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误：JSON文件未找到 {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"错误：无法解码JSON来自 {file_path}。文件可能已损坏或不是有效的JSON。")
        return None
    except Exception as e:
        print(f"读取JSON文件错误 {file_path}: {e}")
        return None


# --- 文本处理 ---
def split_text_into_chapters(text: str, chapter_regex: str) -> List[Dict[str, Any]]:
    """
    根据正则表达式将小说文本分割成章节。

    Args:
        text: 完整的小说文本。
        chapter_regex: 用于匹配章节标题的正则表达式。

    Returns:
        一个包含章节信息的字典列表，每个字典包含 "chapter_number", "title", "content"。
    """
    chapters = []
    # 查找所有章节标记 (标题) 及其开始位置
    matches = list(re.finditer(chapter_regex, text, re.MULTILINE)) # re.MULTILINE 使^和$匹配每行的开始和结束

    if not matches: # 如果没有找到任何章节标记
        print("警告：未使用提供的正则表达式找到章节标记。将整个文本视为单个章节。")
        return [{
            "chapter_number": 1,
            "title": "全文内容",  # 标题设为“全文内容”
            "content": text.strip()
        }]

    # 遍历匹配到的章节标记，提取章节内容
    for i, match in enumerate(matches):
        start_pos = match.start() # 当前章节标题的开始位置
        title = match.group(0).strip()  # 整个匹配项作为标题

        # 内容从当前标题的结束位置到下一个标题的开始位置
        # 如果是最后一个章节，则到文本末尾
        content_start_pos = match.end()
        if i + 1 < len(matches): # 如果不是最后一个匹配项
            content_end_pos = matches[i + 1].start()
        else: # 如果是最后一个匹配项
            content_end_pos = len(text)

        content = text[content_start_pos:content_end_pos].strip() # 提取并去除首尾空白

        chapters.append({
            "chapter_number": i + 1, # 章节号从1开始
            "title": title,
            "content": content
        })

    # 处理第一个章节标记之前的内容 (例如，序言)
    if matches and matches[0].start() > 0:
        preface_content = text[:matches[0].start()].strip()
        if preface_content:
            # 将序言内容作为第0章或特殊章节添加
            chapters.insert(0, {
                "chapter_number": 0,  # 或者使用特殊键如 "preface_number"
                "title": "序言/前言",
                "content": preface_content
            })
            # 如果添加了序言作为第0章，则重新编号后续章节
            for j in range(1, len(chapters)):
                chapters[j]["chapter_number"] = j
            print("检测到并添加了序言内容。")

    return chapters


def extract_narrative_and_metadata(full_text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    从LLM的完整响应中提取叙事文本和JSON元数据块。
    元数据期望被 [NARRATIVE_METADATA_JSON_START] 和 [NARRATIVE_METADATA_JSON_END] 标记包裹。

    Args:
        full_text: LLM返回的完整文本字符串。

    Returns:
        一个元组 (narrative_text, metadata_dict):
        - narrative_text: 提取的叙事文本。
        - metadata_dict: 解析后的元数据字典，如果未找到或解析失败则为None。
    """
    metadata_start_tag = "[NARRATIVE_METADATA_JSON_START]"
    metadata_end_tag = "[NARRATIVE_METADATA_JSON_END]"

    start_index = full_text.find(metadata_start_tag) # 查找开始标记
    end_index = full_text.rfind(metadata_end_tag)  # 使用rfind查找结束标记的最后一次出现，以处理可能的嵌套问题（尽管不期望）

    narrative_text = full_text  # 默认情况下，如果未找到标记，则整个文本都是叙事
    metadata_dict = None

    if start_index != -1 and end_index != -1 and start_index < end_index: # 如果标记存在且顺序正确
        # 提取JSON字符串部分
        json_str_start = start_index + len(metadata_start_tag)
        json_str = full_text[json_str_start:end_index].strip()

        # 叙事文本是开始标记之前的部分
        narrative_text = full_text[:start_index].strip()

        # (可选) 检查元数据结束标记之后是否还有文本
        text_after_metadata = full_text[end_index + len(metadata_end_tag):].strip()
        if text_after_metadata:
            print(f"警告：在元数据结束标记后发现内容: '{text_after_metadata[:100]}...'")
            # 此处可以决定如何处理这部分文本：附加到叙事、记录日志或忽略。
            # 目前假设主要叙事在元数据之前。

        try:
            metadata_dict = json.loads(json_str) # 尝试解析JSON字符串
        except json.JSONDecodeError as e:
            print(f"错误：解码元数据JSON时出错: {e}\nJSON 字符串是: {json_str}")
            # 如果JSON解析失败，metadata_dict 保持为None，narrative_text 已设置为标记前的文本。
            # 返回我们能抢救出的叙事部分。
            pass  # metadata_dict 将为 None
    else:
        # 未找到标记或标记顺序错误，假设没有按特殊格式提供元数据
        print("警告：未在LLM响应中找到预期的元数据标记。")
        pass

    return narrative_text, metadata_dict

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除或替换不适用于文件系统路径的字符。
    Args:
        filename: 原始文件名。
    Returns:
        清理后的文件名。
    """
    # 移除或替换常见非法字符，例如 / \ : * ? " < > |
    # 这是一个基本实现，可以根据需要扩展
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # 也可以移除路径分隔符，以防万一
    sanitized = sanitized.replace(os.sep, "_")
    # 移除可能导致问题的首尾空格
    sanitized = sanitized.strip()
    # 防止文件名过长（某些文件系统有限制）
    max_len = 200 # 设定一个合理的最大长度
    if len(sanitized) > max_len:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:max_len - len(ext)] + ext
    return sanitized


# --- 哈希计算 ---
def calculate_md5(file_path: str) -> Optional[str]:
    """
    计算文件的MD5校验和。

    Args:
        file_path: 文件路径。

    Returns:
        文件的MD5哈希值 (十六进制字符串)，如果文件未找到或计算错误则返回None。
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f: # 以二进制读取模式打开文件
            for chunk in iter(lambda: f.read(4096), b""): # 分块读取以处理大文件
                hash_md5.update(chunk)
        return hash_md5.hexdigest() # 返回十六进制摘要
    except FileNotFoundError:
        print(f"错误：文件未找到 {file_path} 以计算MD5。")
        return None
    except Exception as e:
        print(f"计算MD5错误 {file_path}: {e}")
        return None


# --- 用户交互 (简单的命令行界面) ---
# 这些函数主要用于早期开发或非Streamlit环境下的测试。
def get_user_input(prompt_message: str) -> str:
    """通过命令行获取用户输入。"""
    return input(prompt_message).strip()


def display_narrative(text: str, source: str = "AI"):
    """向用户显示AI生成的叙事或用户行动。"""
    if source.lower() == "user":
        print(f"\n> 你决定: {text}")
    else:
        print("\n--- 故事继续 ---")
        print(text)
    print("----------------")


def display_options(options: List[str]) -> Optional[int]:
    """向用户显示选项列表并获取其选择。"""
    if not options:
        return None
    print("\n--- 请选择一个行动 ---")
    for i, option in enumerate(options):
        print(f"{i + 1}. {option}")
    print("----------------------")
    while True:
        try:
            choice = get_user_input("输入你的选择 (数字): ")
            choice_num = int(choice)
            if 1 <= choice_num <= len(options):
                return choice_num - 1  # 返回基于0的索引
            else:
                print(f"无效选择。请输入 1 到 {len(options)} 之间的数字。")
        except ValueError:
            print("无效输入。请输入一个数字。")


# --- 辅助函数：数字转换 (示例) ---
def chinese_to_arabic_number(chinese_num_str: str) -> Optional[int]:
    """
    一个非常简化的中文章节数字到阿拉伯数字的转换器。
    这是一个占位符，通用场景需要更健壮的实现。
    """
    # 这是一个非常基础的示例，实际实现会更复杂。
    mapping_simple_digits = { # 简单个位数映射
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '零': 0
    }
    # 这个示例主要处理简单的个位数或直接的阿拉伯数字字符串。
    # 对于像 "二十三", "一百零五" 这样的数字，需要一个完整的解析器。

    # 尝试直接转换（针对 "1", "23" 等情况）
    try:
        return int(chinese_num_str)
    except ValueError:
        # 如果直接转换失败，尝试简单映射 (主要针对单个中文字符)
        if len(chinese_num_str) == 1 and chinese_num_str in mapping_simple_digits:
            return mapping_simple_digits[chinese_num_str]
        # 对于更复杂的中文数字（如 "十章", "百章" 等），可以扩展此处的逻辑
        # 例如，可以添加对 "十", "百", "千", "万" 的处理
        # 但这超出了当前这个简单辅助函数的范围。
        print(f"警告：无法将中文数字 '{chinese_num_str}' 转换为阿拉伯数字。此功能需要更完善的实现。")
        return None


if __name__ == "__main__":
    # 主程序块，用于测试utils.py中的函数
    print("测试 utils.py...")

    # 创建测试用数据目录
    test_data_dir = "test_utils_data"
    if not os.path.exists(test_data_dir):
        os.makedirs(test_data_dir)

    test_json_path = os.path.join(test_data_dir, "test.json")
    test_txt_path = os.path.join(test_data_dir, "test.txt")

    # 测试JSON读写
    sample_json_data = {"name": "测试小说", "version": 1.0, "chapters": ["介绍", "高潮"]}
    write_json_file(sample_json_data, test_json_path)
    loaded_json_data = read_json_file(test_json_path)
    assert loaded_json_data == sample_json_data, "JSON 读/写 失败"
    print(f"JSON 读/写 测试通过。数据: {loaded_json_data}")

    # 测试文本文件读取
    sample_text_content = "这是一个测试文件。\n它有多行。"
    with open(test_txt_path, "w", encoding="utf-8") as f:
        f.write(sample_text_content)
    loaded_text_content = read_file_content(test_txt_path)
    assert loaded_text_content == sample_text_content, "文本文件读取失败"
    print(f"文本文件读取测试通过。内容:\n{loaded_text_content}")

    # 测试MD5计算
    md5_hash = calculate_md5(test_txt_path)
    print(f"MD5 of {test_txt_path}: {md5_hash}")
    assert md5_hash is not None, "MD5 计算失败"

    # 测试章节分割
    novel_text_simple = """
    序言部分。
    这里是一些序言。
    第一章 开始
    第一章的内容。
    更多内容。
    第二章 中间
    第二章的内容。
    就是这样。
    """
    # 使用config.py中的正则表达式或类似的进行测试
    # 此处直接使用config中定义的，如果config.py在此测试环境中不可直接导入，
    # 则应在此处复制该正则表达式。假设config.py可导入。
    try:
        from config import CHAPTER_SPLIT_REGEX as test_chapter_regex_from_config
    except ImportError:
        print("警告: 无法从config导入CHAPTER_SPLIT_REGEX，将使用本地定义的测试正则。")
        test_chapter_regex_from_config = r"^\s*第[一二三四五六七八九十百千万零\d]+章.*$|^Chapter\s+\w+.*|^\s*章节标题示例\s*\d+.*"


    print("\n测试章节分割 (简单):")
    chapters_simple = split_text_into_chapters(novel_text_simple, test_chapter_regex_from_config)
    for ch in chapters_simple:
        print(f"  章节号: {ch['chapter_number']}, 标题: '{ch['title']}', 内容长度: {len(ch['content'])}")
    # 期望: 序言 (章节0), 第1章, 第2章
    assert len(chapters_simple) == 3, f"简单章节分割失败，期望3个部分，得到{len(chapters_simple)}"
    assert chapters_simple[0]['title'] == "序言/前言", "序言标题不匹配"
    assert chapters_simple[1]['title'] == "第一章 开始", "简单章节标题不匹配"

    print("\n测试元数据提取:")
    test_llm_output_with_meta = """这是故事的叙述部分。主角做了一些事情。
然后情节继续发展。
[NARRATIVE_METADATA_JSON_START]
{
  "protagonist_action_summary": "主角探索了森林",
  "event_time_readable_context": "次日下午",
  "immediate_consequences_and_observations": ["发现了一个秘密路径"],
  "character_state_changes": {"主角": {"mood": "好奇"}},
  "item_changes": {},
  "world_state_changes": [],
  "divergence_from_original_plot": {"level": "轻微", "description": "比原著早一天发现路径"},
  "current_chapter_progression_hint": "接近第一章末尾"
}
[NARRATIVE_METADATA_JSON_END]
一些可能在元数据标记后的意外文本。
    """
    narrative, metadata = extract_narrative_and_metadata(test_llm_output_with_meta)
    print(f"提取的叙事: '{narrative}'")
    print(f"提取的元数据: {json.dumps(metadata, ensure_ascii=False, indent=2)}")
    assert narrative.strip() == "这是故事的叙述部分。主角做了一些事情。\n然后情节继续发展。", "叙事提取不正确"
    assert metadata is not None and metadata["protagonist_action_summary"] == "主角探索了森林", "元数据提取不正确"

    test_llm_output_no_meta = "这只是纯粹的叙事，没有元数据标记。"
    narrative_no_meta, metadata_no_meta = extract_narrative_and_metadata(test_llm_output_no_meta)
    print(f"无元数据 - 叙事: '{narrative_no_meta}'")
    print(f"无元数据 - 元数据: {metadata_no_meta}")
    assert narrative_no_meta == test_llm_output_no_meta, "无元数据时叙事提取不正确"
    assert metadata_no_meta is None, "无元数据时元数据应为None"

    test_llm_output_bad_json = """叙事部分。
[NARRATIVE_METADATA_JSON_START]
{
  "key": "value",
  "broken": "json,
}
[NARRATIVE_METADATA_JSON_END]
    """
    narrative_bad_json, metadata_bad_json = extract_narrative_and_metadata(test_llm_output_bad_json)
    print(f"错误JSON - 叙事: '{narrative_bad_json}'")
    print(f"错误JSON - 元数据: {metadata_bad_json}")
    assert narrative_bad_json.strip() == "叙事部分。", "错误JSON时叙事提取不正确"
    assert metadata_bad_json is None, "错误JSON时元数据应为None"

    print("\n测试 sanitize_filename:")
    test_filenames = {
        "my novel: chapter 1?.txt": "my novel_ chapter 1_.txt",
        "  leading and trailing spaces  ": "leading and trailing spaces",
        "path/to/file.name": "path_to_file.name",
        "a"*250 + ".longextension": "a"*(200-len(".longextension")) + ".longextension"
    }
    for original, expected in test_filenames.items():
        sanitized = sanitize_filename(original)
        print(f"Sanitizing '{original}' -> '{sanitized}' (Expected: '{expected}')")
        assert sanitized == expected, f"Sanitize filename failed for '{original}'"

    print("\nutils.py 测试完成。")

    # 清理测试目录和文件
    # import shutil
    # if os.path.exists(test_data_dir):
    #     shutil.rmtree(test_data_dir)
    #     print(f"测试目录 {test_data_dir} 已删除。")