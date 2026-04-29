"""pytest 配置和共享 fixtures

提供异步测试支持、测试数据库、mock 数据等公共 fixtures。
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from typing import Any, Dict, Generator, Optional

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# 事件循环策略
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """创建 session 级别的事件循环，供所有异步测试共享。"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Mock 数据工厂
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_account_data() -> Dict[str, Any]:
    """生成模拟账户数据。"""
    return {
        "account_id": "test_account_001",
        "broker": "paper_broker",
        "account_type": "paper",
        "total_value": 1_000_000.0,
        "cash": 800_000.0,
        "market_value": 200_000.0,
        "available_cash": 800_000.0,
        "created_at": datetime(2025, 1, 1, 9, 30, 0),
        "updated_at": datetime(2025, 1, 15, 15, 0, 0),
    }


@pytest.fixture
def mock_position_data() -> Dict[str, Any]:
    """生成模拟持仓数据。"""
    return {
        "symbol": "AAPL",
        "quantity": 100.0,
        "avg_cost": 150.0,
        "current_price": 155.0,
        "market_value": 15500.0,
        "unrealized_pnl": 500.0,
        "unrealized_pnl_pct": 0.0333,
        "account_id": "test_account_001",
        "created_at": datetime(2025, 1, 5, 10, 0, 0),
        "updated_at": datetime(2025, 1, 15, 15, 0, 0),
    }


@pytest.fixture
def mock_order_data() -> Dict[str, Any]:
    """生成模拟订单数据。"""
    return {
        "order_id": str(uuid.uuid4()),
        "symbol": "AAPL",
        "side": "buy",
        "order_type": "limit",
        "quantity": 100.0,
        "price": 150.0,
        "status": "pending",
        "filled_quantity": 0.0,
        "filled_price": 0.0,
        "fee": 0.0,
        "created_at": datetime(2025, 1, 15, 10, 0, 0),
        "filled_at": None,
        "account_id": "test_account_001",
        "broker": "paper_broker",
    }


@pytest.fixture
def mock_decision_data() -> Dict[str, Any]:
    """生成模拟决策数据。"""
    return {
        "decision_id": str(uuid.uuid4()),
        "timestamp": datetime(2025, 1, 15, 10, 0, 0),
        "model": "gpt-4o",
        "provider": "openai",
        "action": "buy",
        "symbol": "AAPL",
        "quantity": 100.0,
        "price": 150.0,
        "confidence": 0.85,
        "reasoning": "技术指标显示上升趋势，均线金叉",
        "raw_response": '{"action": "buy", "symbol": "AAPL", "quantity": 100}',
        "executed": False,
        "execution_result": None,
        "latency_ms": 1200,
    }


@pytest.fixture
def mock_quote_data() -> Dict[str, Any]:
    """生成模拟行情数据。"""
    return {
        "symbol": "AAPL",
        "open": 148.0,
        "high": 152.0,
        "low": 147.5,
        "close": 151.0,
        "volume": 1_000_000.0,
        "timestamp": datetime(2025, 1, 15, 15, 0, 0),
    }


@pytest.fixture
def mock_kline_data() -> Dict[str, Any]:
    """生成模拟K线数据。"""
    return {
        "symbol": "AAPL",
        "interval": "1d",
        "open": 148.0,
        "high": 152.0,
        "low": 147.5,
        "close": 151.0,
        "volume": 1_000_000.0,
        "timestamp": datetime(2025, 1, 15, 9, 30, 0),
    }


@pytest.fixture
def mock_market_prices() -> Dict[str, float]:
    """生成模拟市场价格字典。"""
    return {
        "AAPL": 151.0,
        "GOOGL": 2800.0,
        "MSFT": 380.0,
        "TSLA": 250.0,
        "AMZN": 3500.0,
    }


@pytest.fixture
def mock_ai_response_buy() -> str:
    """模拟 AI 模型返回的买入决策 JSON。"""
    return (
        '{"action": "buy", "symbol": "AAPL", "quantity": 100, '
        '"price": 150.0, "confidence": 0.85, '
        '"reasoning": "均线金叉，MACD向上，建议买入"}'
    )


@pytest.fixture
def mock_ai_response_sell() -> str:
    """模拟 AI 模型返回的卖出决策 JSON。"""
    return (
        '{"action": "sell", "symbol": "AAPL", "quantity": 50, '
        '"confidence": 0.75, '
        '"reasoning": "RSI超买，均线死叉，建议减仓"}'
    )


@pytest.fixture
def mock_ai_response_hold() -> str:
    """模拟 AI 模型返回的持有决策 JSON。"""
    return (
        '{"action": "hold", "symbol": "AAPL", "confidence": 0.5, '
        '"reasoning": "趋势不明朗，建议观望"}'
    )


@pytest.fixture
def mock_ai_response_natural_language() -> str:
    """模拟 AI 模型返回的自然语言决策。"""
    return (
        "根据当前技术分析，AAPL 的 5 日均线已上穿 20 日均线形成金叉，"
        "MACD 柱状图由负转正，RSI 在 55 附近，成交量较前日放大 1.8 倍。"
        "综合判断建议买入 100 股，置信度较高。"
    )


# ===========================================================================
# Phase 5 新增 fixtures
# ===========================================================================


@pytest.fixture
def app() -> FastAPI:
    """创建测试用 FastAPI 应用实例。

    不包含 lifespan（避免数据库初始化），仅注册路由。
    """
    from src.api.routes import (
        account_router,
        ai_router,
        config_router,
        logs_router,
        strategy_router,
        trading_router,
    )

    application = FastAPI()
    application.include_router(trading_router)
    application.include_router(strategy_router)
    application.include_router(logs_router)
    application.include_router(account_router)
    application.include_router(ai_router)
    application.include_router(config_router)

    # 健康检查
    @application.get("/health")
    async def health():
        return {"status": "healthy"}

    return application


@pytest.fixture
def client(app) -> TestClient:
    """创建 FastAPI TestClient。"""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
async def db_session():
    """创建异步数据库测试会话。

    使用内存 SQLite 数据库，每个测试独立。
    """
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import StaticPool

    from src.database.schema import Base

    # 使用内存 SQLite 数据库
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建会话工厂
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def mock_agent_engine() -> MagicMock:
    """创建 mock 的 AIAgentEngine。

    模拟所有主要方法，供路由测试使用。
    """
    import json
    from src.models.decision import Decision, DecisionAction

    engine = MagicMock()

    # 模拟 make_decision
    decision = Decision(
        decision_id=str(uuid.uuid4()),
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        model="gpt-4o",
        provider="openai",
        action=DecisionAction.BUY,
        symbol="AAPL",
        quantity=100,
        price=150.0,
        confidence=0.85,
        reasoning="均线金叉，MACD向上",
        latency_ms=1200,
    )
    engine.make_decision = AsyncMock(return_value=decision)

    # 模拟 make_decision_multi_model
    multi_decision = Decision(
        decision_id=str(uuid.uuid4()),
        timestamp=datetime(2025, 1, 15, 10, 0, 0),
        model="multi_model",
        provider="multi",
        action=DecisionAction.BUY,
        symbol="AAPL",
        quantity=100,
        price=150.0,
        confidence=0.75,
        reasoning="[多模型-多数投票] 动作=buy",
        raw_response=json.dumps([
            {"model": "gpt-4o", "action": "buy", "confidence": 0.85, "symbol": "AAPL"},
        ]),
        latency_ms=2500,
    )
    engine.make_decision_multi_model = AsyncMock(return_value=multi_decision)

    # 模拟 list_models
    engine.list_models = MagicMock(return_value=[
        {"name": "gpt-4o", "provider": "openai", "model": "gpt-4o", "available": "True"},
        {"name": "deepseek-chat", "provider": "deepseek", "model": "deepseek-chat", "available": "True"},
    ])

    # 模拟其他方法
    engine.register_model = MagicMock()
    engine.unregister_model = MagicMock()
    engine.get_model = MagicMock(return_value=None)
    engine.get_decision_history = MagicMock(return_value=[])
    engine.clear_history = MagicMock()

    return engine


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """创建有效的 JWT 认证头。

    生成一个包含 testuser 信息的 JWT token，
    用于测试需要认证的 API 端点。
    """
    from src.api.auth import create_access_token

    token = create_access_token(
        data={"sub": "testuser", "role": "user"},
        expires_delta=timedelta(minutes=60),
    )

    return {"Authorization": f"Bearer {token}"}
