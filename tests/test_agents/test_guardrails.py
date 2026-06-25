from __future__ import annotations

import json

from trifolium.agents.guardrails import validate_brain_output


def _valid() -> dict:
    return {
        "target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"],
        "element_diff": {"x": {"from": 1, "to": 2}},
        "rationale": "D2 Section 2 shows a trade-count gate failure, so a narrow threshold change can make the flat strategy produce behavior.",
        "expected_metric_change": {"metric": "trade_count", "direction": "+"},
    }


def test_guardrails_accept_valid_json():
    passed, hypothesis, error = validate_brain_output(json.dumps(_valid()))
    assert passed is True
    assert hypothesis["target_files"]
    assert error is None


def test_guardrails_reject_malformed_and_forbidden():
    passed, _hypothesis, error = validate_brain_output("not json")
    assert passed is False
    assert "No JSON" in error
    bad = _valid()
    bad["rationale"] = "Please modify risk_limits to make trading easier."
    passed, _hypothesis, error = validate_brain_output(json.dumps(bad))
    assert passed is False
    assert "Schema" in error


def test_guardrails_normalizes_common_strategy_config_alias():
    payload = _valid()
    payload["target_files"] = ["src/trifolium/strategy/v0/config/strategy_v0.yaml"]
    passed, hypothesis, error = validate_brain_output(json.dumps(payload))
    assert passed is True
    assert error is None
    assert hypothesis["target_files"] == ["src/trifolium/strategy/config/strategy_v0.yaml"]
