from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from scripts import live_profit_harvester as harvester


def test_harvester_state_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(harvester, "ROOT", tmp_path)
    states = {
        "EURUSD": harvester.HarvestState(
            last_exit_price=Decimal("1.13643"),
            last_exit_time=datetime(2026, 6, 26, 0, 42, 4, tzinfo=timezone.utc),
            cycles_completed=1,
        )
    }

    harvester.save_states(states)
    restored = harvester.load_states([harvester.HarvestTarget("EURUSD", "sell", Decimal("0.5"), Decimal("0.0003"))])

    assert restored["EURUSD"].last_exit_price == Decimal("1.13643")
    assert restored["EURUSD"].last_exit_time == datetime(2026, 6, 26, 0, 42, 4, tzinfo=timezone.utc)
    assert restored["EURUSD"].cycles_completed == 1


def test_heartbeat_writes_timestamp(monkeypatch, tmp_path):
    monkeypatch.setattr(harvester, "ROOT", tmp_path)

    harvester.write_heartbeat({"equity": Decimal("1000")})

    text = (tmp_path / "logs" / "profit_harvester_heartbeat.json").read_text(encoding="utf-8")
    assert "timestamp" in text
    assert '"equity": "1000"' in text
