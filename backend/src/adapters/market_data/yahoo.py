# src/adapters/market_data/yahoo.py
# Yahoo Finance 行情适配器 - 使用 yfinance 库获取美股、港股延迟行情

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable, Awaitable
from datetime import datetime, timedelta

from src.adapters.market_data.base import (
    BaseMarketDataAdapter,
    MarketDataError,
)
from src.models.market_data import Quote, Kline

logger = logging.getLogger(__name__)


class YahooFinanceAdapter(BaseMarketDataAdapter):
    """
    Yahoo Finance 行情适配器

    使用 yfinance 库获取美股、港股等市场的延迟行情数据。

    配置参数:
        proxy: 代理地址（可选）
        timeout: 请求超时时间（秒），默认 30
        max_retries: 最大重试次数，默认 3
        retry_delay: 重试延迟（秒），默认 2
    """

    # 支持的K线周期映射
    INTERVAL_MAP = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "90m": "90m",
        "1h": "60m",
        "1d": "1d",
        "5d": "5d",
        "1w": "1wk",
        "1M": "1mo",
        "3M": "3mo",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.proxy = self.config.get("proxy", "")
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 2)

    async def connect(self) -> bool:
        """连接 Yahoo Finance（验证库可用性）"""
        try:
            import yfinance as yf
            self._yf = yf
            self._connected = True
            logger.info("Yahoo Finance: 连接成功")
            return True
        except ImportError:
            raise MarketDataError(
                "yfinance 未安装，请执行: pip install yfinance",
                source="YahooFinance"
            )

    async def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        logger.info("Yahoo Finance: 已断开连接")

    async def get_quote(self, symbol: str) -> Quote:
        """获取单个标的实时行情"""
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
                source="YahooFinance"
            )

    def _get_quote_sync(self, symbol: str) -> Quote:
        """同步获取行情"""
        try:
            ticker = self._yf.Ticker(symbol)

            # 获取快速行情信息
            info = ticker.fast_info

            # 获取详细行情
            history = ticker.history(period="1d")
            if history.empty:
                raise MarketDataError(
                    f"未获取到行情数据: {symbol}",
                    source="YahooFinance"
                )

            row = history.iloc[0]
            close_price = float(row.get('Close', 0) or 0)
            open_price = float(row.get('Open', 0) or 0)
            high_price = float(row.get('High', 0) or 0)
            low_price = float(row.get('Low', 0) or 0)
            volume = float(row.get('Volume', 0) or 0)

            # 获取前收盘价
            prev_close = close_price
            try:
                prev_history = ticker.history(period="2d")
                if len(prev_history) >= 2:
                    prev_close = float(prev_history.iloc[0].get('Close', close_price) or close_price)
            except Exception:
                pass

            quote = Quote(
                symbol=symbol,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                prev_close=prev_close,
                timestamp=datetime.now(),
            )

            logger.debug(f"Yahoo Finance: 获取行情成功, symbol={symbol}, price={close_price}")
            return quote

        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"获取行情失败: {e}",
                source="YahooFinance"
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
                source="YahooFinance"
            )

    def _get_quotes_sync(self, symbols: List[str]) -> List[Quote]:
        """同步批量获取行情"""
        try:
            # 使用 download 批量获取
            tickers = self._yf.download(
                " ".join(symbols),
                period="1d",
                progress=False,
                timeout=self.timeout,
            )

            quotes = []
            for symbol in symbols:
                try:
                    if symbol in tickers.columns.get_level_values(0):
                        close_price = float(
                            tickers[('Close', symbol)].iloc[-1] or 0
                        )
                        open_price = float(
                            tickers[('Open', symbol)].iloc[-1] or 0
                        )
                        high_price = float(
                            tickers[('High', symbol)].iloc[-1] or 0
                        )
                        low_price = float(
                            tickers[('Low', symbol)].iloc[-1] or 0
                        )
                        volume = float(
                            tickers[('Volume', symbol)].iloc[-1] or 0
                        )

                        quotes.append(Quote(
                            symbol=symbol,
                            open=open_price,
                            high=high_price,
                            low=low_price,
                            close=close_price,
                            volume=volume,
                            timestamp=datetime.now(),
                        ))
                    else:
                        logger.warning(
                            f"Yahoo Finance: 未获取到 {symbol} 的行情数据"
                        )
                except Exception as e:
                    logger.error(
                        f"Yahoo Finance: 获取 {symbol} 行情异常: {e}"
                    )

            logger.info(f"Yahoo Finance: 批量获取行情成功, {len(quotes)}/{len(symbols)}")
            return quotes

        except Exception as e:
            raise MarketDataError(
                f"批量获取行情失败: {e}",
                source="YahooFinance"
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
                source="YahooFinance"
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
        try:
            ticker = self._yf.Ticker(symbol)

            # 转换周期格式
            yf_interval = self.INTERVAL_MAP.get(interval, "1d")

            # 计算时间范围
            if start_time and end_time:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
            elif start_time:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.now()
            else:
                # 根据 limit 和 interval 计算回溯时间
                period_map = {
                    "1m": timedelta(minutes=limit),
                    "5m": timedelta(minutes=limit * 5),
                    "15m": timedelta(minutes=limit * 15),
                    "30m": timedelta(minutes=limit * 30),
                    "60m": timedelta(hours=limit),
                    "1d": timedelta(days=limit * 2),
                    "1wk": timedelta(weeks=limit * 2),
                    "1mo": timedelta(days=limit * 35),
                }
                delta = period_map.get(interval, timedelta(days=limit * 2))
                start_dt = datetime.now() - delta
                end_dt = datetime.now()

            # 获取历史数据
            history = ticker.history(
                start=start_dt,
                end=end_dt,
                interval=yf_interval,
            )

            if history.empty:
                logger.warning(f"Yahoo Finance: 未获取到K线数据, symbol={symbol}")
                return []

            # 限制返回条数
            history = history.tail(limit)

            klines = []
            for idx, row in history.iterrows():
                klines.append(Kline(
                    symbol=symbol,
                    interval=interval,
                    open=float(row.get('Open', 0) or 0),
                    high=float(row.get('High', 0) or 0),
                    low=float(row.get('Low', 0) or 0),
                    close=float(row.get('Close', 0) or 0),
                    volume=float(row.get('Volume', 0) or 0),
                    timestamp=idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else datetime.now(),
                    turnover=float(row.get('Close', 0) or 0) * float(row.get('Volume', 0) or 0),
                ))

            logger.info(
                f"Yahoo Finance: 获取K线成功, symbol={symbol}, "
                f"interval={interval}, count={len(klines)}"
            )
            return klines

        except Exception as e:
            raise MarketDataError(
                f"获取K线数据失败: {e}",
                source="YahooFinance"
            )

    async def subscribe_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], Awaitable[None]]
    ) -> None:
        """
        订阅实时行情（轮询模式）

        由于 Yahoo Finance 不支持真正的实时推送，使用轮询方式模拟。
        """
        self._ensure_connected()

        for symbol in symbols:
            self._quote_callbacks[symbol] = callback

        # 启动轮询任务
        async def _poll_loop():
            """轮询获取行情"""
            poll_interval = self.config.get("poll_interval", 30)
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
                                f"Yahoo Finance: 轮询 {symbol} 行情异常: {e}"
                            )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Yahoo Finance: 轮询异常: {e}")
                await asyncio.sleep(poll_interval)

        self._poll_task = asyncio.create_task(_poll_loop())
        logger.info(f"Yahoo Finance: 订阅行情成功 (轮询模式), symbols={symbols}")

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

        logger.info(f"Yahoo Finance: 取消订阅行情, symbols={symbols}")
