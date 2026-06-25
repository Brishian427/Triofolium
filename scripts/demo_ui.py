"""Minimal localhost demo UI for Task 05."""

from __future__ import annotations

import argparse
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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


def render_html() -> str:
    memory = StrategyMemory(ROOT / "data" / "strategy_memory.db")
    entries = memory.list_all()
    rows = []
    for entry in entries:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(entry['nickname']))}</td>"
            f"<td>{html.escape(str(entry['parent_nickname']))}</td>"
            f"<td>{html.escape(str(entry['decision']))}</td>"
            f"<td>{html.escape(str(entry['modification_type']))}</td>"
            "</tr>"
        )
    brain = _latest_event("step2_brain_propose")
    coder = _latest_event("step4_coder")
    patch_text = ""
    if coder:
        patch_path = coder.get("data", {}).get("patch_path")
        if patch_path and Path(patch_path).exists():
            patch_text = Path(patch_path).read_text(encoding="utf-8")
    log_tail = "\n".join(_tail(_latest_log()))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <title>Triofolium Task 05</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f7f5; color: #1b1b1b; }}
    table {{ border-collapse: collapse; width: 100%; background: white; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    pre {{ background: #111; color: #eee; padding: 12px; overflow: auto; }}
    details {{ margin: 16px 0; }}
  </style>
</head>
<body>
  <h1>Task 05 Self-Improving Loop</h1>
  <p>Current iteration count: {len(entries)}</p>
  <h2>Memory Table</h2>
  <table><tr><th>Nickname</th><th>Parent</th><th>Decision</th><th>Type</th></tr>{''.join(rows)}</table>
  <h2>Latest Brain Output</h2>
  <pre>{html.escape(json.dumps(brain, indent=2) if brain else 'No brain output yet')}</pre>
  <details><summary>Latest Coder Patch</summary><pre>{html.escape(patch_text or 'No patch yet')}</pre></details>
  <h2>JSONL Tail</h2>
  <pre>{html.escape(log_tail)}</pre>
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
