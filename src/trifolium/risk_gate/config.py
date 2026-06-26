"""Risk Gate configuration loader and module-init validation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = ROOT / "config" / "risk_limits.yaml"


class ModeLimits(BaseModel):
    """Per-mode Risk Gate limits."""

    model_config = ConfigDict(extra="forbid")

    max_lot_per_order: Decimal
    max_total_leverage: Decimal
    max_single_symbol_pct: Decimal
    numeric_tolerance_abs: Decimal
    numeric_tolerance_rel: Decimal
    max_orders_per_minute: int


class SymbolOverride(BaseModel):
    """Symbol-specific overrides for lot caps."""

    model_config = ConfigDict(extra="forbid")

    max_lot_per_order: Decimal


class SymbolSideRule(BaseModel):
    """Symbol-specific allowed order sides."""

    model_config = ConfigDict(extra="forbid")

    allowed_sides: list[Literal["buy", "sell"]]


class HardFloors(BaseModel):
    """Hard floors that apply in every mode."""

    model_config = ConfigDict(extra="forbid")

    min_margin_level_pct: Decimal
    max_drawdown_session_pct: Decimal


class RiskLimits(BaseModel):
    """Validated `config/risk_limits.yaml` model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["calibration", "production"]
    calibration: ModeLimits
    production: ModeLimits
    symbol_overrides: dict[str, SymbolOverride] = Field(default_factory=dict)
    symbol_side_rules: dict[str, SymbolSideRule] = Field(default_factory=dict)
    hard_floors: HardFloors

    @model_validator(mode="after")
    def validate_required_sections(self) -> "RiskLimits":
        if self.mode == "calibration" and self.calibration is None:
            raise ValueError("calibration limits are required")
        if self.mode == "production" and self.production is None:
            raise ValueError("production limits are required")
        return self

    @property
    def active(self) -> ModeLimits:
        """Return limits for the configured mode."""

        return self.calibration if self.mode == "calibration" else self.production


def load_risk_limits(path: str | Path | None = None) -> RiskLimits:
    """Load and validate Risk Gate limits, raising on missing or malformed keys."""

    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Risk Gate config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Risk Gate config must be a mapping: {config_path}")
    return RiskLimits.model_validate(data)


RISK_LIMITS = load_risk_limits()
