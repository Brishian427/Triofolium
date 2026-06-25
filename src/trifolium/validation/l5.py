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


def _resolve_symbols(symbols: str | list[str]) -> list[str]:
    if isinstance(symbols, list):
        return symbols
    if symbols == "all_tradable":
        return load_strategy_v0_config().tradable_symbols
    return [item.strip() for item in symbols.split(",") if item.strip()]


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


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
    legacy.write_report(markdown_path, full, (f1_pass, f1_incidents), windows, f2_metrics, f2_pass, f3_rows, f3_pass, plots)

    full_backtest = legacy.result_dict(full)
    result = ValidationResult(
        strategy=strategy.name,
        symbols=resolved_symbols,
        start=run_start.isoformat(),
        end=run_end.isoformat(),
        passed=f1_pass and f2_pass and f3_pass,
        report_dir=str(report_dir),
        markdown_report=str(markdown_path),
        json_report=str(json_path),
        full_backtest=full_backtest,
        filter1=FilterOutcome(passed=f1_pass, details={"incidents": f1_incidents}),
        filter2=FilterOutcome(passed=f2_pass, details={"metrics": f2_metrics, "windows": [legacy.result_dict(item) for item in windows]}),
        filter3=FilterOutcome(passed=f3_pass, details={"rows": f3_rows}),
    )
    _dump_json(json_path, result.model_dump(mode="json"))
    (report_dir / "result.json").write_text(json.dumps(full_backtest, indent=2), encoding="utf-8")
    return result
