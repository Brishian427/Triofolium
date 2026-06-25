"""Order execution simulator with netting positions and stop-out logic."""

from __future__ import annotations

import logging
from decimal import Decimal

from trifolium.backtest.config import InstrumentSpec, load_backtest_config, load_instrument_specs
from trifolium.backtest.types import AccountState, Fill, Order, Position, Tick


class Executor:
    """Simulate fills, pending orders, margin, and netting-mode positions."""

    def __init__(
        self,
        instruments: dict[str, InstrumentSpec] | None = None,
        *,
        leverage: Decimal | None = None,
        slippage: Decimal | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        config = load_backtest_config()
        self.instruments = instruments or load_instrument_specs()
        self.leverage = leverage or config.leverage
        self.slippage = slippage if slippage is not None else config.slippage_market_price_units
        self.pending_orders: list[Order] = []
        self.logger = logger or logging.getLogger(__name__)

    def simulate_fill(self, order: Order, tick: Tick, account: AccountState) -> Fill | None:
        """Fill market orders immediately, or enqueue inactive pending orders."""

        if order.symbol != tick.symbol:
            return None
        if order.order_type == "limit" and not self._limit_active(order, tick):
            self.pending_orders.append(order)
            return None
        if order.order_type == "stop" and not self._stop_active(order, tick):
            self.pending_orders.append(order)
            return None
        price = self._execution_price(order, tick)
        fill = Fill(
            timestamp=tick.timestamp,
            symbol=order.symbol,
            side=order.side,
            lots=order.lots,
            price=price,
            order_type=order.order_type,
            tag=order.tag,
        )
        fill.realized_pnl = self.apply_fill(fill, account)
        return fill

    def process_pending_orders(self, tick: Tick, account: AccountState) -> list[Fill]:
        """Activate pending orders whose trigger conditions are met on this tick."""

        remaining: list[Order] = []
        fills: list[Fill] = []
        for order in self.pending_orders:
            active = order.symbol == tick.symbol and (
                (order.order_type == "limit" and self._limit_active(order, tick))
                or (order.order_type == "stop" and self._stop_active(order, tick))
            )
            if not active:
                remaining.append(order)
                continue
            fill = self.simulate_fill(order, tick, account)
            if fill is not None:
                fills.append(fill)
        self.pending_orders = remaining
        return fills

    def apply_fill(self, fill: Fill, account: AccountState) -> Decimal:
        """Update net position and realized balance for a fill."""

        signed_lots = fill.lots if fill.side == "buy" else -fill.lots
        position = account.positions.get(fill.symbol, Position(symbol=fill.symbol))
        realized = Decimal("0")
        old_lots = position.lots
        new_lots = old_lots + signed_lots

        if old_lots == 0 or (old_lots > 0 and signed_lots > 0) or (old_lots < 0 and signed_lots < 0):
            total_abs = abs(old_lots) + abs(signed_lots)
            position.avg_price = (
                (position.avg_price * abs(old_lots)) + (fill.price * abs(signed_lots))
            ) / total_abs
            position.lots = new_lots
        else:
            closing_lots = min(abs(old_lots), abs(signed_lots))
            direction = Decimal("1") if old_lots > 0 else Decimal("-1")
            realized = (fill.price - position.avg_price) * closing_lots * self.contract_size(fill.symbol) * direction
            account.balance += realized
            if new_lots == 0:
                position = Position(symbol=fill.symbol)
            elif old_lots.copy_sign(new_lots) == old_lots:
                position.lots = new_lots
            else:
                position.lots = new_lots
                position.avg_price = fill.price

        if position.lots == 0:
            account.positions.pop(fill.symbol, None)
        else:
            account.positions[fill.symbol] = position
        self.mark_to_market(account)
        return realized

    def mark_to_market(self, account: AccountState) -> None:
        """Recompute equity and margin from current ticks."""

        unrealized = Decimal("0")
        margin = Decimal("0")
        for symbol, position in list(account.positions.items()):
            tick = account.latest_ticks.get(symbol)
            if tick is None:
                continue
            mark = tick.bid if position.lots > 0 else tick.ask
            direction = Decimal("1") if position.lots > 0 else Decimal("-1")
            unrealized += (mark - position.avg_price) * abs(position.lots) * self.contract_size(symbol) * direction
            margin += self.margin_for_position(symbol, position, mark)
        account.equity = account.balance + unrealized
        account.margin_used = margin

    def margin_level(self, account: AccountState) -> Decimal | None:
        if account.margin_used <= 0:
            return None
        return (account.equity / account.margin_used) * Decimal("100")

    def enforce_stop_out(self, account: AccountState, tick: Tick) -> list[Fill]:
        """Auto-close positions if simulated margin level breaches 30%."""

        level = self.margin_level(account)
        if level is None or level >= Decimal("30"):
            return []
        fills: list[Fill] = []
        account.stop_out_events.append(f"{tick.timestamp.isoformat()} margin_level={level}")
        losses = sorted(account.positions.values(), key=lambda pos: self.unrealized_pnl(pos, account), reverse=False)
        for position in losses:
            close_side = "sell" if position.lots > 0 else "buy"
            close_order = Order(symbol=position.symbol, side=close_side, lots=abs(position.lots), order_type="market", tag="stop_out")
            current_tick = account.latest_ticks.get(position.symbol)
            if current_tick is None:
                continue
            fill = self.simulate_fill(close_order, current_tick, account)
            if fill:
                fills.append(fill)
            level = self.margin_level(account)
            if level is None or level >= Decimal("30"):
                break
        return fills

    def unrealized_pnl(self, position: Position, account: AccountState) -> Decimal:
        tick = account.latest_ticks.get(position.symbol)
        if tick is None:
            return Decimal("0")
        mark = tick.bid if position.lots > 0 else tick.ask
        direction = Decimal("1") if position.lots > 0 else Decimal("-1")
        return (mark - position.avg_price) * abs(position.lots) * self.contract_size(position.symbol) * direction

    def contract_size(self, symbol: str) -> Decimal:
        return self.instruments.get(symbol, InstrumentSpec(symbol, "unknown", Decimal("1"), Decimal("0.0001"), Decimal("0.01"))).contract_size

    def margin_for_position(self, symbol: str, position: Position, mark: Decimal) -> Decimal:
        notional = abs(position.lots) * self.contract_size(symbol) * mark
        return notional / self.leverage

    def _execution_price(self, order: Order, tick: Tick) -> Decimal:
        if order.side == "buy":
            return tick.ask + self.slippage
        return tick.bid - self.slippage

    @staticmethod
    def _limit_active(order: Order, tick: Tick) -> bool:
        if order.limit_price is None:
            return False
        return tick.ask <= order.limit_price if order.side == "buy" else tick.bid >= order.limit_price

    @staticmethod
    def _stop_active(order: Order, tick: Tick) -> bool:
        if order.stop_price is None:
            return False
        return tick.ask >= order.stop_price if order.side == "buy" else tick.bid <= order.stop_price
