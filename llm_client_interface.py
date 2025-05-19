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