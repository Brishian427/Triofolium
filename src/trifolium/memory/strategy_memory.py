"""SQLite Memory Table CRUD for strategy discovery iterations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class StrategyMemory:
    """Small SQLite-backed strategy lineage and metric store."""

    def __init__(self, db_path: str | Path = "data/strategy_memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    def insert(
        self,
        *,
        nickname: str,
        element_table: dict[str, Any],
        parent_nickname: str | None = None,
        metrics: dict[str, Any] | None = None,
        decision: str | None = None,
        rationale: str | None = None,
        current_rank: int | None = None,
        modification_type: str | None = None,
        iteration_log_path: str | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_memory
                (nickname, timestamp, parent_nickname, element_table_json, metrics_json,
                 decision, rationale, current_rank, modification_type, iteration_log_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nickname,
                    datetime.now(timezone.utc).isoformat(),
                    parent_nickname,
                    json.dumps(element_table, default=str),
                    json.dumps(metrics, default=str) if metrics is not None else None,
                    decision,
                    rationale,
                    current_rank,
                    modification_type,
                    iteration_log_path,
                ),
            )

    def get(self, nickname: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM strategy_memory WHERE nickname = ?", (nickname,))
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [item[0] for item in cursor.description]
            return dict(zip(columns, row, strict=False))

    def list_all(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM strategy_memory ORDER BY timestamp ASC")
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def get_tree(self) -> dict[str, list[str]]:
        tree: dict[str, list[str]] = {}
        for entry in self.list_all():
            parent = entry["parent_nickname"] or "ROOT"
            tree.setdefault(parent, []).append(entry["nickname"])
        return tree

    def to_markdown_summary(self) -> str:
        lines = ["# Strategy Memory History", ""]
        for entry in self.list_all():
            lines.extend(
                [
                    f"## {entry['nickname']} (parent: {entry['parent_nickname'] or 'ROOT'})",
                    f"- Timestamp: {entry['timestamp']}",
                    f"- Decision: {entry['decision']}",
                    f"- Rationale: {entry['rationale']}",
                    f"- Current rank: {entry['current_rank']}",
                ]
            )
            if entry["metrics_json"]:
                lines.append(f"- Metrics: `{entry['metrics_json']}`")
            lines.append("")
        return "\n".join(lines)

