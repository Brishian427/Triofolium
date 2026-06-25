"""Task 03 L3 competition round-structure simulation."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.config import load_backtest_config
from trifolium.backtest.engine import backtest
from trifolium.backtest.metrics import final_score_projection, score_from_metric
from trifolium.strategy.base import Strategy


BASELINES = {
    "do_nothing": "trifolium.strategy.baselines.do_nothing:DoNothingStrategy",
    "buy_and_hold_audusd": "trifolium.strategy.baselines.buy_and_hold_audusd:BuyAndHoldAUDUSDStrategy",
    "ping_pong_audusd": "trifolium.strategy.baselines.ping_pong_audusd:PingPongAUDUSDStrategy",
    "simple_mean_reversion": "trifolium.strategy.baselines.simple_mean_reversion:SimpleMeanReversionStrategy",
}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def import_strategy(path: str) -> type[Strategy]:
    module_name, class_name = BASELINES.get(path, path).split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def audit_free_segments(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    segments: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        audit_start = cursor.replace(hour=21, minute=0, second=0, microsecond=0)
        audit_end = cursor.replace(hour=22, minute=0, second=0, microsecond=0)
        # BST 22:00-23:00 equals UTC 21:00-22:00 for the competition dates.
        if cursor < audit_start < end:
            segments.append((cursor, min(audit_start, end)))
            cursor = min(audit_end, end)
        else:
            next_day = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            segments.append((cursor, min(next_day, end)))
            cursor = min(next_day, end)
    return [(a, b) for a, b in segments if b > a]


def projected_score(result) -> Decimal:
    return final_score_projection(
        score_from_metric(result.total_return, higher_is_better=True),
        score_from_metric(result.max_drawdown, higher_is_better=False),
        Decimal("50") if result.sharpe is None else score_from_metric(result.sharpe, higher_is_better=True),
        result.projected_risk_discipline,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="do_nothing")
    parser.add_argument("--symbols", default="AUDUSD")
    parser.add_argument("--start")
    parser.add_argument("--recalibrate", action="store_true")
    args = parser.parse_args()
    cfg = load_backtest_config()
    start = parse_dt(args.start) if args.start else cfg.default_start
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    cls = import_strategy(args.strategy)
    report_dir = ROOT / "reports" / f"round_simulation_{args.strategy}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    report_dir.mkdir(parents=True, exist_ok=True)
    schedule = [
        ("round_1", start, start + timedelta(hours=24)),
        ("round_2", start + timedelta(hours=24), start + timedelta(hours=48)),
        ("round_3", start + timedelta(hours=48), start + timedelta(hours=72)),
        ("finals", start + timedelta(hours=72), start + timedelta(hours=120)),
    ]
    rows = []
    for name, seg_start, seg_end in schedule:
        segment_results = []
        strategy = cls(symbols=symbols)
        for part_start, part_end in audit_free_segments(seg_start, seg_end):
            if args.recalibrate and hasattr(strategy, "recalibrate"):
                strategy.recalibrate(None, [])
            segment_results.append(backtest(strategy, symbols, part_start, part_end, cfg.initial_equity, data_dir=cfg.data_dir))
        if not segment_results:
            continue
        final = segment_results[-1]
        rows.append(
            {
                "round": name,
                "start": seg_start.isoformat(),
                "end": seg_end.isoformat(),
                "segments": len(segment_results),
                "return": str(final.total_return),
                "maxdd": str(final.max_drawdown),
                "sharpe": None if final.sharpe is None else str(final.sharpe),
                "risk": str(final.projected_risk_discipline),
                "projected_final_score": str(projected_score(final)),
            }
        )
    report = ["# Round Simulation", "", "```json", json.dumps(rows, indent=2), "```", ""]
    (report_dir / "round_simulation_report.md").write_text("\n".join(report), encoding="utf-8")
    print(report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
