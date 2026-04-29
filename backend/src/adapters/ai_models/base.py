# src/adapters/ai_models/base.py
# AI模型适配器基类 - 定义统一的AI模型接口规范

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """AI模型供应商枚举"""
    OPENAI = "openai"
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    SEED = "seed"
    MINIMAX = "minimax"
    QWEN = "qwen"
    SILICONFLOW = "siliconflow"
    ZHIPU = "zhipu"
    QIANFAN = "qianfan"
    MOONSHOT = "moonshot"
    OLLAMA = "ollama"


# ---------------------------------------------------------------------------
# 各模型定价 (每百万 token, USD)
# ---------------------------------------------------------------------------

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    # Claude
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen
    "qwen-max": {"input": 1.6, "output": 4.8},
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen-turbo": {"input": 0.3, "output": 0.6},
    # 默认
    "default": {"input": 1.0, "output": 3.0},
}


@dataclass
class ModelResponse:
    """AI模型响应数据类"""
    content: str
    model: str
    provider: ModelProvider
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = ""
    raw_response: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider.value,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
        }


@dataclass
class ModelConfig:
    """AI模型配置数据类"""
    provider: ModelProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "provider": self.provider.value,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }


class AIModelError(Exception):
    """AI模型适配器基础异常"""
    def __init__(self, message: str, provider: str = "", code: str = ""):
        self.provider = provider
        self.code = code
        super().__init__(f"[{provider}] {message}" if provider else message)


class AIModelConnectionError(AIModelError):
    """AI模型连接异常"""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, provider=provider, code="CONNECTION_ERROR")


class AIModelRateLimitError(AIModelError):
    """AI模型限流异常"""
    def __init__(self, message: str, provider: str = "", retry_after: float = 0):
        self.retry_after = retry_after
        super().__init__(message, provider=provider, code="RATE_LIMIT")


class AIModelTimeoutError(AIModelError):
    """AI模型超时异常"""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, provider=provider, code="TIMEOUT")


class BaseAIModelAdapter(ABC):
    """
    AI模型适配器抽象基类

    所有AI模型适配器必须继承此类并实现所有抽象方法。
    提供统一的AI模型调用接口规范。
    """

    def __init__(self, config: ModelConfig):
        """
        初始化AI模型适配器

        Args:
            config: 模型配置
        """
        self.config = config
        self._available = False

    @property
    def provider(self) -> ModelProvider:
        """返回模型供应商"""
        return self.config.provider

    @property
    def model_name(self) -> str:
        """返回模型名称"""
        return self.config.model_name

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ModelResponse:
        """
        发送对话消息

        Args:
            messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]
            **kwargs: 额外参数（temperature, max_tokens 等）

        Returns:
            ModelResponse: 模型响应

        Raises:
            AIModelError: 调用失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs
    ) -> ModelResponse:
        """
        使用系统提示词发送消息

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            **kwargs: 额外参数

        Returns:
            ModelResponse: 模型响应

        Raises:
            AIModelError: 调用失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查模型是否可用

        Returns:
            bool: 模型是否可用
        """
        raise NotImplementedError

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息

        Returns:
            Dict[str, Any]: 模型信息字典
        """
        raise NotImplementedError

    # ==================== 工具方法 ====================

    def _build_messages(
        self,
        system_prompt: Optional[str] = None,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """构建消息列表"""
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        if messages:
            result.extend(messages)
        if user_message:
            result.append({"role": "user", "content": user_message})
        return result

    def _measure_latency(self, start_time: float) -> float:
        """计算延迟（毫秒）"""
        return (time.time() - start_time) * 1000

    @staticmethod
    def calculate_cost(
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """计算 AI 调用成本。

        Args:
            model:         模型名称。
            input_tokens:  输入 token 数。
            output_tokens: 输出 token 数。

        Returns:
            成本（美元）。
        """
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"provider={self.provider.value} "
            f"model={self.model_name} "
            f"available={self._available}>"
        )


# ===========================================================================
# OpenAICompatibleAdapter - OpenAI 兼容适配器基类
# ===========================================================================


class OpenAICompatibleAdapter(BaseAIModelAdapter):
    """
    OpenAI 兼容适配器基类

    适用于所有兼容 OpenAI API 格式的 AI 提供商。
    子类只需定义 SUPPORTED_MODELS 和 DEFAULT_BASE_URL 即可。

    支持的提供商: OpenAI, DeepSeek, Seed(豆包), MiniMax,
    SiliconFlow(硅基流动), Zhipu(智谱), Moonshot(月之暗面) 等。
    """

    # 子类应覆盖这些类属性
    SUPPORTED_MODELS: List[str] = []
    DEFAULT_BASE_URL: str = ""
    PROVIDER_NAME: str = ""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._async_client = None
        self._client = None

        # 设置默认 base_url
        if not self.config.base_url and self.DEFAULT_BASE_URL:
            self.config.base_url = self.DEFAULT_BASE_URL

    def _init_client(self):
        """初始化 OpenAI 兼容客户端"""
        try:
            from openai import OpenAI, AsyncOpenAI

            client_kwargs = {
                "api_key": self.config.api_key,
                "timeout": self.config.timeout,
            }

            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url

            self._client = OpenAI(**client_kwargs)
            self._async_client = AsyncOpenAI(**client_kwargs)

            logger.info(
                f"{self.PROVIDER_NAME}: 客户端初始化成功, "
                f"model={self.config.model_name}, "
                f"base_url={self.config.base_url}"
            )

        except ImportError:
            raise AIModelConnectionError(
                "openai SDK 未安装，请执行: pip install openai",
                provider=self.PROVIDER_NAME
            )
        except Exception as e:
            raise AIModelConnectionError(
                f"初始化客户端失败: {e}",
                provider=self.PROVIDER_NAME
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

            logger.debug(
                f"{self.PROVIDER_NAME}: 发送请求, model={self.config.model_name}, "
                f"messages_count={len(messages)}"
            )

            response = await self._async_client.chat.completions.create(**request_params)

            latency_ms = self._measure_latency(start_time)

            # 解析响应
            choice = response.choices[0] if response.choices else None
            content = choice.message.content if choice else ""
            finish_reason = choice.finish_reason if choice else ""

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
                provider=self.config.provider,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason or "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

            logger.info(
                f"{self.PROVIDER_NAME}: 响应成功, model={model_response.model}, "
                f"tokens={usage.get('total_tokens', 0)}, "
                f"latency={latency_ms:.0f}ms, cost=${cost:.6f}"
            )

            return model_response

        except AIModelConnectionError:
            raise
        except Exception as e:
            latency_ms = self._measure_latency(start_time)
            error = self._parse_error(e)
            logger.error(
                f"{self.PROVIDER_NAME}: 请求失败, error={error}, latency={latency_ms:.0f}ms"
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
            logger.warning(f"{self.PROVIDER_NAME}: api_key 未配置")
            return False

        try:
            if self._client is None:
                self._init_client()

            response = self._client.chat.completions.create(
                model=self.config.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            self._available = True
            return True

        except Exception as e:
            self._available = False
            logger.warning(f"{self.PROVIDER_NAME}: 可用性检查失败: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        info = {
            "provider": self.PROVIDER_NAME,
            "model": self.config.model_name,
            "available": self._available,
            "supported_models": self.SUPPORTED_MODELS,
            "config": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "timeout": self.config.timeout,
            },
        }
        if self.config.base_url:
            info["base_url"] = self.config.base_url
        return info

    def _parse_error(self, error: Exception) -> AIModelError:
        """解析错误"""
        error_str = str(error)
        provider = self.PROVIDER_NAME

        if "timeout" in error_str.lower() or "timed out" in error_str.lower():
            return AIModelTimeoutError(
                f"请求超时: {error_str}",
                provider=provider
            )
        elif "rate" in error_str.lower() and "limit" in error_str.lower():
            retry_after = 0
            try:
                retry_after = float(error_str.split("retry after")[1].strip().split()[0])
            except (IndexError, ValueError):
                retry_after = 5.0
            return AIModelRateLimitError(
                f"请求限流: {error_str}",
                provider=provider,
                retry_after=retry_after,
            )
        elif "auth" in error_str.lower() or "key" in error_str.lower():
            return AIModelConnectionError(
                f"认证失败: {error_str}",
                provider=provider
            )
        elif "connect" in error_str.lower():
            return AIModelConnectionError(
                f"连接失败: {error_str}",
                provider=provider
            )
        else:
            return AIModelError(
                f"请求失败: {error_str}",
                provider=provider
            )
