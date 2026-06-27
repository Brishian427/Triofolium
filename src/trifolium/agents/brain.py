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
- Current principal live policy: USDCAD and USDJPY may trade up to 0.5 lots
  per order; AUDUSD is sell-only exposure, so never propose changes that
  encourage AUDUSD long exposure. AUDUSD buys are only acceptable when reducing
  an existing AUDUSD short.
- Output valid JSON only with: target_files, element_diff, rationale, expected_metric_change.

Use the D2 9-section evaluation report exactly:
- STEP 1 Gate: read Section 2. If any gate fails, especially Trade Count < 30
  or Active Intervals < 8, propose a modification that addresses that gate.
- STEP 2 Binding: read Section 5. If verdict is DEAD CODE, propose a binding
  modification that changes the position path or fill pattern.
- STEP 3 Objective: read Section 3. Total Return is the primary objective
  only after hard gates pass.
- STEP 4 Tie-break: read Section 4. MaxDD, Sharpe, Sortino, Win Rate, and
  Avg Trade Duration are secondary tie-break metrics only.
- STEP 5 Robustness override: read Section 6. If isolated peak or unstable,
  propose a more robust variant instead of chasing return.

Improvement targeting rules:
- If Section 2 shows Trade Count = 0 or Trade Count < 30, target behavior that
  creates trades. For 6h smoke windows, target at least 5 trades while keeping
  Risk Discipline >= 90 and MaxDD < 5%.
- If Section 5 says DEAD CODE, change a decision threshold, sizing path, or
  predictor/trader branch so the candidate is behaviorally different.
- If Section 6 warns isolated peak or unstable, prefer a smaller or smoother
  parameter change.

First-iteration hint: if Section 2 fails due zero trades, prefer lowering a
StrategyV0 confidence, destroyer, or sizing threshold in the YAML config so
behavior can change in a controlled way.

Current known baseline: StrategyV0 currently makes 0 trades. Section 2 Gate
Check shows Trade Count = 0 (FAIL). Propose ONE modification per iteration that
addresses this gate failure. Encourage diverse exploration across iterations:
threshold relaxation, signal compression, sizing activation, trader branch, or
predictor gating are all acceptable if they stay inside allowed target files.
"""

NAVIGATOR_SYSTEM_PROMPT = """You are the navigator for Triofolium's self-evolving strategy loop.
Choose the next branch direction only. Do not write code or patches.
Return a concise navigation note with: branch_type, target_area, and why.
Stay within StrategyV0 sandbox files only.
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
        "rationale": "D2 Section 2 shows the Trade Count gate is failing with zero trades, and Section 5 indicates no binding behavior change yet; relaxing the destroyer validation threshold may allow fitted symbols to trade inside the sandboxed strategy config.",
        "expected_metric_change": {"metric": "trade_count", "direction": "+"},
    }


class TieredBrain:
    """Two-tier planner: fast navigator first, stronger architect second."""

    DEFAULT_NAVIGATOR_MODEL = "mistralai/mistral-nemotron"
    DEFAULT_ARCHITECT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
    DEFAULT_FALLBACK_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
    DISABLED_ULTRA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

    def __init__(
        self,
        architect_client: NIMClient | None = None,
        *,
        navigator_client: NIMClient | None = None,
        navigator_model: str = DEFAULT_NAVIGATOR_MODEL,
        architect_model: str = DEFAULT_ARCHITECT_MODEL,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        allow_fallback: bool = False,
        navigator_timeout_seconds: float = 60,
        architect_timeout_seconds: float = 60,
        reasoning_budget: int = 8192,
        temperature: float = 0.7,
        max_retries: int = 2,
    ) -> None:
        self.navigator_model = navigator_model
        self.architect_model = architect_model
        self.fallback_model = fallback_model
        self.navigator = navigator_client or NIMClient(model=navigator_model)
        self.architect = architect_client or NIMClient(model=architect_model)
        self.allow_fallback = allow_fallback
        self.navigator_timeout_seconds = navigator_timeout_seconds
        self.architect_timeout_seconds = architect_timeout_seconds
        self.reasoning_budget = reasoning_budget
        self.temperature = temperature
        self.max_retries = max_retries
        self.last_raw: str | None = None
        self.last_navigation: str | None = None
        self.last_metadata: dict[str, Any] = {}

    def _navigate(self, user_content: str) -> tuple[str, dict[str, Any]]:
        try:
            raw = self.navigator.chat(
                messages=[
                    {"role": "system", "content": NAVIGATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                reasoning_budget=1024,
                max_tokens=256,
                temperature=0,
                timeout=self.navigator_timeout_seconds,
            )
            return raw, {
                "model": self.navigator_model,
                "real_call": True,
                "fallback_used": False,
            }
        except Exception as exc:
            if not self.allow_fallback:
                raise
            raw = self.navigator.chat(
                messages=[
                    {"role": "system", "content": NAVIGATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                model=self.fallback_model,
                reasoning_budget=512,
                max_tokens=256,
                temperature=0,
                timeout=self.navigator_timeout_seconds,
            )
            return raw, {
                "model": self.navigator_model,
                "real_call": True,
                "fallback_used": True,
                "fallback_model": self.fallback_model,
                "error": f"{type(exc).__name__}: {exc}",
            }

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
        try:
            navigation, navigator_metadata = self._navigate(user_content)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            self.last_metadata = {
                "provider": "tiered_nvidia_nim",
                "real_call": True,
                "navigator": {
                    "model": self.navigator_model,
                    "real_call": True,
                    "fallback_used": False,
                    "error": last_error,
                },
                "architect": None,
                "fallback_used": False,
            }
            if self.allow_fallback:
                hypothesis = fallback_zero_trade_hypothesis()
                self.last_metadata["fallback_used"] = True
                return True, hypothesis, None
            return False, None, f"Navigator call failed: {last_error}"

        self.last_navigation = navigation
        architect_user_content = f"{user_content}\n\n# Navigator Note\n\n{navigation}\n\nReturn architect JSON only."
        last_error = None
        for attempt in range(retry_count + 1):
            try:
                raw = self.architect.chat(
                    messages=[
                        {"role": "system", "content": BRAIN_SYSTEM_PROMPT},
                        {"role": "user", "content": architect_user_content},
                    ],
                    reasoning_budget=self.reasoning_budget,
                    max_tokens=1024,
                    temperature=self.temperature,
                    timeout=self.architect_timeout_seconds,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.last_metadata = {
                    "provider": "tiered_nvidia_nim",
                    "real_call": True,
                    "navigator": navigator_metadata,
                    "architect": {
                        "model": self.architect_model,
                        "real_call": True,
                        "attempt": attempt + 1,
                        "fallback_used": False,
                        "error": last_error,
                    },
                    "fallback_used": False,
                }
                if self.allow_fallback:
                    hypothesis = fallback_zero_trade_hypothesis()
                    self.last_metadata["fallback_used"] = True
                    self.last_metadata["architect"]["fallback_used"] = True
                    return True, hypothesis, None
                return False, None, f"Brain call failed: {last_error}"
            self.last_raw = raw
            self.last_metadata = {
                "provider": "tiered_nvidia_nim",
                "real_call": True,
                "navigator": navigator_metadata,
                "architect": {
                    "model": self.architect_model,
                    "real_call": True,
                    "attempt": attempt + 1,
                    "fallback_used": False,
                },
                "fallback_used": False,
            }
            passed, hypothesis, error = validate_brain_output(raw)
            if passed:
                return True, hypothesis, None
            last_error = error
            architect_user_content = (
                f"Previous attempt failed validation: {error}\n\n"
                "Return corrected JSON only with exactly these keys: target_files, element_diff, rationale, expected_metric_change.\n"
                "Allowed target_files are exactly:\n"
                "- src/trifolium/strategy/v0/predictor.py\n"
                "- src/trifolium/strategy/v0/trader.py\n"
                "- src/trifolium/strategy/v0/portfolio.py\n"
                "- src/trifolium/strategy/config/strategy_v0.yaml\n"
                "expected_metric_change must be an object/dict, not a string.\n"
                "The rationale must cite the D2 section being addressed."
            )

        if self.allow_fallback:
            hypothesis = fallback_zero_trade_hypothesis()
            self.last_metadata["fallback_used"] = True
            self.last_metadata["fallback_reason"] = last_error
            self.last_metadata["architect"]["fallback_used"] = True
            return True, hypothesis, None
        return False, None, f"Brain failed schema validation after {retry_count + 1} attempts: {last_error}"

    def evaluate_candidate(self, parent_metrics: dict[str, Any], candidate_metrics: dict[str, Any]) -> tuple[str, str]:
        d2_decision = candidate_metrics.get("d2", {}).get("decision", {})
        if d2_decision:
            verdict = str(d2_decision.get("verdict", "REJECT"))
            reason = str(d2_decision.get("reason", "D2 decision did not include a reason."))
            if verdict == "ACCEPT v_N":
                return "ACCEPT", reason
            if verdict in {"KEEP v_N-1", "NO-OP", "INSUFFICIENT DATA"}:
                return "KEEP", reason
            return "REJECT", reason
        if not candidate_metrics.get("passed", False):
            return "REJECT", "Candidate failed validation gate."
        parent_trades = int(parent_metrics.get("full_backtest", {}).get("trade_count", 0) or 0)
        candidate_trades = int(candidate_metrics.get("full_backtest", {}).get("trade_count", 0) or 0)
        if candidate_trades > parent_trades:
            return "ACCEPT", "Candidate increases trade_count while passing validation."
        return "KEEP", "Candidate passes validation but does not improve the primary zero-trade binding yet."


Brain = TieredBrain
