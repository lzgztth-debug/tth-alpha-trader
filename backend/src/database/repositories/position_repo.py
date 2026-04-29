"""持仓数据仓库

提供持仓的异步CRUD操作。
"""

from typing import List, Optional

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.schema import PositionORM
from src.models.position import Position, PositionCreate, PositionUpdate


class PositionRepository:
    """持仓数据仓库，封装持仓的异步CRUD操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 创建 / 更新 (Upsert)
    # ------------------------------------------------------------------

    async def create_position(self, data: PositionCreate) -> PositionORM:
        """创建新持仓记录。

        Args:
            data: 持仓创建参数。

        Returns:
            新创建的 PositionORM 实例。
        """
        market_value = data.quantity * data.current_price
        unrealized_pnl = (data.current_price - data.avg_cost) * data.quantity
        unrealized_pnl_pct = (
            (data.current_price - data.avg_cost) / data.avg_cost
            if data.avg_cost > 0
            else 0.0
        )

        orm = PositionORM(
            account_id=data.account_id,
            symbol=data.symbol,
            quantity=data.quantity,
            avg_cost=data.avg_cost,
            current_price=data.current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"持仓已创建: {data.account_id} {data.symbol} x{data.quantity}")
        return orm

    async def upsert_position(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        avg_cost: float,
        current_price: float,
    ) -> PositionORM:
        """创建或更新持仓 (Upsert)。

        如果该账户下该标的已有持仓，则合并数量并重新计算平均成本；
        否则创建新持仓记录。

        Args:
            account_id:    账户ID。
            symbol:        标的代码。
            quantity:      新增数量 (买入为正数)。
            avg_cost:      本次交易价格。
            current_price: 当前市场价格。

        Returns:
            更新后的 PositionORM 实例。
        """
        existing = await self.get_position(account_id, symbol)

        if existing is not None:
            # 合并持仓
            new_quantity = existing.quantity + quantity
            new_avg_cost = (
                (existing.avg_cost * existing.quantity + avg_cost * quantity)
                / new_quantity
                if new_quantity > 0
                else 0.0
            )
            market_value = new_quantity * current_price
            unrealized_pnl = (current_price - new_avg_cost) * new_quantity
            unrealized_pnl_pct = (
                (current_price - new_avg_cost) / new_avg_cost
                if new_avg_cost > 0
                else 0.0
            )

            stmt = (
                update(PositionORM)
                .where(
                    PositionORM.account_id == account_id,
                    PositionORM.symbol == symbol,
                )
                .values(
                    quantity=new_quantity,
                    avg_cost=new_avg_cost,
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                )
            )
            await self.session.execute(stmt)
            await self.session.flush()
            logger.info(f"持仓已更新: {account_id} {symbol} -> 数量={new_quantity}")
            return await self.get_position(account_id, symbol)
        else:
            data = PositionCreate(
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                avg_cost=avg_cost,
                current_price=current_price,
            )
            return await self.create_position(data)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_position(
        self,
        account_id: str,
        symbol: str,
    ) -> Optional[PositionORM]:
        """查询指定账户的指定标的持仓。"""
        stmt = select(PositionORM).where(
            PositionORM.account_id == account_id,
            PositionORM.symbol == symbol,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_positions_by_account(
        self,
        account_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PositionORM]:
        """查询指定账户的所有持仓。

        Args:
            account_id: 账户ID。
            skip:       跳过记录数。
            limit:      返回记录数上限。

        Returns:
            PositionORM 列表。
        """
        stmt = (
            select(PositionORM)
            .where(PositionORM.account_id == account_id)
            .offset(skip)
            .limit(limit)
            .order_by(PositionORM.symbol)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_positions(
        self,
        symbol: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PositionORM]:
        """查询所有持仓，支持按标的筛选。

        Args:
            symbol: 按标的代码筛选。
            skip:   跳过记录数。
            limit:  返回记录数上限。

        Returns:
            PositionORM 列表。
        """
        stmt = select(PositionORM)
        if symbol is not None:
            stmt = stmt.where(PositionORM.symbol == symbol)
        stmt = stmt.offset(skip).limit(limit).order_by(PositionORM.account_id, PositionORM.symbol)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_positions(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> int:
        """统计持仓数量。"""
        from sqlalchemy import func as sa_func

        stmt = select(sa_func.count()).select_from(PositionORM)
        if account_id is not None:
            stmt = stmt.where(PositionORM.account_id == account_id)
        if symbol is not None:
            stmt = stmt.where(PositionORM.symbol == symbol)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    async def update_position(
        self,
        account_id: str,
        symbol: str,
        data: PositionUpdate,
    ) -> Optional[PositionORM]:
        """更新持仓信息。

        Args:
            account_id: 账户ID。
            symbol:     标的代码。
            data:       更新字段。

        Returns:
            更新后的 PositionORM 实例，不存在时返回 None。
        """
        values = data.model_dump(exclude_unset=True)
        if not values:
            return await self.get_position(account_id, symbol)

        stmt = (
            update(PositionORM)
            .where(
                PositionORM.account_id == account_id,
                PositionORM.symbol == symbol,
            )
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        logger.info(f"持仓已更新: {account_id} {symbol}, 字段: {list(values.keys())}")
        return await self.get_position(account_id, symbol)

    async def update_position_price(
        self,
        account_id: str,
        symbol: str,
        current_price: float,
    ) -> Optional[PositionORM]:
        """更新持仓的当前价格及相关盈亏计算。

        Args:
            account_id:    账户ID。
            symbol:        标的代码。
            current_price: 新的当前价格。

        Returns:
            更新后的 PositionORM 实例，不存在时返回 None。
        """
        orm = await self.get_position(account_id, symbol)
        if orm is None:
            return None

        market_value = orm.quantity * current_price
        unrealized_pnl = (current_price - orm.avg_cost) * orm.quantity
        unrealized_pnl_pct = (
            (current_price - orm.avg_cost) / orm.avg_cost
            if orm.avg_cost > 0
            else 0.0
        )

        stmt = (
            update(PositionORM)
            .where(
                PositionORM.account_id == account_id,
                PositionORM.symbol == symbol,
            )
            .values(
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get_position(account_id, symbol)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    async def delete_position(
        self,
        account_id: str,
        symbol: str,
    ) -> bool:
        """删除持仓记录。

        Args:
            account_id: 账户ID。
            symbol:     标的代码。

        Returns:
            是否删除成功。
        """
        orm = await self.get_position(account_id, symbol)
        if orm is None:
            return False
        await self.session.delete(orm)
        await self.session.flush()
        logger.info(f"持仓已删除: {account_id} {symbol}")
        return True

    # ------------------------------------------------------------------
    # ORM -> dataclass 转换
    # ------------------------------------------------------------------

    @staticmethod
    def to_model(orm: PositionORM) -> Position:
        """将 PositionORM 转换为 Position dataclass。"""
        unrealized_pnl_pct = (
            (orm.current_price - orm.avg_cost) / orm.avg_cost
            if orm.avg_cost > 0
            else 0.0
        )
        return Position(
            symbol=orm.symbol,
            quantity=orm.quantity,
            avg_cost=orm.avg_cost,
            current_price=orm.current_price,
            market_value=orm.market_value,
            unrealized_pnl=orm.unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            account_id=orm.account_id,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
