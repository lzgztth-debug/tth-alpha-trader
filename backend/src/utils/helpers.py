"""
辅助函数模块
============
通用工具函数集合，包括时间处理、数据转换、数值计算等。
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar, Union

T = TypeVar("T")


# ============================================================
# 时间工具
# ============================================================

def now_utc() -> datetime:
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


def now_local(tz_str: str = "Asia/Shanghai") -> datetime:
    """
    获取指定时区的当前时间。

    Args:
        tz_str: 时区字符串，如 "Asia/Shanghai", "America/New_York"

    Returns:
        对应时区的当前时间
    """
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_str)
    return datetime.now(tz)


def timestamp_ms() -> int:
    """获取当前时间戳（毫秒）"""
    return int(time.time() * 1000)


def timestamp_s() -> int:
    """获取当前时间戳（秒）"""
    return int(time.time())


def datetime_to_str(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将 datetime 对象格式化为字符串。

    Args:
        dt: datetime 对象
        fmt: 格式字符串

    Returns:
        格式化后的时间字符串
    """
    return dt.strftime(fmt)


def str_to_datetime(s: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """
    将字符串解析为 datetime 对象。

    Args:
        s: 时间字符串
        fmt: 格式字符串

    Returns:
        解析后的 datetime 对象
    """
    return datetime.strptime(s, fmt)


# ============================================================
# 数值工具
# ============================================================

def round_decimal(value: Union[float, str, Decimal], decimals: int = 2) -> Decimal:
    """
    精确的十进制四舍五入，避免浮点数精度问题。

    Args:
        value: 数值（float、str 或 Decimal）
        decimals: 保留小数位数

    Returns:
        四舍五入后的 Decimal
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    quantize_str = "0." + "0" * decimals if decimals > 0 else "1"
    return value.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    安全地将值转换为 float，转换失败返回默认值。

    Args:
        value: 待转换的值
        default: 转换失败时的默认值

    Returns:
        转换后的 float
    """
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    安全地将值转换为 int，转换失败返回默认值。

    Args:
        value: 待转换的值
        default: 转换失败时的默认值

    Returns:
        转换后的 int
    """
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    将数值限制在指定范围内。

    Args:
        value: 输入值
        min_val: 最小值
        max_val: 最大值

    Returns:
        限制后的值
    """
    return max(min_val, min(value, max_val))


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    计算变化百分比。

    Args:
        old_value: 原始值
        new_value: 新值

    Returns:
        变化百分比，old_value 为 0 时返回 0.0
    """
    if old_value == 0:
        return 0.0
    return ((new_value - old_value) / abs(old_value)) * 100.0


# ============================================================
# 字符串工具
# ============================================================

def sanitize_symbol(symbol: str) -> str:
    """
    标准化交易标的符号（去除空格，转大写）。

    Args:
        symbol: 原始标的符号

    Returns:
        标准化后的符号
    """
    return symbol.strip().upper().replace(" ", "")


def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """
    生成字符串的哈希值。

    Args:
        data: 输入字符串
        algorithm: 哈希算法（sha256, md5, sha1 等）

    Returns:
        十六进制哈希字符串
    """
    h = hashlib.new(algorithm)
    h.update(data.encode("utf-8"))
    return h.hexdigest()


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断字符串。

    Args:
        s: 输入字符串
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        截断后的字符串
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def camel_to_snake(name: str) -> str:
    """
    将驼峰命名转换为下划线命名。

    Args:
        name: 驼峰命名字符串

    Returns:
        下划线命名字符串
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """
    将下划线命名转换为驼峰命名。

    Args:
        name: 下划线命名字符串

    Returns:
        驼峰命名字符串
    """
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


# ============================================================
# 数据转换工具
# ============================================================

def to_json(obj: Any, ensure_ascii: bool = False, indent: Optional[int] = None) -> str:
    """
    将对象序列化为 JSON 字符串。
    支持 datetime 和 Decimal 类型的自动转换。

    Args:
        obj: 待序列化的对象
        ensure_ascii: 是否转义非 ASCII 字符
        indent: 缩进空格数

    Returns:
        JSON 字符串
    """
    def default_serializer(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=default_serializer, ensure_ascii=ensure_ascii, indent=indent)


def from_json(json_str: str) -> Any:
    """
    将 JSON 字符串反序列化为 Python 对象。

    Args:
        json_str: JSON 字符串

    Returns:
        反序列化后的 Python 对象
    """
    return json.loads(json_str)


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    将嵌套字典展平为单层字典。

    Args:
        d: 嵌套字典
        parent_key: 父级键前缀
        sep: 键分隔符

    Returns:
        展平后的字典
    """
    items: List[tuple] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


# ============================================================
# 异步工具
# ============================================================

async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    在异步上下文中运行同步函数（使用线程池）。

    Args:
        func: 同步函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数执行结果
    """
    loop = asyncio.get_running_loop()
    partial = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial)


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    在同步上下文中运行异步协程。

    Args:
        coro: 异步协程

    Returns:
        协程执行结果
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# ============================================================
# 验证工具
# ============================================================

def is_valid_symbol(symbol: str) -> bool:
    """
    验证交易标的符号是否合法。

    Args:
        symbol: 标的符号

    Returns:
        是否合法
    """
    pattern = r"^[A-Za-z0-9.\-]{1,20}$"
    return bool(re.match(pattern, symbol))


def is_valid_percentage(value: float) -> bool:
    """
    验证是否为有效的百分比值（0-100）。

    Args:
        value: 百分比值

    Returns:
        是否有效
    """
    return 0.0 <= value <= 100.0
