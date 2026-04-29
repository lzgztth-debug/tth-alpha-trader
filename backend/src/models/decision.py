"""决策模型模块

定义AI决策相关的数据类、枚举和Pydantic Schema。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class DecisionAction(str, Enum):
    """决策动作枚举"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """AI决策数据类

    Attributes:
        decision_id:       决策唯一标识
        timestamp:         决策时间
        model:             使用的模型名称
        provider:          模型供应商
        action:            决策动作 (buy / sell / hold)
        symbol:            标的代码
        quantity:          建议数量
        price:             建议价格
        confidence:        决策置信度 (0.0 ~ 1.0)
        reasoning:         决策理由
        raw_response:      模型原始输出
        executed:          是否已执行
        execution_result:  执行结果描述
        latency_ms:        模型推理延迟 (毫秒)
        prompt:            发送给模型的Prompt
        market_context:    决策时的市场快照 (JSON字符串)
        account_context:   决策时的账户快照 (JSON字符串)
    """
    decision_id: str
    timestamp: datetime
    model: str
    provider: str
    action: DecisionAction
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
    raw_response: str = ""
    executed: bool = False
    execution_result: Optional[str] = None
    latency_ms: Optional[int] = None
    prompt: Optional[str] = None
    market_context: Optional[str] = None
    account_context: Optional[str] = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class DecisionCreate(BaseModel):
    """创建决策日志请求Schema"""
    model: str = Field(..., min_length=1, max_length=64, description="模型名称")
    provider: str = Field(..., min_length=1, max_length=32, description="模型供应商")
    action: DecisionAction = Field(..., description="决策动作")
    symbol: Optional[str] = Field(default=None, max_length=32, description="标的代码")
    quantity: Optional[float] = Field(default=None, ge=0, description="建议数量")
    price: Optional[float] = Field(default=None, ge=0, description="建议价格")
    confidence: float = Field(default=0.0, ge=0, le=1, description="决策置信度")
    reasoning: str = Field(default="", description="决策理由")
    raw_response: str = Field(default="", description="模型原始输出")
    executed: bool = Field(default=False, description="是否已执行")
    execution_result: Optional[str] = Field(default=None, description="执行结果")
    latency_ms: Optional[int] = Field(default=None, ge=0, description="推理延迟(ms)")
    prompt: Optional[str] = Field(default=None, description="Prompt内容")
    market_context: Optional[str] = Field(default=None, description="市场快照JSON")
    account_context: Optional[str] = Field(default=None, description="账户快照JSON")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "gpt-4o",
                    "provider": "openai",
                    "action": "buy",
                    "symbol": "AAPL",
                    "quantity": 100,
                    "price": 150.0,
                    "confidence": 0.85,
                    "reasoning": "技术指标显示上升趋势",
                    "raw_response": '{"action": "buy", "symbol": "AAPL", ...}',
                }
            ]
        }
    }


class DecisionResponse(BaseModel):
    """决策响应Schema"""
    decision_id: str
    timestamp: datetime
    model: str
    provider: str
    action: DecisionAction
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    confidence: float
    reasoning: str
    raw_response: str
    executed: bool
    execution_result: Optional[str] = None
    latency_ms: Optional[int] = None

    model_config = {"from_attributes": True}
