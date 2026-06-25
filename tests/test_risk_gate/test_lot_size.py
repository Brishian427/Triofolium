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


def test_lot_size_allows_principal_fx_conviction_cap(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.14")))

    assert passed
    assert reason is None


def test_lot_size_keeps_metal_symbol_overrides(make_request) -> None:
    xau_passed, xau_reason = check_lot_size(
        make_request(symbol="XAUUSD", lots=Decimal("0.11"), price=Decimal("2400"), contract_size=Decimal("100"))
    )
    xag_passed, xag_reason = check_lot_size(
        make_request(symbol="XAGUSD", lots=Decimal("0.02"), price=Decimal("30"), contract_size=Decimal("5000"))
    )

    assert not xau_passed
    assert "XAUUSD" in xau_reason
    assert not xag_passed
    assert "XAGUSD" in xag_reason
