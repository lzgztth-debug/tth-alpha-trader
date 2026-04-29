# src/adapters/ai_models/zhipu_adapter.py
# 智谱 (GLM) 适配器 - 兼容 OpenAI API 格式

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class ZhipuAdapter(OpenAICompatibleAdapter):
    """
    智谱 (GLM) 适配器

    智谱 AI 大模型，兼容 OpenAI API 格式。
    支持 GLM-4, GLM-4-Plus, GLM-3-Turbo 等模型。
    """

    SUPPORTED_MODELS = [
        "glm-4-plus",
        "glm-4",
        "glm-4-air",
        "glm-4-airx",
        "glm-4-long",
        "glm-4-flash",
        "glm-3-turbo",
    ]

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    PROVIDER_NAME = "Zhipu"
