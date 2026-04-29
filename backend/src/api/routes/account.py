"""账户API路由

提供账户管理相关的API端点：
- GET  /api/accounts           - 获取账户列表
- GET  /api/accounts/{id}      - 获取账户详情
- POST /api/accounts/paper     - 创建模拟账户
- POST /api/accounts/sync      - 同步账户数据
- PUT  /api/accounts/{id}/mode - 切换交易模式
"""

import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.account import (
    AccountActionResponse,
    AccountDetailResponse,
    AccountListResponse,
    CreatePaperAccountRequest,
    SwitchModeRequest,
    SyncAccountRequest,
)
from src.database.connection import get_async_session
from src.database.repositories.account_repo import AccountRepository
from src.database.schema import AccountORM
from src.models.account import AccountCreate, AccountType

router = APIRouter(prefix="/api/v1/accounts", tags=["账户"])


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_db() -> AsyncSession:
    """获取异步数据库会话的依赖。"""
    async with get_async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# ORM -> Schema 转换辅助函数
# ---------------------------------------------------------------------------

def _orm_to_account_detail(orm: AccountORM) -> AccountDetailResponse:
    """将 AccountORM 转换为 AccountDetailResponse。"""
    return AccountDetailResponse(
        account_id=orm.account_id,
        broker=orm.broker,
        account_type=orm.account_type,
        total_value=orm.total_value,
        cash=orm.cash,
        market_value=orm.market_value,
        available_cash=orm.available_cash,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/accounts - 获取账户列表
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=AccountListResponse,
    summary="获取账户列表",
    description="获取所有账户列表，支持按类型和券商筛选，支持分页。",
)
async def list_accounts(
    account_type: Optional[AccountType] = Query(default=None, description="按账户类型筛选"),
    broker: Optional[str] = Query(default=None, max_length=32, description="按券商名称筛选"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页记录数"),
    db: AsyncSession = Depends(get_db),
) -> AccountListResponse:
    """获取账户列表。"""
    try:
        repo = AccountRepository(db)

        total = await repo.count_accounts(
            account_type=account_type,
            broker=broker,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        skip = (page - 1) * page_size

        orms = await repo.get_all_accounts(
            account_type=account_type,
            broker=broker,
            skip=skip,
            limit=page_size,
        )

        items = [_orm_to_account_detail(orm) for orm in orms]

        return AccountListResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    except Exception as e:
        logger.error(f"获取账户列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取账户列表失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/accounts/{id} - 获取账户详情
# ---------------------------------------------------------------------------

@router.get(
    "/{account_id}",
    response_model=AccountDetailResponse,
    summary="获取账户详情",
    description="根据账户ID获取账户的详细信息。",
)
async def get_account_detail(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> AccountDetailResponse:
    """获取账户详情。"""
    try:
        repo = AccountRepository(db)
        orm = await repo.get_account_by_id(account_id)

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户不存在: {account_id}",
            )

        return _orm_to_account_detail(orm)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取账户详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取账户详情失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/accounts/paper - 创建模拟账户
# ---------------------------------------------------------------------------

@router.post(
    "/paper",
    response_model=AccountActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建模拟账户",
    description="创建一个新的模拟交易账户。",
)
async def create_paper_account(
    request: CreatePaperAccountRequest,
    db: AsyncSession = Depends(get_db),
) -> AccountActionResponse:
    """创建模拟账户。"""
    try:
        repo = AccountRepository(db)

        # 检查账户ID是否已存在
        existing = await repo.get_account_by_id(request.account_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"账户ID已存在: {request.account_id}",
            )

        # 创建账户
        create_data = AccountCreate(
            account_id=request.account_id,
            broker=request.broker,
            account_type=AccountType.PAPER,
            initial_cash=request.initial_cash,
        )
        orm = await repo.create_account(create_data)
        await db.commit()

        logger.info(
            f"模拟账户已创建: {request.account_id}, "
            f"初始资金: {request.initial_cash:,.2f}"
        )

        return AccountActionResponse(
            success=True,
            message=f"模拟账户创建成功: {request.account_id}",
            account_id=orm.account_id,
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建模拟账户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建模拟账户失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/accounts/sync - 同步账户数据
# ---------------------------------------------------------------------------

@router.post(
    "/sync",
    response_model=AccountActionResponse,
    summary="同步账户数据",
    description="从券商同步指定账户的最新数据，包括持仓和订单信息。",
)
async def sync_account(
    request: SyncAccountRequest,
    db: AsyncSession = Depends(get_db),
) -> AccountActionResponse:
    """同步账户数据。"""
    try:
        repo = AccountRepository(db)

        # 检查账户是否存在
        orm = await repo.get_account_by_id(request.account_id)
        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户不存在: {request.account_id}",
            )

        # 模拟同步操作 (实际项目中会调用券商API)
        # 这里更新 updated_at 字段来表示同步完成
        stmt = (
            update(AccountORM)
            .where(AccountORM.account_id == request.account_id)
            .values(updated_at=datetime.now())
        )
        await db.execute(stmt)
        await db.commit()

        sync_details = []
        if request.sync_positions:
            sync_details.append("持仓")
        if request.sync_orders:
            sync_details.append("订单")

        logger.info(
            f"账户数据同步完成: {request.account_id}, "
            f"同步内容: {', '.join(sync_details)}"
        )

        return AccountActionResponse(
            success=True,
            message=f"账户数据同步完成: {request.account_id} ({', '.join(sync_details)})",
            account_id=request.account_id,
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"同步账户数据失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步账户数据失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# PUT /api/accounts/{id}/mode - 切换交易模式
# ---------------------------------------------------------------------------

@router.put(
    "/{account_id}/mode",
    response_model=AccountActionResponse,
    summary="切换交易模式",
    description="切换指定账户的交易模式 (paper / live / backtest)。",
)
async def switch_account_mode(
    account_id: str,
    request: SwitchModeRequest,
    db: AsyncSession = Depends(get_db),
) -> AccountActionResponse:
    """切换账户交易模式。"""
    try:
        repo = AccountRepository(db)

        # 检查账户是否存在
        orm = await repo.get_account_by_id(account_id)
        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户不存在: {account_id}",
            )

        # 检查目标模式是否与当前相同
        current_type = orm.account_type
        target_mode = request.mode

        if current_type == target_mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"账户已处于 {target_mode} 模式",
            )

        # 更新账户类型
        stmt = (
            update(AccountORM)
            .where(AccountORM.account_id == account_id)
            .values(account_type=target_mode)
        )
        await db.execute(stmt)
        await db.commit()

        logger.info(
            f"账户交易模式已切换: {account_id} "
            f"{current_type} -> {target_mode}"
        )

        return AccountActionResponse(
            success=True,
            message=f"交易模式已切换: {current_type} -> {target_mode}",
            account_id=account_id,
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"切换交易模式失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"切换交易模式失败: {str(e)}",
        )
