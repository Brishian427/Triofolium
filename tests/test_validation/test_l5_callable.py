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
    assert result.passed is True
    assert result.filter1.passed is True
    assert result.filter2.passed is True
    assert result.filter3.passed is True
    assert result.markdown_report.endswith("validation_report.md")
    assert result.json_report.endswith("validation_result.json")
