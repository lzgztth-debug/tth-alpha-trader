"""模拟交易引擎模块

提供完整的模拟交易功能，包括模拟账户管理、订单撮合、手续费和滑点模拟。
支持多账户管理和数据库持久化。
"""

from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.models.account import Account, AccountType
from src.models.order import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
)
from src.models.position import Position


# ===========================================================================
# 模拟交易配置
# ===========================================================================


@dataclass
class PaperTradingConfig:
    """模拟交易配置"""
    # 账户默认配置
    default_initial_cash: float = 1_000_000.0
    default_broker: str = "paper_broker"
    # 手续费配置
    commission_rate: float = 0.0003  # 佣金费率 (万分之三)
    min_commission: float = 5.0  # 最低佣金
    stamp_tax_rate: float = 0.001  # 印花税率 (千分之一，仅卖出)
    # 滑点配置
    slippage_enabled: bool = True
    slippage_min_pct: float = 0.0  # 最小滑点百分比
    slippage_max_pct: float = 0.2  # 最大滑点百分比
    slippage_fixed_pct: Optional[float] = None  # 固定滑点百分比，设置后忽略随机滑点
    # 撮合配置
    auto_fill_market_orders: bool = True  # 市价单自动撮合
    limit_order_price_tolerance: float = 0.01  # 限价单价格容差 (1%)


# ===========================================================================
# Trade Record - 成交记录
# ===========================================================================


@dataclass
class TradeRecord:
    """成交记录"""
    trade_id: str
    order_id: str
    account_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    stamp_tax: float
    slippage_pct: float
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "stamp_tax": self.stamp_tax,
            "slippage_pct": self.slippage_pct,
            "timestamp": self.timestamp.isoformat(),
        }


# ===========================================================================
# PaperTradingEngine - 模拟交易引擎
# ===========================================================================


class PaperTradingError(Exception):
    """模拟交易异常基类"""
    pass


class InsufficientFundsError(PaperTradingError):
    """资金不足"""
    pass


class AccountNotFoundError(PaperTradingError):
    """账户不存在"""
    pass


class OrderNotFoundError(PaperTradingError):
    """订单不存在"""
    pass


class PaperTradingEngine:
    """模拟交易引擎

    提供完整的模拟交易功能:
    - 多账户管理 (创建、查询、重置)
    - 模拟订单撮合 (市价单、限价单)
    - 手续费模拟 (佣金、印花税)
    - 滑点模拟 (固定/随机)
    - 持仓管理和盈亏计算
    - 数据持久化到JSON文件
    """

    def __init__(
        self,
        config: Optional[PaperTradingConfig] = None,
        data_dir: Optional[str] = None,
    ) -> None:
        """
        初始化PaperTradingEngine。

        Args:
            config:   模拟交易配置，None则使用默认配置。
            data_dir: 数据持久化目录，None则使用默认目录。
        """
        self._config = config or PaperTradingConfig()

        if data_dir is None:
            data_dir = str(
                Path(__file__).resolve().parent.parent.parent / "data" / "paper_trading"
            )
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # {account_id: Account}
        self._accounts: Dict[str, Account] = {}
        # {(account_id, symbol): Position}
        self._positions: Dict[Tuple[str, str], Position] = {}
        # {order_id: Order}
        self._orders: Dict[str, Order] = {}
        # {account_id: [order_id, ...]}
        self._account_orders: Dict[str, List[str]] = defaultdict(list)
        # {trade_id: TradeRecord}
        self._trades: Dict[str, TradeRecord] = {}
        # {account_id: [trade_id, ...]}
        self._account_trades: Dict[str, List[str]] = defaultdict(list)
        # 当前市场价格 {symbol: price}
        self._market_prices: Dict[str, float] = {}

        logger.info(
            "模拟交易引擎初始化完成: data_dir={}, initial_cash={:.2f}",
            self._data_dir,
            self._config.default_initial_cash,
        )

    # ------------------------------------------------------------------
    # 账户管理
    # ------------------------------------------------------------------

    def create_account(
        self,
        account_id: str,
        initial_cash: Optional[float] = None,
        broker: Optional[str] = None,
    ) -> Account:
        """创建模拟账户。

        Args:
            account_id:    账户ID。
            initial_cash:  初始资金，None则使用默认值。
            broker:        券商名称。

        Returns:
            创建的 Account 实例。

        Raises:
            PaperTradingError: 账户已存在。
        """
        if account_id in self._accounts:
            raise PaperTradingError(f"账户已存在: {account_id}")

        cash = initial_cash if initial_cash is not None else self._config.default_initial_cash
        brk = broker or self._config.default_broker
        now = datetime.now()

        account = Account(
            account_id=account_id,
            broker=brk,
            account_type=AccountType.PAPER,
            total_value=cash,
            cash=cash,
            market_value=0.0,
            available_cash=cash,
            created_at=now,
            updated_at=now,
        )

        self._accounts[account_id] = account
        logger.info(
            "模拟账户已创建: id={}, cash={:.2f}", account_id, cash
        )
        return account

    def get_account(self, account_id: str) -> Account:
        """获取账户信息。

        Args:
            account_id: 账户ID。

        Returns:
            Account 实例。

        Raises:
            AccountNotFoundError: 账户不存在。
        """
        account = self._accounts.get(account_id)
        if account is None:
            raise AccountNotFoundError(f"账户不存在: {account_id}")
        return account

    def get_all_accounts(self) -> List[Account]:
        """获取所有账户。"""
        return list(self._accounts.values())

    def reset_account(self, account_id: str) -> Account:
        """重置账户 (清空持仓和订单，恢复初始资金)。

        Args:
            account_id: 账户ID。

        Returns:
            重置后的 Account 实例。

        Raises:
            AccountNotFoundError: 账户不存在。
        """
        if account_id not in self._accounts:
            raise AccountNotFoundError(f"账户不存在: {account_id}")

        # 清除该账户的持仓
        keys_to_remove = [
            k for k in self._positions if k[0] == account_id
        ]
        for key in keys_to_remove:
            del self._positions[key]

        # 取消所有待处理订单
        pending_order_ids = self._account_orders.get(account_id, [])
        for oid in pending_order_ids:
            if oid in self._orders:
                self._orders[oid].status = OrderStatus.CANCELLED

        # 重置账户资金
        now = datetime.now()
        account = self._accounts[account_id]
        initial_cash = self._config.default_initial_cash
        account.cash = initial_cash
        account.available_cash = initial_cash
        account.market_value = 0.0
        account.total_value = initial_cash
        account.updated_at = now

        logger.info("模拟账户已重置: id={}, cash={:.2f}", account_id, initial_cash)
        return account

    def delete_account(self, account_id: str) -> bool:
        """删除账户及其所有关联数据。

        Args:
            account_id: 账户ID。

        Returns:
            是否删除成功。
        """
        if account_id not in self._accounts:
            return False

        # 删除持仓
        keys_to_remove = [
            k for k in self._positions if k[0] == account_id
        ]
        for key in keys_to_remove:
            del self._positions[key]

        # 删除订单
        order_ids = self._account_orders.pop(account_id, [])
        for oid in order_ids:
            self._orders.pop(oid, None)

        # 删除成交记录
        trade_ids = self._account_trades.pop(account_id, [])
        for tid in trade_ids:
            self._trades.pop(tid, None)

        # 删除账户
        del self._accounts[account_id]

        logger.info("模拟账户已删除: id={}", account_id)
        return True

    # ------------------------------------------------------------------
    # 持仓查询
    # ------------------------------------------------------------------

    def get_positions(self, account_id: str) -> List[Position]:
        """获取账户的所有持仓。

        Args:
            account_id: 账户ID。

        Returns:
            持仓列表 (仅非零持仓)。
        """
        return [
            p
            for (aid, _), p in self._positions.items()
            if aid == account_id and p.quantity > 0
        ]

    def get_position(
        self, account_id: str, symbol: str
    ) -> Optional[Position]:
        """获取指定持仓。"""
        return self._positions.get((account_id, symbol.upper().strip()))

    # ------------------------------------------------------------------
    # 订单管理
    # ------------------------------------------------------------------

    def place_order(
        self,
        account_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
    ) -> Order:
        """下单。

        Args:
            account_id: 账户ID。
            symbol:     标的代码。
            side:       买卖方向。
            quantity:   数量。
            order_type: 订单类型。
            price:      限价单价格。

        Returns:
            创建的 Order 实例。

        Raises:
            AccountNotFoundError: 账户不存在。
            InsufficientFundsError: 资金不足。
            PaperTradingError: 参数不合法。
        """
        # 校验账户
        if account_id not in self._accounts:
            raise AccountNotFoundError(f"账户不存在: {account_id}")

        if quantity <= 0:
            raise PaperTradingError(f"数量必须大于0: {quantity}")

        symbol = symbol.upper().strip()
        market_price = self._market_prices.get(symbol, 0.0)

        if order_type == OrderType.LIMIT and price is None:
            raise PaperTradingError("限价单必须指定价格")

        # 买入时检查资金
        if side == OrderSide.BUY:
            exec_price = price if price else market_price
            if exec_price <= 0:
                raise PaperTradingError(
                    f"无法确定执行价格: symbol={symbol}, 请先更新市场价格"
                )
            estimated_cost = exec_price * quantity
            account = self._accounts[account_id]
            if estimated_cost > account.available_cash:
                raise InsufficientFundsError(
                    f"资金不足: 需要={estimated_cost:.2f}, "
                    f"可用={account.available_cash:.2f}"
                )

        # 卖出时检查持仓
        if side == OrderSide.SELL:
            position = self._positions.get((account_id, symbol))
            available_qty = position.quantity if position else 0
            if quantity > available_qty:
                raise PaperTradingError(
                    f"持仓不足: 需要={quantity}, 可用={available_qty}"
                )

        # 创建订单
        order_id = str(uuid.uuid4())
        now = datetime.now()
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
            created_at=now,
            account_id=account_id,
            broker=self._config.default_broker,
        )

        self._orders[order_id] = order
        self._account_orders[account_id].append(order_id)

        logger.info(
            "模拟订单已创建: id={}, account={}, {} {} {} x{}",
            order_id,
            account_id,
            side.value,
            symbol,
            order_type.value,
            quantity,
        )

        # 市价单自动撮合
        if order_type == OrderType.MARKET and self._config.auto_fill_market_orders:
            if market_price > 0:
                self._try_match_order(order_id, market_price)

        return order

    def cancel_order(self, account_id: str, order_id: str) -> Order:
        """取消订单。

        Args:
            account_id: 账户ID。
            order_id:   订单ID。

        Returns:
            取消后的 Order。

        Raises:
            OrderNotFoundError: 订单不存在。
            PaperTradingError: 订单无法取消。
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"订单不存在: {order_id}")

        if order.account_id != account_id:
            raise PaperTradingError(
                f"订单不属于该账户: order_account={order.account_id}, "
                f"request_account={account_id}"
            )

        if order.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED):
            raise PaperTradingError(
                f"订单状态 {order.status.value} 不允许取消"
            )

        order.status = OrderStatus.CANCELLED
        logger.info("模拟订单已取消: id={}", order_id)
        return order

    def get_orders(
        self,
        account_id: str,
        status: Optional[OrderStatus] = None,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        """获取账户的订单列表。

        Args:
            account_id: 账户ID。
            status:     按状态筛选。
            symbol:     按标的筛选。

        Returns:
            订单列表。
        """
        order_ids = self._account_orders.get(account_id, [])
        orders = [self._orders[oid] for oid in order_ids if oid in self._orders]

        if status is not None:
            orders = [o for o in orders if o.status == status]
        if symbol is not None:
            orders = [o for o in orders if o.symbol == symbol.upper().strip()]

        return list(reversed(orders))

    def get_trades(self, account_id: str) -> List[TradeRecord]:
        """获取账户的成交记录。

        Args:
            account_id: 账户ID。

        Returns:
            成交记录列表。
        """
        trade_ids = self._account_trades.get(account_id, [])
        trades = [self._trades[tid] for tid in trade_ids if tid in self._trades]
        return list(reversed(trades))

    # ------------------------------------------------------------------
    # 市场价格更新
    # ------------------------------------------------------------------

    def update_market_prices(self, prices: Dict[str, float]) -> int:
        """更新市场价格并尝试撮合挂单。

        Args:
            prices: {symbol: price} 字典。

        Returns:
            更新的价格数量。
        """
        updated_count = 0
        for symbol, price in prices.items():
            symbol = symbol.upper().strip()
            old_price = self._market_prices.get(symbol, 0.0)
            self._market_prices[symbol] = price
            updated_count += 1

            if old_price != price:
                # 更新持仓的当前价格
                self._update_position_prices(symbol, price)

                # 尝试撮合挂单
                self._match_orders_for_symbol(symbol, price)

        if updated_count > 0:
            logger.debug("市场价格已更新: count={}", updated_count)

        return updated_count

    def get_market_price(self, symbol: str) -> float:
        """获取市场价格。"""
        return self._market_prices.get(symbol.upper().strip(), 0.0)

    # ------------------------------------------------------------------
    # 盈亏计算
    # ------------------------------------------------------------------

    def calculate_pnl(self, account_id: str) -> Dict[str, Any]:
        """计算账户的综合盈亏。

        Args:
            account_id: 账户ID。

        Returns:
            盈亏信息字典。
        """
        if account_id not in self._accounts:
            raise AccountNotFoundError(f"账户不存在: {account_id}")

        account = self._accounts[account_id]
        positions = self.get_positions(account_id)

        # 未实现盈亏
        total_unrealized_pnl = 0.0
        total_market_value = 0.0
        total_cost = 0.0

        for pos in positions:
            total_unrealized_pnl += pos.unrealized_pnl
            total_market_value += pos.market_value
            total_cost += pos.avg_cost * pos.quantity

        # 已实现盈亏 (从成交记录计算)
        total_realized_pnl = 0.0
        total_commission = 0.0
        total_stamp_tax = 0.0

        trade_ids = self._account_trades.get(account_id, [])
        for tid in trade_ids:
            trade = self._trades.get(tid)
            if trade is None:
                continue
            total_commission += trade.commission
            total_stamp_tax += trade.stamp_tax

            # 卖出时计算已实现盈亏
            if trade.side == OrderSide.SELL:
                pos = self._positions.get((account_id, trade.symbol))
                if pos and pos.avg_cost > 0:
                    realized = (trade.price - pos.avg_cost) * trade.quantity
                    total_realized_pnl += realized

        # 总盈亏
        total_pnl = total_unrealized_pnl + total_realized_pnl
        total_fees = total_commission + total_stamp_tax
        net_pnl = total_pnl - total_fees

        # 收益率
        initial_cash = self._config.default_initial_cash
        return_pct = (net_pnl / initial_cash * 100) if initial_cash > 0 else 0.0

        return {
            "account_id": account_id,
            "initial_cash": initial_cash,
            "current_cash": round(account.cash, 2),
            "market_value": round(total_market_value, 2),
            "total_value": round(account.cash + total_market_value, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "realized_pnl": round(total_realized_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "total_commission": round(total_commission, 2),
            "total_stamp_tax": round(total_stamp_tax, 2),
            "total_fees": round(total_fees, 2),
            "net_pnl": round(net_pnl, 2),
            "return_pct": round(return_pct, 4),
            "position_count": len(positions),
            "trade_count": len(trade_ids),
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    async def save_to_database(self) -> Dict[str, bool]:
        """将模拟数据持久化到JSON文件。

        Returns:
            {"accounts": bool, "orders": bool, "positions": bool, "trades": bool}
        """
        results: Dict[str, bool] = {}

        try:
            # 保存账户数据
            accounts_data = {}
            for aid, account in self._accounts.items():
                accounts_data[aid] = {
                    "account_id": account.account_id,
                    "broker": account.broker,
                    "account_type": account.account_type.value,
                    "total_value": account.total_value,
                    "cash": account.cash,
                    "market_value": account.market_value,
                    "available_cash": account.available_cash,
                    "created_at": account.created_at.isoformat() if account.created_at else None,
                    "updated_at": account.updated_at.isoformat() if account.updated_at else None,
                }
            accounts_file = self._data_dir / "accounts.json"
            accounts_file.write_text(
                json.dumps(accounts_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results["accounts"] = True

            # 保存订单数据
            orders_data = {}
            for oid, order in self._orders.items():
                orders_data[oid] = {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "order_type": order.order_type.value,
                    "quantity": order.quantity,
                    "price": order.price,
                    "status": order.status.value,
                    "filled_quantity": order.filled_quantity,
                    "filled_price": order.filled_price,
                    "fee": order.fee,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                    "account_id": order.account_id,
                    "broker": order.broker,
                }
            orders_file = self._data_dir / "orders.json"
            orders_file.write_text(
                json.dumps(orders_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results["orders"] = True

            # 保存持仓数据
            positions_data = {}
            for (aid, symbol), pos in self._positions.items():
                key = f"{aid}:{symbol}"
                positions_data[key] = {
                    "account_id": pos.account_id,
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "current_price": pos.current_price,
                    "market_value": pos.market_value,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                }
            positions_file = self._data_dir / "positions.json"
            positions_file.write_text(
                json.dumps(positions_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results["positions"] = True

            # 保存成交记录
            trades_data = {}
            for tid, trade in self._trades.items():
                trades_data[tid] = trade.to_dict()
            trades_file = self._data_dir / "trades.json"
            trades_file.write_text(
                json.dumps(trades_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results["trades"] = True

            logger.info("模拟交易数据已持久化: {}", results)
        except Exception as e:
            logger.error("持久化失败: {}", e)
            for key in ("accounts", "orders", "positions", "trades"):
                results.setdefault(key, False)

        return results

    async def load_from_database(self) -> Dict[str, int]:
        """从JSON文件加载模拟数据。

        Returns:
            {"accounts": int, "orders": int, "positions": int, "trades": int}
        """
        results: Dict[str, int] = {}

        try:
            # 加载账户
            accounts_file = self._data_dir / "accounts.json"
            if accounts_file.exists():
                data = json.loads(accounts_file.read_text(encoding="utf-8"))
                for aid, info in data.items():
                    account = Account(
                        account_id=info["account_id"],
                        broker=info["broker"],
                        account_type=AccountType(info["account_type"]),
                        total_value=info.get("total_value", 0.0),
                        cash=info.get("cash", 0.0),
                        market_value=info.get("market_value", 0.0),
                        available_cash=info.get("available_cash", 0.0),
                        created_at=(
                            datetime.fromisoformat(info["created_at"])
                            if info.get("created_at")
                            else None
                        ),
                        updated_at=(
                            datetime.fromisoformat(info["updated_at"])
                            if info.get("updated_at")
                            else None
                        ),
                    )
                    self._accounts[aid] = account
                results["accounts"] = len(data)

            # 加载订单
            orders_file = self._data_dir / "orders.json"
            if orders_file.exists():
                data = json.loads(orders_file.read_text(encoding="utf-8"))
                for oid, info in data.items():
                    order = Order(
                        order_id=info["order_id"],
                        symbol=info["symbol"],
                        side=OrderSide(info["side"]),
                        order_type=OrderType(info["order_type"]),
                        quantity=info["quantity"],
                        price=info.get("price"),
                        status=OrderStatus(info["status"]),
                        filled_quantity=info.get("filled_quantity", 0.0),
                        filled_price=info.get("filled_price", 0.0),
                        fee=info.get("fee", 0.0),
                        created_at=(
                            datetime.fromisoformat(info["created_at"])
                            if info.get("created_at")
                            else None
                        ),
                        filled_at=(
                            datetime.fromisoformat(info["filled_at"])
                            if info.get("filled_at")
                            else None
                        ),
                        account_id=info.get("account_id"),
                        broker=info.get("broker"),
                    )
                    self._orders[oid] = order
                    if order.account_id:
                        self._account_orders[order.account_id].append(oid)
                results["orders"] = len(data)

            # 加载持仓
            positions_file = self._data_dir / "positions.json"
            if positions_file.exists():
                data = json.loads(positions_file.read_text(encoding="utf-8"))
                for key, info in data.items():
                    position = Position(
                        symbol=info["symbol"],
                        quantity=info["quantity"],
                        avg_cost=info.get("avg_cost", 0.0),
                        current_price=info.get("current_price", 0.0),
                        market_value=info.get("market_value", 0.0),
                        unrealized_pnl=info.get("unrealized_pnl", 0.0),
                        unrealized_pnl_pct=info.get("unrealized_pnl_pct", 0.0),
                        account_id=info.get("account_id"),
                    )
                    self._positions[(info["account_id"], info["symbol"])] = position
                results["positions"] = len(data)

            # 加载成交记录
            trades_file = self._data_dir / "trades.json"
            if trades_file.exists():
                data = json.loads(trades_file.read_text(encoding="utf-8"))
                for tid, info in data.items():
                    trade = TradeRecord(
                        trade_id=info["trade_id"],
                        order_id=info["order_id"],
                        account_id=info["account_id"],
                        symbol=info["symbol"],
                        side=OrderSide(info["side"]),
                        quantity=info["quantity"],
                        price=info["price"],
                        commission=info.get("commission", 0.0),
                        stamp_tax=info.get("stamp_tax", 0.0),
                        slippage_pct=info.get("slippage_pct", 0.0),
                        timestamp=(
                            datetime.fromisoformat(info["timestamp"])
                            if info.get("timestamp")
                            else datetime.now()
                        ),
                    )
                    self._trades[tid] = trade
                    self._account_trades[trade.account_id].append(tid)
                results["trades"] = len(data)

            logger.info("模拟交易数据已加载: {}", results)
        except Exception as e:
            logger.error("加载数据失败: {}", e)

        return results

    # ------------------------------------------------------------------
    # 内部方法 - 订单撮合
    # ------------------------------------------------------------------

    def _try_match_order(
        self, order_id: str, market_price: float
    ) -> Optional[Order]:
        """尝试撮合订单。

        Args:
            order_id:     订单ID。
            market_price: 当前市场价格。

        Returns:
            撮合后的订单，未撮合则返回None。
        """
        order = self._orders.get(order_id)
        if order is None or order.status not in (
            OrderStatus.PENDING,
            OrderStatus.PARTIAL_FILLED,
        ):
            return None

        if order.order_type == OrderType.MARKET:
            # 市价单直接以市场价撮合
            return self._execute_fill(order, market_price)

        elif order.order_type == OrderType.LIMIT and order.price is not None:
            # 限价单检查价格
            if order.side == OrderSide.BUY:
                # 买入限价单: 市场价 <= 委托价 时成交
                if market_price <= order.price * (1 + self._config.limit_order_price_tolerance):
                    return self._execute_fill(order, market_price)
            elif order.side == OrderSide.SELL:
                # 卖出限价单: 市场价 >= 委托价 时成交
                if market_price >= order.price * (1 - self._config.limit_order_price_tolerance):
                    return self._execute_fill(order, market_price)

        return None

    def _execute_fill(
        self, order: Order, market_price: float
    ) -> Order:
        """执行订单成交。

        Args:
            order:       订单。
            market_price: 市场价格。

        Returns:
            更新后的订单。
        """
        # 计算滑点
        slippage_pct = self._calculate_slippage(order.side)
        if order.side == OrderSide.BUY:
            exec_price = market_price * (1 + slippage_pct / 100)
        else:
            exec_price = market_price * (1 - slippage_pct / 100)
        exec_price = round(exec_price, 4)

        # 计算手续费
        trade_value = exec_price * order.quantity
        commission = max(
            round(trade_value * self._config.commission_rate, 2),
            self._config.min_commission,
        )
        stamp_tax = 0.0
        if order.side == OrderSide.SELL:
            stamp_tax = round(trade_value * self._config.stamp_tax_rate, 2)
        total_fee = commission + stamp_tax

        # 更新订单状态
        remaining_qty = order.quantity - order.filled_quantity
        fill_qty = remaining_qty

        order.filled_quantity = order.quantity
        order.filled_price = exec_price
        order.fee = round(order.fee + total_fee, 2)
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now()

        # 更新持仓
        account_id = order.account_id
        if account_id:
            if order.side == OrderSide.BUY:
                self._update_position_buy(
                    account_id, order.symbol, fill_qty, exec_price
                )
                # 扣减资金
                account = self._accounts.get(account_id)
                if account:
                    cost = exec_price * fill_qty + total_fee
                    account.cash = round(account.cash - cost, 2)
                    account.available_cash = round(account.available_cash - cost, 2)
            elif order.side == OrderSide.SELL:
                self._update_position_sell(
                    account_id, order.symbol, fill_qty, exec_price
                )
                # 增加资金
                account = self._accounts.get(account_id)
                if account:
                    proceeds = exec_price * fill_qty - total_fee
                    account.cash = round(account.cash + proceeds, 2)
                    account.available_cash = round(account.available_cash + proceeds, 2)

            # 同步账户总资产
            self._sync_account_value(account_id)

        # 创建成交记录
        trade_id = str(uuid.uuid4())
        trade = TradeRecord(
            trade_id=trade_id,
            order_id=order.order_id,
            account_id=account_id or "",
            symbol=order.symbol,
            side=order.side,
            quantity=fill_qty,
            price=exec_price,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage_pct=slippage_pct,
        )
        self._trades[trade_id] = trade
        if account_id:
            self._account_trades[account_id].append(trade_id)

        logger.info(
            "订单已成交: id={}, {} {} x{} @{}, fee={:.2f} (commission={:.2f}, tax={:.2f}), slippage={:.3f}%",
            order.order_id,
            order.side.value,
            order.symbol,
            fill_qty,
            exec_price,
            total_fee,
            commission,
            stamp_tax,
            slippage_pct,
        )

        return order

    def _match_orders_for_symbol(self, symbol: str, price: float) -> int:
        """对指定标的的所有挂单尝试撮合。

        Args:
            symbol: 标的代码。
            price:  当前价格。

        Returns:
            撮合的订单数量。
        """
        matched = 0
        for oid, order in list(self._orders.items()):
            if order.symbol != symbol:
                continue
            if order.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL_FILLED):
                continue
            result = self._try_match_order(oid, price)
            if result is not None:
                matched += 1
        return matched

    # ------------------------------------------------------------------
    # 内部方法 - 持仓更新
    # ------------------------------------------------------------------

    def _update_position_buy(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        """买入后更新持仓。"""
        key = (account_id, symbol)
        existing = self._positions.get(key)
        now = datetime.now()

        if existing and existing.quantity > 0:
            new_qty = existing.quantity + quantity
            new_avg = (
                (existing.avg_cost * existing.quantity + price * quantity)
                / new_qty
            )
            existing.quantity = round(new_qty, 4)
            existing.avg_cost = round(new_avg, 4)
            existing.current_price = price
            existing.market_value = round(new_qty * price, 2)
            existing.unrealized_pnl = round((price - new_avg) * new_qty, 2)
            existing.unrealized_pnl_pct = round(
                (price - new_avg) / new_avg if new_avg > 0 else 0.0, 6
            )
            existing.updated_at = now
        else:
            self._positions[key] = Position(
                symbol=symbol,
                quantity=quantity,
                avg_cost=price,
                current_price=price,
                market_value=round(quantity * price, 2),
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                account_id=account_id,
                created_at=now,
                updated_at=now,
            )

    def _update_position_sell(
        self,
        account_id: str,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        """卖出后更新持仓。"""
        key = (account_id, symbol)
        existing = self._positions.get(key)

        if existing is None or existing.quantity < quantity:
            available = existing.quantity if existing else 0
            logger.error(
                "模拟卖出持仓不足: symbol={}, need={}, have={}",
                symbol,
                quantity,
                available,
            )
            return

        new_qty = existing.quantity - quantity
        now = datetime.now()

        if new_qty < 1e-8:
            existing.quantity = 0.0
            existing.market_value = 0.0
            existing.unrealized_pnl = 0.0
            existing.unrealized_pnl_pct = 0.0
            existing.updated_at = now
        else:
            existing.quantity = round(new_qty, 4)
            existing.current_price = price
            existing.market_value = round(new_qty * price, 2)
            existing.unrealized_pnl = round(
                (price - existing.avg_cost) * new_qty, 2
            )
            existing.unrealized_pnl_pct = round(
                (price - existing.avg_cost) / existing.avg_cost
                if existing.avg_cost > 0
                else 0.0,
                6,
            )
            existing.updated_at = now

    def _update_position_prices(
        self, symbol: str, price: float
    ) -> None:
        """更新所有账户中该标的的持仓价格。"""
        for (aid, sym), pos in self._positions.items():
            if sym == symbol and pos.quantity > 0:
                pos.current_price = price
                pos.market_value = round(pos.quantity * price, 2)
                pos.unrealized_pnl = round(
                    (price - pos.avg_cost) * pos.quantity, 2
                )
                pos.unrealized_pnl_pct = round(
                    (price - pos.avg_cost) / pos.avg_cost
                    if pos.avg_cost > 0
                    else 0.0,
                    6,
                )
                pos.updated_at = datetime.now()

    def _sync_account_value(self, account_id: str) -> None:
        """同步账户总资产。"""
        account = self._accounts.get(account_id)
        if account is None:
            return

        positions = self.get_positions(account_id)
        market_value = sum(p.market_value for p in positions)
        account.market_value = round(market_value, 2)
        account.total_value = round(account.cash + market_value, 2)
        account.updated_at = datetime.now()

    # ------------------------------------------------------------------
    # 内部方法 - 滑点计算
    # ------------------------------------------------------------------

    def _calculate_slippage(self, side: OrderSide) -> float:
        """计算滑点百分比。

        Args:
            side: 买卖方向。

        Returns:
            滑点百分比 (正数)。
        """
        if not self._config.slippage_enabled:
            return 0.0

        if self._config.slippage_fixed_pct is not None:
            return self._config.slippage_fixed_pct

        # 随机滑点
        min_pct = self._config.slippage_min_pct
        max_pct = self._config.slippage_max_pct
        return round(random.uniform(min_pct, max_pct), 4)
