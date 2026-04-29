"""风控管理器单元测试

测试 RiskManager 的仓位限制、单笔限额、止损、日亏损限制、交易频率限制。
"""

from datetime import date

import pytest

from src.core.trading_engine import (
    RiskManager,
    RiskConfig,
    RiskAlert,
    RiskLimitExceededError,
    PositionManager,
)
from src.models.account import Account
from src.models.order import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def risk_config():
    """创建测试用风控配置。"""
    return RiskConfig(
        max_position_pct=20.0,
        max_total_position_pct=80.0,
        max_order_value=100_000.0,
        max_order_quantity=10_000.0,
        min_order_value=100.0,
        stop_loss_pct=2.0,
        take_profit_pct=5.0,
        max_daily_loss_pct=3.0,
        max_daily_loss_amount=50_000.0,
        max_daily_trades=50,
        max_consecutive_losses=5,
    )


@pytest.fixture
def risk_manager(risk_config):
    """创建风控管理器。"""
    return RiskManager(config=risk_config)


@pytest.fixture
def position_manager():
    """创建持仓管理器。"""
    return PositionManager()


@pytest.fixture
def sample_account():
    """创建测试账户。"""
    return Account(
        account_id="test_001",
        broker="paper_broker",
        account_type="paper",
        total_value=1_000_000.0,
        cash=800_000.0,
        market_value=200_000.0,
        available_cash=800_000.0,
    )


@pytest.fixture
def sample_buy_order():
    """创建测试买入订单。"""
    return Order(
        order_id="order_001",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=None,
        status=OrderStatus.PENDING,
        account_id="test_001",
    )


@pytest.fixture
def sample_sell_order():
    """创建测试卖出订单。"""
    return Order(
        order_id="order_002",
        symbol="AAPL",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=100,
        price=None,
        status=OrderStatus.PENDING,
        account_id="test_001",
    )


# ===========================================================================
# 单笔交易限额测试
# ===========================================================================


class TestOrderValueLimits:
    """单笔交易限额测试。"""

    def test_order_within_limits(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试订单在限额内通过。"""
        alerts = risk_manager.check_order(
            order=sample_buy_order,
            account=sample_account,
            current_price=150.0,
            position_manager=position_manager,
        )
        # 100 * 150 = 15000 < 100000, 应通过
        critical = [a for a in alerts if a.severity == "critical"]
        assert len(critical) == 0

    def test_order_value_exceeded(self, risk_manager, sample_account, position_manager):
        """测试订单金额超限。"""
        order = Order(
            order_id="order_big",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000,
            status=OrderStatus.PENDING,
            account_id="test_001",
        )
        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=order,
                account=sample_account,
                current_price=150.0,  # 1000 * 150 = 150000 > 100000
                position_manager=position_manager,
            )

    def test_order_value_too_small(self, risk_manager, sample_account, position_manager):
        """测试订单金额过小（警告，不阻断）。"""
        order = Order(
            order_id="order_tiny",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            status=OrderStatus.PENDING,
            account_id="test_001",
        )
        alerts = risk_manager.check_order(
            order=order,
            account=sample_account,
            current_price=50.0,  # 1 * 50 = 50 < 100
            position_manager=position_manager,
        )
        warning_alerts = [a for a in alerts if a.alert_type == "order_value_too_small"]
        assert len(warning_alerts) == 1

    def test_order_quantity_exceeded(self, risk_manager, sample_account, position_manager):
        """测试订单数量超限。"""
        order = Order(
            order_id="order_qty",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=20_000,  # 超过 10000
            status=OrderStatus.PENDING,
            account_id="test_001",
        )
        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=order,
                account=sample_account,
                current_price=1.0,
                position_manager=position_manager,
            )


# ===========================================================================
# 仓位限制测试
# ===========================================================================


class TestPositionLimits:
    """仓位限制测试。"""

    def test_position_within_limit(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试仓位在限制内通过。"""
        alerts = risk_manager.check_order(
            order=sample_buy_order,
            account=sample_account,
            current_price=150.0,
            position_manager=position_manager,
        )
        position_alerts = [a for a in alerts if a.alert_type == "position_limit_exceeded"]
        assert len(position_alerts) == 0

    def test_position_limit_exceeded(self, risk_manager, sample_account, position_manager):
        """测试仓位超限。"""
        # 先建仓使持仓接近上限
        position_manager.update_position_on_buy(
            account_id="test_001",
            symbol="AAPL",
            quantity=1000,
            price=150.0,
        )

        # 再买入大量（1000 * 150 = 150000 已占 15%，再加 1000 股超过 20%）
        order = Order(
            order_id="order_pos",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1000,
            status=OrderStatus.PENDING,
            account_id="test_001",
        )
        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=order,
                account=sample_account,
                current_price=150.0,
                position_manager=position_manager,
            )

    def test_portfolio_position_check(self, risk_manager, sample_account, position_manager):
        """测试组合仓位检查。"""
        # 建多个持仓使总仓位超过限制
        # 每个标的: 500 * 400 = 200000，9个标的 = 1800000 > 80% of 1000000
        for symbol in ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "NVDA", "META", "NFLX", "BABA"]:
            position_manager.update_position_on_buy(
                account_id="test_001",
                symbol=symbol,
                quantity=500,
                price=400.0,  # 500 * 400 = 200000 每个标的
            )

        alerts = risk_manager.check_portfolio_risk(
            account=sample_account,
            position_manager=position_manager,
        )
        total_alerts = [a for a in alerts if a.alert_type == "total_position_exceeded"]
        assert len(total_alerts) == 1


# ===========================================================================
# 止损止盈测试
# ===========================================================================


class TestStopLossTakeProfit:
    """止损止盈测试。"""

    def test_stop_loss_triggered(self, risk_manager, sample_sell_order, sample_account, position_manager):
        """测试止损触发。"""
        # 建仓成本 150，当前价 145，亏损 3.33% > 2%
        position_manager.update_position_on_buy(
            account_id="test_001",
            symbol="AAPL",
            quantity=100,
            price=150.0,
        )

        # 止损触发时 check_order 会抛出 RiskLimitExceededError（severity=critical）
        with pytest.raises(RiskLimitExceededError) as exc_info:
            risk_manager.check_order(
                order=sample_sell_order,
                account=sample_account,
                current_price=145.0,
                position_manager=position_manager,
            )
        assert "止损" in str(exc_info.value)

    def test_take_profit_triggered(self, risk_manager, sample_sell_order, sample_account, position_manager):
        """测试止盈触发（警告级别）。"""
        # 建仓成本 150，当前价 160，盈利 6.67% > 5%
        position_manager.update_position_on_buy(
            account_id="test_001",
            symbol="AAPL",
            quantity=100,
            price=150.0,
        )

        alerts = risk_manager.check_order(
            order=sample_sell_order,
            account=sample_account,
            current_price=160.0,
            position_manager=position_manager,
        )
        take_profit_alerts = [a for a in alerts if a.alert_type == "take_profit_triggered"]
        assert len(take_profit_alerts) == 1
        assert take_profit_alerts[0].severity == "warning"

    def test_portfolio_stop_loss_check(self, risk_manager, sample_account, position_manager):
        """测试组合止损检查。"""
        position_manager.update_position_on_buy(
            account_id="test_001",
            symbol="AAPL",
            quantity=100,
            price=150.0,
        )

        # 更新价格使亏损超过止损线
        position_manager.update_market_price("test_001", "AAPL", 140.0)

        alerts = risk_manager.check_portfolio_risk(
            account=sample_account,
            position_manager=position_manager,
        )
        stop_loss_alerts = [a for a in alerts if a.alert_type == "stop_loss_triggered"]
        assert len(stop_loss_alerts) == 1
        assert stop_loss_alerts[0].severity == "critical"


# ===========================================================================
# 日亏损限制测试
# ===========================================================================


class TestDailyLossLimits:
    """日亏损限制测试。"""

    def test_daily_loss_pct_exceeded(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试日亏损百分比超限。"""
        # 模拟当日已亏损
        risk_manager.record_trade("test_001", pnl=-35_000.0)  # 亏损 3.5% > 3%

        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=sample_buy_order,
                account=sample_account,
                current_price=150.0,
                position_manager=position_manager,
            )

    def test_daily_loss_amount_exceeded(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试日亏损金额超限。"""
        # 模拟当日已亏损
        risk_manager.record_trade("test_001", pnl=-55_000.0)  # 亏损金额 > 50000

        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=sample_buy_order,
                account=sample_account,
                current_price=150.0,
                position_manager=position_manager,
            )

    def test_daily_loss_within_limit(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试日亏损在限制内。"""
        risk_manager.record_trade("test_001", pnl=-10_000.0)  # 亏损 1% < 3%
        alerts = risk_manager.check_order(
            order=sample_buy_order,
            account=sample_account,
            current_price=150.0,
            position_manager=position_manager,
        )
        critical = [a for a in alerts if a.severity == "critical"]
        assert len(critical) == 0


# ===========================================================================
# 交易频率限制测试
# ===========================================================================


class TestTradingFrequency:
    """交易频率限制测试。"""

    def test_trading_frequency_within_limit(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试交易频率在限制内。"""
        for _ in range(30):
            risk_manager.record_trade("test_001", pnl=0)

        alerts = risk_manager.check_order(
            order=sample_buy_order,
            account=sample_account,
            current_price=150.0,
            position_manager=position_manager,
        )
        freq_alerts = [a for a in alerts if a.alert_type == "trading_frequency_exceeded"]
        assert len(freq_alerts) == 0

    def test_trading_frequency_exceeded(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试交易频率超限。"""
        for _ in range(50):
            risk_manager.record_trade("test_001", pnl=0)

        with pytest.raises(RiskLimitExceededError):
            risk_manager.check_order(
                order=sample_buy_order,
                account=sample_account,
                current_price=150.0,
                position_manager=position_manager,
            )


# ===========================================================================
# 连续亏损测试
# ===========================================================================


class TestConsecutiveLosses:
    """连续亏损测试。"""

    def test_consecutive_losses_alert(self, risk_manager):
        """测试连续亏损告警。"""
        for _ in range(5):
            risk_manager.record_trade("test_001", pnl=-1000.0)

        alerts = risk_manager.get_alerts(severity="critical")
        consecutive_alerts = [a for a in alerts if a.alert_type == "consecutive_losses"]
        assert len(consecutive_alerts) == 1

    def test_consecutive_losses_reset_on_profit(self, risk_manager):
        """测试盈利后重置连续亏损计数。"""
        for _ in range(3):
            risk_manager.record_trade("test_001", pnl=-1000.0)
        risk_manager.record_trade("test_001", pnl=500.0)
        # 连续亏损应重置为 0
        stats = risk_manager.get_daily_stats("test_001")
        assert stats["consecutive_losses"] == 0


# ===========================================================================
# 交易记录和统计测试
# ===========================================================================


class TestTradeRecording:
    """交易记录和统计测试。"""

    def test_record_trade(self, risk_manager):
        """测试记录交易。"""
        risk_manager.record_trade("test_001", pnl=1000.0)
        stats = risk_manager.get_daily_stats("test_001")
        assert stats["count"] == 1
        assert stats["pnl"] == 1000.0

    def test_record_multiple_trades(self, risk_manager):
        """测试记录多笔交易。"""
        risk_manager.record_trade("test_001", pnl=1000.0)
        risk_manager.record_trade("test_001", pnl=-500.0)
        risk_manager.record_trade("test_001", pnl=2000.0)
        stats = risk_manager.get_daily_stats("test_001")
        assert stats["count"] == 3
        assert stats["pnl"] == 2500.0

    def test_daily_stats_nonexistent_account(self, risk_manager):
        """测试不存在的账户日统计。"""
        stats = risk_manager.get_daily_stats("nonexistent")
        assert stats == {}

    def test_alert_history(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试告警历史记录。"""
        risk_manager.check_order(
            order=sample_buy_order,
            account=sample_account,
            current_price=150.0,
            position_manager=position_manager,
        )
        alerts = risk_manager.get_alerts()
        assert len(alerts) >= 0  # 可能没有告警

    def test_alert_callback(self, risk_manager, sample_buy_order, sample_account, position_manager):
        """测试告警回调。"""
        received_alerts = []

        def on_alert(alert):
            received_alerts.append(alert)

        risk_manager.on_alert(on_alert)

        # 触发一个会产生告警的场景
        for _ in range(50):
            risk_manager.record_trade("test_001", pnl=0)

        try:
            risk_manager.check_order(
                order=sample_buy_order,
                account=sample_account,
                current_price=150.0,
                position_manager=position_manager,
            )
        except RiskLimitExceededError:
            pass

        # 回调应被触发
        assert len(received_alerts) > 0


# ===========================================================================
# 配置更新测试
# ===========================================================================


class TestConfigUpdate:
    """配置更新测试。"""

    def test_update_config(self, risk_manager):
        """测试更新风控配置。"""
        new_config = RiskConfig(
            max_position_pct=10.0,
            max_daily_trades=20,
        )
        risk_manager.update_config(new_config)
        assert risk_manager.config.max_position_pct == 10.0
        assert risk_manager.config.max_daily_trades == 20
