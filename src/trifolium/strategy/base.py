"""Base strategy interface for the Trifolium backtest engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from trifolium.backtest.types import AccountState, Bar, Order, Tick


class Strategy(BaseModel):
    """Base class for strategies used by the offline engine."""

    name: str
    symbols: list[str]
    config: dict[str, Any] = Field(default_factory=dict)
    lot_multiplier: float = 1.0

    def on_tick(self, tick: Tick, state: AccountState) -> list[Order]:
        return []

    def on_bar_close(self, bar: Bar, state: AccountState) -> list[Order]:
        return []

    def should_call_on_tick(self, tick: Tick) -> bool:
        """Return whether the engine should call `on_tick` for this tick."""

        return True

    def should_call_on_bar_close(self, bar: Bar) -> bool:
        """Return whether the engine should call `on_bar_close` for this bar."""

        return False

    def recalibrate(self, state: AccountState, history: list[Tick]) -> None:
        return None
