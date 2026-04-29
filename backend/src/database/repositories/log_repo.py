"""日志数据仓库

提供决策日志和交易日志的异步CRUD操作，支持分页和条件筛选。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.schema import DecisionLogORM, TradeLogORM
from src.models.decision import Decision, DecisionAction, DecisionCreate


# =========================================================================
# 决策日志仓库
# =========================================================================

class DecisionLogRepository:
    """决策日志数据仓库，封装决策日志的异步CRUD操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    async def save_decision_log(
        self,
        decision_id: str,
        data: DecisionCreate,
    ) -> DecisionLogORM:
        """保存决策日志。

        Args:
            decision_id: 决策唯一标识。
            data:        决策创建参数。

        Returns:
            新创建的 DecisionLogORM 实例。
        """
        orm = DecisionLogORM(
            decision_id=decision_id,
            model=data.model,
            provider=data.provider,
            action=data.action.value,
            symbol=data.symbol,
            quantity=data.quantity,
            price=data.price,
            confidence=data.confidence,
            reasoning=data.reasoning,
            raw_response=data.raw_response,
            prompt=data.prompt,
            market_context=data.market_context,
            account_context=data.account_context,
            executed=data.executed,
            execution_result=data.execution_result,
            latency_ms=data.latency_ms,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"决策日志已保存: {decision_id} {data.action.value}")
        return orm

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_decision_log(
        self,
        decision_id: str,
    ) -> Optional[DecisionLogORM]:
        """根据 decision_id 查询决策日志。"""
        stmt = select(DecisionLogORM).where(
            DecisionLogORM.decision_id == decision_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
    ) -> List[DecisionLogORM]:
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
            DecisionLogORM 列表。
        """
        stmt = select(DecisionLogORM)
        if model is not None:
            stmt = stmt.where(DecisionLogORM.model == model)
        if provider is not None:
            stmt = stmt.where(DecisionLogORM.provider == provider)
        if action is not None:
            stmt = stmt.where(DecisionLogORM.action == action.value)
        if symbol is not None:
            stmt = stmt.where(DecisionLogORM.symbol == symbol)
        if executed is not None:
            stmt = stmt.where(DecisionLogORM.executed == executed)
        if start_time is not None:
            stmt = stmt.where(DecisionLogORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(DecisionLogORM.created_at <= end_time)

        stmt = stmt.offset(skip).limit(limit).order_by(DecisionLogORM.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_decision_logs(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        action: Optional[DecisionAction] = None,
        symbol: Optional[str] = None,
        executed: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """统计决策日志数量。"""
        stmt = select(func.count()).select_from(DecisionLogORM)
        if model is not None:
            stmt = stmt.where(DecisionLogORM.model == model)
        if provider is not None:
            stmt = stmt.where(DecisionLogORM.provider == provider)
        if action is not None:
            stmt = stmt.where(DecisionLogORM.action == action.value)
        if symbol is not None:
            stmt = stmt.where(DecisionLogORM.symbol == symbol)
        if executed is not None:
            stmt = stmt.where(DecisionLogORM.executed == executed)
        if start_time is not None:
            stmt = stmt.where(DecisionLogORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(DecisionLogORM.created_at <= end_time)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_decision_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取决策统计信息。

        Returns:
            包含以下键的字典:
            - total:        总决策数
            - buy_count:    买入决策数
            - sell_count:   卖出决策数
            - hold_count:   持有决策数
            - executed_count: 已执行数
            - avg_confidence: 平均置信度
            - avg_latency_ms: 平均延迟(ms)
        """
        base = select(DecisionLogORM)
        if start_time is not None:
            base = base.where(DecisionLogORM.created_at >= start_time)
        if end_time is not None:
            base = base.where(DecisionLogORM.created_at <= end_time)

        # 总数
        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(total_stmt)).scalar_one()

        # 按动作统计
        buy_stmt = select(func.count()).select_from(
            base.where(DecisionLogORM.action == "buy").subquery()
        )
        sell_stmt = select(func.count()).select_from(
            base.where(DecisionLogORM.action == "sell").subquery()
        )
        hold_stmt = select(func.count()).select_from(
            base.where(DecisionLogORM.action == "hold").subquery()
        )
        executed_stmt = select(func.count()).select_from(
            base.where(DecisionLogORM.executed == True).subquery()  # noqa: E712
        )

        buy_count = (await self.session.execute(buy_stmt)).scalar_one()
        sell_count = (await self.session.execute(sell_stmt)).scalar_one()
        hold_count = (await self.session.execute(hold_stmt)).scalar_one()
        executed_count = (await self.session.execute(executed_stmt)).scalar_one()

        # 平均置信度和延迟
        avg_conf_stmt = select(func.avg(DecisionLogORM.confidence))
        avg_latency_stmt = select(func.avg(DecisionLogORM.latency_ms))
        if start_time is not None:
            avg_conf_stmt = avg_conf_stmt.where(DecisionLogORM.created_at >= start_time)
            avg_latency_stmt = avg_latency_stmt.where(DecisionLogORM.created_at >= start_time)
        if end_time is not None:
            avg_conf_stmt = avg_conf_stmt.where(DecisionLogORM.created_at <= end_time)
            avg_latency_stmt = avg_latency_stmt.where(DecisionLogORM.created_at <= end_time)

        avg_confidence = (await self.session.execute(avg_conf_stmt)).scalar_one() or 0.0
        avg_latency = (await self.session.execute(avg_latency_stmt)).scalar_one() or 0

        return {
            "total": total,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "executed_count": executed_count,
            "avg_confidence": round(float(avg_confidence), 4),
            "avg_latency_ms": round(float(avg_latency), 2) if avg_latency else 0,
        }

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    async def update_execution_status(
        self,
        decision_id: str,
        executed: bool,
        execution_result: Optional[str] = None,
    ) -> Optional[DecisionLogORM]:
        """更新决策的执行状态。

        Args:
            decision_id:      决策唯一标识。
            executed:         是否已执行。
            execution_result: 执行结果描述。

        Returns:
            更新后的 DecisionLogORM 实例，不存在时返回 None。
        """
        orm = await self.get_decision_log(decision_id)
        if orm is None:
            return None

        orm.executed = executed
        if execution_result is not None:
            orm.execution_result = execution_result
        await self.session.flush()
        logger.info(f"决策执行状态已更新: {decision_id} executed={executed}")
        return orm

    # ------------------------------------------------------------------
    # ORM -> dataclass 转换
    # ------------------------------------------------------------------

    @staticmethod
    def to_model(orm: DecisionLogORM) -> Decision:
        """将 DecisionLogORM 转换为 Decision dataclass。"""
        return Decision(
            decision_id=orm.decision_id,
            timestamp=orm.created_at,
            model=orm.model,
            provider=orm.provider,
            action=DecisionAction(orm.action),
            symbol=orm.symbol,
            quantity=orm.quantity,
            price=orm.price,
            confidence=orm.confidence,
            reasoning=orm.reasoning or "",
            raw_response=orm.raw_response or "",
            executed=orm.executed,
            execution_result=orm.execution_result,
            latency_ms=orm.latency_ms,
            prompt=orm.prompt,
            market_context=orm.market_context,
            account_context=orm.account_context,
        )


# =========================================================================
# 交易日志仓库
# =========================================================================

class TradeLogRepository:
    """交易日志数据仓库，封装交易日志的异步CRUD操作。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 创建
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
    ) -> TradeLogORM:
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
            新创建的 TradeLogORM 实例。
        """
        orm = TradeLogORM(
            order_id=order_id,
            decision_id=decision_id,
            account_id=account_id,
            broker=broker,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            commission=commission,
            pnl=pnl,
        )
        self.session.add(orm)
        await self.session.flush()
        logger.info(f"交易日志已保存: {order_id} {side} {symbol} x{quantity} @{price}")
        return orm

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def get_trade_log(self, log_id: int) -> Optional[TradeLogORM]:
        """根据主键ID查询交易日志。"""
        stmt = select(TradeLogORM).where(TradeLogORM.id == log_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
    ) -> List[TradeLogORM]:
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
            TradeLogORM 列表。
        """
        stmt = select(TradeLogORM)
        if account_id is not None:
            stmt = stmt.where(TradeLogORM.account_id == account_id)
        if symbol is not None:
            stmt = stmt.where(TradeLogORM.symbol == symbol)
        if side is not None:
            stmt = stmt.where(TradeLogORM.side == side)
        if broker is not None:
            stmt = stmt.where(TradeLogORM.broker == broker)
        if decision_id is not None:
            stmt = stmt.where(TradeLogORM.decision_id == decision_id)
        if start_time is not None:
            stmt = stmt.where(TradeLogORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(TradeLogORM.created_at <= end_time)

        stmt = stmt.offset(skip).limit(limit).order_by(TradeLogORM.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_trade_logs(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        broker: Optional[str] = None,
        decision_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """统计交易日志数量。"""
        stmt = select(func.count()).select_from(TradeLogORM)
        if account_id is not None:
            stmt = stmt.where(TradeLogORM.account_id == account_id)
        if symbol is not None:
            stmt = stmt.where(TradeLogORM.symbol == symbol)
        if side is not None:
            stmt = stmt.where(TradeLogORM.side == side)
        if broker is not None:
            stmt = stmt.where(TradeLogORM.broker == broker)
        if decision_id is not None:
            stmt = stmt.where(TradeLogORM.decision_id == decision_id)
        if start_time is not None:
            stmt = stmt.where(TradeLogORM.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(TradeLogORM.created_at <= end_time)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_trade_statistics(
        self,
        account_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取交易统计信息。

        Returns:
            包含以下键的字典:
            - total:           总交易数
            - buy_count:       买入次数
            - sell_count:      卖出次数
            - total_commission: 总手续费
            - total_pnl:       总盈亏
            - win_count:       盈利次数
            - loss_count:      亏损次数
        """
        base = select(TradeLogORM)
        if account_id is not None:
            base = base.where(TradeLogORM.account_id == account_id)
        if start_time is not None:
            base = base.where(TradeLogORM.created_at >= start_time)
        if end_time is not None:
            base = base.where(TradeLogORM.created_at <= end_time)

        subq = base.subquery()

        total = (await self.session.execute(
            select(func.count()).select_from(subq)
        )).scalar_one()

        buy_count = (await self.session.execute(
            select(func.count()).select_from(
                base.where(TradeLogORM.side == "buy").subquery()
            )
        )).scalar_one()

        sell_count = (await self.session.execute(
            select(func.count()).select_from(
                base.where(TradeLogORM.side == "sell").subquery()
            )
        )).scalar_one()

        total_commission = (await self.session.execute(
            select(func.coalesce(func.sum(TradeLogORM.commission), 0)).select_from(subq)
        )).scalar_one()

        total_pnl = (await self.session.execute(
            select(func.coalesce(func.sum(TradeLogORM.pnl), 0)).select_from(subq)
        )).scalar_one()

        win_count = (await self.session.execute(
            select(func.count()).select_from(
                base.where(TradeLogORM.pnl > 0).subquery()
            )
        )).scalar_one()

        loss_count = (await self.session.execute(
            select(func.count()).select_from(
                base.where(TradeLogORM.pnl < 0).subquery()
            )
        )).scalar_one()

        return {
            "total": total,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_commission": round(float(total_commission), 4),
            "total_pnl": round(float(total_pnl), 4),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_count / total, 4) if total > 0 else 0.0,
        }
