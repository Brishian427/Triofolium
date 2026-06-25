"""Streaming PyArrow data loader for xSyphon pricer parquet files."""

from __future__ import annotations

import heapq
import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pyarrow.compute as pc
import pyarrow.parquet as pq

from trifolium.backtest.config import ROOT, load_instrument_specs
from trifolium.backtest.types import Bar, DataQualityStats, Tick


Prefilter = Callable[[Tick], bool]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def symbol_files(data_dir: Path, symbol: str, start: datetime, end: datetime) -> list[Path]:
    files = []
    for path in sorted(data_dir.glob(f"{symbol}_*.parquet")):
        parts = path.stem.rsplit("_", 3)
        if len(parts) != 4:
            continue
        day = datetime(int(parts[1]), int(parts[2]), int(parts[3]), tzinfo=timezone.utc)
        if start.date() <= day.date() <= end.date():
            files.append(path)
    return files


def iter_ticks(
    symbol: str,
    start: datetime,
    end: datetime,
    data_dir: Path,
    *,
    prefilter: Prefilter | None = None,
    quality: DataQualityStats | None = None,
    quality_logger: logging.Logger | None = None,
) -> Iterator[Tick]:
    """Yield valid bid/ask ticks for a symbol without loading full files."""

    for path in symbol_files(data_dir, symbol, start, end):
        parquet_file = pq.ParquetFile(path)
        columns = [name for name in ["time", "sym", "bid", "ask"] if name in parquet_file.schema_arrow.names]
        for row_group in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(row_group, columns=columns)
            valid = pc.less(table["bid"], table["ask"])
            invalid = pc.invert(valid)
            invalid_count = int(pc.sum(pc.cast(invalid, "int64")).as_py() or 0)
            if invalid_count and quality is not None:
                quality.skipped_ticks += invalid_count
                examples = pc.filter(table["time"], invalid).slice(0, 5).to_pylist()
                for example in examples:
                    text = f"{symbol} {example}"
                    if len(quality.skipped_examples) < 100:
                        quality.skipped_examples.append(text)
                    if quality_logger is not None:
                        quality_logger.warning("skipped corrupt tick %s", text)
            valid_table = table.filter(valid)
            for row in valid_table.to_pylist():
                timestamp = parse_time(row["time"])
                if timestamp < start or timestamp >= end:
                    continue
                tick = Tick(
                    timestamp=timestamp,
                    symbol=symbol,
                    bid=Decimal(str(row["bid"])),
                    ask=Decimal(str(row["ask"])),
                )
                if prefilter is not None and not prefilter(tick):
                    continue
                yield tick


def bar_from_ticks(symbol: str, ticks: list[Tick], pip_size: Decimal, timestamp: datetime) -> Bar:
    mids = [tick.mid for tick in ticks]
    last = ticks[-1]
    return Bar(
        timestamp=timestamp,
        symbol=symbol,
        open=mids[0],
        high=max(mids),
        low=min(mids),
        close=mids[-1],
        bid=last.bid,
        ask=last.ask,
        volume=Decimal(len(ticks)),
        spread_pips=last.spread / pip_size,
    )


def floor_time(timestamp: datetime, minutes: int) -> datetime:
    discard_minutes = timestamp.minute % minutes
    return timestamp.replace(minute=timestamp.minute - discard_minutes, second=0, microsecond=0)


def load_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: Literal["tick", "1m", "5m", "15m", "1h"],
    *,
    data_dir: Path | None = None,
    prefilter: Prefilter | None = None,
) -> Iterator[Bar]:
    """Stream bars for one symbol from parquet tick data."""

    specs = load_instrument_specs()
    pip_size = specs[symbol].pip_size if symbol in specs else Decimal("0.0001")
    source_dir = data_dir or ROOT / "pricer-output-2026-05-11_2026-06-10"
    minutes = {"tick": 0, "1m": 1, "5m": 5, "15m": 15, "1h": 60}[timeframe]
    bucket: list[Tick] = []
    bucket_time: datetime | None = None
    for tick in iter_ticks(symbol, start, end, source_dir, prefilter=prefilter):
        if timeframe == "tick":
            yield bar_from_ticks(symbol, [tick], pip_size, tick.timestamp)
            continue
        current_bucket = floor_time(tick.timestamp, minutes)
        if bucket and bucket_time is not None and current_bucket != bucket_time:
            yield bar_from_ticks(symbol, bucket, pip_size, bucket_time)
            bucket = []
        bucket_time = current_bucket
        bucket.append(tick)
    if bucket and bucket_time is not None:
        yield bar_from_ticks(symbol, bucket, pip_size, bucket_time)


def merged_ticks(
    symbols: list[str],
    start: datetime,
    end: datetime,
    data_dir: Path,
    *,
    prefilter: Prefilter | None = None,
    quality: DataQualityStats | None = None,
    quality_logger: logging.Logger | None = None,
) -> Iterator[Tick]:
    """Merge multiple symbol tick streams into timestamp order."""

    streams = [
        iter_ticks(symbol, start, end, data_dir, prefilter=prefilter, quality=quality, quality_logger=quality_logger)
        for symbol in symbols
    ]
    heap: list[tuple[datetime, int, Tick, Iterator[Tick]]] = []
    for index, stream in enumerate(streams):
        try:
            tick = next(stream)
        except StopIteration:
            continue
        heapq.heappush(heap, (tick.timestamp, index, tick, stream))
    while heap:
        _timestamp, index, tick, stream = heapq.heappop(heap)
        yield tick
        try:
            next_tick = next(stream)
        except StopIteration:
            continue
        heapq.heappush(heap, (next_tick.timestamp, index, next_tick, stream))
