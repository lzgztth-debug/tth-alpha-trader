"""订单数据仓库

提供订单的异步CRUD操作，支持分页和条件筛选。
"""

from datetime import datetime
from typing import List, Optional

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.schema import OrderORM
from src.models.order import (
    Order,
    OrderCreate,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
)


class OrderRepository:
    """订单数据仓库，封装订单的异步CRUD操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    async def create_order(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        account_id: Optional[str] = None,
        broker: Optional[str] = None,
    ) -> OrderORM:
        """创建新订单。

        Args:
            order_id:   订单唯一标识。
            symbol:     标的代码。
            side:       买卖方向。
            order_type: 订单类型。
            quantity:   委托数量。
            price:      委托价格。
            account_id: 所属账户ID。
            broker:     券商名称。

        Returns:
            新创建的 OrderORM 实例。
        """
        orm = OrderORM(
            order_id=order_id,
            symbol=symbol,
            side=side.value,
            order_type=order_type.value,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING.value,
            account_id=account_id or "",
            broker=broker or "",
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"订单已创建: {order_id} {side.value} {symbol} x{quantity}")
        return orm

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_order_by_id(self, order_id: str) -> Optional[OrderORM]:
        """根据 order_id 查询订单。"""
        stmt = select(OrderORM).where(OrderORM.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_orders(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[OrderSide] = None,
        status: Optional[OrderStatus] = None,
        order_type: Optional[OrderType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[OrderORM]:
        """查询订单列表，支持多条件筛选和分页。

        Args:
            account_id: 按账户ID筛选。
            symbol:     按标的代码筛选。
            side:       按买卖方向筛选。
            status:     按订单状态筛选。
            order_type: 按订单类型筛选。
            start_time: 起始时间。
            end_time:   结束时间。
            skip:       跳过记录数。
            limit:      返回记录数上限。

        Returns:
            OrderORM 列表。
        """
        stmt = select(OrderORM)
        if account_id is not None:
            stmt = stmt.where(OrderORM.account_id == account_id)
        if symbol is not None:
            stmt = stmt.where(OrderORM.symbol == symbol)
        if side is not None:
            stmt = stmt.where(OrderORM.side == side.value)
        if status is not None:
            stmt = stmt.where(OrderORM.status == status.value)
        if order_type is not None:
            stmt = stmt.where(OrderORM.order_type == order_type.value)
        if start_time is not None:
            stmt = stmt.where(OrderORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(OrderORM.created_at <= end_time)

        stmt = stmt.offset(skip).limit(limit).order_by(OrderORM.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_orders(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[OrderSide] = None,
        status: Optional[OrderStatus] = None,
        order_type: Optional[OrderType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """统计订单数量。"""
        stmt = select(func.count()).select_from(OrderORM)
        if account_id is not None:
            stmt = stmt.where(OrderORM.account_id == account_id)
        if symbol is not None:
            stmt = stmt.where(OrderORM.symbol == symbol)
        if side is not None:
            stmt = stmt.where(OrderORM.side == side.value)
        if status is not None:
            stmt = stmt.where(OrderORM.status == status.value)
        if order_type is not None:
            stmt = stmt.where(OrderORM.order_type == order_type.value)
        if start_time is not None:
            stmt = stmt.where(OrderORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(OrderORM.created_at <= end_time)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    async def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: Optional[float] = None,
        filled_price: Optional[float] = None,
        fee: Optional[float] = None,
        filled_at: Optional[datetime] = None,
    ) -> Optional[OrderORM]:
        """更新订单状态。

        Args:
            order_id:       订单唯一标识。
            status:         新的订单状态。
            filled_quantity: 已成交数量。
            filled_price:   成交均价。
            fee:            手续费。
            filled_at:      成交时间。

        Returns:
            更新后的 OrderORM 实例，不存在时返回 None。
        """
        values: dict = {"status": status.value}
        if filled_quantity is not None:
            values["filled_quantity"] = filled_quantity
        if filled_price is not None:
            values["filled_price"] = filled_price
        if fee is not None:
            values["fee"] = fee
        if filled_at is not None:
            values["filled_at"] = filled_at

        stmt = (
            update(OrderORM)
            .where(OrderORM.order_id == order_id)
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        logger.info(f"订单状态已更新: {order_id} -> {status.value}")
        return await self.get_order_by_id(order_id)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    async def delete_order(self, order_id: str) -> bool:
        """删除订单。

        Args:
            order_id: 订单唯一标识。

        Returns:
            是否删除成功。
        """
        orm = await self.get_order_by_id(order_id)
        if orm is None:
            return False
        await self.session.delete(orm)
        await self.session.flush()
        logger.info(f"订单已删除: {order_id}")
        return True

    # ------------------------------------------------------------------
    # ORM -> dataclass 转换
    # ------------------------------------------------------------------

    @staticmethod
    def to_model(orm: OrderORM) -> Order:
        """将 OrderORM 转换为 Order dataclass。"""
        return Order(
            order_id=orm.order_id,
            symbol=orm.symbol,
            side=OrderSide(orm.side),
            order_type=OrderType(orm.order_type),
            quantity=orm.quantity,
            price=orm.price,
            status=OrderStatus(orm.status),
            filled_quantity=orm.filled_quantity,
            filled_price=orm.filled_price,
            fee=orm.fee,
            created_at=orm.created_at,
            filled_at=orm.filled_at,
            account_id=orm.account_id,
            broker=orm.broker,
        )
