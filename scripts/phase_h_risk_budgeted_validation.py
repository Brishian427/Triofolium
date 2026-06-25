"""Create and validate the Phase H FX-only risk-budgeted StrategyV0 candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.phase_g_conviction_validation import classify_result, load_base_config, parse_dt, summarize_result
from trifolium.backtest.config import load_backtest_config
from trifolium.validation import validate_strategy


DEFAULT_CANDIDATE_ROOT = ROOT / "sandboxes" / "v_fx_only_risk_budgeted"
FX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "EURGBP"]


def build_fx_only_risk_budgeted_config(base: dict[str, Any], variant: str = "base") -> dict[str, Any]:
    config = json.loads(json.dumps(base))
    config["tradable_symbols"] = list(FX_SYMBOLS)
    config["hard_excluded_symbols"]["XAUUSD"] = "Phase H FX-only test: metals removed to isolate FX edge and concentration drag"
    config["hard_excluded_symbols"]["XAGUSD"] = "Phase H FX-only test: metals removed to isolate FX edge and concentration drag"
    config["destroyer_validation_sharpe_threshold"] = "-1.0"

    features = config["features"]
    features["lagged_returns"] = [{"lag": 1}, {"lag": 5}, {"lag": 20}]
    features["volatility"] = [{"window": 20}]

    trader = config["trader"]
    trader.pop("selected_signal_floor", None)
    trader.pop("disabled_symbols", None)
    trader.pop("invert_signals", None)
    trader.pop("max_lots_by_symbol", None)
    trader["top_n"] = 3
    trader["bottom_n"] = 3
    trader["cost_gate_spread_multiplier"] = "35"
    trader["cost_gate_min_abs_signal"] = "0.03"
    trader["allowed_sessions"] = ["london_morning", "london_ny_overlap"]
    trader["flatten_disallowed_sessions"] = True
    trader["sizing_table"] = [
        {"abs_signal_max": "0.03", "exposure_pct": "0.0"},
        {"abs_signal_max": "0.06", "exposure_pct": "0.15"},
        {"abs_signal_max": "0.10", "exposure_pct": "0.35"},
        {"abs_signal_max": "0.18", "exposure_pct": "0.75"},
        {"abs_signal_max": "1.01", "exposure_pct": "1.50"},
    ]

    portfolio = config["portfolio"]
    portfolio["max_single_symbol_concentration_pct"] = "35"
    portfolio["max_symbol_notional_pct"] = "8"
    portfolio["gross_leverage_threshold"] = "0.35"
    if variant == "h2_strict":
        trader["cost_gate_spread_multiplier"] = "50"
        trader["cost_gate_min_abs_signal"] = "0.05"
        trader["allowed_sessions"] = ["london_morning"]
        trader["sizing_table"] = [
            {"abs_signal_max": "0.05", "exposure_pct": "0.0"},
            {"abs_signal_max": "0.10", "exposure_pct": "0.10"},
            {"abs_signal_max": "0.15", "exposure_pct": "0.25"},
            {"abs_signal_max": "0.25", "exposure_pct": "0.50"},
            {"abs_signal_max": "1.01", "exposure_pct": "1.00"},
        ]
        portfolio["max_symbol_notional_pct"] = "5"
    elif variant != "base":
        raise ValueError(f"unknown Phase H variant: {variant}")
    return config


def write_candidate_config(candidate_root: Path, config: dict[str, Any]) -> Path:
    config_path = candidate_root / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--variant", choices=["base", "h2_strict"], default="base")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    cfg = load_backtest_config()
    start = parse_dt(args.start) or cfg.default_start
    end = parse_dt(args.end) or cfg.default_end
    if args.candidate_root == DEFAULT_CANDIDATE_ROOT and args.variant != "base":
        args.candidate_root = ROOT / "sandboxes" / f"v_fx_only_risk_budgeted_{args.variant}"
    candidate_config = build_fx_only_risk_budgeted_config(load_base_config(), args.variant)
    candidate_config_path = write_candidate_config(args.candidate_root, candidate_config)
    print(f"candidate_config={candidate_config_path}")
    if args.skip_validation:
        return 0

    result = validate_strategy(
        "strategy_v0",
        symbols=FX_SYMBOLS,
        start=start,
        end=end,
        report_root=args.candidate_root / "reports",
        strategy_config_path=candidate_config_path,
        parent_nickname="v0",
        changed_parameters={
            "candidate": "v_fx_only_risk_budgeted",
            "variant": args.variant,
            "universe": "FX-only",
            "destroyer_validation_sharpe_threshold": "-1.0",
            "feature_lookback": "lagged_returns=[1,5,20], volatility=[20]",
            "cost_gate_spread_multiplier": candidate_config["trader"]["cost_gate_spread_multiplier"],
            "cost_gate_min_abs_signal": candidate_config["trader"]["cost_gate_min_abs_signal"],
            "allowed_sessions": candidate_config["trader"]["allowed_sessions"],
            "flatten_disallowed_sessions": candidate_config["trader"]["flatten_disallowed_sessions"],
            "portfolio_max_single_symbol_concentration_pct": "35",
            "portfolio_max_symbol_notional_pct": candidate_config["portfolio"]["max_symbol_notional_pct"],
            "sizing_table": candidate_config["trader"]["sizing_table"],
        },
    )
    classification, reason = classify_result(result)
    summary = summarize_result(result, classification, reason, candidate_config_path, candidate_name=f"v_fx_only_risk_budgeted_{args.variant}")
    summary_path = args.candidate_root / "phase_h_result.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"classification={classification}")
    print(f"reason={reason}")
    print(f"summary={summary_path}")
    print(f"markdown_report={result.markdown_report}")
    print(f"json_report={result.json_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
