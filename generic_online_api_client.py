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
            timeout: Optional[int] = None,
            options: Optional[Dict[str, Any]] = None  # 已修改: 添加 options 参数
    ) -> Optional[Dict[str, Any]]:
        """
        从在线API生成聊天完成。

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
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}"
            }

            payload = {
                "model": model or self._default_model,
                "messages": messages,
                "stream": stream
            }

            if expect_json_in_content:
                # 许多类似OpenAI的API使用此格式请求JSON对象输出
                payload["response_format"] = {"type": "json_object"}

            if options:  # 已修改: 将 options 更新到 payload 中
                payload.update(options)

            response = requests.post(
                self._api_url,
                headers=headers,
                json=payload,
                timeout=timeout or 60  # 小说分析时这里会被150秒覆盖，叙事时用默认或options里的
            )

            if response.status_code == 200:
                result = response.json()

                # 标准化响应格式，尝试适配OpenAI的结构
                if "choices" in result and len(result["choices"]) > 0 and "message" in result["choices"][0]:
                    return {
                        "message": result["choices"][0]["message"]
                    }
                # 如果API直接返回 "message" 对象 (非标准但作为后备)
                elif "message" in result and isinstance(result["message"], dict):
                    return {"message": result["message"]}
                else:
                    print(f"在线API响应格式非预期 (状态码200): {result}")
                    # 尝试从其他常见位置提取内容作为最后的努力
                    if "content" in result and isinstance(result["content"], str):
                        return {"message": {"role": "assistant", "content": result["content"]}}
                    return None  # 无法解析为标准格式
            else:
                error_message = f"在线API错误: {response.status_code}"
                try:
                    error_details = response.json()
                    error_message += f" - {error_details}"
                except ValueError:
                    error_message += f" - {response.text}"
                print(error_message)
                return None

        except requests.exceptions.Timeout:
            print(f"在线API请求超时 ({timeout or 60}秒)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"在线API请求错误: {str(e)}")
            return None
        except Exception as e:
            print(f"生成在线API聊天完成时出错: {str(e)}")
            return None

    def list_local_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        对于在线API，这通常会返回配置的默认模型，或尝试从标准端点（如 /v1/models）获取模型列表。
        """
        # 优先返回配置的默认模型
        if self._default_model:
            models_list = [{"name": self._default_model, "details": "配置的默认在线模型"}]
        else:
            models_list = []

        # 尝试从类似OpenAI的 /models 端点获取列表
        # 这部分是可选的，取决于API是否支持
        try:
            # 假设API URL类似于 "https://api.example.com/v1/chat/completions"
            # 尝试构造 "/v1/models" 端点
            base_url = self._api_url
            if "/chat/completions" in base_url:
                models_url = base_url.replace("/chat/completions", "/models")
            elif base_url.endswith("/v1"):  # 如果是 /v1 结尾
                models_url = base_url + "/models"
            else:  # 无法确定标准模型端点，仅返回默认模型
                return models_list if models_list else []

            headers = {"Authorization": f"Bearer {self._api_key}"}
            response = requests.get(models_url, headers=headers, timeout=10)  # 短超时用于此调用

            if response.status_code == 200:
                data = response.json().get("data", [])
                api_models = [{"name": model.get("id"), "details": model} for model in data if model.get("id")]

                # 合并并去重
                name_set = {m["name"] for m in models_list}
                for api_model in api_models:
                    if api_model["name"] not in name_set:
                        models_list.append(api_model)
                        name_set.add(api_model["name"])
                return models_list
            else:
                print(
                    f"无法从在线API的 {models_url} 获取模型列表 (状态码: {response.status_code})。仅返回默认模型（如果已配置）。")
                return models_list if models_list else []

        except Exception as e:
            print(f"尝试从在线API获取模型列表时出错: {e}。仅返回默认模型（如果已配置）。")
            return models_list if models_list else []