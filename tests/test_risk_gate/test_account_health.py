from decimal import Decimal

from trifolium.risk_gate.checks.account_health import check_account_health
from trifolium.risk_gate.types import AccountSnapshot


def test_account_health_accepts_healthy_margin(make_request) -> None:
    passed, reason = check_account_health(make_request())
    assert passed
    assert reason is None


def test_account_health_rejects_low_margin_level(make_request) -> None:
    low = AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("199"))
    passed, reason = check_account_health(make_request(account=low))
    assert not passed
    assert "check_account_health" in reason
