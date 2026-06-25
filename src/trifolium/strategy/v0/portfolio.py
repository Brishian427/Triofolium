"""Portfolio constraints for StrategyV0 target positions."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_DOWN

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


def check_single_symbol_concentration(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, str | None]:
    """Check max single-symbol share of total absolute notional."""

    threshold_pct = settings.portfolio.max_single_symbol_concentration_pct
    if threshold_pct >= 100:
        return True, None
    notionals = [
        (symbol, abs(lot * settings.instrument_contract_size[symbol] * price))
        for symbol, lot, price in positions
        if lot != 0
    ]
    total = sum((notional for _symbol, notional in notionals), Decimal("0"))
    if total == 0:
        return True, None
    for symbol, notional in notionals:
        concentration_pct = notional / total * Decimal("100")
        if concentration_pct > threshold_pct:
            return False, f"Symbol {symbol} concentration {concentration_pct}% exceeds {threshold_pct}%"
    return True, None


def check_all_constraints(
    positions: list[PositionTuple],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[bool, list[str]]:
    """Run all StrategyV0 portfolio constraints."""

    messages: list[str] = []
    for check in (check_currency_constraint, check_metals_constraint, check_gross_leverage, check_single_symbol_concentration):
        ok, message = check(positions, equity, settings)
        if not ok and message is not None:
            messages.append(message)
    return not messages, messages


def _quantize_abs_lot(lot: Decimal, settings: StrategyV0Config) -> Decimal:
    quantized = lot.quantize(settings.broker_lot_step, rounding=ROUND_DOWN)
    return quantized if quantized >= settings.broker_lot_step else Decimal("0")


def _cap_symbol_notional(
    target_lots: dict[str, Decimal],
    prices: dict[str, Decimal],
    equity: Decimal,
    settings: StrategyV0Config,
) -> dict[str, Decimal]:
    max_pct = settings.portfolio.max_symbol_notional_pct
    if max_pct >= 100:
        return dict(target_lots)
    capped = dict(target_lots)
    max_notional = equity * max_pct / Decimal("100")
    for symbol, lot in list(capped.items()):
        price = prices.get(symbol)
        if price is None or price <= 0 or lot == 0:
            continue
        contract_size = settings.instrument_contract_size[symbol]
        current_notional = abs(lot) * contract_size * price
        if current_notional <= max_notional:
            continue
        max_lot = _quantize_abs_lot(max_notional / (contract_size * price), settings)
        capped[symbol] = max_lot if lot > 0 else -max_lot
    return capped


def _cap_single_symbol_concentration(
    target_lots: dict[str, Decimal],
    prices: dict[str, Decimal],
    settings: StrategyV0Config,
) -> dict[str, Decimal]:
    threshold_pct = settings.portfolio.max_single_symbol_concentration_pct
    if threshold_pct >= 100:
        return dict(target_lots)
    threshold = threshold_pct / Decimal("100")
    capped = dict(target_lots)
    for _ in range(max(1, len(capped) * 2)):
        notionals = {
            symbol: abs(lot) * settings.instrument_contract_size[symbol] * prices[symbol]
            for symbol, lot in capped.items()
            if lot != 0 and symbol in prices and prices[symbol] > 0
        }
        total = sum(notionals.values(), Decimal("0"))
        if total == 0:
            return capped
        symbol, largest = max(notionals.items(), key=lambda item: item[1])
        if largest / total <= threshold:
            return capped
        others = total - largest
        if others <= 0:
            capped[symbol] = Decimal("0")
            continue
        max_notional = (threshold / (Decimal("1") - threshold)) * others
        max_lot = _quantize_abs_lot(max_notional / (settings.instrument_contract_size[symbol] * prices[symbol]), settings)
        capped[symbol] = max_lot if capped[symbol] > 0 else -max_lot
    return capped


def apply_risk_budgets(
    target_lots: dict[str, Decimal],
    prices: dict[str, Decimal],
    equity: Decimal,
    settings: StrategyV0Config,
) -> dict[str, Decimal]:
    """Apply per-symbol and concentration budgets before global scaling."""

    capped = _cap_symbol_notional(target_lots, prices, equity, settings)
    return _cap_single_symbol_concentration(capped, prices, settings)


def apply_portfolio_scaling(
    target_lots: dict[str, Decimal],
    prices: dict[str, Decimal],
    equity: Decimal,
    settings: StrategyV0Config,
) -> tuple[dict[str, Decimal], Decimal, list[str]]:
    """Scale all target positions down to the largest factor satisfying constraints."""

    budgeted_lots = apply_risk_budgets(target_lots, prices, equity, settings)
    base_positions = [(symbol, lot, prices[symbol]) for symbol, lot in budgeted_lots.items() if lot != 0 and symbol in prices]
    ok, messages = check_all_constraints(base_positions, equity, settings)
    if ok:
        return budgeted_lots, Decimal("1"), []
    steps = settings.portfolio.scaling_steps
    for index in range(steps - 1, -1, -1):
        scale = Decimal(index) / Decimal(steps - 1)
        scaled = {symbol: (lot * scale).quantize(settings.broker_lot_step) for symbol, lot in budgeted_lots.items()}
        positions = [(symbol, lot, prices[symbol]) for symbol, lot in scaled.items() if lot != 0 and symbol in prices]
        ok, messages = check_all_constraints(positions, equity, settings)
        if ok:
            return scaled, scale, []
    return {symbol: Decimal("0") for symbol in target_lots}, Decimal("0"), messages
