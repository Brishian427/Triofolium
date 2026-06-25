"""Guarded live StrategyV0 runner.

This script is a readiness harness. It must not be launched for live trading
unless the principal explicitly passes ``--live-approved`` after reviewing L5.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.gate import submit_order
from trifolium.risk_gate.observability import get_live_account_snapshot, get_live_positions_snapshot, log_account_state
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, OrderResult, PositionSnapshot
from trifolium.strategy.v0.config import load_strategy_v0_config
from trifolium.strategy.v0.strategy import StrategyV0


LEGACY_AUDUSD_TICKET = 46678
EMERGENCY_MARGIN_LEVEL_PCT = Decimal("50")
SLEEP_SECONDS = 60


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="python"))
    return value


def strategy_log_path(now: datetime | None = None) -> Path:
    timestamp = now or datetime.now(timezone.utc)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"strategy_v0_{timestamp.date().isoformat()}.jsonl"


def log_strategy_event(event: str, payload: dict[str, Any], *, now: datetime | None = None) -> Path:
    record = {
        "timestamp": (now or datetime.now(timezone.utc)).isoformat(),
        "event": event,
        "payload": _json_safe(payload),
    }
    path = strategy_log_path(now)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def assert_risk_gate_production(limits: RiskLimits = RISK_LIMITS) -> None:
    if limits.mode != "production":
        raise RuntimeError(f"Risk Gate must be in production mode before live StrategyV0 start; current mode={limits.mode}")


def _position_ticket(position: PositionSnapshot | dict[str, Any]) -> int | None:
    if isinstance(position, dict):
        value = position.get("ticket")
    else:
        value = getattr(position, "ticket", None)
    return None if value is None else int(value)


def _position_symbol(position: PositionSnapshot | dict[str, Any]) -> str:
    if isinstance(position, dict):
        return str(position.get("symbol", ""))
    return position.symbol


def assert_legacy_audusd_flat(positions: list[PositionSnapshot | dict[str, Any]]) -> None:
    for position in positions:
        ticket = _position_ticket(position)
        symbol = _position_symbol(position)
        if ticket == LEGACY_AUDUSD_TICKET or symbol == "AUDUSD":
            raise RuntimeError(f"Refusing live start: legacy AUDUSD exposure still present (ticket={ticket}, symbol={symbol})")


def _flatten_request(position: PositionSnapshot, account: AccountSnapshot) -> OrderRequest:
    side = "sell" if position.signed_lots > 0 else "buy"
    lots = abs(position.signed_lots)
    return OrderRequest(
        symbol=position.symbol,
        side=side,
        lots=lots,
        price=position.price,
        contract_size=position.contract_size,
        strategy_notional=lots * position.contract_size * position.price,
        comment="strategy_v0_emergency_flatten",
        existing_positions=[position],
        account=account,
    )


def emergency_flatten_positions(
    positions: list[PositionSnapshot],
    account: AccountSnapshot,
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
) -> list[OrderResult]:
    results: list[OrderResult] = []
    for position in positions:
        if position.signed_lots == 0:
            continue
        request = _flatten_request(position, account)
        result = submitter(request)
        log_strategy_event("emergency_flatten_order", {"request": request, "result": result})
        results.append(result)
    return results


def check_margin_or_flatten(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
) -> list[OrderResult]:
    if account.margin_level_pct is None or account.margin_level_pct >= EMERGENCY_MARGIN_LEVEL_PCT:
        return []
    log_strategy_event("emergency_margin_trigger", {"account": account, "positions": positions})
    return emergency_flatten_positions(positions, account, submitter=submitter)


def run_readiness_checks(
    *,
    limits: RiskLimits = RISK_LIMITS,
    account_provider: Callable[[], AccountSnapshot] = get_live_account_snapshot,
    positions_provider: Callable[[], list[PositionSnapshot]] = get_live_positions_snapshot,
) -> list[str]:
    assert_risk_gate_production(limits)
    positions = positions_provider()
    assert_legacy_audusd_flat(positions)
    account = account_provider()
    log_account_state(account, positions)
    check_margin_or_flatten(account, positions)
    log_strategy_event("readiness_check_passed", {"account": account, "positions": positions})
    return [
        "risk_gate_production",
        "legacy_audusd_flat",
        "account_state_logged",
        "margin_monitor_ready",
        "strategy_jsonl_logging_ready",
    ]


def run_live_loop(iterations: int | None = None) -> None:
    settings = load_strategy_v0_config()
    strategy = StrategyV0()
    log_strategy_event("strategy_started", {"strategy": strategy.name, "symbols": settings.tradable_symbols})
    count = 0
    while iterations is None or count < iterations:
        account = get_live_account_snapshot()
        positions = get_live_positions_snapshot()
        log_account_state(account, positions)
        check_margin_or_flatten(account, positions)
        log_strategy_event(
            "heartbeat",
            {
                "strategy": strategy.name,
                "destroyer_symbols": sorted(strategy.destroyer_symbols),
                "last_signals": strategy.last_signals,
                "portfolio_messages": strategy.portfolio_messages,
            },
        )
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(SLEEP_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-approved", action="store_true", help="Principal-only acknowledgement required before live loop.")
    parser.add_argument("--iterations", type=int, default=None)
    args = parser.parse_args()

    from trifolium.adapter.mt5_client import mt5_session

    with mt5_session():
        checks = run_readiness_checks()
        print("readiness_passed: " + ", ".join(checks))
        if not args.live_approved:
            print("live loop not started: pass --live-approved only after principal go-ahead")
            return 0
        run_live_loop(iterations=args.iterations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
