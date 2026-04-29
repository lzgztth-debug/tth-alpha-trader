# src/adapters/ai_models/minimax_adapter.py
# MiniMax 适配器 - 兼容 OpenAI API 格式

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class MiniMaxAdapter(OpenAICompatibleAdapter):
    """
    MiniMax 适配器

    MiniMax 大模型，兼容 OpenAI API 格式。
    支持 abab6.5s-chat, abab6.5-chat 等模型。
    """

    SUPPORTED_MODELS = [
        "abab6.5s-chat",
        "abab6.5-chat",
        "abab6-chat",
        "MiniMax-Text-01",
    ]

    DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
    PROVIDER_NAME = "MiniMax"
