"""Groq provider adapter — cloud models over an OpenAI-compatible API.

Constructed with explicit credentials; reads no globals.
"""
from typing import AsyncGenerator, Dict, List


def _needs_reasoning_hidden(model: str) -> bool:
    return "qwen" in model.lower()


class GroqAdapter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._extra_body = {"reasoning_format": "hidden"} if _needs_reasoning_hidden(model) else None

    @property
    def identity(self) -> tuple[str, str]:
        return "groq", self._model

    def describe(self) -> dict:
        return {"reasoning_format": "hidden"} if self._extra_body else {}

    async def check_available(self) -> tuple[bool, str | None]:
        ok = bool(self._api_key)
        return ok, None if ok else "GROQ_API_KEY not configured (selected provider is groq)"

    async def stream_tokens(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        s = await client.chat.completions.create(
            model=self._model, messages=messages, temperature=0.2,
            max_completion_tokens=4096, stream=True,
            extra_body=self._extra_body,
        )
        async for chunk in s:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
