"""Run Task 03 L2 validation filters for a strategy."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import matplotlib
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

matplotlib.use("Agg")

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.config import load_backtest_config
from trifolium.backtest.bar_engine import bar_backtest
from trifolium.backtest.data_loader import symbol_files
from trifolium.backtest.engine import backtest
from trifolium.backtest.metrics import final_score_projection, score_from_metric
from trifolium.backtest.types import BacktestResult, DataQualityStats, EquityPoint, Trade
from trifolium.strategy.base import Strategy
from trifolium.strategy.v0.config import load_strategy_v0_config


BASELINES = {
    "do_nothing": "trifolium.strategy.baselines.do_nothing:DoNothingStrategy",
    "buy_and_hold_audusd": "trifolium.strategy.baselines.buy_and_hold_audusd:BuyAndHoldAUDUSDStrategy",
    "ping_pong_audusd": "trifolium.strategy.baselines.ping_pong_audusd:PingPongAUDUSDStrategy",
    "simple_mean_reversion": "trifolium.strategy.baselines.simple_mean_reversion:SimpleMeanReversionStrategy",
    "strategy_v0": "trifolium.strategy.v0.strategy:StrategyV0",
}


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def import_strategy(path: str) -> type[Strategy]:
    module_name, class_name = BASELINES.get(path, path).split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def instantiate_strategy(
    path: str,
    symbols: list[str],
    config: dict[str, Any] | None = None,
    lot_multiplier: float = 1.0,
    config_path: str | Path | None = None,
) -> Strategy:
    cls = import_strategy(path)
    if config_path is not None and cls.__name__ == "StrategyV0":
        return cls(config_path=config_path, symbols=symbols, config=config or getattr(cls, "config", {}), lot_multiplier=lot_multiplier)
    return cls(symbols=symbols, config=config or getattr(cls, "config", {}), lot_multiplier=lot_multiplier)


def is_exact_noop(strategy_path: str) -> bool:
    """Return true for the known no-op baseline where full-data semantics are exact."""

    return BASELINES.get(strategy_path, strategy_path).endswith(":DoNothingStrategy")


def is_streamable_buy_and_hold(strategy_path: str, symbols: list[str]) -> bool:
    """Return true for the one-shot AUDUSD baseline with a closed-form tick stream."""

    return BASELINES.get(strategy_path, strategy_path).endswith(":BuyAndHoldAUDUSDStrategy") and symbols == ["AUDUSD"]


def is_streamable_ping_pong(strategy_path: str, symbols: list[str]) -> bool:
    """Return true for hourly AUDUSD round-trip baseline."""

    return BASELINES.get(strategy_path, strategy_path).endswith(":PingPongAUDUSDStrategy") and symbols == ["AUDUSD"]


def is_bar_only_strategy(strategy_path: str, strategy: Strategy, symbols: list[str]) -> bool:
    """Return true when validation can preserve strategy semantics at bar granularity."""

    return BASELINES.get(strategy_path, strategy_path).endswith(":StrategyV0") and len(symbols) > 1 and all(
        not strategy.should_call_on_tick(type("ProbeTick", (), {"symbol": symbol})()) for symbol in symbols
    )


def noop_result(strategy_name: str, symbols: list[str], start: datetime, end: datetime, initial_equity: Decimal) -> BacktestResult:
    """Construct the exact full-range result for a strategy that never trades."""

    return BacktestResult(
        strategy_name=strategy_name,
        symbols=symbols,
        start=start,
        end=end,
        initial_equity=initial_equity,
        final_equity=initial_equity,
        total_return=Decimal("0"),
        max_drawdown=Decimal("0"),
        sharpe=None,
        projected_risk_discipline=Decimal("100"),
        trade_count=0,
        trades=[],
        equity_curve=[
            EquityPoint(timestamp=start, equity=initial_equity, balance=initial_equity, margin_used=Decimal("0"), margin_level=None),
            EquityPoint(timestamp=end, equity=initial_equity, balance=initial_equity, margin_used=Decimal("0"), margin_level=None),
        ],
        data_quality=DataQualityStats(),
        stop_out_events=[],
        risk_events=[],
    )


def _naive_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(timezone.utc).replace(tzinfo=None)


def _ceil_to_quarter(timestamp: datetime) -> datetime:
    minute = ((timestamp.minute // 15) + 1) * 15
    base = timestamp.replace(second=0, microsecond=0)
    if minute >= 60:
        return base.replace(minute=0) + timedelta(hours=1)
    return base.replace(minute=minute)


def _np_datetime_to_utc(timestamp: np.datetime64) -> datetime:
    value = timestamp.astype("datetime64[us]").astype(object)
    return value.replace(tzinfo=timezone.utc)


def _decimal_from_float(value: float) -> Decimal:
    return Decimal(str(value))


def _buy_and_hold_equity(initial_equity: Decimal, entry_ask: float, bid: float, units: float) -> Decimal:
    return initial_equity + _decimal_from_float((bid - entry_ask) * units)


def _sample_buy_and_hold(
    points: list[EquityPoint],
    timestamp: datetime,
    equity: Decimal,
    initial_equity: Decimal,
    margin_used: Decimal,
    leverage: Decimal,
) -> tuple[Decimal, Decimal]:
    margin_level = None if margin_used <= 0 else (equity / margin_used) * Decimal("100")
    points.append(
        EquityPoint(
            timestamp=timestamp,
            equity=equity,
            balance=initial_equity,
            margin_used=margin_used,
            margin_level=margin_level,
        )
    )
    return equity, margin_level or Decimal("0")


def _sharpe(points: list[EquityPoint]) -> Decimal | None:
    if len(points) < 9:
        return None
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if previous.equity == 0:
            continue
        returns.append(float((current.equity - previous.equity) / previous.equity))
    if len(returns) < 8:
        return None
    std = pstdev(returns)
    if std == 0:
        return None
    return Decimal(str(mean(returns) / std))


def buy_and_hold_stream_result(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal,
    data_dir: Path,
) -> BacktestResult:
    """Evaluate buy-and-hold AUDUSD by streaming every tick without object-per-tick overhead."""

    cfg = load_backtest_config()
    lots = Decimal("0.01") * Decimal(str(strategy.lot_multiplier))
    contract_size = Decimal("100000")
    units = float(lots * contract_size)
    leverage = cfg.leverage
    timestamp_type = pa.timestamp("us")
    start_scalar = pa.scalar(_naive_utc(start), type=timestamp_type)
    end_scalar = pa.scalar(_naive_utc(end), type=timestamp_type)

    entered = False
    entry_ask = 0.0
    entry_time: datetime | None = None
    entry_bid = 0.0
    last_bid = 0.0
    last_timestamp: datetime | None = None
    processed_ticks = 0
    skipped_ticks = 0
    points: list[EquityPoint] = []
    next_sample_time: datetime | None = None
    peak_equity = initial_equity
    max_drawdown = Decimal("0")
    max_leverage_seen = Decimal("0")

    def record_sample(sample_time: datetime, bid: float) -> None:
        nonlocal peak_equity, max_drawdown, max_leverage_seen
        equity = _buy_and_hold_equity(initial_equity, entry_ask, bid, units)
        margin_used = (lots * contract_size * _decimal_from_float(bid)) / leverage
        _sample_buy_and_hold(points, sample_time, equity, initial_equity, margin_used, leverage)
        if equity > peak_equity:
            peak_equity = equity
        if peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        if equity > 0:
            leverage_seen = margin_used * leverage / equity
            if leverage_seen > max_leverage_seen:
                max_leverage_seen = leverage_seen

    for path in symbol_files(data_dir, "AUDUSD", start, end):
        parquet_file = pq.ParquetFile(path)
        for row_group in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(row_group, columns=["time", "bid", "ask"])
            valid_price = pc.less(table["bid"], table["ask"])
            invalid_count = int(pc.sum(pc.cast(pc.invert(valid_price), "int64")).as_py() or 0)
            skipped_ticks += invalid_count
            parsed_time = pc.cast(table["time"], timestamp_type)
            in_range = pc.and_(pc.greater_equal(parsed_time, start_scalar), pc.less(parsed_time, end_scalar))
            mask = pc.and_(valid_price, in_range)
            if int(pc.sum(pc.cast(mask, "int64")).as_py() or 0) == 0:
                continue
            filtered = table.append_column("_timestamp", parsed_time).filter(mask)
            times = filtered["_timestamp"].to_numpy(zero_copy_only=False)
            bids = filtered["bid"].to_numpy(zero_copy_only=False)
            asks = filtered["ask"].to_numpy(zero_copy_only=False)
            processed_ticks += len(times)
            if not entered:
                entered = True
                entry_ask = float(asks[0])
                entry_bid = float(bids[0])
                entry_time = _np_datetime_to_utc(times[0])
                next_sample_time = _ceil_to_quarter(entry_time)
            if entered and next_sample_time is not None:
                last_time_in_group = times[-1]
                while np.datetime64(_naive_utc(next_sample_time), "us") <= last_time_in_group:
                    idx = int(np.searchsorted(times, np.datetime64(_naive_utc(next_sample_time), "us"), side="left"))
                    if idx >= len(times):
                        break
                    record_sample(next_sample_time, float(bids[idx]))
                    next_sample_time += timedelta(minutes=15)
            last_bid = float(bids[-1])
            last_timestamp = _np_datetime_to_utc(times[-1])

    if not entered or entry_time is None or last_timestamp is None:
        return noop_result(strategy.name, symbols, start, end, initial_equity)

    final_equity = _buy_and_hold_equity(initial_equity, entry_ask, last_bid, units)
    record_sample(end, last_bid)
    risk_discipline = Decimal("100")
    if max_leverage_seen > Decimal("28"):
        risk_discipline -= Decimal("25")
    risk_discipline -= Decimal("10")

    return BacktestResult(
        strategy_name=strategy.name,
        symbols=symbols,
        start=start,
        end=end,
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return=(final_equity - initial_equity) / initial_equity,
        max_drawdown=max_drawdown,
        sharpe=_sharpe(points),
        projected_risk_discipline=max(Decimal("0"), risk_discipline),
        trade_count=1,
        trades=[
            Trade(
                timestamp=entry_time,
                symbol="AUDUSD",
                side="buy",
                lots=lots,
                price=_decimal_from_float(entry_ask),
                realized_pnl=Decimal("0"),
                equity_after=_buy_and_hold_equity(initial_equity, entry_ask, entry_bid, units),
                tag="buy_and_hold_entry",
            )
        ],
        equity_curve=points,
        data_quality=DataQualityStats(processed_ticks=processed_ticks, skipped_ticks=skipped_ticks),
        stop_out_events=[],
        risk_events=[],
    )


def ping_pong_stream_result(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal,
    data_dir: Path,
) -> BacktestResult:
    """Evaluate hourly immediate AUDUSD round trips from first valid tick per hour."""

    timestamp_type = pa.timestamp("us")
    start_scalar = pa.scalar(_naive_utc(start), type=timestamp_type)
    end_scalar = pa.scalar(_naive_utc(end), type=timestamp_type)
    lots = Decimal("0.01") * Decimal(str(strategy.lot_multiplier))
    units = lots * Decimal("100000")
    balance = initial_equity
    peak = initial_equity
    max_drawdown = Decimal("0")
    points: list[EquityPoint] = []
    trades: list[Trade] = []
    seen_hours: set[datetime] = set()
    processed_ticks = 0
    skipped_ticks = 0

    for path in symbol_files(data_dir, "AUDUSD", start, end):
        parquet_file = pq.ParquetFile(path)
        for row_group in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(row_group, columns=["time", "bid", "ask"])
            valid_price = pc.less(table["bid"], table["ask"])
            skipped_ticks += int(pc.sum(pc.cast(pc.invert(valid_price), "int64")).as_py() or 0)
            parsed_time = pc.cast(table["time"], timestamp_type)
            in_range = pc.and_(pc.greater_equal(parsed_time, start_scalar), pc.less(parsed_time, end_scalar))
            mask = pc.and_(valid_price, in_range)
            if int(pc.sum(pc.cast(mask, "int64")).as_py() or 0) == 0:
                continue
            filtered = table.append_column("_timestamp", parsed_time).filter(mask)
            times = filtered["_timestamp"].to_numpy(zero_copy_only=False)
            bids = filtered["bid"].to_numpy(zero_copy_only=False)
            asks = filtered["ask"].to_numpy(zero_copy_only=False)
            processed_ticks += len(times)
            for raw_time, bid, ask in zip(times, bids, asks, strict=False):
                timestamp = _np_datetime_to_utc(raw_time)
                hour = timestamp.replace(minute=0, second=0, microsecond=0)
                if hour in seen_hours:
                    continue
                seen_hours.add(hour)
                bid_dec = _decimal_from_float(float(bid))
                ask_dec = _decimal_from_float(float(ask))
                spread_cost = (ask_dec - bid_dec) * units
                balance -= spread_cost
                points.append(EquityPoint(timestamp=timestamp, equity=balance, balance=balance, margin_used=Decimal("0"), margin_level=None))
                trades.append(
                    Trade(timestamp=timestamp, symbol="AUDUSD", side="buy", lots=lots, price=ask_dec, realized_pnl=Decimal("0"), equity_after=balance, tag="ping_open")
                )
                trades.append(
                    Trade(timestamp=timestamp, symbol="AUDUSD", side="sell", lots=lots, price=bid_dec, realized_pnl=-spread_cost, equity_after=balance, tag="ping_close")
                )
                if balance > peak:
                    peak = balance
                if peak > 0:
                    drawdown = (peak - balance) / peak
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown

    if not points:
        return noop_result(strategy.name, symbols, start, end, initial_equity)
    points.append(EquityPoint(timestamp=end, equity=balance, balance=balance, margin_used=Decimal("0"), margin_level=None))
    return BacktestResult(
        strategy_name=strategy.name,
        symbols=symbols,
        start=start,
        end=end,
        initial_equity=initial_equity,
        final_equity=balance,
        total_return=(balance - initial_equity) / initial_equity,
        max_drawdown=max_drawdown,
        sharpe=_sharpe(points),
        projected_risk_discipline=Decimal("100"),
        trade_count=len(trades),
        trades=trades,
        equity_curve=points,
        data_quality=DataQualityStats(processed_ticks=processed_ticks, skipped_ticks=skipped_ticks),
        stop_out_events=[],
        risk_events=[],
    )


def run_backtest_for_validation(
    strategy_path: str,
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal,
    data_dir: Path,
) -> BacktestResult:
    """Run a validation backtest, using exact shortcuts only when mathematically identical."""

    if is_exact_noop(strategy_path):
        return noop_result(strategy.name, symbols, start, end, initial_equity)
    if is_streamable_buy_and_hold(strategy_path, symbols):
        return buy_and_hold_stream_result(strategy, symbols, start, end, initial_equity, data_dir)
    if is_streamable_ping_pong(strategy_path, symbols):
        return ping_pong_stream_result(strategy, symbols, start, end, initial_equity, data_dir)
    if is_bar_only_strategy(strategy_path, strategy, symbols):
        return bar_backtest(strategy, symbols, start, end, initial_equity, data_dir=data_dir)
    return backtest(strategy, symbols, start, end, initial_equity, data_dir=data_dir)


def result_dict(result: BacktestResult) -> dict[str, Any]:
    return {
        "strategy": result.strategy_name,
        "start": result.start.isoformat(),
        "end": result.end.isoformat(),
        "final_equity": str(result.final_equity),
        "total_return": str(result.total_return),
        "max_drawdown": str(result.max_drawdown),
        "sharpe": None if result.sharpe is None else str(result.sharpe),
        "risk_discipline": str(result.projected_risk_discipline),
        "trade_count": result.trade_count,
        "stop_out_events": result.stop_out_events,
        "data_quality_processed_ticks": result.data_quality.processed_ticks,
        "data_quality_skipped_ticks": result.data_quality.skipped_ticks,
    }


def filter1(result: BacktestResult) -> tuple[bool, list[str]]:
    incidents: list[str] = []
    if result.stop_out_events:
        incidents.extend(result.stop_out_events)
    if result.final_equity <= 0:
        incidents.append("final equity <= 0")
    if result.projected_risk_discipline < Decimal("100"):
        incidents.append(f"projected risk discipline below 100: {result.projected_risk_discipline}")
    return not incidents, incidents


def date_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(hours=24), end)
        if nxt > cursor:
            windows.append((cursor, nxt))
        cursor = nxt
    return windows


def filter2(
    strategy_path: str,
    symbols: list[str],
    start: datetime,
    end: datetime,
    *,
    base_config: dict[str, Any] | None = None,
    lot_multiplier: float = 1.0,
) -> tuple[bool, list[BacktestResult], dict[str, Any]]:
    cfg = load_backtest_config()
    results: list[BacktestResult] = []
    for w_start, w_end in date_windows(start, end):
        strategy = instantiate_strategy(strategy_path, symbols, base_config, lot_multiplier)
        results.append(run_backtest_for_validation(strategy_path, strategy, symbols, w_start, w_end, cfg.initial_equity, cfg.data_dir))
    returns = [float(item.total_return) for item in results]
    maxdds = [float(item.max_drawdown) for item in results]
    negative_fraction = sum(1 for value in returns if value < 0) / len(returns) if returns else 0
    avg_return = mean(returns) if returns else 0
    cv = 0.0 if abs(avg_return) < 1e-12 else pstdev(returns) / abs(avg_return)
    worst_dd = max(maxdds) if maxdds else 0
    passed = (
        worst_dd <= float(cfg.worst_window_maxdd_pct / Decimal("100"))
        and (cv <= float(cfg.coefficient_variation_threshold) or all(abs(value) < 1e-12 for value in returns))
        and negative_fraction <= float(cfg.negative_return_fraction_threshold)
    )
    return passed, results, {"worst_dd": worst_dd, "cv": cv, "negative_fraction": negative_fraction}


def perturb_config(config: dict[str, Any], multiplier: float) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, int | float) and ("threshold" in key or "window" in key or "std" in key):
            changed[key] = value * multiplier
        else:
            changed[key] = value
    return changed


def filter3(strategy_path: str, symbols: list[str], start: datetime, end: datetime, base_config: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for hours in [-6, -3, 3, 6]:
        shifted_start = start + timedelta(hours=hours)
        shifted_end = end + timedelta(hours=hours)
        strategy = instantiate_strategy(strategy_path, symbols, base_config)
        cfg = load_backtest_config()
        full = run_backtest_for_validation(strategy_path, strategy, symbols, shifted_start, shifted_end, cfg.initial_equity, cfg.data_dir)
        f1, incidents = filter1(full)
        rows.append({"kind": "time_shift", "case": f"{hours:+}h", "filter1": f1, "filter2": None, "incidents": incidents})
    for multiplier in [0.8, 1.0, 1.2]:
        f2, _results, metrics = filter2(strategy_path, symbols, start, end, base_config=perturb_config(base_config, multiplier))
        rows.append({"kind": "parameter", "case": str(multiplier), "filter1": None, "filter2": f2, "metrics": metrics})
    for multiplier in [0.7, 1.0, 1.3]:
        f2, _results, metrics = filter2(strategy_path, symbols, start, end, base_config=base_config, lot_multiplier=multiplier)
        rows.append({"kind": "sizing", "case": str(multiplier), "filter1": None, "filter2": f2, "metrics": metrics})
    time_ok = all(row["filter1"] for row in rows if row["kind"] == "time_shift")
    param_ok = sum(1 for row in rows if row["kind"] == "parameter" and row["filter2"]) >= 2
    sizing_ok = sum(1 for row in rows if row["kind"] == "sizing" and row["filter2"]) >= 2
    return time_ok and param_ok and sizing_ok, rows


def plot_outputs(report_dir: Path, full: BacktestResult, windows: list[BacktestResult]) -> tuple[Path, Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    equity_path = report_dir / "equity_curve.png"
    returns_path = report_dir / "returns_distribution.png"
    sharpe_path = report_dir / "rolling_sharpe.png"
    plt.figure(figsize=(10, 4))
    plt.plot([p.timestamp for p in full.equity_curve], [float(p.equity) for p in full.equity_curve])
    plt.title("Equity Curve")
    plt.tight_layout()
    plt.savefig(equity_path, dpi=140)
    plt.close()
    returns = [float(item.total_return) for item in windows]
    plt.figure(figsize=(8, 4))
    plt.hist(returns, bins=min(20, max(1, len(returns))))
    plt.title("Per-window Returns")
    plt.tight_layout()
    plt.savefig(returns_path, dpi=140)
    plt.close()
    sharpes = [float(item.sharpe) if item.sharpe is not None else 0.0 for item in windows]
    plt.figure(figsize=(8, 4))
    plt.plot(range(len(sharpes)), sharpes)
    plt.title("Rolling Window Sharpe")
    plt.tight_layout()
    plt.savefig(sharpe_path, dpi=140)
    plt.close()
    return equity_path, returns_path, sharpe_path


def write_report(path: Path, full: BacktestResult, f1: tuple[bool, list[str]], windows: list[BacktestResult], f2_metrics: dict[str, Any], f2_pass: bool, f3_rows: list[dict[str, Any]], f3_pass: bool, plots: tuple[Path, Path, Path]) -> None:
    lines = [
        "# Validation Report",
        "",
        "## Full Backtest",
        "",
        "```json",
        json.dumps(result_dict(full), indent=2),
        "```",
        "",
        "## Filter 1 - No Blow-Up",
        "",
        f"Status: {'PASS' if f1[0] else 'FAIL'}",
        "",
        f"Incidents: {f1[1] if f1[1] else 'None'}",
        "",
        "## Filter 2 - Distribution Stability",
        "",
        f"Status: {'PASS' if f2_pass else 'FAIL'}",
        "",
        f"Metrics: `{f2_metrics}`",
        "",
        "| Window | Return | MaxDD | Sharpe | Trades |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in windows:
        lines.append(f"| {item.start.isoformat()} | {item.total_return} | {item.max_drawdown} | {item.sharpe} | {item.trade_count} |")
    lines.extend(
        [
            "",
            "## Filter 3 - Robustness",
            "",
            f"Status: {'PASS' if f3_pass else 'FAIL'}",
            "",
            "| Kind | Case | Filter1 | Filter2 | Details |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in f3_rows:
        lines.append(f"| {row['kind']} | {row['case']} | {row.get('filter1')} | {row.get('filter2')} | {row.get('metrics') or row.get('incidents')} |")
    lines.extend(["", "## Plots", ""])
    for plot in plots:
        lines.append(f"- `{plot}`")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="do_nothing")
    parser.add_argument("--symbols", default="AUDUSD")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args()
    cfg = load_backtest_config()
    start = parse_dt(args.start) if args.start else cfg.default_start
    end = parse_dt(args.end) if args.end else cfg.default_end
    symbols = (
        load_strategy_v0_config().tradable_symbols
        if args.symbols == "all_tradable"
        else [item.strip() for item in args.symbols.split(",") if item.strip()]
    )
    strategy = instantiate_strategy(args.strategy, symbols)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = ROOT / "reports" / f"validation_{strategy.name}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    full = run_backtest_for_validation(args.strategy, strategy, symbols, start, end, cfg.initial_equity, cfg.data_dir)
    f1 = filter1(full)
    f2_pass, windows, f2_metrics = filter2(args.strategy, symbols, start, end, base_config=strategy.config)
    f3_pass, f3_rows = filter3(args.strategy, symbols, start, end, strategy.config)
    plots = plot_outputs(report_dir, full, windows)
    write_report(report_dir / "validation_report.md", full, f1, windows, f2_metrics, f2_pass, f3_rows, f3_pass, plots)
    (report_dir / "result.json").write_text(json.dumps(result_dict(full), indent=2), encoding="utf-8")
    print(report_dir)
    return 0 if f1[0] and f2_pass and f3_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
