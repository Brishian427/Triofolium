"""Buy 0.01 lot AUDUSD on the first tick and hold."""

from __future__ import annotations

from decimal import Decimal

from pydantic import PrivateAttr

from trifolium.backtest.types import AccountState, Order, Tick
from trifolium.strategy.base import Strategy


class BuyAndHoldAUDUSDStrategy(Strategy):
    """One-shot long AUDUSD baseline for unrealized P&L sanity checks."""

    name: str = "buy_and_hold_audusd"
    symbols: list[str] = ["AUDUSD"]
    _entered: bool = PrivateAttr(default=False)

    def should_call_on_tick(self, tick: Tick) -> bool:
        return not self._entered and tick.symbol == "AUDUSD"

    def on_tick(self, tick: Tick, state: AccountState) -> list[Order]:
        if self._entered or tick.symbol != "AUDUSD":
            return []
        self._entered = True
        lots = Decimal("0.01") * Decimal(str(self.lot_multiplier))
        return [Order(symbol="AUDUSD", side="buy", lots=lots, tag="buy_and_hold_entry")]
