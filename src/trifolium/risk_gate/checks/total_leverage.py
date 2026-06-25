"""Risk Gate check: projected gross notional leverage cap."""

from __future__ import annotations

from decimal import Decimal

from trifolium.risk_gate.checks.numeric_consistency import recompute_notional
from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def _position_notional(position: object) -> Decimal:
    return abs(position.signed_lots * position.contract_size * position.price)


def check_total_leverage(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Return whether projected gross notional stays under active leverage cap."""

    if request.account is None:
        return False, "check_total_leverage: account snapshot is required"
    if request.account.equity <= 0:
        return False, f"check_total_leverage: equity {request.account.equity} is non-positive"
    existing = sum((_position_notional(position) for position in request.existing_positions), Decimal("0"))
    projected = existing + recompute_notional(request)
    max_allowed = limits.active.max_total_leverage * request.account.equity
    if projected <= max_allowed:
        return True, None
    return False, f"check_total_leverage: projected notional {projected} exceeds max {max_allowed}"
