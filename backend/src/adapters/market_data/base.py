# src/adapters/market_data/base.py
# 行情适配器基类 - 定义统一的行情数据接口规范

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable, Awaitable

from src.models.market_data import Quote, Kline


class MarketDataError(Exception):
    """行情适配器基础异常"""
    def __init__(self, message: str, source: str = "", code: str = ""):
        self.source = source
        self.code = code
        super().__init__(f"[{source}] {message}" if source else message)


class MarketDataConnectionError(MarketDataError):
    """行情连接异常"""
    def __init__(self, message: str, source: str = ""):
        super().__init__(message, source=source, code="CONNECTION_ERROR")


class BaseMarketDataAdapter(ABC):
    """
    行情适配器抽象基类

    所有行情数据适配器必须继承此类并实现所有抽象方法。
    提供统一的行情数据接口规范。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化行情适配器

        Args:
            config: 配置字典
        """
        self.config = config or {}
        self._connected = False
        self._quote_callbacks: Dict[str, List[Callable]] = {}

    @property
    def connected(self) -> bool:
        """返回当前连接状态"""
        return self._connected

    @property
    def name(self) -> str:
        """返回适配器名称"""
        return self.__class__.__name__

    # ==================== 连接管理 ====================

    async def connect(self) -> bool:
        """
        连接行情数据源（可选，部分数据源不需要显式连接）

        Returns:
            bool: 连接是否成功
        """
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """断开行情数据源连接"""
        self._connected = False

    # ==================== 行情数据 ====================

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """
        获取单个标的实时行情

        Args:
            symbol: 标的代码

        Returns:
            Quote: 行情数据对象

        Raises:
            MarketDataError: 获取行情失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        """
        批量获取标的行情

        Args:
            symbols: 标的代码列表

        Returns:
            List[Quote]: 行情数据列表

        Raises:
            MarketDataError: 获取行情失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Kline]:
        """
        获取K线数据

        Args:
            symbol: 标的代码
            interval: K线周期（如 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M）
            limit: 返回数据条数
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）

        Returns:
            List[Kline]: K线数据列表

        Raises:
            MarketDataError: 获取K线数据失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def subscribe_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], Awaitable[None]]
    ) -> None:
        """
        订阅实时行情

        Args:
            symbols: 标的代码列表
            callback: 行情回调函数

        Raises:
            MarketDataError: 订阅失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe_quotes(self, symbols: List[str]) -> None:
        """
        取消订阅行情

        Args:
            symbols: 标的代码列表

        Raises:
            MarketDataError: 取消订阅失败时抛出
        """
        raise NotImplementedError

    # ==================== 工具方法 ====================

    def _ensure_connected(self) -> None:
        """确保已连接"""
        if not self._connected:
            raise MarketDataConnectionError(
                "未连接到行情数据源",
                source=self.name
            )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()

    def __repr__(self) -> str:
        return f"<{self.name} connected={self._connected}>"
