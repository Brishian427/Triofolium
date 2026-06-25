"""Guarded live StrategyV0 runner.

This script is a readiness harness. It must not be launched for live trading
unless the principal explicitly passes ``--live-approved`` after reviewing L5.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.backtest.bar_engine import load_symbol_bars
from trifolium.backtest.config import load_backtest_config
from trifolium.backtest.types import AccountState as StrategyAccountState
from trifolium.backtest.types import Bar, Order, Position, Tick
from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.gate import submit_order
from trifolium.risk_gate.observability import get_live_account_snapshot, get_live_positions_snapshot, log_account_state
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, OrderResult, PositionSnapshot
from trifolium.strategy.v0.config import StrategyV0Config, load_strategy_v0_config
from trifolium.strategy.v0.strategy import StrategyV0


LEGACY_AUDUSD_TICKET = 46678
EMERGENCY_MARGIN_LEVEL_PCT = Decimal("50")
SINGLE_INSTRUMENT_UNREALIZED_FLOOR = Decimal("-200")
TOTAL_UNREALIZED_FLOOR = Decimal("-500")
SESSION_TOTAL_LOSS_USD = Decimal("1000")
TRADE_ANOMALY_COUNT = 100
TRADE_ANOMALY_WINDOW = timedelta(minutes=30)
SESSION_DRAWDOWN_PCT = Decimal("5")
SLEEP_SECONDS = 60
DEFAULT_WARMUP_DAYS = 30
LIVE_RUN_LOG_STEM = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


@dataclass
class LiveRiskState:
    """State needed for live-session hard kills."""

    session_start_equity: Decimal
    session_peak_equity: Decimal
    recent_trade_timestamps: deque[datetime] = field(default_factory=deque)
    halted: bool = False
    halt_reason: str | None = None

    @classmethod
    def from_account(cls, account: AccountSnapshot) -> "LiveRiskState":
        return cls(session_start_equity=account.equity, session_peak_equity=account.equity)

    def update_peak(self, equity: Decimal) -> None:
        if equity > self.session_peak_equity:
            self.session_peak_equity = equity

    def record_trade(self, timestamp: datetime) -> None:
        self.recent_trade_timestamps.append(timestamp)
        self.prune_trades(timestamp)

    def prune_trades(self, timestamp: datetime) -> None:
        floor = timestamp - TRADE_ANOMALY_WINDOW
        while self.recent_trade_timestamps and self.recent_trade_timestamps[0] < floor:
            self.recent_trade_timestamps.popleft()

    def recent_trade_count(self, timestamp: datetime) -> int:
        self.prune_trades(timestamp)
        return len(self.recent_trade_timestamps)


@dataclass
class LiveBarState:
    """Mutable sampled OHLC state for one live symbol/bar bucket."""

    timestamp: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    bid: Decimal
    ask: Decimal
    volume: Decimal = Decimal("1")

    @classmethod
    def from_tick(cls, bucket: datetime, tick: Tick) -> "LiveBarState":
        mid = tick.mid
        return cls(
            timestamp=bucket,
            symbol=tick.symbol,
            open=mid,
            high=mid,
            low=mid,
            close=mid,
            bid=tick.bid,
            ask=tick.ask,
        )

    def update(self, tick: Tick) -> None:
        mid = tick.mid
        if mid > self.high:
            self.high = mid
        if mid < self.low:
            self.low = mid
        self.close = mid
        self.bid = tick.bid
        self.ask = tick.ask
        self.volume += Decimal("1")

    def to_bar(self) -> Bar:
        return Bar(
            timestamp=self.timestamp,
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            bid=self.bid,
            ask=self.ask,
            volume=self.volume,
            spread_pips=Decimal("0"),
        )


@dataclass
class LiveBarAggregator:
    """Sample current ticks into complete StrategyV0 bar buckets."""

    minutes: int
    current_bucket: datetime | None = None
    builders: dict[str, LiveBarState] = field(default_factory=dict)

    def update(self, ticks: dict[str, Tick], required_symbols: list[str]) -> list[Bar]:
        if not ticks:
            return []
        bucket = _bucket_timestamp(max(tick.timestamp for tick in ticks.values()), self.minutes)
        if self.current_bucket is None:
            self.current_bucket = bucket
            self.builders = {
                symbol: LiveBarState.from_tick(bucket, tick)
                for symbol, tick in ticks.items()
            }
            return []
        if bucket == self.current_bucket:
            for symbol, tick in ticks.items():
                if symbol in self.builders:
                    self.builders[symbol].update(tick)
                else:
                    self.builders[symbol] = LiveBarState.from_tick(bucket, tick)
            return []

        completed: list[Bar] = []
        if all(symbol in self.builders for symbol in required_symbols):
            completed = [self.builders[symbol].to_bar() for symbol in required_symbols]
        else:
            missing = [symbol for symbol in required_symbols if symbol not in self.builders]
            log_strategy_event(
                "live_bar_incomplete",
                {"bucket": self.current_bucket, "missing_symbols": missing, "available_symbols": sorted(self.builders)},
            )
        self.current_bucket = bucket
        self.builders = {
            symbol: LiveBarState.from_tick(bucket, tick)
            for symbol, tick in ticks.items()
        }
        return completed


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
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"live_run_{LIVE_RUN_LOG_STEM}.jsonl"


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


def hard_kill_armed_status(limits: RiskLimits = RISK_LIMITS) -> dict[str, Any]:
    """Return the live hard-kill thresholds for audit logging."""

    return {
        "margin_flatten_all_pct": EMERGENCY_MARGIN_LEVEL_PCT,
        "single_instrument_unrealized_pnl_floor": SINGLE_INSTRUMENT_UNREALIZED_FLOOR,
        "total_unrealized_pnl_floor": TOTAL_UNREALIZED_FLOOR,
        "session_peak_drawdown_pct": SESSION_DRAWDOWN_PCT,
        "per_trade_volume_cap": limits.active.max_lot_per_order,
        "symbol_volume_overrides": {
            symbol: override.max_lot_per_order for symbol, override in limits.symbol_overrides.items()
        },
        "session_total_loss_usd": SESSION_TOTAL_LOSS_USD,
        "trade_count_anomaly": {
            "count": TRADE_ANOMALY_COUNT,
            "window_seconds": int(TRADE_ANOMALY_WINDOW.total_seconds()),
        },
    }


def initialize_live_risk_state(
    account: AccountSnapshot,
    *,
    session_start_equity: Decimal | None = None,
    now: datetime | None = None,
) -> LiveRiskState:
    """Create live risk state and log the session-loss baseline."""

    if session_start_equity is None:
        state = LiveRiskState.from_account(account)
        baseline_source = "account_snapshot"
    else:
        state = LiveRiskState(
            session_start_equity=session_start_equity,
            session_peak_equity=max(session_start_equity, account.equity),
        )
        baseline_source = "cli_override"
    log_strategy_event(
        "live_session_risk_started",
        {
            "session_start_equity": state.session_start_equity,
            "session_loss_floor": state.session_start_equity - SESSION_TOTAL_LOSS_USD,
            "baseline_source": baseline_source,
            "account_equity_at_start": account.equity,
            "hard_kills_armed": hard_kill_armed_status(),
        },
        now=now,
    )
    return state


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


def _bucket_timestamp(timestamp: datetime, minutes: int) -> datetime:
    utc = timestamp.astimezone(timezone.utc) if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
    minute = (utc.minute // minutes) * minutes
    return utc.replace(minute=minute, second=0, microsecond=0)


def _strategy_position(position: PositionSnapshot) -> Position:
    return Position(symbol=position.symbol, lots=position.signed_lots, avg_price=position.price)


def _strategy_account_state(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    ticks: dict[str, Tick],
) -> StrategyAccountState:
    return StrategyAccountState(
        balance=account.balance or account.equity,
        equity=account.equity,
        leverage=account.leverage or Decimal("30"),
        positions={
            position.symbol: _strategy_position(position)
            for position in positions
            if position.signed_lots != 0
        },
        latest_ticks=ticks,
    )


def _pip_sizes_by_symbol() -> dict[str, Decimal]:
    from trifolium.adapter.market_data import load_instruments

    return {
        instrument.symbol: instrument.pip_size
        for instrument in load_instruments(ROOT / "config" / "instruments.yaml")
    }


def load_current_strategy_ticks(
    settings: StrategyV0Config,
    *,
    pip_sizes: dict[str, Decimal] | None = None,
) -> dict[str, Tick]:
    """Fetch one current tick per StrategyV0 symbol and convert to backtest tick shape."""

    from trifolium.adapter.market_data import get_tick

    resolved_pip_sizes = pip_sizes or _pip_sizes_by_symbol()
    ticks: dict[str, Tick] = {}
    errors: dict[str, str] = {}
    for symbol in settings.tradable_symbols:
        try:
            live_tick = get_tick(symbol, resolved_pip_sizes.get(symbol, Decimal("0.0001")))
        except Exception as exc:
            errors[symbol] = f"{type(exc).__name__}: {exc}"
            continue
        ticks[symbol] = Tick(
            timestamp=live_tick.time,
            symbol=symbol,
            bid=live_tick.bid,
            ask=live_tick.ask,
        )
    if errors:
        log_strategy_event("live_tick_errors", {"errors": errors})
    return ticks


def warmup_strategy_from_local_bars(
    strategy: StrategyV0,
    settings: StrategyV0Config,
    *,
    warmup_days: int = DEFAULT_WARMUP_DAYS,
) -> None:
    """Seed StrategyV0 predictor and bar history from the local historical dataset."""

    backtest_config = load_backtest_config()
    warmup_start = max(backtest_config.default_start, backtest_config.default_end - timedelta(days=warmup_days))
    by_time: dict[datetime, list[Bar]] = {}
    bar_counts: dict[str, int] = {}
    for symbol in settings.tradable_symbols:
        bars, _quality = load_symbol_bars(
            backtest_config.data_dir,
            symbol,
            warmup_start,
            backtest_config.default_end,
            minutes=settings.bar_interval_minutes,
        )
        if not bars:
            raise RuntimeError(f"Cannot warm up StrategyV0: no local bars for {symbol}")
        bar_counts[symbol] = len(bars)
        for bar in bars:
            by_time.setdefault(bar.timestamp, []).append(bar)

    for timestamp in sorted(by_time):
        for bar in sorted(by_time[timestamp], key=lambda item: item.symbol):
            if strategy.should_call_on_bar_close(bar):
                strategy._append_bar(bar)  # type: ignore[attr-defined]
    strategy.recalibrate_from_bars(getattr(strategy, "_bar_history", {}))
    if not getattr(strategy, "_predictor").has_active_models:
        raise RuntimeError("Cannot warm up StrategyV0: predictor has no active models after local-bar fit")
    log_strategy_event(
        "strategy_warmup_completed",
        {
            "warmup_start": warmup_start,
            "warmup_end": backtest_config.default_end,
            "warmup_days": warmup_days,
            "bar_counts": bar_counts,
            "destroyer_symbols": sorted(strategy.destroyer_symbols),
            "source_data_dir": str(backtest_config.data_dir),
        },
    )


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


def _order_request_from_strategy_order(
    order: Order,
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    ticks: dict[str, Tick],
    settings: StrategyV0Config,
) -> OrderRequest | None:
    tick = ticks.get(order.symbol)
    if tick is None:
        log_strategy_event("strategy_order_skipped_no_tick", {"order": order})
        return None
    price = tick.ask if order.side == "buy" else tick.bid
    contract_size = settings.instrument_contract_size.get(order.symbol, Decimal("100000"))
    return OrderRequest(
        symbol=order.symbol,
        side=order.side,
        lots=order.lots,
        price=price,
        contract_size=contract_size,
        strategy_notional=order.lots * contract_size * price,
        comment=order.tag or "strategy_v0_live",
        existing_positions=positions,
        account=account,
    )


def submit_strategy_orders(
    orders: list[Order],
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    ticks: dict[str, Tick],
    settings: StrategyV0Config,
    state: LiveRiskState,
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
    now: datetime | None = None,
) -> list[OrderResult]:
    """Submit StrategyV0 orders through the Risk Gate and record live telemetry."""

    timestamp = now or datetime.now(timezone.utc)
    results: list[OrderResult] = []
    for order in orders:
        request = _order_request_from_strategy_order(order, account, positions, ticks, settings)
        if request is None:
            continue
        result = submitter(request)
        results.append(result)
        if result.status in {"accepted", "submitted", "filled"}:
            state.record_trade(timestamp)
        log_strategy_event("strategy_order_result", {"order": order, "request": request, "result": result}, now=timestamp)
    return results


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


def _position_unrealized_pnl(position: PositionSnapshot) -> Decimal:
    return position.unrealized_pnl if position.unrealized_pnl is not None else Decimal("0")


def _unrealized_by_symbol(positions: list[PositionSnapshot]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for position in positions:
        totals[position.symbol] = totals.get(position.symbol, Decimal("0")) + _position_unrealized_pnl(position)
    return totals


def close_instrument_positions(
    symbol: str,
    positions: list[PositionSnapshot],
    account: AccountSnapshot,
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
) -> list[OrderResult]:
    """Close all net positions for one symbol through the Risk Gate."""

    matching = [position for position in positions if position.symbol == symbol and position.signed_lots != 0]
    results = emergency_flatten_positions(matching, account, submitter=submitter)
    log_strategy_event("hard_kill_close_instrument", {"symbol": symbol, "results": results})
    return results


def halt_loop(state: LiveRiskState, reason: str, payload: dict[str, Any] | None = None) -> None:
    """Mark the live loop halted and log a critical audit event."""

    state.halted = True
    state.halt_reason = reason
    log_strategy_event("live_loop_halted", {"reason": reason, "payload": payload or {}})


def _flatten_all_and_halt(
    state: LiveRiskState,
    reason: str,
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
    payload: dict[str, Any] | None = None,
) -> list[OrderResult]:
    results = emergency_flatten_positions(positions, account, submitter=submitter)
    halt_loop(state, reason, {"account": account, "positions": positions, "flatten_results": results, **(payload or {})})
    return results


def apply_hard_kills(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    state: LiveRiskState,
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
    now: datetime | None = None,
) -> list[OrderResult]:
    """Apply the seven live hard kills before any strategy order is considered."""

    timestamp = now or datetime.now(timezone.utc)
    account.open_positions_count = len(positions)
    state.update_peak(account.equity)
    results: list[OrderResult] = []

    if positions and account.margin_level_pct is not None and account.margin_level_pct < EMERGENCY_MARGIN_LEVEL_PCT:
        log_strategy_event("hard_kill_margin_level", {"account": account, "positions": positions}, now=timestamp)
        return _flatten_all_and_halt(
            state,
            f"margin_level_below_{EMERGENCY_MARGIN_LEVEL_PCT}",
            account,
            positions,
            submitter=submitter,
            payload={"margin_level_pct": account.margin_level_pct},
        )

    by_symbol = _unrealized_by_symbol(positions)
    for symbol, unrealized in sorted(by_symbol.items()):
        if unrealized < SINGLE_INSTRUMENT_UNREALIZED_FLOOR:
            log_strategy_event(
                "hard_kill_single_instrument_loss",
                {"symbol": symbol, "unrealized_pnl": unrealized, "floor": SINGLE_INSTRUMENT_UNREALIZED_FLOOR},
                now=timestamp,
            )
            results.extend(close_instrument_positions(symbol, positions, account, submitter=submitter))

    total_unrealized = sum((_position_unrealized_pnl(position) for position in positions), Decimal("0"))
    if total_unrealized < TOTAL_UNREALIZED_FLOOR:
        log_strategy_event(
            "hard_kill_total_unrealized_loss",
            {"total_unrealized_pnl": total_unrealized, "floor": TOTAL_UNREALIZED_FLOOR},
            now=timestamp,
        )
        return results + _flatten_all_and_halt(
            state,
            f"total_unrealized_pnl_below_{TOTAL_UNREALIZED_FLOOR}",
            account,
            positions,
            submitter=submitter,
            payload={"total_unrealized_pnl": total_unrealized},
        )

    session_drawdown_floor = state.session_peak_equity * (Decimal("1") - SESSION_DRAWDOWN_PCT / Decimal("100"))
    if account.equity < session_drawdown_floor:
        log_strategy_event(
            "hard_kill_session_drawdown",
            {"equity": account.equity, "peak": state.session_peak_equity, "floor": session_drawdown_floor},
            now=timestamp,
        )
        return results + _flatten_all_and_halt(
            state,
            f"session_drawdown_gt_{SESSION_DRAWDOWN_PCT}_pct",
            account,
            positions,
            submitter=submitter,
            payload={"session_peak_equity": state.session_peak_equity, "drawdown_floor": session_drawdown_floor},
        )

    session_loss_floor = state.session_start_equity - SESSION_TOTAL_LOSS_USD
    if account.equity <= session_loss_floor:
        log_strategy_event(
            "hard_kill_session_total_loss",
            {"equity": account.equity, "session_start_equity": state.session_start_equity, "floor": session_loss_floor},
            now=timestamp,
        )
        return results + _flatten_all_and_halt(
            state,
            f"session_loss_ge_{SESSION_TOTAL_LOSS_USD}",
            account,
            positions,
            submitter=submitter,
            payload={"session_start_equity": state.session_start_equity, "session_loss_floor": session_loss_floor},
        )

    if state.recent_trade_count(timestamp) > TRADE_ANOMALY_COUNT:
        log_strategy_event(
            "hard_kill_trade_count_anomaly",
            {"recent_trade_count": state.recent_trade_count(timestamp), "window": str(TRADE_ANOMALY_WINDOW)},
            now=timestamp,
        )
        return results + _flatten_all_and_halt(
            state,
            f"trade_count_gt_{TRADE_ANOMALY_COUNT}_in_30m",
            account,
            positions,
            submitter=submitter,
        )

    return results


def check_margin_or_flatten(
    account: AccountSnapshot,
    positions: list[PositionSnapshot],
    *,
    submitter: Callable[[OrderRequest], OrderResult] = submit_order,
) -> list[OrderResult]:
    if not positions or account.margin_level_pct is None or account.margin_level_pct >= EMERGENCY_MARGIN_LEVEL_PCT:
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
    account.open_positions_count = len(positions)
    log_account_state(account, positions)
    state = LiveRiskState.from_account(account)
    apply_hard_kills(account, positions, state)
    if state.halted:
        raise RuntimeError(f"Refusing live start: hard kill triggered during readiness ({state.halt_reason})")
    log_strategy_event(
        "readiness_check_passed",
        {"account": account, "positions": positions, "hard_kills_armed": hard_kill_armed_status(limits)},
    )
    return [
        "risk_gate_production",
        "legacy_audusd_flat",
        "account_state_logged",
        "hard_kill_margin_flatten_ready",
        "hard_kill_single_instrument_loss_ready",
        "hard_kill_total_unrealized_loss_ready",
        "hard_kill_session_drawdown_ready",
        "hard_kill_per_trade_volume_cap_ready",
        "hard_kill_session_total_loss_ready",
        "hard_kill_trade_count_anomaly_ready",
        "strategy_jsonl_logging_ready",
    ]


def run_live_loop(
    iterations: int | None = None,
    *,
    sleep_seconds: int = SLEEP_SECONDS,
    warmup_days: int = DEFAULT_WARMUP_DAYS,
    session_start_equity: Decimal | None = None,
) -> None:
    settings = load_strategy_v0_config()
    strategy = StrategyV0()
    pip_sizes = _pip_sizes_by_symbol()
    account = get_live_account_snapshot()
    positions = get_live_positions_snapshot()
    account.open_positions_count = len(positions)
    risk_state = initialize_live_risk_state(account, session_start_equity=session_start_equity)
    warmup_strategy_from_local_bars(strategy, settings, warmup_days=warmup_days)
    bar_aggregator = LiveBarAggregator(minutes=settings.bar_interval_minutes)
    log_strategy_event(
        "live_config_loaded",
        {
            "allowed_sessions": settings.trader.allowed_sessions,
            "flatten_disallowed_sessions": settings.trader.flatten_disallowed_sessions,
            "cost_gate_spread_multiplier": settings.trader.cost_gate_spread_multiplier,
            "cost_gate_min_abs_signal": settings.trader.cost_gate_min_abs_signal,
            "max_lots_by_symbol": settings.trader.max_lots_by_symbol,
            "max_symbol_notional_pct": settings.portfolio.max_symbol_notional_pct,
            "max_single_symbol_concentration_pct": settings.portfolio.max_single_symbol_concentration_pct,
            "tradable_symbols": settings.tradable_symbols,
        },
    )
    log_strategy_event(
        "strategy_started",
        {
            "strategy": strategy.name,
            "symbols": settings.tradable_symbols,
            "hard_kills_armed": hard_kill_armed_status(),
            "destroyer_symbols": sorted(strategy.destroyer_symbols),
        },
    )
    count = 0
    while iterations is None or count < iterations:
        now = datetime.now(timezone.utc)
        account = get_live_account_snapshot()
        positions = get_live_positions_snapshot()
        account.open_positions_count = len(positions)
        log_account_state(account, positions)
        apply_hard_kills(account, positions, risk_state, now=now)
        if risk_state.halted:
            log_strategy_event("heartbeat_skipped_halted", {"reason": risk_state.halt_reason}, now=now)
            break

        ticks = load_current_strategy_ticks(settings, pip_sizes=pip_sizes)
        if len(ticks) != len(settings.tradable_symbols):
            missing = [symbol for symbol in settings.tradable_symbols if symbol not in ticks]
            log_strategy_event("strategy_decision_skipped_missing_ticks", {"missing_symbols": missing}, now=now)
        else:
            completed_bars = bar_aggregator.update(ticks, settings.tradable_symbols)
            if completed_bars:
                strategy_state = _strategy_account_state(account, positions, ticks)
                orders: list[Order] = []
                for bar in completed_bars:
                    if strategy.should_call_on_bar_close(bar):
                        orders.extend(strategy.on_bar_close(bar, strategy_state.clone_for_strategy()))
                results = submit_strategy_orders(orders, account, positions, ticks, settings, risk_state, now=now)
                if results:
                    refreshed_account = get_live_account_snapshot()
                    refreshed_positions = get_live_positions_snapshot()
                    refreshed_account.open_positions_count = len(refreshed_positions)
                    apply_hard_kills(refreshed_account, refreshed_positions, risk_state, now=now)
            else:
                log_strategy_event(
                    "strategy_waiting_for_bar_close",
                    {"current_bucket": bar_aggregator.current_bucket, "sampled_symbols": sorted(bar_aggregator.builders)},
                    now=now,
                )
        log_strategy_event(
            "heartbeat",
            {
                "strategy": strategy.name,
                "destroyer_symbols": sorted(strategy.destroyer_symbols),
                "last_signals": strategy.last_signals,
                "portfolio_messages": strategy.portfolio_messages,
                "session_start_equity": risk_state.session_start_equity,
                "session_peak_equity": risk_state.session_peak_equity,
                "recent_trade_count_30m": risk_state.recent_trade_count(now),
                "halted": risk_state.halted,
                "halt_reason": risk_state.halt_reason,
            },
            now=now,
        )
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(sleep_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-approved", action="store_true", help="Principal-only acknowledgement required before live loop.")
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=int, default=SLEEP_SECONDS)
    parser.add_argument("--warmup-days", type=int, default=DEFAULT_WARMUP_DAYS)
    parser.add_argument(
        "--session-start-equity",
        type=Decimal,
        default=None,
        help="Preserve the original live-run equity baseline across a supervised restart.",
    )
    args = parser.parse_args()

    from trifolium.adapter.mt5_client import mt5_session

    with mt5_session():
        checks = run_readiness_checks()
        print("readiness_passed: " + ", ".join(checks))
        if not args.live_approved:
            print("live loop not started: pass --live-approved only after principal go-ahead")
            return 0
        run_live_loop(
            iterations=args.iterations,
            sleep_seconds=args.sleep_seconds,
            warmup_days=args.warmup_days,
            session_start_equity=args.session_start_equity,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
