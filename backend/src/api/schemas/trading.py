"""交易API Schema定义

定义交易相关的请求/响应Pydantic模型，包括下单、撤单、订单查询、持仓查询、账户查询等。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.order import OrderSide, OrderStatus, OrderType


# ---------------------------------------------------------------------------
# 通用分页响应
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    """通用分页响应包装"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=200, description="每页记录数")
    total_pages: int = Field(..., ge=0, description="总页数")


# ---------------------------------------------------------------------------
# 下单请求
# ---------------------------------------------------------------------------

class OrderRequest(BaseModel):
    """下单请求Schema"""
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    side: OrderSide = Field(..., description="买卖方向: buy / sell")
    order_type: OrderType = Field(default=OrderType.MARKET, description="订单类型: market / limit")
    quantity: float = Field(..., gt=0, description="委托数量")
    price: Optional[float] = Field(default=None, ge=0, description="委托价格 (限价单必填)")
    account_id: Optional[str] = Field(default=None, max_length=64, description="所属账户ID")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "side": "buy",
                    "order_type": "limit",
                    "quantity": 100,
                    "price": 150.0,
                    "account_id": "paper_001",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# 撤单请求
# ---------------------------------------------------------------------------

class CancelOrderRequest(BaseModel):
    """撤单请求Schema"""
    reason: Optional[str] = Field(default=None, max_length=256, description="撤单原因")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"reason": "价格偏离预期"}
            ]
        }
    }


# ---------------------------------------------------------------------------
# 订单响应
# ---------------------------------------------------------------------------

class OrderResponse(BaseModel):
    """订单响应Schema"""
    order_id: str = Field(..., description="订单唯一标识")
    symbol: str = Field(..., description="标的代码")
    side: OrderSide = Field(..., description="买卖方向")
    order_type: OrderType = Field(..., description="订单类型")
    quantity: float = Field(..., description="委托数量")
    price: Optional[float] = Field(default=None, description="委托价格")
    status: OrderStatus = Field(..., description="订单状态")
    filled_quantity: float = Field(default=0.0, description="已成交数量")
    filled_price: float = Field(default=0.0, description="成交均价")
    fee: float = Field(default=0.0, description="手续费")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    filled_at: Optional[datetime] = Field(default=None, description="成交时间")
    account_id: Optional[str] = Field(default=None, description="所属账户ID")
    broker: Optional[str] = Field(default=None, description="券商名称")

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """订单列表响应Schema"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=200, description="每页记录数")
    total_pages: int = Field(..., ge=0, description="总页数")
    items: List[OrderResponse] = Field(default_factory=list, description="订单列表")


# ---------------------------------------------------------------------------
# 持仓响应
# ---------------------------------------------------------------------------

class PositionResponse(BaseModel):
    """持仓响应Schema"""
    symbol: str = Field(..., description="标的代码")
    quantity: float = Field(..., description="持仓数量")
    avg_cost: float = Field(..., description="平均成本")
    current_price: float = Field(..., description="当前价格")
    market_value: float = Field(..., description="持仓市值")
    unrealized_pnl: float = Field(..., description="未实现盈亏(金额)")
    unrealized_pnl_pct: float = Field(..., description="未实现盈亏(百分比)")
    account_id: Optional[str] = Field(default=None, description="所属账户ID")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    model_config = {"from_attributes": True}


class PositionListResponse(BaseModel):
    """持仓列表响应Schema"""
    total: int = Field(..., ge=0, description="总记录数")
    items: List[PositionResponse] = Field(default_factory=list, description="持仓列表")


# ---------------------------------------------------------------------------
# 账户查询响应 (交易API中使用)
# ---------------------------------------------------------------------------

class AccountResponse(BaseModel):
    """账户信息响应Schema (交易API中使用)"""
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
# 操作结果响应
# ---------------------------------------------------------------------------

class ActionResponse(BaseModel):
    """通用操作结果响应Schema"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(default="", description="操作结果描述")
    order_id: Optional[str] = Field(default=None, description="关联的订单ID")
    timestamp: Optional[datetime] = Field(default=None, description="操作时间")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "订单已提交",
                    "order_id": "ORD_20240101_001",
                }
            ]
        }
    }
