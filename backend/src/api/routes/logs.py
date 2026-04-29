"""日志API路由

提供日志查询和导出相关的API端点：
- GET /api/logs/decisions      - 查询决策日志 (分页+筛选)
- GET /api/logs/decisions/{id} - 查询决策详情
- GET /api/logs/trades         - 查询交易日志 (分页+筛选)
- GET /api/logs/export         - 导出日志 (CSV/JSON)
- GET /api/logs/statistics     - 获取统计信息
"""

import csv
import io
import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_async_session
from src.database.repositories.log_repo import DecisionLogRepository, TradeLogRepository
from src.models.decision import DecisionAction

router = APIRouter(prefix="/api/v1/logs", tags=["日志"])


# ---------------------------------------------------------------------------
# Schema 定义 (日志专用)
# ---------------------------------------------------------------------------

class DecisionLogResponse(BaseModel):
    """决策日志响应"""
    decision_id: str = Field(..., description="决策唯一标识")
    timestamp: Optional[datetime] = Field(default=None, description="决策时间")
    model: str = Field(..., description="模型名称")
    provider: str = Field(..., description="模型供应商")
    action: str = Field(..., description="决策动作")
    symbol: Optional[str] = Field(default=None, description="标的代码")
    quantity: Optional[float] = Field(default=None, description="建议数量")
    price: Optional[float] = Field(default=None, description="建议价格")
    confidence: float = Field(default=0.0, description="决策置信度")
    reasoning: Optional[str] = Field(default=None, description="决策理由")
    executed: bool = Field(default=False, description="是否已执行")
    execution_result: Optional[str] = Field(default=None, description="执行结果")
    latency_ms: Optional[int] = Field(default=None, description="推理延迟(ms)")

    model_config = {"from_attributes": True}


class DecisionLogDetailResponse(DecisionLogResponse):
    """决策日志详情响应 (包含完整信息)"""
    raw_response: Optional[str] = Field(default=None, description="模型原始输出")
    prompt: Optional[str] = Field(default=None, description="Prompt内容")
    market_context: Optional[str] = Field(default=None, description="市场快照JSON")
    account_context: Optional[str] = Field(default=None, description="账户快照JSON")


class DecisionLogListResponse(BaseModel):
    """决策日志列表响应"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=200, description="每页记录数")
    total_pages: int = Field(..., ge=0, description="总页数")
    items: List[DecisionLogResponse] = Field(default_factory=list, description="决策日志列表")


class TradeLogResponse(BaseModel):
    """交易日志响应"""
    id: int = Field(..., description="日志ID")
    order_id: str = Field(..., description="订单ID")
    decision_id: Optional[str] = Field(default=None, description="关联的决策ID")
    account_id: str = Field(..., description="账户ID")
    broker: str = Field(default="", description="券商名称")
    symbol: str = Field(..., description="标的代码")
    side: str = Field(..., description="买卖方向")
    quantity: float = Field(..., description="成交数量")
    price: float = Field(..., description="成交价格")
    commission: float = Field(default=0.0, description="手续费")
    pnl: Optional[float] = Field(default=None, description="盈亏金额")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")

    model_config = {"from_attributes": True}


class TradeLogListResponse(BaseModel):
    """交易日志列表响应"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=200, description="每页记录数")
    total_pages: int = Field(..., ge=0, description="总页数")
    items: List[TradeLogResponse] = Field(default_factory=list, description="交易日志列表")


class LogStatisticsResponse(BaseModel):
    """日志统计响应"""
    decision_stats: Dict[str, Any] = Field(default_factory=dict, description="决策统计")
    trade_stats: Dict[str, Any] = Field(default_factory=dict, description="交易统计")


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

def _decision_orm_to_response(orm) -> DecisionLogResponse:
    """将 DecisionLogORM 转换为 DecisionLogResponse。"""
    return DecisionLogResponse(
        decision_id=orm.decision_id,
        timestamp=orm.created_at,
        model=orm.model,
        provider=orm.provider,
        action=orm.action,
        symbol=orm.symbol,
        quantity=orm.quantity,
        price=orm.price,
        confidence=orm.confidence,
        reasoning=orm.reasoning,
        executed=orm.executed,
        execution_result=orm.execution_result,
        latency_ms=orm.latency_ms,
    )


def _decision_orm_to_detail(orm) -> DecisionLogDetailResponse:
    """将 DecisionLogORM 转换为 DecisionLogDetailResponse。"""
    return DecisionLogDetailResponse(
        decision_id=orm.decision_id,
        timestamp=orm.created_at,
        model=orm.model,
        provider=orm.provider,
        action=orm.action,
        symbol=orm.symbol,
        quantity=orm.quantity,
        price=orm.price,
        confidence=orm.confidence,
        reasoning=orm.reasoning,
        executed=orm.executed,
        execution_result=orm.execution_result,
        latency_ms=orm.latency_ms,
        raw_response=orm.raw_response,
        prompt=orm.prompt,
        market_context=orm.market_context,
        account_context=orm.account_context,
    )


def _trade_orm_to_response(orm) -> TradeLogResponse:
    """将 TradeLogORM 转换为 TradeLogResponse。"""
    return TradeLogResponse(
        id=orm.id,
        order_id=orm.order_id,
        decision_id=orm.decision_id,
        account_id=orm.account_id,
        broker=orm.broker,
        symbol=orm.symbol,
        side=orm.side,
        quantity=orm.quantity,
        price=orm.price,
        commission=orm.commission,
        pnl=orm.pnl,
        created_at=orm.created_at,
    )


# ---------------------------------------------------------------------------
# GET /api/logs/decisions - 查询决策日志
# ---------------------------------------------------------------------------

@router.get(
    "/decisions",
    response_model=DecisionLogListResponse,
    summary="查询决策日志",
    description="查询AI决策日志列表，支持分页和多条件筛选。",
)
async def list_decisions(
    model: Optional[str] = Query(default=None, max_length=64, description="按模型名称筛选"),
    provider: Optional[str] = Query(default=None, max_length=32, description="按模型供应商筛选"),
    action: Optional[DecisionAction] = Query(default=None, description="按决策动作筛选"),
    symbol: Optional[str] = Query(default=None, max_length=32, description="按标的代码筛选"),
    executed: Optional[bool] = Query(default=None, description="按执行状态筛选"),
    start_time: Optional[datetime] = Query(default=None, description="起始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页记录数"),
    db: AsyncSession = Depends(get_db),
) -> DecisionLogListResponse:
    """查询决策日志列表。"""
    try:
        repo = DecisionLogRepository(db)

        total = await repo.count_decision_logs(
            model=model,
            provider=provider,
            action=action,
            symbol=symbol,
            executed=executed,
            start_time=start_time,
            end_time=end_time,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        skip = (page - 1) * page_size

        orms = await repo.get_decision_logs(
            model=model,
            provider=provider,
            action=action,
            symbol=symbol,
            executed=executed,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=page_size,
        )

        items = [_decision_orm_to_response(orm) for orm in orms]

        return DecisionLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    except Exception as e:
        logger.error(f"查询决策日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询决策日志失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/logs/decisions/{id} - 查询决策详情
# ---------------------------------------------------------------------------

@router.get(
    "/decisions/{decision_id}",
    response_model=DecisionLogDetailResponse,
    summary="查询决策详情",
    description="根据决策ID查询决策的完整详细信息，包括原始输出和上下文。",
)
async def get_decision_detail(
    decision_id: str,
    db: AsyncSession = Depends(get_db),
) -> DecisionLogDetailResponse:
    """查询决策详情。"""
    try:
        repo = DecisionLogRepository(db)
        orm = await repo.get_decision_log(decision_id)

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"决策日志不存在: {decision_id}",
            )

        return _decision_orm_to_detail(orm)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询决策详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询决策详情失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/logs/trades - 查询交易日志
# ---------------------------------------------------------------------------

@router.get(
    "/trades",
    response_model=TradeLogListResponse,
    summary="查询交易日志",
    description="查询交易日志列表，支持分页和多条件筛选。",
)
async def list_trades(
    account_id: Optional[str] = Query(default=None, max_length=64, description="按账户ID筛选"),
    symbol: Optional[str] = Query(default=None, max_length=32, description="按标的代码筛选"),
    side: Optional[str] = Query(default=None, description="按买卖方向筛选"),
    broker: Optional[str] = Query(default=None, max_length=32, description="按券商名称筛选"),
    decision_id: Optional[str] = Query(default=None, max_length=64, description="按关联决策ID筛选"),
    start_time: Optional[datetime] = Query(default=None, description="起始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=200, description="每页记录数"),
    db: AsyncSession = Depends(get_db),
) -> TradeLogListResponse:
    """查询交易日志列表。"""
    try:
        repo = TradeLogRepository(db)

        total = await repo.count_trade_logs(
            account_id=account_id,
            symbol=symbol,
            side=side,
            broker=broker,
            decision_id=decision_id,
            start_time=start_time,
            end_time=end_time,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 1
        skip = (page - 1) * page_size

        orms = await repo.get_trade_logs(
            account_id=account_id,
            symbol=symbol,
            side=side,
            broker=broker,
            decision_id=decision_id,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=page_size,
        )

        items = [_trade_orm_to_response(orm) for orm in orms]

        return TradeLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    except Exception as e:
        logger.error(f"查询交易日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询交易日志失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/logs/export - 导出日志
# ---------------------------------------------------------------------------

@router.get(
    "/export",
    summary="导出日志",
    description="导出决策日志或交易日志，支持CSV和JSON格式。",
)
async def export_logs(
    log_type: str = Query(
        ...,
        pattern=r"^(decisions|trades)$",
        description="日志类型: decisions / trades",
    ),
    format: str = Query(
        default="json",
        pattern=r"^(csv|json)$",
        description="导出格式: csv / json",
    ),
    start_time: Optional[datetime] = Query(default=None, description="起始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """导出日志数据。"""
    try:
        if log_type == "decisions":
            repo = DecisionLogRepository(db)
            orms = await repo.get_decision_logs(
                start_time=start_time,
                end_time=end_time,
                skip=0,
                limit=10000,
            )
            rows = [
                {
                    "decision_id": orm.decision_id,
                    "timestamp": orm.created_at.isoformat() if orm.created_at else "",
                    "model": orm.model,
                    "provider": orm.provider,
                    "action": orm.action,
                    "symbol": orm.symbol or "",
                    "quantity": orm.quantity or 0,
                    "price": orm.price or 0,
                    "confidence": orm.confidence,
                    "reasoning": orm.reasoning or "",
                    "executed": orm.executed,
                    "execution_result": orm.execution_result or "",
                    "latency_ms": orm.latency_ms or 0,
                }
                for orm in orms
            ]
        else:
            repo = TradeLogRepository(db)
            orms = await repo.get_trade_logs(
                start_time=start_time,
                end_time=end_time,
                skip=0,
                limit=10000,
            )
            rows = [
                {
                    "id": orm.id,
                    "order_id": orm.order_id,
                    "decision_id": orm.decision_id or "",
                    "account_id": orm.account_id,
                    "broker": orm.broker,
                    "symbol": orm.symbol,
                    "side": orm.side,
                    "quantity": orm.quantity,
                    "price": orm.price,
                    "commission": orm.commission,
                    "pnl": orm.pnl or 0,
                    "created_at": orm.created_at.isoformat() if orm.created_at else "",
                }
                for orm in orms
            ]

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"没有找到符合条件的{log_type}日志",
            )

        if format == "json":
            content = json.dumps(rows, ensure_ascii=False, indent=2)
            media_type = "application/json"
            filename = f"{log_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            # CSV格式
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            content = output.getvalue()
            media_type = "text/csv; charset=utf-8"
            filename = f"{log_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出日志失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/logs/statistics - 获取统计信息
# ---------------------------------------------------------------------------

@router.get(
    "/statistics",
    response_model=LogStatisticsResponse,
    summary="获取统计信息",
    description="获取决策和交易的汇总统计信息。",
)
async def get_statistics(
    account_id: Optional[str] = Query(default=None, max_length=64, description="按账户ID筛选"),
    start_time: Optional[datetime] = Query(default=None, description="起始时间"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间"),
    db: AsyncSession = Depends(get_db),
) -> LogStatisticsResponse:
    """获取日志统计信息。"""
    try:
        decision_repo = DecisionLogRepository(db)
        trade_repo = TradeLogRepository(db)

        decision_stats = await decision_repo.get_decision_statistics(
            start_time=start_time,
            end_time=end_time,
        )

        trade_stats = await trade_repo.get_trade_statistics(
            account_id=account_id,
            start_time=start_time,
            end_time=end_time,
        )

        return LogStatisticsResponse(
            decision_stats=decision_stats,
            trade_stats=trade_stats,
        )

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}",
        )
