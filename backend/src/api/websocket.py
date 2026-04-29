"""WebSocket 管理器

提供 WebSocket 连接管理功能，支持实时推送交易决策、市场数据等。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class WebSocketManager:
    """WebSocket 连接管理器

    管理 WebSocket 连接的生命周期，支持按频道分组广播消息。

    Usage::

        manager = WebSocketManager()
        await manager.connect(websocket, "decisions")
        await manager.broadcast("decisions", {"action": "buy", "symbol": "AAPL"})
        await manager.disconnect(websocket, "decisions")
    """

    def __init__(self) -> None:
        # {channel: {websocket: ...}}
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

        logger.info("WebSocketManager 已创建")

    async def connect(
        self,
        websocket: WebSocket,
        channel: str = "default",
    ) -> None:
        """接受 WebSocket 连接并加入频道。

        Args:
            websocket: WebSocket 连接实例。
            channel:   频道名称。
        """
        await websocket.accept()

        async with self._lock:
            if channel not in self._connections:
                self._connections[channel] = set()
            self._connections[channel].add(websocket)

        logger.info(f"WebSocket 已连接: channel={channel}, 当前连接数={self.get_connection_count(channel)}")

    async def disconnect(
        self,
        websocket: WebSocket,
        channel: str = "default",
    ) -> None:
        """断开 WebSocket 连接并从频道移除。

        Args:
            websocket: WebSocket 连接实例。
            channel:   频道名称。
        """
        async with self._lock:
            if channel in self._connections:
                self._connections[channel].discard(websocket)
                if not self._connections[channel]:
                    del self._connections[channel]

        logger.info(f"WebSocket 已断开: channel={channel}")

    async def broadcast(
        self,
        channel: str,
        message: Any,
    ) -> int:
        """向指定频道的所有连接广播消息。

        Args:
            channel: 频道名称。
            message: 消息内容（将自动序列化为 JSON）。

        Returns:
            成功发送的连接数。
        """
        if isinstance(message, (dict, list)):
            data = json.dumps(message, ensure_ascii=False)
        else:
            data = str(message)

        sent_count = 0

        async with self._lock:
            connections = list(self._connections.get(channel, set()))

        for connection in connections:
            try:
                await connection.send_text(data)
                sent_count += 1
            except Exception as e:
                logger.warning(f"WebSocket 发送消息失败: {e}")
                await self.disconnect(connection, channel)

        return sent_count

    async def broadcast_all(self, message: Any) -> int:
        """向所有频道的所有连接广播消息。

        Args:
            message: 消息内容。

        Returns:
            成功发送的连接数。
        """
        total_sent = 0
        async with self._lock:
            channels = list(self._connections.keys())

        for channel in channels:
            total_sent += await self.broadcast(channel, message)

        return total_sent

    def get_connection_count(self, channel: str = "default") -> int:
        """获取指定频道的连接数。

        Args:
            channel: 频道名称。

        Returns:
            连接数。
        """
        return len(self._connections.get(channel, set()))

    def get_all_channels(self) -> List[str]:
        """获取所有活跃频道。

        Returns:
            频道名称列表。
        """
        return list(self._connections.keys())

    def get_total_connections(self) -> int:
        """获取总连接数。

        Returns:
            所有频道的总连接数。
        """
        return sum(len(conns) for conns in self._connections.values())


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

ws_manager = WebSocketManager()
