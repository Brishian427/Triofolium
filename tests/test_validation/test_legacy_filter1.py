from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from scripts.validate_strategy import filter1
from trifolium.backtest.types import BacktestResult, DataQualityStats


def _result(risk_discipline: str) -> BacktestResult:
    now = datetime(2026, 5, 11, tzinfo=timezone.utc)
    return BacktestResult(
        strategy_name="strategy_v0",
        symbols=["AUDUSD"],
        start=now,
        end=now,
        initial_equity=Decimal("1000000"),
        final_equity=Decimal("1000000"),
        total_return=Decimal("0"),
        max_drawdown=Decimal("0"),
        sharpe=None,
        projected_risk_discipline=Decimal(risk_discipline),
        trade_count=0,
        trades=[],
        equity_curve=[],
        data_quality=DataQualityStats(),
        stop_out_events=[],
        risk_events=[],
    )


def test_filter1_accepts_risk_discipline_90():
    passed, incidents = filter1(_result("90"))
    assert passed is True
    assert incidents == []


def test_filter1_rejects_risk_discipline_below_90():
    passed, incidents = filter1(_result("89"))
    assert passed is False
    assert incidents == ["projected risk discipline below 90: 89"]
