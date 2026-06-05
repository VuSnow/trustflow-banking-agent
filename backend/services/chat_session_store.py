from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

import psycopg2
import psycopg2.extras

from backend.config import DATABASE_URL


class ChatSessionStore:
    """PostgreSQL-backed chat session and message history."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or DATABASE_URL

    def create_session(self, user_id: str, title: str | None = None, session_id: str | None = None) -> dict:
        session_id = session_id or str(uuid4())
        now = self._now()
        title = title or f"Session {session_id[:8]}"
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (
                        session_id, user_id, title, status, created_at, updated_at, last_message_at
                    ) VALUES (%s, %s, %s, 'active', %s, %s, %s)
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
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT s.session_id, s.user_id, s.title, s.status, s.created_at, s.updated_at,
                           COALESCE(COUNT(m.id), 0) AS message_count,
                           MAX(m.created_at) AS last_message_at
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON m.session_id = s.session_id
                    WHERE s.user_id = %s
                    GROUP BY s.session_id
                    ORDER BY COALESCE(MAX(m.created_at), s.updated_at) DESC
                    """,
                    (user_id,),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict | None:
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT s.session_id, s.user_id, s.title, s.status, s.created_at, s.updated_at,
                           COALESCE(COUNT(m.id), 0) AS message_count,
                           MAX(m.created_at) AS last_message_at
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON m.session_id = s.session_id
                    WHERE s.session_id = %s
                    GROUP BY s.session_id
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET title = COALESCE(%s, title),
                        status = COALESCE(%s, status),
                        updated_at = %s
                    WHERE session_id = %s
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
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
                cur.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_messages (session_id, user_id, role, message, data_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (session_id, user_id, role, message,
                     json.dumps(data, ensure_ascii=False) if data is not None else None, now),
                )
                row_id = cur.fetchone()[0]
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET updated_at = %s, last_message_at = %s, title = COALESCE(title, %s)
                    WHERE session_id = %s
                    """,
                    (now, now, message[:48] or "Session", session_id),
                )
            conn.commit()
            return {
                "id": row_id,
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
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, session_id, user_id, role, message, data_json, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY id ASC
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()
            messages = []
            for row in rows:
                item = dict(row)
                item["data"] = json.loads(item.pop("data_json")) if item.get("data_json") else None
                messages.append(item)
            return messages
        finally:
            conn.close()

    # ─── Pipeline state persistence ──────────────────────────────────────────

    def get_pipeline_state(self, session_id: str) -> dict | None:
        """Retrieve active pipeline state for a session."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT pipeline_state FROM chat_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if row and row["pipeline_state"]:
                    state = row["pipeline_state"]
                    # psycopg2 auto-parses JSONB to dict; handle str just in case
                    if isinstance(state, str):
                        return json.loads(state)
                    return state
            return None
        finally:
            conn.close()

    def set_pipeline_state(self, session_id: str, state: dict | None) -> None:
        """Store or clear pipeline state for a session."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET pipeline_state = %s, updated_at = %s
                    WHERE session_id = %s
                    """,
                    (
                        json.dumps(state, ensure_ascii=False) if state else None,
                        self._now(),
                        session_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def clear_pipeline_state(self, session_id: str) -> None:
        """Clear pipeline state when pipeline completes or is cancelled."""
        self.set_pipeline_state(session_id, None)

    # ─── Transaction state persistence (FSM + draft snapshot) ────────────────

    def get_transaction_state(self, session_id: str) -> dict | None:
        """Retrieve active transaction state for a session."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT transaction_state FROM chat_sessions WHERE session_id = %s",
                    (session_id,),
                )
                row = cur.fetchone()
                if row and row["transaction_state"]:
                    state = row["transaction_state"]
                    if isinstance(state, str):
                        return json.loads(state)
                    return state
            return None
        finally:
            conn.close()

    def set_transaction_state(self, session_id: str, state: dict | None) -> None:
        """Store or clear transaction state for a session."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET transaction_state = %s, updated_at = %s
                    WHERE session_id = %s
                    """,
                    (
                        json.dumps(state, ensure_ascii=False) if state else None,
                        self._now(),
                        session_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def clear_transaction_state(self, session_id: str) -> None:
        """Clear transaction state when transaction completes or is cancelled."""
        self.set_transaction_state(session_id, None)

    # ─── Card operation state persistence ────────────────────────────────────

    def get_card_operation_state(self, session_id: str) -> dict | None:
        """Retrieve active card operation state for a session."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT card_operation_state FROM chat_sessions WHERE session_id = %s",
                    (session_id,),
                )
                row = cur.fetchone()
                if row and row["card_operation_state"]:
                    state = row["card_operation_state"]
                    if isinstance(state, str):
                        return json.loads(state)
                    return state
            return None
        finally:
            conn.close()

    def set_card_operation_state(self, session_id: str, state: dict | None) -> None:
        """Store or clear card operation state for a session."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET card_operation_state = %s, updated_at = %s
                    WHERE session_id = %s
                    """,
                    (
                        json.dumps(state, ensure_ascii=False) if state else None,
                        self._now(),
                        session_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def clear_card_operation_state(self, session_id: str) -> None:
        """Clear card operation state."""
        self.set_card_operation_state(session_id, None)

    def _connect(self):
        return psycopg2.connect(self.dsn)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
