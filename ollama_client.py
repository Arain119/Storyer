# ollama_client.py
# 该文件定义了与本地Ollama LLM服务交互的客户端。

import requests # 用于发送HTTP请求
import json # 用于处理JSON数据
from typing import List, Dict, Optional, Any

import config # 导入配置
import utils # 导入工具函数
from llm_client_interface import LLMClientInterface # 导入LLM客户端接口

class OllamaClient(LLMClientInterface): # 继承自LLM客户端接口
    """
    与本地Ollama服务交互的客户端。
    """
    def __init__(self, base_url: str = config.OLLAMA_API_BASE_URL,
                 default_model: Optional[str] = config.DEFAULT_OLLAMA_MODEL):
        """
        初始化OllamaClient。

        Args:
            base_url: Ollama API的基础URL。
            default_model: (可选) 默认使用的Ollama模型名称。
        """
        self.base_url = base_url
        self.default_model = default_model
        self.session = requests.Session() # 使用requests.Session以复用连接
        self.default_timeout = 120  # 默认超时时间（秒）
        print(f"OllamaClient已为基础URL初始化: {self.base_url}")

    @property
    def client_type(self) -> str:
        """返回客户端类型。"""
        return "ollama"

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, stream: bool = False,
                      timeout: Optional[int] = None) -> Optional[Any]:
        """
        向Ollama API发送请求的内部辅助方法。

        Args:
            method: HTTP方法 (例如 "GET", "POST")。
            endpoint: API端点 (例如 "/api/tags")。
            data: (可选) POST请求的数据。
            stream: (可选) 是否以流式方式处理响应。
            timeout: (可选) 请求超时时间（秒）。

        Returns:
            解码后的JSON响应，或在流式传输时返回聚合的响应字典，或在出错时返回None。
        """
        url = f"{self.base_url}{endpoint}" # 拼接完整URL
        request_timeout = timeout if timeout is not None else self.default_timeout
        if method.upper() == "GET": # GET请求通常超时时间可以短一些
            request_timeout = timeout if timeout is not None else 30

        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=request_timeout)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, stream=stream, timeout=request_timeout)
            else:
                print(f"不支持的HTTP方法: {method}")
                return None
            response.raise_for_status() # 如果HTTP状态码表示错误，则抛出异常

            if stream:
                # 对于流式响应，需要聚合内容并可能返回最终的"done"消息部分。
                # 接口期望 Optional[Dict[str, Any]]，理想情况下应结构化为 {"message": {"content": "..."}}。
                # 我们将聚合内容并形成这样的结构。
                full_response_content = ""
                # final_json_part = None # 在新的流式返回结构中不直接使用
                for line in response.iter_lines(): # 迭代处理流中的每一行
                    if line:
                        decoded_line = line.decode("utf-8")
                        try:
                            json_part = json.loads(decoded_line) #尝试解析为JSON
                            # 检查Ollama聊天API的流式响应结构
                            if "message" in json_part and "content" in json_part["message"]:
                                full_response_content += json_part["message"]["content"]
                            elif "response" in json_part: # Ollama非聊天API的流式格式 (例如 /api/generate)
                                full_response_content += json_part["response"]

                            if json_part.get("done"): # 如果收到表示流结束的标记
                                # final_json_part = json_part # 此时已获得完整内容
                                break
                        except json.JSONDecodeError:
                            print(f"警告：无法将流中的一行解码为JSON: {decoded_line}")
                            full_response_content += decoded_line # 如果不是JSON，则作为原始文本追加
                # 返回聚合后的流式响应
                return {
                    "message": {"role": "assistant", "content": full_response_content.strip()},
                    "model": data.get("model") if data else "unknown_streamed_model" # 添加模型信息
                }
            else: # 非流式响应
                return response.json() # 直接返回JSON解码后的响应

        except requests.exceptions.Timeout:
            print(f"错误：向Ollama API {url} 的请求在 {request_timeout} 秒后超时。")
            return None
        except requests.exceptions.RequestException as e:
            print(f"错误：连接到Ollama API {url} 时出错: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try: print(f"响应内容: {e.response.text}")
                except Exception: pass
            return None
        except json.JSONDecodeError as e:
            print(f"错误：解码来自Ollama API的JSON响应时出错: {e}")
            if 'response' in locals() and hasattr(response, 'text'): print(f"响应文本: {response.text[:500]}")
            return None

    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        列出Ollama服务中可用的本地模型。
        对应 /api/tags 端点。

        Returns:
            模型信息字典的列表，或在出错时返回None。
        """
        response_data = self._make_request("GET", "/api/tags")
        if response_data and "models" in response_data:
            return response_data["models"]
        print("未能列出本地模型或未找到模型。")
        return None

    def generate_chat_completion(
            self,
            model: str,
            messages: List[Dict[str, str]],
            stream: bool = False,
            expect_json_in_content: bool = False, # Ollama为此使用 "format":"json"
            timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用Ollama生成聊天完成。
        对应 /api/chat 端点。

        Args:
            model: 要使用的模型名称。
            messages: 消息列表。
            stream: 是否流式传输响应。
            expect_json_in_content: 是否期望内容为JSON。如果为True且非流式，则设置 "format": "json"。
            timeout: 请求超时时间。

        Returns:
            包含LLM响应的字典，或在出错时返回None。
        """
        payload = {
            "model": model or self.default_model, # 如果未提供模型，则使用默认模型
            "messages": messages,
            "stream": stream,
        }
        # 如果期望JSON内容且非流式，Ollama支持 "format": "json" 参数
        if expect_json_in_content and not stream:
            payload["format"] = "json"

        print(f"\n向Ollama模型发送请求: {payload['model']} (期望内容为JSON: {expect_json_in_content}, 流式: {stream})...")
        response_data = self._make_request("POST", "/api/chat", data=payload, stream=stream, timeout=timeout)

        if response_data:
            if stream:
                # _make_request 对于流式已返回 {"message": {"content": "..."}, "model": ...} 结构
                return response_data
            else: # 非流式响应
                # response_data 已经是字典，通常是 {"model": ..., "created_at": ..., "message": {"role": ..., "content": ...}, ...}
                # 如果使用了 format:json，message.content 是一个需要解析的字符串。
                if expect_json_in_content and response_data.get("message") and isinstance(response_data["message"].get("content"), str):
                    try:
                        parsed_content = json.loads(response_data["message"]["content"])
                        response_data["message"]["content"] = parsed_content # 将解析后的JSON对象放回
                        print("成功解析LLM JSON响应内容。")
                    except json.JSONDecodeError:
                        print(f"LLM响应内容期望为JSON但无效: {response_data['message']['content'][:200]}... 将其视为纯文本。")
                return response_data # 返回Ollama的完整响应字典
        return None

    # select_model 是一个命令行界面的辅助方法，不属于LLMClientInterface接口。
    def select_model(self) -> Optional[str]:
        """
        允许用户从可用的Ollama模型列表中选择一个模型 (用于命令行测试)。

        Returns:
            用户选择的模型名称，或None。
        """
        models = self.list_local_models() # 获取模型列表
        if not models:
            print("无法获取模型列表。请确保Ollama正在运行并且可以访问。")
            if self.default_model:
                print(f"尝试使用默认模型: {self.default_model}")
                return self.default_model
            # 如果无法获取列表且无默认模型，提示用户手动输入
            user_model = utils.get_user_input("请手动输入您希望使用的Ollama模型名称: ")
            return user_model if user_model else None

        print("\n可用的Ollama模型:")
        for i, model_info in enumerate(models):
            # 显示模型名称和部分ID
            print(f"{i + 1}. {model_info.get('name')} (ID: {model_info.get('digest', 'N/A')[:12]}...)")

        # 如果有默认模型，询问用户是否使用
        if self.default_model:
            use_default = utils.get_user_input(f"使用默认模型 '{self.default_model}'? (y/n, 默认 y): ").lower()
            if use_default == "" or use_default == "y":
                if any(m["name"] == self.default_model for m in models): # 检查默认模型是否存在于列表中
                    print(f"使用默认模型: {self.default_model}")
                    return self.default_model
                else:
                    print(f"警告: 默认模型 '{self.default_model}' 未在列表中找到。请手动选择。")

        # 循环直到用户做出有效选择
        while True:
            try:
                choice_str = utils.get_user_input(f"通过数字选择模型 (1-{len(models)}) 或输入模型名称: ")
                if choice_str.isdigit(): # 如果输入是数字
                    choice = int(choice_str)
                    if 1 <= choice <= len(models):
                        return models[choice - 1]["name"] # 返回对应索引的模型名称
                    else:
                        print(f"无效数字。请输入1到{len(models)}之间的数字。")
                elif any(m["name"] == choice_str for m in models): # 如果输入是列表中的模型名称
                    return choice_str
                else:
                    print(f"模型名称 '{choice_str}' 未在列表中找到。请重试。")
            except ValueError:
                print("无效输入。请输入数字或有效的模型名称。")

if __name__ == "__main__":
    # 主程序块，用于测试OllamaClient
    print("测试 ollama_client.py (已适配LLMClientInterface)...")
    try:
        client = OllamaClient() # 使用config.py中的默认URL
        print(f"使用Ollama API基础URL: {client.base_url}")
        print(f"客户端类型: {client.client_type}")

        print("\n--- 列出模型 ---")
        models = client.list_local_models()
        if models:
            print("可用模型:")
            for m in models:
                print(f"- {m.get('name')}")
        else:
            print("未找到模型或Ollama无法访问。")

        # 为自动化测试选择模型，避免交互
        selected_model_for_test = config.DEFAULT_OLLAMA_MODEL
        if not models or not any(m["name"] == selected_model_for_test for m in models):
            if models: # 如果默认模型不在，则使用列表中的第一个
                selected_model_for_test = models[0]["name"]
                print(f"默认模型未找到，使用第一个可用模型: {selected_model_for_test}")
            else: # 如果没有可用模型，则跳过聊天测试
                print("无可用模型，跳过聊天测试。")
                selected_model_for_test = None
        else:
             print(f"将使用模型 {selected_model_for_test} 进行测试。")

        if selected_model_for_test:
            print(f"\n选择的模型进行聊天测试: {selected_model_for_test}")

            print("\n--- 聊天完成测试 (非流式，期望纯文本) ---")
            messages_text = [
                {"role": "system", "content": "你是一个乐于助人的助手。请简明扼要地回答。"},
                {"role": "user", "content": "法国的首都是哪里？"}
            ]
            response_text_data = client.generate_chat_completion(selected_model_for_test, messages_text, expect_json_in_content=False)
            if response_text_data and response_text_data.get("message") and isinstance(response_text_data["message"].get("content"), str):
                print(f"纯文本API响应 (内容): {response_text_data['message']['content']}")
            else:
                print("纯文本API调用失败或返回意外结构。")
                if response_text_data: print(f"完整响应: {response_text_data}")

            print("\n--- 聊天完成测试 (非流式，期望JSON) ---")
            messages_json = [
                {"role": "system", "content": "你是一个只以JSON格式响应的助手。你的响应应该是一个JSON对象，包含一个键 'answer'，其值为首都城市。"},
                {"role": "user", "content": "法国的首都是哪里？请以JSON格式提供答案。"}
            ]
            response_json_data = client.generate_chat_completion(selected_model_for_test, messages_json, expect_json_in_content=True)
            # 期望 message.content 是一个字典
            if response_json_data and response_json_data.get("message") and isinstance(response_json_data["message"].get("content"), dict):
                print(f"JSON API响应 (解析后的内容): {response_json_data['message']['content']}")
                assert "answer" in response_json_data['message']['content'], "JSON响应缺少 'answer' 键"
            elif response_json_data and response_json_data.get("message"): # 如果内容不是字典，打印原始字符串
                print(f"JSON API响应 (原始内容，未解析为字典): {response_json_data['message'].get('content')}")
            else:
                print("JSON API调用失败或返回意外结构。")
                if response_json_data: print(f"完整响应: {response_json_data}")

            print("\n--- 聊天完成测试 (流式) ---")
            messages_stream = [
                {"role": "system", "content": "你是一位富有诗意的助手，请用短诗作答。"},
                {"role": "user", "content": "用三行诗句描述日出。"}
            ]
            response_stream_data = client.generate_chat_completion(selected_model_for_test, messages_stream, stream=True, expect_json_in_content=False)
            if response_stream_data and response_stream_data.get("message") and isinstance(response_stream_data["message"].get("content"), str):
                print(f"流式聊天API响应 (累积文本): {response_stream_data['message']['content']}")
            else:
                print("流式聊天API调用失败或返回意外结构。")
                if response_stream_data: print(f"完整响应: {response_stream_data}")
        else:
            print("未选择模型，跳过聊天测试。")
    except ImportError as e:
        print(f"测试失败，导入错误: {e}. 请确保 config.py 和 utils.py 在正确的位置。")
    except Exception as e:
        print(f"测试期间发生意外错误: {e}")
        import traceback
        traceback.print_exc()

    print("\nollama_client.py 测试完成。")