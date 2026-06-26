# 2026-06-26 Trading Incident Report

## Executive Summary

2026-06-26 was a live-trading failure driven primarily by manual intervention under time pressure, not by an automated-system malfunction.

The key failure mode was not prediction quality alone. It was the interaction of:

- competition deadline pressure,
- manual recovery trading after losses,
- increasing exposure in metals,
- disabling automated hard-kill protection for manual positions,
- repeated high-emotion decisions after the system had already separated manual and automated trades.

The automated profit harvester did not secretly close manual positions. MT5 history marks the large manual trades as `magic=0`, `comment=""`, `reason=0`. Harvester trades are distinguishable as `magic=10181`, `comment="profit_harvester"`.

## Final Observed Account State

Snapshot time: approximately 2026-06-26 21:02 UTC.

| Field | Value |
|---|---:|
| Balance | 998,491.78 |
| Equity | 985,764.88 |
| Floating PnL | -12,726.90 |
| Margin | 87,719.59 |
| Free margin | 898,045.29 |
| Margin level | 1123.77% |

Open positions at snapshot:

| Symbol | Side | Volume | Open price | Current price | Floating PnL | Owner |
|---|---|---:|---:|---:|---:|---|
| XAGUSD | Sell | 2.0 | 58.5988 | 59.6000 | -10,012.00 | Manual |
| XAUUSD | Buy | 5.0 | 4091.1998 | 4085.7700 | -2,714.90 | Manual |

Both open positions had `comment=""` and `magic=0`, meaning they were manual / non-harvester positions.

## System Attribution

### Harvester Behavior

The live profit harvester was active and writing heartbeat logs. It was modified to protect manual trades:

- `hard_kills_disabled_for_manual_trade_protection` was repeatedly logged.
- manual positions were skipped as unmanaged positions.
- no harvester hard-kill closed manual positions.
- no rejected / halted / hard-kill event was observed in the harvester log after the override.

Recent harvester activity:

| Event | Symbol | Result |
|---|---|---|
| Entry | GBPUSD | Filled |
| Take profit | GBPUSD | Filled, +5.00 |
| Entry | GBPUSD | Filled |
| Take profit | GBPUSD | Filled, +5.00 |

The harvester remained mechanically functional, but its small positive expectancy could not offset manual metals exposure.

### Realized PnL by System Marker

Window analyzed: approximately 2026-06-26 09:02 UTC to 21:02 UTC.

| Marker | Realized PnL |
|---|---:|
| `magic=0` manual/client-side | -419.96 |
| `magic=10181` automated | +147.46 |

By comment:

| Comment | Realized PnL |
|---|---:|
| `profit_harvester` | +413.05 |
| `harv_reconcile` | -62.95 |
| `strategy_v0_emer` | -202.64 |
| blank/manual | -419.96 |

The largest damage at the final snapshot was not realized closed-trade loss in the analyzed window, but open floating loss on manual XAGUSD and XAUUSD positions.

## Timeline Narrative

### Phase 1: Automated System Working

The profit harvester demonstrated that it could:

- open through Risk Gate,
- close at the configured profit threshold,
- persist state,
- distinguish harvester positions from manual positions,
- avoid touching manual positions after the protection change.

This is a valid engineering success.

### Phase 2: Manual-Trade Protection Override

After manual positions were near or beyond prior hard-kill thresholds, the system was modified so the harvester would not apply hard-kills to manual trades.

This achieved the requested behavior:

- manual positions were not flattened by the bot,
- manual positions were not auto-harvested at +5,
- manual positions were logged and skipped.

However, this also removed the last automatic barrier against escalating manual loss.

### Phase 3: Recovery Trading Spiral

After earlier losses, manual trading became the dominant source of exposure.

Observed pattern:

- direction was changed repeatedly,
- metals position sizes increased,
- losses were allowed to run,
- attempts to recover concentrated around XAGUSD / XAUUSD,
- the account moved from manageable drawdown into a large open floating loss.

This was a principal-risk event, not a strategy-risk event.

## Root Cause

Primary root cause:

Manual recovery trading under emotional and deadline pressure.

Contributing causes:

- No manual-trade lockout after large loss.
- No cool-down period after accidental or regretted manual close.
- No maximum manual exposure cap independent of automated strategy.
- Hard-kill rules were disabled for manual positions without a replacement guardrail.
- Competition-end pressure encouraged "one more attempt" behavior.
- The system was built to protect strategy execution, not to protect the principal from manual escalation.

## What Went Right

- The audit trail was strong enough to identify ownership of trades.
- `magic` and `comment` separation worked.
- Harvester/manual position distinction worked.
- The system did not secretly close manual trades.
- Risk Gate still guarded automated order submission.
- The final facts were recoverable from MT5 history and JSONL logs.

## What Went Wrong

- Manual trades were allowed to bypass the same institutional discipline imposed on automated trades.
- The bot was prevented from intervening, but no alternative manual-risk circuit breaker was installed.
- The emotional state of the principal became an unmodeled system input.
- Position sizing escalated in the most volatile instruments.
- The last hour was treated as a recovery window instead of a shutdown window.

## Lessons

1. Principal risk is system risk.

   The system must model the human operator as part of the trading system. A live trading architecture that only constrains strategy code is incomplete.

2. Manual trades need their own risk policy.

   "Do not touch manual trades" is not enough. Manual trades need separate limits, lockouts, and cool-downs.

3. Recovery mode must be forbidden.

   After a defined loss threshold, the system should stop accepting manual escalation. This is not about being right or wrong on market direction; it is about preventing nonlinear damage.

4. Small automated edge cannot rescue oversized manual exposure.

   A +5 harvester loop is useful only when exposure is bounded. It cannot offset thousands of dollars of floating loss from large metals positions.

5. Auditability matters.

   Because comments and magic numbers were logged, we could distinguish bot behavior from manual behavior. This prevented false blame and clarified the real failure mode.

## Recommended Policy Changes

### P0: Manual Trade Lockout

Implement a principal-risk lock:

- If floating PnL falls below a threshold, block new manual-inspired automation.
- If manual loss exceeds a threshold, require a cool-down period before any new position can be opened.
- If three manual trades occur inside a short window, freeze further trading until explicit written reset.

### P1: Manual Position Sentinel

Add a read-only sentinel that does not close trades but escalates alerts:

- manual exposure by symbol,
- manual floating PnL,
- manual position age,
- manual add-on detection,
- "revenge trading" pattern detection.

### P2: Separate "Do Not Touch" From "No Risk"

Manual positions can remain protected from bot closure while still triggering:

- alerts,
- UI warnings,
- trade-entry lockout,
- new-order block,
- required reflection timer.

### P3: End-of-Competition Mode

In the final hour of any challenge:

- no new manual metals trades,
- no increase in position size,
- only reduce or hold existing exposure,
- no strategy changes unless they reduce risk.

### P4: Post-Incident Rule

Add a written rule:

> When I feel the urge to recover a loss immediately, the system must assume I am impaired and restrict new risk.

## Final Assessment

This was not a failure of the harvester's core mechanics. It was a failure of governance around manual intervention.

The right next version of the institution is not a smarter entry signal first. It is a principal-protection layer:

- manual exposure caps,
- emotional-state lockouts,
- hard stop on recovery trading,
- irreversible cool-down after large loss,
- audit-first reporting.

The painful lesson is clear: the system must protect the principal not only from market risk, but from the principal's own high-pressure override behavior.
