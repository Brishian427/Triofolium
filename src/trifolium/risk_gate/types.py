"""Typed request, result, and state models for the Risk Gate."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OrderSide = Literal["buy", "sell"]
OrderStatus = Literal["accepted", "rejected", "submitted", "filled", "error"]


class PositionSnapshot(BaseModel):
    """Existing signed position snapshot used by independent risk checks."""

    symbol: str
    signed_lots: Decimal
    price: Decimal
    contract_size: Decimal


class AccountSnapshot(BaseModel):
    """Minimal account state required by Risk Gate checks."""

    equity: Decimal
    margin_level_pct: Decimal | None = None
    balance: Decimal | None = None
    open_positions_count: int = 0
    leverage: Decimal | None = None


class OrderRequest(BaseModel):
    """Strategy order request that must pass the Risk Gate before MT5."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: OrderSide
    lots: Decimal
    price: Decimal
    contract_size: Decimal
    strategy_notional: Decimal
    comment: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    existing_positions: list[PositionSnapshot] = Field(default_factory=list)
    account: AccountSnapshot | None = None


class CheckResult(BaseModel):
    """Result from one Risk Gate check."""

    name: str
    passed: bool
    reason: str | None = None
    warning: str | None = None


class OrderResult(BaseModel):
    """Public result returned by `risk_gate.submit_order`."""

    status: OrderStatus
    reason: str | None = None
    request: OrderRequest
    checks: list[CheckResult] = Field(default_factory=list)
    mt5_response: dict[str, object] | None = None


class GateState(BaseModel):
    """Serializable snapshot of stateful Risk Gate locks and buffers."""

    locked: bool = False
    lock_reason: str | None = None
    session_peak_equity: Decimal | None = None
    recent_order_timestamps: list[datetime] = Field(default_factory=list)
