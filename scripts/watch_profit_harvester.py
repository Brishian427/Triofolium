"""Watchdog for the live profit harvester.

The harvester can occasionally hang inside MT5 API calls without exiting.
This watchdog treats a stale heartbeat as failure, kills stale harvester
processes, and restarts the supervised command.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = ROOT / "logs" / "profit_harvester_heartbeat.json"


def _heartbeat_age_seconds() -> float | None:
    if not HEARTBEAT.exists():
        return None
    try:
        raw = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(raw["timestamp"])
    except Exception:
        return None
    return (datetime.now(timezone.utc) - timestamp).total_seconds()


def _harvester_processes() -> list[dict[str, object]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*live_profit_harvester.py*' -and $_.CommandLine -notlike '*watch_profit_harvester.py*' } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, cwd=ROOT)
    text = result.stdout.strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        return [data]
    return list(data)


def _stop_harvesters() -> None:
    command = (
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*live_profit_harvester.py*' -and $_.CommandLine -notlike '*watch_profit_harvester.py*' }; "
        "foreach ($proc in $procs) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], cwd=ROOT)


def _start_harvester(session_start_equity: str) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout = ROOT / "logs" / f"profit_harvester_stdout_watch_{stamp}.log"
    stderr = ROOT / "logs" / f"profit_harvester_stderr_watch_{stamp}.log"
    command = (
        "$env:PYTHONPATH='src'; "
        "$env:OPENBLAS_NUM_THREADS='1'; "
        "$env:OMP_NUM_THREADS='1'; "
        f".\\.venv\\Scripts\\python.exe scripts\\live_profit_harvester.py --live-approved --session-start-equity {session_start_equity}"
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        stdout=stdout.open("w", encoding="utf-8"),
        stderr=stderr.open("w", encoding="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _log(event: str, payload: dict[str, object]) -> None:
    path = ROOT / "logs" / "profit_harvester_watchdog.jsonl"
    path.parent.mkdir(exist_ok=True)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, "payload": payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def run_watchdog(max_heartbeat_age_seconds: int, session_start_equity: str, poll_seconds: int) -> None:
    while True:
        procs = _harvester_processes()
        age = _heartbeat_age_seconds()
        stale = age is None or age > max_heartbeat_age_seconds
        if not procs or stale:
            _log("harvester_restart", {"process_count": len(procs), "heartbeat_age_seconds": age})
            _stop_harvesters()
            _start_harvester(session_start_equity)
            time.sleep(max(3, poll_seconds))
        else:
            time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-heartbeat-age-seconds", type=int, default=10)
    parser.add_argument("--session-start-equity", default="999988.39")
    parser.add_argument("--poll-seconds", type=int, default=2)
    args = parser.parse_args()
    run_watchdog(args.max_heartbeat_age_seconds, args.session_start_equity, args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
