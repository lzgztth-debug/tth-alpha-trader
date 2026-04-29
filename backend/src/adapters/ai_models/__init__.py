# src/adapters/ai_models/__init__.py
# AI模型适配器包初始化

from src.adapters.ai_models.base import (
    BaseAIModelAdapter,
    OpenAICompatibleAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
    MODEL_PRICING,
)

# 各提供商适配器
from src.adapters.ai_models.openai_adapter import OpenAIAdapter
from src.adapters.ai_models.claude_adapter import ClaudeAdapter
from src.adapters.ai_models.deepseek_adapter import DeepSeekAdapter
from src.adapters.ai_models.qwen_adapter import QwenAdapter
from src.adapters.ai_models.ollama_adapter import OllamaAdapter
from src.adapters.ai_models.seed_adapter import SeedAdapter
from src.adapters.ai_models.minimax_adapter import MiniMaxAdapter
from src.adapters.ai_models.siliconflow_adapter import SiliconFlowAdapter
from src.adapters.ai_models.zhipu_adapter import ZhipuAdapter
from src.adapters.ai_models.qianfan_adapter import QianfanAdapter
from src.adapters.ai_models.moonshot_adapter import MoonshotAdapter


# ---------------------------------------------------------------------------
# ADAPTER_MAP: 提供商名称 -> 适配器类
# ---------------------------------------------------------------------------

ADAPTER_MAP: dict = {
    "openai": OpenAIAdapter,
    "claude": ClaudeAdapter,
    "deepseek": DeepSeekAdapter,
    "qwen": QwenAdapter,
    "ollama": OllamaAdapter,
    "seed": SeedAdapter,
    "minimax": MiniMaxAdapter,
    "siliconflow": SiliconFlowAdapter,
    "zhipu": ZhipuAdapter,
    "qianfan": QianfanAdapter,
    "moonshot": MoonshotAdapter,
}


__all__ = [
    "BaseAIModelAdapter",
    "OpenAICompatibleAdapter",
    "ModelProvider",
    "ModelConfig",
    "ModelResponse",
    "MODEL_PRICING",
    "ADAPTER_MAP",
    "OpenAIAdapter",
    "ClaudeAdapter",
    "DeepSeekAdapter",
    "QwenAdapter",
    "OllamaAdapter",
    "SeedAdapter",
    "MiniMaxAdapter",
    "SiliconFlowAdapter",
    "ZhipuAdapter",
    "QianfanAdapter",
    "MoonshotAdapter",
]
