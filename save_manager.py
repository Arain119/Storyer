# 存档管理模块
import os
import json
import time
from typing import Dict, List, Any, Optional

import utils

# 存档保存目录
SAVES_DIR = "saves"

def get_saves_list(novel_data_dir: str) -> List[Dict[str, Any]]:
    """
    获取指定小说的存档列表
    
    Args:
        novel_data_dir: 小说数据目录路径
        
    Returns:
        存档列表
    """
    saves_dir = os.path.join(novel_data_dir, SAVES_DIR)
    if not os.path.exists(saves_dir):
        os.makedirs(saves_dir, exist_ok=True)
        return []

    save_files = [f for f in os.listdir(saves_dir) if f.endswith('.json')]
    saves_list = []

    for file in save_files:
        try:
            file_path = os.path.join(saves_dir, file)
            save_data = utils.read_json_file(file_path)
            if save_data:
                # 提取存档元数据
                timestamp = int(file.split('_')[1].split('.')[0]) if '_' in file else 0
                formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
                
                # 从会话记忆中提取当前章节和进度信息
                chapter_info = "未知章节"
                progress_info = "未知进度"
                
                if "session_memory" in save_data and save_data["session_memory"]:
                    last_memory = save_data["session_memory"][-1]
                    chapter_info = last_memory.get("current_chapter_progression_hint", "未知章节")
                    
                    # 提取最后一段叙事作为进度信息
                    narrative = last_memory.get("generated_narrative_segment", "")
                    progress_info = narrative[:50] + "..." if narrative else "无进度信息"
                
                # 构建存档摘要
                save_summary = {
                    "file_path": file_path,
                    "timestamp": timestamp,
                    "formatted_time": formatted_time,
                    "chapter_info": chapter_info,
                    "progress_info": progress_info
                }
                
                saves_list.append(save_summary)
        except Exception as e:
            print(f"加载存档文件 {file} 失败: {e}")

    # 按时间倒序排序
    saves_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return saves_list

def save_game_state(narrative_engine, novel_data_dir: str) -> Optional[str]:
    """
    保存游戏状态
    
    Args:
        narrative_engine: 叙事引擎实例
        novel_data_dir: 小说数据目录路径
        
    Returns:
        保存的文件路径，如果保存失败则返回None
    """
    if not narrative_engine:
        return None

    try:
        # 使用叙事引擎的保存方法
        save_path = narrative_engine.save_state_to_file()
        return save_path
    except Exception as e:
        print(f"保存游戏状态失败: {e}")
        return None

def load_game_state(file_path: str) -> Optional[Dict[str, Any]]:
    """
    加载游戏状态
    
    Args:
        file_path: 存档文件路径
        
    Returns:
        加载的游戏状态，如果加载失败则返回None
    """
    try:
        if os.path.exists(file_path):
            save_data = utils.read_json_file(file_path)
            return save_data
        return None
    except Exception as e:
        print(f"加载游戏状态失败: {e}")
        return None

def delete_save(file_path: str) -> bool:
    """
    删除指定的存档
    
    Args:
        file_path: 存档文件路径
        
    Returns:
        是否删除成功
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        print(f"删除存档失败: {e}")
        return False
