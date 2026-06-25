# Task 01 — MT5 + Python Pipeline (Connectivity & Order Execution)

**Prerequisite**: You have read `00_charter.md`.

## Goal in one sentence

Get a Python process to issue a real order to the Syphonix competition server through MT5, and confirm the order executed correctly, end-to-end.

## Why this matters

Until this task is done, no other Trifolium work can land. Backtest, strategy logic, risk gate — they all assume this pipeline exists. **Today this task blocks every other task.**

## Acceptance criteria

Report which level you reached. Stop at any level that fails; do not paper over a failure to claim a higher level.

### L0 — Connectivity

Pass criteria:
- [ ] MT5 client installed locally, opens, can log in to account `10181` at server `3.11.134.149:443` via GUI
- [ ] `pip install MetaTrader5` succeeds in the project's venv
- [ ] Running `python -c "import MetaTrader5 as mt5; print(mt5.initialize())"` prints `True`
- [ ] Credentials loaded from `.env` (using `python-dotenv` or `pydantic-settings`), not hardcoded
- [ ] `.env.example` committed with placeholder values; `.env` in `.gitignore`

Deliverable: `scripts/smoke_test_mt5.py` that exits 0 on success, prints account login + terminal info.

### L1 — Read

Pass criteria — `scripts/smoke_test_mt5.py` extends to:
- [ ] Print account info: login, balance, equity, margin, free margin, leverage, currency
- [ ] Print current tick for XAUUSD: bid, ask, spread (in price units AND in pips), time
- [ ] Print last 10 M1 candles for XAUUSD (OHLCV)
- [ ] Print available symbols count and verify all 15 competition symbols are accessible (loop over the list in `config/instruments.yaml`)
- [ ] If any symbol is missing from MT5's symbol list, raise and report which

For each printed value, also assert sanity bounds (e.g. balance > 0, ask > bid, spread > 0).

### L2 — Order (calibration)

**Mode: this runs against the real competition account. Treat it accordingly.**

Build `scripts/calibration_trade.py`. It must:

- [ ] Take CLI args: `--symbol AUDUSD --lots 0.01 --mode ping_pong`
- [ ] Refuse to run unless `MT5_CALIBRATION_MODE=1` env var is set (a deliberate "yes I mean this" gate)
- [ ] Refuse to run unless symbol's spread is < 5 pips (sanity check — don't trade EUR/CHF accidentally)
- [ ] Send one market buy at 0.01 lots
- [ ] Wait for fill confirmation (poll positions, max 5s timeout)
- [ ] Immediately send a closing market sell of the same position
- [ ] Print: open price, close price, P&L in account currency, time-to-fill, slippage vs the bid/ask at request time
- [ ] Log the full order request + response objects (use logfire if installed, else stdlib logging at DEBUG, written to `logs/calibration_YYYY-MM-DD.jsonl`)
- [ ] Exit code: 0 on full success, 1 on any error

The point is to lose a small known amount (~$0.20 per round-trip) and learn exact behaviour.

**Do NOT run this in a loop without me. One trade per invocation, principal-supervised.**

### L3 — Error handling

Add to `smoke_test_mt5.py` (or a new `scripts/error_handling_test.py`):

- [ ] Simulate network disconnect: kill MT5 client, run smoke test, confirm clean error (not silent hang)
- [ ] Simulate bad order: try a market order for 1000 lots XAUUSD on the test account, confirm:
  - The order request fails (rejected by margin / leverage)
  - The Python code catches the failure cleanly
  - No partial state is left (no orphan orders / pending positions)
  - The failure mode + return code from MT5 is logged
- [ ] Implement a retry policy somewhere reusable: max 3 retries, exponential backoff (1s, 2s, 4s), only on transient errors (network, timeout), NOT on logical errors (insufficient margin, invalid symbol)

## Files you should create

```
src/trifolium/adapter/__init__.py
src/trifolium/adapter/mt5_client.py      # connection wrapper
src/trifolium/adapter/account.py         # account state queries
src/trifolium/adapter/market_data.py     # tick + candle queries
src/trifolium/adapter/orders.py          # order send + status polling
config/instruments.yaml                  # 15 symbols + lot conventions
scripts/smoke_test_mt5.py
scripts/calibration_trade.py
.env.example
.gitignore
pyproject.toml
README.md                                # how to setup + run smoke tests
```

## Files you should NOT create

- No strategy code yet (`src/trifolium/strategy/` should be empty / not exist)
- No risk gate code (Task 2's job)
- No backtest code (Task 3's job)
- No "AI agent" code

If you find yourself writing strategy logic to test the pipeline, **stop** — use the simplest possible deterministic order (market buy at 0.01 lots, immediate close).

## Reference: MT5 Python library

Use the official `MetaTrader5` library. Key calls:

```python
mt5.initialize(login=..., password=..., server=...)
mt5.account_info()
mt5.symbol_info(symbol)
mt5.symbol_info_tick(symbol)
mt5.copy_rates_from_pos(symbol, timeframe, start, count)
mt5.order_send(request)
mt5.positions_get()
mt5.shutdown()
```

Documentation: https://www.mql5.com/en/docs/python_metatrader5

## Lot conventions (verify on L1)

Per Syphonix competition rules:
- XAUUSD: 1 lot = 100 oz
- FX pairs: 1 lot = 100,000 base currency (industry standard, verify)
- Crypto: TBD, varies per symbol — verify and put in `instruments.yaml`

If MT5 reports lot size differs from above, **report the discrepancy and stop**, do not proceed to L2.

## Reporting

When done with each level, report per Charter §8.

When L0–L3 are all green, I will release Task 02 (Risk Gate).

If L2 cannot be reached because the principal hasn't authorised live trades yet — that's fine. L0 + L1 + L3 (dry-run with mock orders) is acceptable to unblock Task 02.

## Hard NO

- Do not trade more than 0.01 lots in any calibration script
- Do not run calibration in a loop
- Do not commit `.env` to git (verify `.gitignore` covers it before any `git add`)
- Do not modify any file under `config/` from runtime code
- Do not start writing Task 02 work "while you're at it"
