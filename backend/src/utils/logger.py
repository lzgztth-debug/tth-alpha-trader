"""
日志模块
========
基于 loguru 的统一日志管理。
支持控制台输出和文件输出，自动日志轮转。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from src.utils.config import LogSettings


# 移除 loguru 默认的 handler
logger.remove()


def setup_logger(
    settings: Optional[LogSettings] = None,
    log_dir: Optional[str] = None,
    level: str = "INFO",
    log_file: str = "trading.log",
    rotation: str = "00:00",
    retention: str = "30 days",
    console_output: bool = True,
    file_output: bool = True,
) -> None:
    """
    初始化日志系统。

    Args:
        settings: LogSettings 配置对象，若提供则忽略其他参数
        log_dir: 日志文件目录
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        log_file: 日志文件名
        rotation: 日志轮转周期，支持时间字符串或大小字符串
        retention: 日志保留时间
        console_output: 是否输出到控制台
        file_output: 是否输出到文件
    """
    if settings is not None:
        level = settings.level
        log_dir = settings.log_dir
        log_file = settings.log_file
        rotation = settings.rotation
        retention = settings.retention
        console_output = settings.console_output
        file_output = settings.file_output

    # 日志格式
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 控制台输出
    if console_output:
        logger.add(
            sys.stderr,
            format=log_format,
            level=level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # 文件输出
    if file_output:
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            full_log_file = str(log_path / log_file)
        else:
            full_log_file = log_file

        logger.add(
            full_log_file,
            format=log_format,
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
            enqueue=True,  # 异步写入，避免阻塞主线程
            backtrace=True,
            diagnose=True,
        )

    logger.info("日志系统初始化完成 | level={} | file={} | console={}", level, file_output, console_output)


def get_logger(name: str = "ai_trading"):
    """
    获取带有模块名称的 logger 实例。

    Args:
        name: 模块名称，用于日志标识

    Returns:
        绑定了模块名称的 loguru logger
    """
    return logger.bind(name=name)


# ============================================================
# 便捷函数
# ============================================================

def log_debug(message: str, **kwargs) -> None:
    """记录 DEBUG 级别日志"""
    logger.debug(message, **kwargs)


def log_info(message: str, **kwargs) -> None:
    """记录 INFO 级别日志"""
    logger.info(message, **kwargs)


def log_warning(message: str, **kwargs) -> None:
    """记录 WARNING 级别日志"""
    logger.warning(message, **kwargs)


def log_error(message: str, **kwargs) -> None:
    """记录 ERROR 级别日志"""
    logger.error(message, **kwargs)


def log_critical(message: str, **kwargs) -> None:
    """记录 CRITICAL 级别日志"""
    logger.critical(message, **kwargs)


def log_exception(message: str, **kwargs) -> None:
    """记录异常日志（自动包含堆栈信息）"""
    logger.exception(message, **kwargs)
