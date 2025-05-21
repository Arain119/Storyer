# 历史对话管理模块
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

import utils

# 历史对话保存目录
HISTORY_DIR = "history"

def load_history_conversations(data_dir: str) -> List[Dict[str, Any]]:
    """
    加载所有历史对话
    
    Args:
        data_dir: 数据目录路径
        
    Returns:
        历史对话列表
    """
    history_dir = os.path.join(data_dir, HISTORY_DIR)
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
            print(f"加载历史对话文件 {file} 失败: {e}")

    # 按时间倒序排序
    history_list.sort(key=lambda x: x["metadata"].get("timestamp", 0), reverse=True)
    return history_list

def save_current_conversation(data_dir: str, narrative_engine, novel_name: str, app_config: Dict[str, Any], original_filename: str = None) -> Optional[str]:
    """
    保存当前对话到历史记录
    
    Args:
        data_dir: 数据目录路径
        narrative_engine: 叙事引擎实例
        novel_name: 小说名称
        app_config: 应用配置
        original_filename: 原始上传文件名，用作历史对话标题
        
    Returns:
        保存的文件路径，如果保存失败则返回None
    """
    if not narrative_engine or not novel_name:
        return None

    try:
        # 确保历史目录存在
        history_dir = os.path.join(data_dir, HISTORY_DIR)
        os.makedirs(history_dir, exist_ok=True)

        # 获取叙事引擎的当前状态
        engine_state = narrative_engine.get_state_for_saving()

        # 提取对话内容的摘要作为备用标题
        conversation_summary = "无对话内容"
        if narrative_engine.conversation_history:
            # 使用最后一条AI消息作为摘要
            for msg in reversed(narrative_engine.conversation_history):
                if msg["role"] == "assistant":
                    # 截取前30个字符作为摘要
                    conversation_summary = msg["content"][:30] + ("..." if len(msg["content"]) > 30 else "")
                    break

        # 创建元数据
        timestamp = int(time.time())
        formatted_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        # 如果提供了原始文件名，则使用它作为标题
        title = original_filename if original_filename else conversation_summary

        metadata = {
            "novel_name": novel_name,
            "title": title,
            "timestamp": timestamp,
            "formatted_time": formatted_time,
            "message_count": len(narrative_engine.conversation_history)
        }

        # 组合完整的存档数据
        history_data = {
            "metadata": metadata,
            "app_config": app_config,
            "engine_state": engine_state
        }

        # 生成文件名
        filename = f"history_{timestamp}_{utils.sanitize_filename(novel_name)}.json"
        file_path = os.path.join(history_dir, filename)

        # 保存到文件
        utils.write_json_file(history_data, file_path)

        return file_path

    except Exception as e:
        print(f"保存历史对话失败: {e}")
        return None

def delete_history_conversation(file_path: str) -> bool:
    """
    删除指定的历史对话
    
    Args:
        file_path: 历史对话文件路径
        
    Returns:
        是否删除成功
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        print(f"删除历史对话失败: {e}")
        return False

def load_conversation_from_history(history_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    从历史记录加载对话
    
    Args:
        history_item: 历史对话数据
        
    Returns:
        加载的应用配置和引擎状态
    """
    result = {
        "success": False,
        "app_config": {},
        "engine_state": None,
        "error": None
    }
    
    try:
        if "app_config" not in history_item or "engine_state" not in history_item:
            result["error"] = "历史对话数据格式不正确"
            return result

        # 从历史记录恢复应用配置和引擎状态
        result["app_config"] = history_item["app_config"]
        result["engine_state"] = history_item["engine_state"]
        result["success"] = True
        
        return result
    except Exception as e:
        result["error"] = f"加载历史对话失败: {e}"
        return result
