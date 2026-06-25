"""Portfolio constraints for StrategyV0 target positions."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from trifolium.strategy.v0.config import StrategyV0Config
from trifolium.strategy.v0.trader import FX_SYMBOLS


PositionTuple = tuple[str, Decimal, Decimal]


def decompose_to_currency_exposure(positions: list[PositionTuple], settings: StrategyV0Config) -> dict[str, Decimal]:
    """Return approximate net currency/metal exposure from signed lots."""

    currency_net: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for symbol, lot, price in positions:
        contract_size = settings.instrument_contract_size[symbol]
        if symbol in FX_SYMBOLS:
            base, quote = symbol[:3], symbol[3:]
            base_units = lot * contract_size
            quote_units = -(lot * contract_size * price)
            currency_net[base] += base_units
            currency_net[quote] += quote_units
        elif symbol in {"XAUUSD", "XAGUSD"}:
            metal, quote = symbol[:3], symbol[3:]
            metal_value = lot * contract_size * price
            currency_net[metal] += metal_value
            currency_net[quote] -= metal_value
    return dict(currency_net)


def check_currency_constraint(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, str | None]:
    """Check per-currency net exposure cap."""

    threshold = equity * settings.portfolio.currency_threshold_pct / Decimal("100")
    for currency, exposure in decompose_to_currency_exposure(positions, settings).items():
        if abs(exposure) > threshold:
            return False, f"Currency {currency} net exposure {exposure} exceeds {settings.portfolio.currency_threshold_pct}% of equity"
    return True, None


def check_metals_constraint(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, str | None]:
    """Check combined XAU/XAG directional exposure cap."""

    combined = Decimal("0")
    for symbol, lot, price in positions:
        if symbol in {"XAUUSD", "XAGUSD"}:
            combined += lot * settings.instrument_contract_size[symbol] * price
    threshold = equity * settings.portfolio.metals_threshold_pct / Decimal("100")
    if abs(combined) > threshold:
        return False, f"Metals combined exposure {combined} exceeds {settings.portfolio.metals_threshold_pct}% of equity"
    return True, None


def check_gross_leverage(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, str | None]:
    """Check total absolute notional cap."""

    total_notional = Decimal("0")
    for symbol, lot, price in positions:
        total_notional += abs(lot * settings.instrument_contract_size[symbol] * price)
    if equity <= 0:
        return False, "Equity is non-positive"
    gross = total_notional / equity
    if gross > settings.portfolio.gross_leverage_threshold:
        return False, f"Gross leverage {gross:.2f} exceeds {settings.portfolio.gross_leverage_threshold}"
    return True, None


def check_all_constraints(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, list[str]]:
    """Run all StrategyV0 portfolio constraints."""

    messages: list[str] = []
    for check in (check_currency_constraint, check_metals_constraint, check_gross_leverage):
        ok, message = check(positions, equity, settings)
        if not ok and message is not None:
            messages.append(message)
    return not messages, messages


def apply_portfolio_scaling(
    target_lots: dict[str, Decimal],
    prices: dict[str, Decimal],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[dict[str, Decimal], Decimal, list[str]]:
    """Scale all target positions down to the largest factor satisfying constraints."""

    base_positions = [(symbol, lot, prices[symbol]) for symbol, lot in target_lots.items() if lot != 0 and symbol in prices]
    ok, messages = check_all_constraints(base_positions, equity, settings)
    if ok:
        return target_lots, Decimal("1"), []
    steps = settings.portfolio.scaling_steps
    for index in range(steps - 1, -1, -1):
        scale = Decimal(index) / Decimal(steps - 1)
        scaled = {symbol: (lot * scale).quantize(settings.broker_lot_step) for symbol, lot in target_lots.items()}
        positions = [(symbol, lot, prices[symbol]) for symbol, lot in scaled.items() if lot != 0 and symbol in prices]
        ok, messages = check_all_constraints(positions, equity, settings)
        if ok:
            return scaled, scale, []
    return {symbol: Decimal("0") for symbol in target_lots}, Decimal("0"), messages
