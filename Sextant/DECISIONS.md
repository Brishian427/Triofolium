# Technical Decision Record

## 2026-06-25 Phase G Conviction-Based Redesign From v0 Baseline

**Context:** Candidate `v_backtest_pass_candidate_i` passed 6-hour hard gates but failed robustness and 24-hour Risk Discipline; `selected_signal_floor` is suspected of forcing dense low-conviction participation.
**Options:** Continue tuning from candidate I; start from v0 and keep only structural fixes; force more participation until metrics improve.
**Decision:** Create `v_conviction_redesign` from v0 baseline, preserve only the predictor-fit and risk-accounting fixes, remove forced participation, and use lowered but still discretized conviction thresholds.
**Rationale:** This tests whether StrategyV0's signal has genuine edge when sizing remains conviction-graded instead of participation-forced.
**Consequences:** Outcomes (b), (c), and (d) are valid no-deploy findings. Live deployment remains blocked unless the 30-day validation meets outcome (a) and the secondary 24-hour validation also preserves Risk Discipline 100.

## 2026-06-25 No-Deploy After Phase G Classification d

**Context:** `v_conviction_redesign` traded actively over the maximum available window but produced negative return, Risk Discipline `90`, and Robustness `UNSTABLE`.
**Options:** Deploy despite D2 hard-gate failure; continue threshold hacking; stop and record the architecture finding.
**Decision:** Stop before G3, do not run live deployment, and classify the result as Phase G outcome `d`.
**Rationale:** D2 Section 2 Risk Discipline failed and D2 Section 6 Robustness failed; no secondary metric can override a hard-gate or robustness violation.
**Consequences:** Risk Gate remains in calibration mode. The next valid work is architectural redesign or concentration-control redesign, not live launch.

## 2026-06-25 Phase H Attribution First, Then Risk-Budgeted FX Candidate

**Context:** Phase G showed active trading with negative expectancy, concentration penalty, and robustness failure; further threshold tweaking would likely repeat the same failure mode.
**Options:** Continue threshold tuning; add forced participation again; build attribution and a cost-aware/risk-budgeted candidate.
**Decision:** Start Phase H with attribution tooling, then test a sandbox `v_fx_only_risk_budgeted` candidate using optional cost and risk-budget controls.
**Rationale:** The next experiment should separate alpha failure from portfolio construction failure and prevent concentration violations by construction.
**Consequences:** Live deployment stays blocked. If the FX-only risk-budgeted candidate fails, the conclusion will be about StrategyV0 architecture rather than another threshold search.

## 2026-06-25 No-Deploy After Phase H Classification b

**Context:** Phase H H2 strict candidate passed hard gates and robustness, but long-window Total Return remained slightly negative.
**Options:** Deploy a risk-clean but non-positive candidate; keep tightening risk wrappers; stop and require a new alpha architecture.
**Decision:** Do not deploy `v_fx_only_risk_budgeted_h2_strict`; classify it as outcome `b`.
**Rationale:** The risk wrapper succeeded, but D2 primary objective did not: non-positive total return means there is no validated edge to deploy.
**Consequences:** Future work should focus on signal architecture or target formulation rather than more portfolio/risk shell improvements around the same v0 predictor.

## 2026-06-25 Select v_backtest_pass_candidate_i As First Backtest-Gate-Pass Candidate

**Context:** The latest principal request was to tune a strategy version that can pass backtest first and explicitly not go live. Multiple sandbox candidates addressed warmup, destroyer neutralization, sizing thresholds, and concentration risk.
**Options:** Keep the last zero-trade diagnostic candidate; select the first candidate passing D2 6-hour hard gates; continue tuning until positive/robust performance appears in the same round.
**Decision:** Select `sandboxes\v_backtest_pass_candidate_i` as the first sandbox candidate that passes D2 6-hour hard gates, but only as a backtest-gate-pass artifact.
**Rationale:** Candidate I produced 37 trades, 14 active intervals, Risk Discipline 100, and MaxDD 0.301949% in the 6-hour D2 backtest while preserving the no-live constraint.
**Consequences:** Candidate I is not promoted to live: its 6-hour return is negative, D2 decision is `KEEP v_N-1`, and the 24-hour sanity check fails Risk Discipline with score 90. Future work should improve return and robustness before any L6/live path resumes.

## 2026-06-25 Sandbox-Only Backtest Tuning Before Live

**Context:** The principal requested a strategy version that can pass backtest first and explicitly said not to go live.
**Options:** Modify live StrategyV0 config directly; tune in sandbox and only promote after passing backtest review; go straight to production/live.
**Decision:** Tune only sandbox StrategyV0 candidates and stop after backtest results.
**Rationale:** The last candidate failed D2 trade gates, and live runner/risk production readiness remain separate blockers.
**Consequences:** This round may produce a backtest-pass candidate artifact, but it is not live-deployed and does not change Risk Gate production mode.

## 2026-06-25 Stop Live Deployment After Diagnostic Fix Failed Phase E

**Context:** The principal approved conditional live deployment after a diagnostic fix, but Phase E required `v_diagnostic_fix` to produce more than 5 trades, keep Risk Discipline at 100, and keep MaxDD below 3%.
**Options:** Deploy despite the failed diagnostic fix; stack additional strategy changes until trades appear; stop and report the serial zero-trade blockers.
**Decision:** Stop before production mode and live deployment because `v_diagnostic_fix` still produced 0 trades and D2 `REJECT`.
**Rationale:** The explicit Phase E deployment gate was not met, and stacking more fixes would exceed the requested one-fix diagnostic scope.
**Consequences:** Risk Gate remains in calibration mode. The next candidate should target the sizing-threshold blocker, and live deployment also needs a real bar-feed/order loop because the current live runner is still a readiness/heartbeat harness.

## 2026-06-25 Architecture 5 Robust Tiered Brain

**Context:** Ultra 550B remained unavailable after 300s timeout tests, and the principal requested a robust two-tier Brain architecture for Task 05.
**Options:** Keep Ultra as primary; use Super for all Brain calls; split navigation and architecture into separate tiers with Mistral Nemotron and Super.
**Decision:** Refactor Brain to `TieredBrain` with `mistralai/mistral-nemotron` as navigator, `nvidia/nemotron-3-super-120b-a12b` as architect, `nvidia/nemotron-3-nano-30b-a3b` as fallback, and Ultra documented as disabled.
**Rationale:** This preserves a fast low-stakes navigation tier and a stronger high-stakes architecture tier while avoiding Ultra's persistent timeout failure.
**Consequences:** Super architect is now the verified working high-stakes model. Mistral passed minimal sanity but degraded during real E2E, so Nano fallback remains necessary for reliable demos.

## 2026-06-25 Config-Driven NIM Timeout Before Model Switch

**Context:** Ultra 550B timed out during Task 05 E2E at the original 45s Brain timeout, but the principal asked to try a longer Ultra timeout before switching models.
**Options:** Keep 45s and rely on fallback; switch Brain to Super 120B; make timeout config-driven and set Ultra timeout to 300s while preserving fallback.
**Decision:** Make timeout config-driven with `brain.timeout_seconds: 300`, keep Ultra 550B as the selected Brain model, and preserve fail-soft fallback behavior.
**Rationale:** This tests whether the blocker is simply conservative client timeout without changing the demo model story or bypassing the verified fallback path.
**Consequences:** E2E attempts can now spend up to about five minutes waiting on Ultra before falling back; controlled diagnostics showed Ultra still timed out at 300s, so future demos should account for this latency risk.

## 2026-06-25 Use Guardrails Fallback and Deterministic Patch Fallbacks

**Context:** Task 05 requires NeMo Guardrails if practical and real NIM/Anthropic calls for the loop, but external model/tooling calls may fail or return unusable formatting under the deadline.
**Options:** Block on NeMo/native LLM output; use Pydantic-only guardrails and deterministic safe fallbacks after real API calls are attempted; skip API calls entirely.
**Decision:** Use Pydantic-only guardrails after NeMo install failed, and allow Brain/Coder safe fallbacks only after real NIM/Anthropic calls are attempted and logged.
**Rationale:** This preserves the audit trail and demo narrative while keeping institution-as-first-class boundaries enforced by deterministic code.
**Consequences:** Final iteration `30021ae2` completed with real API attempts logged, but the hypothesis/patch were safe fallbacks because NIM timed out and Anthropic formatting needed normalization.

## 2026-06-25 Task 05 Plan A Boundary Rules

**Context:** Task 05 starts a self-improving loop that can generate and patch candidate strategies.
**Options:** Let candidates patch the live tree; isolate candidates in sandboxes; defer the loop.
**Decision:** Build the loop in Plan A mode but keep candidate patches sandbox-only. The loop must not modify live StrategyV0, `risk_gate`, `risk_limits.yaml`, or `strategy.py`.
**Rationale:** This preserves institution-as-first-class safety while still allowing a real first iteration and demo narrative.
**Consequences:** Scope guard and adversarial tests are mandatory acceptance evidence. Any candidate that targets forbidden files is skipped and not written to memory.

## 2026-06-25 Deprecate Task 01 L2 Calibration

**Context:** Day 1 trading was manually satisfied and the AUDUSD legacy position was reported flat, making the original Python calibration trade unnecessary.
**Options:** Keep Task 01 L2 active; delete the calibration script; mark L2 deprecated and keep the script as archive.
**Decision:** Mark Task 01 L2 calibration deprecated and keep `scripts\calibration_trade.py` as archive only.
**Rationale:** Any future Python order must go through Risk Gate, and the calibration trade no longer serves a functional requirement.
**Consequences:** Future work should not spend time maintaining or running Task 01 L2 unless the principal explicitly reopens it.

## 2026-06-25 Make L5 Validation Callable and Cache Bar Data

**Context:** The self-improving loop in Task 05 will need to validate many candidate strategies through the same L5 gate.
**Options:** Keep L5 as a one-shot CLI script; expose a callable while leaving existing script behavior intact; build the full self-improving loop now.
**Decision:** Add `trifolium.validation.validate_strategy(...) -> ValidationResult` and cache StrategyV0 bar data for repeated Filter 1/2/3 runs.
**Rationale:** This gives Task 05 a reusable deployment gate without prematurely building the loop. Cached bar replay preserves bar-level semantics and avoids repeated parquet scans.
**Consequences:** L5 now writes both human-readable markdown and machine-readable JSON. Task 05 can call the validation API directly.

## 2026-06-25 Keep L6 Live Start Principal-Gated

**Context:** StrategyV0 L5 passed, but P0 Risk Gate live approval was explicitly deferred.
**Options:** Flip Risk Gate to production and run live readiness; create no L6 script; create a guarded L6 harness that refuses live start until production mode and principal approval are present.
**Decision:** Create `scripts\live_run_strategy_v0.py` as a guarded readiness harness and leave `config\risk_limits.yaml` in calibration mode.
**Rationale:** This satisfies the readiness implementation work while preserving institution-as-first-class safety and the principal's approval boundary.
**Consequences:** The script exists and tests pass, but actual L6 runtime readiness remains blocked until production mode is approved.

## 2026-06-24 Risk Gate L0 Fails Closed

**Context:** Task 02 requires a mandatory physical door before MT5, but L1 checks and L2 integration are not implemented yet.
**Options:** Leave the old adapter send path active; create a pass-through Risk Gate; create Risk Gate L0 but reject all orders until checks are implemented.
**Decision:** Create Risk Gate L0 with a public `submit_order` entrypoint that rejects all orders until L1/L2 are complete, and disable direct MT5 sending in the legacy adapter order helpers.
**Rationale:** This satisfies structural isolation without creating a half-built live order route. It preserves the fail-closed rule and prevents calibration or strategy code from bypassing the future gate.
**Consequences:** Existing Task 01 calibration helpers cannot send live orders until L2 re-integrates sending through Risk Gate. This is intentional for tonight's safety pivot.

## 2026-06-24 Implement StrategyV0 Ridge Without New Dependencies

**Context:** Task 04 requires per-symbol Ridge ensembles, but the current environment does not need another heavy dependency to satisfy L0-L4.
**Options:** Install scikit-learn; implement a minimal NumPy closed-form ridge regressor; defer predictor implementation.
**Decision:** Implement a small NumPy ridge regressor with an unpenalized intercept and bootstrap ensembles.
**Rationale:** NumPy is already installed and sufficient for ridge regression in this simple predictor, keeping the environment smaller while preserving the required model class behavior.
**Consequences:** The predictor has no scikit-learn dependency. Future work can swap in sklearn if model diagnostics or production parity require it.

## 2026-06-24 Stream-Preserving Buy-and-Hold Validation Path

**Context:** The generic event engine timed out after 20 minutes on a single full-range `buy_and_hold_audusd` run because it constructs Python/Pydantic/Decimal objects per tick.
**Options:** Keep the generic engine and accept impractical runtime; use a no-op-style shortcut; add a strategy-specific row-group streaming evaluator that still processes every valid AUDUSD tick.
**Decision:** Add a validation-layer fast path only for `BuyAndHoldAUDUSDStrategy` with `symbols == ["AUDUSD"]`.
**Rationale:** Buy-and-hold has deterministic one-shot behavior: first valid tick ask is the entry, each subsequent bid determines unrealized P&L, and 15-minute equity samples can be computed while streaming row groups. This preserves the price-path dependency without per-tick object construction.
**Consequences:** `buy_and_hold_audusd` validation now completes in about 104 seconds and records processed/skipped tick counts. General strategies still use the event engine unless given their own semantics-preserving evaluator.

## 2026-06-22 Use Sextant for Project Continuity

**Context:** The user explicitly requested project continuity skills and execution of the Task Pool contents.
**Options:** Use transient chat context only; create root-level status files; create the skill-defined `Sextant` folder and state files.
**Decision:** Use `D:\Desktop\Nucleus\Triofolium\Sextant` as the durable project memory location.
**Rationale:** The selected skill requires continuity state under `Sextant`, and this keeps task execution auditable across sessions.
**Consequences:** Future project status, plans, decisions, session logs, and deltas should be read from and written to `Sextant`.

## 2026-06-22 Stop Before Trading Pipeline Code Until L0 Environment Is Valid

**Context:** Task 01 requires MT5 credentials, `MetaTrader5`, git hygiene, and a working MT5 connection before claiming L0. The Charter says to stop before writing code if hard environmental assumptions are wrong.
**Options:** Continue scaffolding project code despite missing prerequisites; install and initialize everything without user-provided credentials; stop and record the blockers.
**Decision:** Stop before writing project trading code and record the exact L0 blockers.
**Rationale:** Missing `.env`, missing `MetaTrader5`, and missing git tracking make the Task 01 acceptance criteria unverifiable.
**Consequences:** Next execution should first restore the L0 environment, then implement and run `scripts/smoke_test_mt5.py`.

## 2026-06-22 Use Requirements File for Initial Python Setup

**Context:** The user directed this setup round to use `requirements.txt` instead of `pyproject.toml`.
**Options:** Create `pyproject.toml`; create `requirements.txt` from `pip freeze`; defer dependency pinning.
**Decision:** Use `.venv` plus `requirements.txt` for the initial Task 01 environment setup.
**Rationale:** This follows the user's request for a simple setup path while still producing pinned package versions.
**Consequences:** Future dependency changes should update `requirements.txt` until the principal approves moving to `pyproject.toml`.

## 2026-06-22 Use MT5 Broker Server Name

**Context:** The principal observed that the MT5 server is shown as `MEXIntGroup-Demo`, the broker name registered for Syphonix, rather than the bare IP address.
**Options:** Keep using `3.11.134.149:443`; use the MT5 broker server name `MEXIntGroup-Demo`.
**Decision:** Use `MEXIntGroup-Demo` for `MT5_SERVER`.
**Rationale:** MT5 Python initialization should match the server name recognized by the local MT5 terminal login.
**Consequences:** `.env.example` now documents `MT5_SERVER=MEXIntGroup-Demo`; the principal should fill `.env` with the same value.

## 2026-06-22 Supersede MT5 Server Name With Principal GUI Observation

**Context:** The principal reported the actual successful MT5 GUI login details after the previous `MEXIntGroup-Demo` note.
**Options:** Keep using `MEXIntGroup-Demo`; use the successful MT5 input field `3.11.134.149:443` while recording broker display `FTWorldwide-MainTrade`.
**Decision:** Treat `3.11.134.149:443` as the `.env` `MT5_SERVER` input value and record `FTWorldwide-MainTrade` as the broker MT5 connected to.
**Rationale:** The principal confirmed this exact GUI configuration logged into account `10181` successfully.
**Consequences:** Future Task 01 L0/L1 work should load `MT5_SERVER` from `.env` without printing it; previous `MEXIntGroup-Demo` guidance is superseded.

## 2026-06-22 Do Not Print Environment Secrets

**Context:** The principal explicitly instructed that `.env` contents must never be printed in conversation, logs, or records.
**Options:** Print `.env` during debugging; avoid reading or displaying `.env` and only verify presence/shape through non-secret checks.
**Decision:** Never print `.env` contents.
**Rationale:** `.env` will contain MT5 credentials.
**Consequences:** Verification should use file existence, git ignore status, and controlled code paths that do not echo values.

## 2026-06-22 Keep L2 Calibration Behind Environment Gate

**Context:** The principal requested Task 01 L0-L2 execution after earlier deferring L2.
**Options:** Run the live calibration trade directly; implement and run L2 only if `MT5_CALIBRATION_MODE=1` is explicitly set.
**Decision:** Preserve the `MT5_CALIBRATION_MODE=1` gate before any L2 live order.
**Rationale:** Task 01 defines this as the deliberate principal-supervised acknowledgement for a real order.
**Consequences:** L0/L1 can run with filled `.env`; L2 reports blocked if the gate is absent or not set to `1`.

## 2026-06-25 Principal Override Deploy H2 Strict

**Context:** D2 validation classifies `v_fx_only_risk_budgeted_h2_strict` as outcome `b` because it is robust, risk-clean, and directionally marginal, but has a slightly negative total return after spread cost.
**Options:** Preserve the D2 no-deploy decision; force a threshold hack to find positive return; accept the principal's explicit 14:45 deployment decision for observing real production behavior.
**Decision:** Deploy only `v_fx_only_risk_budgeted_h2_strict`, after all 7 live hard-kill conditions are implemented and verified.
**Rationale:** The principal explicitly approved this candidate as the best honest finding across the candidate set: D2 hard gates pass, robustness is robust, Risk Discipline is 100, MaxDD is tiny, and win rate is marginally positive despite spread drag.
**Consequences:** The deployment is an observation-driven production experiment, not a D2 alpha acceptance. Risk Gate production mode and the live runner may be enabled only after hard kills pass; Phase K exploration remains sandbox-only and cannot replace the live candidate automatically.

## 2026-06-25 Principal Override Relax H2 Session Gate

**Context:** H2 strict live runner started successfully, but J6 first-trade verification remained pending because the deployed config allowed only London morning. The principal clarified that the session gate is attribution-derived optimization, not a safety boundary.
**Options:** Wait until the next London morning; disable the session gate entirely; expand the session gate while preserving all Risk Gate hard kills and Phase H controls.
**Decision:** Expand the live session gate to allow current-session trading while leaving the session gate enabled and preserving cost gate, concentration budget, per-symbol caps, and all 7 hard kills.
**Rationale:** J6 needs a natural first-order verification, and the actual safety boundary is the Risk Gate plus live hard-kill layer, not the attribution-derived session filter.
**Consequences:** Restart the live runner with the existing session-start equity baseline `999988.39` so the $1000 session-loss tracker is continuous across the config reload. Phase K remains blocked until a real first order is confirmed.

## 2026-06-25 Principal Verdict Disable Concentration Gate

**Context:** After session-gate relaxation, StrategyV0 produced strong live signals and non-zero trader targets, but the Phase H `35%` max single-symbol concentration gate zeroed the portfolio because only two symbols had tradable target lots.
**Options:** Keep the 35% cap and remain live-but-idle; relax the cap to 50-60%; disable the concentration gate and rely on Risk Gate hard kills plus session-loss controls as the actual safety boundary.
**Decision:** Disable the StrategyV0 single-symbol concentration gate for live H2 strict by setting it to the disabled threshold, while keeping cost gate, session gate, FX-only universe, per-symbol XAGUSD cap, per-symbol notional cap, and all Risk Gate hard kills.
**Rationale:** The principal judged the 35% concentration rule as an attribution-derived optimization that suppressed legitimate conviction trades, not a 14:45 explicit safety requirement. Live safety remains enforced by the 7 hard kills and the $1000 session-loss floor.
**Consequences:** J-triple-prime can verify first live order naturally at the next bar close. The live runner must restart with the original `999988.39` session baseline so the loss floor remains `998988.39`.

## 2026-06-25 Treat Flat MT5 Margin Level Zero as Healthy

**Context:** MT5 reports `margin_level=0.0` when the account has no open positions. Risk Gate `check_account_health` interpreted this as below the `200%` floor and rejected the first opening order, despite hard-kill and observability already treating flat-account margin zero as non-actionable.
**Options:** Leave Risk Gate stricter and block first order; fake a high margin level in the live runner; make `check_account_health` understand flat-account MT5 margin semantics.
**Decision:** In `check_account_health`, treat `margin_level_pct == 0` with `open_positions_count == 0` as healthy if equity is positive.
**Rationale:** The hard margin floor protects accounts with active margin exposure. A flat account with no margin used cannot breach margin level in the same sense, and projected exposure is separately checked by Risk Gate leverage and lot caps.
**Consequences:** First opening orders can proceed to later checks and MT5 execution, while low-margin accounts with open positions still fail closed.
