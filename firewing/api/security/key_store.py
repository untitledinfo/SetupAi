"""Multi-user API key management.

Upgrades the beta's single env-var key list into a real store: named
keys, creation timestamps, per-key revocation, without needing a
restart to add a user. Backed by a JSON file for simplicity — swap for
a real database if you need concurrent multi-instance writes (see the
note in docs/troubleshooting.md).

Keys are stored hashed (SHA-256), never in plaintext, so a leaked
store file doesn't hand out live credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Lock


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class ApiKeyRecord:
    key_id: str
    label: str
    key_hash: str
    created_at: float
    revoked: bool = False
    last_used_at: float | None = None
    request_count: int = 0

    def to_public_dict(self) -> dict:
        """Never include key_hash in anything returned to a client."""
        return {
            "key_id": self.key_id,
            "label": self.label,
            "created_at": self.created_at,
            "revoked": self.revoked,
            "last_used_at": self.last_used_at,
            "request_count": self.request_count,
        }


class KeyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = Lock()
        self._records: dict[str, ApiKeyRecord] = {}
        self._last_mtime: float = 0.0
        self._load()

    def _maybe_reload(self) -> None:
        if not self.path.exists():
            return
        try:
            mtime = self.path.stat().st_mtime
            if mtime > self._last_mtime:
                self._load()
        except OSError:
            pass

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            self._last_mtime = self.path.stat().st_mtime
        except (json.JSONDecodeError, OSError):
            raw = []
        new_records = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            rec = ApiKeyRecord(
                key_id=item["key_id"],
                label=item.get("label", ""),
                key_hash=item["key_hash"],
                created_at=item.get("created_at", time.time()),
                revoked=item.get("revoked", False),
                last_used_at=item.get("last_used_at"),
                request_count=item.get("request_count", 0),
            )
            new_records[rec.key_id] = rec
        self._records = new_records

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in self._records.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            self._last_mtime = self.path.stat().st_mtime
        except OSError:
            pass

    def create_key(self, label: str) -> tuple[str, ApiKeyRecord]:
        """Returns (plaintext_key, record). The plaintext key is shown
        exactly once — the store only ever keeps the hash.
        """
        plaintext = f"fw-{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(8)
        record = ApiKeyRecord(
            key_id=key_id,
            label=label,
            key_hash=_hash_key(plaintext),
            created_at=time.time(),
        )
        with self._lock:
            self._maybe_reload()
            self._records[key_id] = record
            self._save()
        return plaintext, record

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            self._maybe_reload()
            record = self._records.get(key_id)
            if not record:
                return False
            record.revoked = True
            self._save()
            return True

    def delete_key(self, key_id: str) -> bool:
        with self._lock:
            self._maybe_reload()
            if key_id not in self._records:
                return False
            del self._records[key_id]
            self._save()
            return True

    def update_key(self, key_id: str, label: str) -> bool:
        with self._lock:
            self._maybe_reload()
            record = self._records.get(key_id)
            if not record:
                return False
            record.label = label
            self._save()
            return True

    def get_key(self, key_id: str) -> ApiKeyRecord | None:
        with self._lock:
            self._maybe_reload()
            return self._records.get(key_id)

    def list_keys(self) -> list[ApiKeyRecord]:
        with self._lock:
            self._maybe_reload()
            return list(self._records.values())

    def is_valid(self, plaintext_key: str) -> bool:
        key_hash = _hash_key(plaintext_key)
        with self._lock:
            self._maybe_reload()
            return any(
                hmac.compare_digest(r.key_hash, key_hash) and not r.revoked
                for r in self._records.values()
            )

    def record_usage(self, plaintext_key: str) -> ApiKeyRecord | None:
        key_hash = _hash_key(plaintext_key)
        with self._lock:
            self._maybe_reload()
            for r in self._records.values():
                if hmac.compare_digest(r.key_hash, key_hash) and not r.revoked:
                    r.last_used_at = time.time()
                    r.request_count += 1
                    self._save()
                    return r
        return None
