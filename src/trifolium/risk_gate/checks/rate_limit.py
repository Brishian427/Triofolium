"""Risk Gate check: stateful per-minute order rate limit."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.state import STATE, record_order_timestamp
from trifolium.risk_gate.types import OrderRequest


def _is_symbol_exposure_reducing(request: OrderRequest) -> bool:
    current_signed_lots = sum(
        (position.signed_lots for position in request.existing_positions if position.symbol == request.symbol),
        Decimal("0"),
    )
    if current_signed_lots == 0:
        return False
    requested_signed_lots = request.lots if request.side == "buy" else -request.lots
    projected_signed_lots = current_signed_lots + requested_signed_lots
    return abs(projected_signed_lots) < abs(current_signed_lots)


def check_rate_limit(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Track accepted check attempts and fail if active mode rate cap is exceeded."""

    if _is_symbol_exposure_reducing(request):
        return True, None

    cutoff = request.timestamp - timedelta(seconds=60)
    STATE.recent_order_timestamps = [stamp for stamp in STATE.recent_order_timestamps if stamp > cutoff]
    if len(STATE.recent_order_timestamps) >= limits.active.max_orders_per_minute:
        return (
            False,
            f"check_rate_limit: {len(STATE.recent_order_timestamps)} orders in trailing 60s "
            f"meets cap {limits.active.max_orders_per_minute}",
        )
    record_order_timestamp(request.timestamp)
    return True, None
