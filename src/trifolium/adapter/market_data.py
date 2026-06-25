"""Market data queries for ticks, candles, and instrument metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import MetaTrader5 as mt5
import yaml

from trifolium.adapter.mt5_client import MT5ConnectionError
from trifolium.adapter.types import Candle, Instrument, Tick


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def load_instruments(path: Path = Path("config/instruments.yaml")) -> list[Instrument]:
    """Load competition instruments from config."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Instrument.model_validate(item) for item in data["instruments"]]


def ensure_symbol(symbol: str) -> object:
    """Select a symbol in Market Watch and return its MT5 metadata."""

    if not mt5.symbol_select(symbol, True):
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbol_select({symbol}) failed: {code} {message}")
    info = mt5.symbol_info(symbol)
    if info is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbol_info({symbol}) failed: {code} {message}")
    return info


def get_tick(symbol: str, pip_size: Decimal) -> Tick:
    """Return the current tick for a symbol with spread in price units and pips."""

    ensure_symbol(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbol_info_tick({symbol}) failed: {code} {message}")
    bid = _decimal(tick.bid)
    ask = _decimal(tick.ask)
    spread = ask - bid
    return Tick(
        symbol=symbol,
        bid=bid,
        ask=ask,
        spread=spread,
        spread_pips=spread / pip_size,
        time=datetime.fromtimestamp(int(tick.time), tz=timezone.utc),
    )


def get_m1_candles(symbol: str, count: int = 10) -> list[Candle]:
    """Return the most recent M1 candles for a symbol."""

    ensure_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, count)
    if rates is None or len(rates) != count:
        code, message = mt5.last_error()
        raise MT5ConnectionError(
            f"mt5.copy_rates_from_pos({symbol}, M1, 0, {count}) failed: {code} {message}"
        )
    candles: list[Candle] = []
    for row in rates:
        candles.append(
            Candle(
                time=datetime.fromtimestamp(int(row["time"]), tz=timezone.utc),
                open=_decimal(row["open"]),
                high=_decimal(row["high"]),
                low=_decimal(row["low"]),
                close=_decimal(row["close"]),
                tick_volume=int(row["tick_volume"]),
                spread=int(row["spread"]),
                real_volume=int(row["real_volume"]),
            )
        )
    return candles


def available_symbols_count() -> int:
    """Return the number of symbols visible to MT5."""

    symbols = mt5.symbols_get()
    if symbols is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbols_get failed: {code} {message}")
    return len(symbols)


def verify_competition_symbols(instruments: list[Instrument]) -> list[dict[str, object]]:
    """Verify configured competition symbols are accessible and contract sizes match."""

    rows: list[dict[str, object]] = []
    missing: list[str] = []
    mismatched: list[str] = []
    for instrument in instruments:
        info = mt5.symbol_info(instrument.symbol)
        if info is None:
            if not mt5.symbol_select(instrument.symbol, True):
                missing.append(instrument.symbol)
                continue
            info = mt5.symbol_info(instrument.symbol)
        if info is None:
            missing.append(instrument.symbol)
            continue
        actual_contract = _decimal(info.trade_contract_size)
        if (
            instrument.expected_contract_size is not None
            and actual_contract != instrument.expected_contract_size
        ):
            mismatched.append(
                f"{instrument.symbol}: expected {instrument.expected_contract_size}, got {actual_contract}"
            )
        rows.append(
            {
                "symbol": instrument.symbol,
                "contract_size": actual_contract,
                "volume_min": _decimal(info.volume_min),
                "volume_step": _decimal(info.volume_step),
                "visible": bool(info.visible),
            }
        )
    if missing:
        raise MT5ConnectionError(f"Missing competition symbols: {', '.join(missing)}")
    if mismatched:
        raise MT5ConnectionError("Contract size mismatch: " + "; ".join(mismatched))
    return rows
