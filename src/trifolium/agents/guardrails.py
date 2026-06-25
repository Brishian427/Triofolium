"""Guardrails layer for Brain hypotheses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from trifolium.agents.scope_guard import ALLOWED_FILES, validate_hypothesis_scope


FORBIDDEN_TOPICS = ["risk_gate", "risk_limits", "mt5" + ".order_send", "Meta" + "Trader5"]
NEMO_FALLBACK_REASON: str | None = None


class HypothesisJSON(BaseModel):
    target_files: list[str] = Field(..., min_length=1, max_length=3)
    element_diff: dict[str, Any]
    rationale: str = Field(..., min_length=20)
    expected_metric_change: dict[str, Any]

    @field_validator("rationale")
    @classmethod
    def no_forbidden_topics(cls, value: str) -> str:
        lowered = value.lower()
        for topic in FORBIDDEN_TOPICS:
            if topic.lower() in lowered:
                raise ValueError(f"Rationale references forbidden topic: {topic}")
        return value

    @field_validator("target_files")
    @classmethod
    def target_files_allowed(cls, values: list[str]) -> list[str]:
        for value in values:
            if value.replace("\\", "/") not in ALLOWED_FILES:
                raise ValueError(f"Target file outside allowed scope: {value}")
        return values


def _extract_json(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return raw_text[start : end + 1]


def validate_brain_output(raw_text: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    json_text = _extract_json(raw_text)
    if json_text is None:
        return False, None, "No JSON found in Brain output"
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return False, None, f"JSON parse error: {exc}"
    try:
        hypothesis = HypothesisJSON.model_validate(parsed).model_dump(mode="json")
    except ValidationError as exc:
        return False, None, f"Schema validation failed: {exc}"
    passed, reason = validate_hypothesis_scope(hypothesis)
    if not passed:
        return False, None, f"Scope validation failed: {reason}"
    return True, hypothesis, None


def validate_hypothesis_dict(payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        hypothesis = HypothesisJSON.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        return False, f"Schema validation failed: {exc}"
    passed, reason = validate_hypothesis_scope(hypothesis)
    if not passed:
        return False, f"Scope validation failed: {reason}"
    return True, None


def try_nemo_guardrails_init(config_path: str | Path = "config/guardrails") -> tuple[object | None, str | None]:
    """Try a minimal NeMo Guardrails init and return a fallback reason on failure."""

    global NEMO_FALLBACK_REASON
    try:
        from nemoguardrails import LLMRails, RailsConfig

        rails_config = RailsConfig.from_path(str(config_path))
        rails = LLMRails(rails_config)
        NEMO_FALLBACK_REASON = None
        return rails, None
    except ImportError:
        NEMO_FALLBACK_REASON = "NeMo Guardrails not installed; using Pydantic-only validation"
        return None, NEMO_FALLBACK_REASON
    except Exception as exc:
        NEMO_FALLBACK_REASON = f"NeMo Guardrails init failed: {exc}; using Pydantic-only validation"
        return None, NEMO_FALLBACK_REASON
