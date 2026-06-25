"""Configuration loading for StrategyV0 thresholds and symbol metadata."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_PATH = ROOT / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml"


class LaggedReturnConfig(BaseModel):
    lag: int


class VolatilityConfig(BaseModel):
    window: int


class TimeSessionConfig(BaseModel):
    start_hour_utc: int
    end_hour_utc: int


class FeatureConfig(BaseModel):
    lagged_returns: list[LaggedReturnConfig]
    volatility: list[VolatilityConfig]
    cross_symbol: list[dict[str, str]]
    gold_silver_ratio_lag: int
    time_of_day: dict[str, TimeSessionConfig]
    bid_ask: dict[str, Any]
    macro: dict[str, int]


class PredictorConfig(BaseModel):
    ridge_alpha: Decimal
    n_bootstraps: int
    bootstrap_seeds: list[int]


class SizingRow(BaseModel):
    abs_signal_max: Decimal
    exposure_pct: Decimal


class TraderConfig(BaseModel):
    sigma_floor: Decimal
    sigmoid_scale: Decimal
    invert_signals: bool = False
    selected_signal_floor: Decimal = Decimal("0")
    disabled_symbols: list[str] = Field(default_factory=list)
    max_lots_by_symbol: dict[str, Decimal] = Field(default_factory=dict)
    cost_gate_spread_multiplier: Decimal = Decimal("0")
    cost_gate_min_abs_signal: Decimal = Decimal("0")
    allowed_sessions: list[str] = Field(default_factory=list)
    flatten_disallowed_sessions: bool = False
    top_n: int
    bottom_n: int
    sizing_table: list[SizingRow]


class PortfolioConfig(BaseModel):
    currency_threshold_pct: Decimal
    metals_threshold_pct: Decimal
    gross_leverage_threshold: Decimal
    scaling_steps: int
    max_single_symbol_concentration_pct: Decimal = Decimal("100")
    max_symbol_notional_pct: Decimal = Decimal("100")


class RiskGateConfig(BaseModel):
    required_for_live: bool
    production_mode_required: bool
    reject_if_legacy_audusd_ticket_open: int
    emergency_flatten_margin_level_pct: Decimal


class StrategyV0Config(BaseModel):
    name: str
    tradable_symbols: list[str]
    hard_excluded_symbols: dict[str, str]
    bar_interval_minutes: int
    broker_lot_step: Decimal
    lot_rounding_decimals: int
    min_training_samples: int
    destroyer_validation_sharpe_threshold: Decimal
    target_rank_center: Decimal
    predictor: PredictorConfig
    features: FeatureConfig
    correlated_symbols: dict[str, list[str]]
    trader: TraderConfig
    instrument_contract_size: dict[str, Decimal]
    portfolio: PortfolioConfig
    risk_gate: RiskGateConfig


def load_strategy_v0_config(path: str | Path | None = None) -> StrategyV0Config:
    """Load StrategyV0 YAML config into typed settings."""

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return StrategyV0Config.model_validate(data)
