"""
配置管理模块
============
使用 Pydantic Settings 支持环境变量和 YAML 配置文件加载。
优先级：环境变量 > .env 文件 > config.yaml > 默认值
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================
# 子配置模型
# ============================================================

class DatabaseSettings(BaseSettings):
    """数据库配置"""

    url: str = Field(default="sqlite+aiosqlite:///./data/trading.db", alias="DATABASE_URL")
    echo: bool = Field(default=False, alias="DATABASE_ECHO")
    pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")
    connect_timeout: int = Field(default=30, alias="DATABASE_CONNECT_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class RedisSettings(BaseSettings):
    """Redis配置"""

    url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    db: int = Field(default=0, alias="REDIS_DB")
    max_connections: int = Field(default=20, alias="REDIS_MAX_CONNECTIONS")
    socket_timeout: int = Field(default=5, alias="REDIS_SOCKET_TIMEOUT")
    enabled: bool = Field(default=False, alias="REDIS_ENABLED")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class OpenAISettings(BaseSettings):
    """OpenAI配置"""

    api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    model: str = Field(default="gpt-4-turbo", alias="OPENAI_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="OPENAI_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="OPENAI_MAX_TOKENS")
    timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class AnthropicSettings(BaseSettings):
    """Anthropic配置"""

    api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-3-opus-20240229", alias="ANTHROPIC_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, alias="ANTHROPIC_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="ANTHROPIC_MAX_TOKENS")
    timeout: int = Field(default=60, alias="ANTHROPIC_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class DashScopeSettings(BaseSettings):
    """DashScope (通义千问) 配置"""

    api_key: Optional[str] = Field(default=None, alias="DASHSCOPE_API_KEY")
    model: str = Field(default="qwen-turbo", alias="DASHSCOPE_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="DASHSCOPE_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="DASHSCOPE_MAX_TOKENS")
    timeout: int = Field(default=60, alias="DASHSCOPE_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class SeedSettings(BaseSettings):
    """Seed (豆包) 配置"""

    api_key: Optional[str] = Field(default=None, alias="SEED_API_KEY")
    base_url: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", alias="SEED_BASE_URL")
    model: str = Field(default="doubao-pro-32k", alias="SEED_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="SEED_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="SEED_MAX_TOKENS")
    timeout: int = Field(default=60, alias="SEED_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class MiniMaxSettings(BaseSettings):
    """MiniMax 配置"""

    api_key: Optional[str] = Field(default=None, alias="MINIMAX_API_KEY")
    base_url: str = Field(default="https://api.minimax.chat/v1", alias="MINIMAX_BASE_URL")
    model: str = Field(default="abab6.5s-chat", alias="MINIMAX_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="MINIMAX_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="MINIMAX_MAX_TOKENS")
    timeout: int = Field(default=60, alias="MINIMAX_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class SiliconFlowSettings(BaseSettings):
    """硅基流动 (SiliconFlow) 配置"""

    api_key: Optional[str] = Field(default=None, alias="SILICONFLOW_API_KEY")
    base_url: str = Field(default="https://api.siliconflow.cn/v1", alias="SILICONFLOW_BASE_URL")
    model: str = Field(default="Qwen/Qwen2.5-7B-Instruct", alias="SILICONFLOW_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="SILICONFLOW_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="SILICONFLOW_MAX_TOKENS")
    timeout: int = Field(default=60, alias="SILICONFLOW_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class ZhipuSettings(BaseSettings):
    """智谱 (GLM) 配置"""

    api_key: Optional[str] = Field(default=None, alias="ZHIPU_API_KEY")
    base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4", alias="ZHIPU_BASE_URL")
    model: str = Field(default="glm-4", alias="ZHIPU_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="ZHIPU_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="ZHIPU_MAX_TOKENS")
    timeout: int = Field(default=60, alias="ZHIPU_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class QianfanSettings(BaseSettings):
    """千帆 (百度文心) 配置"""

    api_key: Optional[str] = Field(default=None, alias="QIANFAN_API_KEY")
    secret_key: Optional[str] = Field(default=None, alias="QIANFAN_SECRET_KEY")
    base_url: str = Field(default="https://aip.baidubce.com", alias="QIANFAN_BASE_URL")
    model: str = Field(default="ernie-bot-4", alias="QIANFAN_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="QIANFAN_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="QIANFAN_MAX_TOKENS")
    timeout: int = Field(default=60, alias="QIANFAN_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class MoonshotSettings(BaseSettings):
    """月之暗面 (Moonshot/Kimi) 配置"""

    api_key: Optional[str] = Field(default=None, alias="MOONSHOT_API_KEY")
    base_url: str = Field(default="https://api.moonshot.cn/v1", alias="MOONSHOT_BASE_URL")
    model: str = Field(default="moonshot-v1-8k", alias="MOONSHOT_MODEL")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, alias="MOONSHOT_TEMPERATURE")
    max_tokens: int = Field(default=4096, gt=0, alias="MOONSHOT_MAX_TOKENS")
    timeout: int = Field(default=60, alias="MOONSHOT_TIMEOUT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class AIModelSettings(BaseSettings):
    """AI模型总配置"""

    default_provider: str = Field(default="openai", alias="AI_DEFAULT_PROVIDER")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    dashscope: DashScopeSettings = Field(default_factory=DashScopeSettings)
    seed: SeedSettings = Field(default_factory=SeedSettings)
    minimax: MiniMaxSettings = Field(default_factory=MiniMaxSettings)
    siliconflow: SiliconFlowSettings = Field(default_factory=SiliconFlowSettings)
    zhipu: ZhipuSettings = Field(default_factory=ZhipuSettings)
    qianfan: QianfanSettings = Field(default_factory=QianfanSettings)
    moonshot: MoonshotSettings = Field(default_factory=MoonshotSettings)
    retry_max_attempts: int = Field(default=3, alias="AI_RETRY_MAX_ATTEMPTS")
    retry_delay: float = Field(default=1.0, alias="AI_RETRY_DELAY")

    @field_validator("default_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        valid_providers = {
            "openai", "claude", "deepseek", "seed", "minimax",
            "qwen", "siliconflow", "zhipu", "qianfan", "moonshot", "ollama",
        }
        if v not in valid_providers:
            raise ValueError(f"AI provider must be one of {valid_providers}, got '{v}'")
        return v

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class BrokerSettings(BaseSettings):
    """券商配置"""

    default_broker: str = Field(default="simulated", alias="BROKER_DEFAULT")
    api_key: Optional[str] = Field(default=None, alias="BROKER_API_KEY")
    api_secret: Optional[str] = Field(default=None, alias="BROKER_API_SECRET")
    passphrase: Optional[str] = Field(default=None, alias="BROKER_PASSPHRASE")
    base_url: Optional[str] = Field(default=None, alias="BROKER_BASE_URL")
    sandbox: bool = Field(default=True, alias="BROKER_SANDBOX")
    rate_limit_per_second: int = Field(default=10, alias="BROKER_RATE_LIMIT")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class TradingModeSettings(BaseSettings):
    """交易模式配置"""

    mode: str = Field(default="paper", alias="TRADING_MODE")
    max_position_size: float = Field(default=10000.0, gt=0, alias="MAX_POSITION_SIZE")
    max_daily_trades: int = Field(default=50, gt=0, alias="MAX_DAILY_TRADES")
    max_drawdown_pct: float = Field(default=5.0, ge=0.0, le=100.0, alias="MAX_DRAWDOWN_PCT")
    stop_loss_pct: float = Field(default=2.0, ge=0.0, le=100.0, alias="STOP_LOSS_PCT")
    take_profit_pct: float = Field(default=5.0, ge=0.0, le=100.0, alias="TAKE_PROFIT_PCT")
    risk_per_trade_pct: float = Field(default=1.0, ge=0.0, le=100.0, alias="RISK_PER_TRADE_PCT")
    allowed_symbols: List[str] = Field(default_factory=list, alias="ALLOWED_SYMBOLS")
    trading_hours_start: str = Field(default="09:30", alias="TRADING_HOURS_START")
    trading_hours_end: str = Field(default="15:00", alias="TRADING_HOURS_END")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid_modes = {"paper", "live", "backtest"}
        if v not in valid_modes:
            raise ValueError(f"Trading mode must be one of {valid_modes}, got '{v}'")
        return v

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class LogSettings(BaseSettings):
    """日志配置"""

    level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default="./logs", alias="LOG_DIR")
    log_file: str = Field(default="trading.log", alias="LOG_FILE")
    rotation: str = Field(default="00:00", alias="LOG_ROTATION")
    retention: str = Field(default="30 days", alias="LOG_RETENTION")
    format_string: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>",
        alias="LOG_FORMAT",
    )
    console_output: bool = Field(default=True, alias="LOG_CONSOLE_OUTPUT")
    file_output: bool = Field(default=True, alias="LOG_FILE_OUTPUT")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}, got '{v}'")
        return v.upper()

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


class APISettings(BaseSettings):
    """API服务配置"""

    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    workers: int = Field(default=1, alias="API_WORKERS")
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://localhost:3000"],
        alias="API_CORS_ORIGINS",
    )
    api_key_enabled: bool = Field(default=True, alias="API_KEY_ENABLED")
    api_key: Optional[str] = Field(default=None, alias="API_KEY")

    model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")


# ============================================================
# 全局配置
# ============================================================

class Settings(BaseSettings):
    """全局应用配置 - 聚合所有子配置"""

    app_name: str = Field(default="AI Trading Platform", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    config_path: Optional[str] = Field(default=None, alias="CONFIG_PATH")

    # 子配置
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ai: AIModelSettings = Field(default_factory=AIModelSettings)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    trading: TradingModeSettings = Field(default_factory=TradingModeSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    api: APISettings = Field(default_factory=APISettings)

    model_config = SettingsConfigDict(
        populate_by_name=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def load_from_yaml(cls, yaml_path: str | Path) -> Dict[str, Any]:
        """
        从YAML文件加载配置字典。

        Args:
            yaml_path: YAML配置文件路径

        Returns:
            解析后的配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML格式错误
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data

    @classmethod
    def from_yaml(cls, yaml_path: str | Path, **overrides: Any) -> "Settings":
        """
        从YAML文件创建Settings实例，支持覆盖参数。

        Args:
            yaml_path: YAML配置文件路径
            **overrides: 覆盖配置项

        Returns:
            Settings实例
        """
        yaml_data = cls.load_from_yaml(yaml_path)
        yaml_data.update(overrides)
        return cls(**yaml_data)

    @classmethod
    def create(cls, config_path: str | Path | None = None) -> "Settings":
        """
        创建Settings实例的工厂方法。
        按优先级加载：环境变量 > .env > config.yaml > 默认值

        Args:
            config_path: 可选的YAML配置文件路径，若为None则使用默认路径

        Returns:
            Settings实例
        """
        if config_path is None:
            # 按顺序查找配置文件
            candidates = [
                Path(os.environ.get("CONFIG_PATH", "")),
                Path("config/config.yaml"),
                Path("config.yaml"),
            ]
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    config_path = candidate
                    break

        if config_path is not None:
            path = Path(config_path)
            if path.exists():
                return cls.from_yaml(path)
            # 尝试相对于项目根目录
            project_root = Path(__file__).resolve().parent.parent.parent
            full_path = project_root / config_path
            if full_path.exists():
                return cls.from_yaml(full_path)

        return cls()


# ============================================================
# 全局单例
# ============================================================

_global_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    获取全局Settings单例。
    首次调用时自动初始化。

    Returns:
        全局Settings实例
    """
    global _global_settings
    if _global_settings is None:
        _global_settings = Settings.create()
    return _global_settings


def reload_settings(config_path: str | Path | None = None) -> Settings:
    """
    重新加载配置。

    Args:
        config_path: 可选的配置文件路径

    Returns:
        新的Settings实例
    """
    global _global_settings
    _global_settings = Settings.create(config_path)
    return _global_settings
