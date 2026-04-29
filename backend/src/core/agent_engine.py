"""AI Agent 引擎模块

提供AI决策的核心能力，包括Prompt管理、上下文构建、决策解析和多模型并行调用。
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from src.adapters.ai_models.base import (
    BaseAIModelAdapter,
    ModelConfig,
    ModelProvider,
    ModelResponse,
)
from src.models.decision import Decision, DecisionAction


# ===========================================================================
# PromptManager - Prompt模板管理
# ===========================================================================


class PromptManager:
    """Prompt模板管理器

    负责加载、管理和渲染Prompt模板。支持:
    - 从文件系统加载模板
    - 变量注入 ({{variable_name}} 语法)
    - 模板版本管理
    - 内存缓存
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        """
        初始化PromptManager。

        Args:
            templates_dir: Prompt模板文件目录路径，默认使用项目内置目录。
        """
        if templates_dir is None:
            templates_dir = str(
                Path(__file__).resolve().parent.parent.parent / "config" / "prompts"
            )
        self._templates_dir = Path(templates_dir)
        # {name: {version: content}}
        self._templates: Dict[str, Dict[int, str]] = defaultdict(dict)
        # {name: active_version}
        self._active_versions: Dict[str, int] = {}
        # {name: {version: metadata}}
        self._metadata: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)

    # ------------------------------------------------------------------
    # 模板加载
    # ------------------------------------------------------------------

    def load_template(
        self,
        name: str,
        content: str,
        version: int = 1,
        category: str = "general",
        variables: Optional[List[str]] = None,
        set_active: bool = True,
    ) -> None:
        """加载一个Prompt模板到内存。

        Args:
            name:       模板名称 (唯一标识)。
            content:    模板内容，支持 {{variable}} 占位符。
            version:    模板版本号。
            category:   模板分类。
            variables:  模板中使用的变量列表。
            set_active: 是否设为当前活跃版本。
        """
        self._templates[name][version] = content
        self._metadata[name][version] = {
            "category": category,
            "variables": variables or self._extract_variables(content),
            "loaded_at": datetime.now().isoformat(),
        }
        if set_active or name not in self._active_versions:
            self._active_versions[name] = version
        logger.info(
            "Prompt模板已加载: name={}, version={}, category={}, variables={}",
            name,
            version,
            category,
            self._metadata[name][version]["variables"],
        )

    def load_from_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        version: int = 1,
        category: str = "general",
        set_active: bool = True,
    ) -> None:
        """从文件加载Prompt模板。

        Args:
            file_path:  模板文件路径。
            name:       模板名称，默认使用文件名(不含扩展名)。
            version:    版本号。
            category:   分类。
            set_active: 是否设为活跃版本。
        """
        path = Path(file_path)
        if not path.exists():
            # 尝试在 templates_dir 下查找
            path = self._templates_dir / file_path
        if not path.exists():
            raise FileNotFoundError(f"Prompt模板文件不存在: {file_path}")

        content = path.read_text(encoding="utf-8")
        template_name = name or path.stem
        self.load_template(
            name=template_name,
            content=content,
            version=version,
            category=category,
            set_active=set_active,
        )

    def load_all_from_directory(self, directory: Optional[str] = None) -> int:
        """从目录批量加载所有 .txt / .md / .prompt 文件。

        Args:
            directory: 目录路径，默认使用 templates_dir。

        Returns:
            加载的模板数量。
        """
        target_dir = Path(directory) if directory else self._templates_dir
        if not target_dir.exists():
            logger.warning("模板目录不存在: {}", target_dir)
            return 0

        count = 0
        for ext in ("*.txt", "*.md", "*.prompt"):
            for file_path in target_dir.rglob(ext):
                try:
                    relative = file_path.relative_to(target_dir)
                    category = str(relative.parent).replace("/", "_").replace("\\", "_")
                    if category == ".":
                        category = "general"
                    self.load_from_file(
                        str(file_path),
                        name=file_path.stem,
                        category=category,
                    )
                    count += 1
                except Exception as e:
                    logger.error("加载模板文件失败: {} -> {}", file_path, e)

        logger.info("批量加载模板完成: 目录={}, 数量={}", target_dir, count)
        return count

    # ------------------------------------------------------------------
    # 模板渲染
    # ------------------------------------------------------------------

    def render(
        self,
        name: str,
        variables: Dict[str, Any],
        version: Optional[int] = None,
    ) -> str:
        """渲染Prompt模板，注入变量。

        Args:
            name:      模板名称。
            variables: 变量字典，key对应模板中的 {{key}}。
            version:   指定版本号，None则使用活跃版本。

        Returns:
            渲染后的Prompt字符串。

        Raises:
            KeyError: 模板不存在。
            ValueError: 缺少必要变量。
        """
        template = self._get_template(name, version)
        if template is None:
            raise KeyError(f"Prompt模板不存在: {name} (version={version})")

        # 检查必要变量
        required_vars = self._extract_variables(template)
        missing = [v for v in required_vars if v not in variables]
        if missing:
            raise ValueError(
                f"Prompt模板 '{name}' 缺少必要变量: {missing}"
            )

        # 逐步替换变量
        result = template
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            result = result.replace(placeholder, str(value))

        # 检查是否还有未替换的占位符
        remaining = self._extract_variables(result)
        if remaining:
            logger.warning(
                "Prompt模板 '{}' 渲染后仍有未替换变量: {}", name, remaining
            )

        return result.strip()

    # ------------------------------------------------------------------
    # 版本管理
    # ------------------------------------------------------------------

    def set_active_version(self, name: str, version: int) -> None:
        """设置模板的活跃版本。

        Args:
            name:    模板名称。
            version: 版本号。

        Raises:
            KeyError: 模板或版本不存在。
        """
        if name not in self._templates or version not in self._templates[name]:
            raise KeyError(
                f"模板或版本不存在: {name} v{version}, "
                f"可用版本: {list(self._templates.get(name, {}).keys())}"
            )
        self._active_versions[name] = version
        logger.info("模板活跃版本已切换: name={}, version={}", name, version)

    def get_active_version(self, name: str) -> int:
        """获取模板的活跃版本号。

        Args:
            name: 模板名称。

        Returns:
            活跃版本号。

        Raises:
            KeyError: 模板不存在。
        """
        if name not in self._active_versions:
            raise KeyError(f"模板不存在: {name}")
        return self._active_versions[name]

    def list_versions(self, name: str) -> List[int]:
        """列出模板的所有版本号。

        Args:
            name: 模板名称。

        Returns:
            版本号列表 (升序)。
        """
        if name not in self._templates:
            return []
        return sorted(self._templates[name].keys())

    def list_templates(
        self, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出所有已加载的模板。

        Args:
            category: 按分类筛选。

        Returns:
            模板信息列表。
        """
        result = []
        for name, versions in self._templates.items():
            for ver, _ in versions.items():
                meta = self._metadata[name].get(ver, {})
                if category and meta.get("category") != category:
                    continue
                result.append(
                    {
                        "name": name,
                        "version": ver,
                        "active": self._active_versions.get(name) == ver,
                        "category": meta.get("category", "unknown"),
                        "variables": meta.get("variables", []),
                    }
                )
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_template(
        self, name: str, version: Optional[int] = None
    ) -> Optional[str]:
        """获取模板内容。"""
        if name not in self._templates:
            return None
        ver = version if version is not None else self._active_versions.get(name)
        if ver is None or ver not in self._templates[name]:
            return None
        return self._templates[name][ver]

    @staticmethod
    def _extract_variables(template: str) -> List[str]:
        """从模板中提取 {{variable}} 变量名列表。"""
        return list(set(re.findall(r"\{\{(\w+)\}\}", template)))


# ===========================================================================
# ContextBuilder - AI决策上下文构建
# ===========================================================================


@dataclass
class MarketContext:
    """市场行情上下文"""
    symbol: str
    current_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    volume: float = 0.0
    change_pct: float = 0.0
    klines: Optional[List[Dict[str, Any]]] = None
    technical_indicators: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "volume": self.volume,
            "change_pct": self.change_pct,
            "klines": self.klines or [],
            "technical_indicators": self.technical_indicators or {},
        }


@dataclass
class AccountContext:
    """账户信息上下文"""
    account_id: str
    cash: float = 0.0
    available_cash: float = 0.0
    total_value: float = 0.0
    market_value: float = 0.0
    positions: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "cash": self.cash,
            "available_cash": self.available_cash,
            "total_value": self.total_value,
            "market_value": self.market_value,
            "positions": self.positions or [],
        }


class ContextBuilder:
    """AI决策上下文构建器

    将账户信息、持仓信息、市场行情、技术指标等数据
    组装为结构化的上下文字符串，供Prompt模板使用。
    """

    def __init__(self) -> None:
        self._market_contexts: Dict[str, MarketContext] = {}
        self._account_contexts: Dict[str, AccountContext] = {}
        self._extra_context: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 设置上下文数据
    # ------------------------------------------------------------------

    def set_market_context(self, context: MarketContext) -> None:
        """设置市场行情上下文。

        Args:
            context: MarketContext 实例。
        """
        self._market_contexts[context.symbol] = context
        logger.debug("市场上下文已更新: symbol={}", context.symbol)

    def set_account_context(self, context: AccountContext) -> None:
        """设置账户信息上下文。

        Args:
            context: AccountContext 实例。
        """
        self._account_contexts[context.account_id] = context
        logger.debug("账户上下文已更新: account_id={}", context.account_id)

    def set_extra_context(self, key: str, value: Any) -> None:
        """设置额外的上下文信息。

        Args:
            key:   上下文键名。
            value: 上下文值。
        """
        self._extra_context[key] = value

    def update_market_price(self, symbol: str, price: float) -> None:
        """更新单个标的的市场价格。

        Args:
            symbol: 标的代码。
            price:  最新价格。
        """
        if symbol in self._market_contexts:
            old_price = self._market_contexts[symbol].current_price
            self._market_contexts[symbol].current_price = price
            if old_price > 0:
                self._market_contexts[symbol].change_pct = (
                    (price - old_price) / old_price * 100
                )
            logger.debug("价格已更新: {} {} -> {}", symbol, old_price, price)

    # ------------------------------------------------------------------
    # 构建上下文
    # ------------------------------------------------------------------

    def build_context(
        self,
        symbol: str,
        account_id: Optional[str] = None,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        """构建完整的决策上下文字典。

        Args:
            symbol:          目标标的代码。
            account_id:      账户ID。
            include_history: 是否包含历史K线数据。

        Returns:
            上下文字典，可直接用于Prompt模板变量注入。
        """
        context: Dict[str, Any] = {}

        # 市场行情
        market_ctx = self._market_contexts.get(symbol)
        if market_ctx:
            context["symbol"] = market_ctx.symbol
            context["current_price"] = market_ctx.current_price
            context["open_price"] = market_ctx.open_price
            context["high_price"] = market_ctx.high_price
            context["low_price"] = market_ctx.low_price
            context["volume"] = market_ctx.volume
            context["change_pct"] = round(market_ctx.change_pct, 2)

            if include_history and market_ctx.klines:
                context["klines"] = json.dumps(
                    market_ctx.klines[-20:], ensure_ascii=False
                )

            if market_ctx.technical_indicators:
                context["technical_indicators"] = json.dumps(
                    market_ctx.technical_indicators, ensure_ascii=False
                )
        else:
            context["symbol"] = symbol
            context["current_price"] = 0.0
            context["open_price"] = 0.0
            context["high_price"] = 0.0
            context["low_price"] = 0.0
            context["volume"] = 0.0
            context["change_pct"] = 0.0

        # 账户信息
        if account_id:
            account_ctx = self._account_contexts.get(account_id)
            if account_ctx:
                context["account_balance"] = round(account_ctx.cash, 2)
                context["available_cash"] = round(account_ctx.available_cash, 2)
                context["total_value"] = round(account_ctx.total_value, 2)
                context["market_value"] = round(account_ctx.market_value, 2)

                if account_ctx.positions:
                    position_summary = []
                    for pos in account_ctx.positions:
                        position_summary.append(
                            f"  {pos.get('symbol', 'N/A')}: "
                            f"数量={pos.get('quantity', 0)}, "
                            f"成本={pos.get('avg_cost', 0):.2f}, "
                            f"现价={pos.get('current_price', 0):.2f}, "
                            f"盈亏={pos.get('unrealized_pnl', 0):.2f}"
                        )
                    context["positions"] = "\n".join(position_summary)
                else:
                    context["positions"] = "无持仓"
            else:
                context["account_balance"] = 0.0
                context["available_cash"] = 0.0
                context["total_value"] = 0.0
                context["market_value"] = 0.0
                context["positions"] = "未知"
        else:
            context["account_balance"] = 0.0
            context["available_cash"] = 0.0
            context["total_value"] = 0.0
            context["market_value"] = 0.0
            context["positions"] = "未提供"

        # 额外上下文
        context.update(self._extra_context)

        # 时间戳
        context["current_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return context

    def build_context_str(
        self,
        symbol: str,
        account_id: Optional[str] = None,
    ) -> str:
        """构建格式化的上下文字符串，可直接嵌入Prompt。

        Args:
            symbol:     标的代码。
            account_id: 账户ID。

        Returns:
            格式化的上下文字符串。
        """
        ctx = self.build_context(symbol, account_id)
        lines = [
            f"=== 决策上下文 ({ctx['current_time']}) ===",
            "",
            "--- 市场行情 ---",
            f"标的: {ctx.get('symbol', 'N/A')}",
            f"当前价格: {ctx.get('current_price', 0):.2f}",
            f"开盘价: {ctx.get('open_price', 0):.2f}",
            f"最高价: {ctx.get('high_price', 0):.2f}",
            f"最低价: {ctx.get('low_price', 0):.2f}",
            f"成交量: {ctx.get('volume', 0):.0f}",
            f"涨跌幅: {ctx.get('change_pct', 0):.2f}%",
        ]

        if ctx.get("technical_indicators"):
            lines.append("")
            lines.append("--- 技术指标 ---")
            lines.append(ctx["technical_indicators"])

        lines.extend(
            [
                "",
                "--- 账户信息 ---",
                f"现金余额: {ctx.get('account_balance', 0):.2f}",
                f"可用现金: {ctx.get('available_cash', 0):.2f}",
                f"总资产: {ctx.get('total_value', 0):.2f}",
                f"持仓市值: {ctx.get('market_value', 0):.2f}",
                "",
                "--- 当前持仓 ---",
                ctx.get("positions", "无持仓"),
                "",
            ]
        )

        return "\n".join(lines)

    def clear(self) -> None:
        """清除所有上下文数据。"""
        self._market_contexts.clear()
        self._account_contexts.clear()
        self._extra_context.clear()
        logger.debug("上下文已清除")


# ===========================================================================
# DecisionParser - AI模型输出解析
# ===========================================================================


@dataclass
class ParsedDecision:
    """解析后的决策结果"""
    action: DecisionAction
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
    raw_response: str = ""

    def to_decision(
        self,
        model: str = "",
        provider: str = "",
        decision_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        prompt: Optional[str] = None,
    ) -> Decision:
        """转换为 Decision 数据类。"""
        return Decision(
            decision_id=decision_id or str(uuid.uuid4()),
            timestamp=datetime.now(),
            model=model,
            provider=provider,
            action=self.action,
            symbol=self.symbol,
            quantity=self.quantity,
            price=self.price,
            confidence=self.confidence,
            reasoning=self.reasoning,
            raw_response=self.raw_response,
            latency_ms=latency_ms,
            prompt=prompt,
        )


class DecisionParser:
    """AI模型输出解析器

    从AI模型的文本输出中提取结构化的交易决策信息。
    支持多种输出格式: JSON、键值对、自然语言。
    """

    # 动作关键词映射
    ACTION_KEYWORDS: Dict[str, List[str]] = {
        "buy": ["买入", "buy", "做多", "long", "建议买入", "推荐买入", "看涨"],
        "sell": ["卖出", "sell", "做空", "short", "建议卖出", "推荐卖出", "看跌", "减仓"],
        "hold": ["持有", "hold", "观望", "等待", "维持", "不变", "不建议操作"],
    }

    def __init__(self, default_symbol: Optional[str] = None) -> None:
        """
        初始化DecisionParser。

        Args:
            default_symbol: 当解析不出标的代码时使用的默认标的。
        """
        self._default_symbol = default_symbol

    def parse(self, raw_response: str) -> ParsedDecision:
        """解析AI模型的原始输出文本。

        依次尝试以下解析策略:
        1. JSON格式解析
        2. 键值对格式解析
        3. 关键词/自然语言解析

        Args:
            raw_response: AI模型的原始输出文本。

        Returns:
            ParsedDecision 解析结果。
        """
        if not raw_response or not raw_response.strip():
            logger.warning("AI模型返回空响应")
            return ParsedDecision(
                action=DecisionAction.HOLD,
                reasoning="模型返回空响应",
                raw_response=raw_response,
            )

        text = raw_response.strip()

        # 策略1: 尝试JSON解析
        decision = self._try_parse_json(text)
        if decision is not None:
            logger.debug("JSON格式解析成功: action={}", decision.action.value)
            return decision

        # 策略2: 尝试键值对解析
        decision = self._try_parse_key_value(text)
        if decision is not None:
            logger.debug("键值对格式解析成功: action={}", decision.action.value)
            return decision

        # 策略3: 关键词/自然语言解析
        decision = self._try_parse_natural_language(text)
        if decision is not None:
            logger.debug("自然语言解析成功: action={}", decision.action.value)
            return decision

        # 所有策略失败，默认HOLD
        logger.warning("所有解析策略均失败，默认HOLD")
        return ParsedDecision(
            action=DecisionAction.HOLD,
            reasoning="无法解析模型输出，默认持有",
            raw_response=raw_response,
        )

    def parse_confidence(self, text: str) -> float:
        """从文本中提取置信度分数。

        支持的格式:
        - "置信度: 0.85" / "confidence: 85%"
        - "确信程度: 高" -> 0.8
        - "信心: 85/100"

        Args:
            text: 文本内容。

        Returns:
            置信度分数 (0.0 ~ 1.0)。
        """
        # 百分比格式
        pct_match = re.search(
            r"(?:置信度|confidence|确信|信心)[：:\s]*(\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE
        )
        if pct_match:
            return min(max(float(pct_match.group(1)) / 100.0, 0.0), 1.0)

        # 小数格式
        dec_match = re.search(
            r"(?:置信度|confidence|确信|信心)[：:\s]*(\d+(?:\.\d+)?)", text, re.IGNORECASE
        )
        if dec_match:
            val = float(dec_match.group(1))
            if val > 1.0:
                val = val / 100.0
            return min(max(val, 0.0), 1.0)

        # 分数格式 "85/100"
        frac_match = re.search(
            r"(?:置信度|confidence|确信|信心)[：:\s]*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE
        )
        if frac_match:
            numerator = float(frac_match.group(1))
            denominator = float(frac_match.group(2))
            if denominator > 0:
                return min(max(numerator / denominator, 0.0), 1.0)

        # 描述性词汇
        high_words = ["高", "非常高", "强烈", "very high", "strong", "high"]
        medium_words = ["中等", "一般", "moderate", "medium"]
        low_words = ["低", "不确定", "较弱", "low", "weak", "uncertain"]

        text_lower = text.lower()
        for word in high_words:
            if word in text_lower:
                return 0.8
        for word in medium_words:
            if word in text_lower:
                return 0.5
        for word in low_words:
            if word in text_lower:
                return 0.3

        return 0.5

    # ------------------------------------------------------------------
    # 内部解析策略
    # ------------------------------------------------------------------

    def _try_parse_json(self, text: str) -> Optional[ParsedDecision]:
        """尝试从文本中提取JSON并解析。"""
        # 尝试提取JSON块 (```json ... ``` 或 { ... })
        json_patterns = [
            r"```(?:json)?\s*\n?(.*?)\n?\s*```",
            r"\{[^{}]*\}",
        ]
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match.strip())
                    return self._parse_json_dict(data, text)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return None

    def _parse_json_dict(
        self, data: Dict[str, Any], raw_text: str
    ) -> Optional[ParsedDecision]:
        """从JSON字典中解析决策。"""
        if not isinstance(data, dict):
            return None

        # 提取action
        action_str = str(data.get("action", data.get("decision", ""))).lower().strip()
        action = self._match_action(action_str)
        if action is None:
            return None

        # 提取symbol
        symbol = data.get("symbol") or data.get("target") or data.get("code")
        if symbol:
            symbol = str(symbol).upper().strip()

        # 提取quantity
        quantity = data.get("quantity") or data.get("amount") or data.get("shares")
        if quantity is not None:
            try:
                quantity = float(quantity)
            except (TypeError, ValueError):
                quantity = None

        # 提取price
        price = data.get("price") or data.get("target_price")
        if price is not None:
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = None

        # 提取confidence
        confidence = data.get("confidence") or data.get("certainty")
        if confidence is not None:
            try:
                confidence = float(confidence)
                if confidence > 1.0:
                    confidence = confidence / 100.0
                confidence = min(max(confidence, 0.0), 1.0)
            except (TypeError, ValueError):
                confidence = self.parse_confidence(raw_text)
        else:
            confidence = self.parse_confidence(raw_text)

        # 提取reasoning
        reasoning = data.get("reasoning") or data.get("reason") or data.get("analysis") or ""

        return ParsedDecision(
            action=action,
            symbol=symbol or self._default_symbol,
            quantity=quantity,
            price=price,
            confidence=round(confidence, 4),
            reasoning=str(reasoning),
            raw_response=raw_text,
        )

    def _try_parse_key_value(self, text: str) -> Optional[ParsedDecision]:
        """尝试键值对格式解析 (如 'action: buy, symbol: AAPL')。"""
        kv_pattern = r"(\w+)\s*[：:]\s*([^\n,;，]+)"
        matches = re.findall(kv_pattern, text, re.IGNORECASE)

        if not matches:
            return None

        data = {}
        for key, value in matches:
            key_clean = key.strip().lower()
            value_clean = value.strip()
            # 映射常见键名
            if key_clean in ("action", "决策", "动作", "操作"):
                data["action"] = value_clean
            elif key_clean in ("symbol", "标的", "代码", "股票"):
                data["symbol"] = value_clean
            elif key_clean in ("quantity", "数量", "股数", "amount"):
                data["quantity"] = value_clean
            elif key_clean in ("price", "价格", "目标价"):
                data["price"] = value_clean
            elif key_clean in ("confidence", "置信度", "信心"):
                data["confidence"] = value_clean
            elif key_clean in ("reasoning", "理由", "分析", "reason"):
                data["reasoning"] = value_clean

        if "action" not in data:
            return None

        return self._parse_json_dict(data, text)

    def _try_parse_natural_language(self, text: str) -> Optional[ParsedDecision]:
        """尝试从自然语言中解析决策。"""
        text_lower = text.lower()

        # 匹配动作
        action = None
        for action_name, keywords in self.ACTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    action = DecisionAction(action_name)
                    break
            if action is not None:
                break

        if action is None:
            return None

        # 提取symbol - 常见股票代码格式 (1-5个大写字母)
        symbol_match = re.search(r"\b([A-Z]{1,5})\b", text)
        symbol = symbol_match.group(1) if symbol_match else self._default_symbol

        # 提取quantity
        quantity = None
        qty_patterns = [
            r"(\d+)\s*股",
            r"(\d+)\s*shares?",
            r"买入\s*(\d+)",
            r"卖出\s*(\d+)",
            r"数量[：:]\s*(\d+)",
            r"quantity[：:]\s*(\d+)",
        ]
        for pattern in qty_patterns:
            qty_match = re.search(pattern, text, re.IGNORECASE)
            if qty_match:
                quantity = float(qty_match.group(1))
                break

        # 提取price
        price = None
        price_patterns = [
            r"(?:价格|price)[：:]\s*(\d+(?:\.\d+)?)",
            r"(?:目标价|target)[：:]\s*(\d+(?:\.\d+)?)",
            r"(?:以|at)\s*(\d+(?:\.\d+)?)\s*(?:元|美元|USD)?\s*(?:的价格|的价格)?",
        ]
        for pattern in price_patterns:
            price_match = re.search(pattern, text, re.IGNORECASE)
            if price_match:
                price = float(price_match.group(1))
                break

        # 提取confidence
        confidence = self.parse_confidence(text)

        # 提取reasoning (取前200字符作为理由)
        reasoning = text[:500].replace("\n", " ").strip()

        return ParsedDecision(
            action=action,
            symbol=symbol,
            quantity=quantity,
            price=price,
            confidence=round(confidence, 4),
            reasoning=reasoning,
            raw_response=text,
        )

    def _match_action(self, action_str: str) -> Optional[DecisionAction]:
        """将字符串匹配为 DecisionAction 枚举。"""
        if not action_str:
            return None
        action_str = action_str.strip().lower()
        for action_name, keywords in self.ACTION_KEYWORDS.items():
            if action_str == action_name or action_str in keywords:
                return DecisionAction(action_name)
        # 直接枚举匹配
        try:
            return DecisionAction(action_str)
        except ValueError:
            return None


# ===========================================================================
# AIAgentEngine - AI Agent引擎主类
# ===========================================================================


@dataclass
class DecisionHistoryEntry:
    """决策历史记录条目"""
    decision: Decision
    model_provider: str
    model_name: str
    timestamp: datetime = field(default_factory=datetime.now)


class AIAgentEngine:
    """AI Agent引擎

    整合 PromptManager、ContextBuilder、DecisionParser，
    提供完整的AI决策流程: 上下文构建 -> Prompt渲染 -> 模型调用 -> 输出解析。
    支持多模型并行调用和决策投票。
    """

    def __init__(
        self,
        prompt_manager: Optional[PromptManager] = None,
        context_builder: Optional[ContextBuilder] = None,
        decision_parser: Optional[DecisionParser] = None,
        default_system_prompt: Optional[str] = None,
    ) -> None:
        """
        初始化AIAgentEngine。

        Args:
            prompt_manager:       PromptManager实例，为None时自动创建。
            context_builder:      ContextBuilder实例，为None时自动创建。
            decision_parser:      DecisionParser实例，为None时自动创建。
            default_system_prompt: 默认系统提示词。
        """
        self._prompt_manager = prompt_manager or PromptManager()
        self._context_builder = context_builder or ContextBuilder()
        self._decision_parser = decision_parser or DecisionParser()
        self._default_system_prompt = default_system_prompt or (
            "你是一个专业的量化交易AI助手。请根据提供的市场数据和账户信息，"
            "做出交易决策。你的回复必须包含以下字段：\n"
            "- action: 决策动作 (buy/sell/hold)\n"
            "- symbol: 标的代码\n"
            "- quantity: 建议数量 (可选)\n"
            "- price: 建议价格 (可选)\n"
            "- confidence: 置信度 (0.0-1.0)\n"
            "- reasoning: 决策理由\n\n"
            "请以JSON格式回复。"
        )
        # 注册的AI模型适配器 {name: adapter}
        self._models: Dict[str, BaseAIModelAdapter] = {}
        # 决策历史
        self._decision_history: List[DecisionHistoryEntry] = []
        self._max_history_size: int = 1000

        logger.info("AIAgentEngine 初始化完成")

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def prompt_manager(self) -> PromptManager:
        return self._prompt_manager

    @property
    def context_builder(self) -> ContextBuilder:
        return self._context_builder

    @property
    def decision_parser(self) -> DecisionParser:
        return self._decision_parser

    @property
    def decision_history(self) -> List[DecisionHistoryEntry]:
        return list(self._decision_history)

    # ------------------------------------------------------------------
    # 模型管理
    # ------------------------------------------------------------------

    def register_model(
        self,
        name: str,
        adapter: BaseAIModelAdapter,
    ) -> None:
        """注册AI模型适配器。

        Args:
            name:    模型注册名称。
            adapter: BaseAIModelAdapter 实例。
        """
        if not adapter.is_available():
            logger.warning(
                "注册的模型不可用: name={}, provider={}, model={}",
                name,
                adapter.provider.value,
                adapter.model_name,
            )
        self._models[name] = adapter
        logger.info(
            "AI模型已注册: name={}, provider={}, model={}",
            name,
            adapter.provider.value,
            adapter.model_name,
        )

    def unregister_model(self, name: str) -> None:
        """注销AI模型适配器。

        Args:
            name: 模型注册名称。
        """
        if name in self._models:
            del self._models[name]
            logger.info("AI模型已注销: name={}", name)
        else:
            logger.warning("AI模型不存在: name={}", name)

    def get_model(self, name: str) -> Optional[BaseAIModelAdapter]:
        """获取已注册的模型适配器。"""
        return self._models.get(name)

    def list_models(self) -> List[Dict[str, str]]:
        """列出所有已注册的模型。"""
        return [
            {
                "name": name,
                "provider": adapter.provider.value,
                "model": adapter.model_name,
                "available": str(adapter.is_available()),
            }
            for name, adapter in self._models.items()
        ]

    # ------------------------------------------------------------------
    # 核心决策方法
    # ------------------------------------------------------------------

    async def make_decision(
        self,
        symbol: str,
        account_id: Optional[str] = None,
        model_name: Optional[str] = None,
        template_name: Optional[str] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
    ) -> Decision:
        """执行一次AI决策。

        流程:
        1. 构建决策上下文
        2. 渲染Prompt模板
        3. 调用AI模型
        4. 解析模型输出
        5. 记录决策历史

        Args:
            symbol:           目标标的代码。
            account_id:       账户ID。
            model_name:       使用的模型名称，None则使用第一个可用模型。
            template_name:    Prompt模板名称。
            extra_variables:  额外的Prompt变量。
            system_prompt:    系统提示词，None则使用默认。

        Returns:
            Decision 决策结果。

        Raises:
            RuntimeError: 没有可用的模型。
        """
        import time

        start_time = time.time()

        # 选择模型
        adapter = self._select_model(model_name)
        if adapter is None:
            raise RuntimeError(
                f"没有可用的AI模型。已注册: {list(self._models.keys())}"
            )

        # 构建上下文
        context = self._context_builder.build_context(symbol, account_id)
        if extra_variables:
            context.update(extra_variables)

        # 渲染Prompt
        if template_name:
            try:
                user_prompt = self._prompt_manager.render(
                    template_name, context
                )
            except (KeyError, ValueError) as e:
                logger.warning("模板渲染失败: {}, 使用默认上下文", e)
                user_prompt = self._context_builder.build_context_str(
                    symbol, account_id
                )
        else:
            user_prompt = self._context_builder.build_context_str(
                symbol, account_id
            )

        sys_prompt = system_prompt or self._default_system_prompt

        # 调用模型
        logger.info(
            "开始AI决策: symbol={}, model={}/{}, account={}",
            symbol,
            adapter.provider.value,
            adapter.model_name,
            account_id,
        )

        try:
            response = await adapter.chat_with_system(
                system_prompt=sys_prompt,
                user_message=user_prompt,
            )
        except Exception as e:
            logger.error("AI模型调用失败: {} -> {}", adapter.model_name, e)
            latency_ms = int((time.time() - start_time) * 1000)
            decision = Decision(
                decision_id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                model=adapter.model_name,
                provider=adapter.provider.value,
                action=DecisionAction.HOLD,
                symbol=symbol,
                confidence=0.0,
                reasoning=f"模型调用失败: {str(e)}",
                raw_response="",
                latency_ms=latency_ms,
                prompt=user_prompt,
            )
            self._add_to_history(decision, adapter.provider.value, adapter.model_name)
            return decision

        latency_ms = int((time.time() - start_time) * 1000)

        # 解析输出
        parsed = self._decision_parser.parse(response.content)
        decision = parsed.to_decision(
            model=adapter.model_name,
            provider=adapter.provider.value,
            latency_ms=latency_ms,
            prompt=user_prompt,
        )

        # 补充symbol (如果解析失败)
        if decision.symbol is None:
            decision.symbol = symbol

        logger.info(
            "AI决策完成: action={}, symbol={}, confidence={:.2f}, latency={}ms",
            decision.action.value,
            decision.symbol,
            decision.confidence,
            latency_ms,
        )

        # 记录历史
        self._add_to_history(decision, adapter.provider.value, adapter.model_name)

        return decision

    async def make_decision_multi_model(
        self,
        symbol: str,
        account_id: Optional[str] = None,
        model_names: Optional[List[str]] = None,
        template_name: Optional[str] = None,
        extra_variables: Optional[Dict[str, Any]] = None,
        voting_strategy: str = "majority",
    ) -> Decision:
        """多模型并行决策，通过投票机制得出最终决策。

        Args:
            symbol:           目标标的代码。
            account_id:       账户ID。
            model_names:      参与决策的模型名称列表，None则使用所有已注册模型。
            template_name:    Prompt模板名称。
            extra_variables:  额外Prompt变量。
            voting_strategy:  投票策略: "majority"(多数) / "confidence"(最高置信度) / "unanimous"(一致)。

        Returns:
            最终的Decision决策结果。

        Raises:
            RuntimeError: 没有可用的模型。
        """
        # 确定参与模型
        if model_names:
            models_to_use = {
                name: self._models[name]
                for name in model_names
                if name in self._models
            }
        else:
            models_to_use = dict(self._models)

        if not models_to_use:
            raise RuntimeError("没有可用的AI模型进行多模型决策")

        logger.info(
            "开始多模型并行决策: symbol={}, models={}, strategy={}",
            symbol,
            list(models_to_use.keys()),
            voting_strategy,
        )

        # 并行调用所有模型
        tasks = []
        for name, adapter in models_to_use.items():
            task = self._call_single_model(
                adapter=adapter,
                symbol=symbol,
                account_id=account_id,
                template_name=template_name,
                extra_variables=extra_variables,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集成功的决策
        successful_decisions: List[Decision] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                model_name = list(models_to_use.keys())[i]
                logger.error(
                    "多模型决策 - 模型调用失败: {} -> {}", model_name, result
                )
            elif isinstance(result, Decision):
                successful_decisions.append(result)

        if not successful_decisions:
            logger.error("多模型决策 - 所有模型均失败")
            return Decision(
                decision_id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                model="multi_model",
                provider="multi",
                action=DecisionAction.HOLD,
                symbol=symbol,
                confidence=0.0,
                reasoning="所有模型调用均失败",
            )

        # 投票
        final_decision = self._vote(
            successful_decisions, voting_strategy, symbol
        )

        logger.info(
            "多模型决策完成: 最终action={}, symbol={}, confidence={:.2f}, "
            "参与模型={}/成功={}",
            final_decision.action.value,
            final_decision.symbol,
            final_decision.confidence,
            len(models_to_use),
            len(successful_decisions),
        )

        return final_decision

    # ------------------------------------------------------------------
    # 决策历史
    # ------------------------------------------------------------------

    def get_decision_history(
        self,
        limit: int = 100,
        symbol: Optional[str] = None,
        action: Optional[DecisionAction] = None,
    ) -> List[DecisionHistoryEntry]:
        """查询决策历史。

        Args:
            limit:  返回记录数上限。
            symbol: 按标的筛选。
            action: 按动作筛选。

        Returns:
            决策历史列表 (最新在前)。
        """
        history = self._decision_history
        if symbol:
            history = [h for h in history if h.decision.symbol == symbol]
        if action:
            history = [h for h in history if h.decision.action == action]
        return list(reversed(history[-limit:]))

    def clear_history(self) -> None:
        """清除决策历史。"""
        self._decision_history.clear()
        logger.info("决策历史已清除")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _select_model(
        self, model_name: Optional[str] = None
    ) -> Optional[BaseAIModelAdapter]:
        """选择要使用的模型。"""
        if model_name and model_name in self._models:
            return self._models[model_name]

        # 返回第一个可用的模型
        for name, adapter in self._models.items():
            if adapter.is_available():
                return adapter

        # 没有可用的，返回第一个注册的
        if self._models:
            return next(iter(self._models.values()))

        return None

    async def _call_single_model(
        self,
        adapter: BaseAIModelAdapter,
        symbol: str,
        account_id: Optional[str],
        template_name: Optional[str],
        extra_variables: Optional[Dict[str, Any]],
    ) -> Decision:
        """调用单个模型获取决策。"""
        import time

        start_time = time.time()

        context = self._context_builder.build_context(symbol, account_id)
        if extra_variables:
            context.update(extra_variables)

        if template_name:
            try:
                user_prompt = self._prompt_manager.render(
                    template_name, context
                )
            except (KeyError, ValueError):
                user_prompt = self._context_builder.build_context_str(
                    symbol, account_id
                )
        else:
            user_prompt = self._context_builder.build_context_str(
                symbol, account_id
            )

        response = await adapter.chat_with_system(
            system_prompt=self._default_system_prompt,
            user_message=user_prompt,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        parsed = self._decision_parser.parse(response.content)
        decision = parsed.to_decision(
            model=adapter.model_name,
            provider=adapter.provider.value,
            latency_ms=latency_ms,
            prompt=user_prompt,
        )

        if decision.symbol is None:
            decision.symbol = symbol

        self._add_to_history(decision, adapter.provider.value, adapter.model_name)
        return decision

    def _vote(
        self,
        decisions: List[Decision],
        strategy: str,
        default_symbol: str,
    ) -> Decision:
        """对多个决策进行投票。

        Args:
            decisions:      决策列表。
            strategy:       投票策略。
            default_symbol: 默认标的代码。

        Returns:
            最终决策。
        """
        if len(decisions) == 1:
            return decisions[0]

        if strategy == "confidence":
            # 选择置信度最高的决策
            best = max(decisions, key=lambda d: d.confidence)
            best.reasoning = (
                f"[多模型-最高置信度] 原始理由: {best.reasoning} | "
                f"参与模型数: {len(decisions)}"
            )
            return best

        if strategy == "unanimous":
            # 所有模型必须一致
            actions = [d.action for d in decisions]
            if len(set(actions)) == 1:
                best = max(decisions, key=lambda d: d.confidence)
                best.reasoning = (
                    f"[多模型-一致决策] 原始理由: {best.reasoning} | "
                    f"参与模型数: {len(decisions)}"
                )
                return best
            else:
                # 不一致则HOLD
                return Decision(
                    decision_id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    model="multi_model",
                    provider="multi",
                    action=DecisionAction.HOLD,
                    symbol=default_symbol,
                    confidence=0.3,
                    reasoning=(
                        f"多模型决策不一致: {[(d.model, d.action.value) for d in decisions]}, "
                        f"默认持有"
                    ),
                )

        # 默认: majority (多数投票)
        action_counts: Dict[DecisionAction, int] = defaultdict(int)
        for d in decisions:
            action_counts[d.action] += 1

        winning_action = max(action_counts, key=lambda a: action_counts[a])
        winning_decisions = [d for d in decisions if d.action == winning_action]

        # 从获胜动作中选置信度最高的
        best = max(winning_decisions, key=lambda d: d.confidence)
        avg_confidence = sum(d.confidence for d in winning_decisions) / len(
            winning_decisions
        )

        return Decision(
            decision_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            model="multi_model",
            provider="multi",
            action=winning_action,
            symbol=best.symbol or default_symbol,
            quantity=best.quantity,
            price=best.price,
            confidence=round(avg_confidence, 4),
            reasoning=(
                f"[多模型-多数投票] 动作={winning_action.value}, "
                f"票数={action_counts[winning_action]}/{len(decisions)}, "
                f"原始理由: {best.reasoning}"
            ),
            raw_response=json.dumps(
                [
                    {
                        "model": d.model,
                        "action": d.action.value,
                        "confidence": d.confidence,
                        "symbol": d.symbol,
                    }
                    for d in decisions
                ],
                ensure_ascii=False,
            ),
        )

    def _add_to_history(
        self,
        decision: Decision,
        provider: str,
        model_name: str,
    ) -> None:
        """添加决策到历史记录。"""
        entry = DecisionHistoryEntry(
            decision=decision,
            model_provider=provider,
            model_name=model_name,
        )
        self._decision_history.append(entry)

        # 限制历史大小
        if len(self._decision_history) > self._max_history_size:
            self._decision_history = self._decision_history[-self._max_history_size:]
