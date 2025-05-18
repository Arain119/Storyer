# api_config.py
# 该文件处理API配置的加载和保存。

import os
import json
from typing import Dict, Any, Optional

# 配置文件路径
CONFIG_FILE_PATH = 'data/api_config.json'

def load_api_config() -> Dict[str, Any]:
    """
    加载API配置。
    
    Returns:
        包含API配置的字典。如果配置文件不存在，则返回默认配置。
    """
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)
    
    # 如果配置文件存在，则加载它
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载API配置时出错: {str(e)}")
    
    # 返回默认配置
    return {
        "use_online_api": False,
        "ollama_api_url": "http://127.0.0.1:11434",
        "selected_ollama_model": "gemma3:12b-it-q8_0",
        "online_api_url": "",
        "online_api_model": "",
        "online_api_key": "",
        "analysis_model_name": "llama3",
        "analysis_custom_type": "ollama",
        "analysis_custom_ollama_model": "",
        "analysis_custom_online_model": "",
        "writing_model_name": "llama3",
        "writing_custom_type": "ollama",
        "writing_custom_ollama_model": "",
        "writing_custom_online_model": "",
        "available_ollama_models": ["gemma3:12b-it-q8_0", "llama3:8b-instruct-q8_0", "mistral:7b-instruct-v0.2-q8_0", "qwen:14b-chat-q8_0"]
    }

def save_api_config(config: Dict[str, Any]) -> bool:
    """
    保存API配置。
    
    Args:
        config: 要保存的配置字典。
        
    Returns:
        如果保存成功则返回True，否则返回False。
    """
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)
    
    try:
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存API配置时出错: {str(e)}")
        return False

def get_active_client_config() -> Dict[str, Any]:
    """
    获取当前激活的客户端配置。
    
    Returns:
        包含客户端配置的字典。
    """
    config = load_api_config()
    
    if config.get("use_online_api", False):
        return {
            "client_type": "online_api",
            "api_url": config.get("online_api_url", ""),
            "api_key": config.get("online_api_key", ""),
            "model_name": config.get("online_api_model", "")
        }
    else:
        return {
            "client_type": "ollama",
            "api_url": config.get("ollama_api_url", "http://127.0.0.1:11434"),
            "model_name": config.get("selected_ollama_model", "gemma3:12b-it-q8_0")
        }
