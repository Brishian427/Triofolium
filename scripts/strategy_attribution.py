"""Generate symbol/day/session attribution for a StrategyV0 sandbox config."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.bar_engine import bar_backtest_from_bars, load_symbol_bars
from trifolium.backtest.config import load_backtest_config
from trifolium.backtest.types import Bar, Trade
from trifolium.strategy.v0.config import load_strategy_v0_config
from trifolium.strategy.v0.strategy import StrategyV0
from trifolium.validation import strategy_v0_warmup_duration


def parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def session_name(timestamp: datetime) -> str:
    hour = timestamp.hour
    if 7 <= hour < 12:
        return "london_morning"
    if 12 <= hour < 16:
        return "london_ny_overlap"
    if 16 <= hour < 21:
        return "ny_afternoon"
    return "off_session"


@dataclass
class PositionState:
    lots: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")


def _update_position(position: PositionState, trade: Trade) -> None:
    signed_lots = trade.lots if trade.side == "buy" else -trade.lots
    old_lots = position.lots
    new_lots = old_lots + signed_lots
    if old_lots == 0 or (old_lots > 0 and signed_lots > 0) or (old_lots < 0 and signed_lots < 0):
        total_abs = abs(old_lots) + abs(signed_lots)
        position.avg_price = ((position.avg_price * abs(old_lots)) + (trade.price * abs(signed_lots))) / total_abs
        position.lots = new_lots
        return
    if new_lots == 0:
        position.lots = Decimal("0")
        position.avg_price = Decimal("0")
        return
    if (old_lots > 0 and new_lots > 0) or (old_lots < 0 and new_lots < 0):
        position.lots = new_lots
        return
    position.lots = new_lots
    position.avg_price = trade.price


def _bar_lookup(bars_by_symbol: dict[str, list[Bar]]) -> dict[tuple[str, datetime], Bar]:
    return {(bar.symbol, bar.timestamp): bar for bars in bars_by_symbol.values() for bar in bars}


def _concentration_snapshots(
    trades: list[Trade],
    bars: dict[tuple[str, datetime], Bar],
    contract_sizes: dict[str, Decimal],
) -> list[dict[str, Any]]:
    positions: dict[str, PositionState] = defaultdict(PositionState)
    snapshots: list[dict[str, Any]] = []
    for trade in sorted(trades, key=lambda item: item.timestamp):
        _update_position(positions[trade.symbol], trade)
        notionals: dict[str, Decimal] = {}
        for symbol, position in positions.items():
            if position.lots == 0:
                continue
            bar = bars.get((symbol, trade.timestamp))
            mark = bar.close if bar is not None else position.avg_price
            notionals[symbol] = abs(position.lots) * contract_sizes[symbol] * mark
        total = sum(notionals.values(), Decimal("0"))
        if total <= 0:
            continue
        dominant_symbol, dominant_notional = max(notionals.items(), key=lambda item: item[1])
        snapshots.append(
            {
                "timestamp": trade.timestamp.isoformat(),
                "dominant_symbol": dominant_symbol,
                "dominant_pct": str(dominant_notional / total * Decimal("100")),
                "open_symbols": len(notionals),
                "total_notional": str(total),
            }
        )
    return snapshots


def _bucket_stats(trades: list[Trade], bars: dict[tuple[str, datetime], Bar], contract_sizes: dict[str, Decimal]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"trade_count": 0, "realized_pnl": Decimal("0"), "wins": 0, "losses": 0, "spread_cost_proxy": Decimal("0")}
    )
    for trade in trades:
        keys = [
            f"symbol::{trade.symbol}",
            f"day::{trade.timestamp.date().isoformat()}",
            f"session::{session_name(trade.timestamp)}",
            f"symbol_day::{trade.symbol}::{trade.timestamp.date().isoformat()}",
        ]
        bar = bars.get((trade.symbol, trade.timestamp))
        spread_cost = Decimal("0")
        if bar is not None:
            spread_cost = (bar.ask - bar.bid) * trade.lots * contract_sizes[trade.symbol]
        for key in keys:
            bucket = buckets[key]
            bucket["trade_count"] += 1
            bucket["realized_pnl"] += trade.realized_pnl
            bucket["spread_cost_proxy"] += spread_cost
            if trade.realized_pnl > 0:
                bucket["wins"] += 1
            elif trade.realized_pnl < 0:
                bucket["losses"] += 1
    output: dict[str, Any] = {}
    for key, bucket in buckets.items():
        closed = bucket["wins"] + bucket["losses"]
        output[key] = {
            "trade_count": bucket["trade_count"],
            "realized_pnl": str(bucket["realized_pnl"]),
            "win_rate": None if closed == 0 else bucket["wins"] / closed,
            "spread_cost_proxy": str(bucket["spread_cost_proxy"]),
        }
    return output


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    symbol_rows = [(key.split("::", 1)[1], value) for key, value in summary["buckets"].items() if key.startswith("symbol::")]
    symbol_rows.sort(key=lambda item: Decimal(item[1]["realized_pnl"]))
    concentration = summary["concentration"]
    lines = [
        "# Strategy Attribution Report",
        "",
        f"- Config: `{summary['strategy_config_path']}`",
        f"- Window: `{summary['start']}` to `{summary['end']}`",
        f"- Trade count: `{summary['trade_count']}`",
        f"- Max concentration snapshot: `{summary['max_concentration']}`",
        "",
        "## Symbol Attribution",
        "",
        "| Symbol | Trades | Realized PnL | Win Rate | Spread Cost Proxy |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for symbol, row in symbol_rows:
        lines.append(f"| {symbol} | {row['trade_count']} | {row['realized_pnl']} | {row['win_rate']} | {row['spread_cost_proxy']} |")
    lines.extend(["", "## Top Concentration Snapshots", ""])
    for row in concentration[:10]:
        lines.append(f"- `{row['timestamp']}` {row['dominant_symbol']} {row['dominant_pct']}% across {row['open_symbols']} symbols")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_attribution(config_path: Path, output_root: Path, start: datetime, end: datetime) -> dict[str, Any]:
    cfg = load_backtest_config()
    settings = load_strategy_v0_config(config_path)
    warmup = strategy_v0_warmup_duration(config_path)
    bars_by_symbol = {
        symbol: load_symbol_bars(cfg.data_dir, symbol, start - warmup - timedelta(hours=6), end + timedelta(hours=6))[0]
        for symbol in settings.tradable_symbols
    }
    strategy = StrategyV0(config_path=config_path)
    result = bar_backtest_from_bars(
        strategy,
        settings.tradable_symbols,
        start,
        end,
        cfg.initial_equity,
        bars_by_symbol=bars_by_symbol,
        warmup_start=start - warmup,
        warmup_recalibrate_at_start=True,
    )
    lookup = _bar_lookup(bars_by_symbol)
    concentration = _concentration_snapshots(result.trades, lookup, settings.instrument_contract_size)
    concentration.sort(key=lambda item: Decimal(item["dominant_pct"]), reverse=True)
    summary = {
        "strategy_config_path": str(config_path),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "trade_count": result.trade_count,
        "total_return": str(result.total_return),
        "risk_discipline": str(result.projected_risk_discipline),
        "buckets": _bucket_stats(result.trades, lookup, settings.instrument_contract_size),
        "max_concentration": None if not concentration else concentration[0],
        "concentration": concentration,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "attribution.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_markdown(output_root / "attribution.md", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-config-path", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    cfg = load_backtest_config()
    summary = run_attribution(args.strategy_config_path, args.output_root, parse_dt(args.start) or cfg.default_start, parse_dt(args.end) or cfg.default_end)
    print(args.output_root / "attribution.md")
    print(json.dumps({key: summary[key] for key in ["trade_count", "total_return", "risk_discipline", "max_concentration"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
