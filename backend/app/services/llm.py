"""
LLM provider abstraction — Pi wrapper that can call Ollama, Anthropic, or OpenAI
without changing application code. Single entry: generate() + stream().
"""
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Optional
from app.config import settings

logger = logging.getLogger("lenny.llm")

# ── Ollama HTTP helpers ──
async def _ollama_chat(messages: List[Dict[str, str]], stream: bool = False) -> str:
    """Non-streaming Ollama chat."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        j = r.json()
        return j.get("message", {}).get("content", "") or j.get("response", "")

async def _ollama_chat_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                import json
                try:
                    j = json.loads(line)
                    # Ollama streaming: {"message":{"content":"..."},"done":false}
                    delta = j.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if j.get("done"):
                        break
                except Exception:
                    continue

async def ollama_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            return r.status_code == 200
    except Exception:
        return False

# ── Anthropic helpers ──
async def _anthropic_chat(messages: List[Dict[str, str]]) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    # Split system
    system = None
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            msgs.append(m)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        temperature=0.2,
        system=system or "",
        messages=msgs,
    )
    return "".join(b.text for b in resp.content if b.type == "text")

async def _anthropic_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    system = None
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            msgs.append(m)
    async with client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=2048,
        temperature=0.2,
        system=system or "",
        messages=msgs,
    ) as stream:
        async for text in stream.text_stream:
            yield text

# ── OpenAI helpers ──
async def _openai_chat(messages: List[Dict[str, str]]) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    r = await client.chat.completions.create(
        model=settings.openai_model, messages=messages, temperature=0.2, max_tokens=2048
    )
    return r.choices[0].message.content or ""

async def _openai_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    s = await client.chat.completions.create(
        model=settings.openai_model, messages=messages, temperature=0.2, max_tokens=2048, stream=True
    )
    async for chunk in s:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

# ── OpenRouter helpers (OpenAI-compatible) ──
def _openrouter_client():
    from openai import AsyncOpenAI
    kwargs = {
        "api_key": settings.openrouter_api_key,
        "base_url": settings.openrouter_base_url,
    }
    headers = {}
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_app_title:
        headers["X-Title"] = settings.openrouter_app_title
    if headers:
        kwargs["default_headers"] = headers
    return AsyncOpenAI(**kwargs)

async def _openrouter_chat(messages: List[Dict[str, str]]) -> str:
    client = _openrouter_client()
    r = await client.chat.completions.create(
        model=settings.openrouter_model, messages=messages, temperature=0.2, max_tokens=2048
    )
    return r.choices[0].message.content or ""

async def _openrouter_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    client = _openrouter_client()
    s = await client.chat.completions.create(
        model=settings.openrouter_model, messages=messages, temperature=0.2, max_tokens=2048, stream=True
    )
    async for chunk in s:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

# ── Public facade ──
async def generate(messages: List[Dict[str, str]]) -> str:
    provider = settings.llm_provider
    if provider == "ollama":
        return await _ollama_chat(messages)
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured (selected provider is anthropic)")
        return await _anthropic_chat(messages)
    elif provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        return await _openai_chat(messages)
    elif provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured (selected provider is openrouter)")
        return await _openrouter_chat(messages)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

async def stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    provider = settings.llm_provider
    if provider == "ollama":
        async for tok in _ollama_chat_stream(messages):
            yield tok
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        async for tok in _anthropic_stream(messages):
            yield tok
    elif provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        async for tok in _openai_stream(messages):
            yield tok
    elif provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")
        async for tok in _openrouter_stream(messages):
            yield tok
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")

# Pi-style descriptor for UI / health
def provider_info() -> dict:
    base = settings.provider_status()
    # keep keys stable for frontend
    return base
