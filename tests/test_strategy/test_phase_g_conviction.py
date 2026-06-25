from scripts.phase_g_conviction_validation import build_conviction_config
from trifolium.strategy.v0.config import load_strategy_v0_config


def test_phase_g_conviction_config_drops_forced_participation():
    base = load_strategy_v0_config().model_dump(mode="json")

    candidate = build_conviction_config(base)
    trader = candidate["trader"]

    assert candidate["destroyer_validation_sharpe_threshold"] == "-1.0"
    assert candidate["features"]["lagged_returns"] == [{"lag": 1}, {"lag": 5}, {"lag": 20}]
    assert candidate["features"]["volatility"] == [{"window": 20}]
    assert "selected_signal_floor" not in trader
    assert trader["top_n"] == 3
    assert trader["bottom_n"] == 3
    assert trader["max_lots_by_symbol"] == {"XAGUSD": "0.01"}
    assert [row["exposure_pct"] for row in trader["sizing_table"]] == ["0.0", "0.1", "0.3", "1.0", "3.0"]
