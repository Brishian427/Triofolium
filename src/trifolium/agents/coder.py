"""Anthropic-backed coder agent with sandbox patch application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trifolium.agents.anthropic_client import AnthropicClient
from trifolium.agents.scope_guard import validate_patch_scope
from trifolium.loop.sandbox import apply_patch_with_git, copy_repo_to_sandbox


class Coder:
    """Generate a patch, apply it to a sandbox, and enforce scope."""

    def __init__(self, anthropic_client: AnthropicClient | None = None, *, allow_fallback: bool = False) -> None:
        self.client = anthropic_client or AnthropicClient()
        self.allow_fallback = allow_fallback
        self.last_patch: str | None = None
        self.last_metadata: dict[str, Any] = {}

    def generate_and_apply_patch(
        self,
        *,
        hypothesis: dict[str, Any],
        repo_root: Path,
        sandbox_dir: Path,
    ) -> tuple[bool, str | None, str | None]:
        relevant: dict[str, str] = {}
        for target in hypothesis["target_files"]:
            full_path = repo_root / target
            if not full_path.exists():
                return False, None, f"Target file {target} not found in repo"
            relevant[target] = full_path.read_text(encoding="utf-8")

        patch_text = self.client.generate_code_patch(hypothesis, relevant)
        self.last_metadata = {"provider": "anthropic", "real_call": True, "fallback_used": False}
        if not patch_text.startswith("diff --git") and self.allow_fallback:
            patch_text = self._fallback_patch(hypothesis, relevant)
            self.last_metadata["fallback_used"] = True
        self.last_patch = patch_text

        passed, reason = validate_patch_scope(patch_text, [])
        if not passed:
            return False, None, f"Patch validation failed: {reason}"

        copy_repo_to_sandbox(repo_root, sandbox_dir)
        applied, error = apply_patch_with_git(sandbox_dir, patch_text)
        if not applied:
            if self.allow_fallback and not self.last_metadata.get("fallback_used"):
                patch_text = self._fallback_patch(hypothesis, relevant)
                self.last_patch = patch_text
                self.last_metadata["fallback_used"] = True
                passed, reason = validate_patch_scope(patch_text, [])
                if not passed:
                    return False, None, f"Fallback patch validation failed: {reason}"
                applied, error = apply_patch_with_git(sandbox_dir, patch_text)
            if not applied:
                return False, None, f"Patch apply failed: {error}"

        resulting_paths = [sandbox_dir / target for target in hypothesis["target_files"]]
        passed, reason = validate_patch_scope(patch_text, resulting_paths)
        if not passed:
            return False, None, f"Post-apply scope check failed: {reason}"

        patch_path = sandbox_dir / ".applied_patch.diff"
        patch_path.write_text(patch_text, encoding="utf-8")
        return True, str(sandbox_dir), None

    @staticmethod
    def _fallback_patch(hypothesis: dict[str, Any], relevant: dict[str, str]) -> str:
        target = hypothesis["target_files"][0]
        content = relevant[target]
        replacements = [
            ('destroyer_validation_sharpe_threshold: "0.0"', 'destroyer_validation_sharpe_threshold: "-0.05"'),
            ('sigmoid_scale: "1.5"', 'sigmoid_scale: "1.2"'),
        ]
        old_line = new_line = None
        line_number = 1
        for old, new in replacements:
            if old in content:
                old_line, new_line = old, new
                line_number = content.splitlines().index(old) + 1
                break
        if old_line is None or new_line is None:
            old_line = content.splitlines()[0]
            new_line = old_line
        return (
            f"diff --git a/{target} b/{target}\n"
            f"--- a/{target}\n"
            f"+++ b/{target}\n"
            f"@@ -{line_number},1 +{line_number},1 @@\n"
            f"-{old_line}\n"
            f"+{new_line}\n"
        )
