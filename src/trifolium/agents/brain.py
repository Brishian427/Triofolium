"""Nemotron-backed hypothesis proposer."""

from __future__ import annotations

import json
from typing import Any

from trifolium.agents.guardrails import validate_brain_output
from trifolium.agents.nim_client import NIMClient


BRAIN_SYSTEM_PROMPT = """You are a quantitative trading strategy improvement agent.
You propose one narrow, sandbox-only modification to StrategyV0.

Strict constraints:
- Allowed targets only:
  - src/trifolium/strategy/v0/predictor.py
  - src/trifolium/strategy/v0/trader.py
  - src/trifolium/strategy/v0/portfolio.py
  - src/trifolium/strategy/config/strategy_v0.yaml
- Never suggest modifying risk controls, broker adapters, live runners, or MT5 plumbing.
- Output valid JSON only with: target_files, element_diff, rationale, expected_metric_change.

First-iteration hint: if the report shows zero trades, prefer lowering a StrategyV0 confidence,
destroyer, or sizing threshold in the YAML config so behavior can change in a controlled way.
"""


def fallback_zero_trade_hypothesis() -> dict[str, Any]:
    return {
        "target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"],
        "element_diff": {
            "signal_layer.model_hyperparams.destroyer_validation_sharpe_threshold": {
                "from": "0.0",
                "to": "-0.05",
            }
        },
        "rationale": "The current validation report is flat with zero trades, so relaxing the destroyer validation threshold may allow fitted symbols to trade while remaining inside the sandboxed strategy config.",
        "expected_metric_change": {"metric": "trade_count", "direction": "+"},
    }


class Brain:
    """Planner agent that calls NIM and validates JSON hypotheses."""

    def __init__(
        self,
        nim_client: NIMClient | None = None,
        *,
        allow_fallback: bool = False,
        timeout_seconds: float = NIMClient.DEFAULT_TIMEOUT_SECONDS,
        reasoning_budget: int = 8192,
        temperature: float = 0.7,
        max_retries: int = 2,
    ) -> None:
        self.nim = nim_client or NIMClient()
        self.allow_fallback = allow_fallback
        self.timeout_seconds = timeout_seconds
        self.reasoning_budget = reasoning_budget
        self.temperature = temperature
        self.max_retries = max_retries
        self.last_raw: str | None = None
        self.last_metadata: dict[str, Any] = {}

    def propose_hypothesis(
        self,
        *,
        v_n_report_markdown: str,
        memory_summary: str,
        max_retries: int | None = None,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        retry_count = self.max_retries if max_retries is None else max_retries
        user_content = (
            f"# Current Strategy Report\n\n{v_n_report_markdown}\n\n"
            f"# Memory of Past Attempts\n\n{memory_summary}\n\n"
            "Propose ONE modification. Output JSON only."
        )
        last_error = None
        for attempt in range(retry_count + 1):
            try:
                raw = self.nim.chat(
                    messages=[{"role": "system", "content": BRAIN_SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
                    reasoning_budget=self.reasoning_budget,
                    max_tokens=1024,
                    temperature=self.temperature,
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.last_metadata = {
                    "provider": "nvidia_nim",
                    "real_call": True,
                    "attempt": attempt + 1,
                    "fallback_used": False,
                    "error": last_error,
                }
                if self.allow_fallback:
                    hypothesis = fallback_zero_trade_hypothesis()
                    self.last_metadata["fallback_used"] = True
                    return True, hypothesis, None
                return False, None, f"Brain call failed: {last_error}"
            self.last_raw = raw
            self.last_metadata = {"provider": "nvidia_nim", "real_call": True, "attempt": attempt + 1, "fallback_used": False}
            passed, hypothesis, error = validate_brain_output(raw)
            if passed:
                return True, hypothesis, None
            last_error = error
            user_content = f"Previous attempt failed validation: {error}\n\nReturn corrected JSON only."

        if self.allow_fallback:
            hypothesis = fallback_zero_trade_hypothesis()
            self.last_metadata["fallback_used"] = True
            self.last_metadata["fallback_reason"] = last_error
            return True, hypothesis, None
        return False, None, f"Brain failed schema validation after {retry_count + 1} attempts: {last_error}"

    def evaluate_candidate(self, parent_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> tuple[str, str]:
        if not candidate_metrics.get("passed", False):
            return "REJECT", "Candidate failed validation gate."
        parent_trades = int(parent_metrics.get("full_backtest", {}).get("trade_count", 0) or 0)
        candidate_trades = int(candidate_metrics.get("full_backtest", {}).get("trade_count", 0) or 0)
        if candidate_trades > parent_trades:
            return "ACCEPT", "Candidate increases trade_count while passing validation."
        return "KEEP", "Candidate passes validation but does not improve the primary zero-trade binding yet."
