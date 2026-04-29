"""AI 决策 API 路由

提供 AI 模型决策相关的 API 端点：
- POST   /api/v1/ai/decide          - 单模型决策
- POST   /api/v1/ai/decide/multi     - 多模型投票决策
- POST   /api/v1/ai/decide/stream    - SSE 流式多模型决策
- GET    /api/v1/ai/models           - 列出已注册模型
- GET    /api/v1/ai/providers        - 列出支持的提供商
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/ai", tags=["AI决策"])


# ---------------------------------------------------------------------------
# Schema 定义
# ---------------------------------------------------------------------------

class DecideRequest(BaseModel):
    """单模型决策请求"""
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    account_id: Optional[str] = Field(default=None, description="账户ID")
    model_name: Optional[str] = Field(default=None, description="模型名称")
    template_name: Optional[str] = Field(default=None, description="Prompt模板名称")
    extra_variables: Optional[Dict[str, Any]] = Field(default=None, description="额外变量")
    system_prompt: Optional[str] = Field(default=None, description="系统提示词")


class DecideMultiRequest(BaseModel):
    """多模型投票决策请求"""
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    account_id: Optional[str] = Field(default=None, description="账户ID")
    model_names: Optional[List[str]] = Field(default=None, description="参与决策的模型名称列表")
    template_name: Optional[str] = Field(default=None, description="Prompt模板名称")
    extra_variables: Optional[Dict[str, Any]] = Field(default=None, description="额外变量")
    voting_strategy: str = Field(default="majority", description="投票策略: majority/confidence/unanimous")


class DecideResponse(BaseModel):
    """决策响应"""
    success: bool = Field(..., description="是否成功")
    decision: Optional[Dict[str, Any]] = Field(default=None, description="决策结果")
    error: Optional[str] = Field(default=None, description="错误信息")


class ModelInfoResponse(BaseModel):
    """模型信息响应"""
    models: List[Dict[str, Any]] = Field(default_factory=list, description="模型列表")


class ProviderInfoResponse(BaseModel):
    """提供商信息响应"""
    providers: List[Dict[str, Any]] = Field(default_factory=list, description="提供商列表")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _get_agent_engine(request: Request):
    """从 app.state 获取 AIAgentEngine 实例。"""
    engine = getattr(request.app.state, "agent_engine", None)
    if engine is None:
        return None
    return engine


# ---------------------------------------------------------------------------
# POST /api/v1/ai/decide - 单模型决策
# ---------------------------------------------------------------------------

@router.post(
    "/decide",
    response_model=DecideResponse,
    summary="单模型决策",
    description="使用单个 AI 模型进行交易决策。",
)
async def decide(
    req: DecideRequest,
    request: Request,
) -> DecideResponse:
    """单模型决策。"""
    engine = _get_agent_engine(request)
    if engine is None:
        return DecideResponse(success=False, error="AI Agent 引擎未初始化")

    try:
        decision = await engine.make_decision(
            symbol=req.symbol,
            account_id=req.account_id,
            model_name=req.model_name,
            template_name=req.template_name,
            extra_variables=req.extra_variables,
            system_prompt=req.system_prompt,
        )

        return DecideResponse(
            success=True,
            decision={
                "decision_id": decision.decision_id,
                "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
                "model": decision.model,
                "provider": decision.provider,
                "action": decision.action.value if decision.action else None,
                "symbol": decision.symbol,
                "quantity": decision.quantity,
                "price": decision.price,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
                "latency_ms": decision.latency_ms,
            },
        )

    except Exception as e:
        logger.error(f"单模型决策失败: {e}")
        return DecideResponse(success=False, error=str(e))


# ---------------------------------------------------------------------------
# POST /api/v1/ai/decide/multi - 多模型投票决策
# ---------------------------------------------------------------------------

@router.post(
    "/decide/multi",
    response_model=DecideResponse,
    summary="多模型投票决策",
    description="使用多个 AI 模型并行决策，通过投票机制得出最终决策。",
)
async def decide_multi(
    req: DecideMultiRequest,
    request: Request,
) -> DecideResponse:
    """多模型投票决策。"""
    engine = _get_agent_engine(request)
    if engine is None:
        return DecideResponse(success=False, error="AI Agent 引擎未初始化")

    try:
        decision = await engine.make_decision_multi_model(
            symbol=req.symbol,
            account_id=req.account_id,
            model_names=req.model_names,
            template_name=req.template_name,
            extra_variables=req.extra_variables,
            voting_strategy=req.voting_strategy,
        )

        return DecideResponse(
            success=True,
            decision={
                "decision_id": decision.decision_id,
                "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
                "model": decision.model,
                "provider": decision.provider,
                "action": decision.action.value if decision.action else None,
                "symbol": decision.symbol,
                "quantity": decision.quantity,
                "price": decision.price,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
                "raw_response": decision.raw_response,
            },
        )

    except Exception as e:
        logger.error(f"多模型决策失败: {e}")
        return DecideResponse(success=False, error=str(e))


# ---------------------------------------------------------------------------
# POST /api/v1/ai/decide/stream - SSE 流式多模型决策
# ---------------------------------------------------------------------------

@router.post(
    "/decide/stream",
    summary="SSE 流式多模型决策",
    description="使用 SSE 流式返回多模型决策的实时进度。",
)
async def decide_stream(
    req: DecideMultiRequest,
    request: Request,
) -> StreamingResponse:
    """SSE 流式多模型决策。"""
    engine = _get_agent_engine(request)
    if engine is None:
        async def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI Agent 引擎未初始化'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'start', 'symbol': req.symbol}, ensure_ascii=False)}\n\n"

            decision = await engine.make_decision_multi_model(
                symbol=req.symbol,
                account_id=req.account_id,
                model_names=req.model_names,
                template_name=req.template_name,
                extra_variables=req.extra_variables,
                voting_strategy=req.voting_strategy,
            )

            result = {
                "type": "result",
                "decision_id": decision.decision_id,
                "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
                "model": decision.model,
                "provider": decision.provider,
                "action": decision.action.value if decision.action else None,
                "symbol": decision.symbol,
                "quantity": decision.quantity,
                "price": decision.price,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
            }
            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"SSE 流式决策失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /api/v1/ai/models - 列出已注册模型
# ---------------------------------------------------------------------------

@router.get(
    "/models",
    response_model=ModelInfoResponse,
    summary="列出已注册模型",
    description="列出所有已注册的 AI 模型及其状态。",
)
async def list_models(
    request: Request,
) -> ModelInfoResponse:
    """列出已注册模型。"""
    engine = _get_agent_engine(request)
    if engine is None:
        return ModelInfoResponse(models=[])

    models = engine.list_models()
    return ModelInfoResponse(models=models)


# ---------------------------------------------------------------------------
# GET /api/v1/ai/providers - 列出支持的提供商
# ---------------------------------------------------------------------------

@router.get(
    "/providers",
    response_model=ProviderInfoResponse,
    summary="列出支持的提供商",
    description="列出所有支持的 AI 模型提供商。",
)
async def list_providers() -> ProviderInfoResponse:
    """列出支持的提供商。"""
    from src.adapters.ai_models.base import ModelProvider

    providers = [
        {
            "name": p.value,
            "display_name": p.name,
        }
        for p in ModelProvider
    ]
    return ProviderInfoResponse(providers=providers)
