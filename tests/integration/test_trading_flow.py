"""端到端交易流程集成测试

测试完整的 AI 决策 -> 风控检查 -> 订单创建 -> 持仓更新流程。
使用 mock 的 AI 适配器和数据库。
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agent_engine import (
    AIAgentEngine,
    ContextBuilder,
    MarketContext,
    AccountContext,
)
from src.core.trading_engine import (
    TradingEngine,
    RiskManager,
    RiskConfig,
    OrderStatus,
)
from src.adapters.ai_models.base import (
    ModelConfig,
    ModelProvider,
    ModelResponse,
)
from src.adapters.ai_models.openai_adapter import OpenAIAdapter
from src.models.account import Account, AccountType
from src.models.decision import Decision, DecisionAction
from src.models.order import OrderSide, OrderType


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def trading_engine():
    """创建交易引擎。"""
    return TradingEngine(mode="paper")


@pytest.fixture
def account():
    """创建测试账户。"""
    return Account(
        account_id="e2e_test_001",
        broker="paper_broker",
        account_type=AccountType.PAPER,
        total_value=1_000_000.0,
        cash=800_000.0,
        market_value=200_000.0,
        available_cash=800_000.0,
    )


@pytest.fixture
def agent_engine():
    """创建 AI Agent 引擎。"""
    return AIAgentEngine()


@pytest.fixture
def mock_ai_adapter():
    """创建 mock 的 AI 适配器。"""
    config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
        api_key="test-key",
    )
    adapter = OpenAIAdapter(config)

    # Mock chat_with_system
    adapter.chat_with_system = AsyncMock(
        return_value=ModelResponse(
            content=json.dumps({
                "action": "buy",
                "symbol": "AAPL",
                "quantity": 100,
                "price": 150.0,
                "confidence": 0.85,
                "reasoning": "均线金叉，MACD向上，建议买入",
            }),
            model="gpt-4o",
            provider=ModelProvider.OPENAI,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_ms=800.0,
            finish_reason="stop",
        )
    )
    adapter.is_available = MagicMock(return_value=True)
    adapter._available = True

    return adapter


@pytest.fixture
def mock_sell_adapter():
    """创建 mock 的卖出 AI 适配器。"""
    config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
        api_key="test-key",
    )
    adapter = OpenAIAdapter(config)

    adapter.chat_with_system = AsyncMock(
        return_value=ModelResponse(
            content=json.dumps({
                "action": "sell",
                "symbol": "AAPL",
                "quantity": 50,
                "confidence": 0.8,
                "reasoning": "RSI超买，建议减仓",
            }),
            model="gpt-4o",
            provider=ModelProvider.OPENAI,
            usage={"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
            latency_ms=700.0,
            finish_reason="stop",
        )
    )
    adapter.is_available = MagicMock(return_value=True)
    adapter._available = True

    return adapter


@pytest.fixture
def mock_hold_adapter():
    """创建 mock 的持有 AI 适配器。"""
    config = ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
        api_key="test-key",
    )
    adapter = OpenAIAdapter(config)

    adapter.chat_with_system = AsyncMock(
        return_value=ModelResponse(
            content=json.dumps({
                "action": "hold",
                "symbol": "AAPL",
                "confidence": 0.5,
                "reasoning": "趋势不明朗，建议观望",
            }),
            model="gpt-4o",
            provider=ModelProvider.OPENAI,
            usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
            latency_ms=600.0,
            finish_reason="stop",
        )
    )
    adapter.is_available = MagicMock(return_value=True)
    adapter._available = True

    return adapter


# ===========================================================================
# 完整交易流程测试: AI 决策 -> 风控检查 -> 订单创建 -> 持仓更新
# ===========================================================================


class TestEndToEndTradingFlow:
    """端到端交易流程测试。"""

    @pytest.mark.asyncio
    async def test_buy_flow_complete(
        self, agent_engine, mock_ai_adapter, trading_engine, account
    ):
        """测试完整买入流程: AI 决策 -> 风控 -> 下单 -> 持仓更新。"""
        # 1. 注册 AI 模型
        agent_engine.register_model("gpt-4o", mock_ai_adapter)

        # 2. 设置市场上下文
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=150.0,
            open_price=148.0,
            high_price=152.0,
            low_price=147.0,
            volume=1_000_000.0,
            change_pct=1.35,
        ))

        # 3. 设置账户上下文
        agent_engine.context_builder.set_account_context(AccountContext(
            account_id="e2e_test_001",
            cash=800_000.0,
            available_cash=800_000.0,
            total_value=1_000_000.0,
            market_value=200_000.0,
        ))

        # 4. AI 决策
        decision = await agent_engine.make_decision(
            symbol="AAPL",
            account_id="e2e_test_001",
            model_name="gpt-4o",
        )

        # 验证 AI 决策
        assert decision is not None
        assert decision.action == DecisionAction.BUY
        assert decision.symbol == "AAPL"
        assert decision.quantity == 100
        assert decision.price == 150.0
        assert decision.confidence == 0.85
        assert decision.model == "gpt-4o"

        # 5. 注册账户并更新价格
        trading_engine.register_account(account)
        trading_engine.update_market_price("AAPL", 150.0)

        # 6. 执行决策 (包含风控检查)
        order = trading_engine.execute_decision(decision, account_id="e2e_test_001")

        # 验证订单创建
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100.0
        assert order.filled_price > 0

        # 7. 验证持仓更新
        positions = trading_engine.get_positions("e2e_test_001")
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 100.0
        assert positions[0].avg_cost > 0

    @pytest.mark.asyncio
    async def test_sell_flow_complete(
        self, agent_engine, mock_sell_adapter, trading_engine, account
    ):
        """测试完整卖出流程: AI 决策 -> 风控 -> 下单 -> 持仓更新。"""
        # 1. 准备: 注册账户、建仓
        trading_engine.register_account(account)
        trading_engine.update_market_price("AAPL", 150.0)

        buy_order = trading_engine.execute_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            account_id="e2e_test_001",
        )
        assert buy_order.status == OrderStatus.FILLED

        # 2. 注册 AI 模型 (卖出)
        agent_engine.register_model("gpt-4o", mock_sell_adapter)
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=155.0,
        ))

        # 3. AI 卖出决策
        decision = await agent_engine.make_decision(
            symbol="AAPL",
            account_id="e2e_test_001",
            model_name="gpt-4o",
        )

        assert decision.action == DecisionAction.SELL
        assert decision.quantity == 50

        # 4. 执行卖出
        trading_engine.update_market_price("AAPL", 155.0)
        sell_order = trading_engine.execute_decision(decision, account_id="e2e_test_001")

        # 验证卖出订单
        assert sell_order is not None
        assert sell_order.side == OrderSide.SELL
        assert sell_order.status == OrderStatus.FILLED
        assert sell_order.filled_quantity == 50.0

        # 5. 验证持仓减少
        positions = trading_engine.get_positions("e2e_test_001")
        assert len(positions) == 1
        assert positions[0].quantity == 50.0

    @pytest.mark.asyncio
    async def test_hold_flow_no_order(
        self, agent_engine, mock_hold_adapter, trading_engine, account
    ):
        """测试持有决策不产生订单。"""
        # 1. 准备
        trading_engine.register_account(account)
        agent_engine.register_model("gpt-4o", mock_hold_adapter)
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=150.0,
        ))

        # 2. AI 持有决策
        decision = await agent_engine.make_decision(
            symbol="AAPL",
            account_id="e2e_test_001",
            model_name="gpt-4o",
        )

        assert decision.action == DecisionAction.HOLD

        # 3. 执行持有决策 (不应产生订单)
        order = trading_engine.execute_decision(decision, account_id="e2e_test_001")
        assert order is None

        # 4. 持仓应为空
        positions = trading_engine.get_positions("e2e_test_001")
        assert len(positions) == 0


# ===========================================================================
# 风控拦截流程测试
# ===========================================================================


class TestRiskControlInFlow:
    """风控在交易流程中的拦截测试。"""

    @pytest.mark.asyncio
    async def test_risk_blocks_large_order(
        self, agent_engine, mock_ai_adapter, trading_engine, account
    ):
        """测试风控拦截大额订单。"""
        # 设置严格的风控
        strict_config = RiskConfig(max_order_value=1000.0)
        trading_engine.risk_manager.update_config(strict_config)

        # 注册账户
        trading_engine.register_account(account)
        trading_engine.update_market_price("AAPL", 150.0)

        # AI 决策买入 100 股 (100 * 150 = 15000 > 1000)
        agent_engine.register_model("gpt-4o", mock_ai_adapter)
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=150.0,
        ))

        decision = await agent_engine.make_decision(
            symbol="AAPL",
            account_id="e2e_test_001",
            model_name="gpt-4o",
        )

        assert decision.action == DecisionAction.BUY

        # 执行时应被风控拦截
        from src.core.trading_engine import RiskLimitExceededError
        with pytest.raises(RiskLimitExceededError):
            trading_engine.execute_decision(decision, account_id="e2e_test_001")


# ===========================================================================
# 决策历史记录测试
# ===========================================================================


class TestDecisionHistoryInFlow:
    """决策历史记录在流程中的测试。"""

    @pytest.mark.asyncio
    async def test_decision_recorded_in_history(
        self, agent_engine, mock_ai_adapter
    ):
        """测试决策被记录到历史中。"""
        agent_engine.register_model("gpt-4o", mock_ai_adapter)
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=150.0,
        ))

        await agent_engine.make_decision(
            symbol="AAPL",
            model_name="gpt-4o",
        )

        history = agent_engine.get_decision_history()
        assert len(history) == 1
        assert history[0].decision.action == DecisionAction.BUY
        assert history[0].model_name == "gpt-4o"
        assert history[0].model_provider == "openai"

    @pytest.mark.asyncio
    async def test_multiple_decisions_in_history(
        self, agent_engine, mock_ai_adapter, mock_hold_adapter
    ):
        """测试多次决策被记录到历史中。"""
        agent_engine.register_model("gpt-4o", mock_ai_adapter)
        agent_engine.context_builder.set_market_context(MarketContext(
            symbol="AAPL",
            current_price=150.0,
        ))

        await agent_engine.make_decision(symbol="AAPL", model_name="gpt-4o")

        # 替换为 hold 适配器
        agent_engine._models["gpt-4o"] = mock_hold_adapter
        await agent_engine.make_decision(symbol="AAPL", model_name="gpt-4o")

        history = agent_engine.get_decision_history()
        assert len(history) == 2
