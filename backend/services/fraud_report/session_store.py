from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "banking.db"


@dataclass
class FraudReportSessionState:
    user_id: str
    session_id: str
    fields: dict = field(default_factory=dict)
    stage: str = "collect_account"
    candidate_transactions: list[dict] = field(default_factory=list)
    selected_transaction_ref: str | None = None
    last_prompt: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class FraudReportSessionStore:
    """SQLite-backed multi-turn state for fraud-report intake."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self._ensure_schema()

    def get(self, user_id: str, session_id: str) -> FraudReportSessionState | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT user_id, session_id, fields_json, stage, candidate_transactions_json,
                       selected_transaction_ref, last_prompt, created_at, updated_at
                FROM fraud_report_sessions
                WHERE user_id = ? AND session_id = ?
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
            if not row:
                return None
            return self._row_to_state(row)
        finally:
            conn.close()

    def get_or_create(self, user_id: str, session_id: str) -> FraudReportSessionState:
        existing = self.get(user_id, session_id)
        if existing:
            return existing

        state = FraudReportSessionState(user_id=user_id, session_id=session_id)
        self._upsert(state)
        return state

    def merge(self, user_id: str, session_id: str, fields: dict) -> FraudReportSessionState:
        state = self.get_or_create(user_id, session_id)
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            state.fields[key] = value
        state.updated_at = self._now()
        self._upsert(state)
        return state

    def set_stage(self, user_id: str, session_id: str, stage: str) -> FraudReportSessionState:
        state = self.get_or_create(user_id, session_id)
        state.stage = stage
        state.updated_at = self._now()
        self._upsert(state)
        return state

    def set_transaction_candidates(
        self,
        user_id: str,
        session_id: str,
        transactions: list[dict],
    ) -> FraudReportSessionState:
        state = self.get_or_create(user_id, session_id)
        state.candidate_transactions = transactions
        state.updated_at = self._now()
        self._upsert(state)
        return state

    def set_selected_transaction(
        self,
        user_id: str,
        session_id: str,
        transaction_ref: str | None,
    ) -> FraudReportSessionState:
        state = self.get_or_create(user_id, session_id)
        state.selected_transaction_ref = transaction_ref
        if transaction_ref:
            state.fields["transaction_ref"] = transaction_ref
        state.updated_at = self._now()
        self._upsert(state)
        return state

    def set_last_prompt(self, user_id: str, session_id: str, prompt: str) -> FraudReportSessionState:
        state = self.get_or_create(user_id, session_id)
        state.last_prompt = prompt
        state.updated_at = self._now()
        self._upsert(state)
        return state

    def clear(self, user_id: str, session_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM fraud_report_sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _upsert(self, state: FraudReportSessionState) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO fraud_report_sessions (
                    user_id, session_id, fields_json, stage, candidate_transactions_json,
                    selected_transaction_ref, last_prompt, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    fields_json=excluded.fields_json,
                    stage=excluded.stage,
                    candidate_transactions_json=excluded.candidate_transactions_json,
                    selected_transaction_ref=excluded.selected_transaction_ref,
                    last_prompt=excluded.last_prompt,
                    updated_at=excluded.updated_at
                """,
                (
                    state.user_id,
                    state.session_id,
                    json.dumps(state.fields, ensure_ascii=False),
                    state.stage,
                    json.dumps(state.candidate_transactions, ensure_ascii=False),
                    state.selected_transaction_ref,
                    state.last_prompt,
                    state.created_at,
                    state.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_state(self, row: sqlite3.Row) -> FraudReportSessionState:
        return FraudReportSessionState(
            user_id=row["user_id"],
            session_id=row["session_id"],
            fields=json.loads(row["fields_json"] or "{}"),
            stage=row["stage"] or "collect_account",
            candidate_transactions=json.loads(row["candidate_transactions_json"] or "[]"),
            selected_transaction_ref=row["selected_transaction_ref"],
            last_prompt=row["last_prompt"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fraud_report_sessions (
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    session_id TEXT NOT NULL,
                    fields_json TEXT NOT NULL DEFAULT '{}',
                    stage TEXT NOT NULL DEFAULT 'collect_account',
                    candidate_transactions_json TEXT NOT NULL DEFAULT '[]',
                    selected_transaction_ref TEXT,
                    last_prompt TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, session_id)
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
