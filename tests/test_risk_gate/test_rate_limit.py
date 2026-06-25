from datetime import timedelta

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
