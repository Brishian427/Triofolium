# Project Status

**Last Updated:** 2026-06-25 14:21:21
**Updated By:** Codex

## Completed
- 2026-06-22: Initialized `Sextant` project continuity folder and required state files.
- 2026-06-22: Read Task Pool files `00_charter.md`, `01_task_pipeline.md`, `02_task_risk_gate.md`, and `03_task_backtest.md`.
- 2026-06-22: Extracted execution order: Task 01 MT5 pipeline gates Task 02 risk gate; Task 03 L0 is offline inventory but needs historical data location.
- 2026-06-22: Audited local prerequisites for Task 01 L0: Windows and Python 3.11.9 are present; MT5 terminal exists at `C:\Program Files\MetaTrader 5\terminal64.exe`.
- 2026-06-22: Initialized git repository in `D:\Desktop\Nucleus\Triofolium`.
- 2026-06-22: Created `.gitignore` covering `.env`, Python caches, virtual environments, logs, and reports.
- 2026-06-22: Created `.venv` and installed `MetaTrader5`, `python-dotenv`, `pydantic`, and `pydantic-settings`.
- 2026-06-22: Generated `requirements.txt` from `.venv`.
- 2026-06-22: Created `.env.example` and `.env` templates; `.env` is ignored by git.
- 2026-06-22: Recorded MT5 broker server name as `MEXIntGroup-Demo` and updated `.env.example` accordingly.
- 2026-06-22: Principal reported successful MT5 GUI login for account `10181` using server input `3.11.134.149:443`; MT5 connected broker displayed as `FTWorldwide-MainTrade`; account mode is Netting and Algo Trading is enabled.
- 2026-06-22: Principal manually satisfied Day 1 trading requirement via MT5 GUI with order `46678` / deal `51380`, market buy `0.01` AUDUSD at `0.70031`, fill latency `13.733 ms`.
- 2026-06-22: Principal reported account status Active, rank `#57/249`, safe by `143` ranks, P&L `-$0.02`.
- 2026-06-22: Re-ran setup sequence a-h: confirmed git repo, updated `.gitignore`, refreshed `.venv`, installed `PyYAML`, regenerated `requirements.txt`, reset `.env.example` to three blank fields, and kept `.env` as a blank ignored template.
- 2026-06-22: Updated ignored `.env` with a local fill-in template for principal-managed MT5 credentials without recording its contents.
- 2026-06-22: Verified `.env` was updated by the principal: required keys exist and are non-empty; `.env` remains ignored by git.
- 2026-06-22: Created Task 01 MT5 adapter package, instruments config, smoke-test script, calibration script, and README.
- 2026-06-22: Verified Python compilation and imports for Task 01 code.
- 2026-06-22: Task 01 L0/L1 runtime smoke test passed after `.env` password update; account `10181` was read successfully and all 15 configured symbols were accessible.
- 2026-06-22: L2 calibration script refused to trade because `MT5_CALIBRATION_MODE=1` is not set; no live order was placed by Codex.
- 2026-06-24: Received backtest data directory `D:\Desktop\Nucleus\Triofolium\pricer-output-2026-05-11_2026-06-10`.
- 2026-06-24: Verified data directory contains 532 files totaling 20.325 GiB: 531 `.parquet` files and 1 `README.txt`.
- 2026-06-24: Verified data README describes xSyphon pricer output for 2026-05-11 through 2026-06-10 with bid/ask and up to 5-level ladder columns.
- 2026-06-24: Initial symbol cross-check found 10 of 15 competition symbols present: AUDUSD, EURCHF, EURGBP, EURUSD, GBPUSD, USDCAD, USDCHF, USDJPY, XAUUSD, XAGUSD.
- 2026-06-24: Installed parquet/report dependencies `pyarrow`, `pandas`, and `matplotlib`; regenerated `requirements.txt`.
- 2026-06-24: Created `scripts/inventory_backtest_data.py` for streaming Task 03 L0 data inventory.
- 2026-06-24: Generated `reports/data_inventory.md` and `reports/spread_heatmap_p95.png`.
- 2026-06-24: Confirmed the 2026-06-22 AUDUSD buy position is still open: ticket `46678`, volume `0.01`, open price `0.70031`, current price `0.69004`, floating profit `-10.27`, swap `0.0`.
- 2026-06-24: Confirmed account has one open position and current equity/profit reflected the AUDUSD floating loss.
- 2026-06-24: Built Task 03 backtest modules, validation script, round simulation script, four baseline strategies, and unit tests.
- 2026-06-24: Unit tests passed: `6 passed`.
- 2026-06-24: Optimized validation for exact no-op strategies and reran `do_nothing`; validation passed with Return `0`, MaxDD `0`, Sharpe `None`, trade_count `0`, and all filters PASS.
- 2026-06-24: Added a stream-preserving fast validation path for `buy_and_hold_audusd` and reran it over the full AUDUSD period; it processed `25,354,588` valid ticks, skipped `2,974,880` invalid ticks, produced report `reports\validation_buy_and_hold_audusd_20260624_145615`, and completed with Filter 1/2/3 FAIL.
- 2026-06-24: Implemented Task 04 StrategyV0 L0-L4 modules: config, per-symbol ridge ensemble predictor, trader transform, portfolio constraints, and Strategy base orchestration.
- 2026-06-24: Added StrategyV0 tests and verified `python -m compileall src scripts tests` plus `pytest tests\test_backtest tests\test_strategy -q`; result `11 passed`.
- 2026-06-24: Completed Task 02 Risk Gate L0: created isolated `src\trifolium\risk_gate` package, typed `OrderRequest`/`OrderResult`, fail-closed `submit_order`, validated `config\risk_limits.yaml` at module import, and removed non-gate Python `mt5.order_send` references.
- 2026-06-24: Completed Task 02 Risk Gate L1: implemented eight independent checks (`lot_size`, `total_leverage`, `single_symbol_concentration`, `numeric_consistency`, `rate_limit`, `direction_sanity`, `account_health`, `hard_floor_drawdown`) and corresponding unit tests.
- 2026-06-24: Verified L1 with `python -m compileall src scripts tests`, full `pytest tests -q` result `24 passed`, standing static grep found no `mt5.order_send`, and tests contain no `MetaTrader5` imports.
- 2026-06-24: Completed Task 02 Risk Gate L2 integration: `submit_order` runs checks in required order, rejects on first failure, rejects on check exception, logs all decisions to `logs\risk_gate_YYYY-MM-DD.jsonl`, calls the Risk Gate-owned MT5 sender only after all checks pass, and includes `tests\test_isolation.py`.
- 2026-06-24: Verified L2 with `python -m compileall src scripts tests`, full `pytest tests -q` result `31 passed`, standing static grep found `mt5.order_send` only in `src\trifolium\risk_gate\execution.py`, and tests contain no `MetaTrader5` imports.
- 2026-06-24: Completed Task 02 Risk Gate L3 observability: added scheduled account-state logging, JSONL output at `logs\account_state_YYYY-MM-DD.jsonl`, margin-buffer WARNING, LOCKED-state CRITICAL logging, currency decomposition, and biggest single-symbol exposure.
- 2026-06-24: Created and ran `scripts\risk_gate_dry_run.py`; all 20 synthetic mocked cases produced expected outcomes.
- 2026-06-24: Verified L3/dry-run with `python -m compileall src scripts tests`, full `pytest tests -q` result `34 passed`, dry-run exit code `0`, standing static grep found `mt5.order_send` only in `src\trifolium\risk_gate\execution.py`, and tests contain no `MetaTrader5` imports.
- 2026-06-25: Applied Style B pivot: P0 Risk Gate live approval remains deferred, P1 Task 01 L2 calibration is deprecated, P2 reusable L5 validation is approved, and Task 05 self-improving loop is explicitly not built in this round.
- 2026-06-25: Implemented Task 03 bar-level multi-symbol fast path for bar-only strategies, including parquet row-group aggregation into 15-minute bars and cached bar replay for StrategyV0 validation.
- 2026-06-25: Refactored L5 into reusable callable `trifolium.validation.validate_strategy(...) -> ValidationResult` with machine-readable JSON plus markdown output.
- 2026-06-25: Optimized StrategyV0 validation runtime by vectorizing training-matrix construction and limiting current prediction features to the required recent lookback while preserving no-future daily recalibration semantics.
- 2026-06-25: Ran full StrategyV0 L5 validation over all tradable symbols; Filter 1/2/3 all passed and wrote `reports\validation_strategy_v0_20260625_105114\validation_report.md` plus `validation_result.json`.
- 2026-06-25: Generated 4-strategy comparison report `reports\strategy_v0_l5_comparison_20260625_110131.md` and machine-readable JSON.
- 2026-06-25: Added guarded L6 readiness harness `scripts\live_run_strategy_v0.py` and tests; the harness refuses to start live unless Risk Gate is production mode and principal passes `--live-approved`.
- 2026-06-25: Verified `python -m compileall src scripts tests`, full `pytest tests -q` result `40 passed`, standing static grep found `mt5.order_send` only in `src\trifolium\risk_gate\execution.py`, and tests contain no direct `MetaTrader5` imports.
- 2026-06-25: Read Task 05 self-improving loop spec fully and switched project goal/plan to Task 05 Plan A.
- 2026-06-25: Installed Task 05 API client dependencies `openai` and `anthropic`, then regenerated `requirements.txt`.
- 2026-06-25: Task 05 C1/C2 early API sanity passed: NVIDIA nano smoke call returned OK and Anthropic cheap smoke call returned OK; no secret values were printed.
- 2026-06-25: Built Task 05 C1-C9: NIM client, Anthropic client, Strategy Element Table, SQLite Strategy Memory, Scope Guard, Guardrails, Brain, Coder, and Loop Orchestrator.
- 2026-06-25: Added Task 05 scripts `scripts\run_loop_iteration.py`, `scripts\run_loop_continuous.py`, and `scripts\demo_ui.py`.
- 2026-06-25: Attempted NeMo Guardrails installation; install failed on Windows because `annoy` requires Microsoft C++ Build Tools, so Guardrails uses the specified Pydantic-only fallback.
- 2026-06-25: Added mandatory adversarial tests proving forbidden Risk Gate targets, forbidden rationale, and forbidden coder patches are skipped without memory writes.
- 2026-06-25: Verified `python -m compileall src scripts tests` and full `pytest tests -q`; result `61 passed`.
- 2026-06-25: Added `pytest.ini` so `python -m pytest tests -q` resolves the local `src` package without relying on a shell-specific `PYTHONPATH`.
- 2026-06-25: Ran end-to-end Task 05 iteration `scripts\run_loop_iteration.py --parent v0`; result completed with iteration `30021ae2`, new memory row `v_30021ae2`, sandbox patch under `sandboxes\v_30021ae2`, and 8-step JSONL log `logs\loop_iterations_30021ae2.jsonl`.
- 2026-06-25: Verified demo UI render includes Task 05 title and `v_30021ae2`; `scripts\demo_ui.py` can serve the page on localhost.
- 2026-06-25: Final static checks passed after clearing caches: `mt5.order_send` appears only in `src\trifolium\risk_gate\execution.py`, and test source files contain no `MetaTrader5` literal.
- 2026-06-25: NVIDIA dashboard browser check reached the unauthenticated sign-in page, so dashboard credits/cost were not visible; screenshot saved to `output\playwright\nvidia_settings_signin_20260625_1323.png`.
- 2026-06-25: Ran controlled NVIDIA experiments A-D and wrote results to `logs\nvidia_experiments_20260625_122352.json`; Ultra 550B timed out at both 60s and 300s, Super 120B returned HTTP 200 in 1.355s, and Nano 30B with the Brain prompt returned HTTP 200 in 3.222s.
- 2026-06-25: NVIDIA API `models.list()` showed Ultra 550B, Super 120B, and Nano 30B all present in the accessible model list; experiment responses did not include credit-consumption fields.
- 2026-06-25: Re-ran the scoped NVIDIA diagnostic with `Say hi` and the full actual Brain prompt; results saved to `logs\nvidia_diagnostic_20260625_123209.json`; Ultra timed out at 60s and 300s, Super returned HTTP 200 in 0.668s, and Nano returned HTTP 200 in 3.49s with 3174 total tokens.
- 2026-06-25: Made Task 05 Brain/NIM timeout config-driven: `config\self_improving.yaml` now sets `brain.timeout_seconds: 300`, `Brain` accepts timeout/retry/sampling settings, and `scripts\run_loop_iteration.py` injects them from config.
- 2026-06-25: Re-ran E2E loop iteration with Ultra 550B at 300s timeout; iteration `ef03fdaa` completed with candidate `v_ef03fdaa`, but Brain still used fallback after `APITimeoutError: Request timed out.`
- 2026-06-25: Because Ultra still timed out at 300s, re-ran A-D NVIDIA diagnostic and saved `logs\nvidia_diagnostic_20260625_131409.json`; Ultra timed out at 60s and 300s, Super returned HTTP 200 in 2.295s, and Nano returned HTTP 200 in 4.043s with 3399 total tokens.
- 2026-06-25: Verified timeout fix with `python -m compileall src scripts tests`, full `pytest tests -q` result `62 passed`, static check found `mt5.order_send` only in `src\trifolium\risk_gate\execution.py`, and test source files contain no `MetaTrader5` literal.

## In Progress
- 2026-06-25: L6 runtime readiness is intentionally blocked because `config\risk_limits.yaml` remains `mode: calibration`; production mode and any live StrategyV0 start require principal approval.

## Not Started
- 2026-06-22: Task 01 project code scaffold has not been created because Charter environment assumptions are not fully satisfied.
- 2026-06-22: Task 02 risk gate is not started because Task 01 has not reached L1.
- 2026-06-22: Task 03 backtest harness is not started; historical data path has not been provided or discovered.

## Known Issues
- 2026-06-22: Task 01 strict repo acceptance still needs an approved git commit if `.env.example committed` is interpreted literally.
- 2026-06-22: MT5 terminal reported `trade_allowed=False` during smoke test while `tradeapi_disabled=False`; verify before any future live L2 order.
- 2026-06-22: L2 calibration trade is blocked until `MT5_CALIBRATION_MODE=1` is explicitly set.
- 2026-06-22: `rg --files` failed with `Access is denied`; use PowerShell file enumeration as fallback unless `rg` access is fixed.
- 2026-06-24: Backtest data is missing competition crypto symbols BARUSD, BTCUSD, ETHUSD, SOLUSD, and XRPUSD.
- 2026-06-24: Backtest data includes extra non-competition symbols: AUDJPY, AUDNZD, EURJPY, NZDUSD, UKOILUSD, USDCNH, USDHKD, USOILUSD, XAUCNH, XAUGCNH, XAUHKD, XAUKUSD.
- 2026-06-24: Backtest data inventory uses bounded samples for P50/P95/P99 spread quantiles; exact all-row quantiles would require a heavier streaming quantile algorithm.
- 2026-06-24: Order book depth analysis in `reports/data_inventory.md` is sample-based, not a full-row proof of static depth.
- 2026-06-24: The unexplained P&L gap is explained by the still-open AUDUSD long; not by swap or a confirmed unknown Codex order.
- 2026-06-24: Previous `do_nothing` validation timeout was resolved with an exact no-op fast path; remaining baselines still need runtime validation.
- 2026-06-24: `buy_and_hold_audusd` validation completed but failed Filter 1 due projected risk discipline `90`, Filter 2 due distribution instability (`cv=3.4830073756586275`, negative fraction `0.5161290322580645`), and Filter 3 due robustness failures.
- 2026-06-24: Task 04 L5 full validation cannot be claimed yet; the current Task 03 generic event engine is too slow for 9-symbol StrategyV0 validation without a bar-level or multi-symbol streaming optimization.
- 2026-06-24: Task 04 L6 live deployment readiness remains blocked because Task 02 Risk Gate is not implemented and live deployment must not be run automatically.
- 2026-06-24: `/home/claude/codex_prompts/02_task_risk_gate.md` was not present in this Windows workspace; used the project Task Pool copy `D:\Desktop\Nucleus\Triofolium\Task Pool\02_task_risk_gate.md`.
- 2026-06-24: Existing Task 01 calibration order helpers now fail closed instead of sending directly; they must be reworked through Risk Gate during L2 integration before any future live calibration.
- 2026-06-24: L2 live sender exists but has only been exercised through monkeypatched tests; do not send live orders until L3 and dry-run are complete and principal explicitly approves.
- 2026-06-24: Risk Gate live sender remains principal-gated; no real MT5 order was sent during L3 or dry-run.
- 2026-06-25: StrategyV0 L5 passed as a flat/no-trade run (`trade_count=0`, final equity unchanged); this proves gate/engine cleanliness, not alpha.
- 2026-06-25: L6 harness exists and unit tests pass, but actual readiness acceptance cannot pass while Risk Gate mode remains `calibration` under the P0 deferral.
- 2026-06-25: Task 05 cannot proceed until the principal adds `NVIDIA_API_KEY` and `ANTHROPIC_API_KEY` to the environment or `.env`; values must not be printed.
- 2026-06-25: Final Task 05 iteration records a real NVIDIA NIM Ultra call attempt, but that call timed out and the loop used the safe fallback hypothesis; Anthropic was also called and then fell back to deterministic safe patch formatting.
- 2026-06-25: Controlled experiments indicate Ultra 550B is listed but not returning within 300s; recommended 14:00+ mitigation is to switch the Brain model to Super 120B rather than simply increasing Ultra timeout.
- 2026-06-25: Even after increasing Task 05 Brain timeout to 300s, Ultra 550B still timed out in both E2E and controlled diagnostics; keep Nano fallback active and do not assume Ultra availability for timed demos.
