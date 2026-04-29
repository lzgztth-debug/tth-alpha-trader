# src/adapters/ai_models/qwen_adapter.py
# 通义千问适配器 - 使用 dashscope SDK 支持 Qwen-Max, Qwen-Plus 等模型

import time
import logging
from typing import List, Dict, Any, Optional

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


class QwenAdapter(BaseAIModelAdapter):
    """
    通义千问适配器

    使用阿里云 dashscope SDK，支持 Qwen-Max, Qwen-Plus, Qwen-Turbo 等模型。

    配置参数:
        provider: ModelProvider.QWEN
        model_name: 模型名称（如 qwen-max, qwen-plus, qwen-turbo）
        api_key: 阿里云 DashScope API Key
        base_url: 自定义 API 地址（可选）
        temperature: 温度参数，默认 0.7
        max_tokens: 最大输出 token 数，默认 4096
        timeout: 超时时间（秒），默认 60
    """

    # 支持的模型列表
    SUPPORTED_MODELS = [
        "qwen-max",
        "qwen-max-latest",
        "qwen-plus",
        "qwen-plus-latest",
        "qwen-turbo",
        "qwen-turbo-latest",
        "qwen-long",
        "qwen-vl-max",
        "qwen-vl-plus",
        "qwen-math-plus",
        "qwen-coder-plus",
    ]

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _init_client(self):
        """初始化 DashScope 客户端"""
        try:
            import dashscope
            from dashscope import Generation

            dashscope.api_key = self.config.api_key
            self._generation = Generation
            self._dashscope = dashscope

            logger.info(f"Qwen: 客户端初始化成功, model={self.config.model_name}")

        except ImportError:
            raise AIModelConnectionError(
                "dashscope SDK 未安装，请执行: pip install dashscope",
                provider="Qwen"
            )
        except Exception as e:
            raise AIModelConnectionError(
                f"初始化客户端失败: {e}",
                provider="Qwen"
            )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """发送对话消息"""
        start_time = time.time()

        try:
            if self._client is None:
                self._init_client()

            import asyncio

            # 合并参数
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
            top_p = kwargs.get('top_p', self.config.top_p)
            stop = kwargs.get('stop', self.config.stop)

            # 构建 dashscope 请求参数
            request_params = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "result_format": "message",
            }

            if stop:
                request_params["stop"] = stop

            logger.debug(
                f"Qwen: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(messages)}"
            )

            # dashscope 的 call 方法是同步的，使用线程池执行
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._generation.call(**request_params)
            )

            latency_ms = self._measure_latency(start_time)

            # 解析响应
            content = ""
            finish_reason = ""

            if hasattr(response, 'output') and response.output:
                if hasattr(response.output, 'choices') and response.output.choices:
                    choice = response.output.choices[0]
                    if hasattr(choice, 'message') and choice.message:
                        content = choice.message.content or ""
                    finish_reason = getattr(choice, 'finish_reason', '') or ""

            usage = {}
            if hasattr(response, 'usage'):
                usage = {
                    "prompt_tokens": getattr(response.usage, 'input_tokens', 0) or 0,
                    "completion_tokens": getattr(response.usage, 'output_tokens', 0) or 0,
                    "total_tokens": getattr(response.usage, 'total_tokens', 0) or 0,
                }

            model_response = ModelResponse(
                content=content,
                model=self.config.model_name,
                provider=ModelProvider.QWEN,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
            )

            logger.info(
                f"Qwen: 响应成功, model={model_response.model}, "
                f"tokens={usage.get('total_tokens', 0)}, "
                f"latency={latency_ms:.0f}ms"
            )

            return model_response

        except AIModelConnectionError:
            raise
        except Exception as e:
            latency_ms = self._measure_latency(start_time)
            error = self._parse_error(e)
            logger.error(
                f"Qwen: 请求失败, error={error}, latency={latency_ms:.0f}ms"
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
            logger.warning("Qwen: api_key 未配置")
            return False

        try:
            if self._client is None:
                self._init_client()

            response = self._generation.call(
                model=self.config.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
                result_format="message",
            )
            self._available = True
            return True

        except Exception as e:
            self._available = False
            logger.warning(f"Qwen: 可用性检查失败: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": "qwen",
            "model": self.config.model_name,
            "available": self._available,
            "supported_models": self.SUPPORTED_MODELS,
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "timeout": self.config.timeout,
            },
        }

    def _parse_error(self, error: Exception) -> AIModelError:
        """解析 Qwen 错误"""
        error_str = str(error)

        if "timeout" in error_str.lower() or "timed out" in error_str.lower():
            return AIModelTimeoutError(
                f"请求超时: {error_str}",
                provider="Qwen"
            )
        elif "rate" in error_str.lower() and "limit" in error_str.lower():
            return AIModelRateLimitError(
                f"请求限流: {error_str}",
                provider="Qwen",
                retry_after=5.0,
            )
        elif "auth" in error_str.lower() or "key" in error_str.lower() or "invalid" in error_str.lower():
            return AIModelConnectionError(
                f"认证失败: {error_str}",
                provider="Qwen"
            )
        elif "connect" in error_str.lower():
            return AIModelConnectionError(
                f"连接失败: {error_str}",
                provider="Qwen"
            )
        else:
            return AIModelError(
                f"请求失败: {error_str}",
                provider="Qwen"
            )
