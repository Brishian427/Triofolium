"""Order submission and position polling helpers for MT5 calibration flows."""

from __future__ import annotations

import time
from decimal import Decimal

import MetaTrader5 as mt5

from trifolium.adapter.mt5_client import MT5ConnectionError
from trifolium.adapter.types import OrderExecutionResult


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _as_dict(value: object) -> dict[str, object]:
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    return {"value": repr(value)}


def build_market_order_request(symbol: str, side: str, lots: Decimal, price: Decimal, comment: str | None = None) -> dict[str, object]:
    """Build an MT5 market-deal request without sending it."""

    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": float(price),
        "deviation": 20,
        "magic": 10181,
        "comment": comment or "trifolium_risk_gate",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }


def send_market_buy(symbol: str, lots: Decimal, comment: str) -> tuple[dict[str, object], OrderExecutionResult]:
    """Send one market buy order through MT5."""

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbol_info_tick({symbol}) failed before buy: {code} {message}")
    request = build_market_order_request(symbol, "buy", lots, _decimal(tick.ask), comment)
    raise MT5ConnectionError("Direct MT5 sending is disabled; route orders through trifolium.risk_gate.submit_order.")


def close_position(position: object, comment: str) -> tuple[dict[str, object], OrderExecutionResult]:
    """Close a netting position with an opposite market order."""

    raw_position = _as_dict(position)
    symbol = str(raw_position["symbol"])
    volume = _decimal(raw_position["volume"])
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.symbol_info_tick({symbol}) failed before close: {code} {message}")
    request: dict[str, object] = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_SELL,
        "position": int(raw_position["ticket"]),
        "price": tick.bid,
        "deviation": 20,
        "magic": 10181,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    raise MT5ConnectionError("Direct MT5 sending is disabled; route orders through trifolium.risk_gate.submit_order.")


def normalize_order_response(response: object) -> OrderExecutionResult:
    """Convert an MT5 order response to a typed result."""

    if response is None:
        code, message = mt5.last_error()
        return OrderExecutionResult(status="error", retcode=code, comment=message)
    raw = _as_dict(response)
    retcode = int(raw.get("retcode", 0))
    status = "filled" if retcode == mt5.TRADE_RETCODE_DONE else "rejected"
    return OrderExecutionResult(
        status=status,
        retcode=retcode,
        order=int(raw["order"]) if raw.get("order") else None,
        deal=int(raw["deal"]) if raw.get("deal") else None,
        volume=_decimal(raw["volume"]) if raw.get("volume") is not None else None,
        price=_decimal(raw["price"]) if raw.get("price") is not None else None,
        comment=str(raw["comment"]) if raw.get("comment") is not None else None,
        raw=raw,
    )


def wait_for_position(symbol: str, min_volume: Decimal, timeout_seconds: float = 5.0) -> object:
    """Poll open positions until the symbol position appears or timeout expires."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for position in positions:
                raw = _as_dict(position)
                if _decimal(raw["volume"]) >= min_volume:
                    return position
        time.sleep(0.25)
    raise MT5ConnectionError(f"Timed out waiting for position in {symbol}")
