from __future__ import annotations

import pytest

from trifolium.agents import anthropic_client


class _FakeMessages:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs

        class Block:
            text = "diff --git a/x b/x"

        class Response:
            content = [Block()]

        return Response()


class _FakeAnthropic:
    messages = _FakeMessages()

    def __init__(self, **kwargs):
        pass


def test_anthropic_client_generates_patch(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic_client.anthropic, "Anthropic", _FakeAnthropic)
    client = anthropic_client.AnthropicClient()
    patch = client.generate_code_patch({"target_files": ["x"]}, {"x": "old"})
    assert patch.startswith("diff --git")
    assert _FakeAnthropic.messages.kwargs["model"] == anthropic_client.AnthropicClient.DEFAULT_MODEL


def test_anthropic_client_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(anthropic_client, "ROOT", __import__("pathlib").Path("Z:/definitely_missing"))
    with pytest.raises(ValueError):
        anthropic_client.AnthropicClient(api_key=None)
