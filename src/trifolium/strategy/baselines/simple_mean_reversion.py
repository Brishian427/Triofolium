"""Simple 50-tick mean-reversion baseline for validation framework smoke tests."""

from __future__ import annotations

from collections import defaultdict, deque
from decimal import Decimal
from statistics import mean, pstdev

from pydantic import PrivateAttr

from trifolium.backtest.types import AccountState, Order, Tick
from trifolium.strategy.base import Strategy


class SimpleMeanReversionStrategy(Strategy):
    """Trade each symbol against a rolling 50-tick mean with a 2 std band."""

    name: str = "simple_mean_reversion"
    symbols: list[str] = ["AUDUSD"]
    config: dict[str, float] = {"window": 50, "std_mult": 2.0, "lot": 0.01}
    _prices: dict[str, deque[float]] = PrivateAttr(default_factory=lambda: defaultdict(lambda: deque(maxlen=50)))

    def on_tick(self, tick: Tick, state: AccountState) -> list[Order]:
        window = int(self.config.get("window", 50))
        std_mult = float(self.config.get("std_mult", 2.0))
        prices = self._prices[tick.symbol]
        if prices.maxlen != window:
            self._prices[tick.symbol] = deque(prices, maxlen=window)
            prices = self._prices[tick.symbol]
        prices.append(float(tick.mid))
        if len(prices) < window:
            return []
        mu = mean(prices)
        sigma = pstdev(prices)
        if sigma == 0:
            return []
        position = state.positions.get(tick.symbol)
        current_lots = position.lots if position is not None else Decimal("0")
        lot = Decimal(str(self.config.get("lot", 0.01))) * Decimal(str(self.lot_multiplier))
        upper = mu + std_mult * sigma
        lower = mu - std_mult * sigma
        price = float(tick.mid)
        if price > upper and current_lots >= 0:
            lots = lot + max(current_lots, Decimal("0"))
            return [Order(symbol=tick.symbol, side="sell", lots=lots, tag="mean_reversion_sell")]
        if price < lower and current_lots <= 0:
            lots = lot + abs(min(current_lots, Decimal("0")))
            return [Order(symbol=tick.symbol, side="buy", lots=lots, tag="mean_reversion_buy")]
        return []
