# Task 02 — Risk Gate (Red-Line Module + Mandatory External Check)

**Prerequisite**: You have read `00_charter.md` AND Task 01 has reached L1 at minimum.

## Goal in one sentence

Build an independent Python module that all order requests must pass through before reaching MT5; any inconsistency between what the strategy says it wants and what would actually be sent gets the order **rejected, logged, and never executed**.

## Why this matters

This module is the only thing standing between a buggy strategy / hallucinating LLM agent / float precision error and **a catastrophic order that wipes the account in seconds**. It is the "physical door" — strategy code must walk through it, cannot go around it.

The principal said it plainly: "防止模型失控" (prevent model from going rogue).

## Acceptance criteria

### L0 — Module exists & is structurally isolated

Pass criteria:
- [ ] New package `src/trifolium/risk_gate/` exists with `__init__.py`
- [ ] Public entrypoint: a single function `submit_order(request: OrderRequest) -> OrderResult`
- [ ] `OrderRequest` and `OrderResult` defined as Pydantic `BaseModel`s in `src/trifolium/risk_gate/types.py`
- [ ] **No strategy code anywhere references `mt5.order_send` directly** — repo-wide grep should find `mt5.order_send` ONLY inside `src/trifolium/risk_gate/`
- [ ] All thresholds loaded from `config/risk_limits.yaml` at module init, NOT hardcoded in Python files
- [ ] `risk_limits.yaml` is committed; values are version-controlled
- [ ] Module init validates the config file has all required keys; raises if not

`config/risk_limits.yaml` initial contents:

```yaml
# Calibration mode (Round 1 remainder) - looser, lets calibration trades through
# Production mode (Round 2+) - tight defaults below
mode: calibration  # values: calibration | production

calibration:
  max_lot_per_order: 0.05         # AUDUSD-equivalent. Calibration trades are 0.01.
  max_total_leverage: 2.0         # Very low, calibration shouldn't accumulate exposure
  max_single_symbol_pct: 100      # Calibration uses one symbol at a time
  numeric_tolerance_abs: 0.000001
  numeric_tolerance_rel: 0.0001
  max_orders_per_minute: 3        # Calibration is slow & deliberate

production:
  max_lot_per_order: 0.1          # XAUUSD-equivalent (~$42k notional at current gold price)
  max_total_leverage: 5.0         # Margin level stays comfortably above stop-out
  max_single_symbol_pct: 40       # Diversification floor
  numeric_tolerance_abs: 0.000001
  numeric_tolerance_rel: 0.0001
  max_orders_per_minute: 5

# Symbol-specific lot caps (when a symbol's notional varies wildly from base assumption)
symbol_overrides:
  XAUUSD:
    max_lot_per_order: 0.05       # 1 lot = 100 oz ≈ $420k. 0.05 = $21k notional.
  BTCUSD:
    max_lot_per_order: 0.05       # TBD, verify lot convention in Task 01

# Hard floors (never breached regardless of mode)
hard_floors:
  min_margin_level_pct: 200       # Stop placing new orders below this
  max_drawdown_session_pct: 5     # If session drawdown breaches this, lock the gate
```

### L1 — Required checks (each with unit test)

For each check below, implement a function in `src/trifolium/risk_gate/checks/<name>.py` AND a unit test in `tests/test_risk_gate/test_<name>.py`. Each check returns `(passed: bool, reason: str | None)`.

1. **`check_lot_size`** — request lots ≤ `max_lot_per_order` (with symbol_overrides applied). Test: 0.01 passes, 0.5 fails.
2. **`check_total_leverage`** — projected gross notional after this order ≤ `max_total_leverage × equity`. Test: from zero exposure, 0.05 lot XAUUSD passes; from existing 4x leverage, additional 0.5 lot XAUUSD fails.
3. **`check_single_symbol_concentration`** — after this order, exposure in this symbol / total exposure ≤ `max_single_symbol_pct`. Test: first order passes, adding to make 80% concentration fails (in production mode).
4. **`check_numeric_consistency`** — recompute the order's notional from `(lots, contract_size, price)` independently; compare to what the strategy claimed. Fail if abs error > `numeric_tolerance_abs` AND rel error > `numeric_tolerance_rel`. Test: a fabricated mismatch (strategy says $1000, recompute says $10000) fails.
5. **`check_rate_limit`** — track last-N order timestamps in module-level state; if more than `max_orders_per_minute` orders in past 60s, fail. Test: 5 in a row pass, 6th fails (in production mode).
6. **`check_direction_sanity`** — soft check: if this order would significantly add to existing same-direction exposure in same symbol (e.g. already long 0.05 lot, ordering another 0.05 buy), emit a **warning** (not fail), log it. Test: confirms the log line exists.
7. **`check_account_health`** — query MT5 for current margin_level; if margin_level < `min_margin_level_pct`, fail. Test: mock account_info with low margin level, confirm reject.
8. **`check_hard_floor_drawdown`** — track session peak equity; if current equity / peak < (1 - `max_drawdown_session_pct/100`), the gate enters LOCKED state, reject all new orders until manually unlocked. Test: simulate equity drop, confirm subsequent orders rejected.

Each check is **independent**, **stateless where possible**, **stateful only where required** (rate limit, hard floor — these need module-level state).

### L2 — Integration

Pass criteria:
- [ ] `submit_order` runs all checks in order; if any check fails, returns `OrderResult(status="rejected", reason=<check name + detail>)` and does NOT call `mt5.order_send`
- [ ] If all checks pass, calls into Task 01's order layer (`src/trifolium/adapter/orders.py`), returns `OrderResult` based on MT5 response
- [ ] Every order request (passed OR rejected) is logged to `logs/risk_gate_YYYY-MM-DD.jsonl` with: timestamp, request, all check results, final status, MT5 response if applicable
- [ ] A repo-wide test confirms there is no path from `src/trifolium/strategy/` (when it exists) to `mt5.order_send` that bypasses `risk_gate.submit_order`. Implement this as a static check (grep / AST walk) in `tests/test_isolation.py`

### L3 — Observability

Pass criteria:
- [ ] A background task (or scheduled function — your design) logs current account state once per minute regardless of order activity: margin_level, equity, leverage, open positions count, biggest single-symbol exposure
- [ ] These are written to `logs/account_state_YYYY-MM-DD.jsonl` for post-hoc analysis
- [ ] If `min_margin_level_pct` is approached (within 20% of breach), emit a WARNING log
- [ ] If gate enters LOCKED state, emit a CRITICAL log with full state dump

## Test mode (run before any real order goes through)

Before integrating with the live MT5 adapter, create `scripts/risk_gate_dry_run.py` that:

- [ ] Feeds 20 synthetic order requests through `submit_order` with a MOCKED MT5 adapter (no real network calls)
- [ ] Covers: legitimate calibration trade (pass), oversized lot (fail check_lot_size), bypass attempt (fail check_total_leverage), float drift (fail check_numeric_consistency), rapid-fire (fail check_rate_limit), account-depleted state (fail check_account_health)
- [ ] Prints a summary: N passed, N rejected, breakdown by failing check
- [ ] Exits 0 if all 20 cases produced the expected outcome (defined in the script), 1 otherwise

This dry-run script is the **gate** to going live. **Do not wire Task 01's real adapter into `submit_order` until dry-run is green.**

## Files you should create

```
src/trifolium/risk_gate/
├── __init__.py                 # exports submit_order
├── types.py                    # OrderRequest, OrderResult, GateState
├── config.py                   # load risk_limits.yaml
├── gate.py                     # submit_order, orchestration
├── state.py                    # LOCKED state, peak equity, rate limit buffer
└── checks/
    ├── __init__.py
    ├── lot_size.py
    ├── total_leverage.py
    ├── single_symbol_concentration.py
    ├── numeric_consistency.py
    ├── rate_limit.py
    ├── direction_sanity.py
    ├── account_health.py
    └── hard_floor_drawdown.py

config/risk_limits.yaml

tests/test_risk_gate/
├── conftest.py                 # fixtures (mock MT5 account, mock equity series)
├── test_lot_size.py
├── test_total_leverage.py
├── test_single_symbol_concentration.py
├── test_numeric_consistency.py
├── test_rate_limit.py
├── test_direction_sanity.py
├── test_account_health.py
├── test_hard_floor_drawdown.py
└── test_isolation.py           # repo-wide grep test for no-bypass

scripts/risk_gate_dry_run.py
```

## Files you should NOT create

- No strategy code
- No backtest code
- No "AI agent" code
- No new fields in `risk_limits.yaml` beyond what's specified — if you think one is needed, ask first

## Design rules — non-negotiable

1. **Stateless by default.** Each check is a pure function of (request, account_state, config). State is concentrated in two places only: `state.py` (rate limit ring buffer, LOCKED flag, session peak equity).
2. **Fail closed.** If a check raises an exception (not returns False — actually raises), `submit_order` rejects the order with reason `"check_error: <name>: <exception>"`. Never let an exception in a check accidentally let an order through.
3. **Order of checks matters.** Cheap & local first (lot_size, numeric_consistency), expensive & I/O last (account_health). Document the rationale in `gate.py`.
4. **No silent precision loss.** All money math in `Decimal`. If you receive a `float` from MT5, convert to Decimal at the boundary with explicit precision.
5. **No hidden bypass.** No `bypass_for_testing=True` flag. No "calibration mode skips checks" — calibration mode uses *looser config*, not *fewer checks*.

## Reporting

When done, report per Charter §8 + provide:
- A sample of 5 rejected-order log lines (showing the reason chain)
- The output of `scripts/risk_gate_dry_run.py` (pass/fail summary)
- Diff stats: lines of code, test coverage of `src/trifolium/risk_gate/`

When L0–L3 are all green AND dry-run passes, I will release Task 03 (Backtest).

## Hard NO

- No global mutable state outside `risk_gate/state.py`
- No exception swallowing — every `except` clause must either re-raise, return a structured failure, or log and continue with explicit comment
- No "config validation can be done later"; init must validate
- No tests that import `MetaTrader5` (tests run on a CI box with no MT5 installed)
- No "I added an extra check that seemed useful"; the spec defines all checks
