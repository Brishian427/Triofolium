"""JSONL logging for every Risk Gate order decision."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from trifolium.risk_gate.config import ROOT
from trifolium.risk_gate.types import OrderResult


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def risk_gate_log_path(now: datetime | None = None) -> Path:
    """Return today's Risk Gate order JSONL path."""

    timestamp = now or datetime.now(timezone.utc)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"risk_gate_{timestamp.date().isoformat()}.jsonl"


def log_order_result(result: OrderResult) -> Path:
    """Append an order result record to the daily Risk Gate JSONL log."""

    path = risk_gate_log_path(result.request.timestamp)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": result.request.model_dump(mode="python"),
        "checks": [check.model_dump(mode="python") for check in result.checks],
        "final_status": result.status,
        "reason": result.reason,
        "mt5_response": result.mt5_response,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(record), sort_keys=True) + "\n")
    return path
