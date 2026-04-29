# src/adapters/brokers/base.py
# 券商适配器基类 - 定义统一的券商接口规范

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable, Awaitable

from src.models.account import Account
from src.models.position import Position
from src.models.order import Order, OrderSide, OrderType


class BrokerError(Exception):
    """券商适配器基础异常"""
    def __init__(self, message: str, broker: str = "", code: str = ""):
        self.broker = broker
        self.code = code
        super().__init__(f"[{broker}] {message}" if broker else message)


class BrokerConnectionError(BrokerError):
    """券商连接异常"""
    def __init__(self, message: str, broker: str = ""):
        super().__init__(message, broker=broker, code="CONNECTION_ERROR")


class BrokerOrderError(BrokerError):
    """券商订单异常"""
    def __init__(self, message: str, broker: str = "", order_id: str = ""):
        self.order_id = order_id
        super().__init__(message, broker=broker, code="ORDER_ERROR")


class BaseBrokerAdapter(ABC):
    """
    券商适配器抽象基类

    所有券商适配器必须继承此类并实现所有抽象方法。
    提供统一的券商API接口规范，支持异步操作。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化券商适配器

        Args:
            config: 券商配置字典，包含认证信息、连接参数等
        """
        self.config = config
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

    @abstractmethod
    async def connect(self) -> bool:
        """
        连接券商服务

        Returns:
            bool: 连接是否成功

        Raises:
            BrokerConnectionError: 连接失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        """
        断开券商连接

        Raises:
            BrokerConnectionError: 断开连接失败时抛出
        """
        raise NotImplementedError

    async def reconnect(self, max_retries: int = 3, retry_interval: float = 5.0) -> bool:
        """
        重新连接券商服务（带重试机制）

        Args:
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）

        Returns:
            bool: 重连是否成功
        """
        for attempt in range(1, max_retries + 1):
            try:
                await self.disconnect()
                await asyncio.sleep(retry_interval)
                result = await self.connect()
                if result:
                    return True
            except Exception as e:
                if attempt == max_retries:
                    raise BrokerConnectionError(
                        f"重连失败，已尝试 {max_retries} 次: {e}",
                        broker=self.name
                    )
                await asyncio.sleep(retry_interval * attempt)
        return False

    # ==================== 账户管理 ====================

    @abstractmethod
    async def get_account(self) -> Account:
        """
        获取账户信息

        Returns:
            Account: 账户信息对象

        Raises:
            BrokerError: 获取账户信息失败时抛出
        """
        raise NotImplementedError

    # ==================== 持仓管理 ====================

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        获取当前持仓列表

        Returns:
            List[Position]: 持仓列表

        Raises:
            BrokerError: 获取持仓失败时抛出
        """
        raise NotImplementedError

    # ==================== 订单管理 ====================

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        **kwargs
    ) -> Order:
        """
        下单

        Args:
            symbol: 标的代码（如 AAPL, 00700.HK, BTC/USDT）
            side: 买卖方向
            quantity: 数量
            order_type: 订单类型（市价/限价）
            price: 限价价格（限价单必填）
            **kwargs: 其他参数

        Returns:
            Order: 订单对象

        Raises:
            BrokerOrderError: 下单失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        撤销订单

        Args:
            order_id: 订单ID

        Returns:
            bool: 撤单是否成功

        Raises:
            BrokerOrderError: 撤单失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """
        查询单个订单详情

        Args:
            order_id: 订单ID

        Returns:
            Order: 订单对象

        Raises:
            BrokerError: 查询订单失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs
    ) -> List[Order]:
        """
        查询订单列表

        Args:
            status: 订单状态筛选
            symbol: 标的代码筛选
            **kwargs: 其他筛选参数

        Returns:
            List[Order]: 订单列表

        Raises:
            BrokerError: 查询订单失败时抛出
        """
        raise NotImplementedError

    # ==================== 行情管理 ====================

    @abstractmethod
    async def subscribe_quote(
        self,
        symbols: List[str],
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """
        订阅实时行情

        Args:
            symbols: 标的代码列表
            callback: 行情回调函数，接收行情数据字典

        Raises:
            BrokerError: 订阅行情失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def unsubscribe_quote(self, symbols: List[str]) -> None:
        """
        取消订阅行情

        Args:
            symbols: 标的代码列表

        Raises:
            BrokerError: 取消订阅失败时抛出
        """
        raise NotImplementedError

    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        获取单个标的实时行情

        Args:
            symbol: 标的代码

        Returns:
            Dict[str, Any]: 行情数据字典

        Raises:
            BrokerError: 获取行情失败时抛出
        """
        raise NotImplementedError

    # ==================== 工具方法 ====================

    def _ensure_connected(self) -> None:
        """确保已连接，未连接则抛出异常"""
        if not self._connected:
            raise BrokerConnectionError(
                "未连接到券商服务，请先调用 connect()",
                broker=self.name
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
