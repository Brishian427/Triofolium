from decimal import Decimal

from trifolium.risk_gate.checks.numeric_consistency import check_numeric_consistency


def test_numeric_consistency_accepts_matching_notional(make_request) -> None:
    passed, reason = check_numeric_consistency(make_request())
    assert passed
    assert reason is None


def test_numeric_consistency_rejects_fabricated_mismatch(make_request) -> None:
    request = make_request(lots=Decimal("0.1"), price=Decimal("1"), strategy_notional=Decimal("1000"))
    passed, reason = check_numeric_consistency(request)
    assert not passed
    assert "check_numeric_consistency" in reason
