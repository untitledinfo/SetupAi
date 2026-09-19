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

    def to_public_dict(self) -> dict:
        """Never include key_hash in anything returned to a client."""
        return {
            "key_id": self.key_id,
            "label": self.label,
            "created_at": self.created_at,
            "revoked": self.revoked,
        }


class KeyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = Lock()
        self._records: dict[str, ApiKeyRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        for item in raw:
            rec = ApiKeyRecord(**item)
            self._records[rec.key_id] = rec

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in self._records.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_key(self, label: str) -> tuple[str, ApiKeyRecord]:
        """Returns (plaintext_key, record). The plaintext key is shown
        exactly once — the store only ever keeps the hash.
        """
        plaintext = secrets.token_urlsafe(32)
        key_id = secrets.token_hex(8)
        record = ApiKeyRecord(
            key_id=key_id,
            label=label,
            key_hash=_hash_key(plaintext),
            created_at=time.time(),
        )
        with self._lock:
            self._records[key_id] = record
            self._save()
        return plaintext, record

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            record = self._records.get(key_id)
            if not record:
                return False
            record.revoked = True
            self._save()
            return True

    def list_keys(self) -> list[ApiKeyRecord]:
        return list(self._records.values())

    def is_valid(self, plaintext_key: str) -> bool:
        key_hash = _hash_key(plaintext_key)
        return any(
            r.key_hash == key_hash and not r.revoked for r in self._records.values()
        )
