"""Concentrated mutable state for Risk Gate locks and rate buffers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from trifolium.risk_gate.types import GateState


STATE = GateState()


def reset_state() -> None:
    """Reset mutable gate state for tests and controlled dry-runs."""

    STATE.locked = False
    STATE.lock_reason = None
    STATE.session_peak_equity = None
    STATE.recent_order_timestamps = []


def lock_gate(reason: str) -> None:
    """Lock the gate until a future explicit manual unlock function is added."""

    STATE.locked = True
    STATE.lock_reason = reason


def record_order_timestamp(timestamp: datetime) -> None:
    """Record an order timestamp for future rate-limit checks."""

    STATE.recent_order_timestamps.append(timestamp)


def update_session_peak(equity: Decimal) -> None:
    """Track the session equity high watermark for drawdown hard floors."""

    if STATE.session_peak_equity is None or equity > STATE.session_peak_equity:
        STATE.session_peak_equity = equity
