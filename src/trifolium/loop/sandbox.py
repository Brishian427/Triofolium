"""Sandbox copy helpers for candidate strategy patches."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


IGNORE_NAMES = (
    ".git",
    ".venv",
    "__pycache__",
    "*.pyc",
    "logs",
    "reports",
    "sandboxes",
    "data",
    "pricer-output-2026-05-11_2026-06-10",
)


def copy_repo_to_sandbox(repo_root: Path, sandbox_dir: Path) -> None:
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
    shutil.copytree(repo_root, sandbox_dir, ignore=shutil.ignore_patterns(*IGNORE_NAMES))


def apply_patch_with_git(sandbox_dir: Path, patch_text: str) -> tuple[bool, str | None]:
    patch_file = sandbox_dir / ".tmp_patch.diff"
    patch_file.write_text(patch_text, encoding="utf-8")
    check = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=sandbox_dir, capture_output=True, text=True)
    if check.returncode != 0:
        return False, check.stderr.strip() or check.stdout.strip()
    applied = subprocess.run(["git", "apply", str(patch_file)], cwd=sandbox_dir, capture_output=True, text=True)
    if applied.returncode != 0:
        return False, applied.stderr.strip() or applied.stdout.strip()
    _apply_simple_line_replacements(sandbox_dir, patch_text)
    return True, None


def _apply_simple_line_replacements(sandbox_dir: Path, patch_text: str) -> None:
    current_path: Path | None = None
    pending_old: str | None = None
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            current_path = sandbox_dir / line[6:].strip()
            pending_old = None
            continue
        if current_path is None or line.startswith("--- ") or line.startswith("@@"):
            continue
        if line.startswith("-") and not line.startswith("---"):
            pending_old = line[1:]
            continue
        if line.startswith("+") and not line.startswith("+++") and pending_old is not None:
            new = line[1:]
            if current_path.exists():
                content = current_path.read_text(encoding="utf-8")
                if pending_old in content and new not in content:
                    current_path.write_text(content.replace(pending_old, new, 1), encoding="utf-8")
            pending_old = None
