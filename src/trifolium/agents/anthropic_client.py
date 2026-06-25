"""Anthropic client wrapper for strategy patch generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]


class AnthropicClient:
    """Wrapper for Sonnet code-generation calls."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        load_dotenv(dotenv_path=ROOT / ".env")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in env or constructor")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL
        self.last_call: dict[str, Any] | None = None

    def cheap_smoke_test(self) -> bool:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8,
            temperature=0,
            messages=[{"role": "user", "content": "Reply with OK only."}],
        )
        self.last_call = {"provider": "anthropic", "model": self.model, "real_call": True}
        text = "".join(getattr(block, "text", "") for block in response.content)
        return "OK" in text.upper()

    def generate_code_patch(
        self,
        hypothesis: dict[str, Any],
        relevant_source_files: dict[str, str],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Return a unified diff patch implementing a validated hypothesis."""

        system = (
            "You are a code generation assistant for a quant trading strategy self-improvement loop. "
            "Respond with valid unified diff format only. No prose, no markdown code fences, "
            "no explanation text. Start with --- a/path and +++ b/path lines, or with a valid "
            "diff --git header followed by --- and +++ lines. Modify only the files listed in "
            "target_files."
        )
        sections = [f"Hypothesis:\n{hypothesis}\n\nSource files:"]
        for filename, content in relevant_source_files.items():
            sections.append(f"\n--- {filename} ---\n{content}\n")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": "\n".join(sections)}],
        )
        self.last_call = {"provider": "anthropic", "model": self.model, "real_call": True}
        return "".join(getattr(block, "text", "") for block in response.content).strip()
