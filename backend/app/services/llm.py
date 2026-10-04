"""
LLM provider abstraction — Ollama (local) or Groq (cloud).
Single entry: generate() + stream().
Toggle via LLM_PROVIDER=ollama|groq in .env / RuntimeConfig.

Observability additions:
  - Structured log on every model call: provider, model, prompt chars, params.
  - For streaming: time-to-first-token (TTFT), chunk count, total duration.
  - <think>-block suppression count logged per stream.
  - Upstream error categorisation: 413 (token limit), 429 (rate limit),
    504/timeout, connection refused → actionable log messages.
"""
import logging
import re
import time
import httpx
from typing import AsyncGenerator, List, Dict, Optional

from app.config import settings, runtime
from app.observability.logger import get_logger, Timer

logger = get_logger("lenny.llm")

# ── Think-block filter ────────────────────────────────────────────────────────
_THINK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.S)


def _strip_think(text: str) -> str:
    """Remove <think>…</think> blocks from completed text."""
    cleaned = _THINK_RE.sub("", text).strip()
    if cleaned != text:
        logger.debug("think_block_stripped", extra={"event": "think_strip", "chars_removed": len(text) - len(cleaned)})
    return cleaned


async def _filter_think_stream(
    raw: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Suppress <think>…</think> from a token stream. Logs suppression stats."""
    inside_think = False
    buf = ""
    suppressed_chars = 0
    async for tok in raw:
        buf += tok
        while buf:
            if inside_think:
                end = buf.find("</think>")
                if end != -1:
                    suppressed_chars += end
                    buf = buf[end + len("</think>"):]
                    inside_think = False
                    buf = buf.lstrip()
                else:
                    if len(buf) > 8:
                        suppressed_chars += len(buf) - 8
                        buf = buf[-8:]
                    break
            else:
                start = buf.find("<think>")
                if start != -1:
                    before = buf[:start]
                    if before:
                        yield before
                    buf = buf[start + len("<think>"):]
                    inside_think = True
                else:
                    safe = len(buf) - 7
                    if safe > 0:
                        yield buf[:safe]
                        buf = buf[safe:]
                    break
    if buf and not inside_think:
        yield buf
    if suppressed_chars:
        logger.debug(
            "think_stream_filtered",
            extra={"event": "think_stream_filter", "suppressed_chars": suppressed_chars},
        )


# ── Error categorisation ──────────────────────────────────────────────────────
def _categorise_error(exc: Exception, provider: str, model: str) -> dict:
    """Return a structured dict with error_code and hint for any upstream error."""
    msg = str(exc)
    if "413" in msg or "tokens" in msg.lower():
        return {
            "error_code": "TOKEN_LIMIT",
            "hint": f"Prompt+output exceeded token limit for {model}. Reduce max_completion_tokens or shorten context.",
        }
    if "429" in msg or "rate_limit" in msg.lower():
        return {
            "error_code": "RATE_LIMIT",
            "hint": f"Rate limit hit on {provider}/{model}. Retry after cooldown or switch to a lower-quota model.",
        }
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return {
            "error_code": "TIMEOUT",
            "hint": f"Request to {provider} timed out. Check network / increase timeout.",
        }
    if "connection" in msg.lower() or "refused" in msg.lower():
        return {
            "error_code": "CONNECTION_REFUSED",
            "hint": f"Cannot reach {provider}. For Ollama: run `ollama serve`. For cloud providers: check base URL and internet connection.",
        }
    if "401" in msg or "api_key" in msg.lower() or "authentication" in msg.lower():
        return {
            "error_code": "AUTH_FAILURE",
            "hint": f"API key missing or invalid. Set {provider.upper()}_API_KEY in .env and restart.",
        }
    return {"error_code": "UPSTREAM_ERROR", "hint": msg[:200]}


# ── Ollama helpers ────────────────────────────────────────────────────────────
async def _ollama_chat(messages: List[Dict[str, str]], model: str) -> str:
    url = f"{runtime.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"ollama generate start model={model}",
        extra={
            "event": "llm_call_start",
            "provider": "ollama", "model": model,
            "messages": len(messages), "prompt_chars": prompt_chars,
        },
    )
    with Timer() as t:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                j = r.json()
                text = j.get("message", {}).get("content", "") or j.get("response", "")
        except Exception as exc:
            cat = _categorise_error(exc, "ollama", model)
            logger.error(
                f"ollama generate failed: {cat['error_code']}",
                extra={"event": "llm_call_error", "provider": "ollama", "model": model,
                       "duration_ms": t.elapsed_ms, **cat},
                exc_info=True,
            )
            raise
    logger.info(
        f"ollama generate done model={model}",
        extra={
            "event": "llm_call_done", "provider": "ollama", "model": model,
            "duration_ms": t.elapsed_ms, "response_chars": len(text),
        },
    )
    return text


async def _ollama_chat_stream(
    messages: List[Dict[str, str]], model: str
) -> AsyncGenerator[str, None]:
    import json as _json

    url = f"{runtime.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model, "messages": messages, "stream": True,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"ollama stream start model={model}",
        extra={"event": "llm_stream_start", "provider": "ollama", "model": model,
               "messages": len(messages), "prompt_chars": prompt_chars},
    )
    t0 = time.perf_counter()
    ttft_ms: Optional[int] = None
    chunks = 0
    try:
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
                            if ttft_ms is None:
                                ttft_ms = int((time.perf_counter() - t0) * 1000)
                            chunks += 1
                            yield delta
                        if j.get("done"):
                            break
                    except Exception:
                        continue
    except Exception as exc:
        cat = _categorise_error(exc, "ollama", model)
        logger.error(
            f"ollama stream failed: {cat['error_code']}",
            extra={"event": "llm_stream_error", "provider": "ollama", "model": model,
                   "duration_ms": int((time.perf_counter() - t0) * 1000), **cat},
            exc_info=True,
        )
        raise
    logger.info(
        f"ollama stream done model={model}",
        extra={
            "event": "llm_stream_done", "provider": "ollama", "model": model,
            "ttft_ms": ttft_ms, "chunks": chunks,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )


async def ollama_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{runtime.ollama_base_url.rstrip('/')}/api/tags")
            ok = r.status_code == 200
            if not ok:
                logger.warning("ollama_health_fail", extra={"event": "ollama_health", "status": r.status_code})
            return ok
    except Exception as exc:
        logger.warning(f"ollama_health_error: {exc}", extra={"event": "ollama_health", "error": str(exc)})
        return False


# ── Groq helpers ──────────────────────────────────────────────────────────────
def _groq_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=runtime.groq_api_key, base_url=runtime.groq_base_url)


def _needs_reasoning_hidden(model: str) -> bool:
    return "qwen" in model.lower()


async def _groq_chat(messages: List[Dict[str, str]], model: str) -> str:
    extra_body = {"reasoning_format": "hidden"} if _needs_reasoning_hidden(model) else None
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"groq generate start model={model}",
        extra={
            "event": "llm_call_start", "provider": "groq", "model": model,
            "messages": len(messages), "prompt_chars": prompt_chars,
            "max_completion_tokens": 4096,
            "reasoning_format": "hidden" if extra_body else "none",
        },
    )
    with Timer() as t:
        try:
            client = _groq_client()
            r = await client.chat.completions.create(
                model=model, messages=messages, temperature=0.2,
                max_completion_tokens=4096,
                extra_body=extra_body,
            )
            text = r.choices[0].message.content or ""
        except Exception as exc:
            cat = _categorise_error(exc, "groq", model)
            logger.error(
                f"groq generate failed: {cat['error_code']}",
                extra={"event": "llm_call_error", "provider": "groq", "model": model,
                       "duration_ms": t.elapsed_ms, **cat},
                exc_info=True,
            )
            raise
    logger.info(
        f"groq generate done model={model}",
        extra={
            "event": "llm_call_done", "provider": "groq", "model": model,
            "duration_ms": t.elapsed_ms, "response_chars": len(text),
        },
    )
    return text


async def _groq_stream(messages: List[Dict[str, str]], model: str) -> AsyncGenerator[str, None]:
    extra_body = {"reasoning_format": "hidden"} if _needs_reasoning_hidden(model) else None
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"groq stream start model={model}",
        extra={
            "event": "llm_stream_start", "provider": "groq", "model": model,
            "messages": len(messages), "prompt_chars": prompt_chars,
            "reasoning_format": "hidden" if extra_body else "none",
        },
    )
    t0 = time.perf_counter()
    ttft_ms: Optional[int] = None
    chunks = 0
    try:
        client = _groq_client()
        s = await client.chat.completions.create(
            model=model, messages=messages, temperature=0.2,
            max_completion_tokens=4096, stream=True,
            extra_body=extra_body,
        )
        async for chunk in s:
            delta = chunk.choices[0].delta.content
            if delta:
                if ttft_ms is None:
                    ttft_ms = int((time.perf_counter() - t0) * 1000)
                chunks += 1
                yield delta
    except Exception as exc:
        cat = _categorise_error(exc, "groq", model)
        logger.error(
            f"groq stream failed: {cat['error_code']}",
            extra={"event": "llm_stream_error", "provider": "groq", "model": model,
                   "duration_ms": int((time.perf_counter() - t0) * 1000), **cat},
            exc_info=True,
        )
        raise
    logger.info(
        f"groq stream done model={model}",
        extra={
            "event": "llm_stream_done", "provider": "groq", "model": model,
            "ttft_ms": ttft_ms, "chunks": chunks,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )


# ── Anthropic Claude helpers ──────────────────────────────────────────────────
def _anthropic_client():
    from anthropic import AsyncAnthropic
    return AsyncAnthropic(api_key=runtime.anthropic_api_key, base_url=runtime.anthropic_base_url)


def _prepare_anthropic_payload(messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
    systems = []
    convo = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            systems.append(content)
        elif role in ("user", "assistant"):
            if convo and convo[-1]["role"] == role:
                convo[-1]["content"] += "\n\n" + content
            else:
                convo.append({"role": role, "content": content})
    if not convo:
        convo = [{"role": "user", "content": "Hello"}]
    return "\n\n".join(systems), convo


async def _anthropic_chat(messages: List[Dict[str, str]], model: str) -> str:
    system_prompt, convo = _prepare_anthropic_payload(messages)
    prompt_chars = sum(len(m.get("content", "")) for m in convo) + len(system_prompt)
    logger.info(
        f"anthropic generate start model={model}",
        extra={
            "event": "llm_call_start", "provider": "anthropic", "model": model,
            "messages": len(convo), "prompt_chars": prompt_chars,
            "max_tokens": 4096,
        },
    )
    with Timer() as t:
        try:
            client = _anthropic_client()
            r = await client.messages.create(
                model=model,
                system=system_prompt if system_prompt else None,
                messages=convo,
                temperature=0.2,
                max_tokens=4096,
            )
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text" or hasattr(b, "text"))
        except Exception as exc:
            cat = _categorise_error(exc, "anthropic", model)
            logger.error(
                f"anthropic generate failed: {cat['error_code']}",
                extra={"event": "llm_call_error", "provider": "anthropic", "model": model,
                       "duration_ms": t.elapsed_ms, **cat},
                exc_info=True,
            )
            raise
    logger.info(
        f"anthropic generate done model={model}",
        extra={
            "event": "llm_call_done", "provider": "anthropic", "model": model,
            "duration_ms": t.elapsed_ms, "response_chars": len(text),
        },
    )
    return text


async def _anthropic_stream(messages: List[Dict[str, str]], model: str) -> AsyncGenerator[str, None]:
    system_prompt, convo = _prepare_anthropic_payload(messages)
    prompt_chars = sum(len(m.get("content", "")) for m in convo) + len(system_prompt)
    logger.info(
        f"anthropic stream start model={model}",
        extra={
            "event": "llm_stream_start", "provider": "anthropic", "model": model,
            "messages": len(convo), "prompt_chars": prompt_chars,
        },
    )
    t0 = time.perf_counter()
    ttft_ms: Optional[int] = None
    chunks = 0
    try:
        client = _anthropic_client()
        async with client.messages.stream(
            model=model,
            system=system_prompt if system_prompt else None,
            messages=convo,
            temperature=0.2,
            max_tokens=4096,
        ) as s:
            async for text in s.text_stream:
                if text:
                    if ttft_ms is None:
                        ttft_ms = int((time.perf_counter() - t0) * 1000)
                    chunks += 1
                    yield text
    except Exception as exc:
        cat = _categorise_error(exc, "anthropic", model)
        logger.error(
            f"anthropic stream failed: {cat['error_code']}",
            extra={"event": "llm_stream_error", "provider": "anthropic", "model": model,
                   "duration_ms": int((time.perf_counter() - t0) * 1000), **cat},
            exc_info=True,
        )
        raise
    logger.info(
        f"anthropic stream done model={model}",
        extra={
            "event": "llm_stream_done", "provider": "anthropic", "model": model,
            "ttft_ms": ttft_ms, "chunks": chunks,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )


# ── Availability capability ───────────────────────────────────────────────────
async def check_available() -> tuple[bool, str | None]:
    """Capability query: is the active provider reachable/configured?

    Returns (ok, hint). Lets callers gate work without importing provider
    specifics. Provider knowledge stays in this module.
    """
    provider = runtime.provider
    if provider == "ollama":
        ok = await ollama_health()
        hint = None if ok else (
            "Ollama is not reachable at OLLAMA_BASE_URL. "
            "Start it with: ollama serve && ollama pull llama3.1:8b"
        )
        return ok, hint
    if provider == "anthropic":
        ok = bool(runtime.anthropic_api_key)
        return ok, None if ok else "ANTHROPIC_API_KEY not configured (selected provider is anthropic)"
    if provider == "groq":
        ok = bool(runtime.groq_api_key)
        return ok, None if ok else "GROQ_API_KEY not configured (selected provider is groq)"
    return False, f"Unknown LLM_PROVIDER: {provider}"


# ── Public facade ─────────────────────────────────────────────────────────────
async def generate(messages: List[Dict[str, str]]) -> str:
    provider = runtime.provider
    model = runtime.model
    if provider == "ollama":
        raw = await _ollama_chat(messages, model)
    elif provider == "anthropic":
        if not runtime.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured (selected provider is anthropic)")
        raw = await _anthropic_chat(messages, model)
    elif provider == "groq":
        if not runtime.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not configured (selected provider is groq)")
        raw = await _groq_chat(messages, model)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")
    return _strip_think(raw)


async def _raw_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    provider = runtime.provider
    model = runtime.model
    if provider == "ollama":
        async for tok in _ollama_chat_stream(messages, model):
            yield tok
    elif provider == "anthropic":
        if not runtime.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        async for tok in _anthropic_stream(messages, model):
            yield tok
    elif provider == "groq":
        if not runtime.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not configured")
        async for tok in _groq_stream(messages, model):
            yield tok
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


async def stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """Token stream with <think> blocks filtered out."""
    async for tok in _filter_think_stream(_raw_stream(messages)):
        yield tok


def provider_info() -> dict:
    """Current runtime provider status for UI / health."""
    return runtime.status()
