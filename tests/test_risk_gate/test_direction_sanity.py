from decimal import Decimal

from trifolium.risk_gate.checks.direction_sanity import check_direction_sanity


def test_direction_sanity_warns_when_adding_same_direction(make_request, position_factory, caplog) -> None:
    existing = [position_factory("AUDUSD", "0.05", "0.7000")]
    request = make_request(lots=Decimal("0.05"), existing_positions=existing)
    passed, reason = check_direction_sanity(request)
    assert passed
    assert reason is None
    assert "adding" in caplog.text
    assert "AUDUSD" in caplog.text
