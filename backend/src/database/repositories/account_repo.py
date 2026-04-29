"""账户数据仓库

提供账户的异步CRUD操作。
"""

from typing import List, Optional

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.schema import AccountORM
from src.models.account import Account, AccountType, AccountCreate, AccountUpdate


class AccountRepository:
    """账户数据仓库，封装账户的异步CRUD操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    async def create_account(self, data: AccountCreate) -> AccountORM:
        """创建新账户。

        Args:
            data: 账户创建参数。

        Returns:
            新创建的 AccountORM 实例。
        """
        orm = AccountORM(
            account_id=data.account_id,
            broker=data.broker,
            account_type=data.account_type.value,
            total_value=data.initial_cash,
            cash=data.initial_cash,
            market_value=0.0,
            available_cash=data.initial_cash,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"账户已创建: {data.account_id}")
        return orm

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_account_by_id(self, account_id: str) -> Optional[AccountORM]:
        """根据 account_id 查询账户。

        Args:
            account_id: 账户唯一标识。

        Returns:
            AccountORM 实例，不存在时返回 None。
        """
        stmt = select(AccountORM).where(AccountORM.account_id == account_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_accounts(
        self,
        account_type: Optional[AccountType] = None,
        broker: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AccountORM]:
        """查询账户列表，支持筛选和分页。

        Args:
            account_type: 按账户类型筛选。
            broker:       按券商名称筛选。
            skip:         跳过记录数。
            limit:        返回记录数上限。

        Returns:
            AccountORM 列表。
        """
        stmt = select(AccountORM)
        if account_type is not None:
            stmt = stmt.where(AccountORM.account_type == account_type.value)
        if broker is not None:
            stmt = stmt.where(AccountORM.broker == broker)
        stmt = stmt.offset(skip).limit(limit).order_by(AccountORM.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_accounts(
        self,
        account_type: Optional[AccountType] = None,
        broker: Optional[str] = None,
    ) -> int:
        """统计账户数量。"""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(AccountORM)
        if account_type is not None:
            stmt = stmt.where(AccountORM.account_type == account_type.value)
        if broker is not None:
            stmt = stmt.where(AccountORM.broker == broker)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    async def update_account(
        self,
        account_id: str,
        data: AccountUpdate,
    ) -> Optional[AccountORM]:
        """更新账户信息。

        Args:
            account_id: 账户唯一标识。
            data:       更新字段。

        Returns:
            更新后的 AccountORM 实例，不存在时返回 None。
        """
        values = data.model_dump(exclude_unset=True)
        if not values:
            return await self.get_account_by_id(account_id)

        stmt = (
            update(AccountORM)
            .where(AccountORM.account_id == account_id)
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        logger.info(f"账户已更新: {account_id}, 字段: {list(values.keys())}")
        return await self.get_account_by_id(account_id)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    async def delete_account(self, account_id: str) -> bool:
        """删除账户。

        Args:
            account_id: 账户唯一标识。

        Returns:
            是否删除成功。
        """
        orm = await self.get_account_by_id(account_id)
        if orm is None:
            return False
        await self.session.delete(orm)
        await self.session.flush()
        logger.info(f"账户已删除: {account_id}")
        return True

    # ------------------------------------------------------------------
    # ORM -> dataclass 转换
    # ------------------------------------------------------------------

    @staticmethod
    def to_model(orm: AccountORM) -> Account:
        """将 AccountORM 转换为 Account dataclass。"""
        return Account(
            account_id=orm.account_id,
            broker=orm.broker,
            account_type=AccountType(orm.account_type),
            total_value=orm.total_value,
            cash=orm.cash,
            market_value=orm.market_value,
            available_cash=orm.available_cash,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )
