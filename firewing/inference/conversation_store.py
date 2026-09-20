"""Persistent conversation storage.

Upgrades the beta's client-resends-full-history-every-time model with
server-side conversation state: create a conversation once, then send
only the new message on each turn. Backed by SQLite (stdlib, no extra
service to run) — fine for a single-instance deployment; if you scale
to multiple replicas sharing one store, point this at a real database
instead (the interface here is intentionally small so that's a
contained change).

Messages are stored as JSON (matching the OpenAI-style content shape
used throughout the API), so multimodal/tool-call messages round-trip
without any special-casing.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StoredMessage:
    role: str
    content: object
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class ConversationRecord:
    conversation_id: str
    title: str
    created_at: float
    updated_at: float
    messages: list[StoredMessage]

    def to_public_dict(self, include_messages: bool = True) -> dict:
        out = {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
        }
        if include_messages:
            out["messages"] = [
                {
                    "role": m.role,
                    "content": m.content,
                    "tool_call_id": m.tool_call_id,
                    "name": m.name,
                    "tool_calls": m.tool_calls,
                    "created_at": m.created_at,
                }
                for m in self.messages
            ]
        return out


class ConversationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._schema_ready = False

    @contextmanager
    def _connect(self):
        # Deferred until the first real use (not at construction time) —
        # mirrors KeyStore's pattern so simply instantiating a store
        # (e.g. at app startup) never requires write access to its
        # directory unless something actually gets saved.
        if not self._schema_ready:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()
            self._schema_ready = True

        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
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
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation "
                "ON messages(conversation_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def create(self, title: str = "New conversation") -> ConversationRecord:
        conversation_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title, now, now),
            )
        return ConversationRecord(conversation_id, title, now, now, [])

    def get(self, conversation_id: str) -> ConversationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            message_rows = conn.execute(
                "SELECT role, content, tool_call_id, name, tool_calls, created_at "
                "FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()

        messages = [
            StoredMessage(
                role=r[0],
                content=json.loads(r[1]),
                tool_call_id=r[2],
                name=r[3],
                tool_calls=json.loads(r[4]) if r[4] else None,
                created_at=r[5],
            )
            for r in message_rows
        ]
        return ConversationRecord(row[0], row[1], row[2], row[3], messages)

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: object,
        tool_call_id: str | None = None,
        name: str | None = None,
        tool_calls: list | None = None,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if not existing:
                raise KeyError(f"Unknown conversation_id: {conversation_id}")
            conn.execute(
                "INSERT INTO messages "
                "(conversation_id, role, content, tool_call_id, name, tool_calls, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    role,
                    json.dumps(content),
                    tool_call_id,
                    name,
                    json.dumps(tool_calls) if tool_calls else None,
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )

    def list(self, limit: int = 50) -> list[ConversationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ConversationRecord(r[0], r[1], r[2], r[3], []) for r in rows]

    def delete(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            return cur.rowcount > 0
