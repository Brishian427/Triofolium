"""Configuration helpers for offline backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    asset_class: str
    contract_size: Decimal
    pip_size: Decimal
    min_lot: Decimal


@dataclass(frozen=True)
class BacktestConfig:
    data_dir: Path
    default_start: datetime
    default_end: datetime
    initial_equity: Decimal
    leverage: Decimal
    slippage_market_price_units: Decimal
    worst_window_maxdd_pct: Decimal
    coefficient_variation_threshold: Decimal
    negative_return_fraction_threshold: Decimal


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_backtest_config(path: Path | None = None) -> BacktestConfig:
    config_path = path or ROOT / "config" / "backtest.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return BacktestConfig(
        data_dir=(ROOT / data["data_dir"]).resolve(),
        default_start=parse_datetime(data["default_start"]),
        default_end=parse_datetime(data["default_end"]),
        initial_equity=Decimal(str(data["initial_equity"])),
        leverage=Decimal(str(data["leverage"])),
        slippage_market_price_units=Decimal(str(data["slippage"]["market_price_units"])),
        worst_window_maxdd_pct=Decimal(str(data["filters"]["worst_window_maxdd_pct"])),
        coefficient_variation_threshold=Decimal(str(data["filters"]["coefficient_variation_threshold"])),
        negative_return_fraction_threshold=Decimal(str(data["filters"]["negative_return_fraction_threshold"])),
    )


def load_instrument_specs(path: Path | None = None) -> dict[str, InstrumentSpec]:
    config_path = path or ROOT / "config" / "instruments.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    specs: dict[str, InstrumentSpec] = {}
    for item in data["instruments"]:
        expected = item.get("expected_contract_size")
        if expected is None:
            expected = 1 if item["asset_class"] == "crypto" else 100000
        specs[item["symbol"]] = InstrumentSpec(
            symbol=item["symbol"],
            asset_class=item["asset_class"],
            contract_size=Decimal(str(expected)),
            pip_size=Decimal(str(item["pip_size"])),
            min_lot=Decimal(str(item["min_lot"])),
        )
    return specs
