"""Run one Task 05 self-evolving loop iteration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.agents.anthropic_client import AnthropicClient
from trifolium.agents.brain import TieredBrain
from trifolium.agents.coder import Coder
from trifolium.agents.nim_client import NIMClient
from trifolium.loop.orchestrator import LoopIteration
from trifolium.memory.strategy_memory import StrategyMemory
from trifolium.strategy.elements import decompose_v0


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _latest_v0_metrics() -> dict[str, Any]:
    candidates = sorted(
        (ROOT / "reports").glob("validation_strategy_v0_*/validation_result.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        metrics = json.loads(candidate.read_text(encoding="utf-8"))
        if "d2" in metrics:
            return metrics
    if candidates:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    return {
        "strategy": "strategy_v0",
        "passed": False,
        "full_backtest": {"trade_count": 0, "final_equity": "1000000", "total_return": "0"},
    }


def seed_v0(memory: StrategyMemory) -> None:
    existing = memory.get("v0")
    if existing is not None:
        raw_metrics = existing.get("metrics_json")
        if raw_metrics and "d2" in json.loads(raw_metrics):
            return
    metrics = _latest_v0_metrics()
    if "d2" not in metrics:
        return
    memory.insert(
        nickname="v0",
        element_table=decompose_v0().model_dump(mode="json"),
        metrics=metrics,
        decision="BASELINE",
        rationale="Initial StrategyV0 D2 baseline for Task 05 self-evolving loop.",
        current_rank=0,
        modification_type="baseline",
    )


def build_iteration(config: dict[str, Any]) -> LoopIteration:
    load_dotenv(dotenv_path=ROOT / ".env")
    memory = StrategyMemory(ROOT / config["memory"]["db_path"])
    seed_v0(memory)
    navigator = NIMClient(model=config["brain"]["navigator_model"])
    architect = NIMClient(model=config["brain"]["architect_model"])
    anthropic = AnthropicClient(model=config["coder"]["model"])
    brain = TieredBrain(
        architect,
        navigator_client=navigator,
        allow_fallback=True,
        navigator_model=config["brain"]["navigator_model"],
        architect_model=config["brain"]["architect_model"],
        fallback_model=config["brain"].get("fallback_model", "nvidia/nemotron-3-nano-30b-a3b"),
        navigator_timeout_seconds=float(config["brain"].get("navigator_timeout_seconds", 60)),
        architect_timeout_seconds=float(config["brain"].get("architect_timeout_seconds", 60)),
        reasoning_budget=int(config["brain"].get("reasoning_budget", 8192)),
        temperature=float(config["brain"].get("temperature", 0.7)),
        max_retries=int(config["brain"].get("max_retries", 2)),
    )
    coder = Coder(anthropic, allow_fallback=True)
    return LoopIteration(
        memory=memory,
        brain=brain,
        coder=coder,
        log_dir=ROOT / "logs",
        repo_root=ROOT,
        sandbox_base=ROOT / config["sandbox"]["base_dir"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", default="v0")
    parser.add_argument("--config", default=str(ROOT / "config" / "self_improving.yaml"))
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    iteration = build_iteration(config)
    result = iteration.run(args.parent)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
