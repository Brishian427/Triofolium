"""Run one Task 05 self-improving loop iteration."""

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
from trifolium.agents.brain import Brain
from trifolium.agents.coder import Coder
from trifolium.agents.nim_client import NIMClient
from trifolium.loop.orchestrator import LoopIteration
from trifolium.memory.strategy_memory import StrategyMemory
from trifolium.strategy.elements import decompose_v0


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _latest_v0_metrics() -> dict[str, Any]:
    preferred = ROOT / "reports" / "validation_strategy_v0_20260625_105114" / "validation_result.json"
    if preferred.exists():
        return json.loads(preferred.read_text(encoding="utf-8"))
    return {
        "strategy": "strategy_v0",
        "passed": True,
        "full_backtest": {"trade_count": 0, "final_equity": "1000000", "total_return": "0"},
    }


def seed_v0(memory: StrategyMemory) -> None:
    if memory.get("v0") is not None:
        return
    memory.insert(
        nickname="v0",
        element_table=decompose_v0().model_dump(mode="json"),
        metrics=_latest_v0_metrics(),
        decision="BASELINE",
        rationale="Initial StrategyV0 L5 baseline for Task 05 self-improving loop.",
        current_rank=0,
        modification_type="baseline",
    )


def build_iteration(config: dict[str, Any]) -> LoopIteration:
    load_dotenv(dotenv_path=ROOT / ".env")
    memory = StrategyMemory(ROOT / config["memory"]["db_path"])
    seed_v0(memory)
    nim = NIMClient(model=config["brain"]["model"])
    anthropic = AnthropicClient(model=config["coder"]["model"])
    brain = Brain(
        nim,
        allow_fallback=True,
        timeout_seconds=float(config["brain"].get("timeout_seconds", 300)),
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
