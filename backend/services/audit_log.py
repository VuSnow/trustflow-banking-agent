"""Structured audit logging — writes to audit_logs table in PostgreSQL.

Tracks state transitions, user actions, classifier results, OTP events,
guardrail decisions, and verification results for full traceability.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

import psycopg2

from backend.config import DATABASE_URL

logger = logging.getLogger(__name__)


def write_audit_log(
    *,
    cif_no: str,
    event_type: str,
    actor: str = "system",
    event_payload: dict | None = None,
    action_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Write a structured audit event to the audit_logs table.

    Args:
        cif_no: Customer identifier.
        event_type: Event category, e.g. "TRANSACTION_DRAFT_CREATED",
                    "CONFIRMATION_CLASSIFIED", "OTP_VALIDATED", etc.
        actor: Who triggered the event — "user", "system", "agent", "guardrail".
        event_payload: Arbitrary JSON payload with event details.
        action_id: Optional link to action_requests table.
        session_id: Chat session for correlation.
    """
    audit_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    payload = event_payload or {}
    if session_id:
        payload["session_id"] = session_id

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_logs (audit_id, action_id, cif_no, event_type, actor, event_payload, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        audit_id,
                        action_id,
                        cif_no,
                        event_type,
                        actor,
                        json.dumps(payload, ensure_ascii=False, default=str),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        # Audit failures should not break the main flow
        logger.error(f"[AUDIT] Failed to write audit log: {e}", exc_info=True)
