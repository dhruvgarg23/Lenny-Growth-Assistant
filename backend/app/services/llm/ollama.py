"""Ollama provider adapter — local models over the Ollama HTTP API.

Constructed with explicit base URL and model; reads no globals.
"""
import httpx
from typing import AsyncGenerator, Dict, List


async def ollama_health(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{base_url.rstrip('/')}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


class OllamaAdapter:
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url
        self._model = model

    @property
    def identity(self) -> tuple[str, str]:
        return "ollama", self._model

    def describe(self) -> dict:
        return {}

    async def check_available(self) -> tuple[bool, str | None]:
        ok = await ollama_health(self._base_url)
        hint = None if ok else (
            "Ollama is not reachable at OLLAMA_BASE_URL. "
            "Start it with: ollama serve && ollama pull llama3.1:8b"
        )
        return ok, hint

    async def stream_tokens(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        import json as _json

        url = f"{self._base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self._model, "messages": messages, "stream": True,
            "options": {"temperature": 0.2, "num_predict": 2048},
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        j = _json.loads(line)
                        delta = j.get("message", {}).get("content", "")
                        if delta:
                            yield delta
                        if j.get("done"):
                            break
                    except Exception:
                        continue
