# Project Goal

**Current Milestone:** Task 05 Self-Evolving Strategy Discovery System
**Defined By:** User
**Date:** 2026-06-22

## Completion Criteria
- [x] Task 02 L0 package exists and is structurally isolated.
- [x] Task 02 L1 checks have independent unit tests.
- [x] Task 02 L2 submit_order orchestration and isolation tests pass.
- [x] Task 02 L3 observability writes account-state logs.
- [x] Task 02 dry-run passes 20 synthetic cases with mocked MT5 adapter.
- [x] Create StrategyV0 L0 module/config structure with module docstrings.
- [x] Implement Layer 1 per-symbol ridge ensemble predictor.
- [x] Implement Layer 2 signal compression, discretized sizing, and cross-sectional selection.
- [x] Implement portfolio constraints and proportional scaling.
- [x] Implement StrategyV0 orchestration compatible with Task 03 Strategy base.
- [x] Compile/import/test StrategyV0.
- [x] Attempt validation through Task 03 where feasible and stop on required failure gates.
- [x] Refactor L5 validation into reusable callable API for future self-evolving loop.
- [x] Implement bar-level multi-symbol fast path for StrategyV0 L5 validation.
- [x] Run StrategyV0 L5 validation and produce machine-readable JSON plus markdown.
- [x] Produce 4-strategy comparison table for do_nothing, buy_and_hold_audusd, ping_pong_audusd, and strategy_v0.
- [x] Create guarded L6 live readiness harness without starting live deployment.
- [ ] Pass actual L6 runtime readiness after principal approves Risk Gate production mode.
- [x] Initialize `Sextant` continuity files under the workspace root.
- [x] Read the Task Pool files provided by the user.
- [x] Convert Task Pool requirements into durable project state.
- [x] Execute feasible Task Pool actions in the workspace.
- [x] Record outcomes and remaining work in `Sextant`.
- [x] Initialize git tracking in the repo root.
- [x] Install `MetaTrader5` and base packages in `.venv`.
- [x] Create `.env.example` and ignored `.env` template.
- [x] Confirm MT5 GUI login and Day 1 manual trading requirement.
- [x] Complete setup sequence a-h and stop before credential-dependent checks.
- [x] Principal fills `.env` with MT5 credentials.
- [x] Create Task 01 MT5 pipeline files.
- [x] Resolve MT5 authorization failure and pass Task 01 L0 runtime checks.
- [x] Execute Task 01 L1 read checks.
- [x] Deprecate Task 01 L2 calibration and keep `scripts/calibration_trade.py` as archive only.
- [x] Receive and verify presence of backtest data directory.
- [x] Install/confirm parquet reader dependency for Task 03 L0 inventory.
- [x] Run Task 03 L0 data inventory.
- [x] Build C1 NVIDIA NIM client and pass early API-key sanity check.
- [x] Build C2 Anthropic client and pass early credit/API sanity check.
- [x] Build C3 Strategy Element Table.
- [x] Build C4 SQLite Strategy Memory.
- [x] Build C5 Scope Guard with D1 B+ enforcement.
- [x] Build C6 Guardrails with NeMo attempt and Pydantic fallback.
- [x] Build C7 Brain agent.
- [x] Build C8 Coder agent with sandbox patching.
- [x] Build C9 8-step loop orchestrator.
- [x] Build `scripts/run_loop_iteration.py`, `scripts/run_loop_continuous.py`, and `scripts/demo_ui.py`.
- [x] Pass adversarial institution-boundary tests.
- [x] Run end-to-end loop iteration from parent `v0`.

## Current Focus
Phase H produced a robust, risk-clean FX-only candidate but still no positive long-window edge; next focus is new alpha architecture rather than more StrategyV0 risk wrapping.
