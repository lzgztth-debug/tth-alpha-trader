"""数据库表结构定义 (SQLAlchemy ORM)

定义以下表:
- accounts          账户表
- positions         持仓表
- orders            订单表
- decision_logs     AI决策日志表
- trade_logs        交易日志表
- prompt_templates  Prompt模板表
- system_config     系统配置表
- market_snapshots  行情快照表

所有表均包含 created_at / updated_at 时间戳字段和必要索引。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """所有ORM模型的基类。"""
    pass


# ---------------------------------------------------------------------------
# Mixin: 公共时间戳字段
# ---------------------------------------------------------------------------

class TimestampMixin:
    """为ORM模型提供 created_at / updated_at 字段。"""
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


# ---------------------------------------------------------------------------
# accounts - 账户表
# ---------------------------------------------------------------------------

class AccountORM(Base, TimestampMixin):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(64), nullable=False, unique=True, comment="账户唯一标识")
    broker = Column(String(32), nullable=False, comment="券商/交易所名称")
    account_type = Column(String(16), nullable=False, comment="账户类型: real / paper")
    total_value = Column(Float, nullable=False, default=0.0, comment="总资产")
    cash = Column(Float, nullable=False, default=0.0, comment="现金余额")
    market_value = Column(Float, nullable=False, default=0.0, comment="持仓市值")
    available_cash = Column(Float, nullable=False, default=0.0, comment="可用现金")

    __table_args__ = (
        Index("idx_accounts_account_id", "account_id"),
        Index("idx_accounts_broker", "broker"),
        Index("idx_accounts_type", "account_type"),
    )


# ---------------------------------------------------------------------------
# positions - 持仓表
# ---------------------------------------------------------------------------

class PositionORM(Base, TimestampMixin):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(64), nullable=False, comment="所属账户ID")
    symbol = Column(String(32), nullable=False, comment="标的代码")
    quantity = Column(Float, nullable=False, default=0.0, comment="持仓数量")
    avg_cost = Column(Float, nullable=False, default=0.0, comment="平均成本")
    current_price = Column(Float, nullable=False, default=0.0, comment="当前价格")
    market_value = Column(Float, nullable=False, default=0.0, comment="持仓市值")
    unrealized_pnl = Column(Float, nullable=False, default=0.0, comment="未实现盈亏")

    __table_args__ = (
        Index("idx_positions_account_id", "account_id"),
        Index("idx_positions_symbol", "symbol"),
        Index("idx_positions_account_symbol", "account_id", "symbol", unique=True),
    )


# ---------------------------------------------------------------------------
# orders - 订单表
# ---------------------------------------------------------------------------

class OrderORM(Base, TimestampMixin):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), nullable=False, unique=True, comment="订单唯一标识")
    account_id = Column(String(64), nullable=False, comment="所属账户ID")
    broker = Column(String(32), nullable=False, default="", comment="券商名称")
    symbol = Column(String(32), nullable=False, comment="标的代码")
    side = Column(String(8), nullable=False, comment="买卖方向: buy / sell")
    order_type = Column(String(16), nullable=False, comment="订单类型: market / limit")
    quantity = Column(Float, nullable=False, comment="委托数量")
    price = Column(Float, nullable=True, comment="委托价格")
    filled_quantity = Column(Float, nullable=False, default=0.0, comment="已成交数量")
    filled_price = Column(Float, nullable=False, default=0.0, comment="成交均价")
    status = Column(String(16), nullable=False, default="pending", comment="订单状态")
    fee = Column(Float, nullable=False, default=0.0, comment="手续费")
    filled_at = Column(DateTime, nullable=True, comment="成交时间")

    __table_args__ = (
        Index("idx_orders_account_id", "account_id"),
        Index("idx_orders_symbol", "symbol"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_created_at", "created_at"),
        Index("idx_orders_account_symbol", "account_id", "symbol"),
    )


# ---------------------------------------------------------------------------
# decision_logs - AI决策日志表
# ---------------------------------------------------------------------------

class DecisionLogORM(Base, TimestampMixin):
    __tablename__ = "decision_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String(64), nullable=False, unique=True, comment="决策唯一标识")
    model = Column(String(64), nullable=False, comment="模型名称")
    provider = Column(String(32), nullable=False, comment="模型供应商")
    action = Column(String(16), nullable=False, comment="决策动作: buy / sell / hold")
    symbol = Column(String(32), nullable=True, comment="标的代码")
    quantity = Column(Float, nullable=True, comment="建议数量")
    price = Column(Float, nullable=True, comment="建议价格")
    confidence = Column(Float, nullable=False, default=0.0, comment="决策置信度")
    reasoning = Column(Text, nullable=True, comment="决策理由")
    raw_response = Column(Text, nullable=True, comment="模型原始输出")
    prompt = Column(Text, nullable=True, comment="发送的Prompt")
    market_context = Column(Text, nullable=True, comment="市场快照JSON")
    account_context = Column(Text, nullable=True, comment="账户快照JSON")
    executed = Column(Boolean, nullable=False, default=False, comment="是否已执行")
    execution_result = Column(Text, nullable=True, comment="执行结果")
    latency_ms = Column(Integer, nullable=True, comment="推理延迟(ms)")

    __table_args__ = (
        Index("idx_decision_logs_model", "model"),
        Index("idx_decision_logs_provider", "provider"),
        Index("idx_decision_logs_action", "action"),
        Index("idx_decision_logs_symbol", "symbol"),
        Index("idx_decision_logs_created_at", "created_at"),
        Index("idx_decision_logs_executed", "executed"),
    )


# ---------------------------------------------------------------------------
# trade_logs - 交易日志表
# ---------------------------------------------------------------------------

class TradeLogORM(Base, TimestampMixin):
    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), nullable=False, comment="订单ID")
    decision_id = Column(String(64), nullable=True, comment="关联的决策ID")
    account_id = Column(String(64), nullable=False, comment="账户ID")
    broker = Column(String(32), nullable=False, default="", comment="券商名称")
    symbol = Column(String(32), nullable=False, comment="标的代码")
    side = Column(String(8), nullable=False, comment="买卖方向")
    quantity = Column(Float, nullable=False, comment="成交数量")
    price = Column(Float, nullable=False, comment="成交价格")
    commission = Column(Float, nullable=False, default=0.0, comment="手续费")
    pnl = Column(Float, nullable=True, comment="盈亏金额")

    __table_args__ = (
        Index("idx_trade_logs_order_id", "order_id"),
        Index("idx_trade_logs_decision_id", "decision_id"),
        Index("idx_trade_logs_account_id", "account_id"),
        Index("idx_trade_logs_symbol", "symbol"),
        Index("idx_trade_logs_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# prompt_templates - Prompt模板表
# ---------------------------------------------------------------------------

class PromptTemplateORM(Base, TimestampMixin):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, comment="模板名称")
    category = Column(String(32), nullable=False, comment="模板分类")
    content = Column(Text, nullable=False, comment="模板内容")
    variables = Column(Text, nullable=True, comment="变量列表JSON")
    version = Column(Integer, nullable=False, default=1, comment="版本号")
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")

    __table_args__ = (
        Index("idx_prompt_templates_category", "category"),
        Index("idx_prompt_templates_active", "is_active"),
    )


# ---------------------------------------------------------------------------
# system_config - 系统配置表
# ---------------------------------------------------------------------------

class SystemConfigORM(Base, TimestampMixin):
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), nullable=False, unique=True, comment="配置键")
    value = Column(Text, nullable=False, comment="配置值")
    encrypted = Column(Boolean, nullable=False, default=False, comment="是否加密")

    __table_args__ = (
        Index("idx_system_config_key", "key"),
    )


# ---------------------------------------------------------------------------
# market_snapshots - 行情快照表
# ---------------------------------------------------------------------------

class MarketSnapshotORM(Base, TimestampMixin):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, comment="标的代码")
    open = Column(Float, nullable=False, default=0.0, comment="开盘价")
    high = Column(Float, nullable=False, default=0.0, comment="最高价")
    low = Column(Float, nullable=False, default=0.0, comment="最低价")
    close = Column(Float, nullable=False, default=0.0, comment="收盘价/最新价")
    volume = Column(Float, nullable=False, default=0.0, comment="成交量")
    timestamp = Column(DateTime, nullable=False, comment="行情时间戳")

    __table_args__ = (
        Index("idx_market_snapshots_symbol", "symbol"),
        Index("idx_market_snapshots_timestamp", "timestamp"),
        Index("idx_market_snapshots_symbol_time", "symbol", "timestamp"),
    )
