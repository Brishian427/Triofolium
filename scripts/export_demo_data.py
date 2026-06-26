"""Export read-only MT5 and local log evidence for demo preparation."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import MetaTrader5 as mt5

from trifolium.adapter.mt5_client import mt5_session


DEFAULT_START = "2026-06-22T00:00:00+00:00"
KEY_HARVESTER_EVENTS = {
    "entry_order_result",
    "take_profit_triggered",
    "take_profit_order_result",
    "rejected",
    "halted",
    "hard_kill",
    "hard_kills_disabled_for_manual_trade_protection",
    "target_skipped_unmanaged_position",
    "profit_harvester_started",
}


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def mt5_record_to_dict(record: Any) -> dict[str, Any]:
    data = record._asdict() if hasattr(record, "_asdict") else dict(record)
    for key in ("time", "time_setup", "time_done", "time_expiration", "time_msc", "time_setup_msc", "time_done_msc"):
        if key in data and data[key]:
            try:
                if str(key).endswith("_msc"):
                    data[f"{key}_iso"] = datetime.fromtimestamp(float(data[key]) / 1000, timezone.utc).isoformat()
                else:
                    data[f"{key}_iso"] = datetime.fromtimestamp(float(data[key]), timezone.utc).isoformat()
            except (OSError, OverflowError, ValueError):
                pass
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], preferred: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    preferred = preferred or []
    keys: list[str] = []
    for key in preferred:
        if any(key in row for row in rows):
            keys.append(key)
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_number, {"_parse_error": str(exc), "_raw": line[:500]}


def export_mt5(out_dir: Path, start: datetime, end: datetime) -> dict[str, Any]:
    with mt5_session():
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        positions = mt5.positions_get() or []
        deals = mt5.history_deals_get(start, end) or []
        orders = mt5.history_orders_get(start, end) or []

        account_payload = account._asdict() if account is not None else {"error": mt5.last_error()}
        terminal_payload = terminal._asdict() if terminal is not None else {"error": mt5.last_error()}
        position_rows = [mt5_record_to_dict(position) for position in positions]
        deal_rows = [mt5_record_to_dict(deal) for deal in deals]
        order_rows = [mt5_record_to_dict(order) for order in orders]

    write_json(out_dir / "mt5_account_snapshot.json", account_payload)
    write_json(out_dir / "mt5_terminal_snapshot.json", terminal_payload)
    write_csv(out_dir / "mt5_open_positions.csv", position_rows)
    write_csv(out_dir / "mt5_history_deals.csv", deal_rows)
    write_csv(out_dir / "mt5_history_orders.csv", order_rows)

    pnl_by_magic_comment: dict[tuple[str, str], float] = defaultdict(float)
    close_deals = 0
    for row in deal_rows:
        profit = float(row.get("profit") or 0)
        if profit == 0:
            continue
        close_deals += 1
        magic = str(row.get("magic", ""))
        comment = str(row.get("comment", ""))
        pnl_by_magic_comment[(magic, comment)] += profit
    attribution_rows = [
        {"magic": magic, "comment": comment, "realized_pnl": round(pnl, 2)}
        for (magic, comment), pnl in sorted(pnl_by_magic_comment.items(), key=lambda item: item[1])
    ]
    write_csv(out_dir / "realized_pnl_by_magic_comment.csv", attribution_rows, ["magic", "comment", "realized_pnl"])

    return {
        "account": account_payload,
        "terminal": terminal_payload,
        "open_positions_count": len(position_rows),
        "deals_count": len(deal_rows),
        "orders_count": len(order_rows),
        "close_deals_with_nonzero_profit": close_deals,
        "realized_pnl_by_magic_comment": attribution_rows,
    }


def export_logs(out_dir: Path, start: datetime, end: datetime) -> dict[str, Any]:
    logs_dir = ROOT / "logs"
    log_files = sorted(logs_dir.glob("*"))
    manifest_rows: list[dict[str, Any]] = []
    harvester_rows: list[dict[str, Any]] = []
    risk_gate_rows: list[dict[str, Any]] = []
    account_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()

    for path in log_files:
        if path.is_dir():
            continue
        stat = path.stat()
        row = {
            "path": str(path.relative_to(ROOT)),
            "size_bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "included_in_raw_zip": path.suffix.lower() in {".jsonl", ".json", ".log"},
        }
        if path.suffix.lower() == ".jsonl":
            line_count = 0
            parse_errors = 0
            for line_number, record in read_jsonl(path):
                line_count += 1
                if "_parse_error" in record:
                    parse_errors += 1
                    continue
                timestamp_raw = record.get("timestamp") or record.get("time")
                timestamp = None
                if isinstance(timestamp_raw, str):
                    try:
                        timestamp = parse_dt(timestamp_raw)
                    except ValueError:
                        timestamp = None

                if "profit_harvester_" in path.name:
                    event = str(record.get("event") or record.get("type") or "")
                    event_counts[event] += 1
                    if event in KEY_HARVESTER_EVENTS:
                        compact = {
                            "timestamp": timestamp_raw,
                            "source": path.name,
                            "event": event,
                            "symbol": record.get("symbol") or record.get("target", {}).get("symbol"),
                            "side": record.get("side") or record.get("target", {}).get("side"),
                            "ticket": record.get("ticket") or record.get("position", {}).get("ticket"),
                            "profit": record.get("profit") or record.get("unrealized_pnl"),
                            "status": record.get("status") or record.get("result", {}).get("status"),
                            "reason": record.get("reason") or record.get("result", {}).get("reason"),
                            "record": record,
                        }
                        harvester_rows.append(compact)
                        if timestamp is None or start <= timestamp <= end:
                            timeline_rows.append({**compact, "source_type": "profit_harvester"})

                if path.name.startswith("risk_gate_"):
                    request = record.get("request") or {}
                    compact = {
                        "timestamp": timestamp_raw,
                        "source": path.name,
                        "symbol": request.get("symbol"),
                        "side": request.get("side"),
                        "lots": request.get("lots"),
                        "comment": request.get("comment"),
                        "final_status": record.get("final_status"),
                        "reason": record.get("reason"),
                        "mt5_retcode": (record.get("mt5_response") or {}).get("retcode"),
                        "mt5_order": (record.get("mt5_response") or {}).get("order"),
                        "mt5_deal": (record.get("mt5_response") or {}).get("deal"),
                    }
                    risk_gate_rows.append(compact)
                    if timestamp is None or start <= timestamp <= end:
                        timeline_rows.append({**compact, "source_type": "risk_gate"})

                if path.name.startswith("account_state_"):
                    account_rows.append(
                        {
                            "timestamp": timestamp_raw,
                            "source": path.name,
                            "level": record.get("level"),
                            "equity": record.get("equity"),
                            "margin_level": record.get("margin_level"),
                            "open_positions_count": record.get("open_positions_count"),
                            "biggest_single_symbol_exposure": record.get("biggest_single_symbol_exposure"),
                            "messages": record.get("messages"),
                        }
                    )
            row["line_count"] = line_count
            row["parse_errors"] = parse_errors
        manifest_rows.append(row)

    write_csv(out_dir / "log_manifest.csv", manifest_rows)
    write_csv(out_dir / "profit_harvester_key_events.csv", harvester_rows)
    write_csv(out_dir / "risk_gate_decisions.csv", risk_gate_rows)
    write_csv(out_dir / "account_state_timeseries.csv", account_rows)
    write_csv(
        out_dir / "event_timeline.csv",
        sorted(timeline_rows, key=lambda item: str(item.get("timestamp") or "")),
    )
    write_csv(out_dir / "profit_harvester_event_counts.csv", [{"event": key, "count": value} for key, value in event_counts.most_common()])

    raw_zip = out_dir / "raw_logs.zip"
    with zipfile.ZipFile(raw_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in log_files:
            if path.is_file() and path.suffix.lower() in {".jsonl", ".json", ".log"}:
                archive.write(path, path.relative_to(ROOT))

    config_dir = out_dir / "config_snapshot"
    config_dir.mkdir(exist_ok=True)
    for path in (ROOT / "config").glob("*.yaml"):
        shutil.copy2(path, config_dir / path.name)

    return {
        "log_files_count": len(manifest_rows),
        "raw_logs_zip": str(raw_zip),
        "raw_logs_zip_size_bytes": raw_zip.stat().st_size,
        "profit_harvester_key_events": len(harvester_rows),
        "risk_gate_decisions": len(risk_gate_rows),
        "account_state_rows": len(account_rows),
        "event_counts_top": event_counts.most_common(20),
    }


def write_readme(out_dir: Path, start: datetime, end: datetime, summary: dict[str, Any]) -> None:
    account = summary.get("mt5", {}).get("account", {})
    lines = [
        "# Triofolium Demo Data Export",
        "",
        f"- Exported at: {datetime.now(timezone.utc).isoformat()}",
        f"- Window start UTC: {start.isoformat()}",
        f"- Window end UTC: {end.isoformat()}",
        "",
        "## Contents",
        "",
        "- `mt5_history_deals.csv`: MT5 deal history for the export window.",
        "- `mt5_history_orders.csv`: MT5 order history for the export window.",
        "- `mt5_open_positions.csv`: current open positions at export time.",
        "- `mt5_account_snapshot.json`: account snapshot at export time.",
        "- `realized_pnl_by_magic_comment.csv`: realized PnL attribution by MT5 magic/comment.",
        "- `risk_gate_decisions.csv`: every logged Risk Gate decision.",
        "- `profit_harvester_key_events.csv`: key harvester lifecycle/order/take-profit events.",
        "- `account_state_timeseries.csv`: account-state observability stream.",
        "- `event_timeline.csv`: combined demo timeline from harvester and Risk Gate logs.",
        "- `log_manifest.csv`: local log inventory.",
        "- `raw_logs.zip`: compressed copy of JSONL/JSON/log evidence.",
        "- `config_snapshot/`: YAML config snapshot, excluding `.env`.",
        "",
        "## Snapshot",
        "",
        f"- Balance: {account.get('balance')}",
        f"- Equity: {account.get('equity')}",
        f"- Floating PnL: {account.get('profit')}",
        f"- Margin level: {account.get('margin_level')}",
        f"- Open positions: {summary.get('mt5', {}).get('open_positions_count')}",
        f"- MT5 deals exported: {summary.get('mt5', {}).get('deals_count')}",
        f"- MT5 orders exported: {summary.get('mt5', {}).get('orders_count')}",
        f"- Risk Gate decisions parsed: {summary.get('logs', {}).get('risk_gate_decisions')}",
        f"- Harvester key events parsed: {summary.get('logs', {}).get('profit_harvester_key_events')}",
        "",
        "## Notes",
        "",
        "This exporter is read-only. It does not submit, close, restart, or modify live trading state.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START, help="UTC ISO timestamp, default competition start estimate.")
    parser.add_argument("--end", default=datetime.now(timezone.utc).isoformat(), help="UTC ISO timestamp.")
    parser.add_argument("--out-dir", default=None, help="Output directory. Defaults to reports/demo_data_<timestamp>.")
    args = parser.parse_args()

    start = parse_dt(args.start)
    end = parse_dt(args.end)
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "reports" / f"demo_data_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "output_dir": str(out_dir),
        "mt5": export_mt5(out_dir, start, end),
        "logs": export_logs(out_dir, start, end),
    }
    write_json(out_dir / "export_summary.json", summary)
    write_readme(out_dir, start, end, summary)
    print(json.dumps({"output_dir": str(out_dir), "summary": summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
