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


def test_single_symbol_concentration_allows_profit_harvester_entry(make_request, production_limits, position_factory) -> None:
    existing = [position_factory("USDJPY", "0.5", "161.5")]
    request = make_request(
        symbol="GBPUSD",
        side="sell",
        lots=Decimal("0.5"),
        price=Decimal("1.32"),
        contract_size=Decimal("100000"),
        strategy_notional=Decimal("66000"),
        existing_positions=existing,
        comment="profit_harvester_entry",
    )

    passed, reason = check_single_symbol_concentration(request, production_limits)

    assert passed
    assert reason is None


def test_single_symbol_concentration_allows_reducing_position(make_request, production_limits, position_factory) -> None:
    existing = [position_factory("EURUSD", "-0.5", "1.13", "100000")]
    request = make_request(
        symbol="EURUSD",
        side="buy",
        lots=Decimal("0.5"),
        price=Decimal("1.13"),
        contract_size=Decimal("100000"),
        strategy_notional=Decimal("56500"),
        existing_positions=existing,
    )

    passed, reason = check_single_symbol_concentration(request, production_limits)

    assert passed
    assert reason is None
