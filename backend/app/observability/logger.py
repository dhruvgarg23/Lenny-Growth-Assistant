"""
Structured observability layer.

Provides:
  - configure_logging()  — call once at startup; JSON in prod, pretty in dev.
  - get_logger(name)     — returns a bound Logger that emits structured events.
  - Context helpers      — bind request_id / session_id into every log record for the
                           duration of a coroutine without thread-safety issues.

Design notes:
  - Uses stdlib logging + python-json-logger (already in requirements) so no new deps.
  - contextvars instead of thread-locals → safe in asyncio.
  - A ContextFilter injects context vars into every LogRecord so all existing
    logger.info() calls pick up request_id automatically.
"""

import json
import logging
import time
from contextvars import ContextVar
from typing import Any

# ── Context variable bag ──────────────────────────────────────────────────────
# Each key stored individually for easy partial overwrite.
_ctx_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_ctx_session_id: ContextVar[str] = ContextVar("session_id", default="-")
_ctx_provider: ContextVar[str] = ContextVar("provider", default="-")
_ctx_model: ContextVar[str] = ContextVar("model", default="-")


def bind(**kwargs: str) -> dict[str, Any]:
    """Bind context vars for the current coroutine. Returns tokens for reset."""
    tokens: dict[str, Any] = {}
    mapping = {
        "request_id": _ctx_request_id,
        "session_id": _ctx_session_id,
        "provider": _ctx_provider,
        "model": _ctx_model,
    }
    for k, v in kwargs.items():
        if k in mapping:
            tokens[k] = mapping[k].set(v)
    return tokens


def unbind(tokens: dict[str, Any]) -> None:
    """Reset context vars to previous values."""
    mapping = {
        "request_id": _ctx_request_id,
        "session_id": _ctx_session_id,
        "provider": _ctx_provider,
        "model": _ctx_model,
    }
    for k, tok in tokens.items():
        if k in mapping:
            mapping[k].reset(tok)


def get_context() -> dict[str, str]:
    return {
        "request_id": _ctx_request_id.get(),
        "session_id": _ctx_session_id.get(),
        "provider": _ctx_provider.get(),
        "model": _ctx_model.get(),
    }


# ── Filter that injects context vars into every LogRecord ────────────────────
class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _ctx_request_id.get()
        record.session_id = _ctx_session_id.get()
        record.provider = _ctx_provider.get()
        record.model = _ctx_model.get()
        return True


# ── JSON formatter (structlog-style, stdlib-based) ───────────────────────────
class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line with canonical fields."""

    LEVEL_MAP = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        doc: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": self.LEVEL_MAP.get(record.levelno, record.levelname),
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "session_id": getattr(record, "session_id", "-"),
            "provider": getattr(record, "provider", "-"),
            "model": getattr(record, "model", "-"),
        }
        # Merge any extra= kwargs passed to the log call
        for key, val in record.__dict__.items():
            if key not in (
                "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "name", "message",
                "request_id", "session_id", "provider", "model", "asctime",
            ) and not key.startswith("_"):
                doc[key] = val
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str, ensure_ascii=False)


# ── Pretty formatter for local dev ───────────────────────────────────────────
class _PrettyFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m",
        "WARNING": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        lvl = record.levelname
        color = self.COLORS.get(lvl, "")
        rid = getattr(record, "request_id", "-")
        sid = getattr(record, "session_id", "-")
        ctx = f"[rid={rid} sid={sid}]" if rid != "-" or sid != "-" else ""
        base = f"{color}{lvl:8s}{self.RESET} {record.name:30s} {ctx} {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Public: configure once at startup ────────────────────────────────────────
def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """
    Call once in app lifespan.
    json_logs=True  → machine-readable JSON (used in Docker / prod).
    json_logs=False → human-readable colorized output (dev).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any handlers added by basicConfig earlier
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JsonFormatter() if json_logs else _PrettyFormatter())
    root.addHandler(handler)

    # Quiet noisy libraries
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib logger; context fields are injected by the filter."""
    return logging.getLogger(name)


# ── Timing helper ─────────────────────────────────────────────────────────────
class Timer:
    """Context manager that measures elapsed wall time."""
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        pass
