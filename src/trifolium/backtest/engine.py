"""Main offline backtest event loop."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trifolium.backtest.config import load_backtest_config, load_instrument_specs
from trifolium.backtest.data_loader import merged_ticks
from trifolium.backtest.equity_tracker import EquityTracker
from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, BacktestResult, Bar, DataQualityStats, Order, Tick, Trade


class FutureDataError(AssertionError):
    """Raised when strategy-visible state contains data at or after simulated time."""


def _assert_no_future_data(state: AccountState, timestamp: datetime) -> None:
    for tick in state.market_history:
        if tick.timestamp >= timestamp:
            raise FutureDataError(
                f"strategy state contains future/current tick {tick.timestamp.isoformat()} at {timestamp.isoformat()}"
            )


def _quality_logger(run_id: str) -> logging.Logger:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger(f"data_quality_{run_id}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_dir / f"data_quality_{run_id}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def _tick_bar(tick: Tick) -> Bar:
    return Bar(
        timestamp=tick.timestamp.replace(second=0, microsecond=0),
        symbol=tick.symbol,
        open=tick.mid,
        high=tick.mid,
        low=tick.mid,
        close=tick.mid,
        bid=tick.bid,
        ask=tick.ask,
        volume=Decimal("1"),
        spread_pips=Decimal("0"),
    )


def backtest(
    strategy: object,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal = Decimal("1000000"),
    *,
    data_dir: Path | None = None,
    run_id: str | None = None,
) -> BacktestResult:
    """Run an offline event-driven backtest."""

    config = load_backtest_config()
    source_dir = data_dir or config.data_dir
    run_id = run_id or f"{getattr(strategy, 'name', 'strategy')}_{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}"
    quality = DataQualityStats()
    logger = _quality_logger(run_id)
    executor = Executor(load_instrument_specs(), leverage=config.leverage)
    account = AccountState(balance=initial_equity, equity=initial_equity, leverage=config.leverage)
    tracker = EquityTracker(initial_equity, executor)
    trades: list[Trade] = []
    current_minute: datetime | None = None

    def apply_orders(orders: list[Order], tick: Tick) -> None:
        for order in orders:
            fill = executor.simulate_fill(order, tick, account)
            if fill is None:
                continue
            trades.append(
                Trade(
                    timestamp=fill.timestamp,
                    symbol=fill.symbol,
                    side=fill.side,
                    lots=fill.lots,
                    price=fill.price,
                    realized_pnl=fill.realized_pnl,
                    equity_after=account.equity,
                    tag=fill.tag,
                )
            )

    for tick in merged_ticks(symbols, start, end, source_dir, quality=quality, quality_logger=logger):
        account.latest_ticks[tick.symbol] = tick
        executor.mark_to_market(account)
        tracker.tick(tick.timestamp, account)
        pending_fills = executor.process_pending_orders(tick, account)
        for fill in pending_fills:
            trades.append(
                Trade(
                    timestamp=fill.timestamp,
                    symbol=fill.symbol,
                    side=fill.side,
                    lots=fill.lots,
                    price=fill.price,
                    realized_pnl=fill.realized_pnl,
                    equity_after=account.equity,
                    tag=fill.tag,
                )
            )

        if strategy.should_call_on_tick(tick):
            visible_state = account.clone_for_strategy()
            visible_state.market_history = [item for item in visible_state.market_history if item.timestamp < tick.timestamp]
            _assert_no_future_data(visible_state, tick.timestamp)
            orders = strategy.on_tick(tick, visible_state)
            _assert_no_future_data(visible_state, tick.timestamp)
            apply_orders(orders, tick)

        minute = tick.timestamp.replace(second=0, microsecond=0)
        if current_minute is None:
            current_minute = minute
        elif minute > current_minute:
            bar = _tick_bar(tick)
            if strategy.should_call_on_bar_close(bar):
                bar_state = account.clone_for_strategy()
                bar_state.market_history = [item for item in bar_state.market_history if item.timestamp < tick.timestamp]
                _assert_no_future_data(bar_state, tick.timestamp)
                apply_orders(strategy.on_bar_close(bar, bar_state), tick)
            current_minute = minute

        account.market_history.append(tick)
        if len(account.market_history) > 16:
            account.market_history = account.market_history[-16:]
        executor.enforce_stop_out(account, tick)

    executor.mark_to_market(account)
    tracker.sample(end, account)
    return BacktestResult(
        strategy_name=getattr(strategy, "name", strategy.__class__.__name__),
        symbols=symbols,
        start=start,
        end=end,
        initial_equity=initial_equity,
        final_equity=account.equity,
        total_return=tracker.total_return(account.equity),
        max_drawdown=tracker.max_drawdown,
        sharpe=tracker.sharpe(),
        projected_risk_discipline=tracker.projected_risk_discipline(account),
        trade_count=len(trades),
        trades=trades,
        equity_curve=tracker.points,
        data_quality=quality,
        stop_out_events=account.stop_out_events,
        risk_events=account.risk_events,
    )
