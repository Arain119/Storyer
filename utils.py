# utils.py
# 该文件提供各种工具函数。

import os
import json
import hashlib
import re
from typing import Any, Dict, List, Optional, Union

def read_text_file(file_path: str) -> Optional[str]:
    """
    读取文本文件内容。
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件内容，如果读取失败则返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取文件 {file_path} 失败: {e}")
        return None

def write_text_file(file_path: str, content: str) -> bool:
    """
    写入文本文件。
    
    Args:
        file_path: 文件路径
        content: 文件内容
        
    Returns:
        是否写入成功
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"写入文件 {file_path} 失败: {e}")
        return False

def read_json_file(file_path: str) -> Optional[Any]:
    """
    读取JSON文件内容。
    
    Args:
        file_path: 文件路径
        
    Returns:
        解析后的JSON内容，如果读取或解析失败则返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取JSON文件 {file_path} 失败: {e}")
        return None

def write_json_file(content: Any, file_path: str) -> bool:
    """
    写入JSON文件。
    
    Args:
        content: 要写入的内容
        file_path: 文件路径
        
    Returns:
        是否写入成功
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"写入JSON文件 {file_path} 失败: {e}")
        return False

def calculate_md5(file_path: str) -> Optional[str]:
    """
    计算文件的MD5哈希值。
    
    Args:
        file_path: 文件路径
        
    Returns:
        MD5哈希值，如果计算失败则返回None
    """
    try:
        with open(file_path, 'rb') as f:
            md5_hash = hashlib.md5()
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        print(f"计算文件 {file_path} 的MD5哈希值失败: {e}")
        return None

def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除不安全字符。
    
    Args:
        filename: 原始文件名
        
    Returns:
        清理后的文件名
    """
    # 移除不安全字符，只保留字母、数字、下划线、连字符和点
    sanitized = re.sub(r'[^\w\-\.]', '_', filename)
    return sanitized

def split_text_into_chapters(text: str, chapter_pattern: str = r'第[一二三四五六七八九十百千万\d]+章|Chapter\s+\d+') -> List[Dict[str, Any]]:
    """
    将文本分割为章节。
    
    Args:
        text: 要分割的文本
        chapter_pattern: 章节标记的正则表达式模式
        
    Returns:
        章节列表，每个章节是一个字典，包含章节号、标题和内容
    """
    try:
        # 查找章节标记
        chapter_markers = re.findall(chapter_pattern, text)
        
        if not chapter_markers:
            # 如果没有找到章节标记，将整个文本作为一个章节
            return [{
                "chapter_number": 1,
                "title": "第1章",
                "content": text
            }]
        
        # 使用章节标记分割文本
        pattern = '|'.join(map(re.escape, chapter_markers))
        splits = re.split(f'({pattern})', text)
        
        chapters = []
        chapter_number = 0
        
        # 处理可能的序言
        if splits[0].strip() and not re.match(chapter_pattern, splits[0].strip()):
            chapters.append({
                "chapter_number": 0,
                "title": "序言",
                "content": "序言\n" + splits[0].strip()
            })
        
        # 重组章节（标题 + 内容）
        for i in range(1, len(splits), 2):
            chapter_number += 1
            title = splits[i].strip()
            
            # 获取章节内容
            content = ""
            if i + 1 < len(splits):
                content = splits[i+1]
            
            chapters.append({
                "chapter_number": chapter_number,
                "title": title,
                "content": title + "\n" + content
            })
        
        return chapters
    except Exception as e:
        print(f"分割文本为章节失败: {e}")
        return [{
            "chapter_number": 1,
            "title": "第1章",
            "content": text
        }]
