from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS
from trifolium.risk_gate.checks.direction_sanity import check_direction_sanity


def test_direction_sanity_warns_when_adding_same_direction(make_request, position_factory, caplog) -> None:
    existing = [position_factory("GBPUSD", "0.05", "0.7000")]
    request = make_request(symbol="GBPUSD", lots=Decimal("0.05"), existing_positions=existing)
    passed, reason = check_direction_sanity(request)
    assert passed
    assert reason is None
    assert "adding" in caplog.text
    assert "GBPUSD" in caplog.text


def test_direction_sanity_rejects_audusd_buy_by_policy(make_request) -> None:
    request = make_request(symbol="AUDUSD", side="buy")

    passed, reason = check_direction_sanity(request)

    assert passed is False
    assert "AUDUSD buy disallowed" in reason


def test_direction_sanity_allows_audusd_sell_by_policy(make_request) -> None:
    request = make_request(symbol="AUDUSD", side="sell")

    passed, reason = check_direction_sanity(request)

    assert passed is True
    assert reason is None


def test_direction_sanity_allows_audusd_buy_to_reduce_short(make_request, position_factory) -> None:
    request = make_request(
        symbol="AUDUSD",
        side="buy",
        lots=Decimal("0.05"),
        existing_positions=[position_factory("AUDUSD", "-0.10", "0.6900")],
    )

    passed, reason = check_direction_sanity(request)

    assert passed is True
    assert reason is None


def test_direction_sanity_rejects_audusd_buy_that_flips_short_long(make_request, position_factory) -> None:
    request = make_request(
        symbol="AUDUSD",
        side="buy",
        lots=Decimal("0.11"),
        existing_positions=[position_factory("AUDUSD", "-0.10", "0.6900")],
    )

    passed, reason = check_direction_sanity(request)

    assert passed is False
    assert "disallowed except to reduce existing exposure" in reason


def test_direction_sanity_does_not_restrict_usdcad_or_usdjpy(make_request) -> None:
    assert RISK_LIMITS.symbol_overrides["USDCAD"].max_lot_per_order == Decimal("0.5")
    assert RISK_LIMITS.symbol_overrides["USDJPY"].max_lot_per_order == Decimal("0.5")

    for symbol in ["USDCAD", "USDJPY"]:
        passed, reason = check_direction_sanity(make_request(symbol=symbol, side="buy"))
        assert passed is True
        assert reason is None
