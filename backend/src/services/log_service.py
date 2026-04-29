"""日志服务模块

提供决策日志管理、交易日志管理、日志查询和导出功能。
支持日志分页、条件筛选、CSV/JSON 导出。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.decision import Decision, DecisionAction, DecisionCreate


# ---------------------------------------------------------------------------
# 日志导出格式枚举
# ---------------------------------------------------------------------------

class ExportFormat(str):
    """日志导出格式"""
    CSV = "csv"
    JSON = "json"


# ---------------------------------------------------------------------------
# 分页结果
# ---------------------------------------------------------------------------

class PaginatedResult:
    """分页查询结果"""

    def __init__(
        self,
        items: List[Any],
        total: int,
        skip: int,
        limit: int,
    ) -> None:
        self.items = items
        self.total = total
        self.skip = skip
        self.limit = limit

    @property
    def page(self) -> int:
        """当前页码（从 1 开始）"""
        return (self.skip // self.limit) + 1 if self.limit > 0 else 1

    @property
    def total_pages(self) -> int:
        """总页数"""
        if self.limit <= 0:
            return 1
        return max(1, (self.total + self.limit - 1) // self.limit)

    @property
    def has_next(self) -> bool:
        """是否有下一页"""
        return self.skip + self.limit < self.total

    @property
    def has_prev(self) -> bool:
        """是否有上一页"""
        return self.skip > 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.limit,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


# ---------------------------------------------------------------------------
# LogService
# ---------------------------------------------------------------------------

class LogService:
    """日志服务

    提供决策日志管理、交易日志管理、日志查询和导出功能。

    Usage::

        service = LogService()
        await service.save_decision_log(decision_id, decision_create)
        logs = await service.get_decision_logs(symbol="AAPL", skip=0, limit=20)
        stats = await service.get_statistics()
        csv_data = await service.export_logs("decision", format="csv")
    """

    def __init__(self) -> None:
        """初始化日志服务。"""
        logger.info("LogService 已创建")

    # ------------------------------------------------------------------
    # 决策日志
    # ------------------------------------------------------------------

    async def save_decision_log(
        self,
        decision_id: str,
        data: DecisionCreate,
    ) -> Optional[Dict[str, Any]]:
        """保存决策日志。

        Args:
            decision_id: 决策唯一标识。
            data:        决策创建参数。

        Returns:
            保存后的日志数据字典，失败返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import DecisionLogRepository

            async with get_async_session() as session:
                repo = DecisionLogRepository(session)
                orm = await repo.save_decision_log(decision_id, data)

                return {
                    "decision_id": orm.decision_id,
                    "model": orm.model,
                    "provider": orm.provider,
                    "action": orm.action,
                    "symbol": orm.symbol,
                    "quantity": orm.quantity,
                    "price": orm.price,
                    "confidence": orm.confidence,
                    "reasoning": orm.reasoning,
                    "executed": orm.executed,
                    "latency_ms": orm.latency_ms,
                    "created_at": orm.created_at.isoformat() if orm.created_at else None,
                }

        except Exception as e:
            logger.error(f"保存决策日志失败: {decision_id}, 错误: {e}")
            return None

    async def get_decision_logs(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        action: Optional[DecisionAction] = None,
        symbol: Optional[str] = None,
        executed: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> PaginatedResult:
        """查询决策日志列表，支持多条件筛选和分页。

        Args:
            model:      按模型名称筛选。
            provider:   按模型供应商筛选。
            action:     按决策动作筛选。
            symbol:     按标的代码筛选。
            executed:   按执行状态筛选。
            start_time: 起始时间。
            end_time:   结束时间。
            skip:       跳过记录数。
            limit:      返回记录数上限。

        Returns:
            PaginatedResult 分页结果。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import DecisionLogRepository

            async with get_async_session() as session:
                repo = DecisionLogRepository(session)

                orms = await repo.get_decision_logs(
                    model=model,
                    provider=provider,
                    action=action,
                    symbol=symbol,
                    executed=executed,
                    start_time=start_time,
                    end_time=end_time,
                    skip=skip,
                    limit=limit,
                )

                total = await repo.count_decision_logs(
                    model=model,
                    provider=provider,
                    action=action,
                    symbol=symbol,
                    executed=executed,
                    start_time=start_time,
                    end_time=end_time,
                )

                items = [self._orm_to_decision_dict(orm) for orm in orms]
                return PaginatedResult(items=items, total=total, skip=skip, limit=limit)

        except Exception as e:
            logger.error(f"查询决策日志失败: {e}")
            return PaginatedResult(items=[], total=0, skip=skip, limit=limit)

    async def get_decision_log(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """查询单条决策日志。

        Args:
            decision_id: 决策唯一标识。

        Returns:
            日志数据字典，不存在返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import DecisionLogRepository

            async with get_async_session() as session:
                repo = DecisionLogRepository(session)
                orm = await repo.get_decision_log(decision_id)

                if orm is None:
                    return None

                return self._orm_to_decision_dict(orm)

        except Exception as e:
            logger.error(f"查询决策日志失败: {decision_id}, 错误: {e}")
            return None

    async def update_decision_execution(
        self,
        decision_id: str,
        executed: bool,
        execution_result: Optional[str] = None,
    ) -> bool:
        """更新决策的执行状态。

        Args:
            decision_id:      决策唯一标识。
            executed:         是否已执行。
            execution_result: 执行结果描述。

        Returns:
            是否更新成功。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import DecisionLogRepository

            async with get_async_session() as session:
                repo = DecisionLogRepository(session)
                orm = await repo.update_execution_status(
                    decision_id, executed, execution_result
                )
                return orm is not None

        except Exception as e:
            logger.error(f"更新决策执行状态失败: {decision_id}, 错误: {e}")
            return False

    # ------------------------------------------------------------------
    # 交易日志
    # ------------------------------------------------------------------

    async def save_trade_log(
        self,
        order_id: str,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        broker: str = "",
        decision_id: Optional[str] = None,
        commission: float = 0.0,
        pnl: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """保存交易日志。

        Args:
            order_id:    订单ID。
            account_id:  账户ID。
            symbol:      标的代码。
            side:        买卖方向。
            quantity:    成交数量。
            price:       成交价格。
            broker:      券商名称。
            decision_id: 关联的决策ID。
            commission:  手续费。
            pnl:         盈亏金额。

        Returns:
            保存后的日志数据字典，失败返回 None。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import TradeLogRepository

            async with get_async_session() as session:
                repo = TradeLogRepository(session)
                orm = await repo.save_trade_log(
                    order_id=order_id,
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    broker=broker,
                    decision_id=decision_id,
                    commission=commission,
                    pnl=pnl,
                )

                return {
                    "id": orm.id,
                    "order_id": orm.order_id,
                    "decision_id": orm.decision_id,
                    "account_id": orm.account_id,
                    "broker": orm.broker,
                    "symbol": orm.symbol,
                    "side": orm.side,
                    "quantity": orm.quantity,
                    "price": orm.price,
                    "commission": orm.commission,
                    "pnl": orm.pnl,
                    "created_at": orm.created_at.isoformat() if orm.created_at else None,
                }

        except Exception as e:
            logger.error(f"保存交易日志失败: {order_id}, 错误: {e}")
            return None

    async def get_trade_logs(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        broker: Optional[str] = None,
        decision_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> PaginatedResult:
        """查询交易日志列表，支持多条件筛选和分页。

        Args:
            account_id:  按账户ID筛选。
            symbol:      按标的代码筛选。
            side:        按买卖方向筛选。
            broker:      按券商名称筛选。
            decision_id: 按关联决策ID筛选。
            start_time:  起始时间。
            end_time:    结束时间。
            skip:        跳过记录数。
            limit:       返回记录数上限。

        Returns:
            PaginatedResult 分页结果。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import TradeLogRepository

            async with get_async_session() as session:
                repo = TradeLogRepository(session)

                orms = await repo.get_trade_logs(
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    broker=broker,
                    decision_id=decision_id,
                    start_time=start_time,
                    end_time=end_time,
                    skip=skip,
                    limit=limit,
                )

                total = await repo.count_trade_logs(
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    broker=broker,
                    decision_id=decision_id,
                    start_time=start_time,
                    end_time=end_time,
                )

                items = [self._orm_to_trade_dict(orm) for orm in orms]
                return PaginatedResult(items=items, total=total, skip=skip, limit=limit)

        except Exception as e:
            logger.error(f"查询交易日志失败: {e}")
            return PaginatedResult(items=[], total=0, skip=skip, limit=limit)

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    async def get_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取日志统计信息。

        Args:
            start_time: 起始时间。
            end_time:   结束时间。
            account_id: 账户ID（用于交易统计）。

        Returns:
            统计信息字典。
        """
        try:
            from src.database.connection import get_async_session
            from src.database.repositories.log_repo import (
                DecisionLogRepository,
                TradeLogRepository,
            )

            async with get_async_session() as session:
                decision_repo = DecisionLogRepository(session)
                trade_repo = TradeLogRepository(session)

                decision_stats = await decision_repo.get_decision_statistics(
                    start_time=start_time,
                    end_time=end_time,
                )

                trade_stats = await trade_repo.get_trade_statistics(
                    account_id=account_id,
                    start_time=start_time,
                    end_time=end_time,
                )

                return {
                    "decision": decision_stats,
                    "trade": trade_stats,
                    "period": {
                        "start_time": start_time.isoformat() if start_time else None,
                        "end_time": end_time.isoformat() if end_time else None,
                    },
                }

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "decision": {},
                "trade": {},
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # 日志导出
    # ------------------------------------------------------------------

    async def export_logs(
        self,
        log_type: str,
        format: str = "json",
        **filters,
    ) -> str:
        """导出日志数据。

        Args:
            log_type: 日志类型 ("decision" 或 "trade")。
            format:   导出格式 ("csv" 或 "json")。
            **filters: 筛选条件，与查询方法参数一致。

        Returns:
            导出的数据字符串（CSV 或 JSON）。

        Raises:
            ValueError: 参数无效。
        """
        if log_type not in ("decision", "trade"):
            raise ValueError(f"无效的日志类型: {log_type}，仅支持 'decision' 或 'trade'")

        if format not in ("csv", "json"):
            raise ValueError(f"无效的导出格式: {format}，仅支持 'csv' 或 'json'")

        # 获取全部数据（不限制数量）
        if log_type == "decision":
            result = await self.get_decision_logs(skip=0, limit=100000, **filters)
            items = result.items
        else:
            result = await self.get_trade_logs(skip=0, limit=100000, **filters)
            items = result.items

        if format == "json":
            return json.dumps(items, ensure_ascii=False, indent=2, default=str)

        # CSV 导出
        if not items:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=items[0].keys())
        writer.writeheader()
        for item in items:
            row = {}
            for k, v in item.items():
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
            writer.writerow(row)

        return output.getvalue()

    async def export_logs_to_file(
        self,
        file_path: str,
        log_type: str,
        format: str = "json",
        **filters,
    ) -> str:
        """导出日志到文件。

        Args:
            file_path: 输出文件路径。
            log_type:  日志类型。
            format:    导出格式。
            **filters: 筛选条件。

        Returns:
            导出文件的完整路径。
        """
        content = await self.export_logs(log_type, format=format, **filters)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(
            f"日志已导出: {file_path} "
            f"(类型={log_type}, 格式={format}, 大小={len(content)} bytes)"
        )
        return file_path

    # ------------------------------------------------------------------
    # ORM 转换
    # ------------------------------------------------------------------

    @staticmethod
    def _orm_to_decision_dict(orm) -> Dict[str, Any]:
        """将 DecisionLogORM 转换为字典。"""
        return {
            "decision_id": orm.decision_id,
            "model": orm.model,
            "provider": orm.provider,
            "action": orm.action,
            "symbol": orm.symbol,
            "quantity": orm.quantity,
            "price": orm.price,
            "confidence": orm.confidence,
            "reasoning": orm.reasoning,
            "raw_response": orm.raw_response,
            "prompt": orm.prompt,
            "market_context": orm.market_context,
            "account_context": orm.account_context,
            "executed": orm.executed,
            "execution_result": orm.execution_result,
            "latency_ms": orm.latency_ms,
            "created_at": orm.created_at.isoformat() if orm.created_at else None,
            "updated_at": orm.updated_at.isoformat() if orm.updated_at else None,
        }

    @staticmethod
    def _orm_to_trade_dict(orm) -> Dict[str, Any]:
        """将 TradeLogORM 转换为字典。"""
        return {
            "id": orm.id,
            "order_id": orm.order_id,
            "decision_id": orm.decision_id,
            "account_id": orm.account_id,
            "broker": orm.broker,
            "symbol": orm.symbol,
            "side": orm.side,
            "quantity": orm.quantity,
            "price": orm.price,
            "commission": orm.commission,
            "pnl": orm.pnl,
            "created_at": orm.created_at.isoformat() if orm.created_at else None,
            "updated_at": orm.updated_at.isoformat() if orm.updated_at else None,
        }
