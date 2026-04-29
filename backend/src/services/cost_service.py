"""AI 成本追踪服务

追踪 AI 模型调用的 token 使用量和成本。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class CostRecord:
    """单次 AI 调用成本记录"""
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# 各模型定价 (每百万 token, USD)
# ---------------------------------------------------------------------------

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    # Claude
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen
    "qwen-max": {"input": 1.6, "output": 4.8},
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "qwen-turbo": {"input": 0.3, "output": 0.6},
    # 默认
    "default": {"input": 1.0, "output": 3.0},
}


# ---------------------------------------------------------------------------
# CostService
# ---------------------------------------------------------------------------

class CostService:
    """AI 成本追踪服务

    追踪每次 AI 模型调用的 token 使用量和成本。
    提供按提供商、按天等维度的统计查询。

    Usage::

        svc = CostService()
        svc.record_usage("openai", "gpt-4o", 100, 200)
        summary = svc.get_summary()
    """

    def __init__(self) -> None:
        self._records: List[CostRecord] = []
        self._lock = threading.Lock()
        self._max_records: int = 100000

        logger.info("CostService 已创建")

    # ------------------------------------------------------------------
    # 记录使用量
    # ------------------------------------------------------------------

    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> CostRecord:
        """记录一次 AI 调用的使用量。

        Args:
            provider:     模型提供商。
            model:        模型名称。
            input_tokens: 输入 token 数。
            output_tokens: 输出 token 数。
            latency_ms:   延迟（毫秒）。

        Returns:
            CostRecord 记录。
        """
        total_tokens = input_tokens + output_tokens
        cost = self.calculate_cost(model, input_tokens, output_tokens)

        record = CostRecord(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            latency_ms=latency_ms,
        )

        with self._lock:
            self._records.append(record)
            # 限制记录数量
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

        logger.debug(
            f"AI 成本记录: provider={provider}, model={model}, "
            f"tokens={total_tokens}, cost=${cost:.6f}"
        )

        return record

    # ------------------------------------------------------------------
    # 统计查询
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """获取总体成本统计。

        Returns:
            统计摘要字典。
        """
        with self._lock:
            records = list(self._records)

        if not records:
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "providers": [],
                "avg_latency_ms": 0.0,
            }

        total_cost = sum(r.cost for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_calls = len(records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        avg_latency = sum(r.latency_ms for r in records) / total_calls

        providers = list(set(r.provider for r in records))

        return {
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "providers": providers,
            "avg_latency_ms": round(avg_latency, 2),
        }

    def get_by_provider(self, provider: str) -> Dict[str, Any]:
        """按提供商获取成本统计。

        Args:
            provider: 提供商名称。

        Returns:
            该提供商的成本统计字典。
        """
        with self._lock:
            records = [r for r in self._records if r.provider == provider]

        if not records:
            return {
                "provider": provider,
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_calls": 0,
                "models": {},
            }

        total_cost = sum(r.cost for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_calls = len(records)

        # 按模型分组
        models: Dict[str, Dict[str, Any]] = {}
        for r in records:
            if r.model not in models:
                models[r.model] = {
                    "model": r.model,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "total_calls": 0,
                }
            models[r.model]["total_cost"] += r.cost
            models[r.model]["total_tokens"] += r.total_tokens
            models[r.model]["total_calls"] += 1

        # 四舍五入
        for m in models.values():
            m["total_cost"] = round(m["total_cost"], 6)

        return {
            "provider": provider,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "models": models,
        }

    def get_by_day(self, days: int = 7) -> List[Dict[str, Any]]:
        """按天获取成本统计。

        Args:
            days: 统计天数。

        Returns:
            每日成本统计列表（最新在前）。
        """
        with self._lock:
            records = list(self._records)

        cutoff = datetime.now() - timedelta(days=days)
        filtered = [r for r in records if r.timestamp >= cutoff]

        # 按天分组
        daily: Dict[str, Dict[str, Any]] = {}
        for r in filtered:
            day_key = r.timestamp.strftime("%Y-%m-%d")
            if day_key not in daily:
                daily[day_key] = {
                    "date": day_key,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "total_calls": 0,
                }
            daily[day_key]["total_cost"] += r.cost
            daily[day_key]["total_tokens"] += r.total_tokens
            daily[day_key]["total_calls"] += 1

        # 排序并四舍五入
        result = sorted(daily.values(), key=lambda x: x["date"], reverse=True)
        for d in result:
            d["total_cost"] = round(d["total_cost"], 6)

        return result

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_cost(
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """计算 AI 调用成本。

        Args:
            model:         模型名称。
            input_tokens:  输入 token 数。
            output_tokens: 输出 token 数。

        Returns:
            成本（美元）。
        """
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def clear_records(self) -> int:
        """清除所有记录。

        Returns:
            清除的记录数。
        """
        with self._lock:
            count = len(self._records)
            self._records.clear()
        logger.info(f"已清除 {count} 条成本记录")
        return count
