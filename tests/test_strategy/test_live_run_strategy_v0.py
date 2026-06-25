from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def test_margin_zero_with_no_positions_does_not_halt(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("0"))
    state = live.LiveRiskState.from_account(account)
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, [], state, submitter=submitter)

    assert not state.halted
    assert seen == []


def test_single_instrument_loss_closes_only_that_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("500"))
    positions = [
        PositionSnapshot(
            symbol="EURUSD",
            signed_lots=Decimal("0.01"),
            price=Decimal("1.10"),
            contract_size=Decimal("100000"),
            unrealized_pnl=Decimal("-201"),
        ),
        PositionSnapshot(
            symbol="GBPUSD",
            signed_lots=Decimal("0.01"),
            price=Decimal("1.25"),
            contract_size=Decimal("100000"),
            unrealized_pnl=Decimal("5"),
        ),
    ]
    state = live.LiveRiskState.from_account(account)
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, positions, state, submitter=submitter)

    assert not state.halted
    assert [request.symbol for request in seen] == ["EURUSD"]


def test_total_unrealized_loss_flattens_all_and_halts(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("500"))
    positions = [
        PositionSnapshot(
            symbol="EURUSD",
            signed_lots=Decimal("0.01"),
            price=Decimal("1.10"),
            contract_size=Decimal("100000"),
            unrealized_pnl=Decimal("-250"),
        ),
        PositionSnapshot(
            symbol="GBPUSD",
            signed_lots=Decimal("-0.01"),
            price=Decimal("1.25"),
            contract_size=Decimal("100000"),
            unrealized_pnl=Decimal("-260"),
        ),
    ]
    state = live.LiveRiskState.from_account(account)
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, positions, state, submitter=submitter)

    assert state.halted
    assert state.halt_reason == "total_unrealized_pnl_below_-500"
    assert {request.symbol for request in seen} == {"EURUSD", "GBPUSD"}


def test_session_drawdown_flattens_all_and_halts(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("940000"), margin_level_pct=Decimal("500"))
    position = PositionSnapshot(
        symbol="EURUSD",
        signed_lots=Decimal("0.01"),
        price=Decimal("1.10"),
        contract_size=Decimal("100000"),
    )
    state = live.LiveRiskState(session_start_equity=Decimal("990000"), session_peak_equity=Decimal("1000000"))
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, [position], state, submitter=submitter)

    assert state.halted
    assert state.halt_reason == "session_drawdown_gt_5_pct"
    assert len(seen) == 1


def test_session_total_loss_flattens_all_and_halts(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("998999"), margin_level_pct=Decimal("500"))
    position = PositionSnapshot(
        symbol="EURUSD",
        signed_lots=Decimal("0.01"),
        price=Decimal("1.10"),
        contract_size=Decimal("100000"),
    )
    state = live.LiveRiskState(session_start_equity=Decimal("1000000"), session_peak_equity=Decimal("1000000"))
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, [position], state, submitter=submitter)

    assert state.halted
    assert state.halt_reason == "session_loss_ge_1000"
    assert len(seen) == 1


def test_trade_count_anomaly_flattens_all_and_halts(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("500"))
    position = PositionSnapshot(
        symbol="EURUSD",
        signed_lots=Decimal("0.01"),
        price=Decimal("1.10"),
        contract_size=Decimal("100000"),
    )
    state = live.LiveRiskState.from_account(account)
    for offset in range(101):
        state.record_trade(now - timedelta(seconds=offset))
    seen: list[OrderRequest] = []

    def submitter(request: OrderRequest) -> OrderResult:
        seen.append(request)
        return OrderResult(status="submitted", request=request)

    live.apply_hard_kills(account, [position], state, submitter=submitter, now=now)

    assert state.halted
    assert state.halt_reason == "trade_count_gt_100_in_30m"
    assert len(seen) == 1


def test_hard_kill_status_lists_per_trade_volume_cap():
    limits = _limits("production")
    status = live.hard_kill_armed_status(limits)

    assert status["per_trade_volume_cap"] == Decimal("0.01")
    assert status["trade_count_anomaly"]["count"] == 100


def test_initialize_live_risk_state_can_preserve_original_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    account = AccountSnapshot(equity=Decimal("999990"), margin_level_pct=Decimal("0"))

    state = live.initialize_live_risk_state(account, session_start_equity=Decimal("999988.39"))

    assert state.session_start_equity == Decimal("999988.39")
    assert state.session_peak_equity == Decimal("999990")
    text = next((tmp_path / "logs").glob("live_run_*.jsonl")).read_text(encoding="utf-8")
    assert '"baseline_source": "cli_override"' in text
    assert '"session_loss_floor": "998988.39"' in text


def test_strategy_event_logging_writes_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    path = live.log_strategy_event("prediction", {"symbol": "EURUSD", "signal": Decimal("0.1")})
    text = path.read_text(encoding="utf-8")
    assert '"event": "prediction"' in text
    assert '"signal": "0.1"' in text
