"""Layer 2 trader for StrategyV0: predictions to target signed lots."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import numpy as np

from trifolium.strategy.v0.config import StrategyV0Config


FX_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "EURGBP"}


def compute_signal(point_estimate: float, uncertainty: float, settings: StrategyV0Config) -> float:
    """Convert ensemble point/uncertainty into a compressed signal in [-1, 1]."""

    sigma = max(uncertainty, float(settings.trader.sigma_floor))
    raw_signal = point_estimate / sigma
    return float(2.0 / (1.0 + np.exp(-raw_signal / float(settings.trader.sigmoid_scale))) - 1.0)


def signal_to_exposure(compressed_signal: float, settings: StrategyV0Config) -> Decimal:
    """Map a compressed signal to signed exposure fraction."""

    abs_signal = Decimal(str(abs(compressed_signal)))
    sign = Decimal("1") if compressed_signal > 0 else Decimal("-1") if compressed_signal < 0 else Decimal("0")
    for row in settings.trader.sizing_table:
        if abs_signal < row.abs_signal_max:
            return sign * row.exposure_pct / Decimal("100")
    return sign * settings.trader.sizing_table[-1].exposure_pct / Decimal("100")


def cross_sectional_filter(signals_per_symbol: dict[str, float], settings: StrategyV0Config) -> dict[str, int]:
    """Keep top-N positive longs and bottom-N negative shorts, flatten the middle."""

    sorted_by_signal = sorted(signals_per_symbol.items(), key=lambda item: item[1], reverse=True)
    top_symbols = {symbol for symbol, _signal in sorted_by_signal[: settings.trader.top_n]}
    bottom_symbols = {symbol for symbol, _signal in sorted_by_signal[-settings.trader.bottom_n :]}
    result: dict[str, int] = {}
    for symbol, signal in signals_per_symbol.items():
        if symbol in top_symbols and signal > 0:
            result[symbol] = 1
        elif symbol in bottom_symbols and signal < 0:
            result[symbol] = -1
        else:
            result[symbol] = 0
    return result


def exposure_to_lot(symbol: str, exposure_pct: Decimal, equity: Decimal, current_price: Decimal, settings: StrategyV0Config) -> Decimal:
    """Convert signed exposure fraction into signed broker lots."""

    if current_price <= 0 or exposure_pct == 0:
        return Decimal("0")
    target_notional = abs(exposure_pct) * equity
    contract_size = settings.instrument_contract_size[symbol]
    divisor = current_price * contract_size if symbol in FX_SYMBOLS else current_price * contract_size
    lots = target_notional / divisor
    quant = Decimal("1").scaleb(-settings.lot_rounding_decimals)
    rounded = lots.quantize(quant, rounding=ROUND_HALF_UP)
    if rounded < settings.broker_lot_step:
        return Decimal("0")
    return -rounded if exposure_pct < 0 else rounded


class StrategyV0Trader:
    """Transforms model predictions into target signed lot sizes."""

    def __init__(self, settings: StrategyV0Config) -> None:
        self.settings = settings

    def target_lots(
        self,
        predictions: dict[str, tuple[float, float]],
        equity: Decimal,
        prices: dict[str, Decimal],
    ) -> tuple[dict[str, Decimal], dict[str, float]]:
        signals = {
            symbol: compute_signal(point, uncertainty, self.settings)
            for symbol, (point, uncertainty) in predictions.items()
        }
        directions = cross_sectional_filter(signals, self.settings)
        targets: dict[str, Decimal] = {}
        for symbol, signal in signals.items():
            if directions.get(symbol, 0) == 0:
                targets[symbol] = Decimal("0")
                continue
            exposure = signal_to_exposure(signal, self.settings)
            if directions[symbol] < 0 and exposure > 0:
                exposure = -exposure
            elif directions[symbol] > 0 and exposure < 0:
                exposure = -exposure
            targets[symbol] = exposure_to_lot(symbol, exposure, equity, prices[symbol], self.settings)
        return targets, signals
