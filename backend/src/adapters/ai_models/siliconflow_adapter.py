# src/adapters/ai_models/siliconflow_adapter.py
# 硅基流动 (SiliconFlow) 适配器 - 兼容 OpenAI API 格式

from typing import List, Dict, Any

from src.adapters.ai_models.base import (
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)


class SiliconFlowAdapter(OpenAICompatibleAdapter):
    """
    硅基流动 (SiliconFlow) 适配器

    硅基流动大模型推理平台，兼容 OpenAI API 格式。
    支持多种开源模型: Qwen, DeepSeek, Llama 等。
    """

    SUPPORTED_MODELS = [
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "deepseek-ai/DeepSeek-V2.5",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "meta-llama/Meta-Llama-3.1-70B-Instruct",
    ]

    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
    PROVIDER_NAME = "SiliconFlow"
