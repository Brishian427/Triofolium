from decimal import Decimal

from trifolium.risk_gate.checks.single_symbol_concentration import check_single_symbol_concentration


def test_single_symbol_concentration_allows_first_order(make_request, production_limits) -> None:
    passed, reason = check_single_symbol_concentration(make_request(), production_limits)
    assert passed
    assert reason is None


def test_single_symbol_concentration_rejects_dominant_symbol(make_request, production_limits, position_factory) -> None:
    existing = [position_factory("EURUSD", "1.0", "1.0")]
    request = make_request(
        symbol="AUDUSD",
        lots=Decimal("3.0"),
        price=Decimal("1.0"),
        contract_size=Decimal("100000"),
        strategy_notional=Decimal("300000"),
        existing_positions=existing,
    )
    passed, reason = check_single_symbol_concentration(request, production_limits)
    assert not passed
    assert "check_single_symbol_concentration" in reason
