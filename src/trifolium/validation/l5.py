"""Reusable L5 validation callable for strategy deployment gates."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from trifolium.backtest.bar_engine import bar_backtest_from_bars, load_symbol_bars
from trifolium.backtest.config import load_backtest_config
from trifolium.backtest.types import BacktestResult, Bar
from trifolium.strategy.v0.config import load_strategy_v0_config


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))


class FilterOutcome(BaseModel):
    """Machine-readable status for one L5 filter."""

    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Reusable L5 output for scripts and future self-improving candidates."""

    strategy: str
    symbols: list[str]
    start: str
    end: str
    passed: bool
    report_dir: str
    markdown_report: str
    json_report: str
    full_backtest: dict[str, Any]
    filter1: FilterOutcome
    filter2: FilterOutcome
    filter3: FilterOutcome
    d2: dict[str, Any]


def _resolve_symbols(symbols: str | list[str]) -> list[str]:
    if isinstance(symbols, list):
        return symbols
    if symbols == "all_tradable":
        return load_strategy_v0_config().tradable_symbols
    return [item.strip() for item in symbols.split(",") if item.strip()]


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _pct(value: Any) -> float:
    return float(value) * 100.0


def _interval_key(timestamp: datetime) -> str:
    minute = (timestamp.minute // 15) * 15
    return timestamp.replace(minute=minute, second=0, microsecond=0).isoformat()


def _active_intervals(full: BacktestResult) -> int:
    return len({_interval_key(trade.timestamp) for trade in full.trades})


def _sortino(full: BacktestResult) -> float | None:
    points = full.equity_curve
    if len(points) < 3:
        return None
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        if previous.equity == 0:
            continue
        returns.append(float((current.equity - previous.equity) / previous.equity))
    downside = [value for value in returns if value < 0]
    if not returns or not downside:
        return None
    avg_return = sum(returns) / len(returns)
    downside_var = sum(value * value for value in downside) / len(downside)
    if downside_var <= 0:
        return None
    return avg_return / (downside_var**0.5)


def _win_rate(full: BacktestResult) -> float | None:
    closed = [trade for trade in full.trades if trade.realized_pnl != 0]
    if not closed:
        return None
    wins = sum(1 for trade in closed if trade.realized_pnl > 0)
    return wins / len(closed)


def _gate_row(name: str, threshold: str, value: Any, passed: bool) -> dict[str, Any]:
    return {"gate": name, "threshold": threshold, "value": value, "passed": passed}


def _parent_value(parent_metrics: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if not parent_metrics:
        return default
    full = parent_metrics.get("full_backtest", {})
    return full.get(key, default)


def _result_dict(result: BacktestResult) -> dict[str, Any]:
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


def _build_d2_report(
    *,
    full: BacktestResult,
    f1: tuple[bool, list[str]],
    windows: list[BacktestResult],
    f2_metrics: dict[str, Any],
    f2_pass: bool,
    f3_rows: list[dict[str, Any]],
    f3_pass: bool,
    plots: tuple[Path, Path, Path],
    symbols: list[str],
    report_dir: Path,
    parent_nickname: str | None = None,
    parent_metrics: dict[str, Any] | None = None,
    changed_parameters: dict[str, Any] | None = None,
    evaluation_method: str = "BACKTEST",
) -> dict[str, Any]:
    maxdd_pct = _pct(full.max_drawdown)
    total_return_pct = _pct(full.total_return)
    risk_discipline = float(full.projected_risk_discipline)
    trade_count = full.trade_count
    active_intervals = _active_intervals(full)
    parent_trade_count = _parent_value(parent_metrics, "trade_count")
    parent_total_raw = _parent_value(parent_metrics, "total_return")
    parent_return_pct = None if parent_total_raw is None else float(parent_total_raw) * 100.0
    return_delta_pct = None if parent_return_pct is None else total_return_pct - parent_return_pct

    gates = [
        _gate_row("MaxDD", "< 30%", round(maxdd_pct, 6), maxdd_pct < 30.0),
        _gate_row("Risk Discipline", "= 100", risk_discipline, risk_discipline == 100.0),
        _gate_row("Trade Count", ">= 30", trade_count, trade_count >= 30),
        _gate_row("Active Intervals", ">= 8", active_intervals, active_intervals >= 8),
    ]
    gate_passed = all(item["passed"] for item in gates)

    behavior_signature = {
        "trade_count": trade_count,
        "symbols_traded": sorted({trade.symbol for trade in full.trades}),
        "first_trade": full.trades[0].model_dump(mode="json") if full.trades else None,
        "last_trade": full.trades[-1].model_dump(mode="json") if full.trades else None,
        "equity_start": str(full.initial_equity),
        "equity_end": str(full.final_equity),
    }
    parent_behavior = {
        "trade_count": parent_trade_count,
        "total_return": _parent_value(parent_metrics, "total_return"),
    }
    binding_different = parent_trade_count is None or int(parent_trade_count or 0) != trade_count or (return_delta_pct is not None and abs(return_delta_pct) > 1e-12)
    binding_verdict = "BINDING" if trade_count > 0 and binding_different else "DEAD CODE"

    sweep_rows = [row for row in f3_rows if row.get("kind") in {"parameter", "sizing"}]
    if not sweep_rows:
        robustness_verdict = "SINGLE_POINT"
        robustness_note = "Single-point evaluation, robustness not assessed"
    elif f3_pass:
        robustness_verdict = "ROBUST"
        robustness_note = "Filter 3 sweep passed enough perturbation cases"
    else:
        robustness_verdict = "UNSTABLE"
        robustness_note = "Parameter/sizing/time-shift sweep failed robustness threshold"

    duration_days = (full.end - full.start).total_seconds() / 86400
    regime_consistency = {
        "train_return_pct": None,
        "validate_return_pct": None,
        "gap_pct": None,
        "verdict": "N/A for live walk-forward" if duration_days < 30 else "N/A: explicit train/validate split not run",
    }

    failure_modes: list[str] = []
    if full.stop_out_events:
        failure_modes.append(f"stop_out_events={full.stop_out_events}")
    if full.risk_events:
        failure_modes.append(f"risk_events={full.risk_events}")
    if maxdd_pct >= 25:
        failure_modes.append("gate-edge proximity: MaxDD near 30% hard gate")
    if risk_discipline < 100:
        failure_modes.append("risk discipline below perfect score")
    if trade_count == 0:
        failure_modes.append("dead strategy path: zero trades")
    if not failure_modes:
        failure_modes.append("None observed in evaluation window")

    if not gate_passed:
        decision = "REJECT"
        reason = "One or more hard gates failed; no secondary metric can override gate failure."
        next_experiment = "Address the first failing Section 2 gate, especially Trade Count or Active Intervals."
    elif binding_verdict == "DEAD CODE":
        decision = "NO-OP"
        reason = "Candidate did not demonstrate behavior change."
        next_experiment = "Make a binding modification that changes position path or fill pattern."
    elif robustness_verdict == "UNSTABLE":
        decision = "KEEP v_N-1"
        reason = "Candidate passed gates but failed robustness sweep."
        next_experiment = "Try a less isolated parameter change."
    else:
        decision = "ACCEPT v_N" if return_delta_pct is None or return_delta_pct >= 0 else "KEEP v_N-1"
        reason = "Gate-first evaluation passed; primary objective and robustness decide acceptance."
        next_experiment = "Improve total return while preserving all Section 2 gates."

    return {
        "identity": {
            "strategy_id": full.strategy_name,
            "parent": parent_nickname,
            "changed_parameters": changed_parameters or {},
            "instruments": symbols,
            "evaluation_method": evaluation_method,
            "report_dir": str(report_dir),
        },
        "gate_check": {"passed": gate_passed, "gates": gates, "termination_rule": "ANY FAIL -> REJECT"},
        "primary_objective": {"total_return_pct": round(total_return_pct, 6), "parent_return_pct": parent_return_pct, "delta_vs_parent_pct": return_delta_pct},
        "secondary_metrics": {
            "maxdd_pct": round(maxdd_pct, 6),
            "sharpe_15min": None if full.sharpe is None else float(full.sharpe),
            "sortino": _sortino(full),
            "win_rate": _win_rate(full),
            "avg_trade_duration": None,
        },
        "binding_check": {
            "trade_count": trade_count,
            "parent_trade_count": parent_trade_count,
            "different": binding_different,
            "behavior_signature": behavior_signature,
            "parent_behavior": parent_behavior,
            "verdict": binding_verdict,
        },
        "robustness": {"sweep_rows": sweep_rows, "verdict": robustness_verdict, "note": robustness_note},
        "regime_consistency": regime_consistency,
        "failure_modes_observed": failure_modes,
        "decision": {"verdict": decision, "reason": reason, "next_experiment_suggested": next_experiment},
        "engine_diagnostics": {
            "filter1": {"passed": f1[0], "incidents": f1[1]},
            "filter2": {"passed": f2_pass, "metrics": f2_metrics, "windows": [_result_dict(item) for item in windows]},
            "filter3": {"passed": f3_pass, "rows": f3_rows},
            "plots": [str(plot) for plot in plots],
        },
    }


def _write_d2_markdown(path: Path, d2: dict[str, Any]) -> None:
    gates = d2["gate_check"]["gates"]
    lines = [
        "# D2 Evaluation Report",
        "",
        "## Section 1 - Identity",
        "",
        f"- Strategy ID: `{d2['identity']['strategy_id']}`",
        f"- Parent: `{d2['identity']['parent']}`",
        f"- Changed parameters: `{d2['identity']['changed_parameters']}`",
        f"- Instruments: `{', '.join(d2['identity']['instruments'])}`",
        f"- Evaluation method: `{d2['identity']['evaluation_method']}`",
        "",
        "## Section 2 - Gate Check",
        "",
        "| Gate | Threshold | Value | PASS/FAIL |",
        "| --- | --- | --- | --- |",
    ]
    for gate in gates:
        lines.append(f"| {gate['gate']} | {gate['threshold']} | {gate['value']} | {'PASS' if gate['passed'] else 'FAIL'} |")
    lines.extend(
        [
            "",
            f"Gate verdict: `{'PASS' if d2['gate_check']['passed'] else 'FAIL -> REJECT'}`",
            "",
            "## Section 3 - Primary Objective",
            "",
            f"- Total Return: `{d2['primary_objective']['total_return_pct']:.6f}%`",
            f"- vs Parent: `{d2['primary_objective']['delta_vs_parent_pct']}` percentage points",
            "",
            "## Section 4 - Secondary Metrics",
            "",
            f"- MaxDD: `{d2['secondary_metrics']['maxdd_pct']:.6f}%`",
            f"- Sharpe (15-min): `{d2['secondary_metrics']['sharpe_15min']}`",
            f"- Sortino: `{d2['secondary_metrics']['sortino']}`",
            f"- Win Rate: `{d2['secondary_metrics']['win_rate']}`",
            f"- Avg Trade Duration: `{d2['secondary_metrics']['avg_trade_duration']}`",
            "",
            "## Section 5 - Binding Check",
            "",
            f"- Trade count vs parent: `{d2['binding_check']['trade_count']}` vs `{d2['binding_check']['parent_trade_count']}`",
            f"- Behavior different: `{'Y' if d2['binding_check']['different'] else 'N'}`",
            f"- Behavior signature: `{d2['binding_check']['behavior_signature']}`",
            f"- Verdict: `{d2['binding_check']['verdict']}`",
            "",
            "## Section 6 - Robustness",
            "",
            "| Kind | Case | Filter1 | Filter2 | Details |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in d2["robustness"]["sweep_rows"]:
        lines.append(f"| {row.get('kind')} | {row.get('case')} | {row.get('filter1')} | {row.get('filter2')} | {row.get('metrics') or row.get('incidents')} |")
    if not d2["robustness"]["sweep_rows"]:
        lines.append("| single-point | N/A | N/A | N/A | Single-point evaluation, robustness not assessed |")
    lines.extend(
        [
            "",
            f"Robustness verdict: `{d2['robustness']['verdict']}`",
            f"Note: {d2['robustness']['note']}",
            "",
            "## Section 7 - Regime Consistency",
            "",
            f"- Train (20d) Return: `{d2['regime_consistency']['train_return_pct']}`",
            f"- Validate (10d) Return: `{d2['regime_consistency']['validate_return_pct']}`",
            f"- Gap: `{d2['regime_consistency']['gap_pct']}`",
            f"- Verdict: `{d2['regime_consistency']['verdict']}`",
            "",
            "## Section 8 - Failure Modes Observed",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in d2["failure_modes_observed"])
    lines.extend(
        [
            "",
            "## Section 9 - Decision",
            "",
            f"- Decision: `{d2['decision']['verdict']}`",
            f"- Reason: {d2['decision']['reason']}",
            f"- Next experiment suggested: {d2['decision']['next_experiment_suggested']}",
            "",
            "## Section 10 - Engine Diagnostics",
            "",
            "```json",
            json.dumps(d2["engine_diagnostics"], indent=2, default=str),
            "```",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _is_strategy_v0(strategy_path: str) -> bool:
    return strategy_path == "strategy_v0" or strategy_path.endswith(":StrategyV0")


def _cached_bar_runner(
    legacy: Any,
    strategy_path: str,
    symbols: list[str],
    start: datetime,
    end: datetime,
    expanded_start: datetime,
    expanded_end: datetime,
    strategy_config_path: Path | None = None,
) -> Any:
    cfg = load_backtest_config()
    bars_by_symbol: dict[str, list[Bar]] = {}
    for symbol in symbols:
        bars, _quality = load_symbol_bars(cfg.data_dir, symbol, expanded_start, expanded_end)
        bars_by_symbol[symbol] = bars

    def run(w_start: datetime, w_end: datetime, *, base_config: dict[str, Any] | None = None, lot_multiplier: float = 1.0) -> BacktestResult:
        strategy = legacy.instantiate_strategy(strategy_path, symbols, base_config, lot_multiplier, config_path=strategy_config_path)
        return bar_backtest_from_bars(
            strategy,
            symbols,
            w_start,
            w_end,
            cfg.initial_equity,
            bars_by_symbol=bars_by_symbol,
        )

    return run


def _filter2_cached(
    legacy: Any,
    runner: Any,
    start: datetime,
    end: datetime,
    *,
    base_config: dict[str, Any] | None = None,
    lot_multiplier: float = 1.0,
) -> tuple[bool, list[BacktestResult], dict[str, Any]]:
    cfg = load_backtest_config()
    results = [runner(w_start, w_end, base_config=base_config, lot_multiplier=lot_multiplier) for w_start, w_end in legacy.date_windows(start, end)]
    returns = [float(item.total_return) for item in results]
    maxdds = [float(item.max_drawdown) for item in results]
    negative_fraction = sum(1 for value in returns if value < 0) / len(returns) if returns else 0
    avg_return = legacy.mean(returns) if returns else 0
    cv = 0.0 if abs(avg_return) < 1e-12 else legacy.pstdev(returns) / abs(avg_return)
    worst_dd = max(maxdds) if maxdds else 0
    passed = (
        worst_dd <= float(cfg.worst_window_maxdd_pct / 100)
        and (cv <= float(cfg.coefficient_variation_threshold) or all(abs(value) < 1e-12 for value in returns))
        and negative_fraction <= float(cfg.negative_return_fraction_threshold)
    )
    return passed, results, {"worst_dd": worst_dd, "cv": cv, "negative_fraction": negative_fraction}


def _filter3_cached(
    legacy: Any,
    runner: Any,
    start: datetime,
    end: datetime,
    base_config: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for hours in [-6, -3, 3, 6]:
        full = runner(start + timedelta(hours=hours), end + timedelta(hours=hours), base_config=base_config)
        f1, incidents = legacy.filter1(full)
        rows.append({"kind": "time_shift", "case": f"{hours:+}h", "filter1": f1, "filter2": None, "incidents": incidents})
    for multiplier in [0.8, 1.0, 1.2]:
        f2, _results, metrics = _filter2_cached(legacy, runner, start, end, base_config=legacy.perturb_config(base_config, multiplier))
        rows.append({"kind": "parameter", "case": str(multiplier), "filter1": None, "filter2": f2, "metrics": metrics})
    for multiplier in [0.7, 1.0, 1.3]:
        f2, _results, metrics = _filter2_cached(legacy, runner, start, end, base_config=base_config, lot_multiplier=multiplier)
        rows.append({"kind": "sizing", "case": str(multiplier), "filter1": None, "filter2": f2, "metrics": metrics})
    time_ok = all(row["filter1"] for row in rows if row["kind"] == "time_shift")
    param_ok = sum(1 for row in rows if row["kind"] == "parameter" and row["filter2"]) >= 2
    sizing_ok = sum(1 for row in rows if row["kind"] == "sizing" and row["filter2"]) >= 2
    return time_ok and param_ok and sizing_ok, rows


def validate_strategy(
    strategy_path: str,
    *,
    symbols: str | list[str] = "AUDUSD",
    start: datetime | None = None,
    end: datetime | None = None,
    report_root: Path | None = None,
    base_config: dict[str, Any] | None = None,
    lot_multiplier: float = 1.0,
    strategy_config_path: Path | None = None,
    parent_nickname: str | None = None,
    parent_metrics: dict[str, Any] | None = None,
    changed_parameters: dict[str, Any] | None = None,
    evaluation_method: str = "BACKTEST",
) -> ValidationResult:
    """Run L5 filters and return a reusable, machine-readable validation result."""

    from scripts import validate_strategy as legacy

    cfg = load_backtest_config()
    resolved_symbols = _resolve_symbols(symbols)
    run_start = start or cfg.default_start
    run_end = end or cfg.default_end
    strategy = legacy.instantiate_strategy(strategy_path, resolved_symbols, base_config, lot_multiplier, config_path=strategy_config_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = report_root or ROOT / "reports"
    report_dir = output_root / f"validation_{strategy.name}_{stamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    if _is_strategy_v0(strategy_path) and len(resolved_symbols) > 1:
        runner = _cached_bar_runner(
            legacy,
            strategy_path,
            resolved_symbols,
            run_start,
            run_end,
            run_start - timedelta(hours=6),
            run_end + timedelta(hours=6),
            strategy_config_path=strategy_config_path,
        )
        full = runner(run_start, run_end, base_config=strategy.config, lot_multiplier=lot_multiplier)
        f1_pass, f1_incidents = legacy.filter1(full)
        f2_pass, windows, f2_metrics = _filter2_cached(
            legacy,
            runner,
            run_start,
            run_end,
            base_config=strategy.config,
            lot_multiplier=lot_multiplier,
        )
        f3_pass, f3_rows = _filter3_cached(legacy, runner, run_start, run_end, strategy.config)
    else:
        full = legacy.run_backtest_for_validation(strategy_path, strategy, resolved_symbols, run_start, run_end, cfg.initial_equity, cfg.data_dir)
        f1_pass, f1_incidents = legacy.filter1(full)
        f2_pass, windows, f2_metrics = legacy.filter2(
            strategy_path,
            resolved_symbols,
            run_start,
            run_end,
            base_config=strategy.config,
            lot_multiplier=lot_multiplier,
        )
        f3_pass, f3_rows = legacy.filter3(strategy_path, resolved_symbols, run_start, run_end, strategy.config)
    plots = legacy.plot_outputs(report_dir, full, windows)
    markdown_path = report_dir / "validation_report.md"
    json_path = report_dir / "validation_result.json"
    d2 = _build_d2_report(
        full=full,
        f1=(f1_pass, f1_incidents),
        windows=windows,
        f2_metrics=f2_metrics,
        f2_pass=f2_pass,
        f3_rows=f3_rows,
        f3_pass=f3_pass,
        plots=plots,
        symbols=resolved_symbols,
        report_dir=report_dir,
        parent_nickname=parent_nickname,
        parent_metrics=parent_metrics,
        changed_parameters=changed_parameters,
        evaluation_method=evaluation_method,
    )
    _write_d2_markdown(markdown_path, d2)

    full_backtest = legacy.result_dict(full)
    result = ValidationResult(
        strategy=strategy.name,
        symbols=resolved_symbols,
        start=run_start.isoformat(),
        end=run_end.isoformat(),
        passed=bool(d2["gate_check"]["passed"] and d2["decision"]["verdict"] not in {"REJECT", "NO-OP"}),
        report_dir=str(report_dir),
        markdown_report=str(markdown_path),
        json_report=str(json_path),
        full_backtest=full_backtest,
        filter1=FilterOutcome(passed=f1_pass, details={"incidents": f1_incidents}),
        filter2=FilterOutcome(passed=f2_pass, details={"metrics": f2_metrics, "windows": [legacy.result_dict(item) for item in windows]}),
        filter3=FilterOutcome(passed=f3_pass, details={"rows": f3_rows}),
        d2=d2,
    )
    _dump_json(json_path, result.model_dump(mode="json"))
    (report_dir / "result.json").write_text(json.dumps(full_backtest, indent=2), encoding="utf-8")
    return result
