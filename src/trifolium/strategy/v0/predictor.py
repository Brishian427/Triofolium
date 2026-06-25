"""Layer 1 predictor for StrategyV0: per-symbol ridge ensembles."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import numpy as np

from trifolium.backtest.types import Bar, Tick
from trifolium.strategy.v0.config import StrategyV0Config


@dataclass(frozen=True)
class BarSnapshot:
    """Compact 15-minute bar view used for feature construction."""

    timestamp: datetime
    symbol: str
    mid: float
    spread: float


class RidgeRegressor:
    """Small NumPy ridge regressor with an unpenalized intercept."""

    def __init__(self, alpha: Decimal) -> None:
        self.alpha = float(alpha)
        self.coef_: np.ndarray | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        design = np.column_stack([np.ones(len(x)), x])
        penalty = np.eye(design.shape[1]) * self.alpha
        penalty[0, 0] = 0.0
        self.coef_ = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            return np.zeros(len(x))
        design = np.column_stack([np.ones(len(x)), x])
        return design @ self.coef_


class PerSymbolEnsemble:
    """Three-bootstrap ridge ensemble for one symbol."""

    def __init__(self, alpha: Decimal, n_bootstraps: int, seeds: list[int]) -> None:
        self.alpha = alpha
        self.n_bootstraps = n_bootstraps
        self.seeds = seeds
        self.models: list[RidgeRegressor] = []

    @property
    def fitted(self) -> bool:
        return bool(self.models)

    def fit(self, x: np.ndarray, y: np.ndarray) -> None:
        self.models = []
        if len(x) == 0:
            return
        for seed in self.seeds[: self.n_bootstraps]:
            rng = np.random.default_rng(seed)
            indexes = rng.integers(0, len(x), size=len(x))
            model = RidgeRegressor(self.alpha)
            model.fit(x[indexes], y[indexes])
            self.models.append(model)

    def predict(self, x: np.ndarray) -> np.ndarray:
        if not self.models:
            return np.zeros(len(x))
        preds = np.array([model.predict(x) for model in self.models])
        return np.mean(preds, axis=0)

    def predict_with_uncertainty(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self.models:
            return np.zeros(len(x)), np.ones(len(x))
        preds = np.array([model.predict(x) for model in self.models])
        return np.mean(preds, axis=0), np.std(preds, axis=0)


class FeatureBuilder:
    """Build StrategyV0 features and cross-sectional rank targets."""

    def __init__(self, settings: StrategyV0Config) -> None:
        self.settings = settings
        self.max_lookback = max(
            [item.lag for item in settings.features.lagged_returns]
            + [item.window for item in settings.features.volatility]
            + [settings.features.bid_ask["spread_rolling_mean_window"]]
            + [settings.features.gold_silver_ratio_lag]
            + [settings.features.macro["dollar_index_proxy_return_lag"]]
        )

    def bars_from_ticks(self, history: list[Tick]) -> dict[str, list[BarSnapshot]]:
        grouped: dict[tuple[str, datetime], Tick] = {}
        minutes = self.settings.bar_interval_minutes
        for tick in history:
            bucket_minute = tick.timestamp.minute - (tick.timestamp.minute % minutes)
            bucket = tick.timestamp.replace(minute=bucket_minute, second=0, microsecond=0)
            grouped[(tick.symbol, bucket)] = tick
        by_symbol: dict[str, list[BarSnapshot]] = defaultdict(list)
        for (symbol, timestamp), tick in sorted(grouped.items(), key=lambda item: item[0][1]):
            by_symbol[symbol].append(
                BarSnapshot(timestamp=timestamp, symbol=symbol, mid=float(tick.mid), spread=float(tick.spread))
            )
        return dict(by_symbol)

    def bars_from_strategy_history(self, history: list[Bar]) -> dict[str, list[BarSnapshot]]:
        by_symbol: dict[str, list[BarSnapshot]] = defaultdict(list)
        for bar in history:
            by_symbol[bar.symbol].append(
                BarSnapshot(timestamp=bar.timestamp, symbol=bar.symbol, mid=float(bar.close), spread=float(bar.ask - bar.bid))
            )
        return {symbol: sorted(items, key=lambda item: item.timestamp) for symbol, items in by_symbol.items()}

    def training_matrices(self, history: list[Tick]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        bars = self.bars_from_ticks(history)
        return self.training_matrices_from_bars(bars)

    def training_matrices_from_bars(self, bars: dict[str, list[BarSnapshot]]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        aligned = self._align_bars(bars)
        if not aligned:
            return {symbol: (np.empty((0, self.feature_count)), np.empty((0,))) for symbol in self.settings.tradable_symbols}
        timestamps = sorted(aligned)
        if len(timestamps) <= self.max_lookback + 1:
            return {symbol: (np.empty((0, self.feature_count)), np.empty((0,))) for symbol in self.settings.tradable_symbols}

        prices = {
            symbol: np.array([aligned[timestamp][symbol].mid for timestamp in timestamps], dtype=float)
            for symbol in self.settings.tradable_symbols
        }
        spreads = {
            symbol: np.array([aligned[timestamp][symbol].spread for timestamp in timestamps], dtype=float)
            for symbol in self.settings.tradable_symbols
        }
        one_bar_returns = {
            symbol: self._lagged_return_array(values, 1)
            for symbol, values in prices.items()
        }
        dollar_proxy = self._dollar_proxy_array(prices)
        session_features = {
            name: np.array([1.0 if self._hour_in_session(timestamp.hour, session.start_hour_utc, session.end_hour_utc) else 0.0 for timestamp in timestamps])
            for name, session in self.settings.features.time_of_day.items()
        }
        spread_window = self.settings.features.bid_ask["spread_rolling_mean_window"]
        target_center = float(self.settings.target_rank_center)
        n_symbols = len(self.settings.tradable_symbols)
        rows: dict[str, list[list[float]]] = defaultdict(list)
        targets: dict[str, list[float]] = defaultdict(list)

        for index in range(self.max_lookback, len(timestamps) - 1):
            next_returns = {
                symbol: (prices[symbol][index + 1] / prices[symbol][index]) - 1.0 if prices[symbol][index] != 0.0 else 0.0
                for symbol in self.settings.tradable_symbols
            }
            ranked_symbols = sorted(next_returns, key=next_returns.get)
            ranks = {symbol: rank + 1 for rank, symbol in enumerate(ranked_symbols)}
            for symbol in self.settings.tradable_symbols:
                row: list[float] = []
                symbol_prices = prices[symbol]
                symbol_spreads = spreads[symbol]
                for item in self.settings.features.lagged_returns:
                    row.append(self._lagged_return_at(symbol_prices, index, item.lag))
                for item in self.settings.features.volatility:
                    window = one_bar_returns[symbol][max(0, index - item.window + 1) : index + 1]
                    row.append(float(np.std(window)) if len(window) else 0.0)
                for pair_symbol in self.settings.correlated_symbols[symbol][:2]:
                    row.append(self._lagged_return_at(prices[pair_symbol], index, 1))
                row.append(self._gold_silver_ratio_return_from_arrays(prices, index, symbol))
                for feature in session_features.values():
                    row.append(float(feature[index]))
                mid = symbol_prices[index]
                row.append((symbol_spreads[index] / mid) * float(self.settings.features.bid_ask["basis_points_multiplier"]) if mid else 0.0)
                row.append(float(np.mean(symbol_spreads[max(0, index - spread_window + 1) : index + 1])))
                row.append(float(dollar_proxy[index]))
                rows[symbol].append(row)
                targets[symbol].append((ranks[symbol] / n_symbols) - target_center)
        return {
            symbol: (np.array(rows[symbol], dtype=float), np.array(targets[symbol], dtype=float))
            for symbol in self.settings.tradable_symbols
        }

    def current_feature_rows(self, bars: dict[str, list[BarSnapshot]]) -> dict[str, np.ndarray]:
        aligned = self._align_bars(bars)
        if len(aligned) <= self.max_lookback:
            return {}
        timestamps = sorted(aligned)
        index = len(timestamps) - 1
        return {
            symbol: np.array([self._feature_row(aligned, timestamps, index, symbol)], dtype=float)
            for symbol in self.settings.tradable_symbols
        }

    @property
    def feature_count(self) -> int:
        return (
            len(self.settings.features.lagged_returns)
            + len(self.settings.features.volatility)
            + len(self.settings.features.cross_symbol)
            + len(self.settings.features.time_of_day)
            + len(self.settings.features.bid_ask)
            + len(self.settings.features.macro)
        )

    def _align_bars(self, bars: dict[str, list[BarSnapshot]]) -> dict[datetime, dict[str, BarSnapshot]]:
        by_time: dict[datetime, dict[str, BarSnapshot]] = defaultdict(dict)
        for symbol in self.settings.tradable_symbols:
            for bar in bars.get(symbol, []):
                by_time[bar.timestamp][symbol] = bar
        return {
            timestamp: values
            for timestamp, values in by_time.items()
            if all(symbol in values for symbol in self.settings.tradable_symbols)
        }

    def _next_returns(self, aligned: dict[datetime, dict[str, BarSnapshot]], timestamps: list[datetime], index: int) -> dict[str, float]:
        now = aligned[timestamps[index]]
        nxt = aligned[timestamps[index + 1]]
        return {
            symbol: (nxt[symbol].mid / now[symbol].mid) - 1.0
            for symbol in self.settings.tradable_symbols
            if now[symbol].mid != 0.0
        }

    def _feature_row(
        self,
        aligned: dict[datetime, dict[str, BarSnapshot]],
        timestamps: list[datetime],
        index: int,
        symbol: str,
    ) -> list[float]:
        row: list[float] = []
        prices = [aligned[timestamp][symbol].mid for timestamp in timestamps]
        spreads = [aligned[timestamp][symbol].spread for timestamp in timestamps]
        for item in self.settings.features.lagged_returns:
            row.append(self._lagged_return(prices, index, item.lag))
        returns = [self._lagged_return(prices, idx, 1) for idx in range(len(prices))]
        for item in self.settings.features.volatility:
            window = returns[max(0, index - item.window + 1) : index + 1]
            row.append(float(np.std(window)) if window else 0.0)
        correlated = self.settings.correlated_symbols[symbol]
        for pair_index in range(2):
            pair_symbol = correlated[pair_index]
            pair_prices = [aligned[timestamp][pair_symbol].mid for timestamp in timestamps]
            row.append(self._lagged_return(pair_prices, index, 1))
        row.append(self._gold_silver_ratio_return(aligned, timestamps, index, symbol))
        timestamp = timestamps[index]
        for session in self.settings.features.time_of_day.values():
            row.append(1.0 if self._hour_in_session(timestamp.hour, session.start_hour_utc, session.end_hour_utc) else 0.0)
        mid = prices[index]
        row.append((spreads[index] / mid) * float(self.settings.features.bid_ask["basis_points_multiplier"]) if mid else 0.0)
        spread_window = self.settings.features.bid_ask["spread_rolling_mean_window"]
        row.append(float(np.mean(spreads[max(0, index - spread_window + 1) : index + 1])))
        row.append(self._dollar_proxy(aligned, timestamps, index))
        return row

    @staticmethod
    def _lagged_return(prices: list[float], index: int, lag: int) -> float:
        if index - lag < 0 or prices[index - lag] == 0.0:
            return 0.0
        return (prices[index] / prices[index - lag]) - 1.0

    @staticmethod
    def _lagged_return_at(prices: np.ndarray, index: int, lag: int) -> float:
        if index - lag < 0 or prices[index - lag] == 0.0:
            return 0.0
        return float((prices[index] / prices[index - lag]) - 1.0)

    @staticmethod
    def _lagged_return_array(prices: np.ndarray, lag: int) -> np.ndarray:
        output = np.zeros(len(prices), dtype=float)
        if len(prices) <= lag:
            return output
        previous = prices[:-lag]
        current = prices[lag:]
        valid = previous != 0.0
        output[lag:][valid] = (current[valid] / previous[valid]) - 1.0
        return output

    def _gold_silver_ratio_return_from_arrays(self, prices: dict[str, np.ndarray], index: int, symbol: str) -> float:
        lag = self.settings.features.gold_silver_ratio_lag
        if symbol not in {"XAUUSD", "XAGUSD"} or index - lag < 0:
            return 0.0
        old_ratio = prices["XAUUSD"][index - lag] / prices["XAGUSD"][index - lag]
        current_ratio = prices["XAUUSD"][index] / prices["XAGUSD"][index]
        return float((current_ratio / old_ratio) - 1.0) if old_ratio else 0.0

    def _gold_silver_ratio_return(
        self,
        aligned: dict[datetime, dict[str, BarSnapshot]],
        timestamps: list[datetime],
        index: int,
        symbol: str,
    ) -> float:
        lag = self.settings.features.gold_silver_ratio_lag
        if symbol not in {"XAUUSD", "XAGUSD"} or index - lag < 0:
            return 0.0
        now = aligned[timestamps[index]]
        old = aligned[timestamps[index - lag]]
        current_ratio = now["XAUUSD"].mid / now["XAGUSD"].mid
        old_ratio = old["XAUUSD"].mid / old["XAGUSD"].mid
        return (current_ratio / old_ratio) - 1.0 if old_ratio else 0.0

    @staticmethod
    def _hour_in_session(hour: int, start: int, end: int) -> bool:
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _dollar_proxy(self, aligned: dict[datetime, dict[str, BarSnapshot]], timestamps: list[datetime], index: int) -> float:
        lag = self.settings.features.macro["dollar_index_proxy_return_lag"]
        usd_symbols = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
        values = []
        for symbol in usd_symbols:
            prices = [aligned[timestamp][symbol].mid for timestamp in timestamps]
            value = self._lagged_return(prices, index, lag)
            values.append(-value if symbol.endswith("USD") else value)
        return float(np.mean(values)) if values else 0.0

    def _dollar_proxy_array(self, prices: dict[str, np.ndarray]) -> np.ndarray:
        lag = self.settings.features.macro["dollar_index_proxy_return_lag"]
        values = []
        for symbol in ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]:
            value = self._lagged_return_array(prices[symbol], lag)
            values.append(-value if symbol.endswith("USD") else value)
        return np.mean(np.vstack(values), axis=0) if values else np.zeros(0, dtype=float)


class StrategyV0Predictor:
    """Owns per-symbol ensembles and feature generation."""

    def __init__(self, settings: StrategyV0Config) -> None:
        self.settings = settings
        self.feature_builder = FeatureBuilder(settings)
        self.ensembles = {
            symbol: PerSymbolEnsemble(
                settings.predictor.ridge_alpha,
                settings.predictor.n_bootstraps,
                settings.predictor.bootstrap_seeds,
            )
            for symbol in settings.tradable_symbols
        }
        self.destroyers: set[str] = set()

    def fit(self, history: list[Tick]) -> None:
        matrices = self.feature_builder.training_matrices(history)
        self._fit_matrices(matrices)

    def fit_from_bars(self, bars: dict[str, list[BarSnapshot]]) -> None:
        matrices = self.feature_builder.training_matrices_from_bars(bars)
        self._fit_matrices(matrices)

    @property
    def has_active_models(self) -> bool:
        return any(symbol not in self.destroyers and ensemble.fitted for symbol, ensemble in self.ensembles.items())

    def predict_from_bars(self, bars: dict[str, list[BarSnapshot]]) -> dict[str, tuple[float, float]]:
        rows = self.feature_builder.current_feature_rows(bars)
        predictions: dict[str, tuple[float, float]] = {}
        for symbol in self.settings.tradable_symbols:
            if symbol in self.destroyers or symbol not in rows:
                predictions[symbol] = (0.0, 1.0)
                continue
            mean_pred, uncertainty = self.ensembles[symbol].predict_with_uncertainty(rows[symbol])
            predictions[symbol] = (float(mean_pred[0]), float(uncertainty[0]))
        return predictions

    def _fit_matrices(self, matrices: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
        self.destroyers = set()
        for symbol, (x, y) in matrices.items():
            if len(x) < self.settings.min_training_samples:
                self.destroyers.add(symbol)
                continue
            self.ensembles[symbol].fit(x, y)
            preds = self.ensembles[symbol].predict(x)
            validation_sharpe = self._validation_sharpe(preds, y)
            if validation_sharpe < float(self.settings.destroyer_validation_sharpe_threshold):
                self.destroyers.add(symbol)

    @staticmethod
    def _validation_sharpe(preds: np.ndarray, y: np.ndarray) -> float:
        pnl_proxy = preds * y
        std = float(np.std(pnl_proxy))
        if std == 0.0:
            return 0.0
        return float(np.mean(pnl_proxy) / std)
