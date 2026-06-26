from datetime import timedelta
from decimal import Decimal

from trifolium.risk_gate.checks.rate_limit import check_rate_limit


def test_rate_limit_allows_five_then_rejects_sixth_in_production(make_request, production_limits) -> None:
    base = make_request()
    for index in range(5):
        request = make_request(timestamp=base.timestamp + timedelta(seconds=index))
        passed, reason = check_rate_limit(request, production_limits)
        assert passed
        assert reason is None
    sixth = make_request(timestamp=base.timestamp + timedelta(seconds=5))
    passed, reason = check_rate_limit(sixth, production_limits)
    assert not passed
    assert "check_rate_limit" in reason


def test_rate_limit_does_not_block_exposure_reducing_close(make_request, production_limits, position_factory) -> None:
    base = make_request()
    for index in range(5):
        request = make_request(timestamp=base.timestamp + timedelta(seconds=index), symbol="EURUSD", side="sell")
        passed, reason = check_rate_limit(request, production_limits)
        assert passed
        assert reason is None

    close_request = make_request(
        timestamp=base.timestamp + timedelta(seconds=5),
        symbol="GBPUSD",
        side="buy",
        lots=Decimal("0.5"),
        existing_positions=[position_factory("GBPUSD", "-0.5", "1.3190")],
    )
    passed, reason = check_rate_limit(close_request, production_limits)

    assert passed
    assert reason is None


def test_rate_limit_does_not_count_exposure_reducing_close(make_request, production_limits, position_factory) -> None:
    base = make_request()
    close_request = make_request(
        symbol="GBPUSD",
        side="buy",
        lots=Decimal("0.5"),
        existing_positions=[position_factory("GBPUSD", "-0.5", "1.3190")],
    )
    passed, reason = check_rate_limit(close_request, production_limits)
    assert passed
    assert reason is None

    for index in range(5):
        request = make_request(timestamp=base.timestamp + timedelta(seconds=index), symbol="EURUSD", side="sell")
        passed, reason = check_rate_limit(request, production_limits)
        assert passed
        assert reason is None
