"""Risk Gate check: warn on adding to same-direction exposure."""

from __future__ import annotations

import logging
from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


LOGGER = logging.getLogger("trifolium.risk_gate.direction_sanity")


def _request_signed_lots(request: OrderRequest) -> Decimal:
    return request.lots if request.side == "buy" else -request.lots


def _existing_signed_lots(request: OrderRequest) -> Decimal:
    total = Decimal("0")
    for position in request.existing_positions:
        if position.symbol == request.symbol:
            total += position.signed_lots
    return total


def _disallowed_side_reduces_exposure(request: OrderRequest) -> bool:
    existing = _existing_signed_lots(request)
    requested = _request_signed_lots(request)
    if existing == 0:
        return False
    if (existing > 0 and requested >= 0) or (existing < 0 and requested <= 0):
        return False
    return abs(requested) <= abs(existing)


def check_direction_sanity(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Enforce configured side bans, then warn on adding to same-direction exposure."""

    side_rule = limits.symbol_side_rules.get(request.symbol)
    if side_rule is not None and request.side not in side_rule.allowed_sides:
        if _disallowed_side_reduces_exposure(request):
            return True, None
        return (
            False,
            f"check_direction_sanity: {request.symbol} {request.side} disallowed except to reduce existing exposure; allowed_sides={side_rule.allowed_sides}",
        )
    requested = _request_signed_lots(request)
    for position in request.existing_positions:
        if position.symbol != request.symbol:
            continue
        if position.signed_lots == 0:
            continue
        if (position.signed_lots > 0 and requested > 0) or (position.signed_lots < 0 and requested < 0):
            LOGGER.warning(
                "check_direction_sanity: adding %s lots to same-direction %s exposure %s",
                requested,
                request.symbol,
                position.signed_lots,
            )
            return True, None
    return True, None
