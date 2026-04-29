"""订单模型模块

定义订单相关的数据类、枚举和Pydantic Schema。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """订单类型枚举"""
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """订单状态枚举"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL_FILLED = "partial_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """订单数据类

    Attributes:
        order_id:       订单唯一标识
        symbol:         标的代码
        side:           买卖方向
        order_type:     订单类型
        quantity:       委托数量
        price:          委托价格 (限价单有效)
        status:         订单状态
        filled_quantity: 已成交数量
        filled_price:   成交均价
        fee:            手续费
        created_at:     创建时间
        filled_at:      成交时间
        account_id:     所属账户ID
        broker:         券商名称
    """
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    account_id: Optional[str] = None
    broker: Optional[str] = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class OrderCreate(BaseModel):
    """创建订单请求Schema"""
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    side: OrderSide = Field(..., description="买卖方向")
    order_type: OrderType = Field(default=OrderType.MARKET, description="订单类型")
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


class OrderUpdate(BaseModel):
    """更新订单请求Schema"""
    status: Optional[OrderStatus] = Field(default=None, description="订单状态")
    filled_quantity: Optional[float] = Field(default=None, ge=0, description="已成交数量")
    filled_price: Optional[float] = Field(default=None, ge=0, description="成交均价")
    fee: Optional[float] = Field(default=None, ge=0, description="手续费")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "filled",
                    "filled_quantity": 100,
                    "filled_price": 150.0,
                    "fee": 4.5,
                }
            ]
        }
    }


class OrderResponse(BaseModel):
    """订单响应Schema"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    status: OrderStatus
    filled_quantity: float
    filled_price: float
    fee: float
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    account_id: Optional[str] = None
    broker: Optional[str] = None

    model_config = {"from_attributes": True}
