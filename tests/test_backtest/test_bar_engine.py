from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from pydantic import PrivateAttr

from trifolium.backtest.bar_engine import bar_backtest, bar_backtest_from_bars
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


class WarmupAwareStrategy(Strategy):
    name: str = "warmup_aware"
    symbols: list[str] = ["AUDUSD"]

    _warmup_symbols: list[str] = PrivateAttr(default_factory=list)
    _recalibrations: int = PrivateAttr(default=0)

    def should_call_on_tick(self, tick: Tick) -> bool:
        return False

    def should_call_on_bar_close(self, bar: Bar) -> bool:
        return True

    def _append_bar(self, bar: Bar) -> None:
        self._warmup_symbols.append(bar.symbol)

    def recalibrate_from_bars(self, bars):
        self._recalibrations += 1

    @property
    def warmup_symbols(self) -> list[str]:
        return list(self._warmup_symbols)

    @property
    def recalibrations(self) -> int:
        return self._recalibrations


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


def test_bar_backtest_from_bars_can_prefit_from_warmup_bars():
    start = datetime(2026, 5, 11, 1, 0, tzinfo=timezone.utc)
    warmup = start - timedelta(minutes=15)
    strategy = WarmupAwareStrategy()
    bars = [
        Bar(
            timestamp=warmup,
            symbol="AUDUSD",
            open=Decimal("1.0"),
            high=Decimal("1.0"),
            low=Decimal("1.0"),
            close=Decimal("1.0"),
            bid=Decimal("0.9999"),
            ask=Decimal("1.0001"),
            volume=Decimal("1"),
            spread_pips=Decimal("0"),
        ),
        Bar(
            timestamp=start,
            symbol="AUDUSD",
            open=Decimal("1.0"),
            high=Decimal("1.0"),
            low=Decimal("1.0"),
            close=Decimal("1.0"),
            bid=Decimal("0.9999"),
            ask=Decimal("1.0001"),
            volume=Decimal("1"),
            spread_pips=Decimal("0"),
        ),
    ]

    result = bar_backtest_from_bars(
        strategy,
        ["AUDUSD"],
        start,
        start + timedelta(minutes=15),
        Decimal("1000000"),
        bars_by_symbol={"AUDUSD": bars},
        warmup_start=warmup,
        warmup_recalibrate_at_start=True,
    )

    assert result.trade_count == 0
    assert strategy.warmup_symbols == ["AUDUSD"]
    assert strategy.recalibrations == 1
