"""策略API路由

提供策略管理相关的API端点：
- GET    /api/strategy/prompts      - 获取Prompt模板列表
- POST   /api/strategy/prompts      - 创建Prompt模板
- PUT    /api/strategy/prompts/{id} - 更新Prompt模板
- DELETE /api/strategy/prompts/{id} - 删除Prompt模板
- GET    /api/strategy/config       - 获取策略配置
- PUT    /api/strategy/config       - 更新策略配置
- POST   /api/strategy/start        - 启动策略
- POST   /api/strategy/stop         - 停止策略
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_async_session
from src.database.schema import PromptTemplateORM, SystemConfigORM

router = APIRouter(prefix="/api/v1/strategy", tags=["策略"])


# ---------------------------------------------------------------------------
# Schema 定义 (策略专用)
# ---------------------------------------------------------------------------

class PromptTemplateCreate(BaseModel):
    """创建Prompt模板请求"""
    name: str = Field(..., min_length=1, max_length=64, description="模板名称")
    category: str = Field(..., min_length=1, max_length=32, description="模板分类")
    content: str = Field(..., min_length=1, description="模板内容")
    variables: Optional[str] = Field(default=None, description="变量列表JSON")
    is_active: bool = Field(default=True, description="是否启用")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "momentum_strategy",
                    "category": "trading",
                    "content": "基于以下市场数据，分析{symbol}的动量指标...",
                    "variables": '["symbol", "timeframe", "indicators"]',
                    "is_active": True,
                }
            ]
        }
    }


class PromptTemplateUpdate(BaseModel):
    """更新Prompt模板请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=64, description="模板名称")
    category: Optional[str] = Field(default=None, min_length=1, max_length=32, description="模板分类")
    content: Optional[str] = Field(default=None, min_length=1, description="模板内容")
    variables: Optional[str] = Field(default=None, description="变量列表JSON")
    is_active: Optional[bool] = Field(default=None, description="是否启用")


class PromptTemplateResponse(BaseModel):
    """Prompt模板响应"""
    id: int = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    category: str = Field(..., description="模板分类")
    content: str = Field(..., description="模板内容")
    variables: Optional[str] = Field(default=None, description="变量列表JSON")
    version: int = Field(..., description="版本号")
    is_active: bool = Field(..., description="是否启用")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    model_config = {"from_attributes": True}


class PromptTemplateListResponse(BaseModel):
    """Prompt模板列表响应"""
    total: int = Field(..., ge=0, description="总数")
    items: List[PromptTemplateResponse] = Field(default_factory=list, description="模板列表")


class StrategyConfigResponse(BaseModel):
    """策略配置响应"""
    configs: Dict[str, Any] = Field(default_factory=dict, description="配置键值对")


class StrategyConfigUpdate(BaseModel):
    """策略配置更新请求"""
    configs: Dict[str, str] = Field(
        ...,
        min_length=1,
        description="要更新的配置键值对",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "configs": {
                        "strategy_mode": "momentum",
                        "max_position_pct": "10",
                        "rebalance_interval": "3600",
                    }
                }
            ]
        }
    }


class StrategyActionResponse(BaseModel):
    """策略操作响应"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(default="", description="操作结果描述")
    timestamp: Optional[datetime] = Field(default=None, description="操作时间")


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_db() -> AsyncSession:
    """获取异步数据库会话的依赖。"""
    async with get_async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# StrategyService 单例
# ---------------------------------------------------------------------------

_strategy_service: Optional["StrategyService"] = None


def get_strategy_service() -> "StrategyService":
    """获取 StrategyService 单例。"""
    global _strategy_service
    if _strategy_service is None:
        from src.services.strategy_service import StrategyService
        _strategy_service = StrategyService()
    return _strategy_service


# ---------------------------------------------------------------------------
# GET /api/strategy/prompts - 获取Prompt模板列表
# ---------------------------------------------------------------------------

@router.get(
    "/prompts",
    response_model=PromptTemplateListResponse,
    summary="获取Prompt模板列表",
    description="获取所有Prompt模板，支持按分类和激活状态筛选。",
)
async def list_prompts(
    category: Optional[str] = Query(default=None, max_length=32, description="按分类筛选"),
    is_active: Optional[bool] = Query(default=None, description="按激活状态筛选"),
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateListResponse:
    """获取Prompt模板列表。"""
    try:
        stmt = select(PromptTemplateORM)
        if category is not None:
            stmt = stmt.where(PromptTemplateORM.category == category)
        if is_active is not None:
            stmt = stmt.where(PromptTemplateORM.is_active == is_active)
        stmt = stmt.order_by(PromptTemplateORM.created_at.desc())

        result = await db.execute(stmt)
        orms = list(result.scalars().all())

        items = [
            PromptTemplateResponse(
                id=orm.id,
                name=orm.name,
                category=orm.category,
                content=orm.content,
                variables=orm.variables,
                version=orm.version,
                is_active=orm.is_active,
                created_at=orm.created_at,
                updated_at=orm.updated_at,
            )
            for orm in orms
        ]

        return PromptTemplateListResponse(total=len(items), items=items)

    except Exception as e:
        logger.error(f"获取Prompt模板列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Prompt模板列表失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/strategy/prompts - 创建Prompt模板
# ---------------------------------------------------------------------------

@router.post(
    "/prompts",
    response_model=PromptTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建Prompt模板",
    description="创建一个新的Prompt模板。",
)
async def create_prompt(
    request: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateResponse:
    """创建Prompt模板。"""
    try:
        # 检查名称是否已存在
        existing_stmt = select(PromptTemplateORM).where(
            PromptTemplateORM.name == request.name
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"模板名称已存在: {request.name}",
            )

        orm = PromptTemplateORM(
            name=request.name,
            category=request.category,
            content=request.content,
            variables=request.variables,
            is_active=request.is_active,
        )
        db.add(orm)
        await db.flush()
        await db.commit()
        await db.refresh(orm)

        logger.info(f"Prompt模板已创建: {request.name} (ID={orm.id})")

        return PromptTemplateResponse(
            id=orm.id,
            name=orm.name,
            category=orm.category,
            content=orm.content,
            variables=orm.variables,
            version=orm.version,
            is_active=orm.is_active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建Prompt模板失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建Prompt模板失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# PUT /api/strategy/prompts/{id} - 更新Prompt模板
# ---------------------------------------------------------------------------

@router.put(
    "/prompts/{prompt_id}",
    response_model=PromptTemplateResponse,
    summary="更新Prompt模板",
    description="根据ID更新Prompt模板，更新content时自动递增版本号。",
)
async def update_prompt(
    prompt_id: int,
    request: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
) -> PromptTemplateResponse:
    """更新Prompt模板。"""
    try:
        stmt = select(PromptTemplateORM).where(PromptTemplateORM.id == prompt_id)
        orm = (await db.execute(stmt)).scalar_one_or_none()

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt模板不存在: ID={prompt_id}",
            )

        # 更新字段
        update_data = request.model_dump(exclude_unset=True)

        # 如果更新了content，自动递增版本号
        if "content" in update_data:
            orm.version += 1

        for key, value in update_data.items():
            setattr(orm, key, value)

        await db.flush()
        await db.commit()
        await db.refresh(orm)

        logger.info(f"Prompt模板已更新: {orm.name} (ID={orm.id}, version={orm.version})")

        return PromptTemplateResponse(
            id=orm.id,
            name=orm.name,
            category=orm.category,
            content=orm.content,
            variables=orm.variables,
            version=orm.version,
            is_active=orm.is_active,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新Prompt模板失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新Prompt模板失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/strategy/prompts/{id} - 删除Prompt模板
# ---------------------------------------------------------------------------

@router.delete(
    "/prompts/{prompt_id}",
    response_model=StrategyActionResponse,
    summary="删除Prompt模板",
    description="根据ID删除Prompt模板。",
)
async def delete_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
) -> StrategyActionResponse:
    """删除Prompt模板。"""
    try:
        stmt = select(PromptTemplateORM).where(PromptTemplateORM.id == prompt_id)
        orm = (await db.execute(stmt)).scalar_one_or_none()

        if orm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt模板不存在: ID={prompt_id}",
            )

        template_name = orm.name
        await db.delete(orm)
        await db.commit()

        logger.info(f"Prompt模板已删除: {template_name} (ID={prompt_id})")

        return StrategyActionResponse(
            success=True,
            message=f"Prompt模板已删除: {template_name}",
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除Prompt模板失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除Prompt模板失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/strategy/config - 获取策略配置
# ---------------------------------------------------------------------------

@router.get(
    "/config",
    response_model=StrategyConfigResponse,
    summary="获取策略配置",
    description="获取所有策略相关的系统配置。",
)
async def get_strategy_config(
    db: AsyncSession = Depends(get_db),
) -> StrategyConfigResponse:
    """获取策略配置。"""
    try:
        stmt = select(SystemConfigORM).where(
            SystemConfigORM.key.like("strategy_%")
        )
        result = await db.execute(stmt)
        orms = list(result.scalars().all())

        configs: Dict[str, Any] = {}
        for orm in orms:
            try:
                configs[orm.key] = json.loads(orm.value) if not orm.encrypted else orm.value
            except (json.JSONDecodeError, TypeError):
                configs[orm.key] = orm.value

        return StrategyConfigResponse(configs=configs)

    except Exception as e:
        logger.error(f"获取策略配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取策略配置失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# PUT /api/strategy/config - 更新策略配置
# ---------------------------------------------------------------------------

@router.put(
    "/config",
    response_model=StrategyActionResponse,
    summary="更新策略配置",
    description="批量更新策略相关的系统配置。",
)
async def update_strategy_config(
    request: StrategyConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> StrategyActionResponse:
    """更新策略配置。"""
    try:
        updated_count = 0
        for key, value in request.configs.items():
            # 查找是否已存在
            stmt = select(SystemConfigORM).where(SystemConfigORM.key == key)
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing is not None:
                # 更新
                stmt_update = (
                    update(SystemConfigORM)
                    .where(SystemConfigORM.key == key)
                    .values(value=value)
                )
                await db.execute(stmt_update)
            else:
                # 创建
                new_config = SystemConfigORM(key=key, value=value, encrypted=False)
                db.add(new_config)

            updated_count += 1

        await db.commit()

        logger.info(f"策略配置已更新: {updated_count} 项")

        return StrategyActionResponse(
            success=True,
            message=f"策略配置已更新: {updated_count} 项",
            timestamp=datetime.now(),
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"更新策略配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新策略配置失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/v1/strategy/start - 启动策略
# ---------------------------------------------------------------------------

@router.post(
    "/start",
    response_model=StrategyActionResponse,
    summary="启动策略",
    description="启动自动交易策略引擎。",
)
async def start_strategy(
    strategy_name: str = Query(default="default", description="策略名称"),
    strategy_svc: "StrategyService" = Depends(get_strategy_service),
) -> StrategyActionResponse:
    """启动策略引擎。"""
    try:
        success = await strategy_svc.start_strategy(strategy_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"策略启动失败: {strategy_name}",
            )

        logger.info(f"策略引擎已启动: {strategy_name}")

        return StrategyActionResponse(
            success=True,
            message=f"策略已启动: {strategy_name}",
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动策略失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/v1/strategy/stop - 停止策略
# ---------------------------------------------------------------------------

@router.post(
    "/stop",
    response_model=StrategyActionResponse,
    summary="停止策略",
    description="停止自动交易策略引擎。",
)
async def stop_strategy(
    strategy_name: str = Query(default="default", description="策略名称"),
    strategy_svc: "StrategyService" = Depends(get_strategy_service),
) -> StrategyActionResponse:
    """停止策略引擎。"""
    try:
        success = await strategy_svc.stop_strategy(strategy_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"策略停止失败: {strategy_name}",
            )

        logger.info(f"策略引擎已停止: {strategy_name}")

        return StrategyActionResponse(
            success=True,
            message=f"策略已停止: {strategy_name}",
            timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止策略失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止策略失败: {str(e)}",
        )
