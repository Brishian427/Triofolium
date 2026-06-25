"""Risk Gate check: account margin health hard floor."""

from __future__ import annotations

from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest


def check_account_health(
    request: OrderRequest,
    limits: RiskLimits = RISK_LIMITS,
    account: AccountSnapshot | None = None,
) -> tuple[bool, str | None]:
    """Fail if margin level is below the hard floor."""

    snapshot = account or request.account
    if snapshot is None:
        return False, "check_account_health: account snapshot is required"
    if snapshot.margin_level_pct is None:
        return False, "check_account_health: margin_level_pct is unavailable"
    floor = limits.hard_floors.min_margin_level_pct
    if snapshot.margin_level_pct < floor:
        return False, f"check_account_health: margin level {snapshot.margin_level_pct}% below floor {floor}%"
    if snapshot.equity <= Decimal("0"):
        return False, f"check_account_health: equity {snapshot.equity} is non-positive"
    return True, None
