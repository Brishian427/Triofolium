"""Baseline strategy that never trades."""

from __future__ import annotations

from trifolium.strategy.base import Strategy


class DoNothingStrategy(Strategy):
    """No-op strategy used to prove the engine has no phantom P&L."""

    name: str = "do_nothing"
    symbols: list[str] = ["AUDUSD"]
