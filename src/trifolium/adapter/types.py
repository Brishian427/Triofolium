"""Typed data structures shared by the MT5 adapter modules."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountState(BaseModel):
    """Sanitized account state returned by MT5."""

    login: int
    balance: Decimal
    equity: Decimal
    margin: Decimal
    margin_free: Decimal
    margin_level: Decimal | None
    leverage: int
    currency: str


class Tick(BaseModel):
    """Current bid/ask tick for a tradable symbol."""

    symbol: str
    bid: Decimal
    ask: Decimal
    spread: Decimal
    spread_pips: Decimal
    time: datetime


class Candle(BaseModel):
    """OHLCV bar returned by MT5."""

    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
    spread: int
    real_volume: int


class Instrument(BaseModel):
    """Instrument metadata loaded from config/instruments.yaml."""

    symbol: str
    asset_class: str
    expected_contract_size: Decimal | None = None
    pip_size: Decimal
    min_lot: Decimal


class OrderExecutionResult(BaseModel):
    """Normalized result from an MT5 order operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: str
    retcode: int | None = None
    order: int | None = None
    deal: int | None = None
    volume: Decimal | None = None
    price: Decimal | None = None
    comment: str | None = None
    raw: dict[str, object] | None = None
