from decimal import Decimal

from trifolium.risk_gate.checks.lot_size import check_lot_size


def test_lot_size_accepts_calibration_trade(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.01")))
    assert passed
    assert reason is None


def test_lot_size_rejects_oversized_lot(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.51")))
    assert not passed
    assert "check_lot_size" in reason


def test_lot_size_allows_principal_fx_conviction_cap(make_request) -> None:
    passed, reason = check_lot_size(make_request(lots=Decimal("0.5")))

    assert passed
    assert reason is None


def test_lot_size_allows_usdcad_and_usdjpy_half_lot(make_request) -> None:
    for symbol in ["USDCAD", "USDJPY"]:
        passed, reason = check_lot_size(make_request(symbol=symbol, lots=Decimal("0.5")))
        assert passed is True
        assert reason is None

        too_large, too_large_reason = check_lot_size(make_request(symbol=symbol, lots=Decimal("0.51")))
        assert too_large is False
        assert symbol in too_large_reason


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
