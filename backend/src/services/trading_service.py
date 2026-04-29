"""交易服务模块

整合交易引擎和券商适配器，提供统一的交易操作接口。
支持模拟/实盘模式切换，实现交易告警通知。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from src.models.account import Account, AccountType
from src.models.decision import Decision, DecisionAction
from src.models.order import Order, OrderSide, OrderStatus, OrderType


# ---------------------------------------------------------------------------
# 告警级别枚举
# ---------------------------------------------------------------------------

class AlertLevel(str, Enum):
    """交易告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TradingAlert:
    """交易告警数据"""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 交易引擎基类 (当 core 模块尚未实现时的本地占位)
# ---------------------------------------------------------------------------

class _TradingEngineStub:
    """交易引擎桩实现，当 core.trading_engine 不可用时提供基本功能。"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._connected = False

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class _PaperTradingEngineStub(_TradingEngineStub):
    """模拟交易引擎桩实现。"""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Dict[str, float]] = {}  # account_id -> {symbol: qty}
        self._accounts: Dict[str, Dict[str, float]] = {}  # account_id -> {cash, ...}

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        account_id: str = "",
    ) -> Order:
        order_id = f"paper_{uuid.uuid4().hex[:12]}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=price or 0.0,
            account_id=account_id,
            broker="paper_broker",
            created_at=datetime.now(),
            filled_at=datetime.now(),
        )
        self._orders[order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.status in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED):
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def get_orders(self, account_id: str = "") -> List[Order]:
        orders = list(self._orders.values())
        if account_id:
            orders = [o for o in orders if o.account_id == account_id]
        return orders


# ---------------------------------------------------------------------------
# 事件总线桩实现
# ---------------------------------------------------------------------------

class _EventBusStub:
    """事件总线桩实现，当 core.event_bus 不可用时提供基本功能。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    async def publish(self, event_type: str, data: Any = None) -> None:
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"事件处理失败: {event_type}, 错误: {e}")


# ---------------------------------------------------------------------------
# 尝试导入核心模块，失败时使用桩实现
# ---------------------------------------------------------------------------

try:
    from src.core.trading_engine import TradingEngine
    from src.core.paper_trading import PaperTradingEngine
    from src.core.event_bus import EventBus

    _HAS_CORE = True
    logger.debug("核心模块导入成功，使用正式实现")
except ImportError:
    TradingEngine = _TradingEngineStub  # type: ignore[assignment, misc]
    PaperTradingEngine = _PaperTradingEngineStub  # type: ignore[assignment, misc]
    EventBus = _EventBusStub  # type: ignore[assignment, misc]
    _HAS_CORE = False
    logger.warning("核心模块不可用，使用桩实现 (stub)")


# ---------------------------------------------------------------------------
# 券商适配器桩实现
# ---------------------------------------------------------------------------

class _BrokerAdapterStub:
    """券商适配器桩实现。"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._connected = False
        self._orders: Dict[str, Order] = {}

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def get_account(self) -> Account:
        return Account(
            account_id=self.config.get("account_id", "default"),
            broker=self.config.get("broker", "stub_broker"),
            account_type=AccountType.REAL,
            total_value=0.0,
            cash=0.0,
        )

    async def get_positions(self) -> List:
        return []

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        **kwargs,
    ) -> Order:
        order_id = f"live_{uuid.uuid4().hex[:12]}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            account_id=kwargs.get("account_id", ""),
            broker=self.config.get("broker", "stub_broker"),
            created_at=datetime.now(),
        )
        self._orders[order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    async def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    async def get_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs,
    ) -> List[Order]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders


# ---------------------------------------------------------------------------
# TradingService
# ---------------------------------------------------------------------------

class TradingService:
    """交易服务

    整合交易引擎和券商适配器，提供统一的交易操作接口。
    支持模拟/实盘模式切换，实现交易告警通知。

    Usage::

        service = TradingService(mode="paper")
        await service.initialize()

        order = await service.execute_decision(decision)
        orders = await service.get_orders()

        await service.shutdown()
    """

    def __init__(
        self,
        mode: str = "paper",
        broker_config: Optional[Dict[str, Any]] = None,
        engine_config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        初始化交易服务。

        Args:
            mode:          交易模式，"paper" 或 "live"。
            broker_config: 券商适配器配置。
            engine_config: 交易引擎配置。
            event_bus:     事件总线实例，为 None 时自动创建。
        """
        self._mode = mode.lower()
        self._broker_config = broker_config or {}
        self._engine_config = engine_config or {}
        self._event_bus = event_bus or EventBus()

        # 引擎和适配器实例
        self._engine: Optional[Any] = None
        self._broker: Optional[Any] = None
        self._initialized = False

        # 告警回调列表
        self._alert_callbacks: List[Callable[[TradingAlert], Any]] = []

        # 当日交易计数
        self._daily_trade_count = 0
        self._daily_trade_date: Optional[str] = None

        # 风控参数
        self._max_position_size: float = 10000.0
        self._max_daily_trades: int = 50
        self._stop_loss_pct: float = 2.0
        self._take_profit_pct: float = 5.0

        logger.info(f"TradingService 已创建, 模式={self._mode}")

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        """当前交易模式"""
        return self._mode

    @property
    def is_paper_mode(self) -> bool:
        """是否为模拟模式"""
        return self._mode == "paper"

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def event_bus(self) -> EventBus:
        """事件总线"""
        return self._event_bus

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """初始化交易服务，连接引擎和券商适配器。"""
        if self._initialized:
            logger.warning("TradingService 已经初始化，跳过重复初始化")
            return

        try:
            if self._mode == "paper":
                self._engine = PaperTradingEngine(self._engine_config)
            else:
                self._engine = TradingEngine(self._engine_config)

            await self._engine.connect()

            if self._mode == "live" and self._broker_config:
                self._broker = _BrokerAdapterStub(self._broker_config)
                await self._broker.connect()

            # 注册事件处理
            self._event_bus.subscribe("order_placed", self._on_order_placed)
            self._event_bus.subscribe("order_cancelled", self._on_order_cancelled)
            self._event_bus.subscribe("order_filled", self._on_order_filled)

            self._initialized = True
            logger.info(f"TradingService 初始化完成, 模式={self._mode}")

        except Exception as e:
            logger.error(f"TradingService 初始化失败: {e}")
            raise RuntimeError(f"交易服务初始化失败: {e}") from e

    async def shutdown(self) -> None:
        """关闭交易服务，释放资源。"""
        try:
            if self._engine:
                await self._engine.disconnect()
            if self._broker:
                await self._broker.disconnect()

            self._event_bus.unsubscribe("order_placed", self._on_order_placed)
            self._event_bus.unsubscribe("order_cancelled", self._on_order_cancelled)
            self._event_bus.unsubscribe("order_filled", self._on_order_filled)

            self._initialized = False
            logger.info("TradingService 已关闭")

        except Exception as e:
            logger.error(f"TradingService 关闭异常: {e}")

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------

    async def switch_mode(self, new_mode: str) -> None:
        """切换交易模式。

        Args:
            new_mode: 新的交易模式 ("paper" 或 "live")。
        """
        if new_mode not in ("paper", "live"):
            raise ValueError(f"无效的交易模式: {new_mode}，仅支持 'paper' 或 'live'")

        if new_mode == self._mode:
            logger.info(f"已在 {new_mode} 模式下，无需切换")
            return

        old_mode = self._mode
        logger.info(f"切换交易模式: {old_mode} -> {new_mode}")

        # 关闭当前引擎
        await self.shutdown()

        # 更新模式并重新初始化
        self._mode = new_mode
        await self.initialize()

        await self._send_alert(
            AlertLevel.INFO,
            "交易模式已切换",
            f"交易模式从 {old_mode} 切换为 {new_mode}",
        )

    # ------------------------------------------------------------------
    # 核心交易方法
    # ------------------------------------------------------------------

    async def execute_decision(
        self,
        decision: Decision,
        account_id: str = "",
    ) -> Optional[Order]:
        """执行 AI 决策。

        将 AI 决策转化为实际的交易订单。

        Args:
            decision:   AI 决策对象。
            account_id: 目标账户ID。

        Returns:
            执行成功返回 Order 对象，hold 决策或失败返回 None。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化，请先调用 initialize()")

        # 检查当日交易限额
        await self._check_daily_limit()

        # HOLD 决策不执行交易
        if decision.action == DecisionAction.HOLD:
            logger.info(f"决策为 HOLD，不执行交易: {decision.decision_id}")
            await self._event_bus.publish("decision_hold", {
                "decision_id": decision.decision_id,
                "symbol": decision.symbol,
            })
            return None

        # 参数校验
        if not decision.symbol:
            logger.warning(f"决策缺少标的代码，跳过执行: {decision.decision_id}")
            return None

        if decision.quantity is None or decision.quantity <= 0:
            logger.warning(f"决策数量无效，跳过执行: {decision.decision_id}")
            return None

        # 风控检查
        if not await self._risk_check(decision):
            logger.warning(f"风控检查未通过，拒绝执行: {decision.decision_id}")
            await self._send_alert(
                AlertLevel.WARNING,
                "风控拦截",
                f"决策 {decision.decision_id} 未通过风控检查，已拒绝执行",
                {"decision_id": decision.decision_id, "symbol": decision.symbol},
            )
            return None

        # 确定买卖方向
        side = (
            OrderSide.BUY
            if decision.action == DecisionAction.BUY
            else OrderSide.SELL
        )

        # 确定订单类型和价格
        order_type = OrderType.LIMIT if decision.price else OrderType.MARKET
        price = decision.price

        logger.info(
            f"执行决策: {decision.decision_id} "
            f"{side.value} {decision.symbol} x{decision.quantity} "
            f"@{price or '市价'} (置信度={decision.confidence:.2f})"
        )

        try:
            order = await self.place_order(
                symbol=decision.symbol,
                side=side,
                quantity=decision.quantity,
                order_type=order_type,
                price=price,
                account_id=account_id,
            )

            # 更新当日交易计数
            self._increment_daily_trade_count()

            # 发布事件
            await self._event_bus.publish("decision_executed", {
                "decision_id": decision.decision_id,
                "order_id": order.order_id,
                "symbol": decision.symbol,
                "side": side.value,
                "quantity": decision.quantity,
                "confidence": decision.confidence,
            })

            # 发送交易告警
            await self._send_alert(
                AlertLevel.INFO,
                f"交易执行: {side.value.upper()} {decision.symbol}",
                f"数量={decision.quantity}, 价格={price or '市价'}, "
                f"置信度={decision.confidence:.2f}, 订单ID={order.order_id}",
                {
                    "decision_id": decision.decision_id,
                    "order_id": order.order_id,
                    "symbol": decision.symbol,
                    "side": side.value,
                    "quantity": decision.quantity,
                },
            )

            return order

        except Exception as e:
            logger.error(f"执行决策失败: {decision.decision_id}, 错误: {e}")
            await self._send_alert(
                AlertLevel.CRITICAL,
                "交易执行失败",
                f"决策 {decision.decision_id} 执行失败: {e}",
                {"decision_id": decision.decision_id, "error": str(e)},
            )
            return None

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        account_id: str = "",
    ) -> Order:
        """下单。

        Args:
            symbol:     标的代码。
            side:       买卖方向。
            quantity:   委托数量。
            order_type: 订单类型。
            price:      委托价格 (限价单必填)。
            account_id: 所属账户ID。

        Returns:
            Order 对象。

        Raises:
            RuntimeError: 服务未初始化。
            ValueError:   参数无效。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化，请先调用 initialize()")

        if not symbol or not symbol.strip():
            raise ValueError("标的代码不能为空")

        if quantity <= 0:
            raise ValueError("委托数量必须大于 0")

        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("限价单必须指定价格")

        start_time = time.monotonic()

        try:
            if self._mode == "paper" and self._engine:
                order = await self._engine.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    price=price,
                    account_id=account_id,
                )
            elif self._broker:
                order = await self._broker.place_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    price=price,
                    account_id=account_id,
                )
            else:
                raise RuntimeError("无可用交易引擎或券商适配器")

            elapsed = (time.monotonic() - start_time) * 1000
            logger.info(
                f"下单成功: {order.order_id} {side.value} {symbol} "
                f"x{quantity} @{price or '市价'} ({elapsed:.1f}ms)"
            )

            await self._event_bus.publish("order_placed", {
                "order_id": order.order_id,
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "price": price,
                "account_id": account_id,
                "mode": self._mode,
            })

            return order

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.error(f"下单失败: {symbol} {side.value} x{quantity}, 错误: {e} ({elapsed:.1f}ms)")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """撤销订单。

        Args:
            order_id: 订单ID。

        Returns:
            是否撤单成功。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化")

        try:
            if self._mode == "paper" and self._engine:
                success = await self._engine.cancel_order(order_id)
            elif self._broker:
                success = await self._broker.cancel_order(order_id)
            else:
                raise RuntimeError("无可用交易引擎或券商适配器")

            if success:
                logger.info(f"撤单成功: {order_id}")
                await self._event_bus.publish("order_cancelled", {
                    "order_id": order_id,
                    "mode": self._mode,
                })
            else:
                logger.warning(f"撤单失败 (订单可能不可撤): {order_id}")

            return success

        except Exception as e:
            logger.error(f"撤单异常: {order_id}, 错误: {e}")
            raise

    async def get_orders(
        self,
        account_id: str = "",
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Order]:
        """查询订单列表。

        Args:
            account_id: 按账户ID筛选。
            symbol:     按标的代码筛选。
            status:     按订单状态筛选。

        Returns:
            Order 列表。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化")

        try:
            if self._mode == "paper" and self._engine:
                orders = self._engine.get_orders(account_id)
            elif self._broker:
                orders = await self._broker.get_orders(
                    status=status,
                    symbol=symbol,
                    account_id=account_id,
                )
            else:
                return []

            # 内存过滤
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            if status:
                orders = [o for o in orders if o.status.value == status]

            return orders

        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            return []

    async def get_positions(self, account_id: str = "") -> List:
        """查询持仓列表。

        Args:
            account_id: 账户ID。

        Returns:
            持仓列表。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化")

        try:
            if self._mode == "paper" and self._engine:
                if hasattr(self._engine, "get_positions"):
                    return await self._engine.get_positions(account_id)
                return []
            elif self._broker:
                return await self._broker.get_positions()
            return []

        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return []

    async def get_account(self, account_id: str = "") -> Optional[Account]:
        """查询账户信息。

        Args:
            account_id: 账户ID。

        Returns:
            Account 对象，失败返回 None。
        """
        if not self._initialized:
            raise RuntimeError("TradingService 未初始化")

        try:
            if self._mode == "live" and self._broker:
                return await self._broker.get_account()
            elif self._mode == "paper" and self._engine:
                if hasattr(self._engine, "get_account"):
                    return await self._engine.get_account(account_id)
                return Account(
                    account_id=account_id or "paper_default",
                    broker="paper_broker",
                    account_type=AccountType.PAPER,
                    total_value=0.0,
                    cash=0.0,
                )
            return None

        except Exception as e:
            logger.error(f"查询账户失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 告警管理
    # ------------------------------------------------------------------

    def add_alert_callback(
        self,
        callback: Callable[[TradingAlert], Any],
    ) -> None:
        """添加告警回调函数。

        Args:
            callback: 告警回调，接收 TradingAlert 参数。
        """
        self._alert_callbacks.append(callback)
        logger.debug(f"告警回调已添加: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def remove_alert_callback(
        self,
        callback: Callable[[TradingAlert], Any],
    ) -> None:
        """移除告警回调函数。

        Args:
            callback: 要移除的回调。
        """
        try:
            self._alert_callbacks.remove(callback)
            logger.debug("告警回调已移除")
        except ValueError:
            pass

    async def _send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """发送交易告警通知。

        Args:
            level:   告警级别。
            title:   告警标题。
            message: 告警内容。
            data:    附加数据。
        """
        alert = TradingAlert(
            level=level,
            title=title,
            message=message,
            data=data or {},
        )

        # 通过日志记录
        log_fn = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.critical,
        }.get(level, logger.info)

        log_fn(f"[交易告警] {title}: {message}")

        # 通过事件总线发布
        await self._event_bus.publish("trading_alert", {
            "level": level.value,
            "title": title,
            "message": message,
            "data": data or {},
            "timestamp": alert.timestamp.isoformat(),
        })

        # 调用回调
        for callback in self._alert_callbacks:
            try:
                result = callback(alert)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"告警回调执行失败: {e}")

    # ------------------------------------------------------------------
    # 风控检查
    # ------------------------------------------------------------------

    async def _risk_check(self, decision: Decision) -> bool:
        """风控检查。

        Args:
            decision: AI 决策对象。

        Returns:
            是否通过风控检查。
        """
        # 置信度过低拒绝
        if decision.confidence < 0.3:
            logger.warning(
                f"置信度过低 ({decision.confidence:.2f} < 0.3)，拒绝执行"
            )
            return False

        # 检查标的是否在允许列表中
        allowed_symbols = self._engine_config.get("allowed_symbols", [])
        if allowed_symbols and decision.symbol not in allowed_symbols:
            logger.warning(f"标的 {decision.symbol} 不在允许交易列表中")
            return False

        # 检查单笔仓位上限
        if decision.price and decision.quantity:
            position_value = decision.price * decision.quantity
            if position_value > self._max_position_size:
                logger.warning(
                    f"单笔仓位超限: {position_value:.2f} > {self._max_position_size:.2f}"
                )
                return False

        return True

    async def _check_daily_limit(self) -> None:
        """检查当日交易次数限制。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_trade_date != today:
            self._daily_trade_count = 0
            self._daily_trade_date = today

        if self._daily_trade_count >= self._max_daily_trades:
            raise RuntimeError(
                f"当日交易次数已达上限 ({self._daily_trade_count}/{self._max_daily_trades})"
            )

    def _increment_daily_trade_count(self) -> None:
        """递增当日交易计数。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_trade_date != today:
            self._daily_trade_count = 0
            self._daily_trade_date = today
        self._daily_trade_count += 1

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    async def _on_order_placed(self, data: Any) -> None:
        """订单已提交事件处理。"""
        logger.debug(f"事件: 订单已提交 - {data}")

    async def _on_order_cancelled(self, data: Any) -> None:
        """订单已撤销事件处理。"""
        logger.debug(f"事件: 订单已撤销 - {data}")

    async def _on_order_filled(self, data: Any) -> None:
        """订单已成交事件处理。"""
        logger.debug(f"事件: 订单已成交 - {data}")
        await self._send_alert(
            AlertLevel.INFO,
            "订单成交",
            f"订单 {data.get('order_id', '')} 已成交",
            data if isinstance(data, dict) else {},
        )

    # ------------------------------------------------------------------
    # 配置更新
    # ------------------------------------------------------------------

    def update_risk_config(
        self,
        max_position_size: Optional[float] = None,
        max_daily_trades: Optional[int] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> None:
        """更新风控参数。

        Args:
            max_position_size: 单笔最大仓位。
            max_daily_trades:  每日最大交易次数。
            stop_loss_pct:     止损百分比。
            take_profit_pct:   止盈百分比。
        """
        if max_position_size is not None:
            self._max_position_size = max_position_size
        if max_daily_trades is not None:
            self._max_daily_trades = max_daily_trades
        if stop_loss_pct is not None:
            self._stop_loss_pct = stop_loss_pct
        if take_profit_pct is not None:
            self._take_profit_pct = take_profit_pct

        logger.info(
            f"风控参数已更新: max_position={self._max_position_size}, "
            f"max_daily={self._max_daily_trades}, "
            f"stop_loss={self._stop_loss_pct}%, take_profit={self._take_profit_pct}%"
        )
