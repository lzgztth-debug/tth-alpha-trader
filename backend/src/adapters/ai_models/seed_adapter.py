# src/adapters/ai_models/seed_adapter.py
# Seed (豆包) 适配器 - 兼容 OpenAI API 格式

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class SeedAdapter(OpenAICompatibleAdapter):
    """
    Seed (豆包) 适配器

    字节跳动旗下豆包大模型，兼容 OpenAI API 格式。
    支持 doubao-pro-32k, doubao-pro-128k 等模型。
    """

    SUPPORTED_MODELS = [
        "doubao-pro-32k",
        "doubao-pro-128k",
        "doubao-lite-32k",
        "doubao-lite-128k",
    ]

    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    PROVIDER_NAME = "Seed"
