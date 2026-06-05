"""FraudScreeningAgent — checks if an account has been reported as fraudulent.

Used by:
- FraudReportAgent: CHECK_ACCOUNT_RISK operation
- Orchestrator/QA: when user asks "is account X a scam?"

Note: TransactionAgent uses its own check_fraud_risk tool (direct DB query)
rather than this sub-agent.
"""
from __future__ import annotations

import logging

from backend.models import AgentTask, AgentTaskResult
from backend.services.fraud_report import FraudReportStore

logger = logging.getLogger(__name__)


class FraudScreeningAgent:
    """Sub-agent that screens an account against reported_accounts."""

    def __init__(self, store: FraudReportStore | None = None):
        self.store = store or FraudReportStore()

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "check_account":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
                confidence=0.0,
            )

        account_no = task.constraints.get("account_no")
        if not account_no:
            return AgentTaskResult(
                status="failed",
                result={"error": "account_no is required"},
                confidence=0.0,
            )

        reported = self.store.get_reported_account(account_no)

        if not reported:
            return AgentTaskResult(
                status="success",
                result={
                    "is_reported": False,
                    "risk_level": None,
                    "bank_code": None,
                    "message": f"Tài khoản {account_no} chưa có báo cáo lừa đảo nào trong hệ thống.",
                },
                confidence=1.0,
            )

        risk_level = reported.get("risk_level", "LOW")
        report_count = reported.get("valid_report_count", 0)
        risk_score = reported.get("risk_score")

        if risk_level in ("HIGH", "CRITICAL"):
            message = (
                f"⚠️ Cảnh báo: Tài khoản {account_no} đã bị báo cáo lừa đảo "
                f"({risk_level}, {report_count} lần báo cáo). "
                f"Bạn nên cẩn trọng và không nên chuyển tiền cho tài khoản này."
            )
        elif risk_level == "MEDIUM":
            message = (
                f"Lưu ý: Tài khoản {account_no} có lịch sử bị báo cáo "
                f"(mức {risk_level}, {report_count} lần). Hãy cẩn thận khi giao dịch."
            )
        else:
            message = (
                f"Tài khoản {account_no} có 1 báo cáo ở mức thấp. "
                f"Chưa có đủ bằng chứng để kết luận."
            )

        return AgentTaskResult(
            status="success",
            result={
                "is_reported": True,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "report_count": report_count,
                "bank_code": reported.get("bank_code"),
                "message": message,
            },
            confidence=1.0,
        )
