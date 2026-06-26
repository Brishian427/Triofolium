from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from scripts import live_profit_harvester as harvester
from trifolium.risk_gate.types import PositionSnapshot


def test_reentry_buy_waits_for_cooldown_and_price_drop():
    target = harvester.HarvestTarget("USDJPY", "buy", Decimal("0.5"), Decimal("0.03"))
    state = harvester.HarvestState(
        last_exit_price=Decimal("160.00"),
        last_exit_time=datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc),
    )

    assert not harvester._reentry_allowed(target, state, Decimal("159.90"), state.last_exit_time + timedelta(seconds=299), 300)
    assert not harvester._reentry_allowed(target, state, Decimal("159.98"), state.last_exit_time + timedelta(seconds=300), 300)
    assert harvester._reentry_allowed(target, state, Decimal("159.97"), state.last_exit_time + timedelta(seconds=300), 300)


def test_reentry_sell_waits_for_cooldown_and_price_rebound():
    target = harvester.HarvestTarget("AUDUSD", "sell", Decimal("0.5"), Decimal("0.0003"))
    state = harvester.HarvestState(
        last_exit_price=Decimal("0.6500"),
        last_exit_time=datetime(2026, 6, 26, 0, 0, tzinfo=timezone.utc),
    )

    assert not harvester._reentry_allowed(target, state, Decimal("0.6502"), state.last_exit_time + timedelta(seconds=300), 300)
    assert harvester._reentry_allowed(target, state, Decimal("0.6503"), state.last_exit_time + timedelta(seconds=300), 300)


def test_chunk_lots_uses_cap_sized_pieces():
    assert harvester._chunk_lots(Decimal("1.10"), Decimal("0.5")) == [Decimal("0.5"), Decimal("0.5"), Decimal("0.10")]


def test_xauusd_target_is_bearish_by_config():
    config = harvester.load_harvest_config()
    xauusd = next(target for target in config.targets if target.symbol == "XAUUSD")

    assert xauusd.side == "buy"


def test_harvester_position_detection_requires_comment_prefix():
    managed = PositionSnapshot(
        symbol="XAUUSD",
        signed_lots=Decimal("0.1"),
        price=Decimal("4075"),
        contract_size=Decimal("100"),
        comment="profit_harvester_entry",
    )
    manual_empty = PositionSnapshot(
        symbol="XAUUSD",
        signed_lots=Decimal("0.1"),
        price=Decimal("4075"),
        contract_size=Decimal("100"),
        comment="",
    )
    manual_other = PositionSnapshot(
        symbol="XAUUSD",
        signed_lots=Decimal("0.1"),
        price=Decimal("4075"),
        contract_size=Decimal("100"),
        comment="manual",
    )

    assert harvester._is_harvester_position(managed)
    assert not harvester._is_harvester_position(manual_empty)
    assert not harvester._is_harvester_position(manual_other)


def test_harvester_position_by_symbol_excludes_manual_positions():
    managed = PositionSnapshot(
        symbol="GBPUSD",
        signed_lots=Decimal("0.5"),
        price=Decimal("1.32"),
        contract_size=Decimal("100000"),
        comment="profit_harvester_entry",
    )
    manual = PositionSnapshot(
        symbol="XAUUSD",
        signed_lots=Decimal("-0.5"),
        price=Decimal("4075"),
        contract_size=Decimal("100"),
        comment="manual",
    )

    by_symbol = harvester._harvester_position_by_symbol([managed, manual])

    assert by_symbol == {"GBPUSD": managed}
