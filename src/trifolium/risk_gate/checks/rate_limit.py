"""Risk Gate check: stateful per-minute order rate limit."""

from __future__ import annotations

from datetime import timedelta

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.state import STATE, record_order_timestamp
from trifolium.risk_gate.types import OrderRequest


def check_rate_limit(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Track accepted check attempts and fail if active mode rate cap is exceeded."""

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
