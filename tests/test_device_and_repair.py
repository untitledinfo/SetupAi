"""Tests for device matching, hardware acceleration detection, and issue auto-repair with data preservation."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from firewing.api.server import create_app
from firewing.inference.conversation_store import ConversationStore
from firewing.utils.system_info import (
    HardwareAccelerator,
    detect_hardware,
    match_device_settings,
)
from setup_ai.cli.main import build_parser, cmd_device, cmd_fix
from setup_ai.system.repair import IssueDetector, IssueRepairer


def _create_test_app(monkeypatch, tmp_path, lazy=True):
    monkeypatch.setenv("FIREWING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIREWING_API_KEYS", "test-secret-key")
    monkeypatch.setenv("FIREWING_ADMIN_KEY", "admin-secret-key")
    app = create_app(config_path="/nonexistent/path.yaml", lazy_load_model=lazy)
    return app


def test_match_device_settings_amd_rocm():
    """Verify optimal settings for an active AMD ROCm GPU (e.g. RX 7900 XTX / MI300)."""
    fake_amd = HardwareAccelerator(
        vendor="amd",
        name="AMD Radeon RX 7900 XTX",
        backend="rocm",
        backend_active=True,
        total_vram_mb=24576,
        free_vram_mb=22000,
        driver_version="24.10.1",
        compute_version="ROCm 6.2.0",
    )
    fake_cpu = HardwareAccelerator(
        vendor="cpu",
        name="CPU (16 cores, 32768 MB RAM)",
        backend="cpu",
        backend_active=True,
        total_vram_mb=32768,
    )

    with patch("firewing.utils.system_info.detect_hardware", return_value=[fake_amd, fake_cpu]):
        result = match_device_settings()
        assert result.status == "matched"
        assert result.recommended_device == "cuda"  # PyTorch uses 'cuda' for ROCm HIP
        assert result.recommended_dtype in ("bfloat16", "float16")
        assert result.recommended_quantization == "int8"
        assert result.mismatch_warning is None


def test_match_device_settings_amd_mismatch():
    """Verify detection when physical AMD GPU is present but PyTorch ROCm is inactive (CPU only)."""
    fake_amd = HardwareAccelerator(
        vendor="amd",
        name="AMD Radeon RX 6800 XT",
        backend="rocm",
        backend_active=False,
        total_vram_mb=16384,
        free_vram_mb=None,
    )
    fake_cpu = HardwareAccelerator(
        vendor="cpu",
        name="CPU",
        backend="cpu",
        backend_active=True,
    )

    with patch("firewing.utils.system_info.detect_hardware", return_value=[fake_amd, fake_cpu]):
        result = match_device_settings()
        assert result.status == "mismatch"
        assert result.recommended_device == "cpu"
        assert result.mismatch_warning is not None
        assert "AMD" in result.mismatch_warning
        assert result.install_hint is not None
        assert "rocm" in result.install_hint.lower() or "directml" in result.install_hint.lower()


def test_match_device_settings_nvidia_cuda():
    """Verify optimal settings for an active NVIDIA CUDA GPU."""
    fake_nvidia = HardwareAccelerator(
        vendor="nvidia",
        name="NVIDIA GeForce RTX 4090",
        backend="cuda",
        backend_active=True,
        total_vram_mb=24576,
        free_vram_mb=23000,
        compute_version="CUDA 12.4",
    )
    fake_cpu = HardwareAccelerator(
        vendor="cpu",
        name="CPU",
        backend="cpu",
        backend_active=True,
    )

    with patch("firewing.utils.system_info.detect_hardware", return_value=[fake_nvidia, fake_cpu]):
        result = match_device_settings()
        assert result.status == "matched"
        assert result.recommended_device == "cuda"
        assert result.recommended_quantization == "int8"


def test_match_device_settings_apple_mps():
    """Verify Apple Silicon MPS acceleration matching."""
    fake_apple = HardwareAccelerator(
        vendor="apple",
        name="Apple Silicon Unified GPU",
        backend="mps",
        backend_active=True,
        total_vram_mb=32768,
        compute_version="Apple Metal MPS",
    )
    fake_cpu = HardwareAccelerator(
        vendor="cpu",
        name="CPU",
        backend="cpu",
        backend_active=True,
    )

    with patch("firewing.utils.system_info.detect_hardware", return_value=[fake_apple, fake_cpu]):
        result = match_device_settings()
        assert result.status == "matched"
        assert result.recommended_device == "mps"
        assert result.recommended_dtype == "float16"


def test_issue_detector_identifies_missing_components(tmp_path):
    """IssueDetector detects missing configuration, uninitialized DB, and empty key store."""
    cfg_file = tmp_path / "missing.yaml"
    data_dir = tmp_path / "data"

    detector = IssueDetector(config_path=str(cfg_file), data_dir=str(data_dir))
    report = detector.diagnose()

    assert report.total_issues > 0
    categories = {issue.category for issue in report.issues}
    assert "config" in categories
    assert "database" in categories
    assert "keys" in categories


def test_issue_repairer_preserves_user_data(tmp_path):
    """IssueRepairer strictly preserves existing conversation history, messages, and API keys."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    cfg_file = tmp_path / "configs" / "firewing.yaml"

    # 1. Populate real user conversations
    db_path = data_dir / "conversations.db"
    store = ConversationStore(str(db_path))
    conv = store.create(title="Important Research", persona="coder")
    store.append_message(conv.conversation_id, "user", "Explain quantum entanglement")
    store.append_message(conv.conversation_id, "assistant", "Quantum entanglement is a physical phenomenon...")

    # 2. Populate real API keys
    key_path = data_dir / "api_keys.json"
    initial_keys = [
        {
            "key_id": "key_abc123",
            "hash": "hash_xyz789",
            "label": "production-client",
            "created_at": 1700000000.0,
            "revoked": False,
            "request_count": 42,
        }
    ]
    with open(key_path, "w", encoding="utf-8") as f:
        json.dump(initial_keys, f)

    # 3. Run auto-repair
    repairer = IssueRepairer(config_path=str(cfg_file), data_dir=str(data_dir))
    rep = repairer.repair(match_device=False, reinstall_packages=False)

    assert rep.success is True
    assert rep.data_preserved is True
    assert rep.backup_path is not None
    assert Path(rep.backup_path).exists()

    # 4. Verify conversation data was 100% preserved
    reloaded_store = ConversationStore(str(db_path))
    reloaded_conv = reloaded_store.get(conv.conversation_id)
    assert reloaded_conv is not None
    assert reloaded_conv.title == "Important Research"
    assert len(reloaded_conv.messages) == 2
    assert reloaded_conv.messages[0].content == "Explain quantum entanglement"
    assert "Quantum entanglement is a physical phenomenon" in reloaded_conv.messages[1].content

    # 5. Verify API keys were 100% preserved
    with open(key_path, "r", encoding="utf-8") as f:
        reloaded_keys = json.load(f)
    assert len(reloaded_keys) == 1
    assert reloaded_keys[0]["key_id"] == "key_abc123"
    assert reloaded_keys[0]["label"] == "production-client"
    assert reloaded_keys[0]["request_count"] == 42


def test_issue_repairer_database_migration(tmp_path):
    """IssueRepairer runs non-destructive SQLite ALTER TABLE to add missing columns without losing rows."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "conversations.db"

    # Create old legacy schema missing 'system_prompt' column
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            persona TEXT
        );
    """)
    conn.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at, persona) VALUES (?, ?, ?, ?, ?);",
        ("conv_legacy_1", "Legacy Chat", 100.0, 200.0, "default"),
    )
    conn.commit()
    conn.close()

    # Repair should migrate the table and add 'system_prompt' column non-destructively
    repairer = IssueRepairer(config_path=str(tmp_path / "configs" / "firewing.yaml"), data_dir=str(data_dir))
    repairer._repair_database([], [])

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(conversations);")
    cols = {col[1] for col in cursor.fetchall()}
    assert "system_prompt" in cols
    assert "persona" in cols

    # Verify existing legacy row is intact
    cursor.execute("SELECT id, title FROM conversations WHERE id='conv_legacy_1';")
    row = cursor.fetchone()
    assert row == ("conv_legacy_1", "Legacy Chat")
    conn.close()


def test_issue_repairer_salvages_corrupted_key_store(tmp_path):
    """IssueRepairer extracts valid key records from broken JSON instead of wiping them out."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    key_path = data_dir / "api_keys.json"

    # Corrupted JSON with a valid record embedded inside
    corrupted_data = """
    <<<CORRUPT_HEADER>>>
    [
      {"key_id": "salvaged_key_1", "hash": "salvaged_hash_1", "label": "rescued_key"},
      {broken json missing close bracket
    """
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(corrupted_data)

    repairer = IssueRepairer(data_dir=str(data_dir))
    repairer._repair_key_store([], [])

    # File should now be valid JSON containing the salvaged record
    with open(key_path, "r", encoding="utf-8") as f:
        keys = json.load(f)
    assert isinstance(keys, list)
    assert len(keys) == 1
    assert keys[0]["key_id"] == "salvaged_key_1"
    assert keys[0]["label"] == "rescued_key"


def test_admin_diagnostics_and_repair_routes(monkeypatch, tmp_path):
    """Test admin API /diagnostics, /repair, and /device endpoints."""
    app = _create_test_app(monkeypatch, tmp_path, lazy=True)
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer admin-secret-key"}

    # 1. GET /v1/admin/diagnostics
    resp = client.get("/v1/admin/diagnostics", headers=admin_headers)
    assert resp.status_code == 200
    diag = resp.json()
    assert "healthy" in diag
    assert "total_issues" in diag
    assert "device_match" in diag

    # 2. GET /v1/admin/device
    resp = client.get("/v1/admin/device", headers=admin_headers)
    assert resp.status_code == 200
    dev = resp.json()
    assert "status" in dev
    assert "primary_accelerator" in dev
    assert "recommended_device" in dev

    # 3. POST /v1/admin/repair
    resp = client.post(
        "/v1/admin/repair",
        json={"match_device": True, "reinstall_packages": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    rep = resp.json()
    assert rep["success"] is True
    assert rep["data_preserved"] is True
    assert "actions_taken" in rep


def test_cli_device_and_fix_commands(capsys):
    """Test CLI parser and execution for `setup-ai device` and `setup-ai fix`."""
    parser = build_parser()

    # Test device command with --json
    args = parser.parse_args(["device", "--json"])
    assert args.command == "device"
    ret = cmd_device(args)
    assert ret == 0
    captured = capsys.readouterr()
    dev_json = json.loads(captured.out)
    assert "status" in dev_json
    assert "primary_accelerator" in dev_json

    # Test fix command with --check-only --json
    args = parser.parse_args(["fix", "--check-only", "--json"])
    assert args.command == "fix"
    ret = cmd_fix(args)
    assert ret in (0, 1)
    captured = capsys.readouterr()
    diag_json = json.loads(captured.out)
    assert "healthy" in diag_json
    assert "issues" in diag_json
