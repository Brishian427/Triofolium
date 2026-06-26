from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trifolium.backtest.types import BacktestResult, DataQualityStats, EquityPoint, Trade
from trifolium.validation.l5 import _build_d2_report
from trifolium.validation import validate_strategy


def test_l5_callable_returns_machine_readable_result(tmp_path):
    result = validate_strategy(
        "do_nothing",
        symbols=["AUDUSD"],
        start=datetime(2026, 5, 11, tzinfo=timezone.utc),
        end=datetime(2026, 5, 12, tzinfo=timezone.utc),
        report_root=tmp_path,
    )

    assert result.strategy == "do_nothing"
    assert result.passed is False
    assert result.filter1.passed is True
    assert result.filter2.passed is True
    assert result.filter3.passed is True
    assert list(result.d2)[:9] == [
        "identity",
        "gate_check",
        "primary_objective",
        "secondary_metrics",
        "binding_check",
        "robustness",
        "regime_consistency",
        "failure_modes_observed",
        "decision",
    ]
    assert result.d2["gate_check"]["passed"] is False
    assert result.d2["decision"]["verdict"] == "REJECT"
    assert result.markdown_report.endswith("validation_report.md")
    assert result.json_report.endswith("validation_result.json")
    markdown = __import__("pathlib").Path(result.markdown_report).read_text(encoding="utf-8")
    expected_headings = [
        "## Section 1 - Identity",
        "## Section 2 - Gate Check",
        "## Section 3 - Primary Objective",
        "## Section 4 - Secondary Metrics",
        "## Section 5 - Binding Check",
        "## Section 6 - Robustness",
        "## Section 7 - Regime Consistency",
        "## Section 8 - Failure Modes Observed",
        "## Section 9 - Decision",
    ]
    assert [heading for heading in expected_headings if heading in markdown] == expected_headings


def test_d2_does_not_accept_non_positive_return_without_parent(tmp_path):
    start = datetime(2026, 5, 11, tzinfo=timezone.utc)
    trades = [
        Trade(
            timestamp=start + timedelta(minutes=15 * index),
            symbol="AUDUSD",
            side="buy",
            lots=Decimal("0.01"),
            price=Decimal("1.0"),
            realized_pnl=Decimal("1") if index % 2 == 0 else Decimal("-1"),
            equity_after=Decimal("999999"),
            tag="test",
        )
        for index in range(30)
    ]
    full = BacktestResult(
        strategy_name="strategy_v0",
        symbols=["AUDUSD"],
        start=start,
        end=start + timedelta(hours=8),
        initial_equity=Decimal("1000000"),
        final_equity=Decimal("999999"),
        total_return=Decimal("-0.000001"),
        max_drawdown=Decimal("0.001"),
        sharpe=Decimal("-0.1"),
        projected_risk_discipline=Decimal("100"),
        trade_count=30,
        trades=trades,
        equity_curve=[
            EquityPoint(timestamp=start, equity=Decimal("1000000"), balance=Decimal("1000000"), margin_used=Decimal("0"), margin_level=None),
            EquityPoint(timestamp=start + timedelta(hours=8), equity=Decimal("999999"), balance=Decimal("999999"), margin_used=Decimal("0"), margin_level=None),
        ],
        data_quality=DataQualityStats(),
        stop_out_events=[],
        risk_events=[],
    )

    d2 = _build_d2_report(
        full=full,
        f1=(True, []),
        windows=[full],
        f2_metrics={"worst_dd": 0.001, "cv": 0.0, "negative_fraction": 0.0},
        f2_pass=True,
        f3_rows=[{"kind": "parameter", "case": "1.0", "filter2": True}],
        f3_pass=True,
        plots=(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"),
        symbols=["AUDUSD"],
        report_dir=tmp_path,
    )

    assert d2["gate_check"]["passed"] is True
    assert d2["robustness"]["verdict"] == "ROBUST"
    assert d2["decision"]["verdict"] == "KEEP v_N-1"


def test_d2_risk_discipline_gate_accepts_90(tmp_path):
    start = datetime(2026, 5, 11, tzinfo=timezone.utc)
    trades = [
        Trade(
            timestamp=start + timedelta(minutes=15 * index),
            symbol="AUDUSD",
            side="buy",
            lots=Decimal("0.01"),
            price=Decimal("1.0"),
            realized_pnl=Decimal("1"),
            equity_after=Decimal("1000001"),
            tag="test",
        )
        for index in range(30)
    ]
    full = BacktestResult(
        strategy_name="strategy_v0",
        symbols=["AUDUSD"],
        start=start,
        end=start + timedelta(hours=8),
        initial_equity=Decimal("1000000"),
        final_equity=Decimal("1000010"),
        total_return=Decimal("0.00001"),
        max_drawdown=Decimal("0.001"),
        sharpe=Decimal("0.1"),
        projected_risk_discipline=Decimal("90"),
        trade_count=30,
        trades=trades,
        equity_curve=[
            EquityPoint(timestamp=start, equity=Decimal("1000000"), balance=Decimal("1000000"), margin_used=Decimal("0"), margin_level=None),
            EquityPoint(timestamp=start + timedelta(hours=8), equity=Decimal("1000010"), balance=Decimal("1000010"), margin_used=Decimal("0"), margin_level=None),
        ],
        data_quality=DataQualityStats(),
        stop_out_events=[],
        risk_events=[],
    )

    d2 = _build_d2_report(
        full=full,
        f1=(True, []),
        windows=[full],
        f2_metrics={"worst_dd": 0.001, "cv": 0.0, "negative_fraction": 0.0},
        f2_pass=True,
        f3_rows=[{"kind": "parameter", "case": "1.0", "filter2": True}],
        f3_pass=True,
        plots=(tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"),
        symbols=["AUDUSD"],
        report_dir=tmp_path,
    )

    gates = {gate["gate"]: gate for gate in d2["gate_check"]["gates"]}
    assert gates["Risk Discipline"]["threshold"] == ">= 90"
    assert gates["Risk Discipline"]["passed"] is True
    assert d2["gate_check"]["passed"] is True
