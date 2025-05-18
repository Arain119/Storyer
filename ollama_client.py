# ollama_client.py
# 该文件实现了Ollama API客户端。

import requests
import json
from typing import List, Dict, Any, Optional

# 导入LLM客户端接口的抽象基类
from llm_client_interface import LLMClientInterface


class OllamaClient(LLMClientInterface):
    """Ollama API客户端实现。"""

    def __init__(self, api_url: str, default_model: str):
        """
        初始化Ollama客户端。

        Args:
            api_url: Ollama API端点URL。
            default_model: 默认模型名称。
        """
        self._api_url = api_url.rstrip('/')
        self._default_model = default_model

    @property
    def default_model(self) -> str:
        """获取默认模型名称。"""
        return self._default_model

    @property
    def client_type(self) -> str:
        """返回客户端类型。"""
        return "ollama"

    def generate_chat_completion(
            self,
            model: str,
            messages: List[Dict[str, str]],
            stream: bool = False,
            expect_json_in_content: bool = False,
            timeout: Optional[int] = None,
            options: Optional[Dict[str, Any]] = None  # 已修改: 添加 options 参数
    ) -> Optional[Dict[str, Any]]:
        """
        从Ollama API生成聊天完成。

        Args:
            model: 用于生成的模型名称。
            messages: 消息字典列表。
            stream: 是否流式传输响应。
            expect_json_in_content: 提示响应内容期望为JSON字符串。
            timeout: API调用的超时时间（秒）。
            options: 包含额外LLM参数的字典。

        Returns:
            一个包含API响应的字典，如果发生错误则返回None。
        """
        try:
            headers = {
                "Content-Type": "application/json"
            }

            payload = {
                "model": model or self._default_model,
                "messages": messages,
                "stream": stream
            }

            if expect_json_in_content:
                payload["format"] = "json"

            if options:  # 已修改: 将 options 加入 payload
                payload["options"] = options

            response = requests.post(
                f"{self._api_url}/api/chat",
                headers=headers,
                json=payload,
                timeout=timeout or 60  # 小说分析时这里会被150秒覆盖，叙事时用默认或options里的
            )

            if response.status_code == 200:
                result = response.json()

                # 标准化响应格式
                return {
                    "message": {
                        "role": "assistant",
                        "content": result.get("message", {}).get("content", "")
                    }
                }
            else:
                error_message = f"Ollama API错误: {response.status_code}"
                try:
                    error_details = response.json()
                    error_message += f" - {error_details}"
                except ValueError:
                    error_message += f" - {response.text}"
                print(error_message)
                return None

        except requests.exceptions.Timeout:
            print(f"Ollama API请求超时 ({timeout or 60}秒)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Ollama API请求错误: {str(e)}")
            return None
        except Exception as e:
            print(f"生成聊天完成时出错: {str(e)}")
            return None

    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        列出可用的本地Ollama模型。

        Returns:
            模型字典列表，如果发生错误则返回None。
        """
        try:
            response = requests.get(
                f"{self._api_url}/api/tags",
                timeout=30  # 为列出模型设置一个合理的超时
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("models", [])
            else:
                print(f"列出Ollama模型时出错: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.Timeout:
            print(f"列出Ollama模型请求超时")
            return None
        except requests.exceptions.RequestException as e:
            print(f"列出Ollama模型请求错误: {str(e)}")
            return None
        except Exception as e:
            print(f"列出Ollama模型时发生意外错误: {str(e)}")
            return None