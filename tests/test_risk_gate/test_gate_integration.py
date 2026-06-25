from __future__ import annotations

import json
from decimal import Decimal

from trifolium.adapter.types import OrderExecutionResult
from trifolium.risk_gate import gate
from trifolium.risk_gate.types import OrderRequest


def test_submit_order_rejects_first_failed_check_without_sender(make_request, monkeypatch) -> None:
    calls = {"sender": 0}

    def fake_sender(request: OrderRequest) -> OrderExecutionResult:
        calls["sender"] += 1
        return OrderExecutionResult(status="filled")

    monkeypatch.setattr(gate, "send_order_to_mt5", fake_sender)
    result = gate.submit_order(make_request(lots=Decimal("0.5")))
    assert result.status == "rejected"
    assert result.reason.startswith("check_lot_size:")
    assert calls["sender"] == 0


def test_submit_order_fails_closed_on_check_exception(make_request, monkeypatch) -> None:
    calls = {"sender": 0}

    def exploding_check(request: OrderRequest) -> tuple[bool, str | None]:
        raise RuntimeError("boom")

    def fake_sender(request: OrderRequest) -> OrderExecutionResult:
        calls["sender"] += 1
        return OrderExecutionResult(status="filled")

    monkeypatch.setattr(gate, "CHECKS", [("exploding_check", exploding_check)])
    monkeypatch.setattr(gate, "send_order_to_mt5", fake_sender)
    result = gate.submit_order(make_request())
    assert result.status == "rejected"
    assert result.reason.startswith("check_error: exploding_check: RuntimeError: boom")
    assert calls["sender"] == 0


def test_submit_order_calls_sender_after_all_checks_pass(make_request, monkeypatch) -> None:
    calls = {"sender": 0}

    def fake_sender(request: OrderRequest) -> OrderExecutionResult:
        calls["sender"] += 1
        return OrderExecutionResult(status="filled", retcode=10009, order=1, deal=2, volume=request.lots, price=request.price)

    monkeypatch.setattr(gate, "send_order_to_mt5", fake_sender)
    result = gate.submit_order(make_request())
    assert result.status == "filled"
    assert result.mt5_response["retcode"] == 10009
    assert calls["sender"] == 1
    assert all(check.passed for check in result.checks)


def test_submit_order_propagates_sender_error(make_request, monkeypatch) -> None:
    def fake_sender(request: OrderRequest) -> OrderExecutionResult:
        return OrderExecutionResult(status="error", retcode=500, comment="mock failure")

    monkeypatch.setattr(gate, "send_order_to_mt5", fake_sender)
    result = gate.submit_order(make_request())
    assert result.status == "error"
    assert result.reason == "mock failure"
    assert result.mt5_response["retcode"] == 500


def test_submit_order_logs_rejections_and_passes(make_request, monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "risk_gate_test.jsonl"

    def fake_log_path(now=None):
        return log_file

    def fake_sender(request: OrderRequest) -> OrderExecutionResult:
        return OrderExecutionResult(status="filled", retcode=10009, order=10, deal=11, volume=request.lots, price=request.price)

    monkeypatch.setattr("trifolium.risk_gate.logging.risk_gate_log_path", fake_log_path)
    monkeypatch.setattr(gate, "send_order_to_mt5", fake_sender)
    rejected = gate.submit_order(make_request(lots=Decimal("0.5")))
    accepted = gate.submit_order(make_request())
    assert rejected.status == "rejected"
    assert accepted.status == "filled"
    rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert [row["final_status"] for row in rows] == ["rejected", "filled"]
    assert rows[0]["reason"].startswith("check_lot_size:")
    assert rows[1]["mt5_response"]["retcode"] == 10009
