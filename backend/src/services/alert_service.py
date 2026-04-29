"""告警服务模块

提供告警规则管理、告警触发和通知功能。
支持多种通知方式：Web 界面通知、邮件通知、Webhook 通知。
"""

from __future__ import annotations

import asyncio
import json
import smtplib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# 尝试导入核心模块
# ---------------------------------------------------------------------------

try:
    from src.core.event_bus import EventBus

    _HAS_EVENT_BUS = True
except ImportError:
    _HAS_EVENT_BUS = False


# ---------------------------------------------------------------------------
# 事件总线桩实现
# ---------------------------------------------------------------------------

class _EventBusStub:
    """事件总线桩实现。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    async def publish(self, event_type: str, data: Any = None) -> None:
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"事件处理失败: {event_type}, 错误: {e}")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class AlertSeverity(str, Enum):
    """告警严重级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotifyChannel(str, Enum):
    """通知渠道"""
    WEB = "web"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    name: str
    description: str = ""
    severity: AlertSeverity = AlertSeverity.MEDIUM
    condition: str = ""  # 条件表达式，如 "drawdown_pct > 5"
    channels: List[NotifyChannel] = field(default_factory=lambda: [NotifyChannel.WEB])
    is_enabled: bool = True
    cooldown_seconds: int = 300  # 冷却时间（秒），防止频繁告警
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # 内部状态
    _last_triggered: Optional[datetime] = field(default=None, repr=False)


@dataclass
class AlertRecord:
    """告警记录"""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    title: str
    message: str
    channels: List[NotifyChannel]
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    notified: bool = False
    notification_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailConfig:
    """邮件通知配置"""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    use_tls: bool = True
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)


@dataclass
class WebhookConfig:
    """Webhook 通知配置"""
    url: str = ""
    method: str = "POST"
    headers: Dict[str, str] = field(default_factory=dict)
    secret: str = ""  # 签名密钥


# ---------------------------------------------------------------------------
# AlertService
# ---------------------------------------------------------------------------

class AlertService:
    """告警服务

    提供告警规则管理、告警触发和通知功能。

    Usage::

        service = AlertService()
        await service.initialize()

        # 添加告警规则
        rule = await service.add_alert_rule(
            name="大额亏损告警",
            condition="drawdown_pct > 5",
            severity=AlertSeverity.HIGH,
            channels=[NotifyChannel.WEB, NotifyChannel.EMAIL],
        )

        # 触发告警
        await service.check_alert_rules({"drawdown_pct": 6.2})

        # 手动发送告警
        await service.send_alert(
            title="紧急通知",
            message="账户出现异常",
            severity=AlertSeverity.CRITICAL,
        )

        # 查询告警历史
        history = await service.get_alert_history()

        await service.shutdown()
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        email_config: Optional[EmailConfig] = None,
        webhook_config: Optional[WebhookConfig] = None,
    ) -> None:
        """
        初始化告警服务。

        Args:
            event_bus:      事件总线实例。
            email_config:   邮件通知配置。
            webhook_config: Webhook 通知配置。
        """
        self._event_bus = event_bus or (_EventBusStub() if not _HAS_EVENT_BUS else None)
        self._email_config = email_config or EmailConfig()
        self._webhook_config = webhook_config or WebhookConfig()

        # 告警规则
        self._rules: Dict[str, AlertRule] = {}
        # 告警历史
        self._history: List[AlertRecord] = []
        self._max_history: int = 10000  # 最大历史记录数

        # Web 通知回调
        self._web_callbacks: List[Callable[[AlertRecord], Any]] = []

        self._initialized = False

        logger.info("AlertService 已创建")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """初始化告警服务，加载持久化的规则。"""
        if self._initialized:
            return

        try:
            # 从数据库加载规则
            await self._load_rules_from_db()

            # 注册事件监听
            if self._event_bus:
                self._event_bus.subscribe("trading_alert", self._on_trading_alert)
                self._event_bus.subscribe("order_filled", self._on_order_filled)
                self._event_bus.subscribe("decision_executed", self._on_decision_executed)

            self._initialized = True
            logger.info(f"AlertService 初始化完成, 规则数={len(self._rules)}")

        except Exception as e:
            logger.error(f"AlertService 初始化失败: {e}")
            self._initialized = True

    async def shutdown(self) -> None:
        """关闭告警服务。"""
        if self._event_bus:
            try:
                self._event_bus.unsubscribe("trading_alert", self._on_trading_alert)
                self._event_bus.unsubscribe("order_filled", self._on_order_filled)
                self._event_bus.unsubscribe("decision_executed", self._on_decision_executed)
            except Exception:
                pass

        self._initialized = False
        logger.info("AlertService 已关闭")

    # ------------------------------------------------------------------
    # 告警规则管理
    # ------------------------------------------------------------------

    async def add_alert_rule(
        self,
        name: str,
        condition: str = "",
        description: str = "",
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        channels: Optional[List[NotifyChannel]] = None,
        cooldown_seconds: int = 300,
        is_enabled: bool = True,
    ) -> AlertRule:
        """添加告警规则。

        Args:
            name:             规则名称。
            condition:        触发条件表达式。
            description:      规则描述。
            severity:         告警严重级别。
            channels:         通知渠道列表。
            cooldown_seconds: 冷却时间（秒）。
            is_enabled:       是否启用。

        Returns:
            新创建的 AlertRule 对象。
        """
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"
        rule = AlertRule(
            rule_id=rule_id,
            name=name,
            description=description,
            severity=severity,
            condition=condition,
            channels=channels or [NotifyChannel.WEB],
            is_enabled=is_enabled,
            cooldown_seconds=cooldown_seconds,
        )

        self._rules[rule_id] = rule

        # 持久化
        try:
            await self._save_rule_to_db(rule)
        except Exception as e:
            logger.error(f"规则持久化失败: {rule_id}, 错误: {e}")

        logger.info(f"告警规则已添加: {name} (ID={rule_id}, 级别={severity.value})")
        return rule

    async def remove_alert_rule(self, rule_id: str) -> bool:
        """移除告警规则。

        Args:
            rule_id: 规则ID。

        Returns:
            是否移除成功。
        """
        rule = self._rules.pop(rule_id, None)
        if rule is None:
            logger.warning(f"告警规则不存在: {rule_id}")
            return False

        try:
            await self._delete_rule_from_db(rule_id)
        except Exception as e:
            logger.error(f"规则删除持久化失败: {rule_id}, 错误: {e}")

        logger.info(f"告警规则已移除: {rule.name} (ID={rule_id})")
        return True

    async def update_alert_rule(
        self,
        rule_id: str,
        **updates,
    ) -> Optional[AlertRule]:
        """更新告警规则。

        Args:
            rule_id:  规则ID。
            **updates: 要更新的字段。

        Returns:
            更新后的 AlertRule 对象，不存在返回 None。
        """
        rule = self._rules.get(rule_id)
        if rule is None:
            return None

        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        rule.updated_at = datetime.now()

        try:
            await self._save_rule_to_db(rule)
        except Exception as e:
            logger.error(f"规则更新持久化失败: {rule_id}, 错误: {e}")

        logger.info(f"告警规则已更新: {rule.name} (ID={rule_id})")
        return rule

    def get_alert_rules(
        self,
        enabled_only: bool = False,
    ) -> List[AlertRule]:
        """获取告警规则列表。

        Args:
            enabled_only: 是否仅返回启用的规则。

        Returns:
            AlertRule 列表。
        """
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.is_enabled]
        return rules

    def get_alert_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取指定告警规则。

        Args:
            rule_id: 规则ID。

        Returns:
            AlertRule 对象，不存在返回 None。
        """
        return self._rules.get(rule_id)

    # ------------------------------------------------------------------
    # 告警触发
    # ------------------------------------------------------------------

    async def check_alert_rules(self, context: Dict[str, Any]) -> List[AlertRecord]:
        """检查所有告警规则并触发匹配的告警。

        Args:
            context: 上下文数据字典，用于条件判断。

        Returns:
            触发的 AlertRecord 列表。
        """
        triggered: List[AlertRecord] = []

        for rule in self._rules.values():
            if not rule.is_enabled:
                continue

            # 检查冷却时间
            if rule._last_triggered:
                elapsed = (datetime.now() - rule._last_triggered).total_seconds()
                if elapsed < rule.cooldown_seconds:
                    continue

            # 评估条件
            if self._evaluate_condition(rule.condition, context):
                rule._last_triggered = datetime.now()

                record = await self.send_alert(
                    title=f"[{rule.name}] 规则触发",
                    message=f"告警规则 '{rule.name}' 已触发。条件: {rule.condition}",
                    severity=rule.severity,
                    channels=rule.channels,
                    data={
                        "rule_id": rule.rule_id,
                        "rule_name": rule.name,
                        "condition": rule.condition,
                        "context": context,
                    },
                )
                triggered.append(record)

        if triggered:
            logger.info(f"告警检查完成: 触发 {len(triggered)} 条告警")

        return triggered

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        channels: Optional[List[NotifyChannel]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> AlertRecord:
        """发送告警通知。

        Args:
            title:    告警标题。
            message:  告警内容。
            severity: 告警严重级别。
            channels: 通知渠道列表。
            data:     附加数据。

        Returns:
            AlertRecord 告警记录。
        """
        alert_id = f"alert_{uuid.uuid4().hex[:12]}"
        channels = channels or [NotifyChannel.WEB]

        record = AlertRecord(
            alert_id=alert_id,
            rule_id=data.get("rule_id", "") if data else "",
            rule_name=data.get("rule_name", "") if data else "",
            severity=severity,
            title=title,
            message=message,
            channels=channels,
            data=data or {},
            created_at=datetime.now(),
        )

        # 按渠道发送通知
        notification_results: Dict[str, Any] = {}

        for channel in channels:
            try:
                if channel == NotifyChannel.WEB:
                    result = await self._notify_web(record)
                elif channel == NotifyChannel.EMAIL:
                    result = await self._notify_email(record)
                elif channel == NotifyChannel.WEBHOOK:
                    result = await self._notify_webhook(record)
                else:
                    result = {"success": False, "error": f"未知渠道: {channel}"}

                notification_results[channel.value] = result

            except Exception as e:
                logger.error(f"发送 {channel.value} 通知失败: {e}")
                notification_results[channel.value] = {
                    "success": False,
                    "error": str(e),
                }

        record.notified = True
        record.notification_results = notification_results

        # 保存到历史
        self._history.append(record)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 通过事件总线发布
        if self._event_bus:
            await self._event_bus.publish("alert_sent", {
                "alert_id": alert_id,
                "title": title,
                "severity": severity.value,
                "channels": [c.value for c in channels],
            })

        # 日志记录
        log_fn = {
            AlertSeverity.LOW: logger.info,
            AlertSeverity.MEDIUM: logger.warning,
            AlertSeverity.HIGH: logger.warning,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(severity, logger.info)

        log_fn(f"[告警] {severity.value.upper()} | {title} | {message}")

        return record

    # ------------------------------------------------------------------
    # 告警历史
    # ------------------------------------------------------------------

    def get_alert_history(
        self,
        severity: Optional[AlertSeverity] = None,
        rule_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询告警历史。

        Args:
            severity:  按严重级别筛选。
            rule_id:   按规则ID筛选。
            start_time: 起始时间。
            end_time:   结束时间。
            skip:       跳过记录数。
            limit:      返回记录数上限。

        Returns:
            包含 items, total, skip, limit 的字典。
        """
        records = list(self._history)

        if severity:
            records = [r for r in records if r.severity == severity]
        if rule_id:
            records = [r for r in records if r.rule_id == rule_id]
        if start_time:
            records = [r for r in records if r.created_at >= start_time]
        if end_time:
            records = [r for r in records if r.created_at <= end_time]

        total = len(records)
        records = records[skip:skip + limit]

        items = [self._record_to_dict(r) for r in records]

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """查询单条告警记录。

        Args:
            alert_id: 告警ID。

        Returns:
            告警记录字典，不存在返回 None。
        """
        for record in self._history:
            if record.alert_id == alert_id:
                return self._record_to_dict(record)
        return None

    def clear_history(self) -> int:
        """清除告警历史。

        Returns:
            清除的记录数。
        """
        count = len(self._history)
        self._history.clear()
        logger.info(f"告警历史已清除: {count} 条记录")
        return count

    # ------------------------------------------------------------------
    # Web 通知回调管理
    # ------------------------------------------------------------------

    def add_web_callback(
        self,
        callback: Callable[[AlertRecord], Any],
    ) -> None:
        """添加 Web 通知回调函数。

        Args:
            callback: 回调函数，接收 AlertRecord 参数。
        """
        self._web_callbacks.append(callback)
        logger.debug("Web 通知回调已添加")

    def remove_web_callback(
        self,
        callback: Callable[[AlertRecord], Any],
    ) -> None:
        """移除 Web 通知回调函数。"""
        try:
            self._web_callbacks.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # 通知渠道实现
    # ------------------------------------------------------------------

    async def _notify_web(self, record: AlertRecord) -> Dict[str, Any]:
        """Web 界面通知。

        通过注册的回调函数推送告警到 Web 前端。

        Args:
            record: 告警记录。

        Returns:
            通知结果字典。
        """
        notified_count = 0
        errors: List[str] = []

        for callback in self._web_callbacks:
            try:
                result = callback(record)
                if asyncio.iscoroutine(result):
                    await result
                notified_count += 1
            except Exception as e:
                errors.append(str(e))

        return {
            "success": notified_count > 0,
            "notified_count": notified_count,
            "errors": errors,
        }

    async def _notify_email(self, record: AlertRecord) -> Dict[str, Any]:
        """邮件通知。

        Args:
            record: 告警记录。

        Returns:
            通知结果字典。
        """
        config = self._email_config

        if not config.smtp_user or not config.to_addrs:
            return {
                "success": False,
                "error": "邮件配置不完整（缺少 smtp_user 或 to_addrs）",
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[AI Trading Alert] [{record.severity.value.upper()}] {record.title}"
            msg["From"] = config.from_addr or config.smtp_user
            msg["To"] = ", ".join(config.to_addrs)

            # 纯文本内容
            text_content = (
                f"告警级别: {record.severity.value.upper()}\n"
                f"告警标题: {record.title}\n"
                f"告警内容: {record.message}\n"
                f"告警时间: {record.created_at.isoformat()}\n"
                f"告警ID:   {record.alert_id}\n"
            )
            if record.data:
                text_content += f"\n附加数据:\n{json.dumps(record.data, ensure_ascii=False, indent=2)}"

            msg.attach(MIMEText(text_content, "plain", "utf-8"))

            # HTML 内容
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333;">
                <div style="padding: 20px; background-color: #f5f5f5; border-radius: 8px;">
                    <h2 style="color: {'#d32f2f' if record.severity == AlertSeverity.CRITICAL else '#f57c00' if record.severity == AlertSeverity.HIGH else '#333'};">
                        [{record.severity.value.upper()}] {record.title}
                    </h2>
                    <p><strong>告警内容:</strong> {record.message}</p>
                    <p><strong>告警时间:</strong> {record.created_at.isoformat()}</p>
                    <p><strong>告警ID:</strong> {record.alert_id}</p>
                    {'<pre style="background: #eee; padding: 10px; border-radius: 4px;">' + json.dumps(record.data, ensure_ascii=False, indent=2) + '</pre>' if record.data else ''}
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # 发送邮件（在线程池中执行以避免阻塞）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email_sync, msg, config)

            logger.info(f"邮件通知已发送: {record.title} -> {config.to_addrs}")
            return {"success": True, "recipients": config.to_addrs}

        except Exception as e:
            logger.error(f"邮件通知发送失败: {e}")
            return {"success": False, "error": str(e)}

    def _send_email_sync(self, msg: MIMEMultipart, config: EmailConfig) -> None:
        """同步发送邮件（在线程池中调用）。"""
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            if config.use_tls:
                server.starttls()
            if config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            server.sendmail(
                config.from_addr or config.smtp_user,
                config.to_addrs,
                msg.as_string(),
            )

    async def _notify_webhook(self, record: AlertRecord) -> Dict[str, Any]:
        """Webhook 通知。

        Args:
            record: 告警记录。

        Returns:
            通知结果字典。
        """
        config = self._webhook_config

        if not config.url:
            return {
                "success": False,
                "error": "Webhook URL 未配置",
            }

        try:
            import aiohttp

            payload = {
                "alert_id": record.alert_id,
                "severity": record.severity.value,
                "title": record.title,
                "message": record.message,
                "data": record.data,
                "created_at": record.created_at.isoformat(),
            }

            headers = {
                "Content-Type": "application/json",
                **config.headers,
            }

            # 签名（如果配置了密钥）
            if config.secret:
                import hashlib
                import hmac
                body_str = json.dumps(payload, ensure_ascii=False)
                signature = hmac.new(
                    config.secret.encode("utf-8"),
                    body_str.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Signature"] = signature

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    config.url,
                    json=payload,
                    headers=headers,
                ) as response:
                    status = response.status
                    body = await response.text()

                    if 200 <= status < 300:
                        logger.info(f"Webhook 通知已发送: {config.url} (HTTP {status})")
                        return {"success": True, "status": status, "body": body}
                    else:
                        logger.warning(f"Webhook 通知失败: {config.url} (HTTP {status})")
                        return {"success": False, "status": status, "body": body}

        except ImportError:
            return {"success": False, "error": "aiohttp 未安装，无法发送 Webhook"}
        except Exception as e:
            logger.error(f"Webhook 通知发送失败: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    async def _on_trading_alert(self, data: Any) -> None:
        """处理交易告警事件。"""
        if not isinstance(data, dict):
            return

        severity_map = {
            "info": AlertSeverity.LOW,
            "warning": AlertSeverity.MEDIUM,
            "critical": AlertSeverity.CRITICAL,
        }
        severity = severity_map.get(data.get("level", ""), AlertSeverity.MEDIUM)

        await self.send_alert(
            title=data.get("title", "交易告警"),
            message=data.get("message", ""),
            severity=severity,
            channels=[NotifyChannel.WEB],
            data=data,
        )

    async def _on_order_filled(self, data: Any) -> None:
        """处理订单成交事件。"""
        if not isinstance(data, dict):
            return

        await self.send_alert(
            title=f"订单成交: {data.get('symbol', '')}",
            message=f"订单 {data.get('order_id', '')} 已成交",
            severity=AlertSeverity.LOW,
            channels=[NotifyChannel.WEB],
            data=data,
        )

    async def _on_decision_executed(self, data: Any) -> None:
        """处理决策执行事件。"""
        if not isinstance(data, dict):
            return

        confidence = data.get("confidence", 0)
        if confidence < 0.5:
            severity = AlertSeverity.LOW
        elif confidence < 0.8:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        await self.send_alert(
            title=f"决策执行: {data.get('side', '').upper()} {data.get('symbol', '')}",
            message=f"置信度={confidence:.2f}, 数量={data.get('quantity', 0)}",
            severity=severity,
            channels=[NotifyChannel.WEB],
            data=data,
        )

    # ------------------------------------------------------------------
    # 条件评估
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
        """安全评估告警条件表达式。

        支持简单的比较表达式，如:
        - "drawdown_pct > 5"
        - "total_pnl < -1000"
        - "confidence < 0.3"

        Args:
            condition: 条件表达式字符串。
            context:   上下文变量字典。

        Returns:
            条件是否满足。
        """
        if not condition or not condition.strip():
            return False

        try:
            # 安全检查：仅允许比较操作符和变量名
            import re
            safe_pattern = r"^[\w\s.]+\s*(>|<|>=|<=|==|!=)\s*[\w\s.\-]+$"
            if not re.match(safe_pattern, condition.strip()):
                logger.warning(f"告警条件表达式不安全，已跳过: {condition}")
                return False

            # 构建安全的评估环境
            safe_globals: Dict[str, Any] = {"__builtins__": {}}
            safe_locals = dict(context)

            result = eval(condition.strip(), safe_globals, safe_locals)  # noqa: S307
            return bool(result)

        except Exception as e:
            logger.warning(f"告警条件评估失败: {condition}, 错误: {e}")
            return False

    # ------------------------------------------------------------------
    # 数据库持久化
    # ------------------------------------------------------------------

    async def _load_rules_from_db(self) -> None:
        """从数据库加载告警规则。"""
        try:
            from src.database.connection import get_async_session
            from sqlalchemy import select
            from src.database.schema import SystemConfigORM

            async with get_async_session() as session:
                stmt = select(SystemConfigORM).where(
                    SystemConfigORM.key.like("alert_rule_%")
                )
                result = await session.execute(stmt)
                orms = result.scalars().all()

                for orm in orms:
                    try:
                        data = json.loads(orm.value)
                        rule = AlertRule(
                            rule_id=data.get("rule_id", ""),
                            name=data.get("name", ""),
                            description=data.get("description", ""),
                            severity=AlertSeverity(data.get("severity", "medium")),
                            condition=data.get("condition", ""),
                            channels=[
                                NotifyChannel(c) for c in data.get("channels", ["web"])
                            ],
                            is_enabled=data.get("is_enabled", True),
                            cooldown_seconds=data.get("cooldown_seconds", 300),
                            created_at=orm.created_at,
                            updated_at=orm.updated_at,
                        )
                        self._rules[rule.rule_id] = rule
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        logger.warning(f"解析告警规则失败: {orm.key}, 错误: {e}")

                logger.debug(f"从数据库加载了 {len(orms)} 条告警规则")

        except Exception as e:
            logger.warning(f"从数据库加载告警规则失败: {e}")

    async def _save_rule_to_db(self, rule: AlertRule) -> None:
        """保存告警规则到数据库。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import SystemConfigORM

        key = f"alert_rule_{rule.rule_id}"
        value = json.dumps({
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "severity": rule.severity.value,
            "condition": rule.condition,
            "channels": [c.value for c in rule.channels],
            "is_enabled": rule.is_enabled,
            "cooldown_seconds": rule.cooldown_seconds,
        }, ensure_ascii=False)

        async with get_async_session() as session:
            existing = await session.execute(
                select(SystemConfigORM).where(SystemConfigORM.key == key)
            )
            orm = existing.scalar_one_or_none()

            if orm:
                orm.value = value
            else:
                orm = SystemConfigORM(key=key, value=value)
                session.add(orm)

            await session.flush()

    async def _delete_rule_from_db(self, rule_id: str) -> None:
        """从数据库删除告警规则。"""
        from src.database.connection import get_async_session
        from sqlalchemy import select
        from src.database.schema import SystemConfigORM

        key = f"alert_rule_{rule_id}"
        async with get_async_session() as session:
            result = await session.execute(
                select(SystemConfigORM).where(SystemConfigORM.key == key)
            )
            orm = result.scalar_one_or_none()
            if orm:
                await session.delete(orm)
                await session.flush()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _record_to_dict(record: AlertRecord) -> Dict[str, Any]:
        """将 AlertRecord 转换为字典。"""
        return {
            "alert_id": record.alert_id,
            "rule_id": record.rule_id,
            "rule_name": record.rule_name,
            "severity": record.severity.value,
            "title": record.title,
            "message": record.message,
            "channels": [c.value for c in record.channels],
            "data": record.data,
            "created_at": record.created_at.isoformat(),
            "notified": record.notified,
            "notification_results": record.notification_results,
        }
