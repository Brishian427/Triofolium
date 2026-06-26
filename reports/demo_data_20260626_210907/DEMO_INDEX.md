# Demo 数据包索引

导出窗口：`2026-06-22T00:00:00Z` 到 `2026-06-26T21:09:07Z`

导出目录：`D:\Desktop\Nucleus\Triofolium\reports\demo_data_20260626_210907`

## 关键结论

- MT5 历史导出：`334` 条 deals，`325` 条 orders。
- 本地系统日志：`12,619` 条 Risk Gate 决策，`14,860` 条 profit harvester 关键事件。
- 导出时账户：balance `998491.78`，equity `985764.88`，floating PnL `-12726.90`。
- 导出时仍有 `2` 个 open positions，均为 `magic=0/comment=""` 的手动仓位：
  - `XAGUSD sell 2.0`，floating PnL `-10012.00`
  - `XAUUSD buy 5.0`，floating PnL `-2714.90`
- 已实现收益归因：
  - `profit_harvester`: `+494.98`
  - `harv_reconcile`: `-112.89`
  - `strategy_v0_emer`: `-202.64`
  - manual/client-side blank comment: `-266.97`

## Demo 时优先看的文件

1. `README.md`
   - 数据包总览和导出时间。

2. `mt5_history_deals.csv`
   - MT5 官方 deal 历史，适合证明真实交易发生过。
   - 重点字段：`time_iso`, `ticket`, `order`, `symbol`, `type`, `volume`, `price`, `profit`, `magic`, `comment`。

3. `mt5_open_positions.csv`
   - 导出时仍未平仓的位置。
   - 用来解释最终 equity 和 floating loss。

4. `realized_pnl_by_magic_comment.csv`
   - 最适合 demo 的归因表。
   - `magic=10181/comment=profit_harvester` 是自动 harvester。
   - `magic=0/comment=""` 是人工或客户端手动行为。

5. `risk_gate_decisions.csv`
   - Risk Gate 的每次 allow/reject 证据。
   - 用来展示 institution-as-first-class：订单不是直接进 MT5，而是先经过 gate。

6. `profit_harvester_key_events.csv`
   - harvester 的 entry / take-profit / halt / manual-skip 等关键事件。
   - 适合展示自动收割逻辑和 manual trade protection。

7. `account_state_timeseries.csv`
   - account observability 流。
   - 可用于画 equity / margin / open position count 时间序列。

8. `event_timeline.csv`
   - 合并后的事件时间线。
   - 适合做 demo 叙事：系统启动、订单请求、Risk Gate 决策、take-profit、人工仓位隔离。

9. `raw_logs.zip`
   - 完整原始 JSONL/JSON/log 证据包。
   - 用于审计追溯，不建议 demo 现场直接打开。

10. `config_snapshot/`
    - 导出时 YAML 配置快照。
    - `.env` 没有被复制。

## 建议 Demo 叙事线

1. 第一幕：从无系统到有 Risk Gate
   - 展示 `risk_gate_decisions.csv` 和 `account_state_timeseries.csv`。
   - 重点：系统有订单审查和账户状态记录，不是裸 MT5 下单。

2. 第二幕：profit harvester 正常工作
   - 展示 `profit_harvester_key_events.csv` 中的 `entry_order_result` 和 `take_profit_triggered`。
   - 展示 `realized_pnl_by_magic_comment.csv` 里 `profit_harvester +494.98`。

3. 第三幕：manual intervention 的风险边界
   - 展示 `mt5_open_positions.csv` 中 `magic=0/comment=""` 的 XAGUSD / XAUUSD open positions。
   - 重点不是甩锅，而是说明下一版需要 principal-protection layer。

4. 第四幕：下一版系统方向
   - manual positions 默认不可自动收割。
   - manual 重仓需要冷却/确认/限额。
   - recovery mode 必须被系统识别并阻断。

## 可视化建议

- Equity over time：来自 `account_state_timeseries.csv`
- Realized PnL by actor：来自 `realized_pnl_by_magic_comment.csv`
- Order decision funnel：来自 `risk_gate_decisions.csv`
- Harvester lifecycle timeline：来自 `profit_harvester_key_events.csv`
- Final exposure table：来自 `mt5_open_positions.csv`
