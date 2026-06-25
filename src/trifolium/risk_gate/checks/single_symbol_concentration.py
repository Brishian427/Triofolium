"""Risk Gate check: cap projected single-symbol concentration."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from trifolium.risk_gate.checks.numeric_consistency import recompute_notional
from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def check_single_symbol_concentration(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Return whether projected symbol exposure share is within the active cap."""

    exposure_by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in request.existing_positions:
        exposure_by_symbol[position.symbol] += abs(position.signed_lots * position.contract_size * position.price)
    if not exposure_by_symbol:
        return True, None
    exposure_by_symbol[request.symbol] += recompute_notional(request)
    total = sum(exposure_by_symbol.values(), Decimal("0"))
    if total == 0:
        return True, None
    ratio_pct = exposure_by_symbol[request.symbol] / total * Decimal("100")
    if ratio_pct <= limits.active.max_single_symbol_pct:
        return True, None
    return (
        False,
        f"check_single_symbol_concentration: {request.symbol} concentration {ratio_pct}% "
        f"exceeds {limits.active.max_single_symbol_pct}%",
    )
