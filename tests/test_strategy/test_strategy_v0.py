from datetime import datetime, timezone
from decimal import Decimal

from trifolium.backtest.types import AccountState, Bar, Tick
from trifolium.strategy.v0.config import load_strategy_v0_config
from trifolium.strategy.v0.portfolio import apply_portfolio_scaling, check_gross_leverage
from trifolium.strategy.v0.strategy import StrategyV0
from trifolium.strategy.v0.trader import compute_signal, cross_sectional_filter, exposure_to_lot, signal_to_exposure


def test_strategy_v0_config_loads() -> None:
    settings = load_strategy_v0_config()
    assert "EURCHF" not in settings.tradable_symbols
    assert len(settings.tradable_symbols) == 9
    assert settings.instrument_contract_size["XAGUSD"] == Decimal("5000")


def test_trader_signal_sizing_and_cross_section() -> None:
    settings = load_strategy_v0_config()
    signal = compute_signal(0.01, 0.002, settings)
    assert 0 < signal < 1
    exposure = signal_to_exposure(signal, settings)
    assert exposure > 0
    directions = cross_sectional_filter(
        {
            "EURUSD": 0.9,
            "GBPUSD": 0.8,
            "USDJPY": 0.7,
            "USDCHF": 0.1,
            "USDCAD": 0.0,
            "AUDUSD": -0.1,
            "EURGBP": -0.7,
            "XAUUSD": -0.8,
            "XAGUSD": -0.9,
        },
        settings,
    )
    assert directions["EURUSD"] == 1
    assert directions["XAGUSD"] == -1
    assert directions["USDCAD"] == 0


def test_exposure_to_lot_uses_configured_contract_sizes() -> None:
    settings = load_strategy_v0_config()
    lot = exposure_to_lot("AUDUSD", Decimal("0.01"), Decimal("1000000"), Decimal("0.7000"), settings)
    assert lot > 0
    xag_lot = exposure_to_lot("XAGUSD", Decimal("0.01"), Decimal("1000000"), Decimal("30"), settings)
    assert xag_lot > 0


def test_portfolio_scaling_reduces_gross_leverage() -> None:
    settings = load_strategy_v0_config()
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")
    targets = {symbol: Decimal("10") for symbol in settings.tradable_symbols}
    scaled, scale, _messages = apply_portfolio_scaling(targets, prices, Decimal("1000000"), settings)
    assert Decimal("0") <= scale <= Decimal("1")
    ok, _message = check_gross_leverage(
        [(symbol, lot, prices[symbol]) for symbol, lot in scaled.items()],
        Decimal("1000000"),
        settings,
    )
    assert ok


def test_strategy_v0_instantiates_and_stays_flat_without_training() -> None:
    strategy = StrategyV0()
    assert strategy.name == "strategy_v0"
    assert len(strategy.symbols) == 9
    timestamp = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
    account = AccountState(balance=Decimal("1000000"), equity=Decimal("1000000"))
    for symbol in strategy.symbols:
        account.latest_ticks[symbol] = Tick(timestamp=timestamp, symbol=symbol, bid=Decimal("1.0"), ask=Decimal("1.0001"))
    bar = Bar(
        timestamp=timestamp,
        symbol="EURUSD",
        open=Decimal("1.0"),
        high=Decimal("1.0"),
        low=Decimal("1.0"),
        close=Decimal("1.0"),
        bid=Decimal("1.0"),
        ask=Decimal("1.0001"),
    )
    assert strategy.on_tick(account.latest_ticks["EURUSD"], account) == []
    assert strategy.on_bar_close(bar, account) == []
