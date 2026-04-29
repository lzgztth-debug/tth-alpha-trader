# src/adapters/__init__.py
# 适配器层包初始化

from src.adapters.brokers import (
    BaseBrokerAdapter,
    BrokerError,
    BrokerConnectionError,
    BrokerOrderError,
)
from src.adapters.market_data import BaseMarketDataAdapter
from src.adapters.ai_models import (
    BaseAIModelAdapter,
    ModelProvider,
    ModelConfig,
    ModelResponse,
)

__all__ = [
    # Broker Adapters
    "BaseBrokerAdapter",
    "BrokerError",
    "BrokerConnectionError",
    "BrokerOrderError",
    # Market Data Adapters
    "BaseMarketDataAdapter",
    # AI Model Adapters
    "BaseAIModelAdapter",
    "ModelProvider",
    "ModelConfig",
    "ModelResponse",
]
