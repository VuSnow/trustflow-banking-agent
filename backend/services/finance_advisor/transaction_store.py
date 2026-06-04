from __future__ import annotations

from datetime import datetime, timedelta
import re

import psycopg2
import psycopg2.extras

from backend.config import DATABASE_URL


def parse_lookback_days(message: str | None, default_days: int = 30) -> int:
    """Parse a simple lookback window from the user's message."""
    if not message:
        return default_days

    text = message.lower()
    if any(token in text for token in ("tháng này", "tháng trước", "this month", "last month")):
        return 30
    if any(token in text for token in ("tuần này", "this week", "last week")):
        return 7

    patterns = [
        (r"(\d+)\s*(ngày|day|days)", 1),
        (r"(\d+)\s*(tuần|week|weeks)", 7),
        (r"(\d+)\s*(tháng|month|months)", 30),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            return max(1, int(match.group(1)) * multiplier)

    return default_days


class FinanceTransactionStore:
    """Reads user transactions from the PostgreSQL database."""

    def load_user_transactions(self, user_id: str, lookback_days: int = 30) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.transaction_ref, t.cif_no, t.account_no, t.counterparty_name,
                           t.counterparty_account_no, t.counterparty_bank_code,
                           t.amount, t.currency, tc.category_name, t.direction,
                           t.description, t.status, t.transaction_time
                    FROM transactions t
                    LEFT JOIN transaction_categories tc ON t.category_id = tc.category_id
                    WHERE t.cif_no = %s AND t.transaction_time >= %s
                    ORDER BY t.transaction_time DESC
                    """,
                    (user_id, cutoff),
                )
                rows = cur.fetchall()

            # Map PG columns to the interface expected downstream
            results = []
            for row in rows:
                results.append({
                    "id": row["transaction_ref"],
                    "user_id": row["cif_no"],
                    "source_account": row["account_no"],
                    "recipient_name": row["counterparty_name"],
                    "recipient_account": row["counterparty_account_no"],
                    "recipient_bank": row["counterparty_bank_code"],
                    "amount": row["amount"],
                    "currency": row["currency"],
                    "category": row["category_name"],
                    "transaction_type": row["direction"],
                    "note": row["description"],
                    "status": row["status"],
                    "created_at": str(row["transaction_time"]) if row["transaction_time"] else None,
                })
            return results
        finally:
            conn.close()
