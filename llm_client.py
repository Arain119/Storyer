# LLM客户端
import requests
import json
from typing import List, Dict, Any, Optional

class LLMClient:
    """LLM客户端类，负责与LLM API交互。"""

    def __init__(self, client_type: str, api_url: str, model_name: str = None, api_key: str = None):
        """
        初始化LLM客户端。

        Args:
            client_type: 客户端类型，"ollama"或"online"。
            api_url: API URL。
            model_name: 模型名称。
            api_key: API密钥（仅在线API需要）。
        """
        self.client_type = client_type
        self.api_url = api_url
        self.model_name = model_name
        self.api_key = api_key

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """
        发送聊天完成请求。

        Args:
            messages: 消息列表。
            **kwargs: 其他参数。

        Returns:
            响应文本，如果请求失败则返回None。
        """
        try:
            if self.client_type == "ollama":
                return self._ollama_chat_completion(messages, **kwargs)
            elif self.client_type == "online":
                return self._online_chat_completion(messages, **kwargs)
            else:
                print(f"不支持的客户端类型: {self.client_type}")
                return None
        except Exception as e:
            print(f"聊天完成请求失败: {str(e)}")
            return None

    def _ollama_chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """Ollama聊天完成请求"""
        if not self.api_url or not self.model_name:
            print("Ollama API URL或模型名称未设置")
            return None

        try:
            # 构建请求URL
            url = f"{self.api_url}/api/chat"
            
            # 构建请求数据
            data = {
                "model": self.model_name,
                "messages": messages,
                "stream": False
            }
            
            # 添加其他参数
            for key, value in kwargs.items():
                data[key] = value
            
            # 发送请求
            response = requests.post(url, json=data)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("message", {}).get("content")
            else:
                print(f"Ollama API请求失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"Ollama聊天完成请求失败: {str(e)}")
            return None

    def _online_chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        """在线API聊天完成请求"""
        if not self.api_url or not self.model_name or not self.api_key:
            print("在线API URL、模型名称或API密钥未设置")
            return None

        try:
            # 构建请求头
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # 构建请求数据
            data = {
                "model": self.model_name,
                "messages": messages
            }
            
            # 添加其他参数
            for key, value in kwargs.items():
                data[key] = value
            
            # 发送请求
            response = requests.post(self.api_url, headers=headers, json=data)
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content")
            else:
                print(f"在线API请求失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"在线API聊天完成请求失败: {str(e)}")
            return None

    def get_available_models(self) -> Optional[List[str]]:
        """
        获取可用模型列表。

        Returns:
            模型列表，如果请求失败则返回None。
        """
        try:
            if self.client_type == "ollama":
                return self._get_ollama_models()
            elif self.client_type == "online":
                return self._get_online_models()
            else:
                print(f"不支持的客户端类型: {self.client_type}")
                return None
        except Exception as e:
            print(f"获取可用模型失败: {str(e)}")
            return None

    def _get_ollama_models(self) -> Optional[List[str]]:
        """获取Ollama可用模型"""
        if not self.api_url:
            print("Ollama API URL未设置")
            return None

        try:
            # 构建请求URL
            url = f"{self.api_url}/api/tags"
            
            # 发送请求
            response = requests.get(url)
            
            if response.status_code == 200:
                result = response.json()
                return [model["name"] for model in result.get("models", [])]
            else:
                print(f"获取Ollama模型列表失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"获取Ollama模型列表出错: {str(e)}")
            return None

    def _get_online_models(self) -> Optional[List[str]]:
        """获取在线API可用模型"""
        if not self.api_url or not self.api_key:
            print("在线API URL或API密钥未设置")
            return None

        try:
            # 构建请求头
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # 构建请求URL（假设API提供了模型列表端点）
            url = f"{self.api_url}/models"
            
            # 发送请求
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                return [model["id"] for model in result.get("data", [])]
            else:
                print(f"获取在线API模型列表失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"获取在线API模型列表出错: {str(e)}")
            return None
