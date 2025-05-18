# generic_online_api_client.py
# 该文件实现了通用的在线API客户端。

import requests
import json
from typing import List, Dict, Any, Optional

# 导入LLM客户端接口的抽象基类
from llm_client_interface import LLMClientInterface

class GenericOnlineAPIClient(LLMClientInterface):
    """通用在线API客户端实现。"""
    
    def __init__(self, api_url: str, api_key: str, default_model: str):
        """
        初始化通用在线API客户端。
        
        Args:
            api_url: API端点URL。
            api_key: API密钥。
            default_model: 默认模型名称。
        """
        self._api_url = api_url
        self._api_key = api_key
        self._default_model = default_model
    
    @property
    def default_model(self) -> str:
        """获取默认模型名称。"""
        return self._default_model
    
    @property
    def client_type(self) -> str:
        """返回客户端类型。"""
        return "online_api"
    
    def generate_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        expect_json_in_content: bool = False,
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        从在线API生成聊天完成。
        
        Args:
            model: 用于生成的模型名称。
            messages: 消息字典列表。
            stream: 是否流式传输响应。
            expect_json_in_content: 提示响应内容期望为JSON字符串。
            timeout: API调用的超时时间（秒）。
            
        Returns:
            一个包含API响应的字典，如果发生错误则返回None。
        """
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}"
            }
            
            payload = {
                "model": model or self._default_model,
                "messages": messages,
                "stream": stream
            }
            
            if expect_json_in_content:
                payload["response_format"] = {"type": "json_object"}
            
            response = requests.post(
                self._api_url,
                headers=headers,
                json=payload,
                timeout=timeout or 60
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 标准化响应格式
                if "choices" in result and len(result["choices"]) > 0:
                    return {
                        "message": result["choices"][0]["message"]
                    }
                
                return result
            else:
                print(f"API错误: {response.status_code} - {response.text}")
                return None
        
        except Exception as e:
            print(f"生成聊天完成时出错: {str(e)}")
            return None
    
    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        列出可用的模型。
        
        Returns:
            包含默认模型的列表，如果发生错误则返回None。
        """
        # 在线API客户端通常不支持列出模型，返回默认模型
        return [{"name": self._default_model}]
