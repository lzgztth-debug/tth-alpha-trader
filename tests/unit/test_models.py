"""数据模型单元测试

测试 Account, Position, Order, Decision, Quote, Kline 的创建和序列化。
"""

import json
from datetime import datetime

import pytest

from src.models.account import (
    Account,
    AccountType,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
)
from src.models.position import (
    Position,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
)
from src.models.order import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    OrderCreate,
    OrderUpdate,
    OrderResponse,
)
from src.models.decision import (
    Decision,
    DecisionAction,
    DecisionCreate,
    DecisionResponse,
)
from src.models.market_data import (
    Quote,
    Kline,
    QuoteResponse,
    KlineResponse,
    MarketSnapshotCreate,
)


# ===========================================================================
# Account 模型测试
# ===========================================================================


class TestAccount:
    """Account 模型测试。"""

    def test_create_account_dataclass(self, mock_account_data):
        """测试 Account dataclass 创建。"""
        account = Account(**mock_account_data)
        assert account.account_id == "test_account_001"
        assert account.broker == "paper_broker"
        assert account.account_type == AccountType.PAPER
        assert account.total_value == 1_000_000.0
        assert account.cash == 800_000.0
        assert account.market_value == 200_000.0
        assert account.available_cash == 800_000.0
        assert account.created_at is not None
        assert account.updated_at is not None

    def test_account_type_enum(self):
        """测试 AccountType 枚举。"""
        assert AccountType.REAL.value == "real"
        assert AccountType.PAPER.value == "paper"

    def test_account_create_schema_valid(self):
        """测试 AccountCreate schema 验证。"""
        data = AccountCreate(
            account_id="paper_001",
            broker="paper_broker",
            account_type=AccountType.PAPER,
            initial_cash=500_000.0,
        )
        assert data.account_id == "paper_001"
        assert data.initial_cash == 500_000.0

    def test_account_create_schema_defaults(self):
        """测试 AccountCreate 默认值。"""
        data = AccountCreate(account_id="test", broker="test_broker")
        assert data.account_type == AccountType.PAPER
        assert data.initial_cash == 1_000_000.0

    def test_account_create_schema_invalid_id_empty(self):
        """测试 AccountCreate 空ID验证失败。"""
        with pytest.raises(Exception):
            AccountCreate(account_id="", broker="test")

    def test_account_create_schema_invalid_cash_negative(self):
        """测试 AccountCreate 负数资金验证失败。"""
        with pytest.raises(Exception):
            AccountCreate(
                account_id="test", broker="test", initial_cash=-100.0
            )

    def test_account_update_schema(self):
        """测试 AccountUpdate schema。"""
        data = AccountUpdate(total_value=1_100_000.0, cash=900_000.0)
        assert data.total_value == 1_100_000.0
        assert data.cash == 900_000.0
        assert data.market_value is None  # 未设置的字段为 None

    def test_account_response_from_dataclass(self, mock_account_data):
        """测试 AccountResponse 从 dataclass 序列化。"""
        account = Account(**mock_account_data)
        response = AccountResponse.model_validate(account, from_attributes=True)
        assert response.account_id == "test_account_001"
        assert response.total_value == 1_000_000.0

    def test_account_response_to_json(self, mock_account_data):
        """测试 AccountResponse JSON 序列化。"""
        account = Account(**mock_account_data)
        response = AccountResponse.model_validate(account, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["account_id"] == "test_account_001"
        assert data["broker"] == "paper_broker"


# ===========================================================================
# Position 模型测试
# ===========================================================================


class TestPosition:
    """Position 模型测试。"""

    def test_create_position_dataclass(self, mock_position_data):
        """测试 Position dataclass 创建。"""
        position = Position(**mock_position_data)
        assert position.symbol == "AAPL"
        assert position.quantity == 100.0
        assert position.avg_cost == 150.0
        assert position.current_price == 155.0
        assert position.market_value == 15500.0
        assert position.unrealized_pnl == 500.0
        assert position.account_id == "test_account_001"

    def test_position_create_schema(self):
        """测试 PositionCreate schema。"""
        data = PositionCreate(
            account_id="test_account_001",
            symbol="GOOGL",
            quantity=50,
            avg_cost=2800.0,
            current_price=2850.0,
        )
        assert data.symbol == "GOOGL"
        assert data.quantity == 50

    def test_position_create_schema_invalid_quantity(self):
        """测试 PositionCreate 非正数量验证失败。"""
        with pytest.raises(Exception):
            PositionCreate(account_id="test", symbol="AAPL", quantity=0)

    def test_position_update_schema(self):
        """测试 PositionUpdate schema。"""
        data = PositionUpdate(current_price=160.0, market_value=16000.0)
        assert data.current_price == 160.0
        assert data.quantity is None

    def test_position_response_from_dataclass(self, mock_position_data):
        """测试 PositionResponse 序列化。"""
        position = Position(**mock_position_data)
        response = PositionResponse.model_validate(position, from_attributes=True)
        assert response.symbol == "AAPL"
        assert response.unrealized_pnl == 500.0

    def test_position_response_to_json(self, mock_position_data):
        """测试 PositionResponse JSON 序列化。"""
        position = Position(**mock_position_data)
        response = PositionResponse.model_validate(position, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert data["quantity"] == 100.0


# ===========================================================================
# Order 模型测试
# ===========================================================================


class TestOrder:
    """Order 模型测试。"""

    def test_create_order_dataclass(self, mock_order_data):
        """测试 Order dataclass 创建。"""
        order = Order(**mock_order_data)
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 100.0
        assert order.price == 150.0
        assert order.status == OrderStatus.PENDING

    def test_order_enums(self):
        """测试 Order 相关枚举。"""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.PARTIAL_FILLED.value == "partial_filled"

    def test_order_create_schema(self):
        """测试 OrderCreate schema。"""
        data = OrderCreate(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=150.0,
            account_id="test_account_001",
        )
        assert data.symbol == "AAPL"
        assert data.side == OrderSide.BUY

    def test_order_create_schema_defaults(self):
        """测试 OrderCreate 默认值。"""
        data = OrderCreate(symbol="AAPL", side=OrderSide.BUY, quantity=100)
        assert data.order_type == OrderType.MARKET
        assert data.price is None
        assert data.account_id is None

    def test_order_create_schema_invalid_quantity(self):
        """测试 OrderCreate 非正数量验证失败。"""
        with pytest.raises(Exception):
            OrderCreate(symbol="AAPL", side=OrderSide.BUY, quantity=-10)

    def test_order_create_schema_limit_without_price(self):
        """测试 OrderCreate 限价单无价格 - schema 允许但引擎会拒绝。"""
        # Pydantic schema 层面不做强制校验（引擎层校验）
        data = OrderCreate(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
        )
        assert data.price is None

    def test_order_update_schema(self):
        """测试 OrderUpdate schema。"""
        data = OrderUpdate(
            status=OrderStatus.FILLED,
            filled_quantity=100.0,
            filled_price=150.5,
            fee=4.5,
        )
        assert data.status == OrderStatus.FILLED
        assert data.filled_quantity == 100.0

    def test_order_response_from_dataclass(self, mock_order_data):
        """测试 OrderResponse 序列化。"""
        order = Order(**mock_order_data)
        response = OrderResponse.model_validate(order, from_attributes=True)
        assert response.symbol == "AAPL"
        assert response.side == OrderSide.BUY
        assert response.status == OrderStatus.PENDING

    def test_order_response_to_json(self, mock_order_data):
        """测试 OrderResponse JSON 序列化。"""
        order = Order(**mock_order_data)
        response = OrderResponse.model_validate(order, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert data["side"] == "buy"
        assert data["order_type"] == "limit"


# ===========================================================================
# Decision 模型测试
# ===========================================================================


class TestDecision:
    """Decision 模型测试。"""

    def test_create_decision_dataclass(self, mock_decision_data):
        """测试 Decision dataclass 创建。"""
        decision = Decision(**mock_decision_data)
        assert decision.action == DecisionAction.BUY
        assert decision.symbol == "AAPL"
        assert decision.quantity == 100.0
        assert decision.confidence == 0.85
        assert decision.model == "gpt-4o"
        assert decision.provider == "openai"
        assert decision.executed is False

    def test_decision_action_enum(self):
        """测试 DecisionAction 枚举。"""
        assert DecisionAction.BUY.value == "buy"
        assert DecisionAction.SELL.value == "sell"
        assert DecisionAction.HOLD.value == "hold"

    def test_decision_create_schema(self):
        """测试 DecisionCreate schema。"""
        data = DecisionCreate(
            model="claude-3-opus",
            provider="claude",
            action=DecisionAction.SELL,
            symbol="TSLA",
            quantity=50,
            confidence=0.9,
            reasoning="技术面破位",
        )
        assert data.model == "claude-3-opus"
        assert data.action == DecisionAction.SELL

    def test_decision_create_schema_defaults(self):
        """测试 DecisionCreate 默认值。"""
        data = DecisionCreate(
            model="gpt-4o",
            provider="openai",
            action=DecisionAction.HOLD,
        )
        assert data.symbol is None
        assert data.quantity is None
        assert data.confidence == 0.0
        assert data.reasoning == ""
        assert data.executed is False

    def test_decision_create_schema_confidence_bounds(self):
        """测试 DecisionCreate 置信度边界。"""
        # 最小值
        data = DecisionCreate(
            model="test", provider="test", action=DecisionAction.HOLD,
            confidence=0.0,
        )
        assert data.confidence == 0.0
        # 最大值
        data = DecisionCreate(
            model="test", provider="test", action=DecisionAction.HOLD,
            confidence=1.0,
        )
        assert data.confidence == 1.0

    def test_decision_create_schema_confidence_out_of_range(self):
        """测试 DecisionCreate 置信度超范围验证失败。"""
        with pytest.raises(Exception):
            DecisionCreate(
                model="test", provider="test", action=DecisionAction.HOLD,
                confidence=1.5,
            )

    def test_decision_response_from_dataclass(self, mock_decision_data):
        """测试 DecisionResponse 序列化。"""
        decision = Decision(**mock_decision_data)
        response = DecisionResponse.model_validate(decision, from_attributes=True)
        assert response.action == DecisionAction.BUY
        assert response.confidence == 0.85

    def test_decision_response_to_json(self, mock_decision_data):
        """测试 DecisionResponse JSON 序列化。"""
        decision = Decision(**mock_decision_data)
        response = DecisionResponse.model_validate(decision, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["action"] == "buy"
        assert data["symbol"] == "AAPL"
        assert data["confidence"] == 0.85


# ===========================================================================
# Quote / Kline 模型测试
# ===========================================================================


class TestQuote:
    """Quote 模型测试。"""

    def test_create_quote_dataclass(self, mock_quote_data):
        """测试 Quote dataclass 创建。"""
        quote = Quote(**mock_quote_data)
        assert quote.symbol == "AAPL"
        assert quote.open == 148.0
        assert quote.high == 152.0
        assert quote.low == 147.5
        assert quote.close == 151.0
        assert quote.volume == 1_000_000.0

    def test_quote_defaults(self):
        """测试 Quote 默认值。"""
        quote = Quote(symbol="AAPL")
        assert quote.open == 0.0
        assert quote.high == 0.0
        assert quote.low == 0.0
        assert quote.close == 0.0
        assert quote.volume == 0.0
        assert quote.timestamp is None

    def test_quote_response_from_dataclass(self, mock_quote_data):
        """测试 QuoteResponse 序列化。"""
        quote = Quote(**mock_quote_data)
        response = QuoteResponse.model_validate(quote, from_attributes=True)
        assert response.symbol == "AAPL"
        assert response.close == 151.0

    def test_quote_response_to_json(self, mock_quote_data):
        """测试 QuoteResponse JSON 序列化。"""
        quote = Quote(**mock_quote_data)
        response = QuoteResponse.model_validate(quote, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert data["volume"] == 1_000_000.0

    def test_market_snapshot_create(self):
        """测试 MarketSnapshotCreate schema。"""
        data = MarketSnapshotCreate(
            symbol="AAPL",
            open=148.0,
            high=152.0,
            low=147.5,
            close=151.0,
            volume=1_000_000,
        )
        assert data.symbol == "AAPL"
        assert data.close == 151.0


class TestKline:
    """Kline 模型测试。"""

    def test_create_kline_dataclass(self, mock_kline_data):
        """测试 Kline dataclass 创建。"""
        kline = Kline(**mock_kline_data)
        assert kline.symbol == "AAPL"
        assert kline.interval == "1d"
        assert kline.open == 148.0
        assert kline.close == 151.0

    def test_kline_defaults(self):
        """测试 Kline 默认值。"""
        kline = Kline(symbol="AAPL", interval="1d")
        assert kline.open == 0.0
        assert kline.close == 0.0
        assert kline.timestamp is None

    def test_kline_response_from_dataclass(self, mock_kline_data):
        """测试 KlineResponse 序列化。"""
        kline = Kline(**mock_kline_data)
        response = KlineResponse.model_validate(kline, from_attributes=True)
        assert response.symbol == "AAPL"
        assert response.interval == "1d"

    def test_kline_response_to_json(self, mock_kline_data):
        """测试 KlineResponse JSON 序列化。"""
        kline = Kline(**mock_kline_data)
        response = KlineResponse.model_validate(kline, from_attributes=True)
        json_str = response.model_dump_json()
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert data["interval"] == "1d"
