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
    assert j["provider"]["selected"] in ("ollama","anthropic","openai")

def test_config_endpoint():
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert "retrieval" in j
    assert "provider" in j
    assert j["retrieval"]["retrieval_k"] == 8
