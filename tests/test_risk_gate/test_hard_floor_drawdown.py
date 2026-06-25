from decimal import Decimal

from trifolium.risk_gate.checks.hard_floor_drawdown import check_hard_floor_drawdown
from trifolium.risk_gate.types import AccountSnapshot


def test_hard_floor_drawdown_locks_after_session_drop(make_request) -> None:
    peak = AccountSnapshot(equity=Decimal("1000"), margin_level_pct=Decimal("1000"))
    passed, reason = check_hard_floor_drawdown(make_request(account=peak))
    assert passed
    assert reason is None

    dropped = AccountSnapshot(equity=Decimal("940"), margin_level_pct=Decimal("1000"))
    passed, reason = check_hard_floor_drawdown(make_request(account=dropped))
    assert not passed
    assert "check_hard_floor_drawdown" in reason

    recovered = AccountSnapshot(equity=Decimal("1000"), margin_level_pct=Decimal("1000"))
    passed, reason = check_hard_floor_drawdown(make_request(account=recovered))
    assert not passed
    assert "gate locked" in reason
