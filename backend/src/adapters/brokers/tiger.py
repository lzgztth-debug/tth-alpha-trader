# src/adapters/brokers/tiger.py
# Tiger Broker 适配器 - 使用 tigeropen SDK 实现美股、港股、A股交易

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable, Awaitable
from datetime import datetime

from src.adapters.brokers.base import (
    BaseBrokerAdapter,
    BrokerError,
    BrokerConnectionError,
    BrokerOrderError,
)
from src.models.account import Account, AccountType
from src.models.position import Position
from src.models.order import Order, OrderSide, OrderType, OrderStatus

logger = logging.getLogger(__name__)


class TigerBrokerAdapter(BaseBrokerAdapter):
    """
    Tiger Broker 适配器

    支持美股、港股、A股的行情订阅和交易。
    使用 tigeropen SDK 进行API调用。

    配置参数:
        tiger_id: Tiger ID
        account: 账户号
        private_key: RSA私钥内容
        private_key_file: RSA私钥文件路径（与 private_key 二选一）
        sandbox: 是否使用模拟环境，默认 False
        language: 语言设置，默认 zh-cn
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.tiger_id = config.get("tiger_id", "")
        self.account = config.get("account", "")
        self.private_key = config.get("private_key", "")
        self.private_key_file = config.get("private_key_file", "")
        self.sandbox = config.get("sandbox", False)
        self.language = config.get("language", "zh-cn")

        self._client = None
        self._trade_client = None
        self._quote_client = None

        if not self.tiger_id:
            logger.warning("Tiger Broker: tiger_id 未配置")
        if not self.account:
            logger.warning("Tiger Broker: account 未配置")

    def _init_client(self):
        """初始化 Tiger Open 客户端"""
        try:
            from tigeropen.tiger_open_config import TigerOpenClientConfig
            from tigeropen.common.const_config import Protocol
            from tigeropen.gateway.tiger_open_gateway import TigerOpenGateway

            # 读取私钥
            private_key = self.private_key
            if not private_key and self.private_key_file:
                try:
                    with open(self.private_key_file, "r") as f:
                        private_key = f.read()
                except FileNotFoundError:
                    raise BrokerConnectionError(
                        f"私钥文件不存在: {self.private_key_file}",
                        broker="Tiger"
                    )

            if not private_key:
                raise BrokerConnectionError(
                    "请提供 private_key 或 private_key_file",
                    broker="Tiger"
                )

            # 配置客户端
            if self.sandbox:
                config = TigerOpenClientConfig(
                    tiger_id=self.tiger_id,
                    private_key=private_key,
                    account=self.account,
                    language=self.language,
                    timeout=30,
                )
                # 模拟环境使用 paper trading
                logger.info("Tiger Broker: 使用模拟环境")
            else:
                config = TigerOpenClientConfig(
                    tiger_id=self.tiger_id,
                    private_key=private_key,
                    account=self.account,
                    language=self.language,
                    timeout=30,
                )

            self._client = TigerOpenGateway(config)
            logger.info("Tiger Broker: 客户端初始化成功")

        except ImportError:
            raise BrokerConnectionError(
                "tigeropen SDK 未安装，请执行: pip install tigeropen",
                broker="Tiger"
            )

    async def connect(self) -> bool:
        """连接 Tiger Broker"""
        try:
            self._init_client()

            # 验证连接 - 获取账户余额作为连接测试
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._test_connection)

            self._connected = True
            logger.info(
                f"Tiger Broker: 连接成功 (account={self.account}, "
                f"sandbox={self.sandbox})"
            )
            return True

        except BrokerConnectionError:
            raise
        except Exception as e:
            self._connected = False
            raise BrokerConnectionError(
                f"连接失败: {e}",
                broker="Tiger"
            )

    def _test_connection(self):
        """测试连接（同步方法，在线程池中执行）"""
        try:
            from tigeropen.quote.quote_client import QuoteClient

            quote_client = QuoteClient(self._client)
            # 获取一个简单数据来验证连接
            quote_client.get_briefs(["AAPL"])
            logger.info("Tiger Broker: 连接测试通过")
        except Exception as e:
            logger.error(f"Tiger Broker: 连接测试失败: {e}")
            raise

    async def disconnect(self) -> None:
        """断开 Tiger Broker 连接"""
        try:
            if self._client:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._disconnect_sync)
            self._connected = False
            logger.info("Tiger Broker: 已断开连接")
        except Exception as e:
            logger.warning(f"Tiger Broker: 断开连接时出错: {e}")
            self._connected = False

    def _disconnect_sync(self):
        """同步断开连接"""
        try:
            from tigeropen.gateway.tiger_open_gateway import TigerOpenGateway
            if hasattr(self._client, 'close'):
                self._client.close()
        except Exception:
            pass

    async def get_account(self) -> Account:
        """获取账户信息"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._get_account_sync)
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取账户信息失败: {e}", broker="Tiger")

    def _get_account_sync(self) -> Account:
        """同步获取账户信息"""
        try:
            from tigeropen.trade.trade_client import TradeClient

            trade_client = TradeClient(self._client)
            # 获取账户资产
            accounts = trade_client.get_accounts([self.account])
            if not accounts:
                raise BrokerError("未获取到账户信息", broker="Tiger")

            acct = accounts[0]
            account = Account(
                account_id=self.account,
                broker="tiger",
                account_type=AccountType.PAPER if self.sandbox else AccountType.REAL,
                total_value=float(getattr(acct, 'total_assets', 0) or 0),
                cash=float(getattr(acct, 'cash', 0) or 0),
                market_value=float(getattr(acct, 'market_value', 0) or 0),
                available_cash=float(getattr(acct, 'buying_power', 0) or 0),
                currency="USD",
                updated_at=datetime.now().isoformat(),
            )
            logger.info(f"Tiger Broker: 获取账户信息成功, 总资产={account.total_value}")
            return account
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取账户信息失败: {e}", broker="Tiger")

    async def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._get_positions_sync)
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取持仓失败: {e}", broker="Tiger")

    def _get_positions_sync(self) -> List[Position]:
        """同步获取持仓列表"""
        try:
            from tigeropen.trade.trade_client import TradeClient

            trade_client = TradeClient(self._client)
            positions = trade_client.get_positions(self.account)

            result = []
            for pos in positions:
                quantity = float(getattr(pos, 'quantity', 0) or 0)
                avg_cost = float(getattr(pos, 'avg_cost', 0) or 0)
                current_price = float(getattr(pos, 'market_price', 0) or 0)
                market_value = float(getattr(pos, 'market_value', 0) or 0)
                unrealized_pnl = float(getattr(pos, 'unrealized_pnl', 0) or 0)
                unrealized_pnl_pct = (
                    unrealized_pnl / (avg_cost * quantity) * 100
                    if avg_cost * quantity != 0 else 0.0
                )

                result.append(Position(
                    symbol=getattr(pos, 'symbol', ''),
                    quantity=quantity,
                    avg_cost=avg_cost,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    broker="tiger",
                    account_id=self.account,
                ))

            logger.info(f"Tiger Broker: 获取持仓成功, 共 {len(result)} 个持仓")
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取持仓失败: {e}", broker="Tiger")

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        **kwargs
    ) -> Order:
        """下单"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._place_order_sync,
                symbol, side, quantity, order_type, price, kwargs
            )
            return result
        except BrokerOrderError:
            raise
        except Exception as e:
            raise BrokerOrderError(
                f"下单失败: {e}",
                broker="Tiger",
                order_id=""
            )

    def _place_order_sync(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        price: Optional[float],
        kwargs: Dict[str, Any]
    ) -> Order:
        """同步下单"""
        try:
            from tigeropen.trade.trade_client import TradeClient
            from tigeropen.common.const_config import (
                OpenClose, Market, Currency, OrderType as TigerOrderType,
                OrderSide as TigerSide
            )

            trade_client = TradeClient(self._client)

            # 构建订单参数
            order_params = {
                'account': self.account,
                'symbol': symbol,
                'order_type': (
                    TigerOrderType.MKT if order_type == OrderType.MARKET
                    else TigerOrderType.LMT
                ),
                'side': TigerSide.BUY if side == OrderSide.BUY else TigerSide.SELL,
                'quantity': int(quantity),
                'currency': kwargs.get('currency', Currency.USD),
            }

            if order_type == OrderType.LIMIT and price is not None:
                order_params['price'] = price
                order_params['limit_price'] = price

            # 设置市价类型
            if order_type == OrderType.MARKET:
                order_params['market'] = Market.US

            logger.info(
                f"Tiger Broker: 下单请求 symbol={symbol}, side={side.value}, "
                f"type={order_type.value}, qty={quantity}, price={price}"
            )

            # 提交订单
            order_result = trade_client.place_order(**order_params)

            if not order_result:
                raise BrokerOrderError(
                    "下单返回结果为空",
                    broker="Tiger"
                )

            order_id = str(getattr(order_result, 'order_id', ''))
            if not order_id:
                raise BrokerOrderError(
                    "下单成功但未获取到订单ID",
                    broker="Tiger"
                )

            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.SUBMITTED,
                broker="tiger",
                account_id=self.account,
            )

            logger.info(f"Tiger Broker: 下单成功, order_id={order_id}")
            return order

        except BrokerOrderError:
            raise
        except Exception as e:
            logger.error(f"Tiger Broker: 下单异常: {e}")
            raise BrokerOrderError(
                f"下单失败: {e}",
                broker="Tiger"
            )

    async def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._cancel_order_sync, order_id
            )
            return result
        except BrokerOrderError:
            raise
        except Exception as e:
            raise BrokerOrderError(
                f"撤单失败: {e}",
                broker="Tiger",
                order_id=order_id
            )

    def _cancel_order_sync(self, order_id: str) -> bool:
        """同步撤销订单"""
        try:
            from tigeropen.trade.trade_client import TradeClient

            trade_client = TradeClient(self._client)
            result = trade_client.cancel_order(order_id)

            if result:
                logger.info(f"Tiger Broker: 撤单成功, order_id={order_id}")
            else:
                logger.warning(f"Tiger Broker: 撤单返回False, order_id={order_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"Tiger Broker: 撤单异常: {e}")
            raise BrokerOrderError(
                f"撤单失败: {e}",
                broker="Tiger",
                order_id=order_id
            )

    async def get_order(self, order_id: str) -> Order:
        """查询单个订单详情"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._get_order_sync, order_id
            )
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"查询订单失败: {e}", broker="Tiger")

    def _get_order_sync(self, order_id: str) -> Order:
        """同步查询单个订单"""
        try:
            from tigeropen.trade.trade_client import TradeClient

            trade_client = TradeClient(self._client)
            orders = trade_client.get_orders([order_id])

            if not orders:
                raise BrokerError(f"未找到订单: {order_id}", broker="Tiger")

            return self._convert_order(orders[0])
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"查询订单失败: {e}", broker="Tiger")

    async def get_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ) -> List[Order]:
        """查询订单列表"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._get_orders_sync, status, symbol, kwargs
            )
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"查询订单列表失败: {e}", broker="Tiger")

    def _get_orders_sync(
        self,
        status: Optional[str],
        symbol: Optional[str],
        kwargs: Dict[str, Any]
    ) -> List[Order]:
        """同步查询订单列表"""
        try:
            from tigeropen.trade.trade_client import TradeClient

            trade_client = TradeClient(self._client)

            # 构建查询参数
            order_ids = kwargs.get('order_ids')
            if order_ids:
                orders = trade_client.get_orders(order_ids)
            else:
                # 按账户查询
                orders = trade_client.get_orders_by_account(
                    self.account,
                    status_codes=status,
                    symbol=symbol,
                )

            result = [self._convert_order(o) for o in orders]
            logger.info(f"Tiger Broker: 查询到 {len(result)} 个订单")
            return result
        except Exception as e:
            raise BrokerError(f"查询订单列表失败: {e}", broker="Tiger")

    def _convert_order(self, tiger_order: Any) -> Order:
        """将 Tiger 订单对象转换为内部 Order 模型"""
        status_map = {
            'Invalid': OrderStatus.REJECTED,
            'Initial': OrderStatus.PENDING,
            'Submitted': OrderStatus.SUBMITTED,
            'PartialFilled': OrderStatus.PARTIALLY_FILLED,
            'Filled': OrderStatus.FILLED,
            'Cancelled': OrderStatus.CANCELLED,
            'Rejected': OrderStatus.REJECTED,
            'Expired': OrderStatus.EXPIRED,
        }

        tiger_status = getattr(tiger_order, 'status', 'Initial')
        order_status = status_map.get(tiger_status, OrderStatus.PENDING)

        side_map = {
            'Buy': OrderSide.BUY,
            'Sell': OrderSide.SELL,
        }
        tiger_side = getattr(tiger_order, 'side', '')
        order_side = side_map.get(tiger_side, OrderSide.BUY)

        type_map = {
            'MKT': OrderType.MARKET,
            'LMT': OrderType.LIMIT,
        }
        tiger_type = getattr(tiger_order, 'order_type', 'MKT')
        order_type = type_map.get(tiger_type, OrderType.MARKET)

        return Order(
            order_id=str(getattr(tiger_order, 'order_id', '')),
            symbol=getattr(tiger_order, 'symbol', ''),
            side=order_side,
            order_type=order_type,
            quantity=float(getattr(tiger_order, 'quantity', 0) or 0),
            price=float(getattr(tiger_order, 'limit_price', 0) or 0),
            status=order_status,
            filled_quantity=float(getattr(tiger_order, 'filled', 0) or 0),
            filled_price=float(getattr(tiger_order, 'avg_filled_price', 0) or 0),
            fee=float(getattr(tiger_order, 'commission', 0) or 0),
            broker="tiger",
            account_id=self.account,
        )

    async def subscribe_quote(
        self,
        symbols: List[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """订阅实时行情"""
        self._ensure_connected()
        try:
            from tigeropen.quote.quote_client import QuoteClient
            from tigeropen.quote.quote_type import QuotePeriod

            quote_client = QuoteClient(self._client)

            # 注册回调
            for symbol in symbols:
                self._quote_callbacks[symbol] = callback

            # 订阅行情
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: quote_client.subscribe_quote(symbols, period=QuotePeriod.ONE_DAY)
            )

            logger.info(f"Tiger Broker: 订阅行情成功, symbols={symbols}")
        except ImportError:
            raise BrokerError(
                "tigeropen SDK 未安装",
                broker="Tiger"
            )
        except Exception as e:
            raise BrokerError(f"订阅行情失败: {e}", broker="Tiger")

    async def unsubscribe_quote(self, symbols: List[str]) -> None:
        """取消订阅行情"""
        self._ensure_connected()
        try:
            from tigeropen.quote.quote_client import QuoteClient

            quote_client = QuoteClient(self._client)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: quote_client.unsubscribe_quote(symbols)
            )

            for symbol in symbols:
                self._quote_callbacks.pop(symbol, None)

            logger.info(f"Tiger Broker: 取消订阅行情, symbols={symbols}")
        except Exception as e:
            raise BrokerError(f"取消订阅行情失败: {e}", broker="Tiger")

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """获取单个标的实时行情"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._get_quote_sync, symbol
            )
            return result
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取行情失败: {e}", broker="Tiger")

    def _get_quote_sync(self, symbol: str) -> Dict[str, Any]:
        """同步获取行情"""
        try:
            from tigeropen.quote.quote_client import QuoteClient

            quote_client = QuoteClient(self._client)
            briefs = quote_client.get_briefs([symbol])

            if not briefs:
                raise BrokerError(f"未获取到行情数据: {symbol}", broker="Tiger")

            brief = briefs[0]
            quote_data = {
                "symbol": symbol,
                "open": float(getattr(brief, 'open', 0) or 0),
                "high": float(getattr(brief, 'high', 0) or 0),
                "low": float(getattr(brief, 'low', 0) or 0),
                "close": float(getattr(brief, 'latest_price', 0) or 0),
                "volume": float(getattr(brief, 'volume', 0) or 0),
                "prev_close": float(getattr(brief, 'prev_close', 0) or 0),
                "timestamp": datetime.now().isoformat(),
                "bid_price": float(getattr(brief, 'bid', 0) or 0),
                "ask_price": float(getattr(brief, 'ask', 0) or 0),
                "turnover": float(getattr(brief, 'turnover', 0) or 0),
            }

            logger.debug(f"Tiger Broker: 获取行情成功, symbol={symbol}")
            return quote_data
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取行情失败: {e}", broker="Tiger")
