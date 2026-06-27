"""Strategy Element Table for explicit self-evolution dimensions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FeatureSet(str, Enum):
    LAGGED_RETURNS = "lagged_returns"
    VOLATILITY = "volatility"
    CROSS_SYMBOL = "cross_symbol"
    TIME_OF_DAY = "time_of_day"
    SPREAD = "spread"
    MACRO_PROXY = "macro_proxy"


class ModelFamily(str, Enum):
    RIDGE_BOOTSTRAP = "ridge_bootstrap_ensemble"
    LASSO_BOOTSTRAP = "lasso_bootstrap_ensemble"
    RANDOM_FOREST = "random_forest"
    HARDCODED_RULE = "hardcoded_rule"


class TargetFormulation(str, Enum):
    RANK_CROSS_SECTIONAL = "rank_cross_sectional"
    ABSOLUTE_RETURN = "absolute_return"
    BINARY_DIRECTION = "binary_direction"


class SignalCompression(str, Enum):
    SIGMOID = "sigmoid"
    THRESHOLD = "threshold"
    DISCRETIZED_5TIER = "discretized_5tier"


class UniverseFilter(str, Enum):
    ALL_TRADABLE = "all_tradable"
    TOP3_BUY_BOTTOM3_SELL = "top3_buy_bottom3_sell"
    TOP_N_BY_SIGNAL = "top_n_by_signal"


class PositionSizing(str, Enum):
    LINEAR_PROPORTIONAL = "linear_proportional"
    SIGMOID = "sigmoid"
    DISCRETIZED_LEVELS = "discretized_levels"


class PortfolioConstraint(str, Enum):
    CURRENCY_DECOMP = "currency_decomposition"
    METALS_COMBINED = "metals_combined_cap"
    GROSS_LEVERAGE = "gross_leverage"
    NONE = "none"


class TimeFilter(str, Enum):
    NO_FILTER = "no_filter"
    SESSION_SPECIFIC = "session_specific"
    MACRO_EVENT_GUARD = "macro_event_guard"


class DrawdownGate(str, Enum):
    NO_GATE = "no_gate"
    SOFT_SCALING = "soft_scaling"
    HARD_STOP = "hard_stop"


class SignalLayer(BaseModel):
    feature_set: list[FeatureSet]
    model_family: ModelFamily
    target_formulation: TargetFormulation
    model_hyperparams: dict[str, Any] = Field(default_factory=dict)


class DecisionLayer(BaseModel):
    signal_compression: SignalCompression
    universe_filter: UniverseFilter
    position_sizing: PositionSizing
    sizing_hyperparams: dict[str, Any] = Field(default_factory=dict)


class RiskLayer(BaseModel):
    portfolio_constraints: list[PortfolioConstraint]
    time_filter: TimeFilter
    drawdown_gate: DrawdownGate
    constraint_hyperparams: dict[str, Any] = Field(default_factory=dict)


class StrategyElementTable(BaseModel):
    """Decomposable representation of one strategy as a structured vector."""

    nickname: str
    parent_nickname: str | None = None
    signal_layer: SignalLayer
    decision_layer: DecisionLayer
    risk_layer: RiskLayer

    def diff(self, other: "StrategyElementTable") -> dict[str, dict[str, Any]]:
        diffs: dict[str, dict[str, Any]] = {}
        for layer_name in ["signal_layer", "decision_layer", "risk_layer"]:
            self_layer = getattr(self, layer_name).model_dump(mode="json")
            other_layer = getattr(other, layer_name).model_dump(mode="json")
            for dimension, self_value in self_layer.items():
                other_value = other_layer.get(dimension)
                if self_value != other_value:
                    diffs[f"{layer_name}.{dimension}"] = {"from": other_value, "to": self_value}
        return diffs


def decompose_v0() -> StrategyElementTable:
    """Return the Task 04 StrategyV0 design as an element table."""

    return StrategyElementTable(
        nickname="v0",
        signal_layer=SignalLayer(
            feature_set=[
                FeatureSet.LAGGED_RETURNS,
                FeatureSet.VOLATILITY,
                FeatureSet.CROSS_SYMBOL,
                FeatureSet.TIME_OF_DAY,
                FeatureSet.SPREAD,
                FeatureSet.MACRO_PROXY,
            ],
            model_family=ModelFamily.RIDGE_BOOTSTRAP,
            target_formulation=TargetFormulation.RANK_CROSS_SECTIONAL,
            model_hyperparams={"ridge_alpha": 1.0, "n_bootstraps": 3, "destroyer_validation_sharpe_threshold": 0.0},
        ),
        decision_layer=DecisionLayer(
            signal_compression=SignalCompression.SIGMOID,
            universe_filter=UniverseFilter.TOP3_BUY_BOTTOM3_SELL,
            position_sizing=PositionSizing.DISCRETIZED_LEVELS,
            sizing_hyperparams={"sigmoid_scale": 1.5, "thresholds_pct": [0.0, 1.0, 2.5, 5.0, 10.0]},
        ),
        risk_layer=RiskLayer(
            portfolio_constraints=[
                PortfolioConstraint.CURRENCY_DECOMP,
                PortfolioConstraint.METALS_COMBINED,
                PortfolioConstraint.GROSS_LEVERAGE,
            ],
            time_filter=TimeFilter.NO_FILTER,
            drawdown_gate=DrawdownGate.NO_GATE,
            constraint_hyperparams={"currency_cap_pct": 20.0, "metals_cap_pct": 15.0, "gross_leverage_cap_pct": 50.0},
        ),
    )

