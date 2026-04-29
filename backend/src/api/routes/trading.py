"""交易API路由

提供交易相关的API端点：
- POST   /api/trading/order       - 下单
- DELETE /api/trading/order/{id}  - 撤单
- GET    /api/trading/orders      - 查询订单列表
- GET    /api/trading/order/{id}  - 查询订单详情
- GET    /api/trading/positions   - 查询持仓
- GET    /api/trading/account     - 查询账户
"""

import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.trading import (
    AccountResponse,
    ActionResponse,
    CancelOrderRequest,
    OrderListResponse,
    OrderRequest,
    OrderResponse,
    PositionListResponse,
    PositionResponse,
)
from src.database.connection import get_async_session
from src.database.repositories.account_repo import AccountRepository
from src.database.repositories.order_repo import OrderRepository
from src.database.repositories.position_repo import PositionRepository
from src.models.order import OrderSide, OrderStatus, OrderType

router = APIRouter(prefix="/api/v1/trading", tags=["交易"])


# ---------------------------------------------------------------------------
# 依赖注入: 获取数据库会话
# ---------------------------------------------------------------------------

async def get_db() -> AsyncSession:
    """获取异步数据库会话的依赖。"""
    async with get_async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# ORM -> Schema 转换辅助函数
# ---------------------------------------------------------------------------

def _orm_to_order_response(orm) -> OrderResponse:
    """将 OrderORM 转换为 OrderResponse。"""
    return OrderResponse(
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
        account_id=orm.account_id or None,
        broker=orm.broker or None,
    )


def _orm_to_position_response(orm) -> PositionResponse:
    """将 PositionORM 转换为 PositionResponse。"""
    unrealized_pnl_pct = (
        (orm.current_price - orm.avg_cost) / orm.avg_cost
        if orm.avg_cost > 0
        else 0.0
    )
    return PositionResponse(
        symbol=orm.symbol,
        quantity=orm.quantity,
        avg_cost=orm.avg_cost,
        current_price=orm.current_price,
        market_value=orm.market_value,
        unrealized_pnl=orm.unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        account_id=orm.account_id or None,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _orm_to_account_response(orm) -> AccountResponse:
    """将 AccountORM 转换为 AccountResponse。"""
    return AccountResponse(
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
# POST /api/trading/order - 下单
# ---------------------------------------------------------------------------

@router.post(
    "/order",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="下单",
    description="提交一个新的交易订单。限价单必须提供price参数。",
)
async def place_order(
    request: OrderRequest,
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    """提交交易订单。"""
    # 限价单必须提供价格
    if request.order_type == OrderType.LIMIT and request.price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="限价单必须提供委托价格 (price)",
        )

    # 生成订单ID
    order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    try:
        repo = OrderRepository(db)
        orm = await repo.create_order(
            order_id=order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            account_id=request.account_id,
        )
        await db.commit()

        logger.info(
            f"订单提交成功: {order_id} {request.side.value} "
            f"{request.symbol} x{request.quantity}"
        )

        return ActionResponse(
            success=True,
            message="订单已提交",
            order_id=orm.order_id,
            timestamp=datetime.now(),
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"下单失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下单失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/trading/order/{order_id} - 撤单
# ---------------------------------------------------------------------------

@router.delete(
    "/order/{order_id}",
    response_model=ActionResponse,
    summary="撤单",
    description="根据订单ID撤销一个未成交的订单。",
)
async def cancel_order(
    order_id: str,
    request: Optional[CancelOrderRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    """撤销订单。"""
    try:
        repo = OrderRepository(db)
        orm = await repo.get_order_by_id(order_id)

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"订单不存在: {order_id}",
            )

        # 检查订单状态是否允许撤销
        current_status = OrderStatus(orm.status)
        if current_status not in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"当前订单状态 ({current_status.value}) 不允许撤销，"
                       f"仅 pending 或 partial_filled 状态可撤销",
            )

        # 更新订单状态为已撤销
        updated = await repo.update_order_status(
            order_id=order_id,
            status=OrderStatus.CANCELLED,
        )
        await db.commit()

        reason = request.reason if request else None
        logger.info(f"订单已撤销: {order_id}, 原因: {reason or '用户主动撤销'}")

        return ActionResponse(
            success=True,
            message=f"订单已撤销: {order_id}",
            order_id=order_id,
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"撤单失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"撤单失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/trading/orders - 查询订单列表
# ---------------------------------------------------------------------------

@router.get(
    "/orders",
    response_model=OrderListResponse,
    summary="查询订单列表",
    description="查询订单列表，支持分页和多条件筛选。",
)
async def list_orders(
    account_id: Optional[str] = Query(default=None, max_length=64, description="按账户ID筛选"),
    symbol: Optional[str] = Query(default=None, max_length=32, description="按标的代码筛选"),
    side: Optional[OrderSide] = Query(default=None, description="按买卖方向筛选"),
    status: Optional[OrderStatus] = Query(default=None, description="按订单状态筛选"),
    order_type: Optional[OrderType] = Query(default=None, description="按订单类型筛选"),
    start_time: Optional[datetime] = Query(default=None, description="起始时间 (ISO格式)"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间 (ISO格式)"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页记录数"),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """查询订单列表。"""
    try:
        repo = OrderRepository(db)

        # 统计总数
        total = await repo.count_orders(
            account_id=account_id,
            symbol=symbol,
            side=side,
            status=status,
            order_type=order_type,
            start_time=start_time,
            end_time=end_time,
        )

        # 分页计算
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        skip = (page - 1) * page_size

        # 查询数据
        orms = await repo.get_orders(
            account_id=account_id,
            symbol=symbol,
            side=side,
            status=status,
            order_type=order_type,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=page_size,
        )

        items = [_orm_to_order_response(orm) for orm in orms]

        return OrderListResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    except Exception as e:
        logger.error(f"查询订单列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询订单列表失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/trading/order/{order_id} - 查询订单详情
# ---------------------------------------------------------------------------

@router.get(
    "/order/{order_id}",
    response_model=OrderResponse,
    summary="查询订单详情",
    description="根据订单ID查询订单详细信息。",
)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """查询订单详情。"""
    try:
        repo = OrderRepository(db)
        orm = await repo.get_order_by_id(order_id)

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"订单不存在: {order_id}",
            )

        return _orm_to_order_response(orm)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询订单详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询订单详情失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/trading/positions - 查询持仓
# ---------------------------------------------------------------------------

@router.get(
    "/positions",
    response_model=PositionListResponse,
    summary="查询持仓",
    description="查询当前持仓列表，支持按账户和标的筛选。",
)
async def list_positions(
    account_id: Optional[str] = Query(default=None, max_length=64, description="按账户ID筛选"),
    symbol: Optional[str] = Query(default=None, max_length=32, description="按标的代码筛选"),
    db: AsyncSession = Depends(get_db),
) -> PositionListResponse:
    """查询持仓列表。"""
    try:
        repo = PositionRepository(db)

        if account_id:
            orms = await repo.get_positions_by_account(account_id, skip=0, limit=500)
            total = await repo.count_positions(account_id=account_id)
        else:
            orms = await repo.get_all_positions(symbol=symbol, skip=0, limit=500)
            total = await repo.count_positions(symbol=symbol)

        items = [_orm_to_position_response(orm) for orm in orms]

        return PositionListResponse(
            total=total,
            items=items,
        )

    except Exception as e:
        logger.error(f"查询持仓失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询持仓失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/trading/account - 查询账户
# ---------------------------------------------------------------------------

@router.get(
    "/account",
    response_model=AccountResponse,
    summary="查询账户",
    description="查询指定账户的详细信息。需提供account_id参数。",
)
async def get_account(
    account_id: str = Query(..., min_length=1, max_length=64, description="账户ID"),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """查询账户信息。"""
    try:
        repo = AccountRepository(db)
        orm = await repo.get_account_by_id(account_id)

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户不存在: {account_id}",
            )

        return _orm_to_account_response(orm)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询账户失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询账户失败: {str(e)}",
        )
