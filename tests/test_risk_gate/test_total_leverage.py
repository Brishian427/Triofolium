from decimal import Decimal

from trifolium.risk_gate.checks.total_leverage import check_total_leverage


def test_total_leverage_from_zero_allows_small_xau(make_request) -> None:
    request = make_request(
        symbol="XAUUSD",
        lots=Decimal("0.05"),
        price=Decimal("2300"),
        contract_size=Decimal("100"),
        strategy_notional=Decimal("11500"),
    )
    passed, reason = check_total_leverage(request)
    assert passed
    assert reason is None


def test_total_leverage_rejects_existing_high_leverage(make_request, production_limits, position_factory) -> None:
    account = make_request().account.model_copy(update={"equity": Decimal("100000")})
    existing = [position_factory("XAUUSD", "1.74", "2300", "100")]
    request = make_request(
        symbol="XAUUSD",
        lots=Decimal("0.5"),
        price=Decimal("2300"),
        contract_size=Decimal("100"),
        strategy_notional=Decimal("115000"),
        account=account,
        existing_positions=existing,
    )
    passed, reason = check_total_leverage(request, production_limits)
    assert not passed
    assert "check_total_leverage" in reason
