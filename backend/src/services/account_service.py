"""账户服务模块

提供账户信息管理、多账户支持、账户同步和数据缓存功能。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.account import (
    Account,
    AccountCreate,
    AccountType,
    AccountUpdate,
)


# ---------------------------------------------------------------------------
# 账户缓存条目
# ---------------------------------------------------------------------------

@dataclass
class _CachedAccount:
    """缓存账户条目"""
    account: Account
    cached_at: float = field(default_factory=time.time)
    ttl: float = 30.0  # 缓存有效期（秒）

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.cached_at) > self.ttl


# ---------------------------------------------------------------------------
# AccountService
# ---------------------------------------------------------------------------

class AccountService:
    """账户服务

    提供账户信息管理、多账户支持、账户同步和数据缓存。

    Usage::

        service = AccountService(session_factory)
        account = await service.get_account_info("paper_001")
        accounts = await service.get_all_accounts()
        await service.sync_account("paper_001")
    """

    def __init__(
        self,
        session_factory,
        cache_ttl: float = 30.0,
    ) -> None:
        """
        初始化账户服务。

        Args:
            session_factory: 异步数据库会话工厂。
            cache_ttl:       账户缓存有效期（秒），默认 30 秒。
        """
        self._session_factory = session_factory
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, _CachedAccount] = {}
        self._initialized = False

        logger.info("AccountService 已创建")

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """初始化账户服务，预热缓存。"""
        if self._initialized:
            return

        try:
            # 预加载所有账户到缓存
            from src.database.connection import get_async_session

            async with get_async_session() as session:
                from src.database.repositories.account_repo import AccountRepository
                repo = AccountRepository(session)
                orms = await repo.get_all_accounts(skip=0, limit=1000)
                for orm in orms:
                    account = AccountRepository.to_model(orm)
                    self._cache[account.account_id] = _CachedAccount(
                        account=account,
                        ttl=self._cache_ttl,
                    )

            self._initialized = True
            logger.info(f"AccountService 初始化完成, 已缓存 {len(self._cache)} 个账户")

        except Exception as e:
            logger.error(f"AccountService 初始化失败: {e}")
            # 初始化失败不阻断服务，只是缓存为空
            self._initialized = True

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def _get_from_cache(self, account_id: str) -> Optional[Account]:
        """从缓存获取账户信息。"""
        cached = self._cache.get(account_id)
        if cached is None:
            return None
        if cached.is_expired:
            del self._cache[account_id]
            return None
        return cached.account

    def _put_to_cache(self, account: Account) -> None:
        """将账户信息放入缓存。"""
        self._cache[account.account_id] = _CachedAccount(
            account=account,
            ttl=self._cache_ttl,
        )

    def _invalidate_cache(self, account_id: Optional[str] = None) -> None:
        """使缓存失效。

        Args:
            account_id: 指定账户ID，为 None 时清除全部缓存。
        """
        if account_id:
            self._cache.pop(account_id, None)
        else:
            self._cache.clear()

    def clear_cache(self) -> None:
        """清除所有账户缓存。"""
        self._cache.clear()
        logger.debug("账户缓存已清除")

    # ------------------------------------------------------------------
    # 账户查询
    # ------------------------------------------------------------------

    async def get_account_info(self, account_id: str) -> Optional[Account]:
        """获取账户信息（优先从缓存获取）。

        Args:
            account_id: 账户唯一标识。

        Returns:
            Account 对象，不存在时返回 None。
        """
        # 先查缓存
        cached = self._get_from_cache(account_id)
        if cached is not None:
            logger.debug(f"账户信息命中缓存: {account_id}")
            return cached

        # 查数据库
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.account_repo import AccountRepository

            async with get_async_session() as session:
                repo = AccountRepository(session)
                orm = await repo.get_account_by_id(account_id)

                if orm is None:
                    logger.warning(f"账户不存在: {account_id}")
                    return None

                account = AccountRepository.to_model(orm)
                self._put_to_cache(account)
                return account

        except Exception as e:
            logger.error(f"获取账户信息失败: {account_id}, 错误: {e}")
            return None

    async def get_all_accounts(
        self,
        account_type: Optional[AccountType] = None,
        broker: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Account]:
        """获取所有账户列表。

        Args:
            account_type: 按账户类型筛选。
            broker:       按券商名称筛选。
            skip:         跳过记录数。
            limit:        返回记录数上限。

        Returns:
            Account 列表。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.account_repo import AccountRepository

            async with get_async_session() as session:
                repo = AccountRepository(session)
                orms = await repo.get_all_accounts(
                    account_type=account_type,
                    broker=broker,
                    skip=skip,
                    limit=limit,
                )
                accounts = [AccountRepository.to_model(orm) for orm in orms]

                # 更新缓存
                for account in accounts:
                    self._put_to_cache(account)

                logger.info(f"查询账户列表: 共 {len(accounts)} 条记录")
                return accounts

        except Exception as e:
            logger.error(f"查询账户列表失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 账户同步
    # ------------------------------------------------------------------

    async def sync_account(self, account_id: str) -> Optional[Account]:
        """同步账户信息。

        从券商/交易所同步最新的账户数据到本地数据库。

        Args:
            account_id: 账户唯一标识。

        Returns:
            更新后的 Account 对象，失败返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.account_repo import AccountRepository

            # 获取当前账户信息
            async with get_async_session() as session:
                repo = AccountRepository(session)
                orm = await repo.get_account_by_id(account_id)

                if orm is None:
                    logger.warning(f"同步失败，账户不存在: {account_id}")
                    return None

                account = AccountRepository.to_model(orm)

                # 模拟账户类型：重新计算总资产
                if account.account_type == AccountType.PAPER:
                    from src.database.repositories.position_repo import PositionRepository
                    pos_repo = PositionRepository(session)
                    positions = await pos_repo.get_positions_by_account(
                        account_id, skip=0, limit=10000
                    )
                    market_value = sum(p.market_value for p in positions)
                    update_data = AccountUpdate(
                        market_value=market_value,
                        total_value=account.cash + market_value,
                        available_cash=account.cash,
                    )
                    updated_orm = await repo.update_account(account_id, update_data)
                    if updated_orm:
                        account = AccountRepository.to_model(updated_orm)
                        logger.info(
                            f"模拟账户已同步: {account_id}, "
                            f"总资产={account.total_value:.2f}, "
                            f"市值={market_value:.2f}"
                        )
                else:
                    # 实盘账户：此处应调用券商适配器获取最新数据
                    # 由于适配器可能不可用，仅更新时间戳
                    logger.info(f"实盘账户同步请求已记录: {account_id}")

                # 更新缓存
                self._put_to_cache(account)
                return account

        except Exception as e:
            logger.error(f"同步账户失败: {account_id}, 错误: {e}")
            return None

    async def sync_all_accounts(self) -> Dict[str, Any]:
        """同步所有账户。

        Returns:
            同步结果统计。
        """
        accounts = await self.get_all_accounts(skip=0, limit=1000)
        success_count = 0
        fail_count = 0
        errors: List[str] = []

        for account in accounts:
            try:
                result = await self.sync_account(account.account_id)
                if result is not None:
                    success_count += 1
                else:
                    fail_count += 1
                    errors.append(f"{account.account_id}: 同步返回空")
            except Exception as e:
                fail_count += 1
                errors.append(f"{account.account_id}: {e}")

        logger.info(
            f"批量同步完成: 成功={success_count}, 失败={fail_count}, "
            f"总计={len(accounts)}"
        )

        return {
            "total": len(accounts),
            "success": success_count,
            "failed": fail_count,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # 账户创建
    # ------------------------------------------------------------------

    async def create_paper_account(
        self,
        account_id: str,
        broker: str = "paper_broker",
        initial_cash: float = 1000000.0,
    ) -> Optional[Account]:
        """创建模拟账户。

        Args:
            account_id:   账户唯一标识。
            broker:       券商名称。
            initial_cash: 初始资金。

        Returns:
            新创建的 Account 对象，失败返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.account_repo import AccountRepository

            create_data = AccountCreate(
                account_id=account_id,
                broker=broker,
                account_type=AccountType.PAPER,
                initial_cash=initial_cash,
            )

            async with get_async_session() as session:
                repo = AccountRepository(session)

                # 检查是否已存在
                existing = await repo.get_account_by_id(account_id)
                if existing is not None:
                    logger.warning(f"账户已存在: {account_id}")
                    return AccountRepository.to_model(existing)

                orm = await repo.create_account(create_data)
                account = AccountRepository.to_model(orm)

                # 更新缓存
                self._put_to_cache(account)

                logger.info(
                    f"模拟账户已创建: {account_id}, "
                    f"初始资金={initial_cash:.2f}, 券商={broker}"
                )
                return account

        except Exception as e:
            logger.error(f"创建模拟账户失败: {account_id}, 错误: {e}")
            return None

    # ------------------------------------------------------------------
    # 账户模式更新
    # ------------------------------------------------------------------

    async def update_account_mode(
        self,
        account_id: str,
        new_type: AccountType,
    ) -> Optional[Account]:
        """更新账户类型（模拟/实盘）。

        Args:
            account_id: 账户唯一标识。
            new_type:   新的账户类型。

        Returns:
            更新后的 Account 对象，失败返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.account_repo import AccountRepository

            async with get_async_session() as session:
                repo = AccountRepository(session)
                orm = await repo.get_account_by_id(account_id)

                if orm is None:
                    logger.warning(f"账户不存在: {account_id}")
                    return None

                old_type = orm.account_type
                if old_type == new_type.value:
                    logger.info(f"账户类型未变更: {account_id} ({old_type})")
                    return AccountRepository.to_model(orm)

                # 更新账户类型
                from sqlalchemy import update
                from src.database.schema import AccountORM

                stmt = (
                    update(AccountORM)
                    .where(AccountORM.account_id == account_id)
                    .values(account_type=new_type.value)
                )
                await session.execute(stmt)
                await session.flush()

                updated_orm = await repo.get_account_by_id(account_id)
                account = AccountRepository.to_model(updated_orm) if updated_orm else None

                # 清除缓存
                self._invalidate_cache(account_id)

                logger.info(
                    f"账户类型已更新: {account_id} "
                    f"{old_type} -> {new_type.value}"
                )
                return account

        except Exception as e:
            logger.error(f"更新账户类型失败: {account_id}, 错误: {e}")
            return None

    # ------------------------------------------------------------------
    # 账户统计
    # ------------------------------------------------------------------

    async def get_account_summary(self) -> Dict[str, Any]:
        """获取所有账户的汇总信息。

        Returns:
            包含账户统计的字典。
        """
        accounts = await self.get_all_accounts(skip=0, limit=1000)

        total_value = 0.0
        total_cash = 0.0
        total_market_value = 0.0
        paper_count = 0
        real_count = 0

        for account in accounts:
            total_value += account.total_value
            total_cash += account.cash
            total_market_value += account.market_value
            if account.account_type == AccountType.PAPER:
                paper_count += 1
            else:
                real_count += 1

        return {
            "total_accounts": len(accounts),
            "paper_accounts": paper_count,
            "real_accounts": real_count,
            "total_value": round(total_value, 2),
            "total_cash": round(total_cash, 2),
            "total_market_value": round(total_market_value, 2),
        }
