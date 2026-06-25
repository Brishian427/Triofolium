"""Periodic account-state observability for the Risk Gate."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from trifolium.risk_gate.config import RISK_LIMITS, ROOT, RiskLimits
from trifolium.risk_gate.state import STATE
from trifolium.risk_gate.types import AccountSnapshot, PositionSnapshot
from trifolium.strategy.v0.config import load_strategy_v0_config


LOGGER = logging.getLogger("trifolium.risk_gate.observability")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def account_state_log_path(now: datetime | None = None) -> Path:
    """Return today's account-state JSONL path."""

    timestamp = now or datetime.now(timezone.utc)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"account_state_{timestamp.date().isoformat()}.jsonl"


def notional(position: PositionSnapshot) -> Decimal:
    """Return signed account-currency notional approximation."""

    return position.signed_lots * position.contract_size * position.price


def currency_decomposition(positions: list[PositionSnapshot]) -> dict[str, Decimal]:
    """Return approximate net exposure by currency or metal code."""

    exposure: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        symbol = position.symbol
        signed_notional = notional(position)
        if len(symbol) == 6:
            base, quote = symbol[:3], symbol[3:]
            exposure[base] += signed_notional
            exposure[quote] -= signed_notional
        else:
            exposure[symbol] += signed_notional
    return dict(exposure)


def biggest_single_symbol_exposure(positions: list[PositionSnapshot]) -> Decimal:
    """Return the largest absolute symbol exposure."""

    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for position in positions:
        by_symbol[position.symbol] += notional(position)
    if not by_symbol:
        return Decimal("0")
    return max(abs(value) for value in by_symbol.values())


def build_account_state_record(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    limits: RiskLimits = RISK_LIMITS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one serializable account-state observability record."""

    timestamp = now or datetime.now(timezone.utc)
    margin_level = account.margin_level_pct
    warning_floor = limits.hard_floors.min_margin_level_pct * Decimal("1.2")
    level = "INFO"
    messages: list[str] = []
    if account.open_positions_count > 0 and margin_level is not None and margin_level < warning_floor:
        level = "WARNING"
        messages.append(f"margin_level {margin_level}% within 20% buffer of floor {limits.hard_floors.min_margin_level_pct}%")
    if STATE.locked:
        level = "CRITICAL"
        messages.append(f"gate locked: {STATE.lock_reason}")
    return {
        "timestamp": timestamp.isoformat(),
        "level": level,
        "margin_level": margin_level,
        "equity": account.equity,
        "leverage": account.leverage,
        "open_positions_count": account.open_positions_count,
        "biggest_single_symbol_exposure": biggest_single_symbol_exposure(positions),
        "currency_decomposition_snapshot": currency_decomposition(positions),
        "gate_state": STATE.model_dump(mode="python"),
        "messages": messages,
    }


def log_account_state(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    limits: RiskLimits = RISK_LIMITS,
    now: datetime | None = None,
) -> Path:
    """Write one account-state line and emit WARNING/CRITICAL logs when required."""

    record = build_account_state_record(account, positions, limits=limits, now=now)
    level = record["level"]
    if level == "WARNING":
        LOGGER.warning("%s", record)
    elif level == "CRITICAL":
        LOGGER.critical("%s", record)
    path = account_state_log_path(now)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(record), sort_keys=True) + "\n")
    return path


def get_live_account_snapshot() -> AccountSnapshot:
    """Fetch live account snapshot lazily from Task 01 adapter."""

    from trifolium.adapter.account import get_account_state

    state = get_account_state()
    positions = get_live_positions_snapshot()
    return AccountSnapshot(
        equity=state.equity,
        margin_level_pct=state.margin_level,
        balance=state.balance,
        open_positions_count=len(positions),
        leverage=Decimal(str(state.leverage)),
    )


def get_live_positions_snapshot() -> list[PositionSnapshot]:
    """Fetch live positions lazily from MT5 for observability."""

    import MetaTrader5 as mt5

    settings = load_strategy_v0_config()
    positions = mt5.positions_get() or []
    snapshots: list[PositionSnapshot] = []
    for position in positions:
        raw = position._asdict() if hasattr(position, "_asdict") else dict(position)
        lots = Decimal(str(raw["volume"]))
        signed_lots = lots if int(raw.get("type", 0)) == 0 else -lots
        symbol = str(raw["symbol"])
        snapshots.append(
            PositionSnapshot(
                symbol=symbol,
                signed_lots=signed_lots,
                price=Decimal(str(raw["price_current"])),
                contract_size=settings.instrument_contract_size.get(symbol, Decimal("100000")),
                ticket=int(raw["ticket"]) if raw.get("ticket") is not None else None,
                unrealized_pnl=Decimal(str(raw["profit"])) if raw.get("profit") is not None else None,
            )
        )
    return snapshots


def run_observability_loop(
    account_provider: Callable[[], AccountSnapshot] = get_live_account_snapshot,
    positions_provider: Callable[[], list[PositionSnapshot]] = get_live_positions_snapshot,
    *,
    interval_seconds: int = 60,
    iterations: int | None = None,
) -> None:
    """Run scheduled account-state logging once per interval."""

    count = 0
    while iterations is None or count < iterations:
        account = account_provider()
        positions = positions_provider()
        account.open_positions_count = len(positions)
        log_account_state(account, positions)
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(interval_seconds)
