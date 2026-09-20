from fastapi.testclient import TestClient

from firewing.api.server import create_app
from firewing.inference.tools import extract_tool_calls, build_default_registry, ToolCall


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREWING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIREWING_API_KEYS", "test-key")
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    return TestClient(app)


def test_create_list_get_delete_conversation(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}

    resp = client.post("/v1/conversations", json={"title": "My chat"}, headers=headers)
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]

    resp = client.get("/v1/conversations", headers=headers)
    titles = [c["title"] for c in resp.json()["conversations"]]
    assert "My chat" in titles

    resp = client.get(f"/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["messages"] == []

    resp = client.delete(f"/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 200

    resp = client.get(f"/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 404


def test_get_unknown_conversation_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}
    resp = client.get("/v1/conversations/does-not-exist", headers=headers)
    assert resp.status_code == 404


def test_add_message_503_when_model_not_loaded(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}

    resp = client.post("/v1/conversations", json={"title": "Test"}, headers=headers)
    conv_id = resp.json()["conversation_id"]

    resp = client.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"message": {"role": "user", "content": "hi"}},
        headers=headers,
    )
    # Model isn't loaded (lazy_load_model=True) — engine is None.
    assert resp.status_code == 503


def test_tools_plus_stream_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}

    resp = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "get_weather", "description": "", "parameters": {}},
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "tools" in resp.json()["detail"].lower()


def test_multimodal_content_schema_accepted(monkeypatch, tmp_path):
    """Multimodal content parts should validate through the schema even
    though we can't exercise actual image decoding without a loaded
    model — this confirms the request shape itself is accepted.
    """
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}

    resp = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What's in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
                    ],
                }
            ],
        },
        headers=headers,
    )
    # Schema validation passes; fails later at 503 (no model loaded),
    # not 422 (which would mean the multimodal shape was rejected).
    assert resp.status_code == 503


def test_tool_role_message_requires_tool_call_id(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": "Bearer test-key"}

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "tool", "content": "result"}]},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "tool_call_id" in resp.json()["detail"]


def test_extract_tool_calls_multiple():
    text = (
        "<tool_call>\n"
        '{"name": "a", "arguments": {"x": 1}}\n'
        "</tool_call>\n"
        "<tool_call>\n"
        '{"name": "b", "arguments": {}}\n'
        "</tool_call>"
    )
    remaining, calls = extract_tool_calls(text)
    assert remaining == ""
    assert [c.name for c in calls] == ["a", "b"]


def test_tool_registry_schemas_are_openai_shaped():
    registry = build_default_registry()
    schemas = registry.schemas()
    assert all(s["type"] == "function" for s in schemas)
    names = {s["function"]["name"] for s in schemas}
    assert "calculator" in names
    assert "get_current_time" in names
