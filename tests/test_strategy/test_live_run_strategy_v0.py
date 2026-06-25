from __future__ import annotations

from decimal import Decimal

import pytest

from scripts import live_run_strategy_v0 as live
from trifolium.risk_gate.config import RiskLimits
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, OrderResult, PositionSnapshot


def _limits(mode: str) -> RiskLimits:
    return RiskLimits.model_validate(
        {
            "mode": mode,
            "calibration": {
                "max_lot_per_order": "0.01",
                "max_total_leverage": "1",
                "max_single_symbol_pct": "0.1",
                "numeric_tolerance_abs": "0.01",
                "numeric_tolerance_rel": "0.01",
                "max_orders_per_minute": 1,
            },
            "production": {
                "max_lot_per_order": "0.01",
                "max_total_leverage": "1",
                "max_single_symbol_pct": "0.1",
                "numeric_tolerance_abs": "0.01",
                "numeric_tolerance_rel": "0.01",
                "max_orders_per_minute": 1,
            },
            "symbol_overrides": {},
            "hard_floors": {"min_margin_level_pct": "200", "max_drawdown_session_pct": "5"},
        }
    )


def test_readiness_requires_production_mode():
    with pytest.raises(RuntimeError, match="production mode"):
        live.assert_risk_gate_production(_limits("calibration"))
    live.assert_risk_gate_production(_limits("production"))


def test_readiness_rejects_legacy_audusd_position():
    with pytest.raises(RuntimeError, match="legacy AUDUSD"):
        live.assert_legacy_audusd_flat([{"ticket": 46678, "symbol": "AUDUSD"}])
    with pytest.raises(RuntimeError, match="legacy AUDUSD"):
        live.assert_legacy_audusd_flat([{"ticket": 1, "symbol": "AUDUSD"}])
    live.assert_legacy_audusd_flat([{"ticket": 2, "symbol": "EURUSD"}])


def test_margin_monitor_triggers_emergency_flatten(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("49"))
    position = PositionSnapshot(symbol="EURUSD", signed_lots=Decimal("0.01"), price=Decimal("1.10"), contract_size=Decimal("100000"))
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    results = live.check_margin_or_flatten(account, [position], submitter=submitter)

    assert len(results) == 1
    assert seen[0].side == "sell"
    assert seen[0].comment == "strategy_v0_emergency_flatten"


def test_strategy_event_logging_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    path = live.log_strategy_event("prediction", {"symbol": "EURUSD", "signal": Decimal("0.1")})
    text = path.read_text(encoding="utf-8")
    assert '"event": "prediction"' in text
    assert '"signal": "0.1"' in text
