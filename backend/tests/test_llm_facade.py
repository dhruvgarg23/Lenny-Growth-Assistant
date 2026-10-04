"""Facade seam tests — dispatch, availability, and shared telemetry.

Fake adapters prove the leverage: provider selection and the think filter
are exercised with zero network and zero keys.
"""
import pytest

from app.services.llm import facade
from app.services.llm.anthropic import AnthropicAdapter
from app.services.llm.groq import GroqAdapter
from app.services.llm.ollama import OllamaAdapter


class FakeAdapter:
    def __init__(self, tokens=(), available=True):
        self.tokens = list(tokens)
        self.available = available

    @property
    def identity(self):
        return "fake", "fake-1"

    def describe(self):
        return {}

    async def check_available(self):
        return (self.available, None if self.available else "fake down")

    async def stream_tokens(self, messages):
        for t in self.tokens:
            yield t


async def collect():
    return [t async for t in facade.stream([{"role": "user", "content": "hi"}])]


async def test_unknown_provider_raises_and_reports_unavailable(monkeypatch):
    monkeypatch.setattr(facade.runtime, "provider", "nope")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        await collect()
    # check_available degrades to (False, hint) instead of raising
    ok, hint = await facade.check_available()
    assert ok is False and "nope" in hint


async def test_missing_key_raises_before_network(monkeypatch):
    monkeypatch.setattr(facade.runtime, "provider", "anthropic")
    monkeypatch.setattr(facade.runtime._settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await collect()


async def test_dispatch_uses_adapter_stream_and_filters_think(monkeypatch):
    monkeypatch.setattr(
        facade, "_active_adapter",
        lambda: FakeAdapter(["<think>hidden reasoning</think>", "Hello"]),
    )
    assert await collect() == ["Hello"]


async def test_adapter_failure_propagates(monkeypatch):
    class Boom(FakeAdapter):
        async def stream_tokens(self, messages):
            raise TimeoutError("timed out waiting")
            yield

    monkeypatch.setattr(facade, "_active_adapter", lambda: Boom())
    with pytest.raises(TimeoutError):
        await collect()


async def test_key_gated_adapters_need_no_network():
    ok, hint = await GroqAdapter("", "http://x", "m").check_available()
    assert (ok, hint) == (False, "GROQ_API_KEY not configured (selected provider is groq)")
    assert await AnthropicAdapter("sk-x", "http://x", "m").check_available() == (True, None)


async def test_ollama_unreachable_returns_hint_not_exception():
    ok, hint = await OllamaAdapter("http://127.0.0.1:1", "m").check_available()
    assert ok is False and "ollama serve" in hint


def test_groq_reasoning_quirk_described_once():
    assert GroqAdapter("k", "http://x", "qwen/qwen3-32b").describe() == {
        "reasoning_format": "hidden"}
    assert GroqAdapter("k", "http://x", "llama-3.3-70b-versatile").describe() == {}
