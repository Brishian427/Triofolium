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
    git_apply_args = ["git", "apply", "--ignore-whitespace", "--recount", "--whitespace=fix"]
    check = subprocess.run([*git_apply_args, "--check", str(patch_file)], cwd=sandbox_dir, capture_output=True, text=True)
    if check.returncode != 0:
        if _apply_unified_diff_fallback(sandbox_dir, patch_text):
            return True, None
        return False, check.stderr.strip() or check.stdout.strip()
    applied = subprocess.run([*git_apply_args, str(patch_file)], cwd=sandbox_dir, capture_output=True, text=True)
    if applied.returncode != 0:
        if _apply_unified_diff_fallback(sandbox_dir, patch_text):
            return True, None
        return False, applied.stderr.strip() or applied.stdout.strip()
    _apply_simple_line_replacements(sandbox_dir, patch_text)
    return True, None


def _apply_unified_diff_fallback(sandbox_dir: Path, patch_text: str) -> bool:
    current_path: Path | None = None
    old_lines: list[str] = []
    new_lines: list[str] = []
    changed = False

    def flush() -> bool:
        nonlocal old_lines, new_lines, changed
        if current_path is None or not current_path.exists() or not old_lines:
            old_lines = []
            new_lines = []
            return False
        content = current_path.read_text(encoding="utf-8")
        old_block = "\n".join(old_lines)
        new_block = "\n".join(new_lines)
        if old_block in content:
            current_path.write_text(content.replace(old_block, new_block, 1), encoding="utf-8")
            changed = True
            old_lines = []
            new_lines = []
            return True
        for old, new in zip([line for line in old_lines if line], [line for line in new_lines if line], strict=False):
            if old != new and old in content:
                content = content.replace(old, new, 1)
                current_path.write_text(content, encoding="utf-8")
                changed = True
                old_lines = []
                new_lines = []
                return True
        old_lines = []
        new_lines = []
        return False

    for line in patch_text.splitlines():
        if line.startswith("--- "):
            flush()
            continue
        if line.startswith("+++ "):
            raw = line[4:].strip().split("\t", 1)[0]
            current_path = sandbox_dir / raw.removeprefix("b/")
            old_lines = []
            new_lines = []
            continue
        if line.startswith("@@"):
            flush()
            old_lines = []
            new_lines = []
            continue
        if current_path is None:
            continue
        if line.startswith("-") and not line.startswith("---"):
            old_lines.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            new_lines.append(line[1:])
        elif line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
    flush()
    return changed


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
