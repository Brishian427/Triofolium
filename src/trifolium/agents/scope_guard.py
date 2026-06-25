"""Scope enforcement for sandbox strategy patches."""

from __future__ import annotations

import re
from pathlib import Path


ALLOWED_FILES = {
    "src/trifolium/strategy/v0/predictor.py",
    "src/trifolium/strategy/v0/trader.py",
    "src/trifolium/strategy/v0/portfolio.py",
    "src/trifolium/strategy/config/strategy_v0.yaml",
    "config/strategy_v0.yaml",
}

FORBIDDEN_FILES = [
    "src/trifolium/risk_gate/",
    "config/risk_limits.yaml",
    "src/trifolium/strategy/v0/strategy.py",
]

FORBIDDEN_PATTERNS = [
    r"\bimport\s+Meta\s*Trader5\b",
    r"\bfrom\s+Meta\s*Trader5\b",
    r"\bimport\s+mt5\b",
    r"\bmt5[.]order_send\b",
]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").removeprefix("a/").removeprefix("b/")


def check_target_files_in_whitelist(target_files: list[str]) -> tuple[bool, str | None]:
    for target in target_files:
        normalized = normalize_path(target)
        if normalized not in ALLOWED_FILES:
            return False, f"Target file '{target}' not in scope whitelist"
    return True, None


def check_file_blacklist(target_files: list[str]) -> tuple[bool, str | None]:
    for target in target_files:
        normalized = normalize_path(target)
        for forbidden in FORBIDDEN_FILES:
            if normalized.startswith(forbidden):
                return False, f"Target file '{target}' is in blacklist (matches {forbidden})"
    return True, None


def extract_patch_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            raw = line[4:].strip()
            if raw == "/dev/null":
                continue
            path = normalize_path(raw.split("\t", 1)[0])
            if path and path not in paths:
                paths.append(path)
    return paths


def check_patch_content(patch_text: str) -> tuple[bool, str | None]:
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, patch_text):
            return False, f"Patch contains forbidden pattern: {pattern}"
    paths = extract_patch_paths(patch_text)
    if paths:
        passed, reason = check_target_files_in_whitelist(paths)
        if not passed:
            return False, reason
        passed, reason = check_file_blacklist(paths)
        if not passed:
            return False, reason
    return True, None


def check_resulting_files(file_paths: list[Path]) -> tuple[bool, str | None]:
    for path in file_paths:
        if not path.exists() or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                return False, f"File {path} contains forbidden pattern: {pattern}"
    return True, None


def validate_hypothesis_scope(hypothesis: dict) -> tuple[bool, str | None]:
    target_files = hypothesis.get("target_files", [])
    if not target_files:
        return False, "Hypothesis has no target_files"
    passed, reason = check_target_files_in_whitelist(target_files)
    if not passed:
        return False, reason
    return check_file_blacklist(target_files)


def validate_patch_scope(patch_text: str, resulting_file_paths: list[Path]) -> tuple[bool, str | None]:
    passed, reason = check_patch_content(patch_text)
    if not passed:
        return False, reason
    return check_resulting_files(resulting_file_paths)

