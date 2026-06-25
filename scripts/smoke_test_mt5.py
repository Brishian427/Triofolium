"""Smoke test for MT5 connectivity and read-only market/account data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.adapter.account import get_account_state
from trifolium.adapter.market_data import (
    available_symbols_count,
    get_m1_candles,
    get_tick,
    load_instruments,
    verify_competition_symbols,
)
from trifolium.adapter.mt5_client import mt5_session, terminal_info


def assert_account_sane() -> None:
    account = get_account_state()
    assert account.login > 0, "account login must be positive"
    assert account.balance > 0, "account balance must be positive"
    assert account.equity > 0, "account equity must be positive"
    assert account.leverage > 0, "account leverage must be positive"
    print(
        "ACCOUNT "
        f"login={account.login} "
        f"balance={account.balance} "
        f"equity={account.equity} "
        f"margin={account.margin} "
        f"free_margin={account.margin_free} "
        f"margin_level={account.margin_level} "
        f"leverage={account.leverage} "
        f"currency={account.currency}"
    )


def assert_xauusd_data_sane() -> None:
    instruments = {item.symbol: item for item in load_instruments()}
    xau = instruments["XAUUSD"]
    tick = get_tick("XAUUSD", xau.pip_size)
    assert tick.ask > tick.bid, "XAUUSD ask must be greater than bid"
    assert tick.spread > 0, "XAUUSD spread must be positive"
    assert tick.spread_pips > 0, "XAUUSD spread pips must be positive"
    print(
        "TICK XAUUSD "
        f"bid={tick.bid} ask={tick.ask} "
        f"spread={tick.spread} spread_pips={tick.spread_pips} "
        f"time={tick.time.isoformat()}"
    )

    candles = get_m1_candles("XAUUSD", 10)
    assert len(candles) == 10, "expected 10 XAUUSD M1 candles"
    print("CANDLES XAUUSD M1 last_10")
    for candle in candles:
        assert candle.high >= candle.low, "candle high must be >= low"
        assert candle.tick_volume >= 0, "candle tick_volume must be non-negative"
        print(
            f"{candle.time.isoformat()} "
            f"O={candle.open} H={candle.high} L={candle.low} C={candle.close} "
            f"tick_volume={candle.tick_volume} spread={candle.spread} real_volume={candle.real_volume}"
        )


def assert_symbols_sane() -> None:
    instruments = load_instruments()
    count = available_symbols_count()
    assert count > 0, "available symbols count must be positive"
    rows = verify_competition_symbols(instruments)
    assert len(rows) == 15, "all 15 competition symbols must be accessible"
    print(f"SYMBOLS available_count={count} competition_accessible={len(rows)}")
    for row in rows:
        print(
            f"SYMBOL {row['symbol']} "
            f"contract_size={row['contract_size']} "
            f"volume_min={row['volume_min']} "
            f"volume_step={row['volume_step']} "
            f"visible={row['visible']}"
        )


def main() -> int:
    try:
        with mt5_session():
            terminal = terminal_info()
            print(
                "TERMINAL "
                f"name={terminal.get('name')} "
                f"company={terminal.get('company')} "
                f"connected={terminal.get('connected')} "
                f"trade_allowed={terminal.get('trade_allowed')} "
                f"tradeapi_disabled={terminal.get('tradeapi_disabled')}"
            )
            assert terminal.get("connected") is True, "terminal must be connected"
            assert_account_sane()
            assert_xauusd_data_sane()
            assert_symbols_sane()
        return 0
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
