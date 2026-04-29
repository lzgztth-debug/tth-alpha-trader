"""模拟交易引擎单元测试

测试 PaperTradingEngine 的买入、卖出、撤单、盈亏计算、资金不足等场景。
"""

import asyncio
import uuid
from datetime import datetime

import pytest

from src.core.paper_trading import (
    PaperTradingEngine,
    PaperTradingConfig,
    InsufficientFundsError,
    AccountNotFoundError,
    OrderNotFoundError,
    PaperTradingError,
)
from src.models.account import AccountType
from src.models.order import OrderSide, OrderType, OrderStatus


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def engine(tmp_path):
    """创建配置了固定滑点的模拟交易引擎。"""
    config = PaperTradingConfig(
        default_initial_cash=1_000_000.0,
        commission_rate=0.0003,
        min_commission=5.0,
        stamp_tax_rate=0.001,
        slippage_enabled=True,
        slippage_fixed_pct=0.05,  # 固定 0.05% 滑点
        auto_fill_market_orders=True,
    )
    return PaperTradingEngine(config=config, data_dir=str(tmp_path))


@pytest.fixture
def funded_engine(engine):
    """创建已初始化账户并设置市场价格的引擎。"""
    engine.create_account("test_001", initial_cash=1_000_000.0)
    engine.update_market_prices({"AAPL": 150.0, "GOOGL": 2800.0, "MSFT": 380.0})
    return engine


# ===========================================================================
# 账户管理测试
# ===========================================================================


class TestAccountManagement:
    """账户管理测试。"""

    def test_create_account(self, engine):
        """测试创建账户。"""
        account = engine.create_account("acc_001", initial_cash=500_000.0)
        assert account.account_id == "acc_001"
        assert account.cash == 500_000.0
        assert account.available_cash == 500_000.0
        assert account.account_type == AccountType.PAPER

    def test_create_duplicate_account(self, engine):
        """测试创建重复账户抛出异常。"""
        engine.create_account("acc_001")
        with pytest.raises(PaperTradingError):
            engine.create_account("acc_001")

    def test_get_account(self, engine):
        """测试获取账户。"""
        engine.create_account("acc_001")
        account = engine.get_account("acc_001")
        assert account.account_id == "acc_001"

    def test_get_account_not_found(self, engine):
        """测试获取不存在的账户。"""
        with pytest.raises(AccountNotFoundError):
            engine.get_account("nonexistent")

    def test_get_all_accounts(self, engine):
        """测试获取所有账户。"""
        engine.create_account("acc_001")
        engine.create_account("acc_002")
        accounts = engine.get_all_accounts()
        assert len(accounts) == 2

    def test_reset_account(self, funded_engine):
        """测试重置账户。"""
        account = funded_engine.reset_account("test_001")
        assert account.cash == 1_000_000.0
        assert account.market_value == 0.0
        # 持仓应被清空
        positions = funded_engine.get_positions("test_001")
        assert len(positions) == 0

    def test_reset_nonexistent_account(self, engine):
        """测试重置不存在的账户。"""
        with pytest.raises(AccountNotFoundError):
            engine.reset_account("nonexistent")

    def test_delete_account(self, engine):
        """测试删除账户。"""
        engine.create_account("acc_001")
        result = engine.delete_account("acc_001")
        assert result is True
        with pytest.raises(AccountNotFoundError):
            engine.get_account("acc_001")

    def test_delete_nonexistent_account(self, engine):
        """测试删除不存在的账户。"""
        result = engine.delete_account("nonexistent")
        assert result is False


# ===========================================================================
# 市场价格测试
# ===========================================================================


class TestMarketPrices:
    """市场价格测试。"""

    def test_update_market_prices(self, engine):
        """测试更新市场价格。"""
        count = engine.update_market_prices({"AAPL": 150.0, "GOOGL": 2800.0})
        assert count == 2
        assert engine.get_market_price("AAPL") == 150.0
        assert engine.get_market_price("GOOGL") == 2800.0

    def test_get_market_price_unknown(self, engine):
        """测试获取未知标的价格。"""
        assert engine.get_market_price("UNKNOWN") == 0.0


# ===========================================================================
# 买入测试
# ===========================================================================


class TestBuyOrders:
    """买入订单测试。"""

    def test_buy_market_order(self, funded_engine):
        """测试市价买入。"""
        order = funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100.0
        assert order.filled_price > 0

    def test_buy_limit_order(self, funded_engine):
        """测试限价买入。"""
        order = funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=140.0,  # 低于市价，不会立即成交
        )
        assert order.status == OrderStatus.PENDING

    def test_buy_limit_order_matchable(self, funded_engine):
        """测试可成交的限价买入。"""
        order = funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=160.0,  # 高于市价150，应可成交
        )
        # 限价单在价格容差范围内应成交
        assert order.status in (OrderStatus.FILLED, OrderStatus.PENDING)

    def test_buy_creates_position(self, funded_engine):
        """测试买入后创建持仓。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        positions = funded_engine.get_positions("test_001")
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 100.0
        assert positions[0].avg_cost > 0

    def test_buy_deducts_cash(self, funded_engine):
        """测试买入后扣减资金。"""
        account_before = funded_engine.get_account("test_001")
        cash_before = account_before.cash

        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )

        account_after = funded_engine.get_account("test_001")
        assert account_after.cash < cash_before

    def test_buy_adds_to_position(self, funded_engine):
        """测试加仓。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.update_market_prices({"AAPL": 155.0})
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )

        positions = funded_engine.get_positions("test_001")
        assert len(positions) == 1
        assert positions[0].quantity == 200.0

    def test_insufficient_funds(self, funded_engine):
        """测试资金不足。"""
        with pytest.raises(InsufficientFundsError):
            funded_engine.place_order(
                account_id="test_001",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=100000,  # 远超资金
                order_type=OrderType.MARKET,
            )

    def test_buy_nonexistent_account(self, engine):
        """测试不存在的账户买入。"""
        engine.update_market_prices({"AAPL": 150.0})
        with pytest.raises(AccountNotFoundError):
            engine.place_order(
                account_id="nonexistent",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.MARKET,
            )

    def test_buy_without_market_price(self, funded_engine):
        """测试无市场价格时买入。"""
        with pytest.raises(PaperTradingError):
            funded_engine.place_order(
                account_id="test_001",
                symbol="UNKNOWN_SYMBOL",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.MARKET,
            )

    def test_buy_limit_without_price(self, funded_engine):
        """测试限价买入未指定价格。"""
        with pytest.raises(PaperTradingError):
            funded_engine.place_order(
                account_id="test_001",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
            )

    def test_buy_zero_quantity(self, funded_engine):
        """测试买入数量为零。"""
        with pytest.raises(PaperTradingError):
            funded_engine.place_order(
                account_id="test_001",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=0,
                order_type=OrderType.MARKET,
            )


# ===========================================================================
# 卖出测试
# ===========================================================================


class TestSellOrders:
    """卖出订单测试。"""

    @pytest.fixture
    def engine_with_position(self, funded_engine):
        """创建已有持仓的引擎。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.update_market_prices({"AAPL": 155.0})
        return funded_engine

    def test_sell_market_order(self, engine_with_position):
        """测试市价卖出。"""
        order = engine_with_position.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=50,
            order_type=OrderType.MARKET,
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 50.0

    def test_sell_reduces_position(self, engine_with_position):
        """测试卖出后减少持仓。"""
        engine_with_position.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=50,
            order_type=OrderType.MARKET,
        )
        positions = engine_with_position.get_positions("test_001")
        assert len(positions) == 1
        assert positions[0].quantity == 50.0

    def test_sell_full_position(self, engine_with_position):
        """测试全部卖出（清仓）。"""
        engine_with_position.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        positions = engine_with_position.get_positions("test_001")
        assert len(positions) == 0

    def test_sell_increases_cash(self, engine_with_position):
        """测试卖出后增加资金。"""
        account_before = engine_with_position.get_account("test_001")
        cash_before = account_before.cash

        engine_with_position.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET,
        )

        account_after = engine_with_position.get_account("test_001")
        assert account_after.cash > cash_before

    def test_sell_insufficient_position(self, engine_with_position):
        """测试持仓不足卖出。"""
        with pytest.raises(PaperTradingError):
            engine_with_position.place_order(
                account_id="test_001",
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=200,  # 超过持仓
                order_type=OrderType.MARKET,
            )

    def test_sell_nonexistent_position(self, funded_engine):
        """测试卖出未持有的标的。"""
        funded_engine.update_market_prices({"TSLA": 250.0})
        with pytest.raises(PaperTradingError):
            funded_engine.place_order(
                account_id="test_001",
                symbol="TSLA",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.MARKET,
            )


# ===========================================================================
# 撤单测试
# ===========================================================================


class TestCancelOrders:
    """撤单测试。"""

    def test_cancel_pending_order(self, funded_engine):
        """测试取消挂单。"""
        # 创建一个不会成交的限价单
        order = funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=100.0,  # 远低于市价150
        )
        assert order.status == OrderStatus.PENDING

        cancelled = funded_engine.cancel_order("test_001", order.order_id)
        assert cancelled.status == OrderStatus.CANCELLED

    def test_cancel_filled_order(self, funded_engine):
        """测试取消已成交订单失败。"""
        order = funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        assert order.status == OrderStatus.FILLED

        with pytest.raises(PaperTradingError):
            funded_engine.cancel_order("test_001", order.order_id)

    def test_cancel_nonexistent_order(self, funded_engine):
        """测试取消不存在的订单。"""
        with pytest.raises(OrderNotFoundError):
            funded_engine.cancel_order("test_001", "nonexistent_order_id")

    def test_cancel_other_account_order(self, funded_engine):
        """测试取消其他账户的订单。"""
        funded_engine.create_account("test_002")
        order = funded_engine.place_order(
            account_id="test_002",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=100.0,
        )
        with pytest.raises(PaperTradingError):
            funded_engine.cancel_order("test_001", order.order_id)


# ===========================================================================
# 盈亏计算测试
# ===========================================================================


class TestPnLCalculation:
    """盈亏计算测试。"""

    def test_pnl_no_trades(self, funded_engine):
        """测试无交易时的盈亏。"""
        pnl = funded_engine.calculate_pnl("test_001")
        assert pnl["unrealized_pnl"] == 0.0
        assert pnl["realized_pnl"] == 0.0
        assert pnl["net_pnl"] == 0.0
        assert pnl["return_pct"] == 0.0

    def test_pnl_after_buy(self, funded_engine):
        """测试买入后的盈亏（未实现盈亏）。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.update_market_prices({"AAPL": 155.0})

        pnl = funded_engine.calculate_pnl("test_001")
        assert pnl["unrealized_pnl"] > 0  # 价格上涨
        assert pnl["position_count"] == 1
        assert pnl["trade_count"] == 1

    def test_pnl_after_buy_and_sell(self, funded_engine):
        """测试买入卖出后的盈亏。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.update_market_prices({"AAPL": 155.0})
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET,
        )

        pnl = funded_engine.calculate_pnl("test_001")
        assert pnl["realized_pnl"] > 0  # 卖出盈利
        assert pnl["position_count"] == 0

    def test_pnl_nonexistent_account(self, funded_engine):
        """测试不存在的账户盈亏计算。"""
        with pytest.raises(AccountNotFoundError):
            funded_engine.calculate_pnl("nonexistent")

    def test_pnl_includes_fees(self, funded_engine):
        """测试盈亏包含手续费。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.update_market_prices({"AAPL": 155.0})
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET,
        )

        pnl = funded_engine.calculate_pnl("test_001")
        assert pnl["total_commission"] > 0
        assert pnl["total_stamp_tax"] > 0  # 卖出有印花税
        assert pnl["total_fees"] > 0


# ===========================================================================
# 订单查询测试
# ===========================================================================


class TestOrderQueries:
    """订单查询测试。"""

    def test_get_orders(self, funded_engine):
        """测试获取订单列表。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        orders = funded_engine.get_orders("test_001")
        assert len(orders) == 1

    def test_get_orders_by_status(self, funded_engine):
        """测试按状态筛选订单。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=50,
            order_type=OrderType.LIMIT,
            price=100.0,
        )

        filled = funded_engine.get_orders("test_001", status=OrderStatus.FILLED)
        pending = funded_engine.get_orders("test_001", status=OrderStatus.PENDING)
        assert len(filled) == 1
        assert len(pending) == 1

    def test_get_trades(self, funded_engine):
        """测试获取成交记录。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        trades = funded_engine.get_trades("test_001")
        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"
        assert trades[0].side == OrderSide.BUY


# ===========================================================================
# 持久化测试
# ===========================================================================


class TestPersistence:
    """持久化测试。"""

    @pytest.mark.asyncio
    async def test_save_to_database(self, funded_engine):
        """测试保存数据到文件。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        result = await funded_engine.save_to_database()
        assert result["accounts"] is True
        assert result["orders"] is True
        assert result["positions"] is True
        assert result["trades"] is True

    @pytest.mark.asyncio
    async def test_save_and_load(self, funded_engine, tmp_path):
        """测试保存后加载数据。"""
        funded_engine.place_order(
            account_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        await funded_engine.save_to_database()

        # 创建新引擎并加载
        new_engine = PaperTradingEngine(
            config=funded_engine._config,
            data_dir=str(tmp_path),
        )
        result = await new_engine.load_from_database()
        assert result["accounts"] == 1
        assert result["orders"] == 1
        assert result["positions"] == 1
        assert result["trades"] == 1
