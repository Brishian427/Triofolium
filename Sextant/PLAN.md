# Action Plan

**For Milestone:** Execute Task Pool Continuity Setup
**Created On:** 2026-06-22

## Steps
1. [done 2026-06-22] Create `Sextant` folder and required continuity files.
2. [done 2026-06-22] Read `Task Pool/00_charter.md`, `Task Pool/01_task_pipeline.md`, `Task Pool/02_task_risk_gate.md`, and `Task Pool/03_task_backtest.md`.
3. [done 2026-06-22] Extract required actions, risks, decisions, and completion criteria from the Task Pool files.
4. [done 2026-06-22] Execute feasible workspace actions from the Task Pool: initialization, task extraction, and prerequisite audit.
5. [done 2026-06-22] Update `Sextant` status, goal, plan, journal, decisions, and delta with exact outcomes.
6. [done 2026-06-22] Run `git init` in the repo root and report.
7. [done 2026-06-22] Create or update `.gitignore` with `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `logs/`, `reports/`, and `*.egg-info/`, then report.
8. [done 2026-06-22] Run `python -m venv .venv` and report.
9. [done 2026-06-22] Install `MetaTrader5`, `python-dotenv`, `pydantic`, `pydantic-settings`, and `PyYAML` into `.venv`, then report.
10. [done 2026-06-22] Generate `requirements.txt` from `.venv` using `pip freeze`, then report.
11. [done 2026-06-22] Create or update `.env.example` with exactly the three blank fields `MT5_LOGIN=`, `MT5_PASSWORD=`, and `MT5_SERVER=`, then report.
12. [done 2026-06-22] Create or update blank `.env` for the principal to fill; do not print its contents, then report.
13. [done 2026-06-22] Stop and wait for the principal to fill `.env` before continuing Task 01 L0/L1.
14. [done 2026-06-22] Verify `.env` contains all required non-empty keys without printing values.
15. [done 2026-06-22] Create Task 01 MT5 adapter modules, instruments config, README, smoke test script, and calibration trade script.
16. [done 2026-06-22] Retry Task 01 L0 after resolving MT5 authorization failure.
17. [done 2026-06-22] Execute Task 01 L1 read checks only after L0 passes.
18. [blocked 2026-06-22] Execute Task 01 L2 calibration script only if L0/L1 pass and `MT5_CALIBRATION_MODE=1` is present; currently blocked because the gate is not set.
19. If approved, commit safe project files while keeping `.env` ignored.
20. [done 2026-06-24] Verify backtest data directory presence, total size, file count, file types, README summary, and initial competition-symbol coverage.
21. [done 2026-06-24] Install parquet/report dependencies (`pyarrow`, `pandas`, `matplotlib`) and update `requirements.txt`.
22. [done 2026-06-24] Create `scripts/inventory_backtest_data.py` to stream-inspect parquet files and produce `reports/data_inventory.md`.
23. [done 2026-06-24] Run Task 03 L0 data inventory and produce `reports/data_inventory.md` plus spread heatmap PNG.
24. Review `reports/data_inventory.md` for missing crypto symbols and sample-based spread/depth limitations.
25. [done 2026-06-24] Verify source of P&L discrepancy using MT5 read-only account/position queries.
26. Principal decides manually whether to close the still-open AUDUSD position; no automated close before Risk Gate approval.
27. [done 2026-06-24] Build Task 03 L1 backtest package: data loader, executor, equity tracker, metrics, engine, and strategy base.
28. [done 2026-06-24] Build Task 03 baseline strategies: do nothing, buy-and-hold AUDUSD, ping-pong AUDUSD, and simple mean reversion.
29. [done 2026-06-24] Build Task 03 L2 validation script with three filters and report/plot outputs.
30. [done 2026-06-24] Build Task 03 L3 round simulation script with no-trading audit windows and optional recalibration.
31. [done 2026-06-24] Add unit tests for executor, equity tracker, and no-future-data guard.
32. [partial 2026-06-24] Run unit tests and acceptance baseline validations; unit tests passed, `do_nothing` passed, and `buy_and_hold_audusd` completed with Filter 1/2/3 FAIL.
33. [done 2026-06-24] Optimize `do_nothing` validation runtime with an exact no-op fast path preserving full-range semantics.
34. Stop acceptance after `buy_and_hold_audusd` filter failure; wait for principal direction before `ping_pong_audusd`, `simple_mean_reversion`, or round simulation.
35. [done 2026-06-24] Run `buy_and_hold_audusd` as the next acceptance item while preserving full AUDUSD tick-stream mark-to-market semantics.
36. [done 2026-06-24] Execute Task 04 L0-L4 by creating StrategyV0 config, predictor, trader, portfolio constraints, and orchestration modules.
37. [done 2026-06-24] Run compile/import/unit smoke checks for StrategyV0 after L0-L4 implementation.
38. [blocked 2026-06-24] Attempt Task 04 L5 validation only after StrategyV0 imports and produces backtest-compatible orders; a 6-hour validation smoke timed out after 5 minutes, so full 30-day L5 needs runtime optimization first.
39. [done 2026-06-24] Execute Task 02 Risk Gate L0: create isolated package, typed public entrypoint, risk limits config, module-init validation, and remove direct non-gate `mt5.order_send` references.
40. [done 2026-06-24] Continue Task 02 L1 by implementing the eight required independent checks and one unit-test file per check.
41. [done 2026-06-24] Continue Task 02 L2 by wiring `submit_order` to run checks in order, log every request, return structured rejection on failures, and keep the only future live send path inside Risk Gate.
42. [done 2026-06-24] Continue Task 02 L3 after principal acceptance by adding once-per-minute account-state observability, warning near margin floor, and critical logging on LOCKED state.
43. [done 2026-06-24] After L3 tests pass, create and run `scripts\risk_gate_dry_run.py` with 20 synthetic mocked cases, then stop for principal review.
44. Stop and wait for principal review; do not relax live approval gates or proceed to real orders.
45. [done 2026-06-25] Apply Style B pivot: defer P0 live approval, deprecate Task 01 L2 calibration, approve P2 L5 work, and design L5 validation as a reusable callable for future self-improving loops.
46. [done 2026-06-25] Implement Task 03 bar-level multi-symbol fast path for bar-only strategies such as StrategyV0.
47. [done 2026-06-25] Refactor L5 validation into a callable API that returns machine-readable JSON plus human-readable markdown.
48. [done 2026-06-25] Run full StrategyV0 L5 validation and write JSON/markdown reports plus 4-strategy comparison.
49. [done 2026-06-25] Create guarded L6 readiness harness `scripts\live_run_strategy_v0.py` with production-mode, legacy-AUDUSD-flat, margin emergency, and JSONL logging checks.
50. [blocked 2026-06-25] Pass actual L6 runtime readiness; blocked because Risk Gate mode remains `calibration` until principal approves production mode.
51. [done 2026-06-25] Execute Task 05 Plan A in spec order C1-C9 without pausing between components; resumed after principal filled API keys.
52. [done 2026-06-25] Build C1 NIM client and immediately test `NVIDIA_API_KEY` with a cheap `nvidia/nemotron-3-nano-30b-a3b` call.
53. [done 2026-06-25] Build C2 Anthropic client and immediately test `ANTHROPIC_API_KEY` with a cheap call; stop immediately on credit/auth error.
54. [done 2026-06-25] Build C3 element table, C4 strategy memory, C5 scope guard, C6 guardrails, C7 brain, C8 coder, and C9 orchestrator.
55. [done 2026-06-25] Add required Task 05 scripts: `run_loop_iteration.py`, `run_loop_continuous.py`, and `demo_ui.py`.
56. [done 2026-06-25] Run checkpoint test report: `pytest tests -q` result `61 passed`.
57. [done 2026-06-25] Run final compile, pytest, static grep, adversarial tests, and `scripts/run_loop_iteration.py --parent v0`.
58. [done 2026-06-25] Make Task 05 NIM Brain timeout config-driven with 300s default while keeping Ultra 550B as the selected Brain model.
59. [done 2026-06-25] Re-run one E2E self-improving iteration; Ultra still timed out at 300s, so the controlled A-D diagnostic was rerun and logged.
60. [done 2026-06-25] Commit `pytest.ini` and the timeout/config fix after tests and the E2E/diagnostic result are logged.
61. [done 2026-06-25] Implement Architecture 5 robust Task 05 Brain: Mistral Nemotron navigator plus Super 120B architect, with Nano as documented local/API fallback.
62. [done 2026-06-25] Re-run Task 05 tests, static checks, and one E2E iteration proving both TieredBrain tiers fire correctly.
63. [done 2026-06-25] Commit Architecture 5 robust configuration with the requested commit message.
64. [done 2026-06-25] Implement D2 9-section validation framework in L5 markdown/JSON and align Brain prompt to the D2 sections before any further deployment work.
65. [done 2026-06-25] Fix Sonnet unified diff output/application path, then run 10 D2-formatted self-improving iterations without pausing.
66. [done 2026-06-25] Select best candidate only if it meets trade_count, risk discipline, drawdown, and return criteria; no candidate qualified, so no-deploy was selected.
67. [blocked 2026-06-25] Strengthen Risk Gate production hard kills including $1000 session cumulative loss from startup equity, then run L6 dry-run readiness; blocked by A4 no-qualifying-candidate stop condition.
68. [blocked 2026-06-25] Deploy live only if D2 candidate criteria and Risk Gate hard-kill/readiness checks all pass; blocked because all 10 candidates failed D2 Section 2 Trade Count/Active Intervals.
69. [done 2026-06-25] Diagnose StrategyV0 zero-trade root cause with 6-hour verbose internal-state backtests and write JSONL plus markdown diagnostic logs.
70. [done 2026-06-25] Implement targeted warmup-aware validation plus sandbox `v_diagnostic_fix` destroyer-threshold change, then run a 6-hour D2 backtest.
71. [blocked 2026-06-25] Deploy `v_diagnostic_fix` only if it produces more than 5 trades, keeps Risk Discipline at 100, and keeps MaxDD below 3%; blocked because the candidate still produced 0 trades.
72. [done 2026-06-25] Add strategy-specific metrics visibility to the demo UI so backtest metrics and live metrics are visible to the principal.
73. [done 2026-06-25] Tune a new sandbox StrategyV0 candidate that addresses the known zero-trade chain: validation warmup, destroyer neutralization, and low-signal sizing thresholds.
74. [done 2026-06-25] Run D2 6-hour backtests for candidate variants and select `sandboxes\v_backtest_pass_candidate_i` as the first version that passes D2 hard gates without live deployment.
75. [done 2026-06-25] Stop before live deployment; Risk Gate stayed in calibration mode and no MT5 live orders were sent in this tuning round.
76. [done 2026-06-25] Create `v_conviction_redesign` from v0 baseline, preserving only destroyer-threshold, shorter-lookback, notional-concentration, and XAGUSD cap changes while dropping forced participation.
77. [done 2026-06-25] Run D2 validation over the 30-day or maximum available historical window and classify the outcome as `d`.
78. [done 2026-06-25] Classification was not (a), so stop without live deployment and report the StrategyV0 architecture finding honestly.
79. [blocked 2026-06-25] Secondary 24-hour validation was not run because Phase G outcome was `d`, not (a).
80. [done 2026-06-25] Verify compile/tests/static MT5 isolation, update Sextant, and commit pending Phase D/E/G/D2/UI work with result-coded commit message.
81. [done 2026-06-25] Start Phase H by adding attribution tooling for Phase G results: symbol/day/session PnL, trade count, win rate, spread cost proxy, and concentration evidence.
82. [done 2026-06-25] Add optional StrategyV0 controls for cost-aware entry gating and risk-budgeted portfolio sizing while preserving default behavior.
83. [done 2026-06-25] Create sandbox candidate `v_fx_only_risk_budgeted` from v0-family lessons: FX-only, short lookback, no forced participation, cost gate, and symbol risk budget.
84. [done 2026-06-25] Run maximum-window D2 validation for `v_fx_only_risk_budgeted` and stricter H2 variant; stop before live because best result is classification `b`, not positive-return deployment candidate.
85. [done 2026-06-25] Run compile/tests/static MT5 isolation, update Sextant, and commit Phase H result.
86. [done 2026-06-25] Phase J: principal-approved live deployment of `v_fx_only_risk_budgeted_h2_strict` after implementing and verifying all 7 hard-kill protections.
87. [done 2026-06-25] Copy H2 strict candidate files into live StrategyV0 config scope without touching `src\trifolium\strategy\v0\strategy.py`.
88. [done 2026-06-25] Switch `config\risk_limits.yaml` to production only after hard-kill verification is implemented and tests pass.
89. [done 2026-06-25] Commit before live with the principal-approved H2 deploy message, then launch `scripts\live_run_strategy_v0.py`.
90. [in_progress 2026-06-25] Verify live runner startup, hard-kill armed status, session baseline equity, and first-order status; live runner is active, but first order is pending because the H2 strict London-morning session gate is currently closed.
91. [pending 2026-06-25] Phase K: after J6 live order confirmation only, run sandbox `v_absolute_return` exploration and do not auto-deploy it.
92. [in_progress 2026-06-25] J-prime: principal override relaxes H2 session gate for current-session first-trade verification while preserving Risk Gate hard kills and Phase H controls.

## Constraints
- All project continuity state must live under `D:\Desktop\Nucleus\Triofolium\Sextant`.
- Preserve Task Pool source files unless a task explicitly requires changing them.
- Charter requires stopping before writing project code if hard environmental assumptions are wrong.
- Do not run live calibration trades without principal supervision and `MT5_CALIBRATION_MODE=1`.
- Follow the user-specified setup order exactly and report after each step.
- For MT5 login, the confirmed GUI server input value is `3.11.134.149:443`; MT5 may display connected broker `FTWorldwide-MainTrade`.
- Never print `.env` contents in conversation, logs, or project records.
- Task 01 L2 calibration trade is now requested by the principal, but it must still pass the explicit `MT5_CALIBRATION_MODE=1` live-order gate.
- Treat `D:\Desktop\Nucleus\Triofolium\pricer-output-2026-05-11_2026-06-10` as the deployed backtest data path.
- Do not load the full 20.325 GiB dataset into memory; Task 03 code must stream or inspect incrementally.
- No live MT5 calls from `src/trifolium/backtest/`.
- Use Decimal for P&L, account equity, lot, notional, and spread-cost money math; floats are acceptable for indicators and plots.
- Task 04 live deployment L6 must not run automatically; principal must explicitly trigger deployment after reviewing logs.
- Strategy code must not call MT5 directly; live order routing must go through Risk Gate once Task 02 exists.
- Task 02 P0 supersedes StrategyV0 deployment tonight; do not deploy StrategyV0 during Round 3.
- Risk Gate must fail closed; L0 should not introduce any live order path before L1-L3 and dry-run are green.
- Task 01 L2 calibration is deprecated; keep `scripts\calibration_trade.py` as archive only and do not maintain it as an active path.
- P0 Risk Gate live approval is deferred; do not switch `config\risk_limits.yaml` to production or start live StrategyV0 without principal approval.
- Task 05 loop must run candidate strategies only in sandbox directories; live StrategyV0 must not be modified by loop iterations.
- Task 05 loop must never modify `src\trifolium\risk_gate\`, `config\risk_limits.yaml`, or `src\trifolium\strategy\v0\strategy.py`.
- Do not print `.env` values; verify only key presence and API outcomes.
- Do not switch Brain to Super for the demo path; keep Ultra as primary and Nano as the verified fallback unless the principal changes this instruction.
- Principal has now explicitly approved live deployment, but D2 implementation, 10-iteration candidate selection, and Risk Gate hard-kill verification are mandatory blockers before live.
- Session loss means cumulative loss from live runner startup equity; at `session_start_equity - 1000`, emergency flatten all positions and halt the loop.
- The diagnostic-fix path supersedes the failed 10-iteration batch only if the sandbox backtest satisfies the Phase E criteria; untested or under-trading fixes must not be deployed.
- Do not proceed to Risk Gate production mode or live launch while the latest diagnostic candidate remains D2 `REJECT`.
- This tuning round is sandbox-only: do not modify `config\risk_limits.yaml`, do not start `scripts\live_run_strategy_v0.py`, and do not send MT5 orders.
- Phase G may only proceed toward live if the long-window candidate satisfies outcome (a) and the secondary 24-hour validation keeps Risk Discipline at 100; otherwise stop before production mode.
- Phase H remains sandbox-only: do not switch Risk Gate production mode, do not launch `scripts\live_run_strategy_v0.py`, and do not send MT5 orders.
- Principal explicitly overrode the Phase H sandbox-only stop for H2 strict on 2026-06-25; deployment is allowed only for `v_fx_only_risk_budgeted_h2_strict` and only after all 7 hard kills are implemented and verified.
- H2 strict deployment must preserve the live StrategyV0 interface lock: do not edit `src\trifolium\strategy\v0\strategy.py` during Phase J wiring.
- Keep H2 strict cost gate, London-morning session gate, FX-only universe, and defensive XAGUSD cap semantics; do not force a first trade outside the allowed session.
- Phase K exploration must not modify the live H2 strict deployment and must not auto-deploy any absolute-return candidate.

## Risks
- 2026-06-22: Task Pool instructions may include ambiguous or high-risk work; pause for confirmation if execution would be destructive or outside the recorded goal.
- 2026-06-22: Continuing without `.env`, `MetaTrader5`, and git setup would violate Task 01/Charter acceptance conditions and could produce unverifiable scaffolding.
- 2026-06-22: `.env` will remain intentionally unfilled; Task 01 L0 smoke testing must not continue until the principal supplies credentials.
- 2026-06-22: `pip` reported a newer version is available, but it was not upgraded because the user requested only the base package installation.
- 2026-06-22: Prior continuity state recorded `MEXIntGroup-Demo`; this is superseded by the principal's update that the MT5 server input field is `3.11.134.149:443` and the connected broker is `FTWorldwide-MainTrade`.
- 2026-06-22: Running L2 places a real order on the competition account; the calibration script must refuse unless `MT5_CALIBRATION_MODE=1` is set.
- 2026-06-22: Current blocker is MT5 authorization failure from Python using `.env`; retry only after verifying terminal login state and credentials.
- 2026-06-22: Future L2 retry should first verify why MT5 reports `trade_allowed=False`.
- 2026-06-24: Task 03 L0 will be incomplete until a parquet reader dependency is available.
- 2026-06-24: Missing crypto symbols in the deployed data may limit competition-faithful backtests unless separate crypto data arrives.
- 2026-06-24: Processing 20.325 GiB may take several minutes; inventory must avoid full-dataset in-memory loads.
- 2026-06-24: Initial pandas-based time parsing hit an `_ArrayMemoryError`; script now uses PyArrow compute and bounded samples for spread quantiles.
- 2026-06-24: AUDUSD position remains live and market P&L can continue changing until manually closed or otherwise resolved.
- 2026-06-24: Full-scope Task 03 may expose data constraints, especially missing competition crypto symbols and sample-based prior inventory assumptions.
- 2026-06-24: Remaining non-noop baselines may still require runtime optimization because Filter 2/3 rerun many tick-level backtests.
- 2026-06-24: `buy_and_hold_audusd` cannot use the no-op fast path; any runtime improvement must still stream every AUDUSD tick needed to compute unrealized P&L.
- 2026-06-24: `buy_and_hold_audusd` is a confirmed negative baseline under current filters; continuing to later baselines without principal acknowledgement may blur acceptance status.
- 2026-06-24: Task 04 lists Task 02 Risk Gate as a prerequisite, but Task 02 is not yet implemented; StrategyV0 can be built for backtest, while live deployment readiness remains blocked.
- 2026-06-24: Full StrategyV0 validation over 9 symbols is likely impractical through the current tick-level event loop; next step is a bar-level/multi-symbol validation path or engine optimization before L5 can be claimed.
- 2026-06-24: Existing Task 01 adapter contains direct `mt5.order_send` references; Task 02 L0 must isolate or disable that legacy send path so there is no non-gate MT5 order route.
- 2026-06-24: L0 intentionally rejects all submitted orders until L1/L2 checks and dry-run are implemented; this is expected fail-closed behavior.
- 2026-06-24: Keep `submit_order` fail-closed during L1; do not relax order routing until all L1 checks and tests are complete.
- 2026-06-24: Run the standing static grep for `mt5.order_send` isolation at the end of L1.
- 2026-06-24: Do not proceed to L3 or dry-run until L2 orchestration is explicit and tested.
- 2026-06-24: L2 tests must monkeypatch the live sender; do not perform real MT5 order sends during integration tests.
- 2026-06-24: Do not run real MT5 orders after L2; dry-run and L3 observability must pass first.
- 2026-06-24: Dry-run must use mocked MT5 sender only and must not relax the single `mt5.order_send` invariant.
- 2026-06-24: Principal explicit approval is still required before any live Risk Gate order or calibration trade can be sent.
- 2026-06-25: Do not build the self-improving loop itself in this round; only make L5 reusable/callable for Task 05.
- 2026-06-25: StrategyV0 L5 currently passes as a flat/no-trade run; treat as validation-gate cleanliness, not trading alpha.
- 2026-06-25: L6 runtime readiness check correctly refuses while Risk Gate mode is `calibration`; this is expected under P0 deferral.
- 2026-06-25: If NVIDIA API sanity check returns 401/403, stop immediately because Brain cannot call NIM.
- 2026-06-25: If Anthropic sanity check reports insufficient credit or auth failure, stop immediately because Coder cannot call Sonnet.
- 2026-06-25: If NeMo Guardrails install/config takes too long or fails, fall back to Pydantic-only guardrails and log the fallback.
- 2026-06-25: C1/C2 sanity cannot start because both required API keys are absent; do not build a fake loop without real Brain/Coder connectivity.
- 2026-06-25: NeMo Guardrails install failed because `annoy` requires Microsoft C++ Build Tools; Pydantic fallback is active.
- 2026-06-25: NIM Ultra calls can be slow or return 504/timeout; final iteration records the real call attempt and uses the safe fallback hypothesis after timeout.
- 2026-06-25: Increasing Ultra timeout to 300s can add up to several minutes to one E2E attempt; preserve fail-soft fallback and log whether the real Ultra call or fallback path was used.
- 2026-06-25: Live deployment is high-risk; if no candidate meets D2 selection criteria or any Risk Gate hard kill is missing/failing, do not deploy despite principal approval.
- 2026-06-25: The UI currently lacks strategy-internal backtest/live metrics; deployment review is impaired until these metrics are surfaced.
- 2026-06-25: StrategyV0 diagnostics revealed serial zero-trade blockers; stacking additional strategy fixes after `v_diagnostic_fix` would exceed the current one-fix Phase E scope.
- 2026-06-25: A candidate can overfit the six-hour D2 gate by forcing tiny signals to trade; mark such a version as backtest-pass candidate only, not live-ready.
- 2026-06-25: Conviction-based redesign may reveal that StrategyV0 has consistent negative expectancy or insufficient trade density over the full available history; treat that as a valid finding rather than forcing another threshold hack.
- 2026-06-25: Removing metals may improve concentration but also remove profitable diversification; Phase H must treat a lower-trade or negative-return FX-only result as useful evidence, not a reason to reintroduce forced participation.
