# 参数配置管理模块
import os
import json
from typing import Dict, Any, Optional, List

import utils

# 配置文件名
CONFIG_FILENAME = "api_config.json"

def load_api_configs(data_dir: str) -> Dict[str, Any]:
    """
    加载API配置
    
    Args:
        data_dir: 数据目录路径
        
    Returns:
        API配置字典
    """
    config_path = os.path.join(data_dir, CONFIG_FILENAME)
    
    # 默认配置
    default_config = {
        "use_online_api": False,
        "ollama_api_url": "http://127.0.0.1:11434",
        "selected_ollama_model": "gemma3:12b-it-q8_0",
        "online_api_url": "",
        "online_api_model": "",
        "online_api_key": "",
        "analysis_model_name": "llama3",
        "writing_model_name": "llama3",
        "available_ollama_models": ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 65536,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "initial_context_chapters": 3,
        "window_before": 2,
        "window_after": 2,
        "divergence_threshold": 0.7
    }
    
    # 如果配置文件存在，加载它
    if os.path.exists(config_path):
        loaded_config = utils.read_json_file(config_path)
        if loaded_config:
            # 合并默认配置和加载的配置
            for key, value in loaded_config.items():
                default_config[key] = value
    else:
        # 如果配置文件不存在，创建一个新的
        utils.write_json_file(default_config, config_path)
    
    return default_config

def save_api_configs(config: Dict[str, Any], data_dir: str) -> bool:
    """
    保存API配置
    
    Args:
        config: API配置字典
        data_dir: 数据目录路径
        
    Returns:
        是否保存成功
    """
    try:
        config_path = os.path.join(data_dir, CONFIG_FILENAME)
        utils.write_json_file(config, config_path)
        return True
    except Exception as e:
        print(f"保存API配置失败: {e}")
        return False

def update_api_config(data_dir: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新API配置
    
    Args:
        data_dir: 数据目录路径
        updates: 要更新的配置项
        
    Returns:
        更新后的完整配置
    """
    # 加载当前配置
    current_config = load_api_configs(data_dir)
    
    # 更新配置
    for key, value in updates.items():
        current_config[key] = value
    
    # 保存更新后的配置
    save_api_configs(current_config, data_dir)
    
    return current_config

def get_model_params(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取模型参数
    
    Args:
        config: API配置字典
        
    Returns:
        模型参数字典
    """
    return {
        "temperature": config.get("temperature", 0.7),
        "top_p": config.get("top_p", 0.9),
        "max_tokens": config.get("max_tokens", 1024),
        "frequency_penalty": config.get("frequency_penalty", 0.0),
        "presence_penalty": config.get("presence_penalty", 0.0)
    }

def reset_api_config(data_dir: str) -> Dict[str, Any]:
    """
    重置API配置到默认值
    
    Args:
        data_dir: 数据目录路径
        
    Returns:
        重置后的配置
    """
    # 默认配置
    default_config = {
        "use_online_api": False,
        "ollama_api_url": "http://127.0.0.1:11434",
        "selected_ollama_model": "gemma3:12b-it-q8_0",
        "online_api_url": "",
        "online_api_model": "",
        "online_api_key": "",
        "analysis_model_name": "llama3",
        "writing_model_name": "llama3",
        "available_ollama_models": ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0"],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 65536,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "initial_context_chapters": 3,
        "window_before": 2,
        "window_after": 2,
        "divergence_threshold": 0.7
    }
    
    # 保存默认配置
    config_path = os.path.join(data_dir, CONFIG_FILENAME)
    utils.write_json_file(default_config, config_path)
    
    return default_config
