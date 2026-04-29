"""
核心模块 - 交易引擎、事件总线、AI Agent引擎、模拟交易
"""

# AI Agent 引擎
from src.core.agent_engine import (
    AIAgentEngine,
    ContextBuilder,
    DecisionHistoryEntry,
    DecisionParser,
    MarketContext,
    AccountContext,
    ParsedDecision,
    PromptManager,
)

# 交易引擎
from src.core.trading_engine import (
    InsufficientPositionError,
    OrderCancelError,
    OrderError,
    OrderManager,
    OrderRejectedError,
    PositionError,
    PositionManager,
    RiskAlert,
    RiskConfig,
    RiskError,
    RiskLimitExceededError,
    RiskManager,
    TradingEngine,
)

# 模拟交易引擎
from src.core.paper_trading import (
    AccountNotFoundError,
    InsufficientFundsError as PaperInsufficientFundsError,
    OrderNotFoundError,
    PaperTradingConfig,
    PaperTradingEngine,
    PaperTradingError,
    TradeRecord,
)

# 事件总线
from src.core.event_bus import (
    AlertEvent,
    DecisionEvent,
    Event,
    EventBus,
    EventType,
    HandlerInfo,
    MarketEvent,
    OrderEvent,
    SyncHandler,
    AsyncHandler,
    EventHandler,
    get_event_bus,
    reset_event_bus,
)

__all__ = [
    # AI Agent 引擎
    "AIAgentEngine",
    "PromptManager",
    "ContextBuilder",
    "DecisionParser",
    "ParsedDecision",
    "MarketContext",
    "AccountContext",
    "DecisionHistoryEntry",
    # 交易引擎
    "OrderManager",
    "PositionManager",
    "RiskManager",
    "RiskConfig",
    "RiskAlert",
    "RiskError",
    "RiskLimitExceededError",
    "TradingEngine",
    "OrderError",
    "OrderRejectedError",
    "OrderCancelError",
    "PositionError",
    "InsufficientPositionError",
    # 模拟交易引擎
    "PaperTradingEngine",
    "PaperTradingConfig",
    "PaperTradingError",
    "TradeRecord",
    "AccountNotFoundError",
    "OrderNotFoundError",
    "PaperInsufficientFundsError",
    # 事件总线
    "EventBus",
    "Event",
    "EventType",
    "MarketEvent",
    "OrderEvent",
    "DecisionEvent",
    "AlertEvent",
    "HandlerInfo",
    "SyncHandler",
    "AsyncHandler",
    "EventHandler",
    "get_event_bus",
    "reset_event_bus",
]
