import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "service" in r.json()

def test_health_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert "status" in j
    assert "provider" in j
    assert "db_ok" in j
    assert j["provider"]["selected"] in ("ollama","groq")

def test_config_endpoint():
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert "retrieval" in j
    assert "provider" in j
    assert "runtime" in j
    assert j["retrieval"]["retrieval_k"] == 8

def test_switch_model_endpoint(monkeypatch):
    # Hermetic: declare the allowlist + key the switch needs instead of
    # depending on the developer's local .env.
    from app.config import runtime as rt
    monkeypatch.setattr(rt._settings, "groq_models",
                        "llama-3.3-70b-versatile,qwen/qwen3-32b")
    monkeypatch.setattr(rt._settings, "groq_api_key", "test-key")
    # Switch to groq / qwen (reasoning model served via Groq)
    r = client.put("/api/config/model", json={"provider": "groq", "model": "qwen/qwen3-32b"})
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "groq"
    assert j["model"] == "qwen/qwen3-32b"

    # Switch to ollama
    r = client.put("/api/config/model", json={"provider": "ollama", "model": "llama3.1:8b"})
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "ollama"
    assert j["model"] == "llama3.1:8b"

    # Reset back to default
    r = client.put("/api/config/model", json={"provider": "groq", "model": "llama-3.3-70b-versatile"})
    assert r.status_code == 200

def test_switch_model_validation():
    # Invalid provider
    r = client.put("/api/config/model", json={"provider": "invalid_provider", "model": "any"})
    assert r.status_code == 400

    # Model not in allowed list
    r = client.put("/api/config/model", json={"provider": "groq", "model": "unsupported-model-xyz"})
    assert r.status_code == 400

