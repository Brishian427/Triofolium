"""One-shot real-account calibration trade for Task 01 L2."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.adapter.account import get_account_state
from trifolium.adapter.market_data import get_tick, load_instruments
from trifolium.adapter.mt5_client import mt5_session
from trifolium.adapter.orders import close_position, send_market_buy, wait_for_position


def json_safe(value: Any) -> Any:
    """Convert Decimal and MT5 namedtuples into JSON-safe structures."""

    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "_asdict"):
        return json_safe(value._asdict())
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    return value


def write_log(record: dict[str, Any]) -> None:
    """Append a JSONL record to the daily calibration log."""

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    path = log_dir / f"calibration_{datetime.now(timezone.utc).date().isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json_safe(record), sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run exactly one calibration ping-pong trade.")
    parser.add_argument("--symbol", default="AUDUSD")
    parser.add_argument("--lots", default="0.01")
    parser.add_argument("--mode", default="ping_pong", choices=["ping_pong"])
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("MT5_CALIBRATION_MODE") != "1":
        print("REFUSED: MT5_CALIBRATION_MODE=1 is required for L2 live calibration.", file=sys.stderr)
        return 1

    args = parse_args()
    lots = Decimal(str(args.lots))
    if lots != Decimal("0.01"):
        print("REFUSED: calibration lots must be exactly 0.01.", file=sys.stderr)
        return 1

    instruments = {item.symbol: item for item in load_instruments()}
    if args.symbol not in instruments:
        print(f"REFUSED: symbol {args.symbol} is not in config/instruments.yaml.", file=sys.stderr)
        return 1

    try:
        with mt5_session():
            instrument = instruments[args.symbol]
            tick_before = get_tick(args.symbol, instrument.pip_size)
            if tick_before.spread_pips >= Decimal("5"):
                print(
                    f"REFUSED: {args.symbol} spread is {tick_before.spread_pips} pips, not < 5.",
                    file=sys.stderr,
                )
                return 1

            account_before = get_account_state()
            started = time.monotonic()
            open_request, open_result = send_market_buy(args.symbol, lots, "trifolium_l2_open")
            if open_result.status != "filled":
                write_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "stage": "open_failed",
                        "request": open_request,
                        "response": open_result.model_dump(),
                    }
                )
                print(f"ERROR: open order failed retcode={open_result.retcode} comment={open_result.comment}")
                return 1

            position = wait_for_position(args.symbol, lots, timeout_seconds=5.0)
            fill_seconds = Decimal(str(time.monotonic() - started))
            close_request, close_result = close_position(position, "trifolium_l2_close")
            account_after = get_account_state()
            if close_result.status != "filled":
                write_log(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "stage": "close_failed",
                        "open_request": open_request,
                        "open_response": open_result.model_dump(),
                        "close_request": close_request,
                        "close_response": close_result.model_dump(),
                    }
                )
                print(f"ERROR: close order failed retcode={close_result.retcode} comment={close_result.comment}")
                return 1

            pnl = account_after.equity - account_before.equity
            open_slippage = (open_result.price or tick_before.ask) - tick_before.ask
            close_tick = get_tick(args.symbol, instrument.pip_size)
            close_slippage = close_tick.bid - (close_result.price or close_tick.bid)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "success",
                "symbol": args.symbol,
                "lots": lots,
                "tick_before": tick_before.model_dump(),
                "open_request": open_request,
                "open_response": open_result.model_dump(),
                "close_request": close_request,
                "close_response": close_result.model_dump(),
                "time_to_fill_seconds": fill_seconds,
                "pnl_account_currency": pnl,
                "open_slippage": open_slippage,
                "close_slippage": close_slippage,
            }
            write_log(record)
            print(
                "CALIBRATION_SUCCESS "
                f"symbol={args.symbol} lots={lots} "
                f"open_price={open_result.price} close_price={close_result.price} "
                f"pnl={pnl} time_to_fill_seconds={fill_seconds} "
                f"open_slippage={open_slippage} close_slippage={close_slippage}"
            )
            return 0
    except Exception as exc:
        write_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": "exception",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
