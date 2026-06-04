from __future__ import annotations

import re
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras

from backend.config import DATABASE_URL


class FraudReportStore:
    """Fraud report data access against PostgreSQL."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or DATABASE_URL

    def is_self_account(self, user_id: str, account_number: str) -> bool:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM accounts
                    WHERE cif_no = %s AND account_no = %s
                    LIMIT 1
                    """,
                    (user_id, account_number),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()

    def find_matching_transactions(
        self,
        *,
        user_id: str,
        reported_account_no: str,
        reported_bank_code: str | None = None,
        transaction_ref: str | None = None,
    ) -> list[dict]:
        params: list[object] = [user_id, reported_account_no]
        filters = [
            "cif_no = %s",
            "counterparty_account_no = %s",
            "direction = 'OUT'",
            "status = 'SUCCESS'",
        ]

        if transaction_ref:
            filters.append("transaction_ref = %s")
            params.append(transaction_ref)

        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT transaction_ref, cif_no, account_no, counterparty_name,
                           counterparty_account_no, counterparty_bank_code,
                           amount, currency, transaction_type, description,
                           status, transaction_time, created_at
                    FROM transactions
                    WHERE {" AND ".join(filters)}
                    ORDER BY transaction_time DESC
                    LIMIT 10
                    """,
                    params,
                )
                rows = cur.fetchall()
            transactions = [self._transaction_to_dict(dict(row)) for row in rows]
            if reported_bank_code:
                transactions.sort(
                    key=lambda tx: self._bank_matches(
                        tx.get("recipient_bank", ""),
                        reported_bank_code,
                    ),
                    reverse=True,
                )
            return transactions
        finally:
            conn.close()

    def get_reported_account(self, account_number: str) -> dict | None:
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT account_no, bank_code, risk_score, risk_level,
                           valid_report_count, unique_reporter_count,
                           total_reported_amount, avg_confidence_score,
                           status, first_reported_at, last_reported_at
                    FROM reported_accounts
                    WHERE account_no = %s
                    LIMIT 1
                    """,
                    (account_number,),
                )
                row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["severity"] = result.get("risk_level", "LOW")
            return result
        finally:
            conn.close()

    def find_user_existing_reports(
        self,
        user_id: str,
        reported_account_no: str,
    ) -> list[dict]:
        """Check if this user already filed a report against this account."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT report_id, reporter_cif_no, transaction_ref, reported_account_no,
                           reported_bank_code, fraud_type, confidence_score, status, created_at
                    FROM fraud_reports
                    WHERE reporter_cif_no = %s AND reported_account_no = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id, reported_account_no),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def persist_report(
        self,
        *,
        reporter_cif_no: str,
        transaction_ref: str | None,
        reported_account_no: str,
        reported_bank_code: str,
        reported_customer_cif: str | None = None,
        fraud_type: str,
        contact_channel: str,
        aftermath: str,
        reason_text: str,
        has_evidence: bool,
        confidence_score: int,
        status: str,
    ) -> str:
        """Insert a fraud report and return the report_id."""
        report_id = str(uuid.uuid4())
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO fraud_reports (
                        report_id, reporter_cif_no, transaction_ref, reported_account_no,
                        reported_bank_code, reported_customer_cif, fraud_type, contact_channel,
                        aftermath, reason_text, has_evidence, confidence_score, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        report_id, reporter_cif_no, transaction_ref, reported_account_no,
                        reported_bank_code, reported_customer_cif, fraud_type, contact_channel,
                        aftermath, reason_text, has_evidence, confidence_score, status,
                        datetime.now(),
                    ),
                )
            conn.commit()
            return report_id
        finally:
            conn.close()

    def update_reported_account_aggregate(
        self,
        account_no: str,
        bank_code: str,
        confidence_score: int,
        reporter_cif_no: str,
        amount: int | None = None,
    ) -> None:
        """Update or insert reported_accounts aggregate after persisting a report."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM reported_accounts WHERE account_no = %s AND bank_code = %s",
                    (account_no, bank_code),
                )
                existing = cur.fetchone()

                now = datetime.now()
                if existing:
                    new_count = (existing["valid_report_count"] or 0) + 1
                    new_unique = (existing["unique_reporter_count"] or 0) + 1
                    new_total = (existing["total_reported_amount"] or 0) + (amount or 0)
                    new_avg = ((existing["avg_confidence_score"] or 0) * (new_count - 1) + confidence_score) // new_count
                    new_risk = min(0.95, (existing["risk_score"] or 0) + 0.15)
                    new_level = self._risk_score_to_level(float(new_risk))
                    cur.execute(
                        """
                        UPDATE reported_accounts
                        SET valid_report_count = %s, unique_reporter_count = %s,
                            total_reported_amount = %s, avg_confidence_score = %s,
                            risk_score = %s, risk_level = %s, last_reported_at = %s
                        WHERE account_no = %s AND bank_code = %s
                        """,
                        (new_count, new_unique, new_total, new_avg,
                         new_risk, new_level, now, account_no, bank_code),
                    )
                else:
                    risk_score = 0.25 if confidence_score < 80 else 0.95
                    risk_level = self._risk_score_to_level(risk_score)
                    cur.execute(
                        """
                        INSERT INTO reported_accounts (
                            reported_account_id, account_no, bank_code, valid_report_count,
                            unique_reporter_count, total_reported_amount, avg_confidence_score,
                            risk_score, risk_level, status, first_reported_at, last_reported_at
                        ) VALUES (%s, %s, %s, 1, 1, %s, %s, %s, %s, 'ACTIVE', %s, %s)
                        """,
                        (str(uuid.uuid4()), account_no, bank_code, amount or 0,
                         confidence_score, risk_score, risk_level, now, now),
                    )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def summarize_transaction(tx: dict) -> str:
        amount = tx.get("amount")
        amount_text = f"{amount:,}".replace(",", ".") if isinstance(amount, int) else str(amount)
        return (
            f"{tx.get('transaction_ref')} | {tx.get('recipient_name')} | "
            f"{tx.get('recipient_account')} | {tx.get('recipient_bank')} | "
            f"{amount_text} {tx.get('currency', 'VND')} | {tx.get('created_at')}"
        )

    def _connect(self):
        return psycopg2.connect(self.dsn)

    @staticmethod
    def _transaction_to_dict(row: dict) -> dict:
        row["transaction_ref"] = row.get("transaction_ref", "")
        row["recipient_name"] = row.pop("counterparty_name", None) or ""
        row["recipient_account"] = row.pop("counterparty_account_no", None) or ""
        row["recipient_bank"] = row.pop("counterparty_bank_code", None) or ""
        row["created_at"] = str(row.get("transaction_time") or row.get("created_at") or "")
        return row

    @staticmethod
    def format_transaction_ref(transaction_ref: str) -> str:
        return transaction_ref

    @staticmethod
    def _risk_score_to_level(score: float) -> str:
        if score >= 0.8:
            return "CRITICAL"
        elif score >= 0.6:
            return "HIGH"
        elif score >= 0.3:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _bank_matches(stored_bank: str, reported_bank_code: str) -> bool:
        return FraudReportStore._normalize_bank(stored_bank) == FraudReportStore._normalize_bank(
            reported_bank_code
        )

    @staticmethod
    def _normalize_bank(value: str) -> str:
        compact = re.sub(r"[^a-z0-9]", "", value.lower())
        aliases = {
            "vcb": "vietcombank",
            "vietcombank": "vietcombank",
            "vpb": "vpbank",
            "vpbank": "vpbank",
            "tcb": "techcombank",
            "techcombank": "techcombank",
            "mb": "mbbank",
            "mbb": "mbbank",
            "mbbank": "mbbank",
            "vtb": "vietinbank",
            "vietinbank": "vietinbank",
            "tpb": "tpbank",
            "tpbank": "tpbank",
        }
        return aliases.get(compact, compact)
