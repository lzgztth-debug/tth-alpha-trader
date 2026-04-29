"""风险管理模块

提供交易前的风险检查功能，包括单笔交易限额、日内交易次数限制、
持仓集中度检查、日内亏损限制、最大回撤限制和交易时段检查。
"""

import sys
from pathlib import Path
_backend_root = str(Path(__file__).resolve().parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ===========================================================================
# 枚举与数据类
# ===========================================================================


class RiskLevel(str, Enum):
    """风险等级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskConfig:
    """风险管理配置

    Attributes:
        max_single_trade_value:   单笔交易最大金额。
        max_daily_trades:         每日最大交易次数。
        max_position_concentration: 单一标的最大持仓集中度 (占总资产比例 0~1)。
        max_daily_loss:           每日最大亏损金额。
        max_drawdown:             最大回撤比例 (0~1)。
        trading_hours_start:      交易开始时间 (HH:MM)。
        trading_hours_end:        交易结束时间 (HH:MM)。
        enabled:                  是否启用风控检查。
    """
    max_single_trade_value: float = 100_000.0
    max_daily_trades: int = 50
    max_position_concentration: float = 0.30
    max_daily_loss: float = 50_000.0
    max_drawdown: float = 0.20
    trading_hours_start: str = "09:30"
    trading_hours_end: str = "15:00"
    enabled: bool = True


@dataclass
class RiskCheckResult:
    """风控检查结果

    Attributes:
        passed:  是否通过检查。
        level:   风险等级。
        reason:  检查结果说明。
        details: 详细信息字典。
    """
    passed: bool
    level: RiskLevel
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "passed": self.passed,
            "level": self.level.value,
            "reason": self.reason,
            "details": self.details,
        }


# ===========================================================================
# RiskManager - 风险管理器
# ===========================================================================


class RiskManager:
    """风险管理器

    在交易执行前进行多层风险检查，确保交易行为在可接受的风险范围内。
    所有检查方法返回 RiskCheckResult，支持组合检查和独立检查。
    """

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        """
        初始化风险管理器。

        Args:
            config: 风控配置，None 则使用默认配置。
        """
        self._config = config or RiskConfig()
        # 每日交易计数 {account_id: count}
        self._daily_trade_counts: Dict[str, int] = {}
        # 每日盈亏记录 {account_id: daily_pnl}
        self._daily_pnl: Dict[str, float] = {}
        # 账户历史最高净值 {account_id: peak_value}
        self._peak_values: Dict[str, float] = {}
        # 上次重置日期
        self._last_reset_date: Optional[str] = None

        logger.info(
            "风险管理器初始化完成: enabled={}, max_single={}, max_daily_trades={}, "
            "max_concentration={}, max_daily_loss={}, max_drawdown={}",
            self._config.enabled,
            self._config.max_single_trade_value,
            self._config.max_daily_trades,
            self._config.max_position_concentration,
            self._config.max_daily_loss,
            self._config.max_drawdown,
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def check_trade_risk(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        current_positions: Optional[List[Dict[str, Any]]] = None,
        account_info: Optional[Dict[str, Any]] = None,
    ) -> RiskCheckResult:
        """执行单笔交易的综合风控检查。

        按优先级依次执行所有检查，遇到首个未通过的检查即返回。

        Args:
            account_id:        账户ID。
            symbol:            标的代码。
            side:              买卖方向 ("buy" / "sell")。
            quantity:          交易数量。
            price:             交易价格。
            current_positions: 当前持仓列表。
            account_info:      账户信息字典。

        Returns:
            RiskCheckResult 综合检查结果。
        """
        if not self._config.enabled:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="风控检查已禁用",
            )

        self._maybe_reset_daily_counters()

        results = await self.check_all(
            account_id, symbol, side, quantity, price,
            current_positions, account_info,
        )

        # 找到第一个未通过的检查
        for result in results:
            if not result.passed:
                logger.warning(
                    "风控检查未通过: account={}, symbol={}, check={}",
                    account_id, symbol, result.reason,
                )
                return result

        # 所有检查通过，取最高风险等级
        max_level = self._get_max_risk_level(results)
        return RiskCheckResult(
            passed=True,
            level=max_level,
            reason="所有风控检查通过",
            details={"checks_passed": len(results)},
        )

    async def check_all(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        current_positions: Optional[List[Dict[str, Any]]] = None,
        account_info: Optional[Dict[str, Any]] = None,
    ) -> List[RiskCheckResult]:
        """执行所有风控检查并返回全部结果。

        Args:
            account_id:        账户ID。
            symbol:            标的代码。
            side:              买卖方向。
            quantity:          交易数量。
            price:             交易价格。
            current_positions: 当前持仓列表。
            account_info:      账户信息字典。

        Returns:
            RiskCheckResult 列表。
        """
        trade_value = quantity * price

        results: List[RiskCheckResult] = [
            self._check_single_trade_limit(trade_value),
            self._check_daily_trade_limit(),
            self._check_position_concentration(symbol, account_info),
            self._check_daily_loss_limit(account_info),
            self._check_drawdown_limit(account_info),
            self._check_trading_hours(),
        ]

        return results

    # ------------------------------------------------------------------
    # 单项检查方法
    # ------------------------------------------------------------------

    def _check_single_trade_limit(self, value: float) -> RiskCheckResult:
        """检查单笔交易金额是否超过限额。

        Args:
            value: 交易金额。

        Returns:
            RiskCheckResult。
        """
        limit = self._config.max_single_trade_value

        if value <= 0:
            return RiskCheckResult(
                passed=False,
                level=RiskLevel.HIGH,
                reason="交易金额无效",
                details={"trade_value": value, "limit": limit},
            )

        ratio = value / limit
        if ratio > 1.0:
            level = RiskLevel.CRITICAL
        elif ratio > 0.8:
            level = RiskLevel.HIGH
        elif ratio > 0.5:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        passed = value <= limit
        reason = (
            f"单笔交易金额检查{'通过' if passed else '未通过'}: "
            f"{value:.2f} / {limit:.2f}"
        )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "trade_value": round(value, 2),
                "limit": limit,
                "ratio": round(ratio, 4),
            },
        )

    def _check_daily_trade_limit(self) -> RiskCheckResult:
        """检查日内交易次数是否超过限额。

        Returns:
            RiskCheckResult。
        """
        # 使用全局计数 (不区分账户)
        total_trades = sum(self._daily_trade_counts.values())
        limit = self._config.max_daily_trades

        ratio = total_trades / limit if limit > 0 else 0
        if ratio >= 1.0:
            level = RiskLevel.CRITICAL
        elif ratio >= 0.8:
            level = RiskLevel.HIGH
        elif ratio >= 0.5:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        passed = total_trades < limit
        reason = (
            f"日内交易次数检查{'通过' if passed else '未通过'}: "
            f"{total_trades} / {limit}"
        )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "daily_trades": total_trades,
                "limit": limit,
                "ratio": round(ratio, 4),
            },
        )

    def _check_position_concentration(
        self,
        symbol: str,
        account_info: Optional[Dict[str, Any]] = None,
    ) -> RiskCheckResult:
        """检查单一标的持仓集中度是否超过限额。

        Args:
            symbol:       标的代码。
            account_info: 账户信息字典，需包含 total_value 和 positions。

        Returns:
            RiskCheckResult。
        """
        if account_info is None:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="持仓集中度检查跳过 (无账户信息)",
            )

        total_value = account_info.get("total_value", 0.0)
        if total_value <= 0:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="持仓集中度检查跳过 (总资产为0)",
            )

        # 查找该标的的持仓市值
        positions = account_info.get("positions", [])
        symbol_position_value = 0.0
        for pos in positions:
            if isinstance(pos, dict) and pos.get("symbol") == symbol:
                symbol_position_value = pos.get("market_value", 0.0)
                break

        concentration = symbol_position_value / total_value
        limit = self._config.max_position_concentration

        if concentration >= limit:
            level = RiskLevel.HIGH
        elif concentration >= limit * 0.8:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        passed = concentration < limit
        reason = (
            f"持仓集中度检查{'通过' if passed else '未通过'}: "
            f"{concentration:.2%} / {limit:.2%}"
        )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "symbol": symbol,
                "position_value": round(symbol_position_value, 2),
                "total_value": round(total_value, 2),
                "concentration": round(concentration, 4),
                "limit": limit,
            },
        )

    def _check_daily_loss_limit(
        self,
        account_info: Optional[Dict[str, Any]] = None,
    ) -> RiskCheckResult:
        """检查日内亏损是否超过限额。

        Args:
            account_info: 账户信息字典，需包含 initial_cash 和 current_value。

        Returns:
            RiskCheckResult。
        """
        if account_info is None:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="日内亏损检查跳过 (无账户信息)",
            )

        current_value = account_info.get("current_value", 0.0)
        initial_value = account_info.get("initial_cash", 0.0)

        if initial_value <= 0:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="日内亏损检查跳过 (初始资金为0)",
            )

        daily_loss = initial_value - current_value
        if daily_loss < 0:
            daily_loss = 0.0

        limit = self._config.max_daily_loss

        ratio = daily_loss / limit if limit > 0 else 0
        if ratio >= 1.0:
            level = RiskLevel.CRITICAL
        elif ratio >= 0.8:
            level = RiskLevel.HIGH
        elif ratio >= 0.5:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        passed = daily_loss < limit
        reason = (
            f"日内亏损检查{'通过' if passed else '未通过'}: "
            f"{daily_loss:.2f} / {limit:.2f}"
        )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "daily_loss": round(daily_loss, 2),
                "limit": limit,
                "ratio": round(ratio, 4),
            },
        )

    def _check_drawdown_limit(
        self,
        account_info: Optional[Dict[str, Any]] = None,
    ) -> RiskCheckResult:
        """检查最大回撤是否超过限额。

        Args:
            account_info: 账户信息字典，需包含 total_value。

        Returns:
            RiskCheckResult。
        """
        if account_info is None:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="最大回撤检查跳过 (无账户信息)",
            )

        account_id = account_info.get("account_id", "__global__")
        current_value = account_info.get("total_value", 0.0)

        # 更新历史最高净值
        peak = self._peak_values.get(account_id, current_value)
        if current_value > peak:
            self._peak_values[account_id] = current_value
            peak = current_value

        if peak <= 0:
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="最大回撤检查跳过 (历史净值为0)",
            )

        drawdown = (peak - current_value) / peak
        limit = self._config.max_drawdown

        if drawdown >= limit:
            level = RiskLevel.CRITICAL
        elif drawdown >= limit * 0.8:
            level = RiskLevel.HIGH
        elif drawdown >= limit * 0.5:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        passed = drawdown < limit
        reason = (
            f"最大回撤检查{'通过' if passed else '未通过'}: "
            f"{drawdown:.2%} / {limit:.2%}"
        )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "current_value": round(current_value, 2),
                "peak_value": round(peak, 2),
                "drawdown": round(drawdown, 4),
                "limit": limit,
            },
        )

    def _check_trading_hours(self) -> RiskCheckResult:
        """检查当前时间是否在允许的交易时段内。

        Returns:
            RiskCheckResult。
        """
        try:
            start_parts = self._config.trading_hours_start.split(":")
            end_parts = self._config.trading_hours_end.split(":")
            start_time = time(int(start_parts[0]), int(start_parts[1]))
            end_time = time(int(end_parts[0]), int(end_parts[1]))
        except (ValueError, IndexError) as e:
            logger.warning("交易时段配置无效: {}", e)
            return RiskCheckResult(
                passed=True,
                level=RiskLevel.LOW,
                reason="交易时段检查跳过 (配置无效)",
            )

        now = datetime.now().time()
        passed = start_time <= now <= end_time

        if not passed:
            level = RiskLevel.HIGH
            reason = (
                f"当前时间不在交易时段内: "
                f"{now.strftime('%H:%M')} 不在 [{self._config.trading_hours_start}, "
                f"{self._config.trading_hours_end}]"
            )
        else:
            level = RiskLevel.LOW
            reason = (
                f"交易时段检查通过: 当前时间 {now.strftime('%H:%M')} "
                f"在 [{self._config.trading_hours_start}, "
                f"{self._config.trading_hours_end}] 内"
            )

        return RiskCheckResult(
            passed=passed,
            level=level,
            reason=reason,
            details={
                "current_time": now.isoformat(),
                "trading_hours_start": self._config.trading_hours_start,
                "trading_hours_end": self._config.trading_hours_end,
            },
        )

    # ------------------------------------------------------------------
    # 交易计数管理
    # ------------------------------------------------------------------

    def record_trade(self, account_id: str) -> None:
        """记录一笔交易 (递增日内计数)。

        Args:
            account_id: 账户ID。
        """
        self._maybe_reset_daily_counters()
        self._daily_trade_counts[account_id] = (
            self._daily_trade_counts.get(account_id, 0) + 1
        )
        logger.debug(
            "交易计数已更新: account={}, count={}",
            account_id,
            self._daily_trade_counts[account_id],
        )

    def record_daily_pnl(self, account_id: str, pnl: float) -> None:
        """记录日内盈亏。

        Args:
            account_id: 账户ID。
            pnl:        盈亏金额 (正数为盈利，负数为亏损)。
        """
        self._maybe_reset_daily_counters()
        self._daily_pnl[account_id] = (
            self._daily_pnl.get(account_id, 0.0) + pnl
        )

    def get_daily_trade_count(self, account_id: str) -> int:
        """获取账户当日交易次数。"""
        self._maybe_reset_daily_counters()
        return self._daily_trade_counts.get(account_id, 0)

    def reset_daily_counters(self) -> None:
        """手动重置日内计数器。"""
        self._daily_trade_counts.clear()
        self._daily_pnl.clear()
        self._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        logger.info("日内计数器已手动重置")

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------

    @property
    def config(self) -> RiskConfig:
        """获取当前风控配置。"""
        return self._config

    def update_config(self, **kwargs: Any) -> None:
        """更新风控配置参数。

        Args:
            **kwargs: 要更新的配置键值对。
        """
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                logger.info("风控配置已更新: {}={}", key, value)
            else:
                logger.warning("未知的风控配置项: {}", key)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _maybe_reset_daily_counters(self) -> None:
        """检查是否需要重置日内计数器 (跨日自动重置)。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            if self._last_reset_date is not None:
                logger.info(
                    "检测到日期变更: {} -> {}, 重置日内计数器",
                    self._last_reset_date,
                    today,
                )
            self._daily_trade_counts.clear()
            self._daily_pnl.clear()
            self._last_reset_date = today

    @staticmethod
    def _get_max_risk_level(results: List[RiskCheckResult]) -> RiskLevel:
        """从多个检查结果中获取最高风险等级。"""
        level_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        max_level = RiskLevel.LOW
        for result in results:
            if level_order.get(result.level, 0) > level_order.get(max_level, 0):
                max_level = result.level
        return max_level
