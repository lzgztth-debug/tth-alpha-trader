# src/adapters/market_data/binance.py
# Binance 行情适配器 - 使用 ccxt 库获取加密货币实时行情

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable, Awaitable
from datetime import datetime

from src.adapters.market_data.base import (
    BaseMarketDataAdapter,
    MarketDataError,
    MarketDataConnectionError,
)
from src.models.market_data import Quote, Kline

logger = logging.getLogger(__name__)


class BinanceMarketDataAdapter(BaseMarketDataAdapter):
    """
    Binance 行情适配器

    使用 ccxt 库获取加密货币实时行情数据，支持 WebSocket 实时订阅。

    配置参数:
        api_key: API Key（可选，公开行情不需要）
        secret_key: Secret Key（可选）
        sandbox: 是否使用测试网，默认 False
        rate_limit: 请求频率限制（毫秒），默认 50
        options: ccxt 额外配置选项
    """

    # K线周期映射
    INTERVAL_MAP = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "3d": "3d",
        "1w": "1w",
        "1M": "1M",
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key", "")
        self.secret_key = self.config.get("secret_key", "")
        self.sandbox = self.config.get("sandbox", False)
        self.rate_limit = self.config.get("rate_limit", 50)
        self.options = self.config.get("options", {})

        self._exchange = None
        self._ws_connected = False

    async def connect(self) -> bool:
        """连接 Binance"""
        try:
            import ccxt.async_support as ccxt

            exchange_config = {
                'enableRateLimit': True,
                'rateLimit': self.rate_limit,
                'options': self.options,
            }

            if self.api_key and self.secret_key:
                exchange_config['apiKey'] = self.api_key
                exchange_config['secret'] = self.secret_key

            if self.sandbox:
                exchange_config['sandbox'] = True
                logger.info("Binance: 使用测试网环境")

            self._exchange = ccxt.binance(exchange_config)
            await self._exchange.load_markets()

            self._connected = True
            logger.info("Binance: 连接成功")
            return True

        except ImportError:
            raise MarketDataConnectionError(
                "ccxt 未安装，请执行: pip install ccxt",
                source="Binance"
            )
        except Exception as e:
            self._connected = False
            raise MarketDataConnectionError(
                f"连接失败: {e}",
                source="Binance"
            )

    async def disconnect(self) -> None:
        """断开 Binance 连接"""
        try:
            self._ws_connected = False
            if hasattr(self, '_watch_task') and self._watch_task:
                self._watch_task.cancel()
                try:
                    await self._watch_task
                except asyncio.CancelledError:
                    pass

            if self._exchange:
                await self._exchange.close()
                self._exchange = None
            self._connected = False
            logger.info("Binance: 已断开连接")
        except Exception as e:
            logger.warning(f"Binance: 断开连接时出错: {e}")
            self._connected = False

    async def get_quote(self, symbol: str) -> Quote:
        """获取单个标的实时行情"""
        self._ensure_connected()
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            quote = self._ticker_to_quote(ticker)
            logger.debug(f"Binance: 获取行情成功, symbol={symbol}")
            return quote
        except Exception as e:
            raise MarketDataError(
                f"获取行情失败: {e}",
                source="Binance"
            )

    async def get_quotes(self, symbols: List[str]) -> List[Quote]:
        """批量获取标的行情"""
        self._ensure_connected()
        try:
            quotes = []
            for symbol in symbols:
                try:
                    ticker = await self._exchange.fetch_ticker(symbol)
                    quotes.append(self._ticker_to_quote(ticker))
                except Exception as e:
                    logger.error(f"Binance: 获取 {symbol} 行情失败: {e}")

            logger.info(f"Binance: 批量获取行情成功, {len(quotes)}/{len(symbols)}")
            return quotes
        except Exception as e:
            raise MarketDataError(
                f"批量获取行情失败: {e}",
                source="Binance"
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
            ccxt_interval = self.INTERVAL_MAP.get(interval, "1d")

            params = {}
            if start_time:
                start_dt = datetime.fromisoformat(start_time)
                params['since'] = int(start_dt.timestamp() * 1000)
            if end_time:
                end_dt = datetime.fromisoformat(end_time)
                params['until'] = end_dt

            ohlcv = await self._exchange.fetch_ohlcv(
                symbol,
                timeframe=ccxt_interval,
                limit=limit,
                params=params,
            )

            klines = []
            for candle in ohlcv:
                timestamp_ms, open_price, high, low, close, volume = candle
                klines.append(Kline(
                    symbol=symbol,
                    interval=interval,
                    open=float(open_price or 0),
                    high=float(high or 0),
                    low=float(low or 0),
                    close=float(close or 0),
                    volume=float(volume or 0),
                    timestamp=datetime.fromtimestamp(timestamp_ms / 1000),
                    turnover=float(close or 0) * float(volume or 0),
                ))

            logger.info(
                f"Binance: 获取K线成功, symbol={symbol}, "
                f"interval={interval}, count={len(klines)}"
            )
            return klines

        except Exception as e:
            raise MarketDataError(
                f"获取K线数据失败: {e}",
                source="Binance"
            )

    async def subscribe_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], Awaitable[None]]
    ) -> None:
        """订阅实时行情（使用 WebSocket）"""
        self._ensure_connected()
        try:
            for symbol in symbols:
                self._quote_callbacks[symbol] = callback

            self._ws_connected = True

            async def _watch_loop():
                """WebSocket 行情监控循环"""
                while self._ws_connected:
                    try:
                        for symbol in list(self._quote_callbacks.keys()):
                            try:
                                ticker = await self._exchange.watch_ticker(symbol)
                                quote = self._ticker_to_quote(ticker)
                                cb = self._quote_callbacks.get(symbol)
                                if cb:
                                    await cb(quote)
                            except asyncio.CancelledError:
                                raise
                            except Exception as e:
                                logger.error(
                                    f"Binance: 获取 {symbol} 行情异常: {e}"
                                )
                                await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Binance: WebSocket 监控异常: {e}")
                        await asyncio.sleep(5)

            self._watch_task = asyncio.create_task(_watch_loop())
            logger.info(f"Binance: 订阅行情成功 (WebSocket), symbols={symbols}")

        except Exception as e:
            raise MarketDataError(
                f"订阅行情失败: {e}",
                source="Binance"
            )

    async def unsubscribe_quotes(self, symbols: List[str]) -> None:
        """取消订阅行情"""
        for symbol in symbols:
            self._quote_callbacks.pop(symbol, None)

        if not self._quote_callbacks:
            self._ws_connected = False
            if hasattr(self, '_watch_task') and self._watch_task:
                self._watch_task.cancel()
                try:
                    await self._watch_task
                except asyncio.CancelledError:
                    pass

        logger.info(f"Binance: 取消订阅行情, symbols={symbols}")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        获取订单簿数据

        Args:
            symbol: 交易对
            limit: 深度档位

        Returns:
            Dict: 包含 bids 和 asks 的订单簿数据
        """
        self._ensure_connected()
        try:
            orderbook = await self._exchange.fetch_order_book(symbol, limit=limit)
            return {
                "symbol": symbol,
                "bids": orderbook.get('bids', []),
                "asks": orderbook.get('asks', []),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            raise MarketDataError(
                f"获取订单簿失败: {e}",
                source="Binance"
            )

    async def get_tickers(self) -> Dict[str, Dict[str, Any]]:
        """获取所有交易对的行情"""
        self._ensure_connected()
        try:
            tickers = await self._exchange.fetch_tickers()
            return tickers
        except Exception as e:
            raise MarketDataError(
                f"获取所有行情失败: {e}",
                source="Binance"
            )

    def _ticker_to_quote(self, ticker: Dict[str, Any]) -> Quote:
        """将 ccxt ticker 转换为 Quote 模型"""
        return Quote(
            symbol=ticker.get('symbol', ''),
            open=float(ticker.get('open', 0) or 0),
            high=float(ticker.get('high', 0) or 0),
            low=float(ticker.get('low', 0) or 0),
            close=float(ticker.get('last', 0) or 0),
            volume=float(ticker.get('baseVolume', 0) or 0),
            prev_close=float(ticker.get('previousClose', 0) or 0),
            timestamp=datetime.now(),
            bid_price=float(ticker.get('bid', 0) or 0),
            ask_price=float(ticker.get('ask', 0) or 0),
            bid_volume=float(ticker.get('bidVolume', 0) or 0),
            ask_volume=float(ticker.get('askVolume', 0) or 0),
            turnover=float(ticker.get('quoteVolume', 0) or 0),
        )
