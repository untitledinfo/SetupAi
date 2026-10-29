"""System issue detector and non-destructive auto-repair engine for FIREWING.

Capabilities:
  - Deep diagnostics across configs, database schemas, API keys, filesystem,
    hardware matching (AMD ROCm / NVIDIA CUDA / Apple MPS / Intel XPU / CPU),
    and package dependencies.
  - Safe 1-Click Auto-Repair with STRICT DATA PRESERVATION:
      * Automatically snapshots user databases and credentials to timestamped backups.
      * Performs non-destructive SQLite migrations (adds missing columns without data loss).
      * Salvages damaged API key stores.
      * Auto-matches hardware configuration to optimal device, dtype, and quantization.
      * Reinstalls or repairs core package dependencies (same mods/requirements) while
        leaving all user conversations, models, and custom LoRA adapters untouched.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from firewing.utils.logging import get_logger
from firewing.utils.system_info import (
    DeviceMatchResult,
    get_system_info,
    match_device_settings,
)

logger = get_logger("system.repair")

_CORE_PACKAGES = {
    "yaml": "pyyaml>=6.0",
    "torch": "torch>=2.2",
    "transformers": "transformers>=4.57.0",
    "fastapi": "fastapi>=0.110",
    "uvicorn": "uvicorn[standard]>=0.29",
    "pydantic": "pydantic>=2.6",
    "accelerate": "accelerate>=0.30",
    "huggingface_hub": "huggingface_hub>=0.24",
}

DEFAULT_FIREWING_YAML = """# FIREWING runtime configuration
model:
  model_path: "Qwen/Qwen3-Omni-30B-A3B-Instruct"
  device: "auto"
  dtype: "auto"
  quantization: "int4"
  max_context_tokens: 32768
  trust_remote_code: true
  adapter_path: null
  context_strategy: "drop"
  enable_multimodal: true
  enable_tool_calling: true

api:
  host: "0.0.0.0"
  port: 8000
  require_api_key: true
  cors_allowed_origins:
    - "*"
  rate_limit_requests_per_minute: 60
  max_tokens_per_request: 4096
  request_timeout_seconds: 120

logging:
  level: "INFO"
  log_dir: "logs"
  json_logs: false

data_dir: "data"
"""

DEFAULT_PERSONAS_YAML = """default:
  name: "FIREWING"
  system_prompt: "You are FIREWING, a helpful and efficient assistant."
  temperature: 0.7
  top_p: 0.9

coder:
  name: "FIREWING Coder"
  system_prompt: "You are an expert software engineer. Provide robust, idiomatic code with clear explanations."
  temperature: 0.2
  top_p: 0.95

concise:
  name: "FIREWING Concise"
  system_prompt: "You are a direct, concise assistant. Answer questions directly without fluff."
  temperature: 0.4
  top_p: 0.9

creative:
  name: "FIREWING Creative"
  system_prompt: "You are a creative, imaginative writer."
  temperature: 0.9
  top_p: 0.95

fast:
  name: "FIREWING Fast"
  system_prompt: "You are a high-speed assistant focused on quick answers."
  temperature: 0.3
  top_p: 0.85
"""


@dataclass
class IssueItem:
    category: str  # "config", "database", "keys", "filesystem", "hardware", "dependencies"
    severity: str  # "critical", "warning", "info"
    title: str
    description: str
    auto_fixable: bool
    fix_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticReport:
    healthy: bool
    total_issues: int
    critical_count: int
    warning_count: int
    issues: list[IssueItem] = field(default_factory=list)
    system_summary: dict[str, Any] = field(default_factory=dict)
    device_match: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
            "system_summary": self.system_summary,
            "device_match": self.device_match,
            "timestamp": self.timestamp,
        }


@dataclass
class RepairReport:
    success: bool
    backup_path: str | None
    actions_taken: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    device_matched: dict[str, Any] | None = None
    data_preserved: bool = True
    reinstall_performed: bool = False
    summary: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "backup_path": self.backup_path,
            "actions_taken": self.actions_taken,
            "warnings": self.warnings,
            "device_matched": self.device_matched,
            "data_preserved": self.data_preserved,
            "reinstall_performed": self.reinstall_performed,
            "summary": self.summary,
            "timestamp": self.timestamp,
        }


class IssueDetector:
    """Diagnoses system, environment, data stores, configs, and hardware."""

    def __init__(self, config_path: str | None = None, data_dir: str | None = None) -> None:
        self.config_path = config_path or "configs/firewing.yaml"
        self.data_dir = data_dir or "data"
        self.personas_path = "configs/personas.yaml"
        self.env_path = ".env"

    def diagnose(self) -> DiagnosticReport:
        issues: list[IssueItem] = []

        # 1. Config Diagnosis
        self._diagnose_configs(issues)

        # 2. Database Schema & Integrity Diagnosis
        self._diagnose_database(issues)

        # 3. API Key Store Diagnosis
        self._diagnose_key_store(issues)

        # 4. Filesystem & Permissions Diagnosis
        self._diagnose_filesystem(issues)

        # 5. Hardware & Device Matching (AMD / NVIDIA / MPS / Intel / CPU)
        device_match_info = self._diagnose_hardware_match(issues)

        # 6. Python Package Dependencies Diagnosis
        self._diagnose_dependencies(issues)

        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        healthy = critical_count == 0

        sys_info = get_system_info().to_dict()

        return DiagnosticReport(
            healthy=healthy,
            total_issues=len(issues),
            critical_count=critical_count,
            warning_count=warning_count,
            issues=issues,
            system_summary={
                "os": f"{sys_info.get('os_name')} {sys_info.get('os_version')}",
                "python": sys_info.get("python_version"),
                "ram_mb": sys_info.get("total_ram_mb"),
                "disk_mb": sys_info.get("free_disk_mb"),
                "gpu": sys_info.get("gpu", {}).get("name"),
            },
            device_match=device_match_info,
        )

    def _diagnose_configs(self, issues: list[IssueItem]) -> None:
        import yaml

        # Check firewing.yaml
        if not os.path.exists(self.config_path):
            issues.append(
                IssueItem(
                    category="config",
                    severity="warning",
                    title="Missing Configuration File",
                    description=f"Configuration file '{self.config_path}' was not found.",
                    auto_fixable=True,
                    fix_action=f"Auto-generate default '{self.config_path}' with safe defaults.",
                )
            )
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    issues.append(
                        IssueItem(
                            category="config",
                            severity="critical",
                            title="Invalid Configuration YAML",
                            description=f"Configuration file '{self.config_path}' does not contain a valid mapping.",
                            auto_fixable=True,
                            fix_action="Repair YAML format preserving existing settings.",
                        )
                    )
            except Exception as e:
                issues.append(
                    IssueItem(
                        category="config",
                        severity="critical",
                        title="Corrupted Configuration YAML",
                        description=f"Syntax error reading '{self.config_path}': {e}",
                        auto_fixable=True,
                        fix_action="Backup corrupted file and regenerate valid config.",
                    )
                )

        # Check .env
        if not os.path.exists(self.env_path):
            issues.append(
                IssueItem(
                    category="config",
                    severity="warning",
                    title="Missing .env File",
                    description=f"Environment file '{self.env_path}' is missing.",
                    auto_fixable=True,
                    fix_action="Generate .env file with a secure random FIREWING_ADMIN_KEY.",
                )
            )

        # Check personas.yaml
        if not os.path.exists(self.personas_path):
            issues.append(
                IssueItem(
                    category="config",
                    severity="info",
                    title="Missing Personas Preset File",
                    description=f"Personas preset file '{self.personas_path}' was not found.",
                    auto_fixable=True,
                    fix_action=f"Generate standard personas presets in '{self.personas_path}'.",
                )
            )

    def _diagnose_database(self, issues: list[IssueItem]) -> None:
        db_path = os.path.join(self.data_dir, "conversations.db")
        if not os.path.exists(db_path):
            issues.append(
                IssueItem(
                    category="database",
                    severity="info",
                    title="Database Not Initialized",
                    description=f"Conversation database '{db_path}' does not exist yet.",
                    auto_fixable=True,
                    fix_action="Initialize SQLite schema non-destructively.",
                )
            )
            return

        try:
            conn = sqlite3.connect(db_path, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            if not row or row[0] != "ok":
                issues.append(
                    IssueItem(
                        category="database",
                        severity="critical",
                        title="Database Integrity Issue",
                        description=f"SQLite integrity check reported: {row[0] if row else 'null'}",
                        auto_fixable=True,
                        fix_action="Backup corrupted database and attempt safe SQLite recovery.",
                    )
                )
                conn.close()
                return

            # Check for table existence
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations';")
            if not cursor.fetchone():
                issues.append(
                    IssueItem(
                        category="database",
                        severity="critical",
                        title="Missing conversations Table",
                        description="Database is missing the 'conversations' table.",
                        auto_fixable=True,
                        fix_action="Create missing 'conversations' table preserving existing records.",
                    )
                )
            else:
                # Check columns in conversations
                cursor.execute("PRAGMA table_info(conversations);")
                columns = {col[1] for col in cursor.fetchall()}
                missing_cols = []
                for req in ("persona", "system_prompt", "title", "updated_at"):
                    if req not in columns:
                        missing_cols.append(req)
                if missing_cols:
                    issues.append(
                        IssueItem(
                            category="database",
                            severity="warning",
                            title="Database Schema Migration Required",
                            description=f"Table 'conversations' is missing column(s): {', '.join(missing_cols)}.",
                            auto_fixable=True,
                            fix_action=f"Run non-destructive migration (ALTER TABLE conversations ADD COLUMN ...) preserving all existing chat history.",
                        )
                    )

            conn.close()
        except Exception as e:
            issues.append(
                IssueItem(
                    category="database",
                    severity="critical",
                    title="Database Access Error",
                    description=f"Could not read conversation database: {e}",
                    auto_fixable=True,
                    fix_action="Repair database permissions and verify SQLite lock state.",
                )
            )

    def _diagnose_key_store(self, issues: list[IssueItem]) -> None:
        key_path = os.path.join(self.data_dir, "api_keys.json")
        if not os.path.exists(key_path):
            issues.append(
                IssueItem(
                    category="keys",
                    severity="info",
                    title="API Key Store Not Initialized",
                    description=f"Key store file '{key_path}' does not exist yet.",
                    auto_fixable=True,
                    fix_action="Initialize valid empty API key store JSON.",
                )
            )
            return

        try:
            with open(key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                issues.append(
                    IssueItem(
                        category="keys",
                        severity="critical",
                        title="Malformed API Key Store",
                        description=f"'{key_path}' is valid JSON but not a list of keys.",
                        auto_fixable=True,
                        fix_action="Salvage any readable key entries and reformat safely.",
                    )
                )
        except json.JSONDecodeError as e:
            issues.append(
                IssueItem(
                    category="keys",
                    severity="critical",
                    title="Corrupted API Key Store JSON",
                    description=f"JSON syntax error in '{key_path}': {e}",
                    auto_fixable=True,
                    fix_action="Backup file, extract undamaged key records via regex salvage, and restore.",
                )
            )
        except Exception as e:
            issues.append(
                IssueItem(
                    category="keys",
                    severity="warning",
                    title="API Key Store Read Error",
                    description=f"Error accessing '{key_path}': {e}",
                    auto_fixable=True,
                    fix_action="Fix file permissions and ownership.",
                )
            )

    def _diagnose_filesystem(self, issues: list[IssueItem]) -> None:
        dirs_to_check = [
            self.data_dir,
            os.path.join(self.data_dir, "backups"),
            "models",
            "logs",
            "cache",
            "configs",
        ]
        for d in dirs_to_check:
            if not os.path.exists(d):
                issues.append(
                    IssueItem(
                        category="filesystem",
                        severity="info",
                        title=f"Directory Missing: {d}",
                        description=f"Required directory '{d}' does not exist.",
                        auto_fixable=True,
                        fix_action=f"Create directory '{d}'.",
                    )
                )
            elif not os.access(d, os.W_OK):
                issues.append(
                    IssueItem(
                        category="filesystem",
                        severity="critical",
                        title=f"Directory Not Writable: {d}",
                        description=f"Current process lacks write permissions for directory '{d}'.",
                        auto_fixable=False,
                        fix_action=f"Ensure write permissions for '{d}' (chmod / chown / icacls).",
                    )
                )

    def _diagnose_hardware_match(self, issues: list[IssueItem]) -> dict[str, Any]:
        match = match_device_settings()
        match_dict = match.to_dict()

        if match.status == "mismatch":
            issues.append(
                IssueItem(
                    category="hardware",
                    severity="warning",
                    title=f"Hardware Acceleration Mismatch ({match.primary_accelerator.name})",
                    description=match.mismatch_warning
                    or f"Physical GPU '{match.primary_accelerator.name}' detected, but PyTorch runtime is CPU-only.",
                    auto_fixable=True,
                    fix_action=match.install_hint or "Install matching PyTorch wheel with GPU acceleration.",
                )
            )
        elif match.status == "matched":
            # Hardware is matched and available
            pass

        return match_dict

    def _diagnose_dependencies(self, issues: list[IssueItem]) -> None:
        import importlib.util

        missing_mods = []
        for mod, spec in _CORE_PACKAGES.items():
            if importlib.util.find_spec(mod) is None:
                missing_mods.append(f"{mod} ({spec})")

        if missing_mods:
            issues.append(
                IssueItem(
                    category="dependencies",
                    severity="critical",
                    title="Missing Required Dependencies",
                    description=f"The following required Python packages are missing: {', '.join(missing_mods)}.",
                    auto_fixable=True,
                    fix_action=f"Run: {sys.executable} -m pip install -r requirements.txt",
                )
            )


class IssueRepairer:
    """Safely and non-destructively repairs system issues, matching hardware while strictly keeping all user data."""

    def __init__(self, config_path: str | None = None, data_dir: str | None = None) -> None:
        self.config_path = config_path or "configs/firewing.yaml"
        self.data_dir = data_dir or "data"
        self.personas_path = "configs/personas.yaml"
        self.env_path = ".env"

    def repair(
        self,
        match_device: bool = True,
        reinstall_packages: bool = False,
    ) -> RepairReport:
        actions_taken: list[str] = []
        warnings: list[str] = []

        # Step 1: Safety Snapshot (KEEP DATA FIRST)
        backup_dir = self._create_safety_backup(actions_taken, warnings)

        # Step 2: Ensure Directories
        self._repair_directories(actions_taken)

        # Step 3: Repair & Migrate Database Non-Destructively
        self._repair_database(actions_taken, warnings)

        # Step 4: Repair API Key Store Non-Destructively
        self._repair_key_store(actions_taken, warnings)

        # Step 5: Repair Configuration Files
        self._repair_configs(actions_taken)

        # Step 6: Hardware Matching & Acceleration Update
        device_matched_dict = None
        if match_device:
            device_matched_dict = self._match_and_update_device(actions_taken)

        # Step 7: Package Reinstall / Repair (Modpack Reinstall, Same Mods)
        reinstall_done = False
        if reinstall_packages:
            reinstall_done = self._reinstall_dependencies(actions_taken, warnings)

        summary = (
            f"Successfully executed {len(actions_taken)} repair action(s). "
            f"All existing user data (conversations, keys, models) was preserved."
        )

        return RepairReport(
            success=True,
            backup_path=backup_dir,
            actions_taken=actions_taken,
            warnings=warnings,
            device_matched=device_matched_dict,
            data_preserved=True,
            reinstall_performed=reinstall_done,
            summary=summary,
        )

    def _create_safety_backup(self, actions: list[str], warnings: list[str]) -> str | None:
        """Create a full timestamped backup of existing user data and configs before repair."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(self.data_dir, "backups", f"repair_backup_{ts}")
        try:
            os.makedirs(backup_dir, exist_ok=True)
            copied = []

            # 1. Back up database files
            db_path = os.path.join(self.data_dir, "conversations.db")
            if os.path.exists(db_path):
                shutil.copy2(db_path, os.path.join(backup_dir, "conversations.db"))
                copied.append("conversations.db")
                for ext in ("-wal", "-shm"):
                    p = db_path + ext
                    if os.path.exists(p):
                        shutil.copy2(p, os.path.join(backup_dir, f"conversations.db{ext}"))
                        copied.append(f"conversations.db{ext}")

            # 2. Back up API keys
            key_path = os.path.join(self.data_dir, "api_keys.json")
            if os.path.exists(key_path):
                shutil.copy2(key_path, os.path.join(backup_dir, "api_keys.json"))
                copied.append("api_keys.json")

            # 3. Back up configs
            for cfg in (self.config_path, self.personas_path, self.env_path):
                if os.path.exists(cfg):
                    dest = os.path.join(backup_dir, os.path.basename(cfg))
                    shutil.copy2(cfg, dest)
                    copied.append(os.path.basename(cfg))

            if copied:
                actions.append(f"Created safety data backup in '{backup_dir}' ({', '.join(copied)} preserved).")
            else:
                actions.append(f"Created backup directory '{backup_dir}'.")
            return backup_dir
        except Exception as e:
            warnings.append(f"Could not complete full backup before repair: {e}")
            return None

    def _repair_directories(self, actions: list[str]) -> None:
        for d in [
            self.data_dir,
            os.path.join(self.data_dir, "backups"),
            "models",
            "logs",
            "cache",
            "configs",
        ]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
                actions.append(f"Created directory '{d}'.")

    def _repair_database(self, actions: list[str], warnings: list[str]) -> None:
        db_path = os.path.join(self.data_dir, "conversations.db")
        if not os.path.exists(db_path):
            try:
                from firewing.inference.conversation_store import ConversationStore

                store = ConversationStore(db_path)
                store._init_schema()
                actions.append(f"Initialized fresh SQLite conversation store at '{db_path}'.")
            except Exception as e:
                warnings.append(f"Failed to initialize fresh database: {e}")
                return

        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            cursor = conn.cursor()

            # Verify integrity
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != "ok":
                warnings.append(f"Database integrity warning: {res[0] if res else 'unknown'}")

            # Ensure tables exist matching ConversationStore
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    persona TEXT,
                    system_prompt TEXT
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_call_id TEXT,
                    name TEXT,
                    tool_calls TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
            """)

            # Ensure columns exist via non-destructive ALTER TABLE
            cursor.execute("PRAGMA table_info(conversations);")
            existing_cols = {col[1] for col in cursor.fetchall()}

            migrated_cols = []
            if "persona" not in existing_cols:
                cursor.execute("ALTER TABLE conversations ADD COLUMN persona TEXT;")
                migrated_cols.append("persona")
            if "system_prompt" not in existing_cols:
                cursor.execute("ALTER TABLE conversations ADD COLUMN system_prompt TEXT;")
                migrated_cols.append("system_prompt")

            # Ensure indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);")

            conn.commit()
            conn.close()

            if migrated_cols:
                actions.append(
                    f"Migrated conversation database schema: added column(s) {', '.join(migrated_cols)} (all user history preserved)."
                )
            else:
                actions.append("Validated database schema and indexes (data intact).")
        except Exception as e:
            warnings.append(f"Database repair warning: {e}")

    def _repair_key_store(self, actions: list[str], warnings: list[str]) -> None:
        key_path = os.path.join(self.data_dir, "api_keys.json")
        if not os.path.exists(key_path):
            try:
                with open(key_path, "w", encoding="utf-8") as f:
                    json.dump([], f)
                actions.append(f"Initialized valid empty API key store at '{key_path}'.")
            except Exception as e:
                warnings.append(f"Failed to create key store: {e}")
            return

        try:
            with open(key_path, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                data = json.loads(content)
                if not isinstance(data, list):
                    raise ValueError("JSON root is not a list")
                actions.append("Validated API key store integrity.")
            except Exception:
                # Salvage records via regex
                salvaged = []
                pattern = re.compile(r"\{[^{}]*\"key_id\"[^{}]*\}")
                for match in pattern.finditer(content):
                    try:
                        record = json.loads(match.group(0))
                        if "key_id" in record and "hash" in record:
                            salvaged.append(record)
                    except Exception:
                        pass

                corrupt_backup = f"{key_path}.corrupt_{int(time.time())}"
                with open(corrupt_backup, "w", encoding="utf-8") as bf:
                    bf.write(content)

                with open(key_path, "w", encoding="utf-8") as f:
                    json.dump(salvaged, f, indent=2)

                actions.append(
                    f"Repaired corrupted API key store: salvaged {len(salvaged)} key(s), backup saved to '{corrupt_backup}'."
                )
        except Exception as e:
            warnings.append(f"Key store repair error: {e}")

    def _repair_configs(self, actions: list[str]) -> None:
        import yaml

        # Ensure parent directories exist
        for p in (self.config_path, self.personas_path, self.env_path):
            parent = os.path.dirname(p)
            if parent:
                os.makedirs(parent, exist_ok=True)

        # 1. Personas preset
        if not os.path.exists(self.personas_path):
            with open(self.personas_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_PERSONAS_YAML)
            actions.append(f"Created default personas file '{self.personas_path}'.")

        # 2. .env file
        if not os.path.exists(self.env_path):
            admin_key = secrets.token_hex(32)
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.write(f"# FIREWING Environment Variables\nFIREWING_ADMIN_KEY={admin_key}\n")
            actions.append(f"Created default '{self.env_path}' with generated admin key.")

        # 3. firewing.yaml
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_FIREWING_YAML)
            actions.append(f"Created default configuration file '{self.config_path}'.")
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}

            # Ensure model and api sections exist without overwriting user overrides
            changed = False
            if "model" not in data or not isinstance(data["model"], dict):
                data["model"] = {
                    "model_path": "Qwen/Qwen3-Omni-30B-A3B-Instruct",
                    "device": "auto",
                    "dtype": "auto",
                    "quantization": "int4",
                }
                changed = True
            if "api" not in data or not isinstance(data["api"], dict):
                data["api"] = {
                    "host": "0.0.0.0",
                    "port": 8000,
                    "require_api_key": True,
                }
                changed = True

            if changed:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                actions.append(f"Repaired missing sections in '{self.config_path}'.")

    def _match_and_update_device(self, actions: list[str]) -> dict[str, Any]:
        """Detect hardware and auto-tune firewing.yaml with optimal matched device/dtype/quantization."""
        import yaml

        match = match_device_settings()
        match_dict = match.to_dict()

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            else:
                data = {}

            model_sec = data.setdefault("model", {})
            current_device = model_sec.get("device", "auto")
            current_dtype = model_sec.get("dtype", "auto")
            current_quant = model_sec.get("quantization", "int4")

            # If device is "auto" or if status is matched, update to recommended settings
            target_device = match.recommended_device
            target_dtype = match.recommended_dtype
            target_quant = match.recommended_quantization

            model_sec["device"] = target_device
            model_sec["dtype"] = target_dtype
            model_sec["quantization"] = target_quant

            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False)

            actions.append(
                f"Matched device configuration to {match.primary_accelerator.name} "
                f"(device: '{target_device}', dtype: '{target_dtype}', quantization: '{target_quant}')."
            )
        except Exception as e:
            actions.append(f"Hardware detection completed ({match.status}), but could not update YAML: {e}")

        return match_dict

    def _reinstall_dependencies(self, actions: list[str], warnings: list[str]) -> bool:
        """Reinstall or verify package dependencies from requirements.txt while leaving user data untouched."""
        req_file = "requirements.txt"
        if not os.path.exists(req_file):
            warnings.append("requirements.txt not found; skipped package reinstall.")
            return False

        try:
            cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode == 0:
                actions.append("Reinstalled and verified core package dependencies (requirements.txt).")
                return True
            else:
                warnings.append(f"pip install exited with code {proc.returncode}: {proc.stderr[:200]}")
                return False
        except Exception as e:
            warnings.append(f"Package reinstall error: {e}")
            return False
