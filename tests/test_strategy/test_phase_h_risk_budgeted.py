from scripts.phase_h_risk_budgeted_validation import FX_SYMBOLS, build_fx_only_risk_budgeted_config
from trifolium.strategy.v0.config import load_strategy_v0_config


def test_phase_h_config_is_fx_only_cost_gated_and_risk_budgeted():
    base = load_strategy_v0_config().model_dump(mode="json")

    candidate = build_fx_only_risk_budgeted_config(base)
    trader = candidate["trader"]
    portfolio = candidate["portfolio"]

    assert candidate["tradable_symbols"] == FX_SYMBOLS
    assert "XAUUSD" in candidate["hard_excluded_symbols"]
    assert "XAGUSD" in candidate["hard_excluded_symbols"]
    assert "selected_signal_floor" not in trader
    assert trader["cost_gate_spread_multiplier"] == "35"
    assert trader["cost_gate_min_abs_signal"] == "0.03"
    assert trader["allowed_sessions"] == ["london_morning", "london_ny_overlap"]
    assert trader["flatten_disallowed_sessions"] is True
    assert portfolio["max_single_symbol_concentration_pct"] == "35"
    assert portfolio["max_symbol_notional_pct"] == "8"


def test_phase_h_strict_variant_raises_cost_gate_and_narrows_session():
    base = load_strategy_v0_config().model_dump(mode="json")

    candidate = build_fx_only_risk_budgeted_config(base, "h2_strict")
    trader = candidate["trader"]

    assert trader["cost_gate_spread_multiplier"] == "50"
    assert trader["cost_gate_min_abs_signal"] == "0.05"
    assert trader["allowed_sessions"] == ["london_morning"]
