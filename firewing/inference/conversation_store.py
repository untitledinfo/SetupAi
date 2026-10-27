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
    persona: str | None = None
    system_prompt: str | None = None

    def to_public_dict(self, include_messages: bool = True) -> dict:
        out = {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "persona": self.persona,
            "system_prompt": self.system_prompt,
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
                    updated_at REAL NOT NULL,
                    persona TEXT,
                    system_prompt TEXT
                )
                """
            )
            # Automatic schema migration for existing databases
            for col in ("persona", "system_prompt"):
                try:
                    conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass

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

    def create(
        self,
        title: str = "New conversation",
        persona: str | None = None,
        system_prompt: str | None = None,
    ) -> ConversationRecord:
        conversation_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, persona, system_prompt) VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, title, now, now, persona, system_prompt),
            )
        return ConversationRecord(
            conversation_id=conversation_id,
            title=title,
            created_at=now,
            updated_at=now,
            messages=[],
            persona=persona,
            system_prompt=system_prompt,
        )

    def get(self, conversation_id: str) -> ConversationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at, persona, system_prompt FROM conversations WHERE id = ?",
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
        return ConversationRecord(
            conversation_id=row[0],
            title=row[1],
            created_at=row[2],
            updated_at=row[3],
            messages=messages,
            persona=row[4],
            system_prompt=row[5],
        )

    def update(
        self,
        conversation_id: str,
        title: str | None = None,
        persona: str | None = None,
        system_prompt: str | None = None,
    ) -> bool:
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if persona is not None:
            updates.append("persona = ?")
            params.append(persona)
        if system_prompt is not None:
            updates.append("system_prompt = ?")
            params.append(system_prompt)
        if not updates:
            return True

        now = time.time()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(conversation_id)

        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            return cur.rowcount > 0

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
                "SELECT id, title, created_at, updated_at, persona, system_prompt FROM conversations "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            ConversationRecord(
                conversation_id=r[0],
                title=r[1],
                created_at=r[2],
                updated_at=r[3],
                messages=[],
                persona=r[4],
                system_prompt=r[5],
            )
            for r in rows
        ]

    def delete(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            return cur.rowcount > 0

    def clear_messages(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (time.time(), conversation_id),
            )
            return cur.rowcount > 0

    def export_markdown(self, conversation_id: str) -> str | None:
        rec = self.get(conversation_id)
        if not rec:
            return None
        lines = [f"# {rec.title}", f"*ID: {rec.conversation_id}*", f"*Date: {time.ctime(rec.created_at)}*"]
        if rec.persona:
            lines.append(f"*Persona: {rec.persona}*")
        lines.append("\n---\n")
        for m in rec.messages:
            lines.append(f"**{m.role.upper()}**:")
            if isinstance(m.content, str):
                lines.append(m.content)
            elif isinstance(m.content, list):
                for part in m.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        lines.append(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        lines.append("*(attached image)*")
            if m.tool_calls:
                lines.append(f"```json\n{json.dumps(m.tool_calls, indent=2)}\n```")
            lines.append("")
        return "\n".join(lines)
