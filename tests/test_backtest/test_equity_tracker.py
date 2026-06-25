from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trifolium.backtest.config import InstrumentSpec
from trifolium.backtest.equity_tracker import EquityTracker
from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, Position, Tick


def test_sharpe_matches_mean_over_std_for_known_input() -> None:
    ex = Executor({"AUDUSD": InstrumentSpec("AUDUSD", "fx", Decimal("100000"), Decimal("0.0001"), Decimal("0.01"))})
    tracker = EquityTracker(Decimal("100"), ex)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    equities = [Decimal("100"), Decimal("101"), Decimal("100"), Decimal("102"), Decimal("101"), Decimal("103"), Decimal("102"), Decimal("104"), Decimal("103")]
    for i, equity in enumerate(equities):
        account = AccountState(balance=equity, equity=equity)
        tracker.sample(start + timedelta(minutes=15 * i), account)
    returns = [float((b - a) / a) for a, b in zip(equities, equities[1:], strict=False)]
    expected = sum(returns) / len(returns)
    variance = sum((item - expected) ** 2 for item in returns) / len(returns)
    assert abs(float(tracker.sharpe()) - expected / (variance**0.5)) < 1e-12


def test_sharpe_none_when_fewer_than_8_intervals() -> None:
    ex = Executor({"AUDUSD": InstrumentSpec("AUDUSD", "fx", Decimal("100000"), Decimal("0.0001"), Decimal("0.01"))})
    tracker = EquityTracker(Decimal("100"), ex)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(4):
        tracker.sample(start + timedelta(minutes=15 * i), AccountState(balance=Decimal("100"), equity=Decimal("100")))
    assert tracker.sharpe() is None


def test_risk_concentration_uses_notional_not_raw_units() -> None:
    instruments = {
        "EURUSD": InstrumentSpec("EURUSD", "fx", Decimal("100000"), Decimal("0.0001"), Decimal("0.01")),
        "XAUUSD": InstrumentSpec("XAUUSD", "metal", Decimal("100"), Decimal("0.01"), Decimal("0.01")),
    }
    ex = Executor(instruments)
    tracker = EquityTracker(Decimal("1000000"), ex)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    account = AccountState(balance=Decimal("1000000"), equity=Decimal("1000000"))
    account.positions["EURUSD"] = Position(symbol="EURUSD", lots=Decimal("0.01"), avg_price=Decimal("1"))
    account.positions["XAUUSD"] = Position(symbol="XAUUSD", lots=Decimal("0.01"), avg_price=Decimal("5000"))
    account.latest_ticks["EURUSD"] = Tick(timestamp=timestamp, symbol="EURUSD", bid=Decimal("1"), ask=Decimal("1"))
    account.latest_ticks["XAUUSD"] = Tick(timestamp=timestamp, symbol="XAUUSD", bid=Decimal("5000"), ask=Decimal("5000"))

    tracker.sample(timestamp, account)

    assert tracker.max_concentration_seen == Decimal("0.8333333333333333333333333333")
