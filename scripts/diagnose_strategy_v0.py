"""Verbose six-hour StrategyV0 zero-trade diagnostic.

This script intentionally observes StrategyV0 through the offline bar engine
shape without modifying the live strategy interface.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.bar_engine import _bar_tick, load_symbol_bars
from trifolium.backtest.config import load_backtest_config, load_instrument_specs, parse_datetime
from trifolium.backtest.equity_tracker import EquityTracker
from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, Bar, DataQualityStats, Order, Trade
from trifolium.strategy.v0.predictor import PerSymbolEnsemble, StrategyV0Predictor
from trifolium.strategy.v0.strategy import StrategyV0
from trifolium.strategy.v0.trader import cross_sectional_filter, signal_to_exposure


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="python"))
    return value


class JsonlLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": _json_safe(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _load_bars(symbols: list[str], start: datetime, end: datetime) -> tuple[dict[str, list[Bar]], DataQualityStats]:
    cfg = load_backtest_config()
    bars_by_symbol: dict[str, list[Bar]] = {}
    merged_quality = DataQualityStats()
    for symbol in symbols:
        bars, quality = load_symbol_bars(cfg.data_dir, symbol, start, end)
        bars_by_symbol[symbol] = bars
        merged_quality.processed_ticks += quality.processed_ticks
        merged_quality.skipped_ticks += quality.skipped_ticks
    return bars_by_symbol, merged_quality


def _aligned_bar_count(strategy: StrategyV0) -> int:
    builder = strategy._predictor.feature_builder
    return len(builder._align_bars(strategy._bar_history))


def _signal_histogram(signals: dict[str, float]) -> dict[str, int]:
    bins = {
        "none": 0,
        "[0,0.2)": 0,
        "[0.2,0.4)": 0,
        "[0.4,0.6)": 0,
        "[0.6,0.8)": 0,
        "[0.8,1.0]": 0,
    }
    if not signals:
        bins["none"] = 1
        return bins
    for value in signals.values():
        mag = abs(value)
        if mag < 0.2:
            bins["[0,0.2)"] += 1
        elif mag < 0.4:
            bins["[0.2,0.4)"] += 1
        elif mag < 0.6:
            bins["[0.4,0.6)"] += 1
        elif mag < 0.8:
            bins["[0.6,0.8)"] += 1
        else:
            bins["[0.8,1.0]"] += 1
    return bins


def _recalibration_diagnostics(strategy: StrategyV0) -> dict[str, Any]:
    settings = strategy._settings
    predictor = strategy._predictor
    matrices = predictor.feature_builder.training_matrices_from_bars(strategy._bar_history)
    rows: dict[str, dict[str, Any]] = {}
    destroyers: list[str] = []
    for symbol, (x, y) in matrices.items():
        samples = int(len(x))
        if samples < settings.min_training_samples:
            rows[symbol] = {
                "samples": samples,
                "reason": "insufficient_training_samples",
                "validation_sharpe": None,
                "destroyer": True,
            }
            destroyers.append(symbol)
            continue
        ensemble = PerSymbolEnsemble(
            settings.predictor.ridge_alpha,
            settings.predictor.n_bootstraps,
            settings.predictor.bootstrap_seeds,
        )
        ensemble.fit(x, y)
        preds = ensemble.predict(x)
        validation_sharpe = StrategyV0Predictor._validation_sharpe(preds, y)
        is_destroyer = validation_sharpe < float(settings.destroyer_validation_sharpe_threshold)
        rows[symbol] = {
            "samples": samples,
            "reason": "validation_sharpe_below_threshold" if is_destroyer else "model_active",
            "validation_sharpe": validation_sharpe,
            "threshold": str(settings.destroyer_validation_sharpe_threshold),
            "destroyer": is_destroyer,
        }
        if is_destroyer:
            destroyers.append(symbol)
    return {"symbols": rows, "would_destroy": sorted(destroyers)}


def _action_diagnostics(strategy: StrategyV0, prices: dict[str, Decimal]) -> dict[str, Any]:
    signals = strategy.last_signals
    if not signals:
        return {"reason": "no_signals", "actions": []}
    directions = cross_sectional_filter(signals, strategy._settings)
    actions: list[dict[str, Any]] = []
    for symbol, signal in sorted(signals.items()):
        exposure = signal_to_exposure(signal, strategy._settings)
        actions.append(
            {
                "symbol": symbol,
                "signal": signal,
                "abs_signal": abs(signal),
                "direction": directions.get(symbol, 0),
                "sizing_exposure_fraction": exposure,
                "price": prices.get(symbol),
            }
        )
    return {"reason": "signals_available", "actions": actions}


def _summarize_root_cause(events: list[dict[str, Any]], strategy: StrategyV0, duration_hours: float) -> tuple[str, list[str], str]:
    recalibration_events = [
        event for event in events if event["event"] in {"daily_recalibration", "initial_recalibration"}
    ]
    order_events = [event for event in events if event["event"] == "order_emitted"]
    max_aligned = max((event["payload"].get("aligned_bars", 0) for event in events if event["event"] == "bar_close"), default=0)
    min_samples = strategy._settings.min_training_samples
    max_lookback = strategy._predictor.feature_builder.max_lookback
    bar_minutes = strategy._settings.bar_interval_minutes
    theoretical_max_bars = int(duration_hours * 60 / bar_minutes)
    required_bars = max_lookback + min_samples + 16

    if not recalibration_events:
        finding = "b) Predictor not fitting"
        evidence = [
            "No daily_recalibration event occurred inside the evaluated six-hour window.",
            f"Six hours at {bar_minutes}-minute bars yields at most {theoretical_max_bars} aligned bars.",
            f"StrategyV0 needs about {required_bars} aligned bars before fitting: max_lookback={max_lookback}, min_training_samples={min_samples}, missing_bar_buffer=16.",
        ]
        fix = "Provide pre-window warmup history or lower the fitting requirement in a sandbox candidate before expecting six-hour smoke trades."
        return finding, evidence, fix

    all_destroyers = all(event["payload"].get("destroyer_count") == len(strategy._settings.tradable_symbols) for event in recalibration_events)
    if all_destroyers:
        finding = "a) All symbols destroyer-neutralized"
        evidence = [
            "Every daily_recalibration event put all tradable symbols in the destroyer set.",
            "No active model remained after recalibration, so signal computation stayed skipped.",
        ]
        fix = "Lower destroyer_validation_sharpe_threshold in a sandbox candidate."
        return finding, evidence, fix

    signal_events = [event for event in events if event["event"] == "potential_order"]
    low_signal_events = [
        event
        for event in signal_events
        if event["payload"].get("action_diagnostics", {}).get("reason") == "signals_available"
        and all(abs(item.get("signal", 0.0)) < 0.2 for item in event["payload"].get("action_diagnostics", {}).get("actions", []))
    ]
    if signal_events and len(low_signal_events) == len(signal_events):
        finding = "c) Signals below sizing threshold"
        evidence = [
            "Signals were computed, but every absolute signal stayed below the first non-zero sizing tier.",
            f"No order_emitted event was recorded; order_count={len(order_events)}.",
        ]
        fix = "Reduce sizing thresholds in a sandbox candidate."
        return finding, evidence, fix

    if order_events:
        rejected = [event for event in order_events if event["payload"].get("risk_gate_status") != "not_invoked_offline_backtest"]
        if rejected:
            finding = "d) Orders submitted but Risk Gate rejected"
            evidence = ["At least one order event reached a Risk Gate status other than offline-not-invoked."]
            fix = "Investigate Risk Gate mode and rejection reason."
            return finding, evidence, fix
        finding = "orders emitted in offline backtest"
        evidence = [f"{len(order_events)} orders were emitted by StrategyV0 during the diagnostic window."]
        fix = "No zero-trade strategy fix needed for this window."
        return finding, evidence, fix

    finding = "e) No order generated after partial signal path"
    evidence = [
        f"Max aligned bars seen: {max_aligned}.",
        "The replay reached neither a conclusive all-destroyer state nor an emitted order.",
    ]
    fix = "Inspect the JSONL potential_order events for the first zero target-lot condition."
    return finding, evidence, fix


def run_diagnostic(
    start: datetime,
    hours: float,
    output_prefix: Path,
    config_path: Path | None = None,
    warmup_start: datetime | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    strategy = StrategyV0(config_path=config_path)
    symbols = strategy._settings.tradable_symbols
    end = start + timedelta(hours=hours)
    load_start = warmup_start if warmup_start is not None and warmup_start < start else start
    bars_by_symbol, quality = _load_bars(symbols, load_start, end)
    jsonl_path = output_prefix.with_suffix(".jsonl")
    md_path = output_prefix.with_suffix(".md")
    logger = JsonlLogger(jsonl_path)
    executor = Executor(load_instrument_specs())
    cfg = load_backtest_config()
    account = AccountState(balance=cfg.initial_equity, equity=cfg.initial_equity, leverage=cfg.leverage)
    tracker = EquityTracker(cfg.initial_equity, executor)
    trades: list[Trade] = []
    recalibrated_dates: set[datetime.date] = set()
    by_time: dict[datetime, list[Bar]] = {}
    events: list[dict[str, Any]] = []

    def log(event: str, payload: dict[str, Any]) -> None:
        record = {"event": event, "payload": _json_safe(payload)}
        events.append(record)
        logger.write(event, payload)

    for bars in bars_by_symbol.values():
        for bar in bars:
            if start <= bar.timestamp < end:
                by_time.setdefault(bar.timestamp, []).append(bar)

    log(
        "diagnostic_start",
        {
            "start": start,
            "end": end,
            "warmup_start": warmup_start,
            "hours": hours,
            "symbols": symbols,
            "bar_counts": {symbol: len(bars) for symbol, bars in bars_by_symbol.items()},
            "data_quality": quality,
            "min_training_samples": strategy._settings.min_training_samples,
            "destroyer_threshold": strategy._settings.destroyer_validation_sharpe_threshold,
        },
    )

    if warmup_start is not None and warmup_start < start:
        warmup_timestamps = sorted(
            {
                bar.timestamp
                for bars in bars_by_symbol.values()
                for bar in bars
                if warmup_start <= bar.timestamp < start
            }
        )
        for timestamp in warmup_timestamps:
            warmup_bars = sorted(
                [bar for bars in bars_by_symbol.values() for bar in bars if bar.timestamp == timestamp],
                key=lambda item: item.symbol,
            )
            for bar in warmup_bars:
                if strategy.should_call_on_bar_close(bar):
                    strategy._append_bar(bar)
        diagnostics = _recalibration_diagnostics(strategy)
        strategy.recalibrate_from_bars(strategy._bar_history)
        log(
            "initial_recalibration",
            {
                "warmup_start": warmup_start,
                "start": start,
                "warmup_timestamp_count": len(warmup_timestamps),
                "aligned_bars": _aligned_bar_count(strategy),
                "pre_fit": diagnostics,
                "actual_destroyers": sorted(strategy.destroyer_symbols),
                "destroyer_count": len(strategy.destroyer_symbols),
                "active_model_symbols": sorted(
                    symbol
                    for symbol, ensemble in strategy._predictor.ensembles.items()
                    if symbol not in strategy.destroyer_symbols and ensemble.fitted
                ),
            },
        )

    def apply_orders(orders: list[Order]) -> None:
        for order in orders:
            tick = account.latest_ticks.get(order.symbol)
            log(
                "order_emitted",
                {
                    "order": order,
                    "tick_available": tick is not None,
                    "risk_gate_status": "not_invoked_offline_backtest",
                },
            )
            if tick is None:
                continue
            fill = executor.simulate_fill(order, tick, account)
            if fill is None:
                continue
            trades.append(
                Trade(
                    timestamp=fill.timestamp,
                    symbol=fill.symbol,
                    side=fill.side,
                    lots=fill.lots,
                    price=fill.price,
                    realized_pnl=fill.realized_pnl,
                    equity_after=account.equity,
                    tag=fill.tag,
                )
            )

    for timestamp in sorted(by_time):
        current_bars = sorted(by_time[timestamp], key=lambda item: item.symbol)
        for bar in current_bars:
            account.latest_ticks[bar.symbol] = _bar_tick(bar)
        executor.mark_to_market(account)
        tracker.tick(timestamp, account)

        before_destroyers = set(strategy.destroyer_symbols)
        before_decision_bar = strategy._last_decision_bar
        orders_this_timestamp = 0
        for bar in current_bars:
            if strategy.should_call_on_bar_close(bar):
                orders = strategy.on_bar_close(bar, account.clone_for_strategy())
                orders_this_timestamp += len(orders)
                apply_orders(orders)

        prices = {symbol: tick.mid for symbol, tick in account.latest_ticks.items()}
        destroyers = strategy.destroyer_symbols
        signals = strategy.last_signals
        decision_fired = strategy._last_decision_bar == timestamp and before_decision_bar != timestamp
        log(
            "bar_close",
            {
                "bar_timestamp": timestamp,
                "bars_this_timestamp": [bar.symbol for bar in current_bars],
                "aligned_bars": _aligned_bar_count(strategy),
                "destroyer_count": len(destroyers),
                "non_destroyer_count": len(strategy._settings.tradable_symbols) - len(destroyers),
                "destroyer_symbols": sorted(destroyers),
                "new_destroyers": sorted(destroyers - before_destroyers),
                "has_active_models": strategy._predictor.has_active_models,
                "signal_histogram_abs": _signal_histogram(signals),
                "decision_fired": decision_fired,
                "orders_this_timestamp": orders_this_timestamp,
            },
        )
        log(
            "potential_order",
            {
                "bar_timestamp": timestamp,
                "decision_fired": decision_fired,
                "action_diagnostics": _action_diagnostics(strategy, prices),
                "portfolio_messages": strategy.portfolio_messages,
            },
        )

        if timestamp.hour == 21 and timestamp.minute == 0 and timestamp.date() not in recalibrated_dates:
            diagnostics = _recalibration_diagnostics(strategy)
            strategy.recalibrate_from_bars(strategy._bar_history)
            recalibrated_dates.add(timestamp.date())
            log(
                "daily_recalibration",
                {
                    "bar_timestamp": timestamp,
                    "pre_fit": diagnostics,
                    "actual_destroyers": sorted(strategy.destroyer_symbols),
                    "destroyer_count": len(strategy.destroyer_symbols),
                    "active_model_symbols": sorted(
                        symbol
                        for symbol, ensemble in strategy._predictor.ensembles.items()
                        if symbol not in strategy.destroyer_symbols and ensemble.fitted
                    ),
                },
            )

    executor.mark_to_market(account)
    tracker.sample(end, account)
    finding, evidence, fix = _summarize_root_cause(events, strategy, hours)
    summary = {
        "finding": finding,
        "evidence": evidence,
        "recommended_fix": fix,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "trade_count": len(trades),
        "final_equity": str(account.equity),
        "max_drawdown": str(tracker.max_drawdown),
        "risk_discipline": str(tracker.projected_risk_discipline(account)),
        "jsonl": str(jsonl_path),
    }
    log("diagnostic_summary", summary)

    md_lines = [
        "# StrategyV0 Zero-Trade Diagnostic",
        "",
        f"- Window: `{start.isoformat()}` to `{end.isoformat()}`",
        f"- JSONL: `{jsonl_path}`",
        "",
        "## Root Cause",
        "",
        finding,
        "",
        "## Evidence",
        "",
    ]
    md_lines.extend(f"- {item}" for item in evidence)
    md_lines.extend(
        [
            "",
            "## Backtest Result",
            "",
            f"- Trades: `{len(trades)}`",
            f"- Final equity: `{account.equity}`",
            f"- MaxDD: `{tracker.max_drawdown}`",
            f"- Risk Discipline: `{tracker.projected_risk_discipline(account)}`",
            "",
            "## Recommended Targeted Fix",
            "",
            fix,
        ]
    )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return jsonl_path, md_path, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--warmup-hours", type=float, default=0.0)
    parser.add_argument("--config-path", default=None)
    args = parser.parse_args()
    cfg = load_backtest_config()
    start = parse_datetime(args.start) if args.start else cfg.default_start
    warmup_start = start - timedelta(hours=args.warmup_hours) if args.warmup_hours > 0 else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = ROOT / "logs" / f"diagnostic_v0_{stamp}"
    _jsonl, md_path, summary = run_diagnostic(
        start,
        args.hours,
        prefix,
        Path(args.config_path) if args.config_path else None,
        warmup_start=warmup_start,
    )
    print(json.dumps({"markdown": str(md_path), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
