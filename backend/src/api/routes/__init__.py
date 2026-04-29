"""API路由定义

导出所有API路由模块。
"""

from src.api.routes.account import router as account_router
from src.api.routes.logs import router as logs_router
from src.api.routes.strategy import router as strategy_router
from src.api.routes.trading import router as trading_router
from src.api.routes.ai import router as ai_router
from src.api.routes.config_api import router as config_router

__all__ = [
    "trading_router",
    "strategy_router",
    "logs_router",
    "account_router",
    "ai_router",
    "config_router",
]
