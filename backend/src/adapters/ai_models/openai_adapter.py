# src/adapters/ai_models/openai_adapter.py
# OpenAI 适配器 - 支持 GPT-4o, GPT-4-turbo 等模型

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class OpenAIAdapter(OpenAICompatibleAdapter):
    """
    OpenAI 适配器

    支持 GPT-4o, GPT-4-turbo, GPT-3.5-turbo 等模型。
    继承 OpenAICompatibleAdapter，使用 openai 官方 Python SDK。
    """

    SUPPORTED_MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
    ]

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    PROVIDER_NAME = "OpenAI"
