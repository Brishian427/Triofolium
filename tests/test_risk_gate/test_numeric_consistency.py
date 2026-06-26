from decimal import Decimal

from trifolium.risk_gate.checks.numeric_consistency import check_numeric_consistency, estimate_signed_account_notional, recompute_notional


def test_numeric_consistency_accepts_matching_notional(make_request) -> None:
    passed, reason = check_numeric_consistency(make_request())
    assert passed
    assert reason is None


def test_signed_notional_preserves_side_for_netting_checks() -> None:
    assert estimate_signed_account_notional("GBPUSD", Decimal("-0.5"), Decimal("100000"), Decimal("1.32")) == Decimal("-66000.000")
    assert estimate_signed_account_notional("USDJPY", Decimal("0.5"), Decimal("100000"), Decimal("161.824")) == Decimal("50000.0")


def test_numeric_consistency_rejects_fabricated_mismatch(make_request) -> None:
    request = make_request(lots=Decimal("0.1"), price=Decimal("1"), strategy_notional=Decimal("1000"))
    passed, reason = check_numeric_consistency(request)
    assert not passed
    assert "check_numeric_consistency" in reason


def test_usd_base_pair_notional_does_not_multiply_by_quote_price(make_request) -> None:
    request = make_request(
        symbol="USDJPY",
        lots=Decimal("0.5"),
        price=Decimal("161.824"),
        contract_size=Decimal("100000"),
        strategy_notional=Decimal("50000"),
    )

    assert recompute_notional(request) == Decimal("50000")
    passed, reason = check_numeric_consistency(request)

    assert passed
    assert reason is None
