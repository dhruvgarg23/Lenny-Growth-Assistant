import json
import logging
from fastapi.testclient import TestClient
from app.main import app
from app.observability.logger import (
    bind, unbind, get_context, Timer, _JsonFormatter, _ContextFilter
)
from app.services.llm import _categorise_error

client = TestClient(app)

def test_context_binding():
    tokens = bind(request_id="req-12345", session_id="sess-abc", provider="groq", model="llama-3.3-70b-versatile")
    ctx = get_context()
    assert ctx["request_id"] == "req-12345"
    assert ctx["session_id"] == "sess-abc"
    assert ctx["provider"] == "groq"
    assert ctx["model"] == "llama-3.3-70b-versatile"
    
    unbind(tokens)
    ctx_after = get_context()
    assert ctx_after["request_id"] == "-"
    assert ctx_after["session_id"] == "-"

def test_timer_elapsed():
    with Timer() as t:
        assert t.elapsed_ms >= 0
    assert t.elapsed_ms >= 0

def test_json_formatter_structure():
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-999"
    record.session_id = "sess-888"
    record.provider = "ollama"
    record.model = "llama3.1:8b"
    record.event = "custom_event"
    record.duration_ms = 42

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["msg"] == "Test message"
    assert data["request_id"] == "req-999"
    assert data["session_id"] == "sess-888"
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3.1:8b"
    assert data["event"] == "custom_event"
    assert data["duration_ms"] == 42
    assert "ts" in data

def test_error_categorisation():
    err_413 = Exception("Error code: 413 - tokens limit exceeded")
    cat = _categorise_error(err_413, "groq", "qwen/qwen3.6-27b")
    assert cat["error_code"] == "TOKEN_LIMIT"
    assert "token limit" in cat["hint"].lower()

    err_429 = Exception("Rate limit reached for requests per minute (429)")
    cat = _categorise_error(err_429, "groq", "llama-3.3-70b-versatile")
    assert cat["error_code"] == "RATE_LIMIT"

    err_timeout = Exception("Request timed out after 30s")
    cat = _categorise_error(err_timeout, "ollama", "llama3.1:8b")
    assert cat["error_code"] == "TIMEOUT"

    err_conn = Exception("Connection refused by host")
    cat = _categorise_error(err_conn, "ollama", "llama3.1:8b")
    assert cat["error_code"] == "CONNECTION_REFUSED"

def test_diagnostics_endpoint():
    r = client.get("/api/diagnostics")
    assert r.status_code == 200
    j = r.json()
    assert "status" in j
    assert "runtime" in j
    assert "diagnostics" in j
    diag = j["diagnostics"]
    assert "database" in diag
    assert "ollama" in diag
    assert "groq" in diag
    assert "total_probe_duration_ms" in diag

def test_health_includes_latency():
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert "db_latency_ms" in j
    assert "runtime" in j
