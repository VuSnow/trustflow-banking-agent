from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "banking.db"


class ChatSessionStore:
    """SQLite-backed chat session and message history."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self._ensure_schema()

    def create_session(self, user_id: str, title: str | None = None, session_id: str | None = None) -> dict:
        session_id = session_id or str(uuid4())
        now = self._now()
        title = title or f"Session {session_id[:8]}"
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, user_id, title, status, created_at, updated_at, last_message_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?)
                """,
                (session_id, user_id, title, now, now, now),
            )
            conn.commit()
            return self.get_session(session_id)
        finally:
            conn.close()

    def ensure_session(self, user_id: str, session_id: str, title: str | None = None) -> dict:
        existing = self.get_session(session_id)
        if existing:
            if existing["user_id"] != user_id:
                raise ValueError("session_id does not belong to the supplied user_id")
            return existing
        return self.create_session(user_id=user_id, title=title, session_id=session_id)

    def list_sessions(self, user_id: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT s.session_id, s.user_id, s.title, s.status, s.created_at, s.updated_at,
                       COALESCE(COUNT(m.id), 0) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.session_id
                WHERE s.user_id = ?
                GROUP BY s.session_id
                ORDER BY COALESCE(MAX(m.created_at), s.updated_at) DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT s.session_id, s.user_id, s.title, s.status, s.created_at, s.updated_at,
                       COALESCE(COUNT(m.id), 0) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM chat_sessions s
                LEFT JOIN chat_messages m ON m.session_id = s.session_id
                WHERE s.session_id = ?
                GROUP BY s.session_id
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_session(self, session_id: str, *, title: str | None = None, status: str | None = None) -> dict | None:
        existing = self.get_session(session_id)
        if not existing:
            return None
        conn = self._connect()
        try:
            now = self._now()
            conn.execute(
                """
                UPDATE chat_sessions
                SET title = COALESCE(?, title),
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE session_id = ?
                """,
                (title, status, now, session_id),
            )
            conn.commit()
            return self.get_session(session_id)
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def add_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: str,
        message: str,
        data: dict | None = None,
    ) -> dict:
        self.ensure_session(user_id, session_id)
        now = self._now()
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO chat_messages (session_id, user_id, role, message, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, role, message, json.dumps(data, ensure_ascii=False) if data is not None else None, now),
            )
            conn.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, last_message_at = ?, title = COALESCE(title, ?)
                WHERE session_id = ?
                """,
                (now, now, message[:48] or "Session", session_id),
            )
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "message": message,
                "data": data,
                "created_at": now,
            }
        finally:
            conn.close()

    def get_messages(self, session_id: str) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, session_id, user_id, role, message, data_json, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            messages = []
            for row in rows:
                item = dict(row)
                item["data"] = json.loads(item.pop("data_json")) if item["data_json"] else None
                messages.append(item)
            return messages
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    title TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_at TEXT
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
