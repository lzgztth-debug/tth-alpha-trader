"""Alembic 环境配置

配置 SQLAlchemy 异步引擎和迁移环境。
从 src.utils.config 获取数据库 URL，使用 src.database.schema 中的 metadata。
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.schema import Base
from src.utils.config import get_settings

# Alembic Config 对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData 对象，用于 autogenerate
target_metadata = Base.metadata

# 从应用配置获取数据库 URL
settings = get_settings()
database_url = settings.database.url

# 覆盖 alembic.ini 中的 sqlalchemy.url
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """以 'offline' 模式运行迁移。

    只需要生成 SQL 脚本，不需要连接数据库。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """执行迁移的辅助函数。"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """以 'online' 模式运行异步迁移。

    创建异步引擎并执行迁移。
    """
    configuration = config.get_section(config.config_ini_section, {})

    # 对于 SQLite 使用 StaticPool
    if database_url.startswith("sqlite"):
        configuration["sqlalchemy.url"] = database_url
        connect_args = {"check_same_thread": False}
        engine = create_async_engine(
            database_url,
            poolclass=pool.StaticPool,
            connect_args=connect_args,
            echo=False,
        )
    else:
        connectable = async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        engine = connectable

    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """以 'online' 模式运行迁移。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
