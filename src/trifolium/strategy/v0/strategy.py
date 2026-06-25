"""StrategyV0 orchestration: predictor, trader, and portfolio constraints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import PrivateAttr

from trifolium.backtest.types import AccountState, Bar, Order, Tick
from trifolium.strategy.base import Strategy
from trifolium.strategy.v0.config import StrategyV0Config, load_strategy_v0_config
from trifolium.strategy.v0.portfolio import apply_portfolio_scaling
from trifolium.strategy.v0.predictor import BarSnapshot, StrategyV0Predictor
from trifolium.strategy.v0.trader import StrategyV0Trader


class StrategyV0(Strategy):
    """Two-layer StrategyV0 implementation for Task 04."""

    name: str = "strategy_v0"
    symbols: list[str] = []

    _settings: StrategyV0Config = PrivateAttr()
    _predictor: StrategyV0Predictor = PrivateAttr()
    _trader: StrategyV0Trader = PrivateAttr()
    _bar_history: dict[str, list[BarSnapshot]] = PrivateAttr(default_factory=dict)
    _last_decision_bar: datetime | None = PrivateAttr(default=None)
    _last_signals: dict[str, float] = PrivateAttr(default_factory=dict)
    _portfolio_messages: list[str] = PrivateAttr(default_factory=list)

    def __init__(self, config_path: str | Path | None = None, **data: object) -> None:
        settings = load_strategy_v0_config(config_path)
        data.setdefault("symbols", settings.tradable_symbols)
        super().__init__(**data)
        self._settings = settings
        self._predictor = StrategyV0Predictor(settings)
        self._trader = StrategyV0Trader(settings)
        self._bar_history = {symbol: [] for symbol in settings.tradable_symbols}

    @property
    def destroyer_symbols(self) -> set[str]:
        """Symbols currently forced flat after recalibration validation."""

        return set(self._predictor.destroyers)

    @property
    def last_signals(self) -> dict[str, float]:
        """Most recent compressed signals by symbol."""

        return dict(self._last_signals)

    @property
    def portfolio_messages(self) -> list[str]:
        """Most recent portfolio constraint messages."""

        return list(self._portfolio_messages)

    def should_call_on_tick(self, tick: Tick) -> bool:
        return False

    def should_call_on_bar_close(self, bar: Bar) -> bool:
        if bar.symbol not in self._settings.tradable_symbols:
            return False
        return bar.timestamp.minute % self._settings.bar_interval_minutes == 0

    def on_tick(self, tick: Tick, state: AccountState) -> list[Order]:
        return []

    def on_bar_close(self, bar: Bar, state: AccountState) -> list[Order]:
        self._append_bar(bar)
        if self._last_decision_bar == bar.timestamp:
            return []
        if not all(symbol in state.latest_ticks for symbol in self._settings.tradable_symbols):
            return []
        if not all(self._has_bar_at_timestamp(symbol, bar.timestamp) for symbol in self._settings.tradable_symbols):
            return []
        self._last_decision_bar = bar.timestamp
        prices = {
            symbol: state.latest_ticks[symbol].mid
            for symbol in self._settings.tradable_symbols
        }
        if not self._predictor.has_active_models:
            return []
        predictions = self._predictor.predict_from_bars(self._recent_prediction_history())
        if not predictions:
            return []
        target_lots, signals = self._trader.target_lots(predictions, state.equity, prices)
        self._last_signals = signals
        scaled_lots, _scale, messages = apply_portfolio_scaling(target_lots, prices, state.equity, self._settings)
        self._portfolio_messages = messages
        return self._orders_from_targets(scaled_lots, state)

    def recalibrate(self, state: AccountState, history: list[Tick]) -> None:
        self._predictor.fit(history)

    def recalibrate_from_bars(self, bars: dict[str, list[BarSnapshot]]) -> None:
        """Fit the predictor from already aggregated bars without tick materialization."""

        self._predictor.fit_from_bars(bars)

    def _append_bar(self, bar: Bar) -> None:
        if bar.symbol not in self._bar_history:
            return
        self._bar_history[bar.symbol].append(
            BarSnapshot(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                mid=float(bar.close),
                spread=float(bar.ask - bar.bid),
            )
        )

    def _has_bar_at_timestamp(self, symbol: str, timestamp: datetime) -> bool:
        return bool(self._bar_history.get(symbol)) and self._bar_history[symbol][-1].timestamp == timestamp

    def _recent_prediction_history(self) -> dict[str, list[BarSnapshot]]:
        lookback = self._predictor.feature_builder.max_lookback + 2
        return {symbol: bars[-lookback:] for symbol, bars in self._bar_history.items()}

    def _orders_from_targets(self, target_lots: dict[str, Decimal], state: AccountState) -> list[Order]:
        orders: list[Order] = []
        for symbol, target in target_lots.items():
            current = state.positions.get(symbol).lots if symbol in state.positions else Decimal("0")
            delta = target - current
            if abs(delta) < self._settings.broker_lot_step:
                continue
            side = "buy" if delta > 0 else "sell"
            orders.append(Order(symbol=symbol, side=side, lots=abs(delta), tag="strategy_v0_rebalance"))
        return orders
