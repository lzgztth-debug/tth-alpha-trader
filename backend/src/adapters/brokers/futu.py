# src/adapters/brokers/futu.py
# Futu OpenD 适配器 - 使用 futu-api SDK 实现港股、美股交易

import asyncio
import logging
import time
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


class FutuBrokerAdapter(BaseBrokerAdapter):
    """
    Futu OpenD 适配器

    通过 Futu OpenD 网关连接富途证券，支持港股、美股交易。

    配置参数:
        host: OpenD 网关地址，默认 127.0.0.1
        port: OpenD 网关端口，默认 33333
        password: 交易密码（加密后）
        unlock_password: 解锁交易密码
        auto_reconnect: 是否自动重连，默认 True
        max_reconnect_attempts: 最大重连次数，默认 5
        reconnect_interval: 重连间隔（秒），默认 10
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host", "127.0.0.1")
        self.port = config.get("port", 33333)
        self.password = config.get("password", "")
        self.unlock_password = config.get("unlock_password", "")
        self.auto_reconnect = config.get("auto_reconnect", True)
        self.max_reconnect_attempts = config.get("max_reconnect_attempts", 5)
        self.reconnect_interval = config.get("reconnect_interval", 10)

        self._quote_ctx = None
        self._trade_ctx = None
        self._reconnect_task = None
        self._reconnecting = False

    def _init_client(self):
        """初始化 Futu 客户端"""
        try:
            from futu import (
                OpenQuoteContext,
                OpenSecTradeContext,
                RET_OK,
                TrdEnv,
                TrdMarket,
            )
            self._futu_module = __import__('futu')
        except ImportError:
            raise BrokerConnectionError(
                "futu-api SDK 未安装，请执行: pip install futu-api",
                broker="Futu"
            )

    async def connect(self) -> bool:
        """连接 Futu OpenD"""
        try:
            self._init_client()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._connect_sync)

            if result:
                self._connected = True
                logger.info(
                    f"Futu OpenD: 连接成功 (host={self.host}, port={self.port})"
                )
                return True
            else:
                raise BrokerConnectionError(
                    "连接 Futu OpenD 失败",
                    broker="Futu"
                )
        except BrokerConnectionError:
            raise
        except Exception as e:
            self._connected = False
            raise BrokerConnectionError(
                f"连接失败: {e}",
                broker="Futu"
            )

    def _connect_sync(self) -> bool:
        """同步连接 Futu OpenD"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        # 创建行情上下文
        self._quote_ctx = futu.OpenQuoteContext(host=self.host, port=self.port)
        ret, data = self._quote_ctx.get_global_state()

        if ret != RET_OK:
            logger.error(f"Futu OpenD: 行情连接失败: {data}")
            return False

        # 创建交易上下文
        if self.password:
            # 解锁交易
            self._trade_ctx = futu.OpenSecTradeContext(
                filter_trdmarket=futu.TrdMarket.HK,
                host=self.host,
                port=self.port,
            )
            if self.unlock_password:
                ret, data = self._trade_ctx.unlock_trade(self.unlock_password)
                if ret != RET_OK:
                    logger.warning(f"Futu OpenD: 交易解锁失败: {data}")
            else:
                ret, data = self._trade_ctx.unlock_trade(self.password)
                if ret != RET_OK:
                    logger.warning(f"Futu OpenD: 交易解锁失败: {data}")

        return True

    async def disconnect(self) -> None:
        """断开 Futu OpenD 连接"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._disconnect_sync)
            self._connected = False
            logger.info("Futu OpenD: 已断开连接")
        except Exception as e:
            logger.warning(f"Futu OpenD: 断开连接时出错: {e}")
            self._connected = False

    def _disconnect_sync(self):
        """同步断开连接"""
        if self._quote_ctx:
            try:
                self._quote_ctx.close()
            except Exception:
                pass
            self._quote_ctx = None

        if self._trade_ctx:
            try:
                self._trade_ctx.close()
            except Exception:
                pass
            self._trade_ctx = None

    async def reconnect(self, max_retries: int = 3, retry_interval: float = 5.0) -> bool:
        """
        重连 Futu OpenD（带重试和状态恢复）

        Args:
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）

        Returns:
            bool: 重连是否成功
        """
        max_attempts = max(max_retries, self.max_reconnect_attempts)
        interval = max(retry_interval, self.reconnect_interval)

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Futu OpenD: 尝试重连 ({attempt}/{max_attempts})..."
                )
                await self.disconnect()
                await asyncio.sleep(interval)

                result = await self.connect()
                if result:
                    logger.info("Futu OpenD: 重连成功")
                    return True
            except Exception as e:
                logger.warning(
                    f"Futu OpenD: 重连尝试 {attempt} 失败: {e}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(interval * attempt)

        logger.error(f"Futu OpenD: 重连失败，已尝试 {max_attempts} 次")
        return False

    async def _execute_with_reconnect(self, func, *args, **kwargs):
        """执行操作，失败时自动重连"""
        try:
            return await func(*args, **kwargs)
        except BrokerConnectionError:
            if self.auto_reconnect:
                logger.info("Futu OpenD: 连接断开，尝试自动重连...")
                reconnected = await self.reconnect()
                if reconnected:
                    return await func(*args, **kwargs)
            raise

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
            raise BrokerError(f"获取账户信息失败: {e}", broker="Futu")

    def _get_account_sync(self) -> Account:
        """同步获取账户信息"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerError("交易上下文未初始化，请检查密码配置", broker="Futu")

        # 获取账户资金
        ret, data = self._trade_ctx.accinfo_query()

        if ret != RET_OK:
            raise BrokerError(f"获取账户信息失败: {data}", broker="Futu")

        if data.empty:
            raise BrokerError("账户数据为空", broker="Futu")

        row = data.iloc[0]
        total_assets = float(row.get('total_assets', 0) or 0)
        cash = float(row.get('cash', 0) or 0)
        market_val = float(row.get('market_val', 0) or 0)
        available = float(row.get('available_funds', 0) or 0)

        account = Account(
            account_id=str(row.get('acc_id', '')),
            broker="futu",
            account_type=AccountType.REAL,
            total_value=total_assets,
            cash=cash,
            market_value=market_val,
            available_cash=available,
            currency="HKD",
            updated_at=datetime.now().isoformat(),
        )

        logger.info(f"Futu OpenD: 获取账户信息成功, 总资产={total_assets}")
        return account

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
            raise BrokerError(f"获取持仓失败: {e}", broker="Futu")

    def _get_positions_sync(self) -> List[Position]:
        """同步获取持仓列表"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerError("交易上下文未初始化", broker="Futu")

        # 查询持仓
        ret, data = self._trade_ctx.position_list_query()

        if ret != RET_OK:
            raise BrokerError(f"获取持仓失败: {data}", broker="Futu")

        if data.empty:
            return []

        positions = []
        for _, row in data.iterrows():
            quantity = float(row.get('quantity', 0) or 0)
            if quantity <= 0:
                continue

            cost = float(row.get('cost_price', 0) or 0)
            current = float(row.get('market_val', 0) or 0)
            market_price = float(row.get('current_price', 0) or 0)
            pnl = float(row.get('pl_val', 0) or 0)
            pnl_pct = float(row.get('pl_ratio', 0) or 0)

            positions.append(Position(
                symbol=str(row.get('code', '')),
                quantity=quantity,
                avg_cost=cost,
                current_price=market_price,
                market_value=current,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
                broker="futu",
                account_id=str(row.get('acc_id', '')),
            ))

        logger.info(f"Futu OpenD: 获取持仓成功, 共 {len(positions)} 个持仓")
        return positions

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
                broker="Futu",
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
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerOrderError("交易上下文未初始化", broker="Futu")

        # 确定订单类型
        if order_type == OrderType.MARKET:
            trd_side = futu.TrdSide.BUY if side == OrderSide.BUY else futu.TrdSide.SELL
            order_type_futu = futu.OrderType.MARKET
        else:
            trd_side = futu.TrdSide.BUY if side == OrderSide.BUY else futu.TrdSide.SELL
            order_type_futu = futu.OrderType.NORMAL

        # 确定价格
        if price is None and order_type == OrderType.LIMIT:
            raise BrokerOrderError(
                "限价单必须指定价格",
                broker="Futu"
            )

        # 下单参数
        trd_params = {
            'code': symbol,
            'price': price if price else 0,
            'qty': int(quantity),
            'trd_side': trd_side,
            'order_type': order_type_futu,
            'trd_env': futu.TrdEnv.REAL,
        }

        logger.info(
            f"Futu OpenD: 下单请求 symbol={symbol}, side={side.value}, "
            f"type={order_type.value}, qty={quantity}, price={price}"
        )

        ret, data = self._trade_ctx.place_order(**trd_params)

        if ret != RET_OK:
            raise BrokerOrderError(
                f"下单失败: {data}",
                broker="Futu"
            )

        if data.empty:
            raise BrokerOrderError(
                "下单返回数据为空",
                broker="Futu"
            )

        order_id = str(data.iloc[0].get('order_id', ''))

        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.SUBMITTED,
            broker="futu",
        )

        logger.info(f"Futu OpenD: 下单成功, order_id={order_id}")
        return order

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
                broker="Futu",
                order_id=order_id
            )

    def _cancel_order_sync(self, order_id: str) -> bool:
        """同步撤销订单"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerOrderError("交易上下文未初始化", broker="Futu")

        ret, data = self._trade_ctx.modify_order(
            modify_order_op=futu.ModifyOrderOp.CANCEL,
            order_id=int(order_id),
        )

        if ret != RET_OK:
            logger.error(f"Futu OpenD: 撤单失败: {data}")
            return False

        logger.info(f"Futu OpenD: 撤单成功, order_id={order_id}")
        return True

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
            raise BrokerError(f"查询订单失败: {e}", broker="Futu")

    def _get_order_sync(self, order_id: str) -> Order:
        """同步查询单个订单"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerError("交易上下文未初始化", broker="Futu")

        ret, data = self._trade_ctx.order_list_query(
            order_id=int(order_id),
        )

        if ret != RET_OK:
            raise BrokerError(f"查询订单失败: {data}", broker="Futu")

        if data.empty:
            raise BrokerError(f"未找到订单: {order_id}", broker="Futu")

        return self._convert_order(data.iloc[0])

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
            raise BrokerError(f"查询订单列表失败: {e}", broker="Futu")

    def _get_orders_sync(
        self,
        status: Optional[str],
        symbol: Optional[str],
        kwargs: Dict[str, Any]
    ) -> List[Order]:
        """同步查询订单列表"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._trade_ctx:
            raise BrokerError("交易上下文未初始化", broker="Futu")

        # 构建查询过滤条件
        filter_dict = {}
        if status:
            status_map = {
                'pending': [futu.OrderStatus.SUBMITTED],
                'submitted': [futu.OrderStatus.SUBMITTED],
                'filled': [futu.OrderStatus.FILLED_ALL, futu.OrderStatus.FILLED_PART],
                'partially_filled': [futu.OrderStatus.FILLED_PART],
                'cancelled': [futu.OrderStatus.CANCELLED_ALL],
                'rejected': [futu.OrderStatus.FAILED],
            }
            filter_dict['status'] = status_map.get(status.lower(), [])

        ret, data = self._trade_ctx.order_list_query(
            status_filter_list=filter_dict.get('status'),
            code=symbol,
        )

        if ret != RET_OK:
            raise BrokerError(f"查询订单列表失败: {data}", broker="Futu")

        if data.empty:
            return []

        orders = []
        for _, row in data.iterrows():
            orders.append(self._convert_order(row))

        logger.info(f"Futu OpenD: 查询到 {len(orders)} 个订单")
        return orders

    def _convert_order(self, row: Any) -> Order:
        """将 Futu 订单数据转换为内部 Order 模型"""
        futu = self._futu_module

        status_map = {
            futu.OrderStatus.UNSUBMITTED: OrderStatus.PENDING,
            futu.OrderStatus.SUBMITTED: OrderStatus.SUBMITTED,
            futu.OrderStatus.FILLED_PART: OrderStatus.PARTIALLY_FILLED,
            futu.OrderStatus.FILLED_ALL: OrderStatus.FILLED,
            futu.OrderStatus.CANCELLED_PART: OrderStatus.CANCELLED,
            futu.OrderStatus.CANCELLED_ALL: OrderStatus.CANCELLED,
            futu.OrderStatus.FAILED: OrderStatus.REJECTED,
        }

        order_status_raw = row.get('order_status', '')
        order_status = status_map.get(order_status_raw, OrderStatus.PENDING)

        side_map = {
            futu.TrdSide.BUY: OrderSide.BUY,
            futu.TrdSide.SELL: OrderSide.SELL,
        }
        order_side_raw = row.get('trd_side', '')
        order_side = side_map.get(order_side_raw, OrderSide.BUY)

        type_map = {
            futu.OrderType.MARKET: OrderType.MARKET,
            futu.OrderType.NORMAL: OrderType.LIMIT,
        }
        order_type_raw = row.get('order_type', '')
        order_type = type_map.get(order_type_raw, OrderType.MARKET)

        return Order(
            order_id=str(row.get('order_id', '')),
            symbol=str(row.get('code', '')),
            side=order_side,
            order_type=order_type,
            quantity=float(row.get('qty', 0) or 0),
            price=float(row.get('price', 0) or 0),
            status=order_status,
            filled_quantity=float(row.get('dealt_qty', 0) or 0),
            filled_price=float(row.get('dealt_avg_price', 0) or 0),
            fee=float(row.get('commission', 0) or 0),
            broker="futu",
        )

    async def subscribe_quote(
        self,
        symbols: List[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """订阅实时行情"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._subscribe_quote_sync, symbols, callback
            )
            logger.info(f"Futu OpenD: 订阅行情成功, symbols={symbols}")
        except Exception as e:
            raise BrokerError(f"订阅行情失败: {e}", broker="Futu")

    def _subscribe_quote_sync(
        self,
        symbols: List[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ):
        """同步订阅行情"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._quote_ctx:
            raise BrokerError("行情上下文未初始化", broker="Futu")

        # 注册回调
        for symbol in symbols:
            self._quote_callbacks[symbol] = callback

        # 设置行情回调处理器
        def quote_handler(symbol, data):
            """行情数据回调"""
            try:
                quote_data = {
                    "symbol": symbol,
                    "open": float(data.get('open_price', 0) or 0),
                    "high": float(data.get('high_price', 0) or 0),
                    "low": float(data.get('low_price', 0) or 0),
                    "close": float(data.get('cur_price', 0) or 0),
                    "volume": float(data.get('volume', 0) or 0),
                    "prev_close": float(data.get('prev_close_price', 0) or 0),
                    "timestamp": datetime.now().isoformat(),
                    "bid_price": float(data.get('bid_price', 0) or 0),
                    "ask_price": float(data.get('ask_price', 0) or 0),
                    "turnover": float(data.get('turnover', 0) or 0),
                }

                # 在事件循环中执行回调
                cb = self._quote_callbacks.get(symbol)
                if cb:
                    loop = asyncio.get_event_loop()
                    loop.create_task(cb(quote_data))
            except Exception as e:
                logger.error(f"Futu OpenD: 行情回调处理异常: {e}")

        self._quote_ctx.set_handler(quote_handler)

        # 订阅
        ret, data = self._quote_ctx.subscribe(symbols, [futu.SubType.QUOTE])
        if ret != RET_OK:
            raise BrokerError(f"订阅行情失败: {data}", broker="Futu")

    async def unsubscribe_quote(self, symbols: List[str]) -> None:
        """取消订阅行情"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._unsubscribe_quote_sync, symbols
            )

            for symbol in symbols:
                self._quote_callbacks.pop(symbol, None)

            logger.info(f"Futu OpenD: 取消订阅行情, symbols={symbols}")
        except Exception as e:
            raise BrokerError(f"取消订阅行情失败: {e}", broker="Futu")

    def _unsubscribe_quote_sync(self, symbols: List[str]):
        """同步取消订阅行情"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._quote_ctx:
            return

        ret, data = self._quote_ctx.unsubscribe(symbols, [futu.SubType.QUOTE])
        if ret != RET_OK:
            logger.warning(f"Futu OpenD: 取消订阅行情失败: {data}")

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
            raise BrokerError(f"获取行情失败: {e}", broker="Futu")

    def _get_quote_sync(self, symbol: str) -> Dict[str, Any]:
        """同步获取行情"""
        futu = self._futu_module
        RET_OK = futu.RET_OK

        if not self._quote_ctx:
            raise BrokerError("行情上下文未初始化", broker="Futu")

        ret, data = self._quote_ctx.get_market_snapshot([symbol])

        if ret != RET_OK:
            raise BrokerError(f"获取行情失败: {data}", broker="Futu")

        if data.empty:
            raise BrokerError(f"未获取到行情数据: {symbol}", broker="Futu")

        row = data.iloc[0]
        quote_data = {
            "symbol": symbol,
            "open": float(row.get('open_price', 0) or 0),
            "high": float(row.get('high_price', 0) or 0),
            "low": float(row.get('low_price', 0) or 0),
            "close": float(row.get('cur_price', 0) or 0),
            "volume": float(row.get('volume', 0) or 0),
            "prev_close": float(row.get('prev_close_price', 0) or 0),
            "timestamp": datetime.now().isoformat(),
            "bid_price": float(row.get('bid_price', 0) or 0),
            "ask_price": float(row.get('ask_price', 0) or 0),
            "bid_volume": float(row.get('bid_vol', 0) or 0),
            "ask_volume": float(row.get('ask_vol', 0) or 0),
            "turnover": float(row.get('turnover', 0) or 0),
        }

        logger.debug(f"Futu OpenD: 获取行情成功, symbol={symbol}")
        return quote_data
