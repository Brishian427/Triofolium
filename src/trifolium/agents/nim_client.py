"""NVIDIA NIM client wrapper for Nemotron planner calls."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[3]


class NIMClient:
    """Small OpenAI-compatible wrapper around NVIDIA NIM."""

    DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
    FALLBACK_MODEL = "nvidia/nemotron-3-super-120b-a12b"
    SMOKE_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_TIMEOUT_SECONDS = 300

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None) -> None:
        load_dotenv(dotenv_path=ROOT / ".env")
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not set in env or constructor")
        self.model = model or self.DEFAULT_MODEL
        self.client = OpenAI(base_url=base_url or self.DEFAULT_BASE_URL, api_key=self.api_key, max_retries=0)
        self.last_call: dict[str, Any] | None = None

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        reasoning_budget: int = 8192,
        max_tokens: int = 16384,
        temperature: float = 0.7,
        model: str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    ) -> str:
        """Return the assistant content string for one non-streaming chat call."""

        selected_model = model or self.model
        kwargs: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if "nemotron-3-nano" not in selected_model:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": reasoning_budget,
            }
        response = self.client.chat.completions.create(**kwargs)
        self.last_call = {"provider": "nvidia_nim", "model": selected_model, "real_call": True}
        return response.choices[0].message.content or ""

    def smoke_test(self) -> bool:
        content = self.chat(
            [{"role": "user", "content": "Reply with OK only."}],
            model=self.SMOKE_MODEL,
            max_tokens=8,
            temperature=0,
        )
        return "OK" in content.upper()
