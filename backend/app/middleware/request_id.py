"""
Request-scoped middleware:
  - Assigns / propagates X-Request-ID on every request.
  - Binds request_id into contextvars so all log records in the same coroutine
    carry it automatically.
  - Emits a structured access log on response (method, path, status, duration_ms,
    client_ip).
  - Adds X-Response-Time header.
"""
import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.logger import bind, unbind, get_logger

logger = get_logger("lenny.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        request.state.request_id = request_id

        tokens = bind(request_id=request_id)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            status = getattr(response, "status_code", 0)
            logger.info(
                f"{request.method} {request.url.path} → {status}",
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else "-",
                    "user_agent": request.headers.get("user-agent", "-")[:120],
                },
            )
            unbind(tokens)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response


# Kept for backward-compat (no longer needed but don't break imports)
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True
