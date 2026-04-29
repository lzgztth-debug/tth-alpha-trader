# src/adapters/brokers/huobi.py
# 火币适配器 - 使用 ccxt 库实现加密货币现货和合约交易

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


class HuobiBrokerAdapter(BaseBrokerAdapter):
    """
    火币适配器

    使用 ccxt 库对接火币API，支持现货和合约交易。

    配置参数:
        api_key: API Key
        secret_key: Secret Key
        passphrase: API Passphrase（部分交易所需要）
        sandbox: 是否使用测试网，默认 False
        default_type: 默认交易类型，spot（现货）或 swap（合约）
        options: ccxt 额外配置选项
    """

    # 交易类型映射
    SPOT = "spot"
    SWAP = "swap"
    FUTURE = "future"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.secret_key = config.get("secret_key", "")
        self.passphrase = config.get("passphrase", "")
        self.sandbox = config.get("sandbox", False)
        self.default_type = config.get("default_type", self.SPOT)
        self.options = config.get("options", {})

        self._exchange = None
        self._ws_connected = False

        if not self.api_key or not self.secret_key:
            logger.warning("Huobi: api_key 或 secret_key 未配置")

    def _init_exchange(self):
        """初始化 ccxt 交易所实例"""
        try:
            import ccxt.async_support as ccxt

            exchange_config = {
                'apiKey': self.api_key,
                'secret': self.secret_key,
                'enableRateLimit': True,
                'options': {
                    'defaultType': self.default_type,
                    **self.options,
                },
            }

            if self.passphrase:
                exchange_config['password'] = self.passphrase

            if self.sandbox:
                exchange_config['sandbox'] = True
                logger.info("Huobi: 使用测试网环境")

            self._exchange = ccxt.huobi(exchange_config)
            logger.info("Huobi: ccxt 交易所实例初始化成功")

        except ImportError:
            raise BrokerConnectionError(
                "ccxt 未安装，请执行: pip install ccxt",
                broker="Huobi"
            )
        except Exception as e:
            raise BrokerConnectionError(
                f"初始化交易所失败: {e}",
                broker="Huobi"
            )

    async def connect(self) -> bool:
        """连接火币交易所"""
        try:
            self._init_exchange()

            # 验证连接 - 获取账户余额
            await self._exchange.load_markets()
            balance = await self._exchange.fetch_balance()

            self._connected = True
            logger.info(
                f"Huobi: 连接成功 (sandbox={self.sandbox}, "
                f"type={self.default_type})"
            )
            return True

        except BrokerConnectionError:
            raise
        except Exception as e:
            self._connected = False
            raise BrokerConnectionError(
                f"连接失败: {e}",
                broker="Huobi"
            )

    async def disconnect(self) -> None:
        """断开火币连接"""
        try:
            if self._exchange:
                await self._exchange.close()
                self._exchange = None
            self._connected = False
            self._ws_connected = False
            logger.info("Huobi: 已断开连接")
        except Exception as e:
            logger.warning(f"Huobi: 断开连接时出错: {e}")
            self._connected = False

    async def get_account(self) -> Account:
        """获取账户信息"""
        self._ensure_connected()
        try:
            balance = await self._exchange.fetch_balance()

            # 计算总资产（仅计算非零余额）
            total_value = 0.0
            for currency, data in balance.get('total', {}).items():
                amount = float(data) if data else 0.0
                if amount > 0:
                    # 尝试获取USD估值
                    try:
                        ticker = await self._exchange.fetch_ticker(f"{currency}/USDT")
                        price = float(ticker.get('last', 0) or 0)
                        total_value += amount * price
                    except Exception:
                        # 无法获取价格时跳过
                        pass

            # 获取USDT余额作为现金
            usdt_free = float(
                balance.get('free', {}).get('USDT', 0) or 0
            )
            usdt_used = float(
                balance.get('used', {}).get('USDT', 0) or 0
            )

            account = Account(
                account_id=self.api_key[:8] + "...",
                broker="huobi",
                account_type=AccountType.PAPER if self.sandbox else AccountType.REAL,
                total_value=total_value,
                cash=usdt_free,
                market_value=total_value - usdt_free,
                available_cash=usdt_free,
                currency="USDT",
                updated_at=datetime.now().isoformat(),
            )

            logger.info(f"Huobi: 获取账户信息成功, 总资产约={total_value:.2f} USDT")
            return account

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取账户信息失败: {e}", broker="Huobi")

    async def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        self._ensure_connected()
        try:
            if self.default_type in (self.SWAP, self.FUTURE):
                positions = await self._get_swap_positions()
            else:
                positions = await self._get_spot_positions()

            logger.info(f"Huobi: 获取持仓成功, 共 {len(positions)} 个持仓")
            return positions

        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"获取持仓失败: {e}", broker="Huobi")

    async def _get_spot_positions(self) -> List[Position]:
        """获取现货持仓"""
        balance = await self._exchange.fetch_balance()

        positions = []
        for currency, data in balance.get('total', {}).items():
            amount = float(data) if data else 0.0
            if amount <= 0:
                continue

            free = float(balance.get('free', {}).get(currency, 0) or 0)
            used = float(balance.get('used', {}).get(currency, 0) or 0)

            # 获取当前价格
            try:
                ticker = await self._exchange.fetch_ticker(f"{currency}/USDT")
                current_price = float(ticker.get('last', 0) or 0)
            except Exception:
                current_price = 0.0

            market_value = amount * current_price

            positions.append(Position(
                symbol=f"{currency}/USDT",
                quantity=amount,
                avg_cost=0.0,  # 现货无平均成本
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                broker="huobi",
            ))

        return positions

    async def _get_swap_positions(self) -> List[Position]:
        """获取合约持仓"""
        try:
            positions_data = await self._exchange.fetch_positions()

            positions = []
            for pos in positions_data:
                symbol = pos.get('symbol', '')
                contracts = float(pos.get('contracts', 0) or 0)
                if contracts <= 0:
                    continue

                entry_price = float(pos.get('entryPrice', 0) or 0)
                mark_price = float(pos.get('markPrice', 0) or 0)
                notional = float(pos.get('notional', 0) or 0)
                unrealized_pnl = float(pos.get('unrealizedPnl', 0) or 0)
                side = pos.get('side', '')

                positions.append(Position(
                    symbol=symbol,
                    quantity=contracts,
                    avg_cost=entry_price,
                    current_price=mark_price,
                    market_value=notional,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=(
                        unrealized_pnl / abs(notional) * 100
                        if notional != 0 else 0.0
                    ),
                    broker="huobi",
                ))

            return positions

        except Exception as e:
            logger.warning(f"Huobi: 获取合约持仓失败: {e}")
            return []

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

        # 验证参数
        if order_type == OrderType.LIMIT and price is None:
            raise BrokerOrderError(
                "限价单必须指定价格",
                broker="Huobi"
            )

        try:
            ccxt_side = 'buy' if side == OrderSide.BUY else 'sell'
            ccxt_type = 'limit' if order_type == OrderType.LIMIT else 'market'

            order_params = {
                'symbol': symbol,
                'type': ccxt_type,
                'side': ccxt_side,
                'amount': quantity,
            }

            if order_type == OrderType.LIMIT and price is not None:
                order_params['price'] = price

            # 合约交易额外参数
            if self.default_type in (self.SWAP, self.FUTURE):
                order_params.setdefault('params', {})
                # 设置杠杆（如果指定）
                leverage = kwargs.get('leverage')
                if leverage:
                    order_params['params']['leverage'] = leverage

            logger.info(
                f"Huobi: 下单请求 symbol={symbol}, side={ccxt_side}, "
                f"type={ccxt_type}, qty={quantity}, price={price}"
            )

            result = await self._exchange.create_order(**order_params)

            order = Order(
                order_id=str(result.get('id', '')),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=self._convert_status(result.get('status', 'open')),
                filled_quantity=float(result.get('filled', 0) or 0),
                filled_price=float(result.get('average', 0) or 0),
                fee=float(result.get('fee', 0) or 0),
                broker="huobi",
            )

            logger.info(f"Huobi: 下单成功, order_id={order.order_id}")
            return order

        except BrokerOrderError:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Huobi: 下单失败: {error_msg}")
            raise BrokerOrderError(
                f"下单失败: {error_msg}",
                broker="Huobi"
            )

    async def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        self._ensure_connected()
        try:
            result = await self._exchange.cancel_order(order_id)
            status = result.get('status', '')

            if status == 'canceled':
                logger.info(f"Huobi: 撤单成功, order_id={order_id}")
                return True
            else:
                logger.warning(
                    f"Huobi: 撤单返回状态={status}, order_id={order_id}"
                )
                return True

        except Exception as e:
            logger.error(f"Huobi: 撤单失败: {e}")
            raise BrokerOrderError(
                f"撤单失败: {e}",
                broker="Huobi",
                order_id=order_id
            )

    async def get_order(self, order_id: str) -> Order:
        """查询单个订单详情"""
        self._ensure_connected()
        try:
            result = await self._exchange.fetch_order(order_id)
            return self._convert_order(result)
        except Exception as e:
            raise BrokerError(f"查询订单失败: {e}", broker="Huobi")

    async def get_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ) -> List[Order]:
        """查询订单列表"""
        self._ensure_connected()
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            if status:
                params['state'] = self._reverse_status(status)

            # 使用 since 参数分页
            since = kwargs.get('since')
            if since:
                params['since'] = since

            limit = kwargs.get('limit', 50)
            orders_raw = await self._exchange.fetch_orders(
                symbol=symbol,
                since=since,
                limit=limit,
            )

            orders = [self._convert_order(o) for o in orders_raw]

            # 按状态过滤
            if status:
                orders = [o for o in orders if o.status.value == status.lower()]

            logger.info(f"Huobi: 查询到 {len(orders)} 个订单")
            return orders

        except Exception as e:
            raise BrokerError(f"查询订单列表失败: {e}", broker="Huobi")

    def _convert_order(self, raw_order: Dict[str, Any]) -> Order:
        """将 ccxt 订单转换为内部 Order 模型"""
        side_map = {
            'buy': OrderSide.BUY,
            'sell': OrderSide.SELL,
        }
        type_map = {
            'market': OrderType.MARKET,
            'limit': OrderType.LIMIT,
        }

        raw_side = raw_order.get('side', 'buy')
        raw_type = raw_order.get('type', 'market')

        return Order(
            order_id=str(raw_order.get('id', '')),
            symbol=raw_order.get('symbol', ''),
            side=side_map.get(raw_side, OrderSide.BUY),
            order_type=type_map.get(raw_type, OrderType.MARKET),
            quantity=float(raw_order.get('amount', 0) or 0),
            price=float(raw_order.get('price', 0) or 0),
            status=self._convert_status(raw_order.get('status', 'open')),
            filled_quantity=float(raw_order.get('filled', 0) or 0),
            filled_price=float(raw_order.get('average', 0) or 0),
            fee=float(raw_order.get('fee', 0) or 0),
            broker="huobi",
        )

    def _convert_status(self, ccxt_status: str) -> OrderStatus:
        """将 ccxt 订单状态转换为内部状态"""
        status_map = {
            'open': OrderStatus.PENDING,
            'pending': OrderStatus.PENDING,
            'partially_filled': OrderStatus.PARTIAL_FILLED,
            'filled': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'closed': OrderStatus.FILLED,
            'expired': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
        }
        return status_map.get(ccxt_status, OrderStatus.PENDING)

    def _reverse_status(self, internal_status: str) -> str:
        """将内部状态转换为 ccxt 状态"""
        reverse_map = {
            'pending': 'open',
            'partially_filled': 'open',
            'filled': 'closed',
            'cancelled': 'canceled',
            'rejected': 'rejected',
            'expired': 'canceled',
        }
        return reverse_map.get(internal_status.lower(), 'open')

    async def subscribe_quote(
        self,
        symbols: List[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """订阅实时行情（使用 WebSocket）"""
        self._ensure_connected()
        try:
            for symbol in symbols:
                self._quote_callbacks[symbol] = callback

            # 使用 ccxt watch_ticker 实现
            async def _watch_loop():
                """行情监控循环"""
                self._ws_connected = True
                while self._ws_connected:
                    try:
                        for symbol in list(self._quote_callbacks.keys()):
                            try:
                                ticker = await self._exchange.watch_ticker(symbol)
                                quote_data = self._ticker_to_quote(ticker)
                                cb = self._quote_callbacks.get(symbol)
                                if cb:
                                    await cb(quote_data)
                            except Exception as e:
                                logger.error(
                                    f"Huobi: 获取 {symbol} 行情异常: {e}"
                                )
                                await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Huobi: 行情监控异常: {e}")
                        await asyncio.sleep(5)

            # 启动监控任务
            self._watch_task = asyncio.create_task(_watch_loop())
            logger.info(f"Huobi: 订阅行情成功, symbols={symbols}")

        except Exception as e:
            raise BrokerError(f"订阅行情失败: {e}", broker="Huobi")

    async def unsubscribe_quote(self, symbols: List[str]) -> None:
        """取消订阅行情"""
        for symbol in symbols:
            self._quote_callbacks.pop(symbol, None)

        if not self._quote_callbacks:
            self._ws_connected = False
            if hasattr(self, '_watch_task') and self._watch_task:
                self._watch_task.cancel()
                try:
                    await self._watch_task
                except asyncio.CancelledError:
                    pass

        logger.info(f"Huobi: 取消订阅行情, symbols={symbols}")

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """获取单个标的实时行情"""
        self._ensure_connected()
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            quote_data = self._ticker_to_quote(ticker)
            logger.debug(f"Huobi: 获取行情成功, symbol={symbol}")
            return quote_data
        except Exception as e:
            raise BrokerError(f"获取行情失败: {e}", broker="Huobi")

    def _ticker_to_quote(self, ticker: Dict[str, Any]) -> Dict[str, Any]:
        """将 ccxt ticker 转换为行情数据字典"""
        return {
            "symbol": ticker.get('symbol', ''),
            "open": float(ticker.get('open', 0) or 0),
            "high": float(ticker.get('high', 0) or 0),
            "low": float(ticker.get('low', 0) or 0),
            "close": float(ticker.get('last', 0) or 0),
            "volume": float(ticker.get('baseVolume', 0) or 0),
            "prev_close": float(ticker.get('previousClose', 0) or 0),
            "timestamp": datetime.now().isoformat(),
            "bid_price": float(ticker.get('bid', 0) or 0),
            "ask_price": float(ticker.get('ask', 0) or 0),
            "bid_volume": float(ticker.get('bidVolume', 0) or 0),
            "ask_volume": float(ticker.get('askVolume', 0) or 0),
            "turnover": float(ticker.get('quoteVolume', 0) or 0),
        }
