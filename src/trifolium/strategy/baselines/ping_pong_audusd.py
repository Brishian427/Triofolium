"""Hourly AUDUSD buy/sell round-trip baseline."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import PrivateAttr

from trifolium.backtest.types import AccountState, Order, Tick
from trifolium.strategy.base import Strategy


class PingPongAUDUSDStrategy(Strategy):
    """Every hour, buy 0.01 lot AUDUSD and sell it immediately."""

    name: str = "ping_pong_audusd"
    symbols: list[str] = ["AUDUSD"]
    _last_hour: datetime | None = PrivateAttr(default=None)

    def should_call_on_tick(self, tick: Tick) -> bool:
        if tick.symbol != "AUDUSD":
            return False
        hour = tick.timestamp.replace(minute=0, second=0, microsecond=0)
        return self._last_hour != hour

    def on_tick(self, tick: Tick, state: AccountState) -> list[Order]:
        if tick.symbol != "AUDUSD":
            return []
        hour = tick.timestamp.replace(minute=0, second=0, microsecond=0)
        if self._last_hour == hour:
            return []
        self._last_hour = hour
        lots = Decimal("0.01") * Decimal(str(self.lot_multiplier))
        return [
            Order(symbol="AUDUSD", side="buy", lots=lots, tag="ping_open"),
            Order(symbol="AUDUSD", side="sell", lots=lots, tag="ping_close"),
        ]
