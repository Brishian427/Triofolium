"""Typed loop records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class IterationLogEntry(BaseModel):
    iteration_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step: str
    data: dict[str, Any]

