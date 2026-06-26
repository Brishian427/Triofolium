# Triofolium Demo Data Export

- Exported at: 2026-06-26T21:09:21.611447+00:00
- Window start UTC: 2026-06-22T00:00:00+00:00
- Window end UTC: 2026-06-26T21:09:07.800866+00:00

## Contents

- `mt5_history_deals.csv`: MT5 deal history for the export window.
- `mt5_history_orders.csv`: MT5 order history for the export window.
- `mt5_open_positions.csv`: current open positions at export time.
- `mt5_account_snapshot.json`: account snapshot at export time.
- `realized_pnl_by_magic_comment.csv`: realized PnL attribution by MT5 magic/comment.
- `risk_gate_decisions.csv`: every logged Risk Gate decision.
- `profit_harvester_key_events.csv`: key harvester lifecycle/order/take-profit events.
- `account_state_timeseries.csv`: account-state observability stream.
- `event_timeline.csv`: combined demo timeline from harvester and Risk Gate logs.
- `log_manifest.csv`: local log inventory.
- `raw_logs.zip`: compressed copy of JSONL/JSON/log evidence.
- `config_snapshot/`: YAML config snapshot, excluding `.env`.

## Snapshot

- Balance: 998491.78
- Equity: 985764.88
- Floating PnL: -12726.9
- Margin level: 1123.768225546882
- Open positions: 2
- MT5 deals exported: 334
- MT5 orders exported: 325
- Risk Gate decisions parsed: 12619
- Harvester key events parsed: 14860

## Notes

This exporter is read-only. It does not submit, close, restart, or modify live trading state.
