"""事件总线模块

提供发布-订阅模式的事件系统，支持异步事件处理、事件优先级和事件历史记录。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, Set

from loguru import logger


# ===========================================================================
# 事件类型定义
# ===========================================================================


class EventType(str, Enum):
    """事件类型枚举"""
    # 市场事件
    MARKET_PRICE_UPDATE = "market.price_update"
    MARKET_KLINE_UPDATE = "market.kline_update"
    MARKET_TICK = "market.tick"
    MARKET_OPEN = "market.open"
    MARKET_CLOSE = "market.close"

    # 订单事件
    ORDER_CREATED = "order.created"
    ORDER_FILLED = "order.filled"
    ORDER_PARTIAL_FILLED = "order.partial_filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_REJECTED = "order.rejected"
    ORDER_UPDATED = "order.updated"

    # 决策事件
    DECISION_MADE = "decision.made"
    DECISION_EXECUTED = "decision.executed"
    DECISION_FAILED = "decision.failed"

    # 告警事件
    ALERT_RISK = "alert.risk"
    ALERT_SYSTEM = "alert.system"
    ALERT_ERROR = "alert.error"

    # 账户事件
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_UPDATED = "account.updated"
    ACCOUNT_DELETED = "account.deleted"

    # 持仓事件
    POSITION_OPENED = "position.opened"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"

    # 系统事件
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"


# ===========================================================================
# 事件数据类
# ===========================================================================


@dataclass
class MarketEvent:
    """市场事件数据"""
    symbol: str
    price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    volume: float = 0.0
    change_pct: float = 0.0
    timestamp: Optional[datetime] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "volume": self.volume,
            "change_pct": self.change_pct,
            "timestamp": (self.timestamp or datetime.now()).isoformat(),
            "extra": self.extra,
        }


@dataclass
class OrderEvent:
    """订单事件数据"""
    order_id: str
    symbol: str
    side: str = ""
    order_type: str = ""
    quantity: float = 0.0
    price: Optional[float] = None
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    status: str = ""
    account_id: Optional[str] = None
    fee: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "filled_price": self.filled_price,
            "status": self.status,
            "account_id": self.account_id,
            "fee": self.fee,
            "extra": self.extra,
        }


@dataclass
class DecisionEvent:
    """决策事件数据"""
    decision_id: str
    action: str = ""
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    confidence: float = 0.0
    model: str = ""
    provider: str = ""
    reasoning: str = ""
    executed: bool = False
    execution_result: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action": self.action,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "confidence": self.confidence,
            "model": self.model,
            "provider": self.provider,
            "reasoning": self.reasoning,
            "executed": self.executed,
            "execution_result": self.execution_result,
            "extra": self.extra,
        }


@dataclass
class AlertEvent:
    """告警事件数据"""
    alert_type: str = ""
    alert_level: str = "info"  # info / warning / error / critical
    message: str = ""
    source: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type,
            "alert_level": self.alert_level,
            "message": self.message,
            "source": self.source,
            "details": self.details,
        }


# ===========================================================================
# Event - 通用事件封装
# ===========================================================================


@dataclass
class Event:
    """通用事件封装

    Attributes:
        event_id:    事件唯一标识。
        event_type:  事件类型。
        data:        事件数据 (可以是任意类型)。
        source:      事件来源。
        priority:    事件优先级 (数值越小优先级越高)。
        timestamp:   事件时间戳。
        metadata:    事件元数据。
    """
    event_id: str
    event_type: EventType
    data: Any = None
    source: str = ""
    priority: int = 5  # 1(最高) ~ 10(最低)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        result: Dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": (
                self.event_type.value
                if isinstance(self.event_type, EventType)
                else str(self.event_type)
            ),
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        if isinstance(self.data, (MarketEvent, OrderEvent, DecisionEvent, AlertEvent)):
            result["data"] = self.data.to_dict()
        elif isinstance(self.data, dict):
            result["data"] = self.data
        elif self.data is not None:
            result["data"] = str(self.data)
        return result


# ===========================================================================
# 事件处理器
# ===========================================================================


# 事件处理器类型: 同步或异步函数
SyncHandler = Callable[[Event], None]
AsyncHandler = Callable[[Event], Awaitable[None]]
EventHandler = Callable[[Event], Any]


@dataclass
class HandlerInfo:
    """处理器注册信息"""
    handler: EventHandler
    name: str
    priority: int = 5
    is_async: bool = False
    filter_event_types: Optional[Set[EventType]] = None
    enabled: bool = True


# ===========================================================================
# EventBus - 事件总线
# ===========================================================================


class EventBus:
    """事件总线

    提供发布-订阅模式的事件系统。特性:
    - 同步和异步事件处理
    - 事件优先级 (数值越小优先级越高)
    - 事件类型过滤
    - 事件历史记录
    - 处理器生命周期管理
    """

    def __init__(
        self,
        max_history_size: int = 10000,
        default_priority: int = 5,
    ) -> None:
        """
        初始化EventBus。

        Args:
            max_history_size: 事件历史最大记录数。
            default_priority:  默认处理器优先级。
        """
        # {event_type: [HandlerInfo, ...]}
        self._handlers: Dict[EventType, List[HandlerInfo]] = defaultdict(list)
        # 全局处理器 (监听所有事件)
        self._global_handlers: List[HandlerInfo] = []
        # 事件历史
        self._event_history: List[Event] = []
        self._max_history_size = max_history_size
        self._default_priority = default_priority
        # 统计
        self._stats: Dict[str, int] = defaultdict(int)
        # 是否运行中
        self._running: bool = False

        logger.info("事件总线初始化完成: max_history={}", max_history_size)

    # ------------------------------------------------------------------
    # 订阅 (注册处理器)
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
        name: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> str:
        """订阅事件。

        Args:
            event_type: 事件类型。
            handler:    事件处理函数 (同步或异步)。
            name:       处理器名称，用于标识和取消订阅。
            priority:   优先级，数值越小越先执行。

        Returns:
            处理器ID。
        """
        handler_name = name or getattr(handler, "__name__", str(id(handler)))
        handler_priority = priority if priority is not None else self._default_priority
        is_async = asyncio.iscoroutinefunction(handler)

        info = HandlerInfo(
            handler=handler,
            name=handler_name,
            priority=handler_priority,
            is_async=is_async,
        )

        self._handlers[event_type].append(info)
        # 按优先级排序 (数值小的在前)
        self._handlers[event_type].sort(key=lambda h: h.priority)

        logger.debug(
            "事件处理器已注册: type={}, handler={}, priority={}, async={}",
            event_type.value,
            handler_name,
            handler_priority,
            is_async,
        )

        return handler_name

    def subscribe_all(
        self,
        handler: EventHandler,
        name: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> str:
        """订阅所有事件 (全局处理器)。

        Args:
            handler:  事件处理函数。
            name:     处理器名称。
            priority: 优先级。

        Returns:
            处理器ID。
        """
        handler_name = name or getattr(handler, "__name__", str(id(handler)))
        handler_priority = priority if priority is not None else self._default_priority
        is_async = asyncio.iscoroutinefunction(handler)

        info = HandlerInfo(
            handler=handler,
            name=handler_name,
            priority=handler_priority,
            is_async=is_async,
        )

        self._global_handlers.append(info)
        self._global_handlers.sort(key=lambda h: h.priority)

        logger.debug(
            "全局事件处理器已注册: handler={}, priority={}, async={}",
            handler_name,
            handler_priority,
            is_async,
        )

        return handler_name

    def subscribe_many(
        self,
        event_types: List[EventType],
        handler: EventHandler,
        name: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> List[str]:
        """批量订阅多个事件类型。

        Args:
            event_types: 事件类型列表。
            handler:     事件处理函数。
            name:        处理器名称。
            priority:    优先级。

        Returns:
            处理器ID列表。
        """
        return [
            self.subscribe(et, handler, name, priority) for et in event_types
        ]

    # ------------------------------------------------------------------
    # 取消订阅
    # ------------------------------------------------------------------

    def unsubscribe(self, event_type: EventType, name: str) -> bool:
        """取消订阅指定事件类型的处理器。

        Args:
            event_type: 事件类型。
            name:       处理器名称。

        Returns:
            是否成功取消。
        """
        handlers = self._handlers.get(event_type, [])
        original_len = len(handlers)
        self._handlers[event_type] = [
            h for h in handlers if h.name != name
        ]
        removed = original_len - len(self._handlers[event_type])
        if removed > 0:
            logger.debug(
                "事件处理器已取消: type={}, handler={}", event_type.value, name
            )
        return removed > 0

    def unsubscribe_all(self, name: str) -> int:
        """取消订阅所有匹配名称的处理器。

        Args:
            name: 处理器名称。

        Returns:
            取消的处理器数量。
        """
        count = 0

        # 从类型处理器中移除
        for event_type in list(self._handlers.keys()):
            handlers = self._handlers[event_type]
            original_len = len(handlers)
            self._handlers[event_type] = [
                h for h in handlers if h.name != name
            ]
            count += original_len - len(self._handlers[event_type])

        # 从全局处理器中移除
        original_len = len(self._global_handlers)
        self._global_handlers = [
            h for h in self._global_handlers if h.name != name
        ]
        count += original_len - len(self._global_handlers)

        if count > 0:
            logger.debug("事件处理器已批量取消: handler={}, count={}", name, count)
        return count

    def unsubscribe_by_event_type(self, event_type: EventType) -> int:
        """取消订阅某个事件类型的所有处理器。

        Args:
            event_type: 事件类型。

        Returns:
            取消的处理器数量。
        """
        count = len(self._handlers.get(event_type, []))
        self._handlers[event_type] = []
        if count > 0:
            logger.debug(
                "事件类型所有处理器已取消: type={}, count={}",
                event_type.value,
                count,
            )
        return count

    # ------------------------------------------------------------------
    # 发布事件
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """同步发布事件。

        按优先级顺序依次调用所有匹配的处理器。
        如果处理器是异步函数，则发出警告但不等待。

        Args:
            event: Event 实例。
        """
        self._record_event(event)
        self._stats["published"] += 1
        self._stats[f"published:{event.event_type.value}"] += 1

        # 收集匹配的处理器
        handlers = self._get_matching_handlers(event.event_type)

        if not handlers:
            logger.debug(
                "事件无匹配处理器: type={}, id={}",
                event.event_type.value,
                event.event_id,
            )
            return

        # 按优先级排序
        handlers.sort(key=lambda h: h.priority)

        for info in handlers:
            if not info.enabled:
                continue

            try:
                if info.is_async:
                    logger.warning(
                        "同步发布遇到异步处理器 (将被跳过): handler={}, event={}",
                        info.name,
                        event.event_type.value,
                    )
                else:
                    info.handler(event)
                    self._stats["handled"] += 1
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(
                    "事件处理器执行异常: handler={}, event={}, error={}",
                    info.name,
                    event.event_type.value,
                    e,
                )

    async def publish_async(self, event: Event) -> None:
        """异步发布事件。

        按优先级顺序依次调用所有匹配的处理器。
        支持同步和异步处理器混合使用。

        Args:
            event: Event 实例。
        """
        self._record_event(event)
        self._stats["published"] += 1
        self._stats[f"published:{event.event_type.value}"] += 1

        handlers = self._get_matching_handlers(event.event_type)

        if not handlers:
            logger.debug(
                "事件无匹配处理器: type={}, id={}",
                event.event_type.value,
                event.event_id,
            )
            return

        handlers.sort(key=lambda h: h.priority)

        for info in handlers:
            if not info.enabled:
                continue

            try:
                if info.is_async:
                    await info.handler(event)
                else:
                    info.handler(event)
                self._stats["handled"] += 1
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(
                    "事件处理器执行异常: handler={}, event={}, error={}",
                    info.name,
                    event.event_type.value,
                    e,
                )

    async def publish_many(self, events: List[Event]) -> None:
        """批量异步发布多个事件。

        Args:
            events: Event 列表。
        """
        for event in events:
            await self.publish_async(event)

    # ------------------------------------------------------------------
    # 便捷发布方法
    # ------------------------------------------------------------------

    def emit_market_event(
        self,
        symbol: str,
        price: float,
        event_type: EventType = EventType.MARKET_PRICE_UPDATE,
        source: str = "market",
        **kwargs: Any,
    ) -> Event:
        """发布市场事件。

        Args:
            symbol:     标的代码。
            price:      价格。
            event_type: 事件类型。
            source:     事件来源。
            **kwargs:   额外的 MarketEvent 参数。

        Returns:
            发布的 Event 实例。
        """
        market_data = MarketEvent(
            symbol=symbol,
            price=price,
            **kwargs,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=market_data,
            source=source,
            priority=3,  # 市场事件优先级较高
        )
        self.publish(event)
        return event

    def emit_order_event(
        self,
        order_id: str,
        symbol: str,
        event_type: EventType = EventType.ORDER_CREATED,
        source: str = "trading",
        **kwargs: Any,
    ) -> Event:
        """发布订单事件。

        Args:
            order_id:   订单ID。
            symbol:     标的代码。
            event_type: 事件类型。
            source:     事件来源。
            **kwargs:   额外的 OrderEvent 参数。

        Returns:
            发布的 Event 实例。
        """
        order_data = OrderEvent(
            order_id=order_id,
            symbol=symbol,
            **kwargs,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=order_data,
            source=source,
            priority=2,
        )
        self.publish(event)
        return event

    def emit_decision_event(
        self,
        decision_id: str,
        action: str,
        event_type: EventType = EventType.DECISION_MADE,
        source: str = "agent",
        **kwargs: Any,
    ) -> Event:
        """发布决策事件。

        Args:
            decision_id: 决策ID。
            action:      决策动作。
            event_type:  事件类型。
            source:      事件来源。
            **kwargs:    额外的 DecisionEvent 参数。

        Returns:
            发布的 Event 实例。
        """
        decision_data = DecisionEvent(
            decision_id=decision_id,
            action=action,
            **kwargs,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            data=decision_data,
            source=source,
            priority=4,
        )
        self.publish(event)
        return event

    def emit_alert_event(
        self,
        alert_type: str,
        message: str,
        alert_level: str = "info",
        source: str = "system",
        **kwargs: Any,
    ) -> Event:
        """发布告警事件。

        Args:
            alert_type:  告警类型。
            message:     告警消息。
            alert_level: 告警级别。
            source:      事件来源。
            **kwargs:    额外的 AlertEvent 参数。

        Returns:
            发布的 Event 实例。
        """
        alert_data = AlertEvent(
            alert_type=alert_type,
            alert_level=alert_level,
            message=message,
            source=source,
            **kwargs,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ALERT_RISK if "risk" in alert_type.lower() else EventType.ALERT_SYSTEM,
            data=alert_data,
            source=source,
            priority=1,  # 告警事件最高优先级
        )
        self.publish(event)
        return event

    # ------------------------------------------------------------------
    # 事件历史
    # ------------------------------------------------------------------

    def get_event_history(
        self,
        event_type: Optional[EventType] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """查询事件历史。

        Args:
            event_type: 按事件类型筛选。
            source:     按来源筛选。
            limit:      返回数量上限。

        Returns:
            事件列表 (最新在前)。
        """
        history = self._event_history

        if event_type is not None:
            history = [e for e in history if e.event_type == event_type]
        if source is not None:
            history = [e for e in history if e.source == source]

        return list(reversed(history[-limit:]))

    def clear_history(self) -> None:
        """清除事件历史。"""
        self._event_history.clear()
        logger.info("事件历史已清除")

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, int]:
        """获取事件总线统计信息。

        Returns:
            统计字典。
        """
        return dict(self._stats)

    def get_handler_count(self, event_type: Optional[EventType] = None) -> int:
        """获取处理器数量。

        Args:
            event_type: 事件类型，None则返回总数。

        Returns:
            处理器数量。
        """
        if event_type is not None:
            return len(self._handlers.get(event_type, []))
        total = len(self._global_handlers)
        for handlers in self._handlers.values():
            total += len(handlers)
        return total

    def list_handlers(self) -> List[Dict[str, Any]]:
        """列出所有已注册的处理器。

        Returns:
            处理器信息列表。
        """
        result = []

        # 全局处理器
        for info in self._global_handlers:
            result.append(
                {
                    "event_type": "* (global)",
                    "name": info.name,
                    "priority": info.priority,
                    "is_async": info.is_async,
                    "enabled": info.enabled,
                }
            )

        # 类型处理器
        for event_type, handlers in self._handlers.items():
            for info in handlers:
                result.append(
                    {
                        "event_type": event_type.value,
                        "name": info.name,
                        "priority": info.priority,
                        "is_async": info.is_async,
                        "enabled": info.enabled,
                    }
                )

        return result

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动事件总线。"""
        self._running = True
        logger.info("事件总线已启动")

    def stop(self) -> None:
        """停止事件总线。"""
        self._running = False
        logger.info("事件总线已停止")

    @property
    def is_running(self) -> bool:
        """事件总线是否运行中。"""
        return self._running

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_matching_handlers(
        self, event_type: EventType
    ) -> List[HandlerInfo]:
        """获取匹配事件类型的所有处理器 (包括全局处理器)。"""
        handlers = list(self._global_handlers)
        handlers.extend(self._handlers.get(event_type, []))
        return handlers

    def _record_event(self, event: Event) -> None:
        """记录事件到历史。"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]


# ===========================================================================
# 全局事件总线单例
# ===========================================================================

_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线单例。

    Returns:
        EventBus 实例。
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
        _global_event_bus.start()
    return _global_event_bus


def reset_event_bus() -> None:
    """重置全局事件总线 (主要用于测试)。"""
    global _global_event_bus
    if _global_event_bus is not None:
        _global_event_bus.stop()
    _global_event_bus = None
