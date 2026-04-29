# src/adapters/ai_models/moonshot_adapter.py
# 月之暗面 (Moonshot/Kimi) 适配器 - 兼容 OpenAI API 格式

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class MoonshotAdapter(OpenAICompatibleAdapter):
    """
    月之暗面 (Moonshot/Kimi) 适配器

    月之暗面大模型，兼容 OpenAI API 格式。
    支持 moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k 等模型。
    """

    SUPPORTED_MODELS = [
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
    ]

    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    PROVIDER_NAME = "Moonshot"
