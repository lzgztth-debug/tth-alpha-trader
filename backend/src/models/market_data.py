"""行情数据模型模块

定义行情相关的数据类和Pydantic Schema。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Quote:
    """实时行情数据类

    Attributes:
        symbol:     标的代码
        open:       开盘价
        high:       最高价
        low:        最低价
        close:      最新价/收盘价
        volume:     成交量
        timestamp:  行情时间戳
    """
    symbol: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass
class Kline:
    """K线数据类

    Attributes:
        symbol:     标的代码
        interval:   K线周期 (如 1m, 5m, 15m, 1h, 1d)
        open:       开盘价
        high:       最高价
        low:        最低价
        close:      收盘价
        volume:     成交量
        timestamp:  K线起始时间戳
    """
    symbol: str
    interval: str
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    timestamp: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class QuoteResponse(BaseModel):
    """行情响应Schema"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KlineResponse(BaseModel):
    """K线响应Schema"""
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketSnapshotCreate(BaseModel):
    """行情快照创建Schema"""
    symbol: str = Field(..., min_length=1, max_length=32, description="标的代码")
    open: float = Field(default=0.0, ge=0, description="开盘价")
    high: float = Field(default=0.0, ge=0, description="最高价")
    low: float = Field(default=0.0, ge=0, description="最低价")
    close: float = Field(default=0.0, ge=0, description="收盘价/最新价")
    volume: float = Field(default=0.0, ge=0, description="成交量")
    timestamp: Optional[datetime] = Field(default=None, description="行情时间戳")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "open": 148.0,
                    "high": 152.0,
                    "low": 147.5,
                    "close": 151.0,
                    "volume": 1000000,
                }
            ]
        }
    }
