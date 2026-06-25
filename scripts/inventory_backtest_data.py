"""Inventory the deployed xSyphon parquet backtest dataset.

The script reads parquet metadata and selected columns incrementally. It avoids
loading the full 20 GiB dataset into memory while producing the Task 03 L0
inventory report and a spread-by-hour heatmap.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "pricer-output-2026-05-11_2026-06-10"
DEFAULT_REPORT = ROOT / "reports" / "data_inventory.md"
DEFAULT_HEATMAP = ROOT / "reports" / "spread_heatmap_p95.png"
FILENAME_RE = re.compile(r"^(?P<symbol>.+)_(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})\.parquet$")


@dataclass
class FileInfo:
    path: Path
    symbol: str
    trading_day: date
    size: int


@dataclass
class SymbolStats:
    symbol: str
    files: list[FileInfo] = field(default_factory=list)
    rows: int = 0
    earliest: str | None = None
    latest: str | None = None
    schema: list[tuple[str, str]] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    depth_static_checked_rows: int = 0
    bidprices_unique: set[str] = field(default_factory=set)
    bidsizes_unique: set[str] = field(default_factory=set)
    askprices_unique: set[str] = field(default_factory=set)
    asksizes_unique: set[str] = field(default_factory=set)


@dataclass
class SpreadAccumulator:
    """Streaming spread statistics with bounded reservoir for quantiles."""

    count: int = 0
    total: float = 0.0
    sample: list[float] = field(default_factory=list)
    max_sample: int = 20_000

    def add_many(self, values: list[float]) -> None:
        for value in values:
            if not math.isfinite(value) or value <= 0:
                continue
            self.count += 1
            self.total += value
            if len(self.sample) < self.max_sample:
                self.sample.append(value)

    def quantiles(self) -> dict[str, float | None]:
        if self.count == 0 or not self.sample:
            return {"mean": None, "p50": None, "p95": None, "p99": None}
        values = sorted(self.sample)
        return {
            "mean": self.total / self.count,
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory xSyphon parquet backtest data.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--heatmap", type=Path, default=DEFAULT_HEATMAP)
    parser.add_argument("--depth-sample-files-per-symbol", type=int, default=3)
    parser.add_argument("--depth-rows-per-file", type=int, default=200)
    return parser.parse_args()


def load_competition_symbols() -> list[str]:
    config_path = ROOT / "config" / "instruments.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return [item["symbol"] for item in data["instruments"]]


def discover_files(data_dir: Path) -> tuple[list[FileInfo], list[Path]]:
    parquet_files: list[FileInfo] = []
    unmatched: list[Path] = []
    for path in sorted(data_dir.glob("*.parquet")):
        match = FILENAME_RE.match(path.name)
        if not match:
            unmatched.append(path)
            continue
        trading_day = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
        parquet_files.append(
            FileInfo(
                path=path,
                symbol=match.group("symbol"),
                trading_day=trading_day,
                size=path.stat().st_size,
            )
        )
    return parquet_files, unmatched


def schema_pairs(schema: pa.Schema) -> list[tuple[str, str]]:
    return [(field.name, str(field.type)) for field in schema]


def scalar_min_max(table: pa.Table, column: str) -> tuple[str | None, str | None]:
    if column not in table.column_names or table.num_rows == 0:
        return None, None
    values = table[column].combine_chunks()
    min_value = pc.min(values).as_py()
    max_value = pc.max(values).as_py()
    return str(min_value) if min_value is not None else None, str(max_value) if max_value is not None else None


def update_range(stats: SymbolStats, earliest: str | None, latest: str | None) -> None:
    if earliest is not None and (stats.earliest is None or earliest < stats.earliest):
        stats.earliest = earliest
    if latest is not None and (stats.latest is None or latest > stats.latest):
        stats.latest = latest


def safe_list_repr(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def collect_depth_samples(stats: SymbolStats, table: pa.Table, max_rows: int) -> None:
    columns = [name for name in ["bidprices", "bidsizes", "askprices", "asksizes"] if name in table.column_names]
    if not columns or max_rows <= 0:
        return
    sample = table.select(columns).slice(0, max_rows).to_pylist()
    for row in sample:
        stats.bidprices_unique.add(safe_list_repr(row.get("bidprices")))
        stats.bidsizes_unique.add(safe_list_repr(row.get("bidsizes")))
        stats.askprices_unique.add(safe_list_repr(row.get("askprices")))
        stats.asksizes_unique.add(safe_list_repr(row.get("asksizes")))
        stats.depth_static_checked_rows += 1


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    position = (len(sorted_values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def inspect_dataset(
    files: list[FileInfo],
    depth_sample_files_per_symbol: int,
    depth_rows_per_file: int,
) -> tuple[dict[str, SymbolStats], dict[tuple[str, int], SpreadAccumulator]]:
    stats_by_symbol: dict[str, SymbolStats] = defaultdict(lambda: SymbolStats(symbol=""))
    spread_values: dict[tuple[str, int], SpreadAccumulator] = defaultdict(SpreadAccumulator)
    files_seen_for_depth: Counter[str] = Counter()

    for index, file_info in enumerate(files, start=1):
        if index == 1 or index % 50 == 0:
            print(f"Scanning {index}/{len(files)}: {file_info.path.name}", flush=True)
        stats = stats_by_symbol[file_info.symbol]
        if not stats.symbol:
            stats.symbol = file_info.symbol
        stats.files.append(file_info)

        parquet_file = pq.ParquetFile(file_info.path)
        stats.rows += parquet_file.metadata.num_rows
        if not stats.schema:
            stats.schema = schema_pairs(parquet_file.schema_arrow)

        first_table = parquet_file.read_row_group(0, columns=[name for name in ["time"] if name in parquet_file.schema_arrow.names])
        earliest, _ = scalar_min_max(first_table, "time")
        last_table = parquet_file.read_row_group(
            parquet_file.num_row_groups - 1,
            columns=[name for name in ["time"] if name in parquet_file.schema_arrow.names],
        )
        _, latest = scalar_min_max(last_table, "time")
        update_range(stats, earliest, latest)

        if not stats.sample_rows:
            sample_columns = [
                name
                for name in [
                    "time",
                    "sym",
                    "provider",
                    "valuedate",
                    "received",
                    "bid",
                    "ask",
                    "bidprices",
                    "bidsizes",
                    "askprices",
                    "asksizes",
                ]
                if name in parquet_file.schema_arrow.names
            ]
            stats.sample_rows = parquet_file.read_row_group(0, columns=sample_columns).slice(0, 5).to_pylist()

        should_sample_depth = files_seen_for_depth[file_info.symbol] < depth_sample_files_per_symbol
        files_seen_for_depth[file_info.symbol] += 1

        columns = [name for name in ["time", "bid", "ask", "bidprices", "bidsizes", "askprices", "asksizes"] if name in parquet_file.schema_arrow.names]
        for row_group_index in range(parquet_file.num_row_groups):
            table = parquet_file.read_row_group(row_group_index, columns=columns)
            if {"time", "bid", "ask"}.issubset(table.column_names):
                hours = pc.cast(pc.utf8_slice_codeunits(table["time"], 11, 13), pa.int8(), safe=False)
                spreads = pc.subtract(table["ask"], table["bid"])
                positive = pc.greater(spreads, 0)
                filtered_hours = pc.filter(hours, positive).to_pylist()
                filtered_spreads = pc.filter(spreads, positive).to_pylist()
                grouped: dict[int, list[float]] = defaultdict(list)
                for hour, spread in zip(filtered_hours, filtered_spreads, strict=False):
                    if hour is not None and spread is not None:
                        grouped[int(hour)].append(float(spread))
                for hour, values in grouped.items():
                    spread_values[(file_info.symbol, hour)].add_many(values)
            if should_sample_depth and row_group_index == 0:
                collect_depth_samples(stats, table, depth_rows_per_file)

    return dict(stats_by_symbol), spread_values


def date_gaps(days: list[date]) -> list[str]:
    if not days:
        return []
    present = set(days)
    current = min(days)
    end = max(days)
    gaps: list[str] = []
    while current <= end:
        if current.weekday() < 5 and current not in present:
            gaps.append(current.isoformat())
        current += timedelta(days=1)
    return gaps


def write_heatmap(spread_values: dict[tuple[str, int], SpreadAccumulator], heatmap_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    symbols = sorted({symbol for symbol, _hour in spread_values})
    for symbol in symbols:
        row = {"symbol": symbol}
        for hour in range(24):
            accumulator = spread_values.get((symbol, hour))
            row[hour] = accumulator.quantiles()["p95"] if accumulator else None
        rows.append(row)
    heatmap = pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame()
    heatmap_path.parent.mkdir(parents=True, exist_ok=True)
    if heatmap.empty:
        return
    fig_width = max(12, len(heatmap.columns) * 0.55)
    fig_height = max(7, len(heatmap.index) * 0.35)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    masked = heatmap.astype(float)
    image = ax.imshow(masked.values, aspect="auto", cmap="viridis")
    ax.set_xticks(range(24))
    ax.set_xticklabels([str(hour) for hour in range(24)])
    ax.set_yticks(range(len(masked.index)))
    ax.set_yticklabels(masked.index)
    ax.set_xlabel("UTC hour")
    ax.set_ylabel("Symbol")
    ax.set_title("Spread p95 by symbol and UTC hour")
    fig.colorbar(image, ax=ax, label="price units")
    fig.tight_layout()
    fig.savefig(heatmap_path, dpi=160)
    plt.close(fig)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
    return "\n".join(lines)


def write_report(
    report_path: Path,
    heatmap_path: Path,
    data_dir: Path,
    files: list[FileInfo],
    unmatched: list[Path],
    stats_by_symbol: dict[str, SymbolStats],
    spread_values: dict[tuple[str, int], SpreadAccumulator],
) -> None:
    competition = load_competition_symbols()
    data_symbols = sorted(stats_by_symbol)
    present = [symbol for symbol in competition if symbol in stats_by_symbol]
    missing = [symbol for symbol in competition if symbol not in stats_by_symbol]
    extra = [symbol for symbol in data_symbols if symbol not in competition]
    total_bytes = sum(file_info.size for file_info in files)

    symbol_rows = []
    for symbol in data_symbols:
        stats = stats_by_symbol[symbol]
        days = sorted(file_info.trading_day for file_info in stats.files)
        gaps = date_gaps(days)
        symbol_rows.append(
            [
                symbol,
                len(stats.files),
                f"{sum(item.size for item in stats.files) / (1024 ** 3):.3f}",
                stats.rows,
                days[0].isoformat() if days else "",
                days[-1].isoformat() if days else "",
                stats.earliest or "",
                stats.latest or "",
                ", ".join(gaps[:8]) + (" ..." if len(gaps) > 8 else ""),
            ]
        )

    schema_sections: list[str] = []
    for symbol in data_symbols:
        stats = stats_by_symbol[symbol]
        schema_md = markdown_table(["Column", "Dtype"], [[name, dtype] for name, dtype in stats.schema])
        sample = pd.DataFrame(stats.sample_rows)
        schema_sections.append(
            f"### {symbol}\n\n"
            f"Schema:\n\n{schema_md}\n\n"
            f"Sample 5 rows:\n\n```text\n{sample.to_string(index=False, max_colwidth=80)}\n```\n"
        )

    spread_rows = []
    for symbol in data_symbols:
        for hour in range(24):
            accumulator = spread_values.get((symbol, hour))
            if accumulator is None:
                continue
            q = accumulator.quantiles()
            if q["mean"] is None:
                continue
            spread_rows.append(
                [
                    symbol,
                    hour,
                    f"{q['mean']:.8g}",
                    f"{q['p50']:.8g}",
                    f"{q['p95']:.8g}",
                    f"{q['p99']:.8g}",
                ]
            )

    depth_rows = []
    for symbol in data_symbols:
        stats = stats_by_symbol[symbol]
        unique_counts = [
            len(stats.bidprices_unique),
            len(stats.bidsizes_unique),
            len(stats.askprices_unique),
            len(stats.asksizes_unique),
        ]
        depth_rows.append(
            [
                symbol,
                stats.depth_static_checked_rows,
                len(stats.bidprices_unique),
                len(stats.bidsizes_unique),
                len(stats.askprices_unique),
                len(stats.asksizes_unique),
                "static sample" if max(unique_counts or [0]) <= 1 else "dynamic sample",
            ]
        )

    barusd_note = (
        "BARUSD is present in the dataset; generate the required last-30-days price plot in the next pass."
        if "BARUSD" in stats_by_symbol
        else "BARUSD is not present in the deployed dataset, so the required BARUSD identification plot cannot be produced from this data."
    )

    lines = [
        "# Data Inventory",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Data directory: `{data_dir}`",
        "",
        "## Summary",
        "",
        markdown_table(
            ["Metric", "Value"],
            [
                ["Total parquet files", len(files)],
                ["Unmatched parquet filenames", len(unmatched)],
                ["Total size GiB", f"{total_bytes / (1024 ** 3):.3f}"],
                ["Symbols", len(data_symbols)],
                ["Date range from filenames", f"{min(item.trading_day for item in files)} .. {max(item.trading_day for item in files)}"],
            ],
        ),
        "",
        "Top-level directory structure: flat file drop with parquet files named `{SYMBOL}_{YYYY}_{MM}_{DD}.parquet` plus `README.txt`.",
        "",
        "## Competition Symbol Cross-Check",
        "",
        f"Present competition symbols ({len(present)}/15): {', '.join(present) if present else 'None'}",
        "",
        f"Missing competition symbols ({len(missing)}/15): {', '.join(missing) if missing else 'None'}",
        "",
        f"Extra non-competition symbols ({len(extra)}): {', '.join(extra) if extra else 'None'}",
        "",
        "## Per-Symbol Coverage",
        "",
        markdown_table(
            ["Symbol", "Files", "GiB", "Rows", "File Start", "File End", "Earliest Time", "Latest Time", "Weekday Gaps"],
            symbol_rows,
        ),
        "",
        "## BARUSD Identification",
        "",
        barusd_note,
        "",
        "## Spread Distribution Per Symbol Per UTC Hour",
        "",
        f"Heatmap PNG: `{heatmap_path}`",
        "",
        "Mean is accumulated across all positive spreads. P50/P95/P99 use a bounded sample of up to 20,000 spreads per symbol/hour to keep memory usage bounded.",
        "",
        markdown_table(["Symbol", "UTC Hour", "Mean", "P50", "P95", "P99"], spread_rows[:528]),
        "",
        "## Order Book Depth Analysis",
        "",
        "Depth static/dynamic assessment is based on sampled rows from up to three files per symbol, first row group only, to avoid loading the full dataset.",
        "",
        markdown_table(
            [
                "Symbol",
                "Rows Checked",
                "Unique bidprices",
                "Unique bidsizes",
                "Unique askprices",
                "Unique asksizes",
                "Assessment",
            ],
            depth_rows,
        ),
        "",
        "## Schema And Samples",
        "",
        "\n".join(schema_sections),
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.data_dir.exists():
        print(f"Data directory missing: {args.data_dir}", file=sys.stderr)
        return 1
    files, unmatched = discover_files(args.data_dir)
    if not files:
        print(f"No parquet files found in {args.data_dir}", file=sys.stderr)
        return 1
    stats_by_symbol, spread_values = inspect_dataset(
        files,
        depth_sample_files_per_symbol=args.depth_sample_files_per_symbol,
        depth_rows_per_file=args.depth_rows_per_file,
    )
    write_heatmap(spread_values, args.heatmap)
    write_report(args.report, args.heatmap, args.data_dir, files, unmatched, stats_by_symbol, spread_values)
    print(f"Wrote {args.report}")
    print(f"Wrote {args.heatmap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
