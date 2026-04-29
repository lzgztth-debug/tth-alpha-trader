"""券商适配器集成测试

使用 mock 测试 Tiger/Futu/火币适配器的基本功能。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.brokers.base import (
    BaseBrokerAdapter,
    BrokerError,
    BrokerConnectionError,
    BrokerOrderError,
)
from src.models.position import Position
from src.adapters.brokers.tiger import TigerBrokerAdapter
from src.adapters.brokers.futu import FutuBrokerAdapter
from src.adapters.brokers.huobi import HuobiBrokerAdapter
from src.models.account import Account, AccountType
from src.models.order import Order, OrderSide, OrderType, OrderStatus


# ===========================================================================
# Tiger Broker 适配器测试
# ===========================================================================


class TestTigerBrokerAdapter:
    """Tiger Broker 适配器测试。"""

    @pytest.fixture
    def tiger_config(self) -> Dict[str, Any]:
        return {
            "tiger_id": "test_tiger_id",
            "account": "TEST_ACCOUNT",
            "private_key": "test_private_key_content",
            "sandbox": True,
        }

    @pytest.fixture
    def tiger_adapter(self, tiger_config):
        return TigerBrokerAdapter(tiger_config)

    def test_init(self, tiger_adapter):
        """测试初始化。"""
        assert tiger_adapter.tiger_id == "test_tiger_id"
        assert tiger_adapter.account == "TEST_ACCOUNT"
        assert tiger_adapter.sandbox is True
        assert tiger_adapter.connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self, tiger_adapter):
        """测试连接成功。"""
        with patch.object(tiger_adapter, "_init_client"):
            with patch.object(tiger_adapter, "_test_connection"):
                result = await tiger_adapter.connect()
                assert result is True
                assert tiger_adapter.connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, tiger_adapter):
        """测试连接失败。"""
        with patch.object(tiger_adapter, "_init_client", side_effect=BrokerConnectionError("连接失败", broker="Tiger")):
            with pytest.raises(BrokerConnectionError):
                await tiger_adapter.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, tiger_adapter):
        """测试断开连接。"""
        tiger_adapter._connected = True
        tiger_adapter._client = MagicMock()
        await tiger_adapter.disconnect()
        assert tiger_adapter.connected is False

    @pytest.mark.asyncio
    async def test_get_account(self, tiger_adapter):
        """测试获取账户信息。"""
        tiger_adapter._connected = True
        mock_account = Account(
            account_id="TEST_ACCOUNT",
            broker="tiger",
            account_type=AccountType.PAPER,
            total_value=500_000.0,
            cash=300_000.0,
            market_value=200_000.0,
            available_cash=300_000.0,
        )
        with patch.object(tiger_adapter, "_get_account_sync", return_value=mock_account):
            account = await tiger_adapter.get_account()
            assert account.account_id == "TEST_ACCOUNT"
            assert account.total_value == 500_000.0

    @pytest.mark.asyncio
    async def test_get_positions(self, tiger_adapter):
        """测试获取持仓。"""
        tiger_adapter._connected = True
        mock_positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_cost=150.0,
                current_price=155.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_pct=0.033,
                account_id="TEST_ACCOUNT",
            )
        ]
        with patch.object(tiger_adapter, "_get_positions_sync", return_value=mock_positions):
            positions = await tiger_adapter.get_positions()
            assert len(positions) == 1
            assert positions[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_place_order(self, tiger_adapter):
        """测试下单。"""
        tiger_adapter._connected = True
        mock_order = Order(
            order_id="TIGER_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            status=OrderStatus.PENDING,
            broker="tiger",
            account_id="TEST_ACCOUNT",
        )
        with patch.object(tiger_adapter, "_place_order_sync", return_value=mock_order):
            order = await tiger_adapter.place_order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.MARKET,
            )
            assert order.order_id == "TIGER_001"
            assert order.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_cancel_order(self, tiger_adapter):
        """测试撤单。"""
        tiger_adapter._connected = True
        with patch.object(tiger_adapter, "_cancel_order_sync", return_value=True):
            result = await tiger_adapter.cancel_order("TIGER_001")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_quote(self, tiger_adapter):
        """测试获取行情。"""
        tiger_adapter._connected = True
        mock_quote = {
            "symbol": "AAPL",
            "open": 148.0,
            "high": 152.0,
            "low": 147.5,
            "close": 151.0,
            "volume": 1_000_000.0,
        }
        with patch.object(tiger_adapter, "_get_quote_sync", return_value=mock_quote):
            quote = await tiger_adapter.get_quote("AAPL")
            assert quote["symbol"] == "AAPL"
            assert quote["close"] == 151.0

    def test_ensure_connected_not_connected(self, tiger_adapter):
        """测试未连接时调用 _ensure_connected。"""
        with pytest.raises(BrokerConnectionError):
            tiger_adapter._ensure_connected()


# ===========================================================================
# Futu Broker 适配器测试
# ===========================================================================


class TestFutuBrokerAdapter:
    """Futu Broker 适配器测试。"""

    @pytest.fixture
    def futu_config(self) -> Dict[str, Any]:
        return {
            "host": "127.0.0.1",
            "port": 33333,
            "password": "test_password",
        }

    @pytest.fixture
    def futu_adapter(self, futu_config):
        return FutuBrokerAdapter(futu_config)

    def test_init(self, futu_adapter):
        """测试初始化。"""
        assert futu_adapter.host == "127.0.0.1"
        assert futu_adapter.port == 33333
        assert futu_adapter.connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self, futu_adapter):
        """测试连接成功。"""
        with patch.object(futu_adapter, "_init_client"):
            with patch.object(futu_adapter, "_connect_sync", return_value=True):
                result = await futu_adapter.connect()
                assert result is True
                assert futu_adapter.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, futu_adapter):
        """测试断开连接。"""
        futu_adapter._connected = True
        with patch.object(futu_adapter, "_disconnect_sync"):
            await futu_adapter.disconnect()
            assert futu_adapter.connected is False

    @pytest.mark.asyncio
    async def test_get_account(self, futu_adapter):
        """测试获取账户信息。"""
        futu_adapter._connected = True
        mock_account = Account(
            account_id="FUTU_001",
            broker="futu",
            account_type=AccountType.REAL,
            total_value=1_000_000.0,
            cash=600_000.0,
            market_value=400_000.0,
            available_cash=600_000.0,
        )
        with patch.object(futu_adapter, "_get_account_sync", return_value=mock_account):
            account = await futu_adapter.get_account()
            assert account.account_id == "FUTU_001"

    @pytest.mark.asyncio
    async def test_place_order(self, futu_adapter):
        """测试下单。"""
        futu_adapter._connected = True
        mock_order = Order(
            order_id="12345",
            symbol="00700.HK",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=350.0,
            status=OrderStatus.PENDING,
            broker="futu",
        )
        with patch.object(futu_adapter, "_place_order_sync", return_value=mock_order):
            order = await futu_adapter.place_order(
                symbol="00700.HK",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                price=350.0,
            )
            assert order.symbol == "00700.HK"

    @pytest.mark.asyncio
    async def test_cancel_order(self, futu_adapter):
        """测试撤单。"""
        futu_adapter._connected = True
        with patch.object(futu_adapter, "_cancel_order_sync", return_value=True):
            result = await futu_adapter.cancel_order("12345")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_quote(self, futu_adapter):
        """测试获取行情。"""
        futu_adapter._connected = True
        mock_quote = {
            "symbol": "00700.HK",
            "open": 345.0,
            "high": 355.0,
            "low": 343.0,
            "close": 350.0,
            "volume": 5_000_000.0,
        }
        with patch.object(futu_adapter, "_get_quote_sync", return_value=mock_quote):
            quote = await futu_adapter.get_quote("00700.HK")
            assert quote["symbol"] == "00700.HK"


# ===========================================================================
# Huobi Broker 适配器测试
# ===========================================================================


class TestHuobiBrokerAdapter:
    """火币适配器测试。"""

    @pytest.fixture
    def huobi_config(self) -> Dict[str, Any]:
        return {
            "api_key": "test_api_key",
            "secret_key": "test_secret_key",
            "sandbox": True,
            "default_type": "spot",
        }

    @pytest.fixture
    def huobi_adapter(self, huobi_config):
        return HuobiBrokerAdapter(huobi_config)

    def test_init(self, huobi_adapter):
        """测试初始化。"""
        assert huobi_adapter.api_key == "test_api_key"
        assert huobi_adapter.secret_key == "test_secret_key"
        assert huobi_adapter.sandbox is True
        assert huobi_adapter.connected is False

    @pytest.mark.asyncio
    async def test_connect_success(self, huobi_adapter):
        """测试连接成功。"""
        mock_exchange = MagicMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.fetch_balance = AsyncMock(return_value={})

        # 直接设置 _exchange 并 mock _init_exchange
        huobi_adapter._exchange = mock_exchange
        with patch.object(huobi_adapter, "_init_exchange"):
            result = await huobi_adapter.connect()
            assert result is True
            assert huobi_adapter.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, huobi_adapter):
        """测试断开连接。"""
        huobi_adapter._exchange = MagicMock()
        huobi_adapter._exchange.close = AsyncMock()
        huobi_adapter._connected = True
        await huobi_adapter.disconnect()
        assert huobi_adapter.connected is False

    @pytest.mark.asyncio
    async def test_place_order(self, huobi_adapter):
        """测试下单。"""
        huobi_adapter._connected = True
        huobi_adapter._exchange = MagicMock()
        huobi_adapter._exchange.create_order = AsyncMock(return_value={
            "id": "huobi_order_001",
            "symbol": "BTC/USDT",
            "amount": 0.01,
            "price": None,
            "side": "buy",
            "type": "market",
            "status": "closed",
            "filled": 0.01,
            "average": 50000.0,
            "fee": 0.5,
        })
        order = await huobi_adapter.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.01,
            order_type=OrderType.MARKET,
        )
        assert order.order_id == "huobi_order_001"
        assert order.symbol == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_place_order_pending_status(self, huobi_adapter):
        """测试下单时返回 open 状态映射为 PENDING。"""
        huobi_adapter._connected = True
        huobi_adapter._exchange = MagicMock()
        huobi_adapter._exchange.create_order = AsyncMock(return_value={
            "id": "huobi_order_002",
            "symbol": "BTC/USDT",
            "amount": 0.01,
            "price": None,
            "side": "buy",
            "type": "market",
            "status": "open",
            "filled": 0.0,
            "average": None,
            "fee": 0.0,
        })
        order = await huobi_adapter.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.01,
            order_type=OrderType.MARKET,
        )
        assert order.order_id == "huobi_order_002"
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_cancel_order(self, huobi_adapter):
        """测试撤单。"""
        huobi_adapter._connected = True
        huobi_adapter._exchange = MagicMock()
        huobi_adapter._exchange.cancel_order = AsyncMock(return_value={"status": "canceled"})
        result = await huobi_adapter.cancel_order("huobi_order_001")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_quote(self, huobi_adapter):
        """测试获取行情。"""
        huobi_adapter._connected = True
        huobi_adapter._exchange = MagicMock()
        huobi_adapter._exchange.fetch_ticker = AsyncMock(return_value={
            "symbol": "BTC/USDT",
            "open": 49000.0,
            "high": 51000.0,
            "low": 48500.0,
            "last": 50000.0,
            "baseVolume": 1000.0,
            "previousClose": 49500.0,
            "bid": 49990.0,
            "ask": 50010.0,
            "bidVolume": 1.5,
            "askVolume": 2.0,
            "quoteVolume": 50_000_000.0,
        })
        quote = await huobi_adapter.get_quote("BTC/USDT")
        assert quote["symbol"] == "BTC/USDT"
        assert quote["close"] == 50000.0

    @pytest.mark.asyncio
    async def test_place_order_limit_without_price(self, huobi_adapter):
        """测试限价单未指定价格。"""
        huobi_adapter._connected = True
        with pytest.raises(BrokerOrderError):
            await huobi_adapter.place_order(
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                quantity=0.01,
                order_type=OrderType.LIMIT,
            )
