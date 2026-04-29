"""配置管理 API 路由

提供配置管理相关的 API 端点：
- GET    /api/v1/config/prompts        - 获取 Prompt 列表
- POST   /api/v1/config/prompts        - 创建 Prompt
- PUT    /api/v1/config/prompts/{name} - 更新 Prompt
- DELETE /api/v1/config/prompts/{name} - 删除 Prompt
- GET    /api/v1/config/risk-rules     - 获取风控规则
- PUT    /api/v1/config/risk-rules     - 更新风控规则
- GET    /api/v1/config/trading-mode   - 获取交易模式
- PUT    /api/v1/config/trading-mode   - 更新交易模式
- GET    /api/v1/config/ai-cost        - 获取 AI 调用成本统计
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/config", tags=["配置管理"])


# ---------------------------------------------------------------------------
# Schema 定义
# ---------------------------------------------------------------------------

class PromptCreateRequest(BaseModel):
    """创建 Prompt 请求"""
    name: str = Field(..., min_length=1, max_length=64, description="Prompt名称")
    category: str = Field(..., min_length=1, max_length=32, description="分类")
    content: str = Field(..., min_length=1, description="Prompt内容")
    variables: Optional[List[str]] = Field(default=None, description="变量列表")
    is_active: bool = Field(default=True, description="是否启用")


class PromptUpdateRequest(BaseModel):
    """更新 Prompt 请求"""
    category: Optional[str] = Field(default=None, max_length=32, description="分类")
    content: Optional[str] = Field(default=None, min_length=1, description="Prompt内容")
    variables: Optional[List[str]] = Field(default=None, description="变量列表")
    is_active: Optional[bool] = Field(default=None, description="是否启用")


class PromptResponse(BaseModel):
    """Prompt 响应"""
    name: str
    category: str
    content: str
    variables: List[str] = Field(default_factory=list)
    version: int = 1
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PromptListResponse(BaseModel):
    """Prompt 列表响应"""
    total: int = 0
    items: List[PromptResponse] = Field(default_factory=list)


class RiskRulesResponse(BaseModel):
    """风控规则响应"""
    rules: Dict[str, Any] = Field(default_factory=dict)


class RiskRulesUpdateRequest(BaseModel):
    """风控规则更新请求"""
    rules: Dict[str, Any] = Field(..., description="风控规则键值对")


class TradingModeResponse(BaseModel):
    """交易模式响应"""
    mode: str
    max_position_size: float = 0.0
    max_daily_trades: int = 0
    max_drawdown_pct: float = 0.0
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    risk_per_trade_pct: float = 0.0


class TradingModeUpdateRequest(BaseModel):
    """交易模式更新请求"""
    mode: Optional[str] = Field(default=None, description="交易模式: paper/live/backtest")
    max_position_size: Optional[float] = Field(default=None, gt=0)
    max_daily_trades: Optional[int] = Field(default=None, gt=0)
    max_drawdown_pct: Optional[float] = Field(default=None, ge=0, le=100)
    stop_loss_pct: Optional[float] = Field(default=None, ge=0, le=100)
    take_profit_pct: Optional[float] = Field(default=None, ge=0, le=100)
    risk_per_trade_pct: Optional[float] = Field(default=None, ge=0, le=100)


class AICostResponse(BaseModel):
    """AI 成本统计响应"""
    total_cost: float = 0.0
    total_tokens: int = 0
    total_calls: int = 0
    by_provider: Dict[str, Any] = Field(default_factory=dict)
    by_day: List[Dict[str, Any]] = Field(default_factory=list)


class ActionResponse(BaseModel):
    """通用操作响应"""
    success: bool
    message: str = ""
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _get_strategy_service(request):
    """获取 StrategyService 实例。"""
    from src.api.routes.strategy import get_strategy_service
    return get_strategy_service()


# ---------------------------------------------------------------------------
# Prompt CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/prompts",
    response_model=PromptListResponse,
    summary="获取 Prompt 列表",
    description="获取所有 Prompt 模板列表。",
)
async def list_prompts(
    category: Optional[str] = Query(default=None, description="按分类筛选"),
) -> PromptListResponse:
    """获取 Prompt 列表。"""
    try:
        from src.services.strategy_service import StrategyService
        svc = StrategyService()
        templates = await svc.get_prompt_templates(category=category, active_only=False)

        items = [
            PromptResponse(
                name=t.name,
                category=t.category,
                content=t.content,
                variables=t.variables,
                version=t.version,
                is_active=t.is_active,
                created_at=t.created_at.isoformat() if t.created_at else None,
                updated_at=t.updated_at.isoformat() if t.updated_at else None,
            )
            for t in templates
        ]

        return PromptListResponse(total=len(items), items=items)

    except Exception as e:
        logger.error(f"获取 Prompt 列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 Prompt 列表失败: {str(e)}",
        )


@router.post(
    "/prompts",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Prompt",
    description="创建新的 Prompt 模板。",
)
async def create_prompt(
    req: PromptCreateRequest,
) -> PromptResponse:
    """创建 Prompt。"""
    try:
        from src.services.strategy_service import StrategyService
        svc = StrategyService()
        template = await svc.save_prompt_template(
            name=req.name,
            category=req.category,
            content=req.content,
            variables=req.variables,
            is_active=req.is_active,
        )

        return PromptResponse(
            name=template.name,
            category=template.category,
            content=template.content,
            variables=template.variables,
            version=template.version,
            is_active=template.is_active,
            created_at=template.created_at.isoformat() if template.created_at else None,
            updated_at=template.updated_at.isoformat() if template.updated_at else None,
        )

    except Exception as e:
        logger.error(f"创建 Prompt 失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建 Prompt 失败: {str(e)}",
        )


@router.put(
    "/prompts/{prompt_name}",
    response_model=PromptResponse,
    summary="更新 Prompt",
    description="更新指定名称的 Prompt 模板。",
)
async def update_prompt(
    prompt_name: str,
    req: PromptUpdateRequest,
) -> PromptResponse:
    """更新 Prompt。"""
    try:
        from src.services.strategy_service import StrategyService
        svc = StrategyService()
        existing = await svc.get_prompt_template(prompt_name)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt 不存在: {prompt_name}",
            )

        updates = req.model_dump(exclude_unset=True)
        if req.content is not None:
            updates["content"] = req.content

        template = await svc.save_prompt_template(
            name=prompt_name,
            category=updates.get("category", existing.category),
            content=updates.get("content", existing.content),
            variables=updates.get("variables", existing.variables),
            is_active=updates.get("is_active", existing.is_active),
        )

        return PromptResponse(
            name=template.name,
            category=template.category,
            content=template.content,
            variables=template.variables,
            version=template.version,
            is_active=template.is_active,
            created_at=template.created_at.isoformat() if template.created_at else None,
            updated_at=template.updated_at.isoformat() if template.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Prompt 失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新 Prompt 失败: {str(e)}",
        )


@router.delete(
    "/prompts/{prompt_name}",
    response_model=ActionResponse,
    summary="删除 Prompt",
    description="删除指定名称的 Prompt 模板。",
)
async def delete_prompt(
    prompt_name: str,
) -> ActionResponse:
    """删除 Prompt。"""
    try:
        from src.services.strategy_service import StrategyService
        svc = StrategyService()
        success = await svc.delete_prompt_template(prompt_name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prompt 不存在: {prompt_name}",
            )

        return ActionResponse(
            success=True,
            message=f"Prompt 已删除: {prompt_name}",
            timestamp=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Prompt 失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除 Prompt 失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# 风控规则
# ---------------------------------------------------------------------------

@router.get(
    "/risk-rules",
    response_model=RiskRulesResponse,
    summary="获取风控规则",
    description="获取当前风控规则配置。",
)
async def get_risk_rules() -> RiskRulesResponse:
    """获取风控规则。"""
    from src.utils.config import get_settings
    settings = get_settings()
    trading = settings.trading

    rules = {
        "max_position_size": trading.max_position_size,
        "max_daily_trades": trading.max_daily_trades,
        "max_drawdown_pct": trading.max_drawdown_pct,
        "stop_loss_pct": trading.stop_loss_pct,
        "take_profit_pct": trading.take_profit_pct,
        "risk_per_trade_pct": trading.risk_per_trade_pct,
        "allowed_symbols": trading.allowed_symbols,
        "trading_hours_start": trading.trading_hours_start,
        "trading_hours_end": trading.trading_hours_end,
    }
    return RiskRulesResponse(rules=rules)


@router.put(
    "/risk-rules",
    response_model=ActionResponse,
    summary="更新风控规则",
    description="更新风控规则配置。",
)
async def update_risk_rules(
    req: RiskRulesUpdateRequest,
) -> ActionResponse:
    """更新风控规则。"""
    try:
        from src.utils.config import get_settings, reload_settings
        settings = get_settings()
        trading = settings.trading

        for key, value in req.rules.items():
            if hasattr(trading, key):
                setattr(trading, key, value)

        return ActionResponse(
            success=True,
            message="风控规则已更新",
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"更新风控规则失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新风控规则失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# 交易模式
# ---------------------------------------------------------------------------

@router.get(
    "/trading-mode",
    response_model=TradingModeResponse,
    summary="获取交易模式",
    description="获取当前交易模式配置。",
)
async def get_trading_mode() -> TradingModeResponse:
    """获取交易模式。"""
    from src.utils.config import get_settings
    settings = get_settings()
    trading = settings.trading

    return TradingModeResponse(
        mode=trading.mode,
        max_position_size=trading.max_position_size,
        max_daily_trades=trading.max_daily_trades,
        max_drawdown_pct=trading.max_drawdown_pct,
        stop_loss_pct=trading.stop_loss_pct,
        take_profit_pct=trading.take_profit_pct,
        risk_per_trade_pct=trading.risk_per_trade_pct,
    )


@router.put(
    "/trading-mode",
    response_model=ActionResponse,
    summary="更新交易模式",
    description="更新交易模式配置。",
)
async def update_trading_mode(
    req: TradingModeUpdateRequest,
) -> ActionResponse:
    """更新交易模式。"""
    try:
        from src.utils.config import get_settings
        settings = get_settings()
        trading = settings.trading

        updates = req.model_dump(exclude_unset=True)
        for key, value in updates.items():
            if hasattr(trading, key):
                setattr(trading, key, value)

        return ActionResponse(
            success=True,
            message="交易模式已更新",
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"更新交易模式失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新交易模式失败: {str(e)}",
        )


# ---------------------------------------------------------------------------
# AI 成本统计
# ---------------------------------------------------------------------------

@router.get(
    "/ai-cost",
    response_model=AICostResponse,
    summary="获取 AI 成本统计",
    description="获取 AI 模型调用的成本统计信息。",
)
async def get_ai_cost(
    provider: Optional[str] = Query(default=None, description="按提供商筛选"),
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
) -> AICostResponse:
    """获取 AI 成本统计。"""
    try:
        from src.services.cost_service import CostService
        svc = CostService()

        summary = svc.get_summary()

        by_provider = {}
        if provider:
            by_provider[provider] = svc.get_by_provider(provider)
        else:
            for p in summary.get("providers", []):
                by_provider[p] = svc.get_by_provider(p)

        by_day = svc.get_by_day(days=days)

        return AICostResponse(
            total_cost=summary.get("total_cost", 0.0),
            total_tokens=summary.get("total_tokens", 0),
            total_calls=summary.get("total_calls", 0),
            by_provider=by_provider,
            by_day=by_day,
        )

    except Exception as e:
        logger.error(f"获取 AI 成本统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 AI 成本统计失败: {str(e)}",
        )
