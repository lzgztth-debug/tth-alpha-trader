"""持仓模型模块

定义持仓相关的数据类和Pydantic Schema。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """持仓数据类

    Attributes:
        symbol:             标的代码
        quantity:           持仓数量
        avg_cost:           平均成本
        current_price:      当前价格
        market_value:       持仓市值
        unrealized_pnl:     未实现盈亏 (金额)
        unrealized_pnl_pct: 未实现盈亏 (百分比)
        account_id:         所属账户ID
        created_at:         创建时间
        updated_at:         更新时间
    """
    symbol: str
    quantity: float
    avg_cost: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    account_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class PositionCreate(BaseModel):
    """创建持仓请求Schema"""
    account_id: str = Field(..., min_length=1, max_length=64, description="所属账户ID")
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    quantity: float = Field(..., gt=0, description="持仓数量")
    avg_cost: float = Field(default=0.0, ge=0, description="平均成本")
    current_price: float = Field(default=0.0, ge=0, description="当前价格")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "account_id": "paper_001",
                    "symbol": "AAPL",
                    "quantity": 100,
                    "avg_cost": 150.0,
                    "current_price": 155.0,
                }
            ]
        }
    }


class PositionUpdate(BaseModel):
    """更新持仓请求Schema"""
    quantity: Optional[float] = Field(default=None, ge=0, description="持仓数量")
    avg_cost: Optional[float] = Field(default=None, ge=0, description="平均成本")
    current_price: Optional[float] = Field(default=None, ge=0, description="当前价格")
    market_value: Optional[float] = Field(default=None, ge=0, description="持仓市值")
    unrealized_pnl: Optional[float] = Field(default=None, description="未实现盈亏")
    unrealized_pnl_pct: Optional[float] = Field(default=None, description="未实现盈亏百分比")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "current_price": 160.0,
                    "market_value": 16000.0,
                    "unrealized_pnl": 1000.0,
                    "unrealized_pnl_pct": 0.0667,
                }
            ]
        }
    }


class PositionResponse(BaseModel):
    """持仓响应Schema"""
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    account_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
