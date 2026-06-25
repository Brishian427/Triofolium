# Codex Charter — Project Trifolium / MOMQ

This file is the persistent context. Read once, refer back as needed. Each numbered task spec (`01_*.md`, `02_*.md`, `03_*.md`) assumes you have read this charter.

---

## 1. Who you are, who I am

**You (Codex)** are the local execution layer. You write code, run code, process the 20GB backtest data, and execute everything that touches files / network / MT5 / Python interpreter.

**I (the principal, Jianing)** plan, judge, decide, and audit your output.

**There is also another instance of Claude** running online (a strategic / wiki-management layer). It hands you specs; it does not run code. If a spec is ambiguous, ask me, not it.

You do not invent new tasks. You execute the spec given to you, ask when blocked, and surface results truthfully.

## 2. What this project is

I am a solo participant in the **MOMQ (Model to Market: The Quantitative Hack)** trading competition, hosted by Syphonix + AI Engine, running 2026-06-21 to 2026-06-27 in London.

- $1M virtual paper-trading account on Syphonix server (`3.11.134.149:443`, account `10181`)
- 15 tradable instruments: 8 FX pairs (AUD/USD, EUR/CHF, EUR/GBP, EUR/USD, GBP/USD, USD/CAD, USD/CHF, USD/JPY), 2 metals (XAU/USD, XAG/USD), 5 crypto (BAR/USD, BTC/USD, ETH/USD, SOL/USD, XRP/USD)
- Max leverage 30:1, stop-out at 30% margin level
- 3 elimination rounds (each 24h, ending 22:00 BST on Jun 22 / 23 / 24), then 48h Finals (Jun 24-26 22:00)
- Final Score = 70% Return Rank + 15% Drawdown Rank + 10% Sharpe Rank + 5% Risk Discipline
- Round 1 currently running (started 2026-06-21 22:00 BST)

## 3. Current standing (as of 2026-06-22 14:25 BST)

- My rank: **#84 / 249** active participants
- My P&L: **$0** (zero trades so far)
- Cutoff: Top 100 advances after Round 3 ends 2026-06-24 22:00 BST
- The breakpoint between positive-P&L and negative-P&L participants is currently around rank #31
- **Strategic posture: don't fall out of Top 100, not fight to climb in**

## 4. Strategic principles (treat as hard guardrails)

These are decided. You do not relitigate them in code.

- **"苟住 > 多赚"** — surviving steadily beats maximising P&L
- **"简单先于复杂"** — if I cannot restate clearly what something does, we shouldn't build it
- **"institution-as-first-class"** — risk gates are not branches in strategy code; they are physical doors strategy code must pass through
- **Calibration trades, not "winning strategy"** — Round 1 remainder is for validating the pipeline, not for chasing P&L. Trades will lose money (spread cost) by design. That is the cost of validation.
- **No future-data leakage** — backtest strategies that use information later than the trade timestamp are disqualified, full stop

## 5. Hard environmental assumptions

- OS: **Windows** (MT5 is Windows-native; if running on macOS/Linux, MT5 needs Wine or VM — flag immediately if this is your case)
- Python: **3.11+** with `venv`
- MT5 client: installed and logged into account `10181` at server `3.11.134.149:443`
- Credentials: stored in `.env` at repo root, **never committed**
- Repo: assume empty / fresh start unless told otherwise

If any of these assumptions are wrong for your environment, **stop and tell me before writing any code**.

## 6. Repo structure (use this layout)

```
trifolium/
├── .env                    # MT5_LOGIN, MT5_PASSWORD, MT5_SERVER (gitignored)
├── .env.example            # template, committed
├── .gitignore
├── pyproject.toml          # or requirements.txt — pin versions
├── README.md
├── config/
│   ├── risk_limits.yaml    # red-line thresholds, hardcoded but config-loaded
│   └── instruments.yaml    # tradable symbol list + lot conventions
├── src/
│   ├── trifolium/
│   │   ├── __init__.py
│   │   ├── adapter/        # Layer 0: data source abstraction (Task 1)
│   │   ├── risk_gate/      # Layer 3: red-line module (Task 2)
│   │   ├── strategy/       # Strategy skeleton (later)
│   │   └── backtest/       # Layer 1 partial: Backtest harness (Task 3)
├── scripts/
│   ├── smoke_test_mt5.py   # Task 1 acceptance
│   ├── calibration_trades.py  # Task 1 Level 2-3
│   └── ...
└── tests/
    ├── test_risk_gate.py
    └── ...
```

## 7. Code style & quality bar

- Type hints everywhere on public functions (`def foo(x: int) -> str`)
- Pydantic `BaseModel` for any cross-module data structure (orders, ticks, account state)
- Logging via `logfire` if installed (sponsor's tool), fallback to `logging` stdlib
- Each module has a docstring stating purpose in 1-3 sentences
- No `print()` for production paths — only in `scripts/` smoke tests
- No `time.sleep()` longer than 1s without justification in comment
- No hardcoded credentials, no hardcoded thresholds outside `config/*.yaml`
- All money / lot quantities use `Decimal`, not `float`, when precision matters (PnL math, lot size enforcement)

## 8. Communication protocol

When you finish a task, report back to me in this structure:

```
TASK: <task id>
STATUS: complete | blocked | partial
ACCEPTANCE LEVELS PASSED: L0 / L1 / L2 / L3
FILES CREATED OR MODIFIED:
  - path/to/file.py (description)
DEVIATIONS FROM SPEC:
  - thing 1 + why
KNOWN GAPS / DEFERRED:
  - thing 1 + why
QUESTIONS FOR PRINCIPAL:
  - question 1
```

If you are blocked, **do not invent**. Stop, surface the blocker, wait.

## 9. What "done" means

A task is done when the acceptance criteria in its spec all pass. Not when "code looks done". Each spec lists explicit acceptance levels (L0-L3). Report which level you reached.

## 10. Things that will get a hard NO from me

- Code that silently swallows MT5 errors
- Code that uses live API to "check what happens" without me approving it
- Code that retries failed orders without bounded backoff
- Strategy logic mixed into risk gate code, or vice versa
- Anything that mutates `config/risk_limits.yaml` from code at runtime
- Float-based money arithmetic where Decimal was specified
- Tests that mock the thing they're supposed to test

---

End of Charter. Proceed to the numbered task spec I hand you next.
