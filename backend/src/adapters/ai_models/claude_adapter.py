# src/adapters/ai_models/claude_adapter.py
# Claude 适配器 - 使用 anthropic SDK 支持 Claude 3.5 Sonnet 等模型

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


class ClaudeAdapter(BaseAIModelAdapter):
    """
    Claude 适配器

    使用 anthropic 官方 Python SDK，支持 Claude 3.5 Sonnet, Claude 3 Opus 等模型。

    配置参数:
        provider: ModelProvider.CLAUDE
        model_name: 模型名称（如 claude-sonnet-4-20250514, claude-3-5-sonnet-20241022）
        api_key: Anthropic API Key
        base_url: 自定义 API 地址（可选）
        temperature: 温度参数，默认 0.7
        max_tokens: 最大输出 token 数，默认 4096
        timeout: 超时时间（秒），默认 60
    """

    # 支持的模型列表
    SUPPORTED_MODELS = [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None
        self._async_client = None

    def _init_client(self):
        """初始化 Anthropic 客户端"""
        try:
            import anthropic

            client_kwargs = {
                "api_key": self.config.api_key,
                "timeout": self.config.timeout,
            }

            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url

            self._client = anthropic.Anthropic(**client_kwargs)
            self._async_client = anthropic.AsyncAnthropic(**client_kwargs)

            logger.info(f"Claude: 客户端初始化成功, model={self.config.model_name}")

        except ImportError:
            raise AIModelConnectionError(
                "anthropic SDK 未安装，请执行: pip install anthropic",
                provider="Claude"
            )
        except Exception as e:
            raise AIModelConnectionError(
                f"初始化客户端失败: {e}",
                provider="Claude"
            )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """发送对话消息"""
        start_time = time.time()

        try:
            if self._async_client is None:
                self._init_client()

            # Claude API 需要将 system 消息单独提取
            system_prompt = ""
            chat_messages = []
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                else:
                    chat_messages.append(msg)

            # 合并参数
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
            top_p = kwargs.get('top_p', self.config.top_p)
            stop_sequences = kwargs.get('stop', self.config.stop)

            # 构建 API 请求参数
            request_params = {
                "model": self.config.model_name,
                "messages": chat_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

            if system_prompt:
                request_params["system"] = system_prompt

            if stop_sequences:
                request_params["stop_sequences"] = stop_sequences

            logger.debug(
                f"Claude: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(chat_messages)}"
            )

            response = await self._async_client.messages.create(**request_params)

            latency_ms = self._measure_latency(start_time)

            # 解析响应
            content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    content += block.text

            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens or 0,
                    "completion_tokens": response.usage.output_tokens or 0,
                    "total_tokens": (
                        (response.usage.input_tokens or 0) +
                        (response.usage.output_tokens or 0)
                    ),
                }

            model_response = ModelResponse(
                content=content,
                model=response.model or self.config.model_name,
                provider=ModelProvider.CLAUDE,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=response.stop_reason or "",
            )

            logger.info(
                f"Claude: 响应成功, model={model_response.model}, "
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
                f"Claude: 请求失败, error={error}, latency={latency_ms:.0f}ms"
            )
            raise error

    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs
    ) -> ModelResponse:
        """使用系统提示词发送消息"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.chat(messages, **kwargs)

    def is_available(self) -> bool:
        """检查模型是否可用"""
        if not self.config.api_key:
            logger.warning("Claude: api_key 未配置")
            return False

        try:
            if self._client is None:
                self._init_client()

            response = self._client.messages.create(
                model=self.config.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            self._available = True
            return True

        except Exception as e:
            self._available = False
            logger.warning(f"Claude: 可用性检查失败: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": "claude",
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
        """解析 Claude 错误"""
        error_str = str(error)

        if "timeout" in error_str.lower() or "timed out" in error_str.lower():
            return AIModelTimeoutError(
                f"请求超时: {error_str}",
                provider="Claude"
            )
        elif "rate" in error_str.lower():
            retry_after = 0
            try:
                # anthropic SDK 可能在错误中包含 retry-after 信息
                if hasattr(error, 'response') and error.response:
                    retry_header = error.response.headers.get('retry-after')
                    if retry_header:
                        retry_after = float(retry_header)
            except Exception:
                retry_after = 5.0
            return AIModelRateLimitError(
                f"请求限流: {error_str}",
                provider="Claude",
                retry_after=retry_after,
            )
        elif "auth" in error_str.lower() or "key" in error_str.lower():
            return AIModelConnectionError(
                f"认证失败: {error_str}",
                provider="Claude"
            )
        elif "connect" in error_str.lower():
            return AIModelConnectionError(
                f"连接失败: {error_str}",
                provider="Claude"
            )
        else:
            return AIModelError(
                f"请求失败: {error_str}",
                provider="Claude"
            )
