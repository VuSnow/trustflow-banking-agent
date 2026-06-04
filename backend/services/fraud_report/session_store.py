from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import psycopg2
import psycopg2.extras

from backend.config import DATABASE_URL


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
    """PostgreSQL-backed multi-turn state for fraud-report intake."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or DATABASE_URL

    def get(self, user_id: str, session_id: str) -> FraudReportSessionState | None:
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, session_id, fields_json, stage, candidate_transactions_json,
                           selected_transaction_ref, last_prompt, created_at, updated_at
                    FROM fraud_report_sessions
                    WHERE user_id = %s AND session_id = %s
                    LIMIT 1
                    """,
                    (user_id, session_id),
                )
                row = cur.fetchone()
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
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM fraud_report_sessions WHERE user_id = %s AND session_id = %s",
                    (user_id, session_id),
                )
            conn.commit()
        finally:
            conn.close()

    def _upsert(self, state: FraudReportSessionState) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fraud_report_sessions (
                        user_id, session_id, fields_json, stage, candidate_transactions_json,
                        selected_transaction_ref, last_prompt, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, session_id) DO UPDATE SET
                        fields_json = EXCLUDED.fields_json,
                        stage = EXCLUDED.stage,
                        candidate_transactions_json = EXCLUDED.candidate_transactions_json,
                        selected_transaction_ref = EXCLUDED.selected_transaction_ref,
                        last_prompt = EXCLUDED.last_prompt,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        state.user_id,
                        state.session_id,
                        json.dumps(state.fields, ensure_ascii=False),
                        state.stage,
                        json.dumps(state.candidate_transactions, ensure_ascii=False, default=str),
                        state.selected_transaction_ref,
                        state.last_prompt,
                        state.created_at,
                        state.updated_at,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _row_to_state(self, row: dict) -> FraudReportSessionState:
        return FraudReportSessionState(
            user_id=row["user_id"],
            session_id=row["session_id"],
            fields=json.loads(row["fields_json"] or "{}"),
            stage=row["stage"] or "collect_account",
            candidate_transactions=json.loads(row["candidate_transactions_json"] or "[]"),
            selected_transaction_ref=row["selected_transaction_ref"],
            last_prompt=row["last_prompt"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _connect(self):
        return psycopg2.connect(self.dsn)

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
