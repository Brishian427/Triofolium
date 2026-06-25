from __future__ import annotations

from pathlib import Path

from trifolium.loop.orchestrator import LoopIteration
from trifolium.memory import StrategyMemory


class FakeBrain:
    last_metadata = {"real_call": False}

    def propose_hypothesis(self, **kwargs):
        return True, {
            "target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"],
            "element_diff": {"x": {"from": 1, "to": 2}},
            "rationale": "A narrow threshold change can make the flat strategy produce behavior.",
            "expected_metric_change": {"metric": "trade_count", "direction": "+"},
        }, None

    def evaluate_candidate(self, parent, candidate):
        return "KEEP", "test"


class BadBrain(FakeBrain):
    def propose_hypothesis(self, **kwargs):
        return True, {
            "target_files": ["src/trifolium/risk_gate/gate.py"],
            "element_diff": {"x": {"from": 1, "to": 2}},
            "rationale": "A narrow threshold change can make the flat strategy produce behavior.",
            "expected_metric_change": {"metric": "trade_count", "direction": "+"},
        }, None


class BadRationaleBrain(FakeBrain):
    def propose_hypothesis(self, **kwargs):
        passed, hypothesis, error = super().propose_hypothesis(**kwargs)
        hypothesis["rationale"] = "Please modify risk_limits so this candidate can trade more aggressively."
        return passed, hypothesis, error


class FakeCoder:
    last_metadata = {"real_call": False}

    def generate_and_apply_patch(self, *, hypothesis, repo_root, sandbox_dir):
        sandbox_dir.mkdir(parents=True)
        (sandbox_dir / ".applied_patch.diff").write_text("diff --git a/x b/x\n", encoding="utf-8")
        return True, str(sandbox_dir), None


class BadCoder(FakeCoder):
    def generate_and_apply_patch(self, *, hypothesis, repo_root, sandbox_dir):
        return False, None, "Patch validation failed: Patch contains forbidden pattern: import mt5"


class Validation:
    def model_dump(self, mode="json"):
        return {"passed": True, "full_backtest": {"trade_count": 0}}


def _memory(tmp_path: Path) -> StrategyMemory:
    memory = StrategyMemory(tmp_path / "memory.db")
    memory.insert(nickname="v0", element_table={"v": 0}, metrics={"passed": True, "full_backtest": {"trade_count": 0}})
    return memory


def test_orchestrator_completes_eight_steps(tmp_path):
    iteration = LoopIteration(
        memory=_memory(tmp_path),
        brain=FakeBrain(),
        coder=FakeCoder(),
        log_dir=tmp_path / "logs",
        repo_root=tmp_path,
        sandbox_base=tmp_path / "sandboxes",
        validation_callable=lambda *args, **kwargs: Validation(),
    )
    result = iteration.run("v0")
    assert result["status"] == "completed"
    log_text = iteration.log_path.read_text(encoding="utf-8")
    assert "step8_memory_write" in log_text


def test_orchestrator_skips_forbidden_hypothesis(tmp_path):
    memory = _memory(tmp_path)
    iteration = LoopIteration(
        memory=memory,
        brain=BadBrain(),
        coder=FakeCoder(),
        log_dir=tmp_path / "logs",
        repo_root=tmp_path,
        sandbox_base=tmp_path / "sandboxes",
        validation_callable=lambda *args, **kwargs: Validation(),
    )
    result = iteration.run("v0")
    assert result["status"] == "skipped"
    assert "Guardrail" in result["error"]
    assert len(memory.list_all()) == 1


def test_orchestrator_skips_forbidden_rationale(tmp_path):
    memory = _memory(tmp_path)
    iteration = LoopIteration(
        memory=memory,
        brain=BadRationaleBrain(),
        coder=FakeCoder(),
        log_dir=tmp_path / "logs",
        repo_root=tmp_path,
        sandbox_base=tmp_path / "sandboxes",
        validation_callable=lambda *args, **kwargs: Validation(),
    )
    result = iteration.run("v0")
    assert result["status"] == "skipped"
    assert "Guardrail" in result["error"]
    assert len(memory.list_all()) == 1


def test_orchestrator_skips_forbidden_coder_patch(tmp_path):
    memory = _memory(tmp_path)
    iteration = LoopIteration(
        memory=memory,
        brain=FakeBrain(),
        coder=BadCoder(),
        log_dir=tmp_path / "logs",
        repo_root=tmp_path,
        sandbox_base=tmp_path / "sandboxes",
        validation_callable=lambda *args, **kwargs: Validation(),
    )
    result = iteration.run("v0")
    assert result["status"] == "skipped"
    assert "Coder failed" in result["error"]
    assert len(memory.list_all()) == 1
