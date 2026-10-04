"""
LLM facade — one seam over the provider adapters.

Owns everything shared: adapter resolution, the telemetry wrapper
(start/done logs, TTFT, chunk counts, error categorisation) and the
<think>-block stream filter. Adapters yield raw deltas; this module
makes them observable. Stream-only: non-streaming paths were deleted
with the non-streaming chat endpoint (same rule — re-add behind this
seam if a caller appears).
"""
import re
import time
from typing import AsyncGenerator, Dict, List, Optional

from app.config import runtime
from app.services.llm.ollama import OllamaAdapter
from app.services.llm.groq import GroqAdapter
from app.services.llm.anthropic import AnthropicAdapter
from app.observability.logger import get_logger

logger = get_logger("lenny.llm")

# ── Think-block filter ────────────────────────────────────────────────────────
_THINK_RE = re.compile(r"<think>.*?</think>\s*", flags=re.S)


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


# ── Adapter resolution ────────────────────────────────────────────────────────
def _active_adapter():
    """Build the active provider adapter from runtime config. One switch, once."""
    provider = runtime.provider
    if provider == "ollama":
        return OllamaAdapter(base_url=runtime.ollama_base_url, model=runtime.model)
    if provider == "anthropic":
        if not runtime.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured (selected provider is anthropic)")
        return AnthropicAdapter(
            api_key=runtime.anthropic_api_key,
            base_url=runtime.anthropic_base_url,
            model=runtime.model,
        )
    if provider == "groq":
        if not runtime.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not configured (selected provider is groq)")
        return GroqAdapter(
            api_key=runtime.groq_api_key,
            base_url=runtime.groq_base_url,
            model=runtime.model,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


# ── Public seam ───────────────────────────────────────────────────────────────
async def check_available() -> tuple[bool, Optional[str]]:
    """Capability query: is the active provider reachable/configured?"""
    try:
        return await _active_adapter().check_available()
    except ValueError as e:
        return False, str(e)


async def stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """Observed token stream with <think> blocks filtered out."""
    adapter = _active_adapter()
    provider, model = adapter.identity
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"{provider} stream start model={model}",
        extra={"event": "llm_stream_start", "provider": provider, "model": model,
               "messages": len(messages), "prompt_chars": prompt_chars,
               **adapter.describe()},
    )
    t0 = time.perf_counter()
    ttft_ms: Optional[int] = None
    chunks = 0
    try:
        async for tok in _filter_think_stream(adapter.stream_tokens(messages)):
            if tok:
                if ttft_ms is None:
                    ttft_ms = int((time.perf_counter() - t0) * 1000)
                chunks += 1
                yield tok
    except Exception as exc:
        cat = _categorise_error(exc, provider, model)
        logger.error(
            f"{provider} stream failed: {cat['error_code']}",
            extra={"event": "llm_stream_error", "provider": provider, "model": model,
                   "duration_ms": int((time.perf_counter() - t0) * 1000), **cat},
            exc_info=True,
        )
        raise
    logger.info(
        f"{provider} stream done model={model}",
        extra={
            "event": "llm_stream_done", "provider": provider, "model": model,
            "ttft_ms": ttft_ms, "chunks": chunks,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
