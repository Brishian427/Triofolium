"""Risk Gate check: lock gate after session drawdown hard floor breach."""

from __future__ import annotations

from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.state import STATE, lock_gate, update_session_peak
from trifolium.risk_gate.types import OrderRequest


def check_hard_floor_drawdown(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Track session peak equity and lock the gate after a hard drawdown breach."""

    if STATE.locked:
        return False, f"check_hard_floor_drawdown: gate locked: {STATE.lock_reason}"
    if request.account is None:
        return False, "check_hard_floor_drawdown: account snapshot is required"
    equity = request.account.equity
    update_session_peak(equity)
    peak = STATE.session_peak_equity
    if peak is None or peak <= 0:
        return True, None
    breach_ratio = Decimal("1") - (limits.hard_floors.max_drawdown_session_pct / Decimal("100"))
    floor_equity = peak * breach_ratio
    if equity < floor_equity:
        reason = f"session equity {equity} below drawdown floor {floor_equity} from peak {peak}"
        lock_gate(reason)
        return False, f"check_hard_floor_drawdown: {reason}"
    return True, None
