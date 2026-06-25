"""Risk Gate check: independently recompute order notional."""

from __future__ import annotations

from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def recompute_notional(request: OrderRequest) -> Decimal:
    """Compute absolute notional from lots, contract size, and price."""

    return abs(request.lots * request.contract_size * request.price)


def check_numeric_consistency(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Fail if claimed notional differs beyond both absolute and relative tolerances."""

    recomputed = recompute_notional(request)
    claimed = abs(request.strategy_notional)
    abs_error = abs(claimed - recomputed)
    rel_error = Decimal("0") if recomputed == 0 else abs_error / recomputed
    if abs_error > limits.active.numeric_tolerance_abs and rel_error > limits.active.numeric_tolerance_rel:
        return (
            False,
            f"check_numeric_consistency: claimed {claimed} recomputed {recomputed} "
            f"abs_error {abs_error} rel_error {rel_error}",
        )
    return True, None
