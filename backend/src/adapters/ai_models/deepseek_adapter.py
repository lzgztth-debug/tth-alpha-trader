# src/adapters/ai_models/deepseek_adapter.py
# DeepSeek 适配器 - 兼容 OpenAI API 格式，支持 DeepSeek-V3 等模型

import time
from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)

import logging

logger = logging.getLogger(__name__)


class DeepSeekAdapter(OpenAICompatibleAdapter):
    """
    DeepSeek 适配器

    DeepSeek API 兼容 OpenAI API 格式，使用 openai SDK 调用。
    支持 DeepSeek-V3, DeepSeek-Chat, DeepSeek-Coder 等模型。
    继承 OpenAICompatibleAdapter，并针对 DeepSeek-Reasoner 模型做特殊处理。
    """

    SUPPORTED_MODELS = [
        "deepseek-chat",
        "deepseek-reasoner",
    ]

    DEFAULT_BASE_URL = "https://api.deepseek.com"
    PROVIDER_NAME = "DeepSeek"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """发送对话消息，针对 DeepSeek-Reasoner 做特殊处理。"""
        start_time = time.time()

        try:
            if self._async_client is None:
                self._init_client()

            # 合并参数
            temperature = kwargs.get('temperature', self.config.temperature)
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
            top_p = kwargs.get('top_p', self.config.top_p)
            frequency_penalty = kwargs.get('frequency_penalty', self.config.frequency_penalty)
            presence_penalty = kwargs.get('presence_penalty', self.config.presence_penalty)
            stop = kwargs.get('stop', self.config.stop)

            request_params = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty,
            }

            if stop:
                request_params["stop"] = stop

            # DeepSeek-Reasoner 模型不支持 temperature 和 top_p
            if self.config.model_name == "deepseek-reasoner":
                request_params.pop("temperature", None)
                request_params.pop("top_p", None)

            logger.debug(
                f"DeepSeek: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(messages)}"
            )

            response = await self._async_client.chat.completions.create(**request_params)

            latency_ms = self._measure_latency(start_time)

            # 解析响应
            choice = response.choices[0] if response.choices else None
            content = choice.message.content if choice else ""
            finish_reason = choice.finish_reason if choice else ""

            # 处理 reasoning_content（DeepSeek-Reasoner 特有）
            reasoning_content = ""
            if choice and hasattr(choice.message, 'reasoning_content'):
                reasoning_content = choice.message.reasoning_content or ""

            usage = {}
            input_tokens = 0
            output_tokens = 0
            if response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
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
                model=response.model or self.config.model_name,
                provider=ModelProvider.DEEPSEEK,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason or "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

            if reasoning_content:
                model_response.raw_response = {
                    "reasoning_content": reasoning_content,
                }

            logger.info(
                f"DeepSeek: 响应成功, model={model_response.model}, "
                f"tokens={usage.get('total_tokens', 0)}, "
                f"latency={latency_ms:.0f}ms, cost=${cost:.6f}"
            )

            return model_response

        except Exception as e:
            latency_ms = self._measure_latency(start_time)
            error = self._parse_error(e)
            logger.error(
                f"DeepSeek: 请求失败, error={error}, latency={latency_ms:.0f}ms"
            )
            raise error
