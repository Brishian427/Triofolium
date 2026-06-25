"""Risk Gate check: warn on adding to same-direction exposure."""

from __future__ import annotations

import logging
from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


LOGGER = logging.getLogger("trifolium.risk_gate.direction_sanity")


def _request_signed_lots(request: OrderRequest) -> Decimal:
    return request.lots if request.side == "buy" else -request.lots


def check_direction_sanity(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Emit a warning, not a failure, when adding to same-direction exposure."""

    del limits
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
