from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trifolium.backtest.types import AccountState, Bar, Tick
from trifolium.strategy.v0.config import SizingRow, load_strategy_v0_config
from trifolium.strategy.v0.portfolio import apply_portfolio_scaling, check_gross_leverage, check_single_symbol_concentration
from trifolium.strategy.v0.predictor import BarSnapshot
from trifolium.strategy.v0.strategy import StrategyV0
from trifolium.strategy.v0.trader import StrategyV0Trader, compute_signal, cross_sectional_filter, exposure_to_lot, passes_cost_gate, signal_to_exposure


def test_strategy_v0_config_loads() -> None:
    settings = load_strategy_v0_config()
    assert "EURCHF" not in settings.tradable_symbols
    assert settings.tradable_symbols == [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "USDCAD",
        "AUDUSD",
        "EURGBP",
        "XAUUSD",
        "XAGUSD",
    ]
    assert "XAUUSD" not in settings.hard_excluded_symbols
    assert "XAGUSD" not in settings.hard_excluded_symbols
    assert settings.instrument_contract_size["XAGUSD"] == Decimal("5000")
    assert settings.trader.max_lots_by_symbol["XAGUSD"] == Decimal("0.01")
    assert "london_morning" in settings.trader.allowed_sessions
    assert "london_ny_overlap" in settings.trader.allowed_sessions
    assert "ny_afternoon" in settings.trader.allowed_sessions
    assert "off_session" in settings.trader.allowed_sessions
    assert settings.trader.flatten_disallowed_sessions is False
    assert settings.portfolio.max_single_symbol_concentration_pct == Decimal("100")
    assert settings.portfolio.max_symbol_notional_pct == Decimal("5")


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


def test_selected_signal_floor_sizes_weak_cross_sectional_picks() -> None:
    settings = load_strategy_v0_config()
    tuned_trader = settings.trader.model_copy(
        update={
                "selected_signal_floor": Decimal("0.000001"),
                "cost_gate_spread_multiplier": Decimal("0"),
                "cost_gate_min_abs_signal": Decimal("0"),
                "top_n": 1,
                "bottom_n": 1,
            "sizing_table": [
                SizingRow(abs_signal_max=Decimal("0.000001"), exposure_pct=Decimal("0.0")),
                SizingRow(abs_signal_max=Decimal("1.01"), exposure_pct=Decimal("0.25")),
            ],
        }
    )
    tuned = settings.model_copy(update={"trader": tuned_trader})
    trader = StrategyV0Trader(tuned)
    predictions = {symbol: (0.0, 1.0) for symbol in settings.tradable_symbols}
    predictions["EURUSD"] = (1e-12, 1.0)
    predictions["AUDUSD"] = (-1e-12, 1.0)
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")

    targets, _signals = trader.target_lots(predictions, Decimal("1000000"), prices)

    assert targets["EURUSD"] > 0
    assert targets["AUDUSD"] < 0


def test_disabled_symbols_are_forced_flat_by_trader() -> None:
    settings = load_strategy_v0_config()
    tuned_trader = settings.trader.model_copy(update={"disabled_symbols": ["XAGUSD"]})
    tuned = settings.model_copy(update={"trader": tuned_trader})
    trader = StrategyV0Trader(tuned)
    predictions = {symbol: (0.0, 1.0) for symbol in settings.tradable_symbols}
    predictions["XAGUSD"] = (-1.0, 0.1)
    predictions["EURUSD"] = (1.0, 0.1)
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")

    targets, _signals = trader.target_lots(predictions, Decimal("1000000"), prices)

    assert targets["XAGUSD"] == 0


def test_max_lots_by_symbol_caps_target_size() -> None:
    settings = load_strategy_v0_config()
    tuned_trader = settings.trader.model_copy(
        update={
            "cost_gate_spread_multiplier": Decimal("0"),
            "cost_gate_min_abs_signal": Decimal("0"),
            "max_lots_by_symbol": {"XAGUSD": Decimal("0.01")},
        }
    )
    tuned = settings.model_copy(update={"trader": tuned_trader})
    trader = StrategyV0Trader(tuned)
    predictions = {symbol: (0.0, 1.0) for symbol in settings.tradable_symbols}
    predictions["XAGUSD"] = (-1.0, 0.1)
    predictions["EURUSD"] = (1.0, 0.1)
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")

    targets, _signals = trader.target_lots(predictions, Decimal("1000000"), prices)

    assert abs(targets["XAGUSD"]) == Decimal("0.01")


def test_invert_signals_flips_cross_sectional_direction() -> None:
    settings = load_strategy_v0_config()
    tuned_trader = settings.trader.model_copy(
        update={
            "cost_gate_spread_multiplier": Decimal("0"),
            "cost_gate_min_abs_signal": Decimal("0"),
            "invert_signals": True,
            "top_n": 1,
            "bottom_n": 1,
        }
    )
    tuned = settings.model_copy(update={"trader": tuned_trader})
    trader = StrategyV0Trader(tuned)
    predictions = {symbol: (0.0, 1.0) for symbol in settings.tradable_symbols}
    predictions["EURUSD"] = (1.0, 0.1)
    predictions["AUDUSD"] = (-1.0, 0.1)
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")

    targets, _signals = trader.target_lots(predictions, Decimal("1000000"), prices)

    assert targets["EURUSD"] < 0
    assert targets["AUDUSD"] > 0


def test_cost_gate_blocks_signal_when_spread_proxy_exceeds_edge() -> None:
    settings = load_strategy_v0_config()
    tuned_trader = settings.trader.model_copy(update={"cost_gate_spread_multiplier": Decimal("100"), "cost_gate_min_abs_signal": Decimal("0.05")})
    tuned = settings.model_copy(update={"trader": tuned_trader})

    assert not passes_cost_gate("EURUSD", 0.001, 0.10, Decimal("1.0"), Decimal("0.0002"), tuned)
    assert not passes_cost_gate("EURUSD", 0.050, 0.01, Decimal("1.0"), Decimal("0.0002"), tuned)
    assert passes_cost_gate("EURUSD", 0.050, 0.10, Decimal("1.0"), Decimal("0.0002"), tuned)


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


def test_portfolio_scaling_caps_single_symbol_concentration() -> None:
    settings = load_strategy_v0_config()
    tuned_portfolio = settings.portfolio.model_copy(update={"max_single_symbol_concentration_pct": Decimal("35"), "max_symbol_notional_pct": Decimal("100")})
    tuned = settings.model_copy(update={"portfolio": tuned_portfolio})
    prices = {symbol: Decimal("1") for symbol in settings.tradable_symbols}
    prices["XAUUSD"] = Decimal("2300")
    prices["XAGUSD"] = Decimal("30")
    targets = {"EURUSD": Decimal("3"), "GBPUSD": Decimal("0.5"), "AUDUSD": Decimal("-0.5")}

    scaled, _scale, _messages = apply_portfolio_scaling(targets, prices, Decimal("1000000"), tuned)
    positions = [(symbol, lot, prices[symbol]) for symbol, lot in scaled.items() if lot != 0]
    ok, message = check_single_symbol_concentration(positions, Decimal("1000000"), tuned)

    assert ok, message


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


def test_recent_prediction_history_keeps_alignment_buffer() -> None:
    strategy = StrategyV0()
    max_lookback = strategy._predictor.feature_builder.max_lookback
    timestamp = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    for symbol in strategy.symbols:
        strategy._bar_history[symbol] = [
            BarSnapshot(
                timestamp=timestamp + timedelta(minutes=15 * index),
                symbol=symbol,
                mid=1.0 + index * 0.0001,
                spread=0.0001,
            )
            for index in range(max_lookback * 4)
        ]

    recent = strategy._recent_prediction_history()

    assert all(len(bars) >= max_lookback * 3 for bars in recent.values())


def test_off_session_bars_still_reach_trader() -> None:
    class FakePredictor:
        has_active_models = True
        feature_builder = type("FeatureBuilder", (), {"max_lookback": 0})()

        def predict_from_bars(self, _bars):
            return {symbol: (1.0, 0.1) for symbol in strategy.symbols}

    class FakeTrader:
        def target_lots(self, _predictions, _equity, _prices, spreads=None):
            return (
                {symbol: (Decimal("0.01") if symbol == "EURUSD" else Decimal("0")) for symbol in strategy.symbols},
                {symbol: 1.0 for symbol in strategy.symbols},
            )

    strategy = StrategyV0()
    timestamp = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
    strategy._predictor = FakePredictor()
    strategy._trader = FakeTrader()
    for symbol in strategy.symbols:
        strategy._bar_history[symbol] = [
            BarSnapshot(timestamp=timestamp, symbol=symbol, mid=1.0, spread=0.0001)
        ]
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

    orders = strategy.on_bar_close(bar, account)

    assert len(orders) == 1
    assert orders[0].symbol == "EURUSD"
