"""Live fixed-direction profit harvesting loop.

This runner is intentionally separate from StrategyV0. It submits only the
principal-approved fixed target set through Risk Gate, takes per-position
profit at a configured dollar threshold, waits for a cooldown plus price
retracement, then re-enters the same direction.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts import live_run_strategy_v0 as live
from trifolium.adapter.market_data import get_tick, load_instruments
from trifolium.adapter.mt5_client import mt5_session
from trifolium.risk_gate.config import RISK_LIMITS
from trifolium.risk_gate.checks.numeric_consistency import estimate_account_notional
from trifolium.risk_gate.gate import submit_order
from trifolium.risk_gate.observability import get_live_account_snapshot, get_live_positions_snapshot, log_account_state
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, OrderResult, PositionSnapshot


Side = Literal["buy", "sell"]
LOG_STEM = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
HARVESTER_COMMENT_PREFIX = "profit_harvester"


@dataclass(frozen=True)
class HarvestTarget:
    symbol: str
    side: Side
    lots: Decimal
    reentry_retrace_price: Decimal


@dataclass
class HarvestState:
    last_exit_price: Decimal | None = None
    last_exit_time: datetime | None = None
    cycles_completed: int = 0


@dataclass(frozen=True)
class HarvestConfig:
    take_profit_usd: Decimal
    poll_seconds: int
    cooldown_seconds: int
    session_total_loss_usd: Decimal
    targets: list[HarvestTarget]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="python"))
    return value


def log_path() -> Path:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"profit_harvester_{LOG_STEM}.jsonl"


def heartbeat_path() -> Path:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "profit_harvester_heartbeat.json"


def state_path() -> Path:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "profit_harvester_state.json"


def log_event(event: str, payload: dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": _json_safe(payload),
    }
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_heartbeat(payload: dict[str, Any]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": None,
        "payload": _json_safe(payload),
        "log_path": str(log_path()),
    }
    heartbeat_path().write_text(json.dumps(record, sort_keys=True), encoding="utf-8")


def load_states(targets: list[HarvestTarget]) -> dict[str, HarvestState]:
    states = {target.symbol: HarvestState() for target in targets}
    path = state_path()
    if not path.exists():
        return states
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log_event("state_load_failed", {"path": str(path), "error": str(exc)})
        return states
    for symbol, item in raw.get("states", {}).items():
        if symbol not in states:
            continue
        last_exit_time = item.get("last_exit_time")
        states[symbol] = HarvestState(
            last_exit_price=Decimal(str(item["last_exit_price"])) if item.get("last_exit_price") is not None else None,
            last_exit_time=datetime.fromisoformat(last_exit_time) if last_exit_time else None,
            cycles_completed=int(item.get("cycles_completed", 0)),
        )
    return states


def save_states(states: dict[str, HarvestState]) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "states": _json_safe(states),
    }
    state_path().write_text(json.dumps(record, sort_keys=True), encoding="utf-8")


def load_harvest_config(path: Path = ROOT / "config" / "profit_harvester.yaml") -> HarvestConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return HarvestConfig(
        take_profit_usd=Decimal(str(data["take_profit_usd"])),
        poll_seconds=int(data["poll_seconds"]),
        cooldown_seconds=int(data["cooldown_seconds"]),
        session_total_loss_usd=Decimal(str(data["session_total_loss_usd"])),
        targets=[
            HarvestTarget(
                symbol=str(item["symbol"]),
                side=str(item["side"]),  # type: ignore[arg-type]
                lots=Decimal(str(item["lots"])),
                reentry_retrace_price=Decimal(str(item["reentry_retrace_price"])),
            )
            for item in data["targets"]
        ],
    )


def _contract_sizes() -> dict[str, Decimal]:
    sizes: dict[str, Decimal] = {}
    for instrument in load_instruments(ROOT / "config" / "instruments.yaml"):
        if instrument.expected_contract_size is not None:
            sizes[instrument.symbol] = instrument.expected_contract_size
    return sizes


def _pip_sizes() -> dict[str, Decimal]:
    return {
        instrument.symbol: instrument.pip_size
        for instrument in load_instruments(ROOT / "config" / "instruments.yaml")
    }


def _target_signed_lots(target: HarvestTarget) -> Decimal:
    return target.lots if target.side == "buy" else -target.lots


def _is_harvester_position(position: PositionSnapshot) -> bool:
    return (position.comment or "").startswith(HARVESTER_COMMENT_PREFIX)


def _position_by_symbol(positions: list[PositionSnapshot]) -> dict[str, PositionSnapshot]:
    return {position.symbol: position for position in positions if position.signed_lots != 0}


def _harvester_position_by_symbol(positions: list[PositionSnapshot]) -> dict[str, PositionSnapshot]:
    return {
        position.symbol: position
        for position in positions
        if position.signed_lots != 0 and _is_harvester_position(position)
    }


def _symbol_max_lots(symbol: str) -> Decimal:
    override = RISK_LIMITS.symbol_overrides.get(symbol)
    if override is not None:
        return override.max_lot_per_order
    return RISK_LIMITS.active.max_lot_per_order


def _chunk_lots(lots: Decimal, max_lots: Decimal) -> list[Decimal]:
    chunks: list[Decimal] = []
    remaining = lots
    while remaining > 0:
        chunk = min(remaining, max_lots)
        chunks.append(chunk)
        remaining -= chunk
    return chunks


def _current_entry_price(target: HarvestTarget, pip_sizes: dict[str, Decimal]) -> Decimal:
    tick = get_tick(target.symbol, pip_sizes[target.symbol])
    return tick.ask if target.side == "buy" else tick.bid


def _current_close_price(position: PositionSnapshot, pip_sizes: dict[str, Decimal]) -> Decimal:
    tick = get_tick(position.symbol, pip_sizes[position.symbol])
    return tick.bid if position.signed_lots > 0 else tick.ask


def _reentry_allowed(target: HarvestTarget, state: HarvestState, current_price: Decimal, now: datetime, cooldown_seconds: int) -> bool:
    if state.last_exit_price is None or state.last_exit_time is None:
        return True
    if (now - state.last_exit_time).total_seconds() < cooldown_seconds:
        return False
    if target.side == "buy":
        return current_price <= state.last_exit_price - target.reentry_retrace_price
    return current_price >= state.last_exit_price + target.reentry_retrace_price


def _entry_request(
    target: HarvestTarget,
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    lots: Decimal,
    price: Decimal,
    contract_sizes: dict[str, Decimal],
) -> OrderRequest:
    contract_size = contract_sizes.get(target.symbol, Decimal("100000"))
    return OrderRequest(
        symbol=target.symbol,
        side=target.side,
        lots=lots,
        price=price,
        contract_size=contract_size,
        strategy_notional=estimate_account_notional(target.symbol, lots, contract_size, price),
        comment="profit_harvester_entry",
        existing_positions=positions,
        account=account,
    )


def _close_request(
    position: PositionSnapshot,
    account: AccountSnapshot,
    *,
    lots: Decimal,
    price: Decimal,
) -> OrderRequest:
    side: Side = "sell" if position.signed_lots > 0 else "buy"
    return OrderRequest(
        symbol=position.symbol,
        side=side,
        lots=lots,
        price=price,
        contract_size=position.contract_size,
        strategy_notional=estimate_account_notional(position.symbol, lots, position.contract_size, price),
        comment="profit_harvester_take_profit",
        existing_positions=[position],
        account=account,
    )


def submit_entry(
    target: HarvestTarget,
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    price: Decimal,
    contract_sizes: dict[str, Decimal],
) -> list[OrderResult]:
    results: list[OrderResult] = []
    for lots in _chunk_lots(target.lots, _symbol_max_lots(target.symbol)):
        request = _entry_request(target, account, positions, lots=lots, price=price, contract_sizes=contract_sizes)
        result = submit_order(request)
        results.append(result)
        log_event("entry_order_result", {"target": target, "request": request, "result": result})
        if result.status not in {"accepted", "submitted", "filled"}:
            break
    return results


def submit_take_profit(
    position: PositionSnapshot,
    account: AccountSnapshot,
    *,
    price: Decimal,
) -> list[OrderResult]:
    results: list[OrderResult] = []
    for lots in _chunk_lots(abs(position.signed_lots), _symbol_max_lots(position.symbol)):
        request = _close_request(position, account, lots=lots, price=price)
        result = submit_order(request)
        results.append(result)
        log_event("take_profit_order_result", {"position": position, "request": request, "result": result})
        if result.status not in {"accepted", "submitted", "filled"}:
            break
    return results


def submit_reconcile_opposite(
    position: PositionSnapshot,
    account: AccountSnapshot,
    *,
    price: Decimal,
) -> list[OrderResult]:
    results: list[OrderResult] = []
    for lots in _chunk_lots(abs(position.signed_lots), _symbol_max_lots(position.symbol)):
        request = _close_request(position, account, lots=lots, price=price)
        request.comment = "harv_reconcile"
        result = submit_order(request)
        results.append(result)
        log_event("reconcile_opposite_order_result", {"position": position, "request": request, "result": result})
        if result.status not in {"accepted", "submitted", "filled"}:
            break
    return results


def run_harvester(
    config: HarvestConfig,
    *,
    iterations: int | None = None,
    session_start_equity: Decimal | None = None,
) -> None:
    pip_sizes = _pip_sizes()
    contract_sizes = _contract_sizes()
    states = load_states(config.targets)
    account = get_live_account_snapshot()
    positions = get_live_positions_snapshot()
    account.open_positions_count = len(positions)
    risk_state = live.initialize_live_risk_state(account, session_start_equity=session_start_equity)
    log_event(
        "profit_harvester_started",
        {
            "config": config,
            "targets": config.targets,
            "hard_kills_armed": live.hard_kill_armed_status(),
            "session_start_equity": risk_state.session_start_equity,
            "session_loss_floor": risk_state.session_start_equity - config.session_total_loss_usd,
            "state_path": str(state_path()),
            "restored_states": states,
        },
    )

    count = 0
    while iterations is None or count < iterations:
        now = datetime.now(timezone.utc)
        account = get_live_account_snapshot()
        positions = get_live_positions_snapshot()
        account.open_positions_count = len(positions)
        log_account_state(account, positions)
        log_event(
            "hard_kills_disabled_for_manual_trade_protection",
            {
                "reason": "principal_override_manual_trades_must_not_be_interfered_with",
                "manual_positions": [position for position in positions if not _is_harvester_position(position)],
                "harvester_positions": [position for position in positions if _is_harvester_position(position)],
            },
        )

        by_symbol = _harvester_position_by_symbol(positions)
        all_by_symbol = _position_by_symbol(positions)
        for target in config.targets:
            position = by_symbol.get(target.symbol)
            state = states[target.symbol]
            unmanaged_position = all_by_symbol.get(target.symbol) if position is None else None
            if unmanaged_position is not None:
                log_event(
                    "target_skipped_unmanaged_position",
                    {
                        "target": target,
                        "position": unmanaged_position,
                        "reason": "manual_or_non_harvester_position_not_managed",
                    },
                )
                continue
            if position is not None:
                target_signed = _target_signed_lots(target)
                if (target_signed > 0 and position.signed_lots < 0) or (target_signed < 0 and position.signed_lots > 0):
                    close_price = _current_close_price(position, pip_sizes)
                    results = submit_reconcile_opposite(position, account, price=close_price)
                    log_event(
                        "target_reconciled_opposite_position",
                        {
                            "target": target,
                            "position": position,
                            "close_price": close_price,
                            "results": results,
                        },
                    )
                    continue
                profit = position.unrealized_pnl or Decimal("0")
                if profit >= config.take_profit_usd:
                    close_price = _current_close_price(position, pip_sizes)
                    results = submit_take_profit(position, account, price=close_price)
                    if any(result.status in {"accepted", "submitted", "filled"} for result in results):
                        state.last_exit_price = close_price
                        state.last_exit_time = now
                        state.cycles_completed += 1
                        save_states(states)
                    log_event(
                        "take_profit_triggered",
                        {
                            "target": target,
                            "position": position,
                            "profit": profit,
                            "threshold": config.take_profit_usd,
                            "close_price": close_price,
                            "cycles_completed": state.cycles_completed,
                        },
                    )
                continue

            entry_price = _current_entry_price(target, pip_sizes)
            if not _reentry_allowed(target, state, entry_price, now, config.cooldown_seconds):
                log_event(
                    "entry_waiting_for_retrace",
                    {
                        "target": target,
                        "current_price": entry_price,
                        "last_exit_price": state.last_exit_price,
                        "last_exit_time": state.last_exit_time,
                        "cooldown_seconds": config.cooldown_seconds,
                    },
                )
                continue
            submit_entry(target, account, positions, price=entry_price, contract_sizes=contract_sizes)

        log_event(
            "heartbeat",
            {
                "open_positions": positions,
                "equity": account.equity,
                "states": states,
                "halted": risk_state.halted,
                "halt_reason": risk_state.halt_reason,
            },
        )
        save_states(states)
        write_heartbeat(
            {
                "equity": account.equity,
                "open_positions_count": len(positions),
                "states": states,
                "halted": risk_state.halted,
                "halt_reason": risk_state.halt_reason,
            }
        )
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(config.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-approved", action="store_true")
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "profit_harvester.yaml")
    parser.add_argument("--session-start-equity", type=Decimal, default=None)
    args = parser.parse_args()

    config = load_harvest_config(args.config)
    if not args.live_approved:
        print("profit harvester not started: pass --live-approved only after principal go-ahead")
        return 0
    with mt5_session():
        live.assert_risk_gate_production()
        run_harvester(config, iterations=args.iterations, session_start_equity=args.session_start_equity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
