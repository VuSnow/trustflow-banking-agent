from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "banking.db"


class FraudReportStore:
    """Read-only fraud report data access against the current SQLite schema."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH

    def is_self_account(self, user_id: str, account_number: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT 1
                FROM accounts
                WHERE user_id = ? AND account_number = ?
                LIMIT 1
                """,
                (user_id, account_number),
            ).fetchone()
            return row is not None
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
        tx_id = self._parse_transaction_ref(transaction_ref)
        params: list[object] = [user_id, reported_account_no]
        filters = [
            "user_id = ?",
            "recipient_account = ?",
            "LOWER(status) IN ('completed', 'success', 'successful')",
        ]

        if tx_id is not None:
            filters.append("id = ?")
            params.append(tx_id)

        conn = self._connect()
        try:
            rows = conn.execute(
                f"""
                SELECT id, user_id, source_account, recipient_name, recipient_account,
                       recipient_bank, amount, currency, category, transaction_type,
                       note, status, created_at
                FROM transactions
                WHERE {" AND ".join(filters)}
                ORDER BY created_at DESC
                LIMIT 10
                """,
                params,
            ).fetchall()
            transactions = [self._transaction_to_dict(row) for row in rows]
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
            row = conn.execute(
                """
                SELECT account_number, bank_name, reason, reported_at, severity
                FROM reported_accounts
                WHERE account_number = ?
                LIMIT 1
                """,
                (account_number,),
            ).fetchone()
            return dict(row) if row else None
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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _transaction_to_dict(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["transaction_ref"] = self.format_transaction_ref(data["id"])
        return data

    @staticmethod
    def format_transaction_ref(transaction_id: int | str) -> str:
        return f"TX-{transaction_id}"

    @staticmethod
    def _parse_transaction_ref(transaction_ref: str | None) -> int | None:
        if not transaction_ref:
            return None
        match = re.search(r"(\d+)", transaction_ref)
        return int(match.group(1)) if match else None

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
