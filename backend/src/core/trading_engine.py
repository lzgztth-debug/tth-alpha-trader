"""交易引擎模块

提供订单管理、持仓管理、风险管理和统一交易接口。
支持模拟/实盘交易模式切换。
"""

import sys
from pathlib import Path
_backend_root = str(Path(__file__).resolve().parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from src.models.account import Account, AccountType
from src.models.decision import Decision, DecisionAction
from src.models.order import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
)
from src.models.position import Position


# ===========================================================================
# OrderManager - 订单管理
# ===========================================================================


class OrderError(Exception):
    """订单操作异常基类"""
    pass


class OrderRejectedError(OrderError):
    """订单被拒绝"""
    pass


class OrderCancelError(OrderError):
    """订单取消失败"""
    pass


class OrderManager:
    """订单管理器

    负责订单的创建、状态跟踪、执行和取消。
    维护内存中的订单簿，提供订单生命周期管理。
    """

    def __init__(self) -> None:
        # {order_id: Order}
        self._orders: Dict[str, Order] = {}
        # {account_id: [order_id, ...]}
        self._account_orders: Dict[str, List[str]] = defaultdict(list)
        # {symbol: [order_id, ...]}
        self._symbol_orders: Dict[str, List[str]] = defaultdict(list)
        # 订单状态变更回调
        self._status_callbacks: List[Callable[[Order, OrderStatus], None]] = []

    # ------------------------------------------------------------------
    # 订单创建
    # ------------------------------------------------------------------

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        account_id: Optional[str] = None,
        broker: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> Order:
        """创建新订单。

        Args:
            symbol:     标的代码。
            side:       买卖方向。
            order_type: 订单类型。
            quantity:   委托数量。
            price:      委托价格 (限价单必填)。
            account_id: 所属账户ID。
            broker:     券商名称。
            order_id:   自定义订单ID。

        Returns:
            创建的 Order 实例。

        Raises:
            OrderRejectedError: 订单参数不合法。
        """
        # 参数校验
        if not symbol or not symbol.strip():
            raise OrderRejectedError("标的代码不能为空")

        if quantity <= 0:
            raise OrderRejectedError(f"委托数量必须大于0: {quantity}")

        if order_type == OrderType.LIMIT and (price is None or price <= 0):
            raise OrderRejectedError("限价单必须指定有效的委托价格")

        oid = order_id or str(uuid.uuid4())
        now = datetime.now()

        order = Order(
            order_id=oid,
            symbol=symbol.upper().strip(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            filled_quantity=0.0,
            filled_price=0.0,
            fee=0.0,
            created_at=now,
            account_id=account_id,
            broker=broker,
        )

        self._orders[oid] = order
        if account_id:
            self._account_orders[account_id].append(oid)
        self._symbol_orders[symbol.upper().strip()].append(oid)

        price_str = "MARKET" if order_type == OrderType.MARKET else str(price)
        logger.info(
            "订单已创建: id={}, {} {} {}x{}",
            oid,
            side.value,
            symbol,
            quantity,
            price_str,
        )

        return order

    def create_order_from_decision(
        self,
        decision: Decision,
        account_id: Optional[str] = None,
        broker: Optional[str] = None,
    ) -> Order:
        """从AI决策创建订单。

        Args:
            decision:   AI决策结果。
            account_id: 账户ID。
            broker:     券商名称。

        Returns:
            创建的 Order 实例。

        Raises:
            OrderRejectedError: 决策为HOLD或参数不合法。
        """
        if decision.action == DecisionAction.HOLD:
            raise OrderRejectedError("决策为HOLD，不创建订单")

        side_map = {
            DecisionAction.BUY: OrderSide.BUY,
            DecisionAction.SELL: OrderSide.SELL,
        }
        side = side_map.get(decision.action)
        if side is None:
            raise OrderRejectedError(f"无法映射决策动作到订单方向: {decision.action}")

        symbol = decision.symbol
        if not symbol:
            raise OrderRejectedError("决策中缺少标的代码")

        return self.create_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT if decision.price else OrderType.MARKET,
            quantity=decision.quantity or 0,
            price=decision.price,
            account_id=account_id,
            broker=broker,
        )

    # ------------------------------------------------------------------
    # 订单查询
    # ------------------------------------------------------------------

    def get_order(self, order_id: str) -> Optional[Order]:
        """根据订单ID查询订单。"""
        return self._orders.get(order_id)

    def get_orders_by_account(
        self,
        account_id: str,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """查询指定账户的订单列表。

        Args:
            account_id: 账户ID。
            status:     按状态筛选。

        Returns:
            订单列表。
        """
        order_ids = self._account_orders.get(account_id, [])
        orders = [self._orders[oid] for oid in order_ids if oid in self._orders]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    def get_orders_by_symbol(
        self,
        symbol: str,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """查询指定标的的订单列表。

        Args:
            symbol: 标的代码。
            status: 按状态筛选。

        Returns:
            订单列表。
        """
        order_ids = self._symbol_orders.get(symbol.upper().strip(), [])
        orders = [self._orders[oid] for oid in order_ids if oid in self._orders]
        if status is not None:
            orders = [o for o in orders if o.status == status]
        return orders

    def get_pending_orders(self, account_id: Optional[str] = None) -> List[Order]:
        """查询所有待处理订单。

        Args:
            account_id: 账户ID筛选。

        Returns:
            待处理订单列表。
        """
        if account_id:
            return self.get_orders_by_account(account_id, OrderStatus.PENDING)
        return [o for o in self._orders.values() if o.status == OrderStatus.PENDING]

    def get_all_orders(self) -> List[Order]:
        """获取所有订单。"""
        return list(self._orders.values())

    # ------------------------------------------------------------------
    # 订单状态更新
    # ------------------------------------------------------------------

    def update_order_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        filled_quantity: Optional[float] = None,
        filled_price: Optional[float] = None,
        fee: Optional[float] = None,
    ) -> Optional[Order]:
        """更新订单状态。

        Args:
            order_id:       订单ID。
            new_status:     新状态。
            filled_quantity: 已成交数量。
            filled_price:   成交均价。
            fee:            手续费。

        Returns:
            更新后的订单，不存在则返回None。

        Raises:
            OrderError: 状态转换不合法。
        """
        order = self._orders.get(order_id)
        if order is None:
            logger.warning("订单不存在: {}", order_id)
            return None

        old_status = order.status

        # 状态转换校验
        if not self._is_valid_transition(old_status, new_status):
            raise OrderError(
                f"非法的订单状态转换: {old_status.value} -> {new_status.value}"
            )

        order.status = new_status

        if filled_quantity is not None:
            order.filled_quantity = filled_quantity
        if filled_price is not None:
            order.filled_price = filled_price
        if fee is not None:
            order.fee = fee

        if new_status in (OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED):
            order.filled_at = datetime.now()

        # 触发回调
        for callback in self._status_callbacks:
            try:
                callback(order, old_status)
            except Exception as e:
                logger.error("订单状态回调异常: {}", e)

        logger.info(
            "订单状态已更新: id={} {} -> {}, filled={}/{}",
            order_id,
            old_status.value,
            new_status.value,
            order.filled_quantity,
            order.quantity,
        )

        return order

    def fill_order(
        self,
        order_id: str,
        filled_quantity: float,
        filled_price: float,
        fee: float = 0.0,
    ) -> Optional[Order]:
        """成交订单 (全部或部分成交)。

        Args:
            order_id:       订单ID。
            filled_quantity: 本次成交数量。
            filled_price:   成交价格。
            fee:            本次手续费。

        Returns:
            更新后的订单。
        """
        order = self._orders.get(order_id)
        if order is None:
            return None

        total_filled = order.filled_quantity + filled_quantity
        total_fee = order.fee + fee

        # 计算成交均价 (加权平均)
        if total_filled > 0:
            avg_price = (
                (order.filled_price * order.filled_quantity + filled_price * filled_quantity)
                / total_filled
            )
        else:
            avg_price = filled_price

        if total_filled >= order.quantity:
            # 全部成交
            return self.update_order_status(
                order_id,
                OrderStatus.FILLED,
                filled_quantity=order.quantity,
                filled_price=round(avg_price, 4),
                fee=round(total_fee, 4),
            )
        else:
            # 部分成交
            return self.update_order_status(
                order_id,
                OrderStatus.PARTIAL_FILLED,
                filled_quantity=round(total_filled, 4),
                filled_price=round(avg_price, 4),
                fee=round(total_fee, 4),
            )

    # ------------------------------------------------------------------
    # 订单取消
    # ------------------------------------------------------------------

    def cancel_order(self, order_id: str) -> Optional[Order]:
        """取消订单。

        Args:
            order_id: 订单ID。

        Returns:
            取消后的订单。

        Raises:
            OrderCancelError: 订单无法取消。
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderCancelError(f"订单不存在: {order_id}")

        if order.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED):
            raise OrderCancelError(
                f"订单状态 {order.status.value} 不允许取消"
            )

        return self.update_order_status(order_id, OrderStatus.CANCELLED)

    def cancel_all_pending(self, account_id: Optional[str] = None) -> int:
        """取消所有待处理订单。

        Args:
            account_id: 账户ID筛选。

        Returns:
            取消的订单数量。
        """
        pending = self.get_pending_orders(account_id)
        count = 0
        for order in pending:
            try:
                self.cancel_order(order.order_id)
                count += 1
            except OrderCancelError as e:
                logger.warning("取消订单失败: {} -> {}", order.order_id, e)
        logger.info("批量取消待处理订单: 取消数量={}", count)
        return count

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on_status_change(
        self, callback: Callable[[Order, OrderStatus], None]
    ) -> None:
        """注册订单状态变更回调。"""
        self._status_callbacks.append(callback)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_statistics(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """获取订单统计信息。

        Args:
            account_id: 账户ID筛选。

        Returns:
            统计字典。
        """
        if account_id:
            orders = self.get_orders_by_account(account_id)
        else:
            orders = list(self._orders.values())

        status_counts: Dict[str, int] = defaultdict(int)
        side_counts: Dict[str, int] = defaultdict(int)
        total_filled_value = 0.0
        total_fee = 0.0

        for order in orders:
            status_counts[order.status.value] += 1
            side_counts[order.side.value] += 1
            total_filled_value += order.filled_quantity * order.filled_price
            total_fee += order.fee

        return {
            "total_orders": len(orders),
            "status_distribution": dict(status_counts),
            "side_distribution": dict(side_counts),
            "total_filled_value": round(total_filled_value, 2),
            "total_fee": round(total_fee, 2),
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_transition(
        old_status: OrderStatus, new_status: OrderStatus
    ) -> bool:
        """校验订单状态转换是否合法。"""
        valid_transitions: Dict[OrderStatus, set] = {
            OrderStatus.PENDING: {
                OrderStatus.FILLED,
                OrderStatus.PARTIAL_FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            },
            OrderStatus.PARTIAL_FILLED: {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
            },
            OrderStatus.FILLED: set(),
            OrderStatus.CANCELLED: set(),
            OrderStatus.REJECTED: set(),
        }
        return new_status in valid_transitions.get(old_status, set())


# ===========================================================================
# PositionManager - 持仓管理
# ===========================================================================


class PositionError(Exception):
    """持仓操作异常基类"""
    pass


class InsufficientPositionError(PositionError):
    """持仓不足"""
    pass


class PositionManager:
    """持仓管理器

    负责持仓的创建、更新和盈亏计算。
    维护内存中的持仓簿。
    """

    def __init__(self) -> None:
        # {(account_id, symbol): Position}
        self._positions: Dict[Tuple[str, str], Position] = {}
        # 价格更新回调
        self._price_callbacks: List[Callable[[Position, float], None]] = []

    # ------------------------------------------------------------------
    # 持仓查询
    # ------------------------------------------------------------------

    def get_position(
        self, account_id: str, symbol: str
    ) -> Optional[Position]:
        """查询指定账户的指定标的持仓。"""
        return self._positions.get((account_id, symbol.upper().strip()))

    def get_positions(self, account_id: str) -> List[Position]:
        """查询指定账户的所有持仓。

        Args:
            account_id: 账户ID。

        Returns:
            持仓列表。
        """
        return [
            p
            for (aid, _), p in self._positions.items()
            if aid == account_id and p.quantity > 0
        ]

    def get_all_positions(self) -> List[Position]:
        """获取所有非零持仓。"""
        return [p for p in self._positions.values() if p.quantity > 0]

    def has_position(self, account_id: str, symbol: str) -> bool:
        """检查是否有持仓。"""
        pos = self._positions.get((account_id, symbol.upper().strip()))
        return pos is not None and pos.quantity > 0

    # ------------------------------------------------------------------
    # 持仓更新
    # ------------------------------------------------------------------

    def update_position_on_buy(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        price: float,
    ) -> Position:
        """买入后更新持仓。

        如果已有持仓则合并计算新的平均成本，否则创建新持仓。

        Args:
            account_id: 账户ID。
            symbol:     标的代码。
            quantity:   买入数量。
            price:      买入价格。

        Returns:
            更新后的 Position 实例。
        """
        key = (account_id, symbol.upper().strip())
        existing = self._positions.get(key)

        now = datetime.now()

        if existing and existing.quantity > 0:
            # 合并持仓，计算新的平均成本
            new_quantity = existing.quantity + quantity
            new_avg_cost = (
                (existing.avg_cost * existing.quantity + price * quantity)
                / new_quantity
            )
            market_value = new_quantity * existing.current_price
            unrealized_pnl = (existing.current_price - new_avg_cost) * new_quantity
            unrealized_pnl_pct = (
                (existing.current_price - new_avg_cost) / new_avg_cost
                if new_avg_cost > 0
                else 0.0
            )

            existing.quantity = round(new_quantity, 4)
            existing.avg_cost = round(new_avg_cost, 4)
            existing.market_value = round(market_value, 2)
            existing.unrealized_pnl = round(unrealized_pnl, 2)
            existing.unrealized_pnl_pct = round(unrealized_pnl_pct, 6)
            existing.updated_at = now

            logger.info(
                "持仓已更新(买入): account={}, symbol={}, qty={} -> {}, avg_cost={:.2f}",
                account_id,
                symbol,
                existing.quantity - quantity,
                existing.quantity,
                new_avg_cost,
            )
            return existing
        else:
            # 创建新持仓
            position = Position(
                symbol=symbol.upper().strip(),
                quantity=quantity,
                avg_cost=price,
                current_price=price,
                market_value=quantity * price,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                account_id=account_id,
                created_at=now,
                updated_at=now,
            )
            self._positions[key] = position

            logger.info(
                "新持仓已创建: account={}, symbol={}, qty={}, cost={:.2f}",
                account_id,
                symbol,
                quantity,
                price,
            )
            return position

    def update_position_on_sell(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        price: float,
    ) -> Position:
        """卖出后更新持仓。

        Args:
            account_id: 账户ID。
            symbol:     标的代码。
            quantity:   卖出数量。
            price:      卖出价格。

        Returns:
            更新后的 Position 实例。

        Raises:
            InsufficientPositionError: 持仓不足。
        """
        key = (account_id, symbol.upper().strip())
        existing = self._positions.get(key)

        if existing is None or existing.quantity < quantity:
            available = existing.quantity if existing else 0
            raise InsufficientPositionError(
                f"持仓不足: account={account_id}, symbol={symbol}, "
                f"需要={quantity}, 可用={available}"
            )

        now = datetime.now()
        new_quantity = existing.quantity - quantity

        if new_quantity < 1e-8:
            # 清仓
            realized_pnl = (price - existing.avg_cost) * quantity
            existing.quantity = 0.0
            existing.market_value = 0.0
            existing.unrealized_pnl = 0.0
            existing.unrealized_pnl_pct = 0.0
            existing.updated_at = now

            logger.info(
                "持仓已清仓: account={}, symbol={}, pnl={:.2f}",
                account_id,
                symbol,
                realized_pnl,
            )
        else:
            existing.quantity = round(new_quantity, 4)
            existing.market_value = round(new_quantity * existing.current_price, 2)
            existing.unrealized_pnl = round(
                (existing.current_price - existing.avg_cost) * new_quantity, 2
            )
            existing.unrealized_pnl_pct = round(
                (existing.current_price - existing.avg_cost) / existing.avg_cost
                if existing.avg_cost > 0
                else 0.0,
                6,
            )
            existing.updated_at = now

            logger.info(
                "持仓已更新(卖出): account={}, symbol={}, qty={} -> {}",
                account_id,
                symbol,
                existing.quantity + quantity,
                existing.quantity,
            )

        return existing

    def update_market_price(
        self,
        account_id: str,
        symbol: str,
        current_price: float,
    ) -> Optional[Position]:
        """更新持仓的当前市场价格。

        Args:
            account_id:    账户ID。
            symbol:        标的代码。
            current_price: 当前价格。

        Returns:
            更新后的 Position，不存在则返回None。
        """
        key = (account_id, symbol.upper().strip())
        position = self._positions.get(key)
        if position is None or position.quantity <= 0:
            return None

        old_price = position.current_price
        position.current_price = current_price
        position.market_value = round(position.quantity * current_price, 2)
        position.unrealized_pnl = round(
            (current_price - position.avg_cost) * position.quantity, 2
        )
        position.unrealized_pnl_pct = round(
            (current_price - position.avg_cost) / position.avg_cost
            if position.avg_cost > 0
            else 0.0,
            6,
        )
        position.updated_at = datetime.now()

        # 触发回调
        for callback in self._price_callbacks:
            try:
                callback(position, old_price)
            except Exception as e:
                logger.error("价格更新回调异常: {}", e)

        return position

    def update_all_prices(
        self,
        prices: Dict[str, float],
        account_id: Optional[str] = None,
    ) -> int:
        """批量更新市场价格。

        Args:
            prices:     {symbol: price} 字典。
            account_id: 账户ID筛选。

        Returns:
            更新的持仓数量。
        """
        count = 0
        for (aid, symbol), position in self._positions.items():
            if account_id and aid != account_id:
                continue
            if position.quantity <= 0:
                continue
            if symbol in prices:
                self.update_market_price(aid, symbol, prices[symbol])
                count += 1
        return count

    # ------------------------------------------------------------------
    # 盈亏计算
    # ------------------------------------------------------------------

    def calculate_total_pnl(self, account_id: str) -> Dict[str, float]:
        """计算指定账户的总盈亏。

        Args:
            account_id: 账户ID。

        Returns:
            {"unrealized_pnl": float, "unrealized_pnl_pct": float, "market_value": float}
        """
        positions = self.get_positions(account_id)
        total_unrealized = 0.0
        total_cost = 0.0
        total_market_value = 0.0

        for pos in positions:
            total_unrealized += pos.unrealized_pnl
            total_cost += pos.avg_cost * pos.quantity
            total_market_value += pos.market_value

        total_pct = (
            (total_unrealized / total_cost * 100) if total_cost > 0 else 0.0
        )

        return {
            "unrealized_pnl": round(total_unrealized, 2),
            "unrealized_pnl_pct": round(total_pct, 4),
            "market_value": round(total_market_value, 2),
            "total_cost": round(total_cost, 2),
        }

    def get_position_summary(self, account_id: str) -> List[Dict[str, Any]]:
        """获取持仓摘要列表。

        Args:
            account_id: 账户ID。

        Returns:
            持仓摘要列表。
        """
        positions = self.get_positions(account_id)
        summary = []
        for pos in positions:
            summary.append(
                {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "current_price": pos.current_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                }
            )
        return summary

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on_price_update(
        self, callback: Callable[[Position, float], None]
    ) -> None:
        """注册价格更新回调。"""
        self._price_callbacks.append(callback)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def clear(self, account_id: Optional[str] = None) -> None:
        """清除持仓数据。

        Args:
            account_id: 指定账户，None则清除全部。
        """
        if account_id:
            keys_to_remove = [
                k for k in self._positions if k[0] == account_id
            ]
            for key in keys_to_remove:
                del self._positions[key]
        else:
            self._positions.clear()
        logger.info("持仓数据已清除: account={}", account_id or "全部")


# ===========================================================================
# RiskManager - 风险管理
# ===========================================================================


class RiskError(Exception):
    """风控异常基类"""
    pass


class RiskLimitExceededError(RiskError):
    """超出风险限制"""
    pass


class RiskAlert:
    """风险告警"""

    def __init__(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.alert_type = alert_type
        self.message = message
        self.severity = severity
        self.details = details or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RiskConfig:
    """风控配置"""
    # 仓位限制
    max_position_pct: float = 20.0  # 单标的最大持仓占比(%)
    max_total_position_pct: float = 80.0  # 总持仓最大占比(%)
    # 单笔交易限制
    max_order_value: float = 100000.0  # 单笔最大金额
    max_order_quantity: float = 10000.0  # 单笔最大数量
    min_order_value: float = 100.0  # 单笔最小金额
    # 止损止盈
    stop_loss_pct: float = 2.0  # 止损百分比
    take_profit_pct: float = 5.0  # 止盈百分比
    # 日亏损限制
    max_daily_loss_pct: float = 3.0  # 日最大亏损百分比
    max_daily_loss_amount: float = 50000.0  # 日最大亏损金额
    # 交易频率
    max_daily_trades: int = 50  # 日最大交易次数
    # 连续亏损
    max_consecutive_losses: int = 5  # 最大连续亏损次数


class RiskManager:
    """风险管理器

    提供全面的风险控制检查，包括:
    - 仓位限制检查
    - 单笔交易限额
    - 止损止盈检查
    - 日亏损限制
    - 交易频率限制
    - 风险告警
    """

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        """
        初始化RiskManager。

        Args:
            config: 风控配置，None则使用默认配置。
        """
        self._config = config or RiskConfig()
        # 告警回调
        self._alert_callbacks: List[Callable[[RiskAlert], None]] = []
        # 告警历史
        self._alert_history: List[RiskAlert] = []
        # 日交易记录 {date_str: {account_id: {"count": int, "pnl": float, "consecutive_losses": int}}}
        self._daily_stats: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    "count": 0,
                    "pnl": 0.0,
                    "consecutive_losses": 0,
                    "orders": [],
                }
            )
        )

    @property
    def config(self) -> RiskConfig:
        return self._config

    def update_config(self, config: RiskConfig) -> None:
        """更新风控配置。"""
        self._config = config
        logger.info("风控配置已更新")

    # ------------------------------------------------------------------
    # 风控检查
    # ------------------------------------------------------------------

    def check_order(
        self,
        order: Order,
        account: Account,
        current_price: float,
        position_manager: PositionManager,
    ) -> List[RiskAlert]:
        """对订单进行全面风控检查。

        Args:
            order:             待检查的订单。
            account:           账户信息。
            current_price:     当前市场价格。
            position_manager:  持仓管理器。

        Returns:
            风险告警列表。空列表表示通过所有检查。

        Raises:
            RiskLimitExceededError: 触发硬性限制时抛出。
        """
        alerts: List[RiskAlert] = []

        # 1. 单笔交易限额检查
        order_value = order.quantity * (order.price or current_price)
        alerts.extend(self._check_order_value(order_value, order))

        # 2. 仓位限制检查
        alerts.extend(
            self._check_position_limit(
                order, account, current_price, position_manager
            )
        )

        # 3. 日亏损限制检查
        alerts.extend(self._check_daily_loss(order, account))

        # 4. 交易频率检查
        alerts.extend(self._check_trading_frequency(order, account))

        # 5. 止损止盈检查 (仅对卖出订单)
        if order.side == OrderSide.SELL:
            alerts.extend(
                self._check_stop_loss_take_profit(
                    order, current_price, position_manager
                )
            )

        # 记录告警
        for alert in alerts:
            self._record_alert(alert)

        # 硬性限制检查
        critical_alerts = [a for a in alerts if a.severity == "critical"]
        if critical_alerts:
            raise RiskLimitExceededError(
                f"订单未通过风控检查: "
                f"{'; '.join(a.message for a in critical_alerts)}"
            )

        return alerts

    def check_portfolio_risk(
        self,
        account: Account,
        position_manager: PositionManager,
    ) -> List[RiskAlert]:
        """检查组合风险。

        Args:
            account:          账户信息。
            position_manager: 持仓管理器。

        Returns:
            风险告警列表。
        """
        alerts: List[RiskAlert] = []
        positions = position_manager.get_positions(account.account_id)

        if not positions or account.total_value <= 0:
            return alerts

        # 检查总仓位占比
        total_market_value = sum(p.market_value for p in positions)
        position_pct = (total_market_value / account.total_value) * 100

        if position_pct > self._config.max_total_position_pct:
            alert = RiskAlert(
                alert_type="total_position_exceeded",
                message=(
                    f"总持仓占比 {position_pct:.1f}% 超过限制 "
                    f"{self._config.max_total_position_pct}%"
                ),
                severity="warning",
                details={
                    "current_pct": round(position_pct, 2),
                    "limit_pct": self._config.max_total_position_pct,
                },
            )
            alerts.append(alert)
            self._record_alert(alert)

        # 检查各持仓止损
        for pos in positions:
            if pos.avg_cost > 0:
                loss_pct = (
                    (pos.current_price - pos.avg_cost) / pos.avg_cost * 100
                )
                if loss_pct <= -self._config.stop_loss_pct:
                    alert = RiskAlert(
                        alert_type="stop_loss_triggered",
                        message=(
                            f"{pos.symbol} 触及止损: 亏损 {loss_pct:.2f}%, "
                            f"当前价={pos.current_price}, 成本={pos.avg_cost}"
                        ),
                        severity="critical",
                        details={
                            "symbol": pos.symbol,
                            "loss_pct": round(loss_pct, 2),
                            "current_price": pos.current_price,
                            "avg_cost": pos.avg_cost,
                        },
                    )
                    alerts.append(alert)
                    self._record_alert(alert)

        return alerts

    # ------------------------------------------------------------------
    # 交易记录
    # ------------------------------------------------------------------

    def record_trade(
        self,
        account_id: str,
        pnl: float = 0.0,
    ) -> None:
        """记录一笔交易，更新日统计。

        Args:
            account_id: 账户ID。
            pnl:        本笔交易盈亏。
        """
        today = date.today().isoformat()
        stats = self._daily_stats[today][account_id]
        stats["count"] += 1
        stats["pnl"] += pnl

        if pnl < 0:
            stats["consecutive_losses"] += 1
        else:
            stats["consecutive_losses"] = 0

        # 检查连续亏损
        if stats["consecutive_losses"] >= self._config.max_consecutive_losses:
            alert = RiskAlert(
                alert_type="consecutive_losses",
                message=(
                    f"连续亏损 {stats['consecutive_losses']} 次，"
                    f"达到限制 {self._config.max_consecutive_losses}"
                ),
                severity="critical",
                details={
                    "account_id": account_id,
                    "consecutive_losses": stats["consecutive_losses"],
                    "limit": self._config.max_consecutive_losses,
                },
            )
            self._record_alert(alert)

    def get_daily_stats(
        self, account_id: str, trade_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取日交易统计。

        Args:
            account_id:  账户ID。
            trade_date:  日期字符串，默认今天。

        Returns:
            日统计字典。
        """
        date_str = trade_date or date.today().isoformat()
        stats = self._daily_stats[date_str].get(account_id, {})
        return dict(stats)

    # ------------------------------------------------------------------
    # 告警管理
    # ------------------------------------------------------------------

    def get_alerts(
        self,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[RiskAlert]:
        """获取告警历史。

        Args:
            severity: 按严重程度筛选。
            limit:    返回数量上限。

        Returns:
            告警列表 (最新在前)。
        """
        alerts = self._alert_history
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return list(reversed(alerts[-limit:]))

    def on_alert(self, callback: Callable[[RiskAlert], None]) -> None:
        """注册告警回调。"""
        self._alert_callbacks.append(callback)

    # ------------------------------------------------------------------
    # 内部检查方法
    # ------------------------------------------------------------------

    def _check_order_value(
        self, order_value: float, order: Order
    ) -> List[RiskAlert]:
        """检查单笔交易金额限制。"""
        alerts: List[RiskAlert] = []

        if order_value > self._config.max_order_value:
            alert = RiskAlert(
                alert_type="order_value_exceeded",
                message=(
                    f"订单金额 {order_value:.2f} 超过单笔最大限制 "
                    f"{self._config.max_order_value:.2f}"
                ),
                severity="critical",
                details={
                    "order_id": order.order_id,
                    "order_value": order_value,
                    "limit": self._config.max_order_value,
                },
            )
            alerts.append(alert)

        if order_value < self._config.min_order_value and order_value > 0:
            alert = RiskAlert(
                alert_type="order_value_too_small",
                message=(
                    f"订单金额 {order_value:.2f} 低于最小限制 "
                    f"{self._config.min_order_value:.2f}"
                ),
                severity="warning",
                details={
                    "order_id": order.order_id,
                    "order_value": order_value,
                    "limit": self._config.min_order_value,
                },
            )
            alerts.append(alert)

        if order.quantity > self._config.max_order_quantity:
            alert = RiskAlert(
                alert_type="order_quantity_exceeded",
                message=(
                    f"订单数量 {order.quantity} 超过最大限制 "
                    f"{self._config.max_order_quantity}"
                ),
                severity="critical",
                details={
                    "order_id": order.order_id,
                    "quantity": order.quantity,
                    "limit": self._config.max_order_quantity,
                },
            )
            alerts.append(alert)

        return alerts

    def _check_position_limit(
        self,
        order: Order,
        account: Account,
        current_price: float,
        position_manager: PositionManager,
    ) -> List[RiskAlert]:
        """检查仓位限制。"""
        alerts: List[RiskAlert] = []

        if account.total_value <= 0:
            return alerts

        if order.side == OrderSide.BUY:
            order_value = order.quantity * (order.price or current_price)
            existing_pos = position_manager.get_position(
                account.account_id, order.symbol
            )
            existing_value = (
                existing_pos.market_value if existing_pos else 0.0
            )
            new_value = existing_value + order_value
            position_pct = (new_value / account.total_value) * 100

            if position_pct > self._config.max_position_pct:
                alert = RiskAlert(
                    alert_type="position_limit_exceeded",
                    message=(
                        f"{order.symbol} 买入后持仓占比 {position_pct:.1f}% "
                        f"超过限制 {self._config.max_position_pct}%"
                    ),
                    severity="critical",
                    details={
                        "symbol": order.symbol,
                        "current_pct": round(position_pct, 2),
                        "limit_pct": self._config.max_position_pct,
                    },
                )
                alerts.append(alert)

        return alerts

    def _check_daily_loss(
        self, order: Order, account: Account
    ) -> List[RiskAlert]:
        """检查日亏损限制。"""
        alerts: List[RiskAlert] = []
        today = date.today().isoformat()
        stats = self._daily_stats[today].get(account.account_id, {})
        daily_pnl = stats.get("pnl", 0.0)

        if account.total_value > 0:
            daily_loss_pct = (daily_pnl / account.total_value) * 100
            if daily_loss_pct < -self._config.max_daily_loss_pct:
                alert = RiskAlert(
                    alert_type="daily_loss_exceeded",
                    message=(
                        f"日亏损 {daily_loss_pct:.2f}% 超过限制 "
                        f"{self._config.max_daily_loss_pct}%"
                    ),
                    severity="critical",
                    details={
                        "daily_loss_pct": round(daily_loss_pct, 4),
                        "limit_pct": self._config.max_daily_loss_pct,
                    },
                )
                alerts.append(alert)

        if abs(daily_pnl) > self._config.max_daily_loss_amount:
            alert = RiskAlert(
                alert_type="daily_loss_amount_exceeded",
                message=(
                    f"日亏损金额 {abs(daily_pnl):.2f} 超过限制 "
                    f"{self._config.max_daily_loss_amount:.2f}"
                ),
                severity="critical",
                details={
                    "daily_loss": round(daily_pnl, 2),
                    "limit": self._config.max_daily_loss_amount,
                },
            )
            alerts.append(alert)

        return alerts

    def _check_trading_frequency(
        self, order: Order, account: Account
    ) -> List[RiskAlert]:
        """检查交易频率限制。"""
        alerts: List[RiskAlert] = []
        today = date.today().isoformat()
        stats = self._daily_stats[today].get(account.account_id, {})
        trade_count = stats.get("count", 0)

        if trade_count >= self._config.max_daily_trades:
            alert = RiskAlert(
                alert_type="trading_frequency_exceeded",
                message=(
                    f"今日交易次数 {trade_count} 已达上限 "
                    f"{self._config.max_daily_trades}"
                ),
                severity="critical",
                details={
                    "trade_count": trade_count,
                    "limit": self._config.max_daily_trades,
                },
            )
            alerts.append(alert)

        return alerts

    def _check_stop_loss_take_profit(
        self,
        order: Order,
        current_price: float,
        position_manager: PositionManager,
    ) -> List[RiskAlert]:
        """检查止损止盈。"""
        alerts: List[RiskAlert] = []

        if order.account_id is None:
            return alerts

        position = position_manager.get_position(
            order.account_id, order.symbol
        )
        if position is None or position.avg_cost <= 0:
            return alerts

        pnl_pct = (
            (current_price - position.avg_cost) / position.avg_cost * 100
        )

        if pnl_pct <= -self._config.stop_loss_pct:
            alert = RiskAlert(
                alert_type="stop_loss_triggered",
                message=(
                    f"{order.symbol} 触及止损线: 亏损 {pnl_pct:.2f}%, "
                    f"止损线 {self._config.stop_loss_pct}%"
                ),
                severity="critical",
                details={
                    "symbol": order.symbol,
                    "pnl_pct": round(pnl_pct, 2),
                    "stop_loss_pct": self._config.stop_loss_pct,
                },
            )
            alerts.append(alert)

        if pnl_pct >= self._config.take_profit_pct:
            alert = RiskAlert(
                alert_type="take_profit_triggered",
                message=(
                    f"{order.symbol} 触及止盈线: 盈利 {pnl_pct:.2f}%, "
                    f"止盈线 {self._config.take_profit_pct}%"
                ),
                severity="warning",
                details={
                    "symbol": order.symbol,
                    "pnl_pct": round(pnl_pct, 2),
                    "take_profit_pct": self._config.take_profit_pct,
                },
            )
            alerts.append(alert)

        return alerts

    def _record_alert(self, alert: RiskAlert) -> None:
        """记录告警并触发回调。"""
        self._alert_history.append(alert)
        if len(self._alert_history) > 5000:
            self._alert_history = self._alert_history[-5000:]

        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error("风控告警回调异常: {}", e)

        logger.warning(
            "风控告警: type={}, severity={}, message={}",
            alert.alert_type,
            alert.severity,
            alert.message,
        )


# ===========================================================================
# TradingEngine - 交易引擎主类
# ===========================================================================


class TradingEngine:
    """交易引擎

    整合订单管理、持仓管理和风险管理，提供统一的交易接口。
    支持模拟/实盘交易模式切换。
    """

    def __init__(
        self,
        order_manager: Optional[OrderManager] = None,
        position_manager: Optional[PositionManager] = None,
        risk_manager: Optional[RiskManager] = None,
        mode: str = "paper",
    ) -> None:
        """
        初始化TradingEngine。

        Args:
            order_manager:    订单管理器，None则自动创建。
            position_manager: 持仓管理器，None则自动创建。
            risk_manager:     风险管理器，None则自动创建。
            mode:             交易模式: "paper" / "live"。
        """
        self._order_manager = order_manager or OrderManager()
        self._position_manager = position_manager or PositionManager()
        self._risk_manager = risk_manager or RiskManager()
        self._mode = mode
        # 账户信息缓存 {account_id: Account}
        self._accounts: Dict[str, Account] = {}
        # 市场价格缓存 {symbol: price}
        self._market_prices: Dict[str, float] = {}
        # 交易回调
        self._trade_callbacks: List[Callable] = []

        logger.info("交易引擎初始化完成: mode={}", mode)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("paper", "live"):
            raise ValueError(f"无效的交易模式: {value}")
        old_mode = self._mode
        self._mode = value
        logger.info("交易模式已切换: {} -> {}", old_mode, value)

    # ------------------------------------------------------------------
    # 账户管理
    # ------------------------------------------------------------------

    def register_account(self, account: Account) -> None:
        """注册账户到交易引擎。

        Args:
            account: Account 实例。
        """
        self._accounts[account.account_id] = account
        logger.info("账户已注册: id={}, type={}", account.account_id, account.account_type)

    def unregister_account(self, account_id: str) -> None:
        """注销账户。"""
        if account_id in self._accounts:
            del self._accounts[account_id]
            logger.info("账户已注销: id={}", account_id)

    def get_account(self, account_id: str) -> Optional[Account]:
        """获取账户信息。"""
        return self._accounts.get(account_id)

    def update_account(self, account: Account) -> None:
        """更新账户信息。"""
        self._accounts[account.account_id] = account

    # ------------------------------------------------------------------
    # 市场价格
    # ------------------------------------------------------------------

    def update_market_price(self, symbol: str, price: float) -> None:
        """更新市场价格。

        Args:
            symbol: 标的代码。
            price:  最新价格。
        """
        self._market_prices[symbol.upper().strip()] = price
        # 更新所有相关持仓的价格
        for account_id in self._accounts:
            self._position_manager.update_market_price(
                account_id, symbol, price
            )

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """批量更新市场价格。

        Args:
            prices: {symbol: price} 字典。
        """
        for symbol, price in prices.items():
            self._market_prices[symbol.upper().strip()] = price
        self._position_manager.update_all_prices(prices)

    def get_market_price(self, symbol: str) -> float:
        """获取市场价格。"""
        return self._market_prices.get(symbol.upper().strip(), 0.0)

    # ------------------------------------------------------------------
    # 统一交易接口
    # ------------------------------------------------------------------

    def execute_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        account_id: Optional[str] = None,
    ) -> Order:
        """执行交易订单 (统一入口)。

        流程:
        1. 创建订单
        2. 风控检查
        3. 模拟/实盘执行
        4. 更新持仓
        5. 更新账户

        Args:
            symbol:     标的代码。
            side:       买卖方向。
            quantity:   数量。
            order_type: 订单类型。
            price:      价格。
            account_id: 账户ID。

        Returns:
            执行后的 Order 实例。

        Raises:
            OrderRejectedError: 订单被拒绝。
            RiskLimitExceededError: 风控限制。
        """
        # 获取账户
        if account_id and account_id not in self._accounts:
            raise OrderRejectedError(f"账户不存在: {account_id}")

        account = self._accounts.get(account_id) if account_id else None

        # 创建订单
        order = self._order_manager.create_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            account_id=account_id,
        )

        # 风控检查
        current_price = price or self.get_market_price(symbol)
        if account:
            try:
                alerts = self._risk_manager.check_order(
                    order=order,
                    account=account,
                    current_price=current_price,
                    position_manager=self._position_manager,
                )
                if alerts:
                    logger.warning(
                        "订单风控告警(已通过): id={}, alerts={}",
                        order.order_id,
                        [a.message for a in alerts],
                    )
            except RiskLimitExceededError as e:
                self._order_manager.update_order_status(
                    order.order_id, OrderStatus.REJECTED
                )
                logger.error("订单被风控拒绝: id={}, reason={}", order.order_id, e)
                raise

        # 执行订单
        executed_price = current_price if current_price > 0 else (price or 0.0)
        fee = self._calculate_fee(executed_price, quantity)

        if executed_price <= 0:
            self._order_manager.update_order_status(
                order.order_id, OrderStatus.REJECTED
            )
            raise OrderRejectedError(
                f"无法确定执行价格: symbol={symbol}, price={price}, "
                f"market_price={current_price}"
            )

        # 模拟成交
        filled_order = self._order_manager.fill_order(
            order.order_id,
            filled_quantity=quantity,
            filled_price=executed_price,
            fee=fee,
        )

        # 更新持仓
        if account_id:
            if side == OrderSide.BUY:
                self._position_manager.update_position_on_buy(
                    account_id, symbol, quantity, executed_price
                )
            elif side == OrderSide.SELL:
                try:
                    self._position_manager.update_position_on_sell(
                        account_id, symbol, quantity, executed_price
                    )
                except InsufficientPositionError as e:
                    self._order_manager.update_order_status(
                        order.order_id, OrderStatus.REJECTED
                    )
                    raise OrderRejectedError(str(e)) from e

            # 更新账户
            self._sync_account(account_id)

            # 记录风控统计
            pnl = 0.0
            if side == OrderSide.SELL and account:
                pos = self._position_manager.get_position(account_id, symbol)
                if pos and pos.avg_cost > 0:
                    pnl = (executed_price - pos.avg_cost) * quantity
            self._risk_manager.record_trade(account_id, pnl)

        # 触发交易回调
        for callback in self._trade_callbacks:
            try:
                callback(filled_order)
            except Exception as e:
                logger.error("交易回调异常: {}", e)

        logger.info(
            "订单执行完成: id={}, {} {} {}x{}, fee={:.2f}",
            filled_order.order_id,
            side.value,
            symbol,
            quantity,
            executed_price,
            fee,
        )

        return filled_order

    def execute_decision(
        self,
        decision: Decision,
        account_id: Optional[str] = None,
    ) -> Optional[Order]:
        """执行AI决策。

        Args:
            decision:   AI决策结果。
            account_id: 账户ID。

        Returns:
            执行的 Order，HOLD则返回None。
        """
        if decision.action == DecisionAction.HOLD:
            logger.info("决策为HOLD，跳过执行")
            return None

        side_map = {
            DecisionAction.BUY: OrderSide.BUY,
            DecisionAction.SELL: OrderSide.SELL,
        }
        side = side_map.get(decision.action)
        if side is None:
            logger.warning("无法映射决策动作: {}", decision.action)
            return None

        symbol = decision.symbol
        if not symbol:
            logger.warning("决策中缺少标的代码")
            return None

        try:
            return self.execute_order(
                symbol=symbol,
                side=side,
                quantity=decision.quantity or 0,
                order_type=OrderType.LIMIT if decision.price else OrderType.MARKET,
                price=decision.price,
                account_id=account_id,
            )
        except (OrderRejectedError, RiskLimitExceededError) as e:
            logger.error("执行AI决策失败: {}", e)
            return None

    def cancel_order(self, order_id: str) -> Optional[Order]:
        """取消订单。

        Args:
            order_id: 订单ID。

        Returns:
            取消后的订单。
        """
        return self._order_manager.cancel_order(order_id)

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def get_orders(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """查询订单。"""
        if account_id:
            orders = self._order_manager.get_orders_by_account(account_id, status)
        else:
            orders = self._order_manager.get_all_orders()

        if symbol:
            orders = [o for o in orders if o.symbol == symbol.upper().strip()]

        return orders

    def get_positions(self, account_id: str) -> List[Position]:
        """查询持仓。"""
        return self._position_manager.get_positions(account_id)

    def get_portfolio_summary(self, account_id: str) -> Dict[str, Any]:
        """获取投资组合摘要。

        Args:
            account_id: 账户ID。

        Returns:
            组合摘要字典。
        """
        account = self._accounts.get(account_id)
        positions = self._position_manager.get_positions(account_id)
        pnl_info = self._position_manager.calculate_total_pnl(account_id)
        order_stats = self._order_manager.get_statistics(account_id)

        return {
            "account": {
                "account_id": account_id,
                "cash": account.cash if account else 0.0,
                "total_value": account.total_value if account else 0.0,
                "market_value": account.market_value if account else 0.0,
            },
            "positions": self._position_manager.get_position_summary(account_id),
            "pnl": pnl_info,
            "order_statistics": order_stats,
            "risk_alerts": [
                a.to_dict()
                for a in self._risk_manager.get_alerts(limit=10)
            ],
        }

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on_trade(self, callback: Callable) -> None:
        """注册交易完成回调。"""
        self._trade_callbacks.append(callback)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _calculate_fee(self, price: float, quantity: float) -> float:
        """计算手续费。

        默认费率: 万分之三，最低5元。

        Args:
            price:    成交价格。
            quantity: 成交数量。

        Returns:
            手续费金额。
        """
        fee_rate = 0.0003
        fee = price * quantity * fee_rate
        return max(round(fee, 2), 5.0)

    def _sync_account(self, account_id: str) -> None:
        """同步账户数据 (现金、市值等)。

        Args:
            account_id: 账户ID。
        """
        account = self._accounts.get(account_id)
        if account is None:
            return

        positions = self._position_manager.get_positions(account_id)
        market_value = sum(p.market_value for p in positions)
        account.market_value = round(market_value, 2)
        account.total_value = round(account.cash + market_value, 2)
        account.available_cash = account.cash  # 简化处理
        account.updated_at = datetime.now()

        logger.debug(
            "账户已同步: id={}, cash={}, market_value={}, total={}",
            account_id,
            account.cash,
            market_value,
            account.total_value,
        )
