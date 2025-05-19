# generic_online_api_client.py
# 该文件定义了一个通用的在线LLM API客户端，兼容类OpenAI的接口。

import requests
import json
import os
from typing import List, Dict, Any, Optional

from llm_client_interface import LLMClientInterface # 导入LLM客户端接口

class GenericOnlineAPIClient(LLMClientInterface):
    """
    一个用于与通用在线LLM API（兼容OpenAI）交互的客户端。
    """

    def __init__(self, api_url: str, api_key: str, model_name: str, timeout: int = 120):
        """
        初始化GenericOnlineAPIClient。

        Args:
            api_url: 在线LLM API的基础URL (例如: "https://api.openai.com/v1/chat/completions")。
            api_key: 用于认证的API密钥。
            model_name: 要使用的在线API中的特定模型。
            timeout: API请求的默认超时时间（秒）。
        """
        if not api_url.endswith("/chat/completions"):
            # 提示：通常聊天完成的API端点以 "/chat/completions" 结尾
            print(f"警告: GenericOnlineAPIClient的api_url通常以/chat/completions结尾。当前: {api_url}")
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        print(f"GenericOnlineAPIClient已为模型初始化: {self.model_name}，URL: {self.api_url}")

    @property
    def client_type(self) -> str:
        """返回客户端类型。"""
        return "online_api"

    def generate_chat_completion(
        self,
        model: str, # 此参数将是self.model_name，但为保持接口兼容性而保留
        messages: List[Dict[str, str]],
        stream: bool = False,
        expect_json_in_content: bool = False, # 标准API不直接使用，但对上下文有益
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用配置的在线LLM API生成聊天完成。

        Args:
            model: 要使用的模型名称 (将使用self.model_name)。
            messages: 消息列表，每个消息是一个字典，如 {"role": "user", "content": "..."}。
            stream: 是否流式传输响应。
            expect_json_in_content: 指示是否期望内容为JSON字符串。
            timeout: API请求的超时时间（秒）。

        Returns:
            一个包含LLM响应的字典，通常结构为 {"message": {"content": "..."}}，
            如果发生错误则返回None。
        """
        request_timeout = timeout if timeout is not None else self.timeout
        payload = {
            "model": self.model_name, # 使用为此客户端实例配置的model_name
            "messages": messages,
            "stream": stream
        }
        # 一些API可能期望顶层的 "response_format": {"type": "json_object"} 用于JSON模式。
        # 这并非普遍标准，因此通用客户端中省略。
        # `expect_json_in_content` 更多是给调用者或后处理的提示。

        print(f"正在向在线API发送请求: {self.api_url}，模型: {self.model_name}")
        # print(f"Payload (不含API密钥): {json.dumps(payload, indent=2)}") # 用于调试，注意日志中的敏感信息

        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=request_timeout,
                stream=stream # 也将stream传递给requests.post
            )
            response.raise_for_status()  # 对HTTP错误 (4xx或5xx) 抛出异常

            if stream:
                # 流式处理更复杂，需要不同的返回类型或回调。
                # 为简单起见，在这个基本客户端中暂时假设非流式。
                # 如果确实需要流式传输，这部分需要大幅扩展。
                print("警告: stream设置为True，但基本的GenericOnlineAPIClient当前返回聚合响应。")
                # 如果实现，则收集流式块，然后解析。
                # 目前，我们将尝试像解析单个JSON响应一样进行解析。
                full_content = ""
                # iter_lines()是一种基本方式，真正的SSE（Server-Sent Events）更复杂
                for chunk in response.iter_lines():
                    if chunk:
                        # 这里需要一个更健壮的SSE解析器
                        # 这是实际流处理的占位符
                        decoded_chunk = chunk.decode("utf-8")
                        if decoded_chunk.startswith("data: "):
                            data_part = decoded_chunk[len("data: "):]
                            if data_part.strip() == "[DONE]": # OpenAI流结束标记
                                break
                            try:
                                chunk_json = json.loads(data_part)
                                # 检查OpenAI流的典型结构
                                if chunk_json.get("choices") and \
                                   chunk_json["choices"][0].get("delta") and \
                                   chunk_json["choices"][0]["delta"].get("content"):
                                    full_content += chunk_json["choices"][0]["delta"]["content"]
                            except json.JSONDecodeError:
                                print(f"解码流块时出错: {data_part}")
                                continue # 或处理错误
                # 收集完所有流式内容后，将其构造成类似非流式响应的结构
                # 这是对流处理的简化模拟
                return {
                    "message": {
                        "role": "assistant",
                        "content": full_content
                    },
                    "model": self.model_name # 在响应中包含模型信息以保持一致性
                }
            else: # 非流式
                response_json = response.json()
                # 标准的类OpenAI响应结构:
                # {"choices": [{"message": {"role": "assistant", "content": "..."}}], ...}
                if response_json.get("choices") and len(response_json["choices"]) > 0:
                    message_content = response_json["choices"][0].get("message")
                    if message_content:
                        # 将模型信息添加到响应中，以便调用者更容易跟踪
                        response_json["model"] = response_json.get("model", self.model_name)
                        # 核心部分是消息本身
                        return {
                            "message": message_content,
                            "model": response_json.get("model", self.model_name),
                            "usage": response_json.get("usage") # 如果可用，传递使用统计信息
                        }
                print(f"来自API的意外响应结构: {response_json}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"调用API {self.api_url} 期间出错: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"解码来自 {self.api_url} 的JSON响应时出错: {e}. 响应文本: {response.text[:500]}")
            return None

    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        对于在线API，我们不像Ollama那样列出“本地”模型。
        我们可以返回配置的模型名称作为此客户端实例唯一可用的模型。
        """
        return [{
            "name": self.model_name,
            "details": "配置的在线API模型"
        }]

if __name__ == "__main__":
    # 主程序块，用于测试GenericOnlineAPIClient
    print("测试 GenericOnlineAPIClient...")
    # 测试时请替换为您的实际API URL、密钥和模型
    # 确保API端点是用于聊天完成的，例如以 /v1/chat/completions 结尾
    test_api_url = os.environ.get("TEST_OPENAI_API_URL") # 例如: "https://api.openai.com/v1/chat/completions"
    test_api_key = os.environ.get("TEST_OPENAI_API_KEY")
    test_model_name = os.environ.get("TEST_OPENAI_MODEL_NAME") # 例如: "gpt-3.5-turbo"

    if not all([test_api_url, test_api_key, test_model_name]):
        print("请设置 TEST_OPENAI_API_URL, TEST_OPENAI_API_KEY, 和 TEST_OPENAI_MODEL_NAME 环境变量以进行测试。")
    else:
        client = GenericOnlineAPIClient(api_url=test_api_url, api_key=test_api_key, model_name=test_model_name)

        print(f"客户端类型: {client.client_type}")
        print(f"可用模型 (此客户端): {client.list_local_models()}")

        test_messages = [
            {"role": "system", "content": "你是一个乐于助人的助手。"},
            {"role": "user", "content": "你好！法国的首都是哪里？"}
        ]

        print("\n测试非流式聊天完成...")
        response = client.generate_chat_completion(model=test_model_name, messages=test_messages, stream=False)
        if response and response.get("message"):
            print(f"API响应 (内容): {response['message'].get('content')}")
            print(f"完整API响应: {json.dumps(response, indent=2, ensure_ascii=False)}")
        else:
            print("未能获取有效的响应或消息内容。")

        # 基本流式测试 (注意: 当前实现是聚合的，真正的流式需要更多工作)
        # print("\n测试流式聊天完成 (模拟)...")
        # stream_response = client.generate_chat_completion(model=test_model_name, messages=test_messages, stream=True)
        # if stream_response and stream_response.get("message"):
        #     print(f"API流式响应 (聚合内容): {stream_response['message'].get('content')}")
        # else:
        #     print("未能获取有效的流式响应。")