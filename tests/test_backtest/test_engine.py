from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from trifolium.backtest.engine import FutureDataError, backtest
from trifolium.backtest.types import AccountState, Tick
from trifolium.strategy.base import Strategy


class FutureLeakingStrategy(Strategy):
    name: str = "future_leaker"
    symbols: list[str] = ["AUDUSD"]

    def on_tick(self, tick: Tick, state: AccountState):
        state.market_history.append(tick)
        return []


def test_no_future_data_assertion_fires(tmp_path: Path) -> None:
    table = pa.table(
        {
            "time": ["2026-01-01 00:00:00.000000", "2026-01-01 00:00:01.000000"],
            "sym": ["AUDUSD", "AUDUSD"],
            "bid": [0.7000, 0.7001],
            "ask": [0.7002, 0.7003],
        }
    )
    pq.write_table(table, tmp_path / "AUDUSD_2026_01_01.parquet")
    with pytest.raises(FutureDataError):
        backtest(
            FutureLeakingStrategy(),
            ["AUDUSD"],
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            Decimal("1000000"),
            data_dir=tmp_path,
        )
