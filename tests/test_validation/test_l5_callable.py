from __future__ import annotations

from datetime import datetime, timezone

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
