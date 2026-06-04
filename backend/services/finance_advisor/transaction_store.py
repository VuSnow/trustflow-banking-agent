from __future__ import annotations

from datetime import datetime, timedelta
import os
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "banking.db"


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
    """Reads user transactions from the existing SQLite database."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH

    def load_user_transactions(self, user_id: str, lookback_days: int = 30) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, user_id, source_account, recipient_name, recipient_account,
                       recipient_bank, amount, currency, category, transaction_type,
                       note, status, created_at
                FROM transactions
                WHERE user_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (user_id, cutoff),
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()
