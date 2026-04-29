"""账户API Schema定义

定义账户管理相关的请求/响应Pydantic模型，包括账户列表、详情、创建模拟账户、切换交易模式等。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 账户列表响应
# ---------------------------------------------------------------------------

class AccountListResponse(BaseModel):
    """账户列表响应Schema"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=200, description="每页记录数")
    total_pages: int = Field(..., ge=0, description="总页数")
    items: List["AccountDetailResponse"] = Field(default_factory=list, description="账户列表")


# ---------------------------------------------------------------------------
# 账户详情响应
# ---------------------------------------------------------------------------

class AccountDetailResponse(BaseModel):
    """账户详情响应Schema"""
    account_id: str = Field(..., description="账户唯一标识")
    broker: str = Field(..., description="券商/交易所名称")
    account_type: str = Field(..., description="账户类型: real / paper")
    total_value: float = Field(..., description="总资产")
    cash: float = Field(..., description="现金余额")
    market_value: float = Field(..., description="持仓市值")
    available_cash: float = Field(..., description="可用现金")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# 创建模拟账户请求
# ---------------------------------------------------------------------------

class CreatePaperAccountRequest(BaseModel):
    """创建模拟账户请求Schema"""
    account_id: str = Field(
        ..., min_length=1, max_length=64, description="账户唯一标识",
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    broker: str = Field(
        default="paper_broker",
        min_length=1,
        max_length=32,
        description="券商/交易所名称",
    )
    initial_cash: float = Field(
        default=1000000.0,
        gt=0,
        le=100_000_000_000,
        description="初始资金 (元)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "account_id": "paper_001",
                    "broker": "paper_broker",
                    "initial_cash": 1000000.0,
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 切换交易模式请求
# ---------------------------------------------------------------------------

class SwitchModeRequest(BaseModel):
    """切换交易模式请求Schema"""
    mode: str = Field(
        ...,
        description="目标交易模式: paper / live / backtest",
        pattern=r"^(paper|live|backtest)$",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"mode": "live"},
                {"mode": "paper"},
            ]
        }
    }


# ---------------------------------------------------------------------------
# 同步账户数据请求
# ---------------------------------------------------------------------------

class SyncAccountRequest(BaseModel):
    """同步账户数据请求Schema"""
    account_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="要同步的账户ID",
    )
    sync_positions: bool = Field(default=True, description="是否同步持仓数据")
    sync_orders: bool = Field(default=True, description="是否同步订单数据")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "account_id": "paper_001",
                    "sync_positions": True,
                    "sync_orders": True,
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 操作结果响应
# ---------------------------------------------------------------------------

class AccountActionResponse(BaseModel):
    """账户操作结果响应Schema"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(default="", description="操作结果描述")
    account_id: Optional[str] = Field(default=None, description="关联的账户ID")
    timestamp: Optional[datetime] = Field(default=None, description="操作时间")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "模拟账户创建成功",
                    "account_id": "paper_001",
                }
            ]
        }
    }


# 解决前向引用
AccountListResponse.model_rebuild()
