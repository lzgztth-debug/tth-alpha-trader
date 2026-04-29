# src/adapters/market_data/tushare.py
# TuShare 行情适配器 - 使用 tushare 库获取A股行情数据

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timedelta

from src.adapters.market_data.base import (
    BaseMarketDataAdapter,
    MarketDataError,
    MarketDataConnectionError,
)
from src.models.market_data import Quote, Kline

logger = logging.getLogger(__name__)


class TuShareAdapter(BaseMarketDataAdapter):
    """
    TuShare 行情适配器

    使用 tushare 库获取A股行情数据。

    配置参数:
        token: TuShare API Token（必需）
        timeout: 请求超时时间（秒），默认 30
        max_retries: 最大重试次数，默认 3
        retry_delay: 重试延迟（秒），默认 2
    """

    # K线周期映射
    INTERVAL_MAP = {
        "1d": "daily",
        "1w": "weekly",
        "1M": "monthly",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "60m": "60min",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.token = self.config.get("token", "")
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 2)

        self._pro_api = None

        if not self.token:
            logger.warning("TuShare: token 未配置，部分接口可能受限")

    async def connect(self) -> bool:
        """连接 TuShare"""
        try:
            import tushare as ts

            self._ts = ts
            if self.token:
                ts.set_token(self.token)
                self._pro_api = ts.pro_api()
                logger.info("TuShare: 使用 Pro API 连接成功")
            else:
                logger.info("TuShare: 使用免费接口连接成功")

            self._connected = True
            return True

        except ImportError:
            raise MarketDataConnectionError(
                "tushare 未安装，请执行: pip install tushare",
                source="TuShare"
            )
        except Exception as e:
            self._connected = False
            raise MarketDataConnectionError(
                f"连接失败: {e}",
                source="TuShare"
            )

    async def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._pro_api = None
        logger.info("TuShare: 已断开连接")

    async def get_quote(self, symbol: str) -> Quote:
        """
        获取单个标的实时行情

        注意: TuShare 免费接口不支持实时行情，返回最近一个交易日数据。
        使用 Pro 接口可获取实时行情。
        """
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._get_quote_sync, symbol
            )
            return result
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"获取行情失败: {e}",
                source="TuShare"
            )

    def _get_quote_sync(self, symbol: str) -> Quote:
        """同步获取行情"""
        # 标准化股票代码格式
        ts_code = self._normalize_symbol(symbol)

        try:
            if self._pro_api:
                # 使用 Pro API 获取实时行情
                df = self._pro_api.daily(
                    ts_code=ts_code,
                    start_date=datetime.now().strftime("%Y%m%d"),
                    end_date=datetime.now().strftime("%Y%m%d"),
                )

                if df.empty:
                    # 如果当天没有数据，获取最近一个交易日
                    df = self._pro_api.daily(
                        ts_code=ts_code,
                        limit=1,
                    )

                if df.empty:
                    raise MarketDataError(
                        f"未获取到行情数据: {symbol}",
                        source="TuShare"
                    )

                row = df.iloc[0]
                quote = Quote(
                    symbol=symbol,
                    open=float(row.get('open', 0) or 0),
                    high=float(row.get('high', 0) or 0),
                    low=float(row.get('low', 0) or 0),
                    close=float(row.get('close', 0) or 0),
                    volume=float(row.get('vol', 0) or 0),
                    prev_close=float(row.get('pre_close', 0) or 0),
                    turnover=float(row.get('amount', 0) or 0),
                    timestamp=datetime.now(),
                )
            else:
                # 使用免费接口
                df = self._ts.get_realtime_quotes(symbol)

                if df.empty:
                    raise MarketDataError(
                        f"未获取到行情数据: {symbol}",
                        source="TuShare"
                    )

                row = df.iloc[0]
                quote = Quote(
                    symbol=symbol,
                    open=float(row.get('open', 0) or 0),
                    high=float(row.get('high', 0) or 0),
                    low=float(row.get('low', 0) or 0),
                    close=float(row.get('price', 0) or 0),
                    volume=float(row.get('volume', 0) or 0),
                    prev_close=float(row.get('pre_close', 0) or 0),
                    bid_price=float(row.get('bid', 0) or 0),
                    ask_price=float(row.get('ask', 0) or 0),
                    bid_volume=float(row.get('b1_v', 0) or 0),
                    ask_volume=float(row.get('a1_v', 0) or 0),
                    turnover=float(row.get('amount', 0) or 0),
                    timestamp=datetime.now(),
                )

            logger.debug(f"TuShare: 获取行情成功, symbol={symbol}")
            return quote

        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"获取行情失败: {e}",
                source="TuShare"
            )

    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        """批量获取标的行情"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._get_quotes_sync, symbols
            )
            return result
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"批量获取行情失败: {e}",
                source="TuShare"
            )

    def _get_quotes_sync(self, symbols: List[str]) -> List[Quote]:
        """同步批量获取行情"""
        try:
            if self._pro_api:
                # Pro API 批量查询
                ts_codes = [self._normalize_symbol(s) for s in symbols]
                df = self._pro_api.daily(
                    ts_code=','.join(ts_codes),
                    start_date=datetime.now().strftime("%Y%m%d"),
                    end_date=datetime.now().strftime("%Y%m%d"),
                )

                if df.empty:
                    df = self._pro_api.daily(
                        ts_code=','.join(ts_codes),
                        limit=1,
                    )

                quotes = []
                for _, row in df.iterrows():
                    ts_code = row.get('ts_code', '')
                    symbol = self._denormalize_symbol(ts_code)
                    quotes.append(Quote(
                        symbol=symbol,
                        open=float(row.get('open', 0) or 0),
                        high=float(row.get('high', 0) or 0),
                        low=float(row.get('low', 0) or 0),
                        close=float(row.get('close', 0) or 0),
                        volume=float(row.get('vol', 0) or 0),
                        prev_close=float(row.get('pre_close', 0) or 0),
                        turnover=float(row.get('amount', 0) or 0),
                        timestamp=datetime.now(),
                    ))
                return quotes
            else:
                # 免费接口逐个获取
                quotes = []
                for symbol in symbols:
                    try:
                        quote = self._get_quote_sync(symbol)
                        quotes.append(quote)
                    except Exception as e:
                        logger.error(f"TuShare: 获取 {symbol} 行情失败: {e}")
                return quotes

        except Exception as e:
            raise MarketDataError(
                f"批量获取行情失败: {e}",
                source="TuShare"
            )

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Kline]:
        """获取K线数据"""
        self._ensure_connected()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._get_klines_sync,
                symbol, interval, limit, start_time, end_time
            )
            return result
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"获取K线数据失败: {e}",
                source="TuShare"
            )

    def _get_klines_sync(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> List[Kline]:
        """同步获取K线数据"""
        ts_code = self._normalize_symbol(symbol)
        ts_freq = self.INTERVAL_MAP.get(interval, "daily")

        try:
            # 计算日期范围
            if start_time:
                start_date = datetime.fromisoformat(start_time).strftime("%Y%m%d")
            else:
                # 默认往前推算
                if interval == "1d":
                    start_date = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y%m%d")
                elif interval == "1w":
                    start_date = (datetime.now() - timedelta(weeks=limit * 2)).strftime("%Y%m%d")
                elif interval == "1M":
                    start_date = (datetime.now() - timedelta(days=limit * 35)).strftime("%Y%m%d")
                else:
                    start_date = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y%m%d")

            if end_time:
                end_date = datetime.fromisoformat(end_time).strftime("%Y%m%d")
            else:
                end_date = datetime.now().strftime("%Y%m%d")

            if self._pro_api:
                if ts_freq in ("daily", "weekly", "monthly"):
                    df = self._pro_api.daily(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                    )

                    if interval == "1w":
                        df = self._pro_api.weekly(
                            ts_code=ts_code,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    elif interval == "1M":
                        df = self._pro_api.monthly(
                            ts_code=ts_code,
                            start_date=start_date,
                            end_date=end_date,
                        )
                else:
                    # 分钟级数据
                    df = self._pro_api.stk_mins(
                        ts_code=ts_code,
                        freq=ts_freq.replace('min', ''),
                        start_date=start_date,
                        end_date=end_date,
                    )

                if df.empty:
                    logger.warning(f"TuShare: 未获取到K线数据, symbol={symbol}")
                    return []

                # 按日期排序并限制条数
                df = df.sort_values('trade_date', ascending=True).tail(limit)

                klines = []
                for _, row in df.iterrows():
                    trade_date = row.get('trade_date', '')
                    try:
                        timestamp = datetime.strptime(trade_date, "%Y%m%d")
                    except (ValueError, TypeError):
                        timestamp = datetime.now()

                    klines.append(Kline(
                        symbol=symbol,
                        interval=interval,
                        open=float(row.get('open', 0) or 0),
                        high=float(row.get('high', 0) or 0),
                        low=float(row.get('low', 0) or 0),
                        close=float(row.get('close', 0) or 0),
                        volume=float(row.get('vol', 0) or 0),
                        timestamp=timestamp,
                        turnover=float(row.get('amount', 0) or 0),
                    ))

                logger.info(
                    f"TuShare: 获取K线成功, symbol={symbol}, "
                    f"interval={interval}, count={len(klines)}"
                )
                return klines

            else:
                # 免费接口
                if interval == "1d":
                    start_dt = datetime.strptime(start_date, "%Y%m%d")
                    end_dt = datetime.strptime(end_date, "%Y%m%d")
                    df = self._ts.get_k_data(
                        symbol,
                        start=str(start_dt.date()),
                        end=str(end_dt.date()),
                    )

                    if df.empty:
                        return []

                    df = df.tail(limit)
                    klines = []
                    for _, row in df.iterrows():
                        klines.append(Kline(
                            symbol=symbol,
                            interval=interval,
                            open=float(row.get('open', 0) or 0),
                            high=float(row.get('high', 0) or 0),
                            low=float(row.get('low', 0) or 0),
                            close=float(row.get('close', 0) or 0),
                            volume=float(row.get('volume', 0) or 0),
                            timestamp=datetime.strptime(str(row.get('date', '')), "%Y-%m-%d"),
                        ))
                    return klines
                else:
                    raise MarketDataError(
                        f"免费接口不支持 {interval} 周期K线",
                        source="TuShare"
                    )

        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"获取K线数据失败: {e}",
                source="TuShare"
            )

    async def subscribe_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], Awaitable[None]]
    ) -> None:
        """
        订阅实时行情（轮询模式）

        TuShare 不支持真正的实时推送，使用轮询方式模拟。
        注意: 频繁调用可能触发限流。
        """
        self._ensure_connected()

        for symbol in symbols:
            self._quote_callbacks[symbol] = callback

        # 轮询间隔（A股建议较长，避免限流）
        poll_interval = self.config.get("poll_interval", 60)

        async def _poll_loop():
            """轮询获取行情"""
            while self._connected:
                try:
                    for symbol in list(self._quote_callbacks.keys()):
                        try:
                            quote = await self.get_quote(symbol)
                            cb = self._quote_callbacks.get(symbol)
                            if cb:
                                await cb(quote)
                        except Exception as e:
                            logger.error(
                                f"TuShare: 轮询 {symbol} 行情异常: {e}"
                            )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"TuShare: 轮询异常: {e}")
                await asyncio.sleep(poll_interval)

        self._poll_task = asyncio.create_task(_poll_loop())
        logger.info(f"TuShare: 订阅行情成功 (轮询模式), symbols={symbols}")

    async def unsubscribe_quotes(self, symbols: List[str]) -> None:
        """取消订阅行情"""
        for symbol in symbols:
            self._quote_callbacks.pop(symbol, None)

        if not self._quote_callbacks:
            if hasattr(self, '_poll_task') and self._poll_task:
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass

        logger.info(f"TuShare: 取消订阅行情, symbols={symbols}")

    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化股票代码为 TuShare 格式

        Examples:
            600519 -> 600519.SH
            000001 -> 000001.SZ
            600519.SH -> 600519.SH
        """
        if '.' in symbol:
            return symbol.upper()

        # 根据代码前缀判断市场
        if symbol.startswith('6'):
            return f"{symbol}.SH"  # 上交所
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"{symbol}.SZ"  # 深交所
        elif symbol.startswith('8') or symbol.startswith('4'):
            return f"{symbol}.BJ"  # 北交所
        else:
            return f"{symbol}.SH"  # 默认上交所

    def _denormalize_symbol(self, ts_code: str) -> str:
        """
        将 TuShare 代码格式转换为标准格式

        Examples:
            600519.SH -> 600519
        """
        if '.' in ts_code:
            return ts_code.split('.')[0]
        return ts_code
