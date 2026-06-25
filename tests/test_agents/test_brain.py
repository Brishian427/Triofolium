from __future__ import annotations

import json

from trifolium.agents.brain import TieredBrain


class FakeNIM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


def valid_json() -> str:
    return json.dumps(
        {
            "target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"],
            "element_diff": {"x": {"from": 1, "to": 2}},
            "rationale": "A narrow threshold change can make the flat strategy produce behavior.",
            "expected_metric_change": {"metric": "trade_count", "direction": "+"},
        }
    )


def test_brain_accepts_valid_json():
    navigator = FakeNIM(["branch_type=config"])
    architect = FakeNIM([valid_json()])
    brain = TieredBrain(architect, navigator_client=navigator)
    passed, hypothesis, error = brain.propose_hypothesis(v_n_report_markdown="flat", memory_summary="")
    assert passed is True
    assert hypothesis["target_files"]
    assert error is None
    assert navigator.calls
    assert architect.calls


def test_brain_retries_then_passes():
    brain = TieredBrain(FakeNIM(["bad", valid_json()]), navigator_client=FakeNIM(["branch_type=config"]))
    passed, hypothesis, _error = brain.propose_hypothesis(v_n_report_markdown="flat", memory_summary="", max_retries=1)
    assert passed is True
    assert hypothesis["element_diff"]


def test_brain_uses_configured_timeout_and_sampling_params():
    navigator = FakeNIM(["branch_type=config"])
    architect = FakeNIM([valid_json()])
    brain = TieredBrain(
        architect,
        navigator_client=navigator,
        navigator_timeout_seconds=17,
        architect_timeout_seconds=60,
        reasoning_budget=1234,
        temperature=0.2,
    )
    passed, _hypothesis, _error = brain.propose_hypothesis(v_n_report_markdown="flat", memory_summary="")
    assert passed is True
    assert navigator.calls[0]["timeout"] == 17
    assert architect.calls[0]["timeout"] == 60
    assert architect.calls[0]["reasoning_budget"] == 1234
    assert architect.calls[0]["temperature"] == 0.2


def test_brain_returns_error_when_invalid():
    brain = TieredBrain(FakeNIM(["bad"]), navigator_client=FakeNIM(["branch_type=config"]))
    passed, hypothesis, error = brain.propose_hypothesis(v_n_report_markdown="flat", memory_summary="", max_retries=0)
    assert passed is False
    assert hypothesis is None
    assert "failed" in error
