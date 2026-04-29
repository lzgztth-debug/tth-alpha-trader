"""数据库连接模块

使用 SQLAlchemy 2.0 异步API，支持 SQLite 和 PostgreSQL。
提供连接池管理、数据库初始化和异步会话上下文管理器。
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

# 数据库URL默认值
_DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./data/trading.db"
_DEFAULT_POSTGRES_URL = "postgresql+asyncpg://user:password@localhost:5432/trading"

# 数据库类型: "sqlite" | "postgres"
DATABASE_TYPE: str = os.getenv("DATABASE_TYPE", "sqlite")

# 连接池配置
_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))
_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"


# ---------------------------------------------------------------------------
# 内部状态
# ---------------------------------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _resolve_database_url(database_url: Optional[str] = None) -> str:
    """根据 DATABASE_TYPE 和传入参数解析最终的数据库URL。"""
    if database_url:
        return database_url

    if DATABASE_TYPE == "postgres":
        url = os.getenv("DATABASE_URL", _DEFAULT_POSTGRES_URL)
    else:
        url = os.getenv("DATABASE_URL", _DEFAULT_SQLITE_URL)

    # SQLite: 确保父目录存在
    if url.startswith("sqlite"):
        db_path = url.split("///")[-1]
        if db_path and not db_path.startswith(":memory:"):
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    return url


def _build_engine_kwargs(url: str) -> dict:
    """根据数据库类型构建引擎参数。"""
    kwargs: dict = {
        "echo": _ECHO,
    }

    if url.startswith("sqlite"):
        # SQLite 使用 StaticPool 以支持多线程/协程共享内存连接
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL 使用连接池
        kwargs["pool_size"] = _POOL_SIZE
        kwargs["max_overflow"] = _MAX_OVERFLOW
        kwargs["pool_recycle"] = _POOL_RECYCLE
        kwargs["pool_pre_ping"] = True

    return kwargs


# ---------------------------------------------------------------------------
# 公共API
# ---------------------------------------------------------------------------

def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """获取或创建异步数据库引擎 (单例模式)。

    Args:
        database_url: 数据库连接URL。为None时从环境变量读取。

    Returns:
        SQLAlchemy AsyncEngine 实例。
    """
    global _engine
    if _engine is None:
        url = _resolve_database_url(database_url)
        kwargs = _build_engine_kwargs(url)
        _engine = create_async_engine(url, **kwargs)
        logger.info(f"数据库引擎已创建: {DATABASE_TYPE} ({url})")
    return _engine


def get_session_factory(
    database_url: Optional[str] = None,
) -> async_sessionmaker[AsyncSession]:
    """获取或创建异步会话工厂 (单例模式)。

    Args:
        database_url: 数据库连接URL。为None时从环境变量读取。

    Returns:
        SQLAlchemy async_sessionmaker 实例。
    """
    global _session_factory
    if _session_factory is None:
        engine = get_engine(database_url)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("会话工厂已创建")
    return _session_factory


# 为了向后兼容和简化导入，提供模块级别名
async_session_factory = get_session_factory


async def init_db(database_url: Optional[str] = None) -> None:
    """初始化数据库，创建所有表。

    Args:
        database_url: 数据库连接URL。为None时从环境变量读取。
    """
    from src.database.schema import Base  # 延迟导入避免循环依赖

    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构初始化完成")


async def close_db() -> None:
    """关闭数据库引擎，释放连接池资源。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("数据库连接已关闭")


@asynccontextmanager
async def get_async_session(
    database_url: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """异步会话上下文管理器。

    用法::

        async with get_async_session() as session:
            result = await session.execute(select(AccountORM))
            accounts = result.scalars().all()

    Args:
        database_url: 数据库连接URL。为None时使用默认引擎。

    Yields:
        AsyncSession 实例。
    """
    factory = get_session_factory(database_url)
    session: AsyncSession = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
