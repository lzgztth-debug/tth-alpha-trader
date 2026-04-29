"""账户模型模块

定义账户相关的数据类、枚举和Pydantic Schema。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class AccountType(str, Enum):
    """账户类型枚举"""
    REAL = "real"
    PAPER = "paper"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Account:
    """账户数据类

    Attributes:
        account_id:     账户唯一标识
        broker:         券商/交易所名称
        account_type:   账户类型 (real / paper)
        total_value:    总资产
        cash:           现金余额
        market_value:   持仓市值
        available_cash: 可用现金
        created_at:     创建时间
        updated_at:     更新时间
    """
    account_id: str
    broker: str
    account_type: AccountType
    total_value: float = 0.0
    cash: float = 0.0
    market_value: float = 0.0
    available_cash: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AccountCreate(BaseModel):
    """创建账户请求Schema"""
    account_id: str = Field(..., min_length=1, max_length=64, description="账户唯一标识")
    broker: str = Field(..., min_length=1, max_length=32, description="券商/交易所名称")
    account_type: AccountType = Field(default=AccountType.PAPER, description="账户类型")
    initial_cash: float = Field(default=1000000.0, gt=0, description="初始资金")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "account_id": "paper_001",
                    "broker": "paper_broker",
                    "account_type": "paper",
                    "initial_cash": 1000000.0,
                }
            ]
        }
    }


class AccountUpdate(BaseModel):
    """更新账户请求Schema"""
    total_value: Optional[float] = Field(default=None, ge=0, description="总资产")
    cash: Optional[float] = Field(default=None, ge=0, description="现金余额")
    market_value: Optional[float] = Field(default=None, ge=0, description="持仓市值")
    available_cash: Optional[float] = Field(default=None, ge=0, description="可用现金")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total_value": 1050000.0,
                    "cash": 500000.0,
                    "market_value": 550000.0,
                    "available_cash": 500000.0,
                }
            ]
        }
    }


class AccountResponse(BaseModel):
    """账户响应Schema"""
    account_id: str
    broker: str
    account_type: AccountType
    total_value: float
    cash: float
    market_value: float
    available_cash: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
