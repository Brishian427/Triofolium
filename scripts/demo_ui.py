"""Minimal localhost demo UI for Task 05."""

from __future__ import annotations

import argparse
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.memory.strategy_memory import StrategyMemory


def _latest_log() -> Path | None:
    logs = sorted((ROOT / "logs").glob("loop_iterations_*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def _latest_file(patterns: list[str]) -> Path | None:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(ROOT.glob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0] if candidates else None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _latest_jsonl(patterns: list[str]) -> tuple[Path | None, dict[str, Any] | None]:
    path = _latest_file(patterns)
    if path is None:
        return None, None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            return path, json.loads(line)
        except json.JSONDecodeError:
            continue
    return path, None


def _tail(path: Path | None, lines: int = 80) -> list[str]:
    if path is None or not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()[-lines:]


def _latest_event(event_name: str) -> dict | None:
    for line in reversed(_tail(_latest_log(), lines=200)):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("step") == event_name:
            return event
    return None


def _safe_metric(metrics: dict[str, Any] | None, key: str, default: str = "-") -> str:
    if not metrics:
        return default
    value = metrics
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return html.escape(str(value))


def _extract_metrics(metrics: dict[str, Any] | None) -> dict[str, str]:
    if not metrics:
        return {
            "trade_count": "-",
            "return_pct": "-",
            "maxdd_pct": "-",
            "risk": "-",
            "decision": "-",
            "gate": "-",
            "report": "-",
        }
    d2 = metrics.get("d2", {})
    full = metrics.get("full_backtest", {})
    return {
        "trade_count": str(full.get("trade_count", d2.get("binding_check", {}).get("trade_count", "-"))),
        "return_pct": str(d2.get("primary_objective", {}).get("total_return_pct", full.get("total_return", "-"))),
        "maxdd_pct": str(d2.get("secondary_metrics", {}).get("maxdd_pct", full.get("max_drawdown", "-"))),
        "risk": str(full.get("risk_discipline", "-")),
        "decision": str(d2.get("decision", {}).get("verdict", metrics.get("decision", "-"))),
        "gate": "PASS" if d2.get("gate_check", {}).get("passed") else "FAIL",
        "report": str(metrics.get("markdown_report", "-")),
    }


def _metrics_from_memory(entry: dict[str, Any]) -> dict[str, Any] | None:
    raw = entry.get("metrics_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _render_gate_table(metrics: dict[str, Any] | None) -> str:
    gates = (metrics or {}).get("d2", {}).get("gate_check", {}).get("gates", [])
    if not gates:
        return "<p>No D2 gate data.</p>"
    rows = []
    for gate in gates:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(gate.get('gate', '-')))}</td>"
            f"<td>{html.escape(str(gate.get('threshold', '-')))}</td>"
            f"<td>{html.escape(str(gate.get('value', '-')))}</td>"
            f"<td>{'PASS' if gate.get('passed') else 'FAIL'}</td>"
            "</tr>"
        )
    return "<table><tr><th>Gate</th><th>Threshold</th><th>Value</th><th>Status</th></tr>" + "".join(rows) + "</table>"


def _render_key_values(items: dict[str, Any]) -> str:
    rows = []
    for key, value in items.items():
        rows.append(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(json.dumps(value, default=str) if isinstance(value, dict | list) else str(value))}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def render_html() -> str:
    memory = StrategyMemory(ROOT / "data" / "strategy_memory.db")
    entries = memory.list_all()
    rows = []
    for entry in entries:
        metrics = _extract_metrics(_metrics_from_memory(entry))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(entry['nickname']))}</td>"
            f"<td>{html.escape(str(entry['parent_nickname']))}</td>"
            f"<td>{html.escape(str(entry['decision']))}</td>"
            f"<td>{html.escape(str(entry['modification_type']))}</td>"
            f"<td>{html.escape(metrics['trade_count'])}</td>"
            f"<td>{html.escape(metrics['return_pct'])}</td>"
            f"<td>{html.escape(metrics['maxdd_pct'])}</td>"
            f"<td>{html.escape(metrics['risk'])}</td>"
            f"<td>{html.escape(metrics['gate'])}</td>"
            "</tr>"
        )
    brain = _latest_event("step2_brain_propose")
    coder = _latest_event("step4_coder")
    patch_text = ""
    if coder:
        patch_path = coder.get("data", {}).get("patch_path")
        if patch_path and Path(patch_path).exists():
            patch_text = Path(patch_path).read_text(encoding="utf-8")
    latest_backtest_path = _latest_file([
        "reports/validation_strategy_v0_*/validation_result.json",
        "sandboxes/*/reports/validation_strategy_v0_*/validation_result.json",
    ])
    latest_backtest = _read_json(latest_backtest_path)
    latest_backtest_metrics = _extract_metrics(latest_backtest)
    account_path, account_state = _latest_jsonl(["logs/account_state_*.jsonl"])
    strategy_path, strategy_state = _latest_jsonl(["logs/strategy_v0_*.jsonl"])
    risk_path, risk_order = _latest_jsonl(["logs/risk_gate_*.jsonl"])
    log_tail = "\n".join(_tail(_latest_log()))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>Triofolium Task 05</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f7f5; color: #1b1b1b; }}
    main {{ max-width: 1440px; }}
    section {{ margin: 20px 0 28px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #efefeb; }}
    pre {{ background: #111; color: #eee; padding: 12px; overflow: auto; }}
    details {{ margin: 16px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
    .mono {{ font-family: Consolas, Menlo, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>Task 05 Self-Improving Loop</h1>
  <p>Current iteration count: {len(entries)}</p>
  <section>
    <h2>Memory Table</h2>
    <table><tr><th>Nickname</th><th>Parent</th><th>Decision</th><th>Type</th><th>Trades</th><th>Return %</th><th>MaxDD %</th><th>Risk</th><th>D2 Gate</th></tr>{''.join(rows)}</table>
  </section>
  <section>
    <h2>Latest Backtest Metrics</h2>
    {_render_key_values({
        "source": str(latest_backtest_path) if latest_backtest_path else "No validation_result.json found",
        "trade_count": latest_backtest_metrics["trade_count"],
        "return_pct": latest_backtest_metrics["return_pct"],
        "maxdd_pct": latest_backtest_metrics["maxdd_pct"],
        "risk_discipline": latest_backtest_metrics["risk"],
        "d2_decision": latest_backtest_metrics["decision"],
        "markdown_report": latest_backtest_metrics["report"],
    })}
    {_render_gate_table(latest_backtest)}
  </section>
  <section class="grid">
    <div>
      <h2>Live Account Metrics</h2>
      {_render_key_values({
        "source": str(account_path) if account_path else "No account_state JSONL found",
        "level": _safe_metric(account_state, "level"),
        "equity": _safe_metric(account_state, "equity"),
        "margin_level": _safe_metric(account_state, "margin_level"),
        "leverage": _safe_metric(account_state, "leverage"),
        "open_positions_count": _safe_metric(account_state, "open_positions_count"),
        "biggest_single_symbol_exposure": _safe_metric(account_state, "biggest_single_symbol_exposure"),
        "currency_decomposition": account_state.get("currency_decomposition_snapshot", "-") if account_state else "-",
        "gate_state": account_state.get("gate_state", "-") if account_state else "-",
      })}
    </div>
    <div>
      <h2>Live Strategy Metrics</h2>
      {_render_key_values({
        "source": str(strategy_path) if strategy_path else "No strategy_v0 JSONL found",
        "event": _safe_metric(strategy_state, "event"),
        "destroyer_symbols": strategy_state.get("payload", {}).get("destroyer_symbols", "-") if strategy_state else "-",
        "last_signals": strategy_state.get("payload", {}).get("last_signals", "-") if strategy_state else "-",
        "portfolio_messages": strategy_state.get("payload", {}).get("portfolio_messages", "-") if strategy_state else "-",
        "latest_risk_gate_log": str(risk_path) if risk_path else "No risk_gate JSONL found",
        "latest_risk_gate_status": risk_order.get("final_status", risk_order.get("status", "-")) if risk_order else "-",
      })}
    </div>
  </section>
  <h2>Latest Brain Output</h2>
  <pre>{html.escape(json.dumps(brain, indent=2) if brain else 'No brain output yet')}</pre>
  <details><summary>Latest Coder Patch</summary><pre>{html.escape(patch_text or 'No patch yet')}</pre></details>
  <h2>JSONL Tail</h2>
  <pre>{html.escape(log_tail)}</pre>
</main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"demo_ui listening on http://127.0.0.1:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
