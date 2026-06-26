"""Risk Gate check: independently recompute order notional."""

from __future__ import annotations

from decimal import Decimal

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def estimate_account_notional(symbol: str, lots: Decimal, contract_size: Decimal, price: Decimal) -> Decimal:
    """Estimate account-currency notional for Risk Gate checks.

    USD-base FX pairs such as USDJPY are already denominated in USD at the
    contract level, so multiplying by quote price would overstate exposure by
    the exchange rate. Instruments quoted in USD, including XAUUSD, use price.
    Crosses remain a conservative price-based approximation.
    """

    if len(symbol) == 6 and symbol.startswith("USD"):
        return abs(lots * contract_size)
    return abs(lots * contract_size * price)


def estimate_signed_account_notional(symbol: str, signed_lots: Decimal, contract_size: Decimal, price: Decimal) -> Decimal:
    """Estimate signed account-currency exposure for netting-mode positions."""

    magnitude = estimate_account_notional(symbol, abs(signed_lots), contract_size, price)
    if signed_lots < 0:
        return -magnitude
    return magnitude


def recompute_notional(request: OrderRequest) -> Decimal:
    """Compute absolute account-currency notional from request fields."""

    return estimate_account_notional(request.symbol, request.lots, request.contract_size, request.price)


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
