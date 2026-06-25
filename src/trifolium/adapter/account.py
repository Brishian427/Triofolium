"""Account-state queries for the MT5 adapter layer."""

from __future__ import annotations

from decimal import Decimal

import MetaTrader5 as mt5

from trifolium.adapter.mt5_client import MT5ConnectionError
from trifolium.adapter.types import AccountState


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def get_account_state() -> AccountState:
    """Return sanitized account state and fail loudly when MT5 returns nothing."""

    info = mt5.account_info()
    if info is None:
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"mt5.account_info failed: {code} {message}")
    raw = info._asdict()
    margin_level = raw.get("margin_level")
    return AccountState(
        login=int(raw["login"]),
        balance=_decimal(raw["balance"]),
        equity=_decimal(raw["equity"]),
        margin=_decimal(raw["margin"]),
        margin_free=_decimal(raw["margin_free"]),
        margin_level=_decimal(margin_level) if margin_level is not None else None,
        leverage=int(raw["leverage"]),
        currency=str(raw["currency"]),
    )
