# Task 03 — Backtest Harness (20GB Data + 苟着 Baseline)

**Prerequisite**: You have read `00_charter.md`. Task 01 and Task 02 should be at L1+ but full completion isn't required for Task 03 to start in parallel.

## Goal in one sentence

Build a backtest framework that can ingest the 20GB historical data, simulate any candidate strategy in a way that mirrors the competition's three-round structure, and produce **trust-worthy Final-Score estimates** for that strategy.

## Why this matters

The principle is "苟住 > 多赚": don't go live with a strategy until backtest has answered:

1. Does it blow up? (binary)
2. Is its behaviour stable across regimes / sub-windows? (structural)
3. Is it robust to parameter / data perturbation? (robustness)

Without this, we are gambling on Round 2 onwards. With this, we are deploying a vetted strategy with known properties.

## Acceptance criteria

### L0 — Data inventory

Pass criteria — `scripts/inventory_backtest_data.py` runs and produces `reports/data_inventory.md` containing:

- [ ] Total file count, total size, top-level directory structure (3 levels deep)
- [ ] For each symbol found: time range covered (earliest, latest, gaps), record count, file format, schema (column names + dtypes), sample of 5 rows
- [ ] Cross-check against competition's 15 instruments list (`config/instruments.yaml`):
  - Which of the 15 are present?
  - Which are missing?
  - Which symbols are present but NOT in the competition's 15? (e.g. AUDJPY was mentioned by Discord users)
- [ ] **BARUSD identification**: if BARUSD is in the data, plot last 30 days price series. From the shape, propose what underlying asset it likely is. If not in the data, flag this.
- [ ] Spread distribution per symbol per hour-of-day (UTC): mean, p50, p95, p99. Output as table + heatmap PNG.
- [ ] Order book depth analysis: confirm or refute the Discord observation that L2 depth is static in backtest data (5 levels at 100K/1M/2M/3M/5M, unchanging). If static, note this; if dynamic, characterise.

This level requires NO strategy code, NO live MT5. Pure data exploration. **Do it first** — it answers questions the other levels depend on.

### L1 — Backtest harness skeleton

Pass criteria:

- [ ] `src/trifolium/backtest/` package with:
  - `engine.py` — main backtest loop
  - `data_loader.py` — streaming access to 20GB (NEVER load all into memory)
  - `executor.py` — simulates order fills, applies spread cost realistically
  - `equity_tracker.py` — tracks Equity, P&L, MaxDD, computes 15-min Sharpe per Syphonix formula
  - `metrics.py` — Final Score computation (70/15/10/5 weighted)
- [ ] A `Strategy` Pydantic base class in `src/trifolium/strategy/base.py` with the interface:
  ```python
  class Strategy(BaseModel):
      name: str
      symbols: list[str]
      
      def on_tick(self, tick: Tick, state: BacktestState) -> list[OrderRequest]:
          """Called on each tick. Returns orders to submit (possibly empty)."""
          ...
      
      def on_bar_close(self, bar: Bar, state: BacktestState) -> list[OrderRequest]:
          """Called on each bar close. Same return contract."""
          ...
  ```
- [ ] A trivial baseline strategy `src/trifolium/strategy/baselines/do_nothing.py`:
  - Issues no orders, ever
  - Used to verify the backtest engine: running this on 24h of XAUUSD data should produce a flat equity curve at $1M, MaxDD = 0, Sharpe = NaN/0, Return = 0
- [ ] Backtest output: `reports/backtest_<strategy>_<timestamp>/`:
  - `equity_curve.png`
  - `trades.csv` (every trade, with entry/exit/PnL/duration)
  - `metrics.json` (Final Score breakdown: Return / MaxDD / Sharpe / would-be Risk Discipline)
  - `summary.md`

### L2 — Three filters (the gate to going live)

Implement `scripts/strategy_filters.py` that takes a strategy module name + parameters and runs THREE filters in sequence. Strategy must pass all three to be cleared for live deployment.

**Filter 1: No blow-up (binary)**
- Run the strategy on the full historical data (or a meaningful subset — at least 30 days)
- At any point during backtest: did margin_level fall below 30%? Did Risk Discipline trigger (leverage >28x for 25+ min, etc.)?
- Output: PASS / FAIL + list of incidents

**Filter 2: Distribution stability (structural)**
- Split the backtest period into non-overlapping 24-hour sub-windows
- Compute Return / MaxDD / Sharpe for each sub-window
- Pass criteria: `std(returns) / mean(returns) < THRESHOLD` (you'll calibrate this threshold against the do-nothing baseline + a few naive baselines; principal will approve the threshold value before promoting Filter 2 to production)
- Worst sub-window's MaxDD must be < 5% (parameter, configurable)
- Output: PASS / FAIL + per-window table + visualisation of returns distribution

**Filter 3: Robustness to noise (robustness)**
- Perturb the strategy in 3 ways: ±20% on key thresholds, ±30% on lot sizing, start-time shifted by ±6 hours
- For each perturbation, re-run Filter 1 + Filter 2
- Pass criteria: all 3 perturbations still pass Filter 1, AND at least 2 of 3 still pass Filter 2
- Output: PASS / FAIL + which perturbations broke which filter

A strategy that passes all three filters is eligible for live deployment. **Below this bar, do not deploy.**

### L3 — Round-structure simulation

Pass criteria — `scripts/round_simulation.py`:

- [ ] Slices the backtest data into rounds matching the competition: each round 24h, with the 22:00-23:00 hour as a "audit window" (no trading)
- [ ] At each audit window, allows the strategy to RE-CALIBRATE its parameters using data ONLY up to that point (no future leakage)
- [ ] Runs at least 3 consecutive rounds + a 48h "finals" segment
- [ ] Reports Final Score for each round AND for the entire sequence
- [ ] Allows comparison: same strategy with vs without recalibration, to see if the "AI engineer wakes up between rounds" pattern actually helps

This level simulates the competition's structure faithfully. Strategies that look great on un-segmented backtest but fail in round-simulation are the dangerous ones — this level catches them.

## Baseline strategies (for calibration of filter thresholds)

Implement these three SIMPLE baselines in `src/trifolium/strategy/baselines/`. Their purpose is to give us reference numbers for what Final Score looks like for trivial strategies; they are NOT for deployment.

1. **`do_nothing.py`** — Already specified above. Reference floor for "what if we don't trade".
2. **`random_walk.py`** — Every hour, with 50% probability open a 0.01 lot position in a random symbol, with 50% probability close any open position. Random seed configurable for reproducibility. Reference for "pure noise" returns.
3. **`buy_and_hold_diversified.py`** — At t=0, open 0.01 lot long in 4 lowest-spread instruments (per Task 02 instrument config). Never trade again. Reference for "passive market exposure".

Running these on the same time range should give us three reference Final Scores. The numbers from these set our intuition for what "good", "bad", and "noise" look like.

## Files you should create

```
src/trifolium/backtest/
├── __init__.py
├── engine.py
├── data_loader.py
├── executor.py
├── equity_tracker.py
└── metrics.py

src/trifolium/strategy/
├── __init__.py
├── base.py
└── baselines/
    ├── __init__.py
    ├── do_nothing.py
    ├── random_walk.py
    └── buy_and_hold_diversified.py

scripts/
├── inventory_backtest_data.py
├── strategy_filters.py
└── round_simulation.py

tests/test_backtest/
├── test_executor.py            # spread cost applied correctly
├── test_equity_tracker.py      # Sharpe formula matches Syphonix spec
└── test_metrics.py             # Final Score weighting correct

reports/
└── (gitignored; outputs go here)
```

## Files you should NOT create

- No live MT5 integration in `backtest/` — backtest is offline only
- No actual strategy beyond the three baselines (real strategy comes later, after we see baseline numbers)
- No fancy ML models — that's a later phase

## Critical correctness rules

1. **No future-data leakage.** Period. At any timestamp `t`, the strategy can see only data with timestamp `< t`. Implement an explicit assertion in `engine.py` that bars/ticks are streamed monotonically and the strategy callback never receives a tick with timestamp ≥ current_simulated_time.

2. **Spread cost is non-negotiable.** Every market buy executes at `ask`, every market sell at `bid`. Use historical spread data, not a constant. If a tick has bid > ask (data corruption), skip that tick and log.

3. **Sharpe formula must match Syphonix exactly.** From rules §12.5:
   ```
   r_t = (equity_t - equity_{t-1}) / equity_{t-1}
   Sharpe = mean(r_t) / std(r_t)
   ```
   15-minute intervals, NON-annualised. If fewer than 8 intervals, Sharpe Rank capped at 50.

4. **MaxDD measured against running peak**, not against starting equity.

5. **Data loader streams.** A loader that does `pd.read_parquet(everything)` is wrong. Use chunked reading, lazy iterators, generators.

## Reporting

When done with each level, report per Charter §8 + provide:
- L0: the `data_inventory.md` summary
- L1: do-nothing baseline backtest output (should be all zeros / NaN, confirming the engine works)
- L2: filter run on all 3 baselines, with threshold proposals for principal review
- L3: round simulation output on baselines

## Hard NO

- No loading 20GB into memory
- No "I'll just fit the threshold to look good"
- No future-data leakage (instant disqualification of the strategy and the harness)
- No live MT5 calls from anywhere in `backtest/`
- No silent failures — every backtest run produces output even on strategy crash (with crash log)
- No "look ahead bias" — `on_tick(tick, state)` can only see what was available at that tick's timestamp
