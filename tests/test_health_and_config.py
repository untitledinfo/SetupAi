"""Tests that don't require the actual model weights to be downloaded —
they exercise config loading and the unauthenticated health endpoints
only. Full generation-path tests belong in a separate, GPU-tagged test
module (not included here — needs real weights to be meaningful).
"""

import os

from fastapi.testclient import TestClient

from firewing.config.settings import load_settings, Settings
from firewing.api.server import create_app


def test_default_settings_load():
    settings = load_settings(config_path="/nonexistent/path.yaml")
    assert isinstance(settings, Settings)
    assert settings.api.port == 8000
    assert settings.model.model_path == "Qwen/Qwen3-Omni-30B-A3B-Instruct"


def test_env_override(monkeypatch):
    monkeypatch.setenv("FIREWING_API_PORT", "9999")
    settings = load_settings(config_path="/nonexistent/path.yaml")
    assert settings.api.port == 9999


def test_health_endpoint():
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_models_endpoint_lists_firewing():
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["data"]]
    assert "firewing-1.0-beta" in ids


def test_chat_completions_requires_auth_when_keys_set(monkeypatch):
    monkeypatch.setenv("FIREWING_API_KEYS", "test-key-123")
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)
    resp = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401
