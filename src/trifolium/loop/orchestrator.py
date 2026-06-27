"""Eight-step self-evolving strategy discovery loop."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from trifolium.agents.brain import Brain
from trifolium.agents.coder import Coder
from trifolium.agents.guardrails import validate_hypothesis_dict
from trifolium.agents.scope_guard import validate_hypothesis_scope
from trifolium.backtest.config import load_backtest_config
from trifolium.loop.types import IterationLogEntry
from trifolium.memory.strategy_memory import StrategyMemory
from trifolium.validation import strategy_v0_warmup_duration, validate_strategy


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


class LoopIteration:
    """Idempotent-ish 8-step iteration with JSONL audit logging."""

    def __init__(
        self,
        *,
        memory: StrategyMemory,
        brain: Brain,
        coder: Coder,
        log_dir: Path,
        repo_root: Path,
        sandbox_base: Path,
        validation_callable: Callable[..., Any] = validate_strategy,
    ) -> None:
        self.memory = memory
        self.brain = brain
        self.coder = coder
        self.log_dir = log_dir
        self.repo_root = repo_root
        self.sandbox_base = sandbox_base
        self.validation_callable = validation_callable
        self.iteration_id = str(uuid.uuid4())[:8]
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_base.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f"loop_iterations_{self.iteration_id}.jsonl"

    def _log(self, step: str, data: dict[str, Any]) -> None:
        entry = IterationLogEntry(iteration_id=self.iteration_id, step=step, data=_json_safe(data))
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    @staticmethod
    def _metrics_from_memory(row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("metrics_json")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    def _report_markdown(self, metrics: dict[str, Any]) -> str:
        markdown_path = metrics.get("markdown_report")
        if markdown_path and Path(markdown_path).exists():
            return Path(markdown_path).read_text(encoding="utf-8")
        return json.dumps(metrics, indent=2)

    def _validate_candidate(self, sandbox_dir: Path, *, parent_nickname: str, parent_metrics: dict[str, Any], hypothesis: dict[str, Any]) -> Any:
        cfg = load_backtest_config()
        config_path = sandbox_dir / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml"
        warmup = strategy_v0_warmup_duration(config_path if config_path.exists() else None)
        smoke_start = cfg.default_start + warmup
        return self.validation_callable(
            "strategy_v0",
            symbols="all_tradable",
            start=smoke_start,
            end=smoke_start + timedelta(hours=6),
            report_root=sandbox_dir / "reports",
            strategy_config_path=config_path if config_path.exists() else None,
            parent_nickname=parent_nickname,
            parent_metrics=parent_metrics,
            changed_parameters=hypothesis.get("element_diff", {}),
            evaluation_method="BACKTEST",
        )

    def run(self, parent_nickname: str = "v0") -> dict[str, Any]:
        state: dict[str, Any] = {"parent": parent_nickname, "status": "started", "iteration_id": self.iteration_id}
        self._log("start", state)
        try:
            parent = self.memory.get(parent_nickname)
            if parent is None:
                state.update({"status": "failed", "error": f"Parent {parent_nickname} not in memory"})
                self._log("step1_read_report", state)
                return state

            parent_metrics = self._metrics_from_memory(parent)
            report_markdown = self._report_markdown(parent_metrics)
            memory_summary = self.memory.to_markdown_summary()
            self._log("step1_read_report", {"parent": parent_nickname, "report_chars": len(report_markdown)})

            passed, hypothesis, error = self.brain.propose_hypothesis(
                v_n_report_markdown=report_markdown,
                memory_summary=memory_summary,
            )
            self._log("step2_brain_propose", {"passed": passed, "hypothesis": hypothesis, "error": error, "api": self.brain.last_metadata})
            if not passed or hypothesis is None:
                state.update({"status": "skipped", "error": f"Brain failed: {error}"})
                return state

            passed, error = validate_hypothesis_dict(hypothesis)
            if passed:
                passed, error = validate_hypothesis_scope(hypothesis)
            self._log("step3_guardrail", {"passed": passed, "error": error})
            if not passed:
                state.update({"status": "skipped", "error": f"Guardrail failed: {error}"})
                return state

            sandbox_dir = self.sandbox_base / f"v_{self.iteration_id}"
            passed, sandbox_path, error = self.coder.generate_and_apply_patch(
                hypothesis=hypothesis,
                repo_root=self.repo_root,
                sandbox_dir=sandbox_dir,
            )
            patch_path = sandbox_dir / ".applied_patch.diff"
            self._log(
                "step4_coder",
                {
                    "passed": passed,
                    "sandbox": sandbox_path,
                    "error": error,
                    "api": self.coder.last_metadata,
                    "patch_path": str(patch_path) if patch_path.exists() else None,
                },
            )
            if not passed or sandbox_path is None:
                state.update({"status": "skipped", "error": f"Coder failed: {error}"})
                return state

            self._log("step5_scope_check", {"passed": True, "sandbox": sandbox_path})

            validation_result = self._validate_candidate(Path(sandbox_path), parent_nickname=parent_nickname, parent_metrics=parent_metrics, hypothesis=hypothesis)
            validation_dict = validation_result.model_dump(mode="json") if hasattr(validation_result, "model_dump") else validation_result
            self._log("step6_backtest", {"result": validation_dict})

            decision, rationale = self.brain.evaluate_candidate(parent_metrics, validation_dict)
            self._log("step7_evaluate", {"decision": decision, "rationale": rationale})

            nickname = f"v_{self.iteration_id}"
            self.memory.insert(
                nickname=nickname,
                element_table=hypothesis.get("element_diff", {}),
                parent_nickname=parent_nickname,
                metrics=validation_dict,
                decision=decision,
                rationale=rationale,
                modification_type="Level_2" if "hyperparams" in json.dumps(hypothesis.get("element_diff", {})) else "Level_1",
                iteration_log_path=str(self.log_path),
            )
            self._log("step8_memory_write", {"nickname": nickname})

            state.update({"status": "completed", "new_strategy": nickname, "decision": decision})
            self._log("end", state)
            return state
        except Exception as exc:
            state.update({"status": "crashed", "error": f"{type(exc).__name__}: {exc}"})
            self._log("crash", state)
            return state
