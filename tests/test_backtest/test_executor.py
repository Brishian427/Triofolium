from datetime import datetime, timezone
from decimal import Decimal

from trifolium.backtest.config import InstrumentSpec
from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, Order, Tick


def tick(bid: str, ask: str) -> Tick:
    return Tick(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), symbol="AUDUSD", bid=Decimal(bid), ask=Decimal(ask))


def executor() -> Executor:
    return Executor({"AUDUSD": InstrumentSpec("AUDUSD", "fx", Decimal("100000"), Decimal("0.0001"), Decimal("0.01"))})


def test_spread_cost_round_trip() -> None:
    ex = executor()
    account = AccountState()
    t = tick("0.7000", "0.7002")
    account.latest_ticks["AUDUSD"] = t
    ex.simulate_fill(Order(symbol="AUDUSD", side="buy", lots=Decimal("0.01")), t, account)
    ex.simulate_fill(Order(symbol="AUDUSD", side="sell", lots=Decimal("0.01")), t, account)
    assert account.balance == Decimal("999999.800000")


def test_netting_correctness() -> None:
    ex = executor()
    account = AccountState()
    t = tick("0.7000", "0.7000")
    account.latest_ticks["AUDUSD"] = t
    ex.simulate_fill(Order(symbol="AUDUSD", side="buy", lots=Decimal("0.02")), t, account)
    ex.simulate_fill(Order(symbol="AUDUSD", side="sell", lots=Decimal("0.01")), t, account)
    assert account.positions["AUDUSD"].lots == Decimal("0.01")


def test_stop_out_closes_positions() -> None:
    ex = executor()
    account = AccountState(balance=Decimal("100"), equity=Decimal("100"))
    t = tick("0.7000", "0.7000")
    account.latest_ticks["AUDUSD"] = t
    ex.simulate_fill(Order(symbol="AUDUSD", side="buy", lots=Decimal("10")), t, account)
    crash = tick("0.1000", "0.1001")
    account.latest_ticks["AUDUSD"] = crash
    ex.mark_to_market(account)
    fills = ex.enforce_stop_out(account, crash)
    assert fills
    assert not account.positions
