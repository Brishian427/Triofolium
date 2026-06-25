"""Risk Gate check: enforce per-order lot caps."""

from __future__ import annotations

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def check_lot_size(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Return whether request lots are within active mode and symbol override caps."""

    cap = limits.active.max_lot_per_order
    override = limits.symbol_overrides.get(request.symbol)
    if override is not None:
        cap = override.max_lot_per_order
    if request.lots <= cap:
        return True, None
    return False, f"check_lot_size: lots {request.lots} exceeds cap {cap} for {request.symbol}"
