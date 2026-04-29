# src/adapters/ai_models/qianfan_adapter.py
# 千帆 (百度文心) 适配器 - 兼容 OpenAI API 格式，使用 httpx 直接调用

import time
import logging
from typing import List, Dict, Any, Optional

import httpx

from src.adapters.ai_models.base import (
    BaseAIModelAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
    AIModelError,
    AIModelConnectionError,
    AIModelRateLimitError,
    AIModelTimeoutError,
)

logger = logging.getLogger(__name__)


class QianfanAdapter(BaseAIModelAdapter):
    """
    千帆 (百度文心) 适配器

    百度千帆大模型平台，兼容 OpenAI API 格式。
    由于千帆使用完整 endpoint URL，使用 httpx 直接调用而非 openai SDK。
    支持 ernie-bot-4, ernie-bot-turbo 等模型。
    """

    SUPPORTED_MODELS = [
        "ernie-bot-4",
        "ernie-bot-4-8k",
        "ernie-bot-turbo",
        "ernie-bot-turbo-8k",
        "ernie-speed-128k",
        "ernie-lite-8k",
        "deepseek-v3",
    ]

    DEFAULT_BASE_URL = "https://aip.baidubce.com"
    PROVIDER_NAME = "Qianfan"

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

        if not self.config.base_url:
            self.config.base_url = self.DEFAULT_BASE_URL

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def _get_access_token(self) -> str:
        """获取百度 API 的 access_token。"""
        client = self._get_client()
        url = (
            f"{self.config.base_url}/oauth/2.0/token"
            f"?grant_type=client_credentials"
            f"&client_id={self.config.api_key}"
            f"&client_secret={self.config.extra.get('secret_key', '')}"
        )

        response = await client.post(url)
        data = response.json()

        if "access_token" not in data:
            raise AIModelConnectionError(
                f"获取 access_token 失败: {data}",
                provider=self.PROVIDER_NAME
            )

        return data["access_token"]

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """发送对话消息"""
        start_time = time.time()

        try:
            client = self._get_client()

            # 获取 access_token
            access_token = await self._get_access_token()

            # 合并参数
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
            top_p = kwargs.get('top_p', self.config.top_p)
            stop = kwargs.get('stop', self.config.stop)

            # 构建请求
            request_body = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": top_p,
            }

            if stop:
                request_body["stop"] = stop

            url = (
                f"{self.config.base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
                f"/{self.config.model_name}"
                f"?access_token={access_token}"
            )

            logger.debug(
                f"Qianfan: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(messages)}"
            )

            response = await client.post(url, json=request_body)
            data = response.json()

            latency_ms = self._measure_latency(start_time)

            # 检查错误
            if "error_code" in data:
                raise AIModelError(
                    f"API 请求失败: {data.get('error_msg', '未知错误')}",
                    provider=self.PROVIDER_NAME
                )

            # 解析响应
            content = data.get("result", "")
            finish_reason = data.get("finish_reason", "normal")
            model = data.get("model", self.config.model_name)

            usage = {}
            input_tokens = 0
            output_tokens = 0
            if "usage" in data:
                usage_data = data["usage"]
                input_tokens = usage_data.get("prompt_tokens", 0) or 0
                output_tokens = usage_data.get("completion_tokens", 0) or 0
                usage = {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": (input_tokens + output_tokens),
                }

            cost = self.calculate_cost(
                self.config.model_name, input_tokens, output_tokens
            )

            model_response = ModelResponse(
                content=content or "",
                model=model,
                provider=ModelProvider.QIANFAN,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

            logger.info(
                f"Qianfan: 响应成功, model={model_response.model}, "
                f"tokens={usage.get('total_tokens', 0)}, "
                f"latency={latency_ms:.0f}ms, cost=${cost:.6f}"
            )

            return model_response

        except AIModelError:
            raise
        except httpx.TimeoutException:
            latency_ms = self._measure_latency(start_time)
            raise AIModelTimeoutError(
                f"请求超时 ({self.config.timeout}s)",
                provider=self.PROVIDER_NAME
            )
        except Exception as e:
            latency_ms = self._measure_latency(start_time)
            error = self._parse_error(e)
            logger.error(
                f"Qianfan: 请求失败, error={error}, latency={latency_ms:.0f}ms"
            )
            raise error

    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs
    ) -> ModelResponse:
        """使用系统提示词发送消息"""
        messages = self._build_messages(
            system_prompt=system_prompt,
            user_message=user_message,
        )
        return await self.chat(messages, **kwargs)

    def is_available(self) -> bool:
        """检查模型是否可用"""
        if not self.config.api_key:
            logger.warning("Qianfan: api_key 未配置")
            return False

        # 千帆使用同步检查较复杂，直接返回 True（在首次调用时验证）
        self._available = True
        return True

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": self.PROVIDER_NAME,
            "model": self.config.model_name,
            "available": self._available,
            "supported_models": self.SUPPORTED_MODELS,
            "base_url": self.config.base_url,
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "timeout": self.config.timeout,
            },
        }

    def _parse_error(self, error: Exception) -> AIModelError:
        """解析千帆错误"""
        error_str = str(error)

        if "timeout" in error_str.lower():
            return AIModelTimeoutError(
                f"请求超时: {error_str}",
                provider=self.PROVIDER_NAME
            )
        elif "rate" in error_str.lower() and "limit" in error_str.lower():
            return AIModelRateLimitError(
                f"请求限流: {error_str}",
                provider=self.PROVIDER_NAME,
                retry_after=5.0,
            )
        elif "auth" in error_str.lower() or "token" in error_str.lower():
            return AIModelConnectionError(
                f"认证失败: {error_str}",
                provider=self.PROVIDER_NAME
            )
        elif "connect" in error_str.lower():
            return AIModelConnectionError(
                f"连接失败: {error_str}",
                provider=self.PROVIDER_NAME
            )
        else:
            return AIModelError(
                f"请求失败: {error_str}",
                provider=self.PROVIDER_NAME
            )
