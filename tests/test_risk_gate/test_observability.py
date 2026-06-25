from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from trifolium.risk_gate import observability
from trifolium.risk_gate.state import lock_gate
from trifolium.risk_gate.types import AccountSnapshot, PositionSnapshot


def test_account_state_logger_writes_jsonl(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "account_state.jsonl"
    monkeypatch.setattr(observability, "account_state_log_path", lambda now=None: log_path)
    account = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("1000"), leverage=Decimal("30"))
    positions = [PositionSnapshot(symbol="AUDUSD", signed_lots=Decimal("0.01"), price=Decimal("0.70"), contract_size=Decimal("100000"))]

    observability.log_account_state(account, positions, now=datetime(2026, 6, 24, tzinfo=timezone.utc))

    row = json.loads(log_path.read_text(encoding="utf-8"))
    assert row["level"] == "INFO"
    assert row["margin_level"] == "1000"
    assert row["equity"] == "1000000"
    assert row["leverage"] == "30"
    assert row["open_positions_count"] == 0
    assert row["biggest_single_symbol_exposure"] == "700.0000"
    assert row["currency_decomposition_snapshot"]["AUD"] == "700.0000"
    assert row["currency_decomposition_snapshot"]["USD"] == "-700.0000"


def test_account_state_logger_warns_inside_margin_buffer(monkeypatch, tmp_path, caplog) -> None:
    log_path = tmp_path / "account_state.jsonl"
    monkeypatch.setattr(observability, "account_state_log_path", lambda now=None: log_path)
    account = AccountSnapshot(
        equity=Decimal("1000000"),
        margin_level_pct=Decimal("239"),
        leverage=Decimal("30"),
        open_positions_count=1,
    )
    positions = [
        PositionSnapshot(
            symbol="EURUSD",
            signed_lots=Decimal("0.01"),
            price=Decimal("1.10"),
            contract_size=Decimal("100000"),
        )
    ]

    with caplog.at_level(logging.WARNING, logger="trifolium.risk_gate.observability"):
        observability.log_account_state(account, positions, now=datetime(2026, 6, 24, tzinfo=timezone.utc))

    row = json.loads(log_path.read_text(encoding="utf-8"))
    assert row["level"] == "WARNING"
    assert "within 20% buffer" in row["messages"][0]
    assert "within 20% buffer" in caplog.text


def test_account_state_logger_critical_when_gate_locked(monkeypatch, tmp_path, caplog) -> None:
    log_path = tmp_path / "account_state.jsonl"
    monkeypatch.setattr(observability, "account_state_log_path", lambda now=None: log_path)
    lock_gate("session equity below drawdown floor")
    account = AccountSnapshot(equity=Decimal("900000"), margin_level_pct=Decimal("1000"), leverage=Decimal("30"))

    with caplog.at_level(logging.CRITICAL, logger="trifolium.risk_gate.observability"):
        observability.log_account_state(account, [], now=datetime(2026, 6, 24, tzinfo=timezone.utc))

    row = json.loads(log_path.read_text(encoding="utf-8"))
    assert row["level"] == "CRITICAL"
    assert row["gate_state"]["locked"] is True
    assert row["gate_state"]["lock_reason"] == "session equity below drawdown floor"
    assert "gate locked" in caplog.text
