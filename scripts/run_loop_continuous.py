"""Run the self-evolving loop repeatedly with config-defined pacing."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import yaml

from run_loop_iteration import build_iteration


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", default="v0")
    parser.add_argument("--config", default=str(ROOT / "config" / "self_improving.yaml"))
    parser.add_argument("--iterations", type=int, default=1)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    parent = args.parent
    delay = int(config["loop"]["min_seconds_between_iterations"])
    for index in range(args.iterations):
        iteration = build_iteration(config)
        result = iteration.run(parent)
        print(result)
        if result.get("new_strategy"):
            parent = result["new_strategy"]
        if index < args.iterations - 1:
            time.sleep(delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

