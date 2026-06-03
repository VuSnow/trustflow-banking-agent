"""RecipientResolutionAgent — resolves recipient_hint to verified candidate(s).

Phase 3: direct DB queries only (no Text2SQL, no LLM).
Data sources:
1. beneficiaries table — saved recipients with nicknames
2. transactions table — historical recipients (fallback)
"""
import json
import sqlite3
import os
import logging

from backend.models import AgentTask, AgentTaskResult

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..",
                       "..", "data", "banking.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class RecipientResolutionAgent:
    """Resolves recipient hints to verified recipient candidates."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type == "resolve_by_name":
            return self._resolve_by_name(task)
        elif task.task_type == "resolve_by_account":
            return self._resolve_by_account(task)
        elif task.task_type == "resolve_with_evidence":
            return self._resolve_with_evidence(task)
        else:
            return AgentTaskResult(status="failed", result={"error": f"Unknown task_type: {task.task_type}"})

    def _resolve_by_name(self, task: AgentTask) -> AgentTaskResult:
        """
        1. Query beneficiaries WHERE user_id=? AND (name LIKE ? OR nicknames LIKE ?)
        2. If 0 results → query transactions for DISTINCT recipients matching name
        3. Deduplicate by account_number
        4. Return candidates
        """
        user_id = task.constraints["user_id"]
        name = task.constraints["name"]
        pattern = f"%{name}%"

        conn = _get_connection()
        try:
            # Step 1: beneficiaries
            rows = conn.execute(
                """SELECT name, nicknames, account_number, bank_name
                   FROM beneficiaries
                   WHERE user_id = ? AND (name LIKE ? OR nicknames LIKE ?)""",
                (user_id, pattern, pattern),
            ).fetchall()

            candidates = []
            for row in rows:
                candidates.append({
                    "name": row["name"],
                    "nicknames": json.loads(row["nicknames"]) if row["nicknames"] else [],
                    "account_number": row["account_number"],
                    "bank_name": row["bank_name"],
                    "source": "saved_beneficiary",
                })

            # Step 2: fallback to transaction history if no beneficiary match
            if not candidates:
                tx_rows = conn.execute(
                    """SELECT DISTINCT recipient_name, recipient_account, recipient_bank
                       FROM transactions
                       WHERE user_id = ? AND recipient_name LIKE ?
                       ORDER BY created_at DESC""",
                    (user_id, pattern),
                ).fetchall()

                seen_accounts = set()
                for row in tx_rows:
                    if row["recipient_account"] not in seen_accounts:
                        seen_accounts.add(row["recipient_account"])
                        candidates.append({
                            "name": row["recipient_name"],
                            "nicknames": [],
                            "account_number": row["recipient_account"],
                            "bank_name": row["recipient_bank"],
                            "source": "transaction_history",
                        })
        finally:
            conn.close()

        # Decision
        if len(candidates) == 0:
            return AgentTaskResult(
                status="needs_clarification",
                result={
                    "message": f"Không tìm thấy người nhận nào tên '{name}'. Vui lòng cung cấp số tài khoản."},
                confidence=0.0,
            )
        elif len(candidates) == 1:
            return AgentTaskResult(
                status="success",
                result={
                    "recipient_name": candidates[0]["name"],
                    "account_number": candidates[0]["account_number"],
                    "bank_name": candidates[0]["bank_name"],
                    "source": candidates[0]["source"],
                },
                confidence=0.95 if candidates[0]["source"] == "saved_beneficiary" else 0.8,
            )
        else:
            # Multiple candidates → clarification
            msg_lines = [
                f"Tìm thấy {len(candidates)} người nhận khớp '{name}'. Bạn muốn chuyển cho ai?"]
            for i, c in enumerate(candidates, 1):
                masked = c["account_number"][-4:].rjust(
                    len(c["account_number"]), "*")
                msg_lines.append(
                    f"{i}. {c['name']} - {c['bank_name']} ...{c['account_number'][-4:]}")
            return AgentTaskResult(
                status="needs_clarification",
                result={"message": "\n".join(
                    msg_lines), "candidates": candidates},
                confidence=0.5,
            )

    def _resolve_by_account(self, task: AgentTask) -> AgentTaskResult:
        """Exact match by account number in beneficiaries or transaction history."""
        user_id = task.constraints["user_id"]
        account = task.constraints["account_number"]

        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT name, account_number, bank_name
                   FROM beneficiaries
                   WHERE user_id = ? AND account_number = ?""",
                (user_id, account),
            ).fetchone()

            if row:
                return AgentTaskResult(
                    status="success",
                    result={
                        "recipient_name": row["name"],
                        "account_number": row["account_number"],
                        "bank_name": row["bank_name"],
                        "source": "saved_beneficiary",
                    },
                    confidence=0.98,
                )

            # Fallback: transaction history
            tx_row = conn.execute(
                """SELECT DISTINCT recipient_name, recipient_account, recipient_bank
                   FROM transactions
                   WHERE user_id = ? AND recipient_account = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, account),
            ).fetchone()

            if tx_row:
                return AgentTaskResult(
                    status="success",
                    result={
                        "recipient_name": tx_row["recipient_name"],
                        "account_number": tx_row["recipient_account"],
                        "bank_name": tx_row["recipient_bank"],
                        "source": "transaction_history",
                    },
                    confidence=0.85,
                )
        finally:
            conn.close()

        return AgentTaskResult(
            status="needs_clarification",
            result={
                "message": f"Không tìm thấy tài khoản {account}. Vui lòng kiểm tra lại."},
            confidence=0.0,
        )

    def _resolve_with_evidence(self, task: AgentTask) -> AgentTaskResult:
        """Verify evidence rows from Text2SQL against beneficiaries/transactions.

        constraints: {user_id, evidence_rows or rows: [...]}

        Logic:
        1. Extract account_number/recipient_name from evidence rows
        2. Verify account exists in beneficiaries or past transactions for this user
        3. Exactly 1 verified → success (auto-resolve)
        4. Multiple verified → needs_clarification with candidate list
        5. 0 verified → needs_clarification
        """
        user_id = task.constraints["user_id"]
        evidence_rows = (
            task.constraints.get("evidence_rows")
            or task.constraints.get("rows")
            or []
        )

        if not evidence_rows:
            return AgentTaskResult(
                status="needs_clarification",
                result={"message": "Không tìm thấy dữ liệu lịch sử phù hợp."},
                confidence=0.0,
            )

        # Extract candidate accounts from evidence
        candidates = []
        seen_accounts: set[str] = set()

        for row in evidence_rows:
            account = row.get("recipient_account") or row.get("account_number")
            if not account or account in seen_accounts:
                continue
            seen_accounts.add(account)
            candidates.append({
                "account_number": account,
                "recipient_name": row.get("recipient_name") or row.get("name"),
                "bank_name": row.get("recipient_bank") or row.get("bank_name"),
            })

        if not candidates:
            return AgentTaskResult(
                status="needs_clarification",
                result={"message": "Không thể xác định người nhận từ dữ liệu lịch sử."},
                confidence=0.0,
            )

        # Verify each candidate against local DB
        verified = []
        conn = _get_connection()
        try:
            for c in candidates:
                # Check beneficiaries first
                row = conn.execute(
                    """SELECT name, account_number, bank_name
                       FROM beneficiaries
                       WHERE user_id = ? AND account_number = ?""",
                    (user_id, c["account_number"]),
                ).fetchone()

                if row:
                    verified.append({
                        "recipient_name": row["name"],
                        "account_number": row["account_number"],
                        "bank_name": row["bank_name"],
                        "source": "saved_beneficiary",
                        "confidence": 0.95,
                    })
                    continue

                # Fallback: transaction history
                tx_row = conn.execute(
                    """SELECT DISTINCT recipient_name, recipient_account, recipient_bank
                       FROM transactions
                       WHERE user_id = ? AND recipient_account = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (user_id, c["account_number"]),
                ).fetchone()

                if tx_row:
                    verified.append({
                        "recipient_name": tx_row["recipient_name"],
                        "account_number": tx_row["recipient_account"],
                        "bank_name": tx_row["recipient_bank"],
                        "source": "transaction_history",
                        "confidence": 0.80,
                    })
        finally:
            conn.close()

        # Decision
        if len(verified) == 0:
            return AgentTaskResult(
                status="needs_clarification",
                result={"message": "Tài khoản từ lịch sử không khớp với dữ liệu đã lưu. Vui lòng xác nhận người nhận."},
                confidence=0.0,
            )
        elif len(verified) == 1:
            return AgentTaskResult(
                status="success",
                result={
                    "recipient_name": verified[0]["recipient_name"],
                    "account_number": verified[0]["account_number"],
                    "bank_name": verified[0]["bank_name"],
                    "source": f"evidence_verified:{verified[0]['source']}",
                },
                confidence=verified[0]["confidence"],
            )
        else:
            # Multiple verified → ask user
            msg_lines = [f"Tìm thấy {len(verified)} người nhận từ lịch sử. Bạn muốn chuyển cho ai?"]
            for i, v in enumerate(verified, 1):
                msg_lines.append(
                    f"{i}. {v['recipient_name']} - {v['bank_name']} ...{v['account_number'][-4:]}"
                )
            return AgentTaskResult(
                status="needs_clarification",
                result={"message": "\n".join(msg_lines), "candidates": verified},
                confidence=0.5,
            )
