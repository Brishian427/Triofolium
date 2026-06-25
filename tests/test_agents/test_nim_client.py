from __future__ import annotations

import pytest

from trifolium.agents import nim_client


class _FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs

        class Message:
            content = "OK"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]

        return Response()


class _FakeOpenAI:
    completions = _FakeCompletions()

    def __init__(self, **kwargs):
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_nim_client_uses_model_and_reasoning(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test")
    monkeypatch.setattr(nim_client, "OpenAI", _FakeOpenAI)
    client = nim_client.NIMClient()
    assert client.chat([{"role": "user", "content": "x"}]) == "OK"
    assert _FakeOpenAI.completions.kwargs["model"] == nim_client.NIMClient.DEFAULT_MODEL
    assert _FakeOpenAI.completions.kwargs["timeout"] == 300
    assert "reasoning_budget" in _FakeOpenAI.completions.kwargs["extra_body"]


def test_nim_client_skips_reasoning_body_for_mistral(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test")
    monkeypatch.setattr(nim_client, "OpenAI", _FakeOpenAI)
    client = nim_client.NIMClient(model="mistralai/mistral-nemotron")
    assert client.chat([{"role": "user", "content": "x"}]) == "OK"
    assert "extra_body" not in _FakeOpenAI.completions.kwargs


def test_nim_client_requires_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(nim_client, "ROOT", __import__("pathlib").Path("Z:/definitely_missing"))
    with pytest.raises(ValueError):
        nim_client.NIMClient(api_key=None)
