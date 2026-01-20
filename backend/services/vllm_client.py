"""
统一的 vLLM 客户端

所有调用 vLLM API 的服务都应使用此客户端，确保：
1. 统一的 API Key 认证
2. 统一的超时和重试策略
3. 统一的错误处理
"""

import httpx
import requests
from typing import Optional, Dict, Any, List
from config import get_settings

settings = get_settings()


class VLLMClient:
    """vLLM API 客户端（单例模式）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.base_url = settings.vllm_base_url
        self.model = settings.vllm_model
        self.api_key = settings.vllm_api_key
        self.default_timeout = 120  # 秒

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头（包含认证）"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        同步调用 vLLM chat completion API

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            model: 模型名称，默认使用配置的模型
            temperature: 温度参数
            max_tokens: 最大 token 数
            timeout: 超时时间（秒）

        Returns:
            API 响应 JSON

        Raises:
            requests.HTTPError: API 调用失败
        """
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._get_headers(),
            json={
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            timeout=timeout or self.default_timeout
        )
        response.raise_for_status()
        return response.json()

    async def chat_completion_async(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        异步调用 vLLM chat completion API

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            model: 模型名称，默认使用配置的模型
            temperature: 温度参数
            max_tokens: 最大 token 数
            timeout: 超时时间（秒）

        Returns:
            API 响应 JSON

        Raises:
            httpx.HTTPStatusError: API 调用失败
        """
        async with httpx.AsyncClient(timeout=timeout or self.default_timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._get_headers(),
                json={
                    "model": model or self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()
            return response.json()

    def get_response_text(self, response: Dict[str, Any]) -> str:
        """从 API 响应中提取文本内容"""
        return response["choices"][0]["message"]["content"].strip()


# 全局客户端实例
vllm_client = VLLMClient()


def get_vllm_client() -> VLLMClient:
    """获取 vLLM 客户端实例"""
    return vllm_client
