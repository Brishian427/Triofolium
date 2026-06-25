from __future__ import annotations

from trifolium.agents.scope_guard import check_patch_content, validate_hypothesis_scope


def test_scope_allows_strategy_config():
    passed, reason = validate_hypothesis_scope({"target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"]})
    assert passed is True
    assert reason is None


def test_scope_rejects_risk_gate_and_strategy_interface():
    passed, reason = validate_hypothesis_scope({"target_files": ["src/trifolium/risk_gate/gate.py"]})
    assert passed is False
    assert "whitelist" in reason or "blacklist" in reason
    passed, reason = validate_hypothesis_scope({"target_files": ["src/trifolium/strategy/v0/strategy.py"]})
    assert passed is False


def test_scope_rejects_forbidden_patch_content():
    passed, reason = check_patch_content("diff --git a/x b/x\n+import mt5\n")
    assert passed is False
    assert "forbidden" in reason

