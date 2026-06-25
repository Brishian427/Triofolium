"""Create and validate the Phase G conviction-based StrategyV0 candidate."""

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
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.config import load_backtest_config
from trifolium.validation import validate_strategy


BASE_CONFIG_PATH = ROOT / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml"
DEFAULT_CANDIDATE_ROOT = ROOT / "sandboxes" / "v_conviction_redesign"


def parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_base_config(path: Path = BASE_CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_conviction_config(base: dict[str, Any]) -> dict[str, Any]:
    """Return Phase G config derived from v0, without forced participation."""

    config = json.loads(json.dumps(base))
    config["destroyer_validation_sharpe_threshold"] = "-1.0"

    features = config["features"]
    features["lagged_returns"] = [{"lag": 1}, {"lag": 5}, {"lag": 20}]
    features["volatility"] = [{"window": 20}]

    trader = config["trader"]
    trader.pop("selected_signal_floor", None)
    trader.pop("disabled_symbols", None)
    trader.pop("invert_signals", None)
    trader["top_n"] = 3
    trader["bottom_n"] = 3
    trader["max_lots_by_symbol"] = {"XAGUSD": "0.01"}
    trader["sizing_table"] = [
        {"abs_signal_max": "0.02", "exposure_pct": "0.0"},
        {"abs_signal_max": "0.04", "exposure_pct": "0.1"},
        {"abs_signal_max": "0.06", "exposure_pct": "0.3"},
        {"abs_signal_max": "0.08", "exposure_pct": "1.0"},
        {"abs_signal_max": "1.01", "exposure_pct": "3.0"},
    ]
    return config


def write_candidate_config(candidate_root: Path, config: dict[str, Any]) -> Path:
    config_path = candidate_root / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def classify_result(result: Any) -> tuple[str, str]:
    full = result.full_backtest
    d2 = result.d2
    trade_count = int(full["trade_count"])
    total_return = float(full["total_return"])
    risk_discipline = float(full["risk_discipline"])
    robustness = d2["robustness"]["verdict"]
    gate_passed = bool(d2["gate_check"]["passed"])

    if trade_count < 30:
        return "c", "trade_count < 30: strategy remains too conservative architecturally"
    if not gate_passed or risk_discipline != 100.0:
        return "d", "hard gate failed: Risk Discipline or another D2 gate violated"
    if robustness != "ROBUST":
        return "d", "robustness failed: IMC principle violation"
    if total_return > 0:
        return "a", "positive long-window return with hard gates and robustness passing"
    return "b", "robust but non-positive long-window return: consistent but no edge"


def summarize_result(result: Any, classification: str, reason: str, candidate_config_path: Path) -> dict[str, Any]:
    d2 = result.d2
    return {
        "candidate": "v_conviction_redesign",
        "classification": classification,
        "reason": reason,
        "candidate_config_path": str(candidate_config_path),
        "markdown_report": result.markdown_report,
        "json_report": result.json_report,
        "full_backtest": result.full_backtest,
        "gate_check": d2["gate_check"],
        "primary_objective": d2["primary_objective"],
        "secondary_metrics": d2["secondary_metrics"],
        "binding_check": d2["binding_check"],
        "robustness": d2["robustness"],
        "decision": d2["decision"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    cfg = load_backtest_config()
    start = parse_dt(args.start) or cfg.default_start
    end = parse_dt(args.end) or cfg.default_end

    candidate_config = build_conviction_config(load_base_config())
    candidate_config_path = write_candidate_config(args.candidate_root, candidate_config)
    print(f"candidate_config={candidate_config_path}")

    if args.skip_validation:
        return 0

    result = validate_strategy(
        "strategy_v0",
        symbols="all_tradable",
        start=start,
        end=end,
        report_root=args.candidate_root / "reports",
        strategy_config_path=candidate_config_path,
        parent_nickname="v0",
        changed_parameters={
            "candidate": "v_conviction_redesign",
            "destroyer_validation_sharpe_threshold": "-1.0",
            "feature_lookback": "lagged_returns=[1,5,20], volatility=[20]",
            "removed": ["selected_signal_floor", "top_n=4", "bottom_n=4"],
            "top_n": 3,
            "bottom_n": 3,
            "sizing_table": candidate_config["trader"]["sizing_table"],
            "max_lots_by_symbol": {"XAGUSD": "0.01"},
        },
    )
    classification, reason = classify_result(result)
    summary = summarize_result(result, classification, reason, candidate_config_path)
    summary_path = args.candidate_root / "phase_g_result.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"classification={classification}")
    print(f"reason={reason}")
    print(f"summary={summary_path}")
    print(f"markdown_report={result.markdown_report}")
    print(f"json_report={result.json_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
