from __future__ import annotations

from backend.models import AgentTask, AgentTaskResult
from backend.services.fraud_report import FraudReportStore


class FraudVerificationAgent:
    """Verify fraud-report evidence from the current banking database."""

    def __init__(self, store: FraudReportStore | None = None):
        self.store = store or FraudReportStore()

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "verify_fraud_report":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
                confidence=0.0,
            )

        user_id = task.constraints.get("user_id")
        reported_account_no = task.constraints.get("reported_account_no")
        reported_bank_code = task.constraints.get("reported_bank_code")
        transaction_ref = task.constraints.get("transaction_ref")

        if not user_id or not reported_account_no:
            return AgentTaskResult(
                status="failed",
                result={"error": "user_id and reported_account_no are required"},
                confidence=0.0,
            )

        is_self_report = self.store.is_self_account(user_id, reported_account_no)
        matching_transactions = self.store.find_matching_transactions(
            user_id=user_id,
            reported_account_no=reported_account_no,
            reported_bank_code=reported_bank_code,
            transaction_ref=transaction_ref,
        )
        reported_account = self.store.get_reported_account(reported_account_no)
        primary_transaction = matching_transactions[0] if matching_transactions else None

        return AgentTaskResult(
            status="success",
            result={
                "is_self_report": is_self_report,
                "transaction_found": primary_transaction is not None,
                "transaction_ref": primary_transaction.get("transaction_ref") if primary_transaction else None,
                "transaction_amount": primary_transaction.get("amount") if primary_transaction else None,
                "transaction_currency": primary_transaction.get("currency") if primary_transaction else None,
                "transaction_time": primary_transaction.get("created_at") if primary_transaction else None,
                "matching_transactions": matching_transactions,
                "existing_reports_count": 1 if reported_account else 0,
                "reported_account_risk": reported_account.get("severity") if reported_account else None,
                "reported_account_record": reported_account,
            },
            confidence=1.0,
        )
