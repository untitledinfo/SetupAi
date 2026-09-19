import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from firewing.api.security.key_store import KeyStore
from firewing.api.server import create_app


def test_key_store_create_and_validate():
    with tempfile.TemporaryDirectory() as tmp:
        store = KeyStore(Path(tmp) / "keys.json")
        plaintext, record = store.create_key("test")
        assert store.is_valid(plaintext)
        assert not store.is_valid("wrong-key")
        assert record.label == "test"


def test_key_store_revoke():
    with tempfile.TemporaryDirectory() as tmp:
        store = KeyStore(Path(tmp) / "keys.json")
        plaintext, record = store.create_key("test")
        assert store.is_valid(plaintext)
        assert store.revoke_key(record.key_id)
        assert not store.is_valid(plaintext)


def test_key_store_persists_across_instances():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store1 = KeyStore(path)
        plaintext, _ = store1.create_key("test")

        store2 = KeyStore(path)
        assert store2.is_valid(plaintext)


def test_admin_routes_disabled_without_admin_key(monkeypatch):
    monkeypatch.delenv("FIREWING_ADMIN_KEY", raising=False)
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)
    resp = client.get("/v1/admin/stats", headers={"Authorization": "Bearer whatever"})
    assert resp.status_code == 503


def test_admin_routes_require_correct_admin_key(monkeypatch):
    monkeypatch.setenv("FIREWING_ADMIN_KEY", "correct-admin-key")
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)

    resp = client.get("/v1/admin/stats", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401

    resp = client.get("/v1/admin/stats", headers={"Authorization": "Bearer correct-admin-key"})
    assert resp.status_code == 200
    assert "uptime_seconds" in resp.json()


def test_admin_create_and_list_and_revoke_key(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREWING_ADMIN_KEY", "correct-admin-key")
    monkeypatch.setenv("FIREWING_DATA_DIR", str(tmp_path))
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer correct-admin-key"}

    resp = client.post("/v1/admin/keys", json={"label": "test-key"}, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" in body
    key_id = body["key_id"]

    resp = client.get("/v1/admin/keys", headers=admin_headers)
    labels = [k["label"] for k in resp.json()["keys"]]
    assert "test-key" in labels

    resp = client.delete(f"/v1/admin/keys/{key_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


def test_new_key_from_store_works_for_chat_auth(monkeypatch, tmp_path):
    monkeypatch.delenv("FIREWING_API_KEYS", raising=False)
    monkeypatch.setenv("FIREWING_ADMIN_KEY", "correct-admin-key")
    monkeypatch.setenv("FIREWING_DATA_DIR", str(tmp_path))
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=True)
    client = TestClient(app)

    resp = client.post(
        "/v1/admin/keys",
        json={"label": "chat-user"},
        headers={"Authorization": "Bearer correct-admin-key"},
    )
    new_key = resp.json()["api_key"]

    # Model isn't loaded (lazy_load_model=True), so we expect 503 (auth
    # passed, engine unavailable) rather than 401 (auth failed).
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {new_key}"},
    )
    assert resp.status_code == 503
