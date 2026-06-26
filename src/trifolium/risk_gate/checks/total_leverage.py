"""Risk Gate check: projected gross notional leverage cap."""

from __future__ import annotations

from decimal import Decimal

from collections import defaultdict
from trifolium.risk_gate.checks.numeric_consistency import estimate_signed_account_notional
from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.types import OrderRequest


def _position_notional(position: object) -> Decimal:
    return estimate_signed_account_notional(position.symbol, position.signed_lots, position.contract_size, position.price)


def _request_signed_notional(request: OrderRequest) -> Decimal:
    signed_lots = request.lots if request.side == "buy" else -request.lots
    return estimate_signed_account_notional(request.symbol, signed_lots, request.contract_size, request.price)


def check_total_leverage(request: OrderRequest, limits: RiskLimits = RISK_LIMITS) -> tuple[bool, str | None]:
    """Return whether projected gross notional stays under active leverage cap."""

    if request.account is None:
        return False, "check_total_leverage: account snapshot is required"
    if request.account.equity <= 0:
        return False, f"check_total_leverage: equity {request.account.equity} is non-positive"
    exposure_by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in request.existing_positions:
        exposure_by_symbol[position.symbol] += _position_notional(position)
    exposure_by_symbol[request.symbol] += _request_signed_notional(request)
    projected = sum((abs(value) for value in exposure_by_symbol.values()), Decimal("0"))
    max_allowed = limits.active.max_total_leverage * request.account.equity
    if projected <= max_allowed:
        return True, None
    return False, f"check_total_leverage: projected notional {projected} exceeds max {max_allowed}"
