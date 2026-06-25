from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd

from trifolium.backtest.bar_engine import bar_backtest
from trifolium.backtest.types import AccountState, Bar, Order, Tick
from trifolium.strategy.base import Strategy


class BarOnlyNoopStrategy(Strategy):
    name: str = "bar_only_noop"
    symbols: list[str] = ["AUDUSD", "EURUSD"]

    def should_call_on_tick(self, tick: Tick) -> bool:
        return False

    def should_call_on_bar_close(self, bar: Bar) -> bool:
        return True

    def on_bar_close(self, bar: Bar, state: AccountState) -> list[Order]:
        return []


def _write_ticks(path, symbol: str) -> None:
    rows = []
    start = datetime(2026, 5, 11, tzinfo=timezone.utc)
    for index in range(20):
        timestamp = start + timedelta(minutes=index)
        rows.append(
            {
                "time": timestamp.replace(tzinfo=None).isoformat(sep=" "),
                "sym": symbol,
                "provider": "test",
                "valuedate": "2026-05-11",
                "received": timestamp.replace(tzinfo=None).isoformat(sep=" "),
                "bid": 1.0 + index * 0.0001,
                "ask": 1.0002 + index * 0.0001,
                "bidprices": [1.0],
                "bidsizes": [1],
                "askprices": [1.0002],
                "asksizes": [1],
            }
        )
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_bar_backtest_aggregates_small_parquet_fixture(tmp_path):
    _write_ticks(tmp_path / "AUDUSD_2026_05_11.parquet", "AUDUSD")
    _write_ticks(tmp_path / "EURUSD_2026_05_11.parquet", "EURUSD")

    result = bar_backtest(
        BarOnlyNoopStrategy(),
        ["AUDUSD", "EURUSD"],
        datetime(2026, 5, 11, tzinfo=timezone.utc),
        datetime(2026, 5, 11, 0, 20, tzinfo=timezone.utc),
        Decimal("1000000"),
        data_dir=tmp_path,
    )

    assert result.trade_count == 0
    assert result.final_equity == Decimal("1000000")
    assert result.data_quality.processed_ticks == 40
