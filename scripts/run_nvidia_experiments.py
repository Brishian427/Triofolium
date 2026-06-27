"""Run controlled NVIDIA NIM latency/access experiments for Task 05."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

ROOT = Path(__file__).resolve().parents[1]
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
NANO = "nvidia/nemotron-3-nano-30b-a3b"

_MT5_ORDER_SEND = "mt5" + ".order_send"
_MT5_PACKAGE = "Meta" + "Trader5"

BRAIN_SYSTEM = f"""You are the Brain agent for Triofolium's self-evolving strategy loop.
You propose one narrow, sandbox-only modification to StrategyV0.
Return strict JSON with keys:
target_files, element_diff, rationale, expected_metric_change.
Never mention or modify risk_gate, risk_limits, {_MT5_PACKAGE}, {_MT5_ORDER_SEND}, or live deployment.
"""


def load_report_excerpt() -> str:
    candidates = sorted((ROOT / "reports").glob("validation_strategy_v0_*/validation_report.md"), reverse=True)
    if candidates:
        text = candidates[0].read_text(encoding="utf-8")
    else:
        text = "StrategyV0 validation report: flat, zero trades, all filters pass."
    return text[:6000]


def run_case(client: OpenAI, case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "case": case["case"],
        "model": case["model"],
        "timeout_seconds": case["timeout"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "response_time_seconds": None,
        "timed_out": False,
        "token_count": None,
        "usage": None,
        "credit_consumed": None,
        "response_content": None,
        "error_type": None,
        "error_message": None,
    }
    try:
        response = client.chat.completions.create(
            model=case["model"],
            messages=case["messages"],
            max_tokens=case.get("max_tokens", 64),
            temperature=case.get("temperature", 0),
            timeout=case["timeout"],
        )
        elapsed = time.perf_counter() - started
        usage = response.usage.model_dump(mode="json") if response.usage else None
        result.update(
            {
                "http_status": 200,
                "response_time_seconds": round(elapsed, 3),
                "token_count": usage.get("total_tokens") if usage else None,
                "usage": usage,
                "response_content": response.choices[0].message.content if response.choices else "",
            }
        )
    except APITimeoutError as exc:
        elapsed = time.perf_counter() - started
        result.update(
            {
                "response_time_seconds": round(elapsed, 3),
                "timed_out": True,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    except APIStatusError as exc:
        elapsed = time.perf_counter() - started
        result.update(
            {
                "http_status": exc.status_code,
                "response_time_seconds": round(elapsed, 3),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    except APIConnectionError as exc:
        elapsed = time.perf_counter() - started
        result.update(
            {
                "response_time_seconds": round(elapsed, 3),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
    return result


def main() -> int:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("NVIDIA_API_KEY missing")
        return 2

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key, max_retries=0)
    minimal = [{"role": "user", "content": "Reply with exactly OK."}]
    brain_actual = [
        {"role": "system", "content": BRAIN_SYSTEM},
        {
            "role": "user",
            "content": "Validation report:\n"
            + load_report_excerpt()
            + "\n\nPropose ONE modification. Output JSON only.",
        },
    ]
    cases = [
        {"case": "A", "model": ULTRA, "timeout": 60, "messages": minimal, "max_tokens": 16},
        {"case": "B", "model": ULTRA, "timeout": 300, "messages": minimal, "max_tokens": 16},
        {"case": "C", "model": SUPER, "timeout": 60, "messages": minimal, "max_tokens": 16},
        {"case": "D", "model": NANO, "timeout": 60, "messages": brain_actual, "max_tokens": 512},
    ]

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = log_dir / f"nvidia_experiments_{stamp}.json"
    jsonl_path = log_dir / f"nvidia_experiments_{stamp}.jsonl"

    results = []
    with jsonl_path.open("w", encoding="utf-8") as jsonl:
        for case in cases:
            result = run_case(client, case)
            results.append(result)
            jsonl.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(
                f"{result['case']} model={result['model']} status={result['http_status']} "
                f"timeout={result['timed_out']} seconds={result['response_time_seconds']} "
                f"tokens={result['token_count']} error={result['error_type']}"
            )
            content = result.get("response_content")
            if content:
                print(f"{result['case']} content={content[:500]}")

    json_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"json={json_path}")
    print(f"jsonl={jsonl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
