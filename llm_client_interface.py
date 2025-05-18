# llm_client_interface.py
# 该文件定义了LLM客户端实现的抽象基类 (ABC)。

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class LLMClientInterface(ABC):
    """LLM客户端实现的抽象基类。"""

    @abstractmethod
    def generate_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        expect_json_in_content: bool = False,
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        从LLM生成聊天完成。

        Args:
            model: 用于生成的模型名称。
            messages: 消息字典列表 (例如: {"role": "user", "content": "..."})。
            stream: 是否流式传输响应 (并非所有实现都完全支持)。
            expect_json_in_content: 提示响应内容期望为JSON字符串。
            timeout: API调用的超时时间（秒）。

        Returns:
            一个包含LLM响应的字典 (通常具有 "message": {"content": "..."} 结构)，
            如果发生错误则返回None。
        """
        pass

    @abstractmethod
    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        列出可用的本地模型 (主要用于类似Ollama的客户端)。
        对于在线API，这可能返回包含配置模型的固定列表或None。

        Returns:
            模型字典列表 (例如: [{"name": "model_name"}, ...]) 或None。
        """
        pass

    @property
    @abstractmethod
    def client_type(self) -> str:
        """返回客户端的类型，例如 "ollama" 或 "online_api"."""
        pass
    
    def chat_completion(self, messages: List[Dict[str, str]], model: str = None) -> Optional[str]:
        """
        从LLM获取聊天完成的简化方法。

        Args:
            messages: 消息字典列表 (例如: {"role": "user", "content": "..."})。
            model: 可选的模型名称，如果未提供则使用客户端默认模型。

        Returns:
            LLM响应的内容字符串，如果发生错误则返回None。
        """
        model_to_use = model or getattr(self, 'default_model', None)
        response = self.generate_chat_completion(model_to_use, messages)
        
        if response and "message" in response and "content" in response["message"]:
            return response["message"]["content"]
        
        return None

def get_llm_client(config: Dict[str, Any]) -> Optional[LLMClientInterface]:
    """
    根据配置创建并返回适当的LLM客户端实例。

    Args:
        config: 包含客户端配置的字典，必须包含 "client_type" 键。
            对于 "ollama" 类型，需要 "api_url" 和 "model_name"。
            对于 "online_api" 类型，需要 "api_url"、"api_key" 和 "model_name"。

    Returns:
        LLMClientInterface 的实例，如果配置无效则返回 None。
    """
    client_type = config.get("client_type")
    
    if not client_type:
        print("错误: 配置中缺少 client_type")
        return None
    
    if client_type == "ollama":
        # 动态导入以避免循环依赖
        from ollama_client import OllamaClient
        
        api_url = config.get("api_url")
        model_name = config.get("model_name")
        
        if not api_url or not model_name:
            print("错误: Ollama 配置缺少必要参数")
            return None
        
        return OllamaClient(api_url, model_name)
    
    elif client_type == "online_api":
        # 动态导入以避免循环依赖
        from generic_online_api_client import GenericOnlineAPIClient
        
        api_url = config.get("api_url")
        api_key = config.get("api_key")
        model_name = config.get("model_name")
        
        if not api_url or not api_key or not model_name:
            print("错误: 在线 API 配置缺少必要参数")
            return None
        
        return GenericOnlineAPIClient(api_url, api_key, model_name)
    
    else:
        print(f"错误: 不支持的客户端类型 {client_type}")
        return None
