import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from firewing.api.server import create_app
from firewing.api.security.key_store import KeyStore
from firewing.api.security.rate_limit import RateLimiter
from firewing.inference.conversation_store import ConversationStore
from firewing.inference.personas import load_personas
from firewing.utils.stats import StatsTracker


def _create_test_app(monkeypatch, tmp_path, lazy=True):
    monkeypatch.setenv("FIREWING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIREWING_API_KEYS", "test-secret-key")
    monkeypatch.setenv("FIREWING_ADMIN_KEY", "admin-secret-key")
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=lazy)
    return app


def test_ready_endpoint(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)

    # When engine is None, ready endpoint should return 503
    resp = client.get("/ready")
    assert resp.status_code == 503

    # When fake engine is set, ready endpoint should return 200
    app.state.engine = MagicMock()
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


def test_personas_endpoints(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)

    resp = client.get("/v1/personas")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["personas"]]
    assert "default" in names
    assert "coding" in names

    resp = client.get("/v1/personas/coding")
    assert resp.status_code == 200
    assert resp.json()["name"] == "coding"
    assert "software engineer" in resp.json()["system_prompt"]


def test_embeddings_endpoint(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}

    # Single string input
    resp = client.post("/v1/embeddings", json={"input": "Hello world"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["object"] == "embedding"
    assert len(data["data"][0]["embedding"]) > 0

    # Multiple string input
    resp = client.post(
        "/v1/embeddings",
        json={"input": ["First sentence", "Second sentence"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


def test_conversation_crud_and_patch(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}

    # Create with persona
    resp = client.post(
        "/v1/conversations",
        json={"title": "Original Title", "persona": "coding"},
        headers=headers,
    )
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]
    assert resp.json()["persona"] == "coding"

    # Update conversation title and persona via PATCH
    resp = client.patch(
        f"/v1/conversations/{conv_id}",
        json={"title": "Updated Title", "persona": "creative"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"
    assert resp.json()["persona"] == "creative"

    # Export markdown
    resp = client.get(f"/v1/conversations/{conv_id}/export?format=markdown", headers=headers)
    assert resp.status_code == 200
    assert "Updated Title" in resp.text

    # Export JSON
    resp = client.get(f"/v1/conversations/{conv_id}/export?format=json", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == conv_id

    # Clear messages
    resp = client.post(f"/v1/conversations/{conv_id}/clear", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True


def test_conversation_streaming(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)

    # Mock engine stream
    mock_engine = MagicMock()
    mock_engine.stream.return_value = iter(["Hello", " from", " stream"])
    app.state.engine = mock_engine

    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}

    # Create conv
    c_resp = client.post("/v1/conversations", json={"title": "Stream Conv"}, headers=headers)
    conv_id = c_resp.json()["conversation_id"]

    # Post message with stream=True
    resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"message": {"role": "user", "content": "Tell me a joke"}, "stream": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data: " in body
    assert "[DONE]" in body

    # Verify message was saved to store
    store = app.state.conversation_store
    rec = store.get(conv_id)
    assert len(rec.messages) == 2
    assert rec.messages[0].role == "user"
    assert rec.messages[1].role == "assistant"
    assert rec.messages[1].content == "Hello from stream"


def test_chat_streaming_openai_format(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    mock_engine = MagicMock()
    mock_engine.stream.return_value = iter(["Hi", "!"])
    app.state.engine = mock_engine

    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret-key"}

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        headers=headers,
    )
    assert resp.status_code == 200
    lines = [line for line in resp.text.split("\n\n") if line.startswith("data: ")]
    assert len(lines) >= 3  # init + 2 tokens + final + DONE

    # Parse first token line
    first_data = json.loads(lines[1].removeprefix("data: "))
    assert first_data["object"] == "chat.completion.chunk"
    assert first_data["choices"][0]["delta"]["content"] == "Hi"


def test_admin_permanent_delete_and_patch(monkeypatch, tmp_path):
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer admin-secret-key"}

    # Create key
    resp = client.post("/v1/admin/keys", json={"label": "to-delete"}, headers=admin_headers)
    key_id = resp.json()["key_id"]

    # Patch label
    resp = client.patch(f"/v1/admin/keys/{key_id}", json={"label": "renamed-key"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["label"] == "renamed-key"

    # Permanently delete
    resp = client.delete(f"/v1/admin/keys/{key_id}?permanent=true", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Ensure key is no longer in list
    resp = client.get("/v1/admin/keys", headers=admin_headers)
    ids = [k["key_id"] for k in resp.json()["keys"]]
    assert key_id not in ids


def test_rate_limiter_retry_after():
    limiter = RateLimiter(requests_per_minute=2)
    limiter.check("key1")
    limiter.check("key1")

    with pytest.raises(Exception) as excinfo:
        limiter.check("key1")
    assert excinfo.value.status_code == 429
    assert "Retry-After" in excinfo.value.headers


def test_enhanced_stats_tracker():
    tracker = StatsTracker()
    tracker.record(50.0, "success", endpoint="chat", tokens=10)
    tracker.record(150.0, "success", endpoint="chat", tokens=20)
    tracker.record(300.0, "error", endpoint="chat", tokens=0)

    snap = tracker.snapshot()
    assert snap["requests_recorded"] == 3
    assert snap["success_recorded"] == 2
    assert snap["errors_recorded"] == 1
    assert snap["tokens_generated"] == 30
    assert "p50_latency_ms" in snap
    assert "p95_latency_ms" in snap
    assert snap["error_rate_pct"] == 33.33
