from decimal import Decimal

from trifolium.risk_gate.checks.lot_size import check_lot_size


def test_lot_size_accepts_calibration_trade(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.01")))
    assert passed
    assert reason is None


def test_lot_size_rejects_oversized_lot(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.5")))
    assert not passed
    assert "check_lot_size" in reason
