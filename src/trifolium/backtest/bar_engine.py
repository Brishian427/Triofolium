"""Bar-level backtest path for strategies that do not consume raw ticks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from trifolium.backtest.config import load_backtest_config, load_instrument_specs
from trifolium.backtest.data_loader import symbol_files
from trifolium.backtest.equity_tracker import EquityTracker
from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, BacktestResult, Bar, DataQualityStats, Order, Tick, Trade
from trifolium.strategy.base import Strategy


def _naive_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(timezone.utc).replace(tzinfo=None)


def _to_utc_datetime(value: pd.Timestamp) -> datetime:
    if value.tzinfo is None:
        return value.to_pydatetime().replace(tzinfo=timezone.utc)
    return value.to_pydatetime().astimezone(timezone.utc)


def _decimal(value: float | int) -> Decimal:
    return Decimal(str(value))


def _chunk_bars(table: pa.Table, symbol: str, start: datetime, end: datetime, minutes: int) -> tuple[pd.DataFrame, int, int]:
    timestamp_type = pa.timestamp("us")
    parsed_time = pc.cast(table["time"], timestamp_type)
    valid_price = pc.and_(pc.is_valid(table["bid"]), pc.is_valid(table["ask"]))
    valid_price = pc.and_(valid_price, pc.less(table["bid"], table["ask"]))
    invalid_count = int(pc.sum(pc.cast(pc.invert(valid_price), "int64")).as_py() or 0)
    in_range = pc.and_(
        pc.greater_equal(parsed_time, pa.scalar(_naive_utc(start), type=timestamp_type)),
        pc.less(parsed_time, pa.scalar(_naive_utc(end), type=timestamp_type)),
    )
    mask = pc.and_(valid_price, in_range)
    selected = int(pc.sum(pc.cast(mask, "int64")).as_py() or 0)
    if selected == 0:
        return pd.DataFrame(), 0, invalid_count

    filtered = table.append_column("_timestamp", parsed_time).filter(mask)
    frame = filtered.select(["_timestamp", "bid", "ask"]).to_pandas()
    frame["_timestamp"] = pd.to_datetime(frame["_timestamp"], utc=True)
    frame["mid"] = (frame["bid"] + frame["ask"]) / 2.0
    frame["bucket"] = frame["_timestamp"].dt.floor(f"{minutes}min")
    frame["symbol"] = symbol
    grouped = (
        frame.groupby("bucket", sort=True)
        .agg(
            first_time=("_timestamp", "first"),
            last_time=("_timestamp", "last"),
            open=("mid", "first"),
            high=("mid", "max"),
            low=("mid", "min"),
            close=("mid", "last"),
            bid=("bid", "last"),
            ask=("ask", "last"),
            volume=("mid", "count"),
        )
        .reset_index()
    )
    return grouped, selected, invalid_count


def load_symbol_bars(
    data_dir: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    minutes: int = 15,
) -> tuple[list[Bar], DataQualityStats]:
    """Aggregate one symbol's parquet ticks into fixed-width OHLCV bars."""

    chunks: list[pd.DataFrame] = []
    quality = DataQualityStats()
    for path in symbol_files(data_dir, symbol, start, end):
        parquet_file = pq.ParquetFile(path)
        for row_group in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(row_group, columns=["time", "bid", "ask"])
            bars, processed, skipped = _chunk_bars(table, symbol, start, end, minutes)
            quality.processed_ticks += processed
            quality.skipped_ticks += skipped
            if not bars.empty:
                chunks.append(bars)

    if not chunks:
        return [], quality

    combined = pd.concat(chunks, ignore_index=True)
    rows: list[dict[str, object]] = []
    for bucket, group in combined.groupby("bucket", sort=True):
        first = group.sort_values("first_time").iloc[0]
        last = group.sort_values("last_time").iloc[-1]
        rows.append(
            {
                "timestamp": bucket,
                "open": first["open"],
                "high": group["high"].max(),
                "low": group["low"].min(),
                "close": last["close"],
                "bid": last["bid"],
                "ask": last["ask"],
                "volume": int(group["volume"].sum()),
            }
        )

    output: list[Bar] = []
    for row in rows:
        output.append(
            Bar(
                timestamp=_to_utc_datetime(pd.Timestamp(row["timestamp"])),
                symbol=symbol,
                open=_decimal(float(row["open"])),
                high=_decimal(float(row["high"])),
                low=_decimal(float(row["low"])),
                close=_decimal(float(row["close"])),
                bid=_decimal(float(row["bid"])),
                ask=_decimal(float(row["ask"])),
                volume=Decimal(int(row["volume"])),
                spread_pips=Decimal("0"),
            )
        )
    return output, quality


def _merge_quality(qualities: Iterable[DataQualityStats]) -> DataQualityStats:
    merged = DataQualityStats()
    for quality in qualities:
        merged.processed_ticks += quality.processed_ticks
        merged.skipped_ticks += quality.skipped_ticks
        merged.skipped_examples.extend(quality.skipped_examples)
    return merged


def _bar_tick(bar: Bar) -> Tick:
    return Tick(timestamp=bar.timestamp, symbol=bar.symbol, bid=bar.bid, ask=bar.ask, volume=bar.volume)


def _is_bar_only(strategy: Strategy, bars_by_symbol: dict[str, list[Bar]]) -> bool:
    for bars in bars_by_symbol.values():
        if bars and strategy.should_call_on_tick(_bar_tick(bars[0])):
            return False
    return True


def bar_backtest(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal = Decimal("1000000"),
    *,
    data_dir: Path | None = None,
    bar_minutes: int = 15,
    recalibrate_daily: bool = True,
    warmup_start: datetime | None = None,
    warmup_recalibrate_at_start: bool = False,
) -> BacktestResult:
    """Run a multi-symbol bar-close backtest for bar-only strategies."""

    config = load_backtest_config()
    source_dir = data_dir or config.data_dir
    bars_by_symbol: dict[str, list[Bar]] = {}
    for symbol in symbols:
        bars, _quality = load_symbol_bars(source_dir, symbol, start, end, minutes=bar_minutes)
        bars_by_symbol[symbol] = bars
    return bar_backtest_from_bars(
        strategy,
        symbols,
        start,
        end,
        initial_equity,
        bars_by_symbol=bars_by_symbol,
        bar_minutes=bar_minutes,
        recalibrate_daily=recalibrate_daily,
        warmup_start=warmup_start,
        warmup_recalibrate_at_start=warmup_recalibrate_at_start,
    )


def bar_backtest_from_bars(
    strategy: Strategy,
    symbols: list[str],
    start: datetime,
    end: datetime,
    initial_equity: Decimal = Decimal("1000000"),
    *,
    bars_by_symbol: dict[str, list[Bar]],
    bar_minutes: int = 15,
    recalibrate_daily: bool = True,
    warmup_start: datetime | None = None,
    warmup_recalibrate_at_start: bool = False,
) -> BacktestResult:
    """Run a bar backtest from pre-aggregated bars, slicing by run window."""

    if not _is_bar_only(strategy, bars_by_symbol):
        raise ValueError("bar_backtest requires a strategy that declares bar-only behavior")

    config = load_backtest_config()
    executor = Executor(load_instrument_specs(), leverage=config.leverage)
    account = AccountState(balance=initial_equity, equity=initial_equity, leverage=config.leverage)
    tracker = EquityTracker(initial_equity, executor)
    trades: list[Trade] = []
    recalibrated_dates: set[datetime.date] = set()

    if warmup_start is not None and warmup_start < start and hasattr(strategy, "_append_bar"):
        warmup_times: dict[datetime, list[Bar]] = {}
        for bars in bars_by_symbol.values():
            for bar in bars:
                if warmup_start <= bar.timestamp < start:
                    warmup_times.setdefault(bar.timestamp, []).append(bar)
        for timestamp in sorted(warmup_times):
            for bar in sorted(warmup_times[timestamp], key=lambda item: item.symbol):
                if strategy.should_call_on_bar_close(bar):
                    strategy._append_bar(bar)  # type: ignore[attr-defined]
        if warmup_recalibrate_at_start and hasattr(strategy, "recalibrate_from_bars"):
            strategy.recalibrate_from_bars(getattr(strategy, "_bar_history", {}))

    by_time: dict[datetime, list[Bar]] = {}
    quality = DataQualityStats()
    for bars in bars_by_symbol.values():
        for bar in bars:
            if bar.timestamp < start or bar.timestamp >= end:
                continue
            quality.processed_ticks += int(bar.volume)
            by_time.setdefault(bar.timestamp, []).append(bar)

    def apply_orders(orders: list[Order]) -> None:
        for order in orders:
            tick = account.latest_ticks.get(order.symbol)
            if tick is None:
                continue
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

    for timestamp in sorted(by_time):
        current_bars = sorted(by_time[timestamp], key=lambda item: item.symbol)
        for bar in current_bars:
            account.latest_ticks[bar.symbol] = _bar_tick(bar)
        executor.mark_to_market(account)
        tracker.tick(timestamp, account)

        for bar in current_bars:
            if strategy.should_call_on_bar_close(bar):
                apply_orders(strategy.on_bar_close(bar, account.clone_for_strategy()))

        if recalibrate_daily and hasattr(strategy, "recalibrate_from_bars"):
            if timestamp.hour == 21 and timestamp.minute == 0 and timestamp.date() not in recalibrated_dates:
                strategy.recalibrate_from_bars(getattr(strategy, "_bar_history", {}))
                recalibrated_dates.add(timestamp.date())

        for tick in list(account.latest_ticks.values()):
            fills = executor.process_pending_orders(tick, account)
            for fill in fills:
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
            executor.enforce_stop_out(account, tick)

    executor.mark_to_market(account)
    tracker.sample(end, account)
    return BacktestResult(
        strategy_name=strategy.name,
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
