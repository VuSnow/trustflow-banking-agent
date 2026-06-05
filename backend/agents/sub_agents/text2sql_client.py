"""Text2SQL Agent client — calls external text2sql-agent service.

Translates AgentTask into a natural language question, sends to the
text2sql-agent REST API, and maps the response back to AgentTaskResult.
"""
import logging

import httpx

from backend.config import TEXT2SQL_AGENT_URL
from backend.models import AgentTask, AgentTaskResult

logger = logging.getLogger(__name__)


class Text2SQLSubAgent:
    """Sub-agent that delegates evidence queries to external text2sql-agent service.

    Supported task_type: "query_evidence"
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or TEXT2SQL_AGENT_URL

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        """Execute a query_evidence task via text2sql-agent.

        constraints expected:
            query_goal: str — "find_previous_transfer" | "find_top_recipient" | free text
            user_id: str
            recipient_hint: str | None
            period: str | None — "last_month", "last_week", etc.
            metric: str | None — "total_amount", "frequency"
            amount: int | None
        """
        if task.task_type != "query_evidence":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        question = self._build_question(task.constraints)
        logger.info(f"[TEXT2SQL] Sending question: {question}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/query/execute",
                    json={"question": question, "execute": True},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[TEXT2SQL] HTTP error: {e}")
            return AgentTaskResult(
                status="failed",
                result={"error": f"text2sql-agent returned {e.response.status_code}"},
            )
        except httpx.RequestError as e:
            logger.error(f"[TEXT2SQL] Connection error: {e}")
            return AgentTaskResult(
                status="failed",
                result={"error": f"Cannot reach text2sql-agent: {e}"},
            )

        return self._map_response(data)

    def _build_question(self, constraints: dict) -> str:
        """Convert structured constraints to natural language question."""
        goal = constraints.get("query_goal", "")
        user_id = constraints.get("user_id", "")
        recipient_hint = constraints.get("recipient_hint")
        period = constraints.get("period")
        metric = constraints.get("metric")
        amount = constraints.get("amount")

        parts: list[str] = []

        if goal == "find_previous_transfer":
            parts.append(f"Tìm giao dịch chuyển tiền trước đó của user {user_id}")
            if recipient_hint:
                parts.append(f"cho người nhận tên '{recipient_hint}'")
            if period:
                parts.append(f"trong khoảng {period}")
            if amount:
                parts.append(f"số tiền {amount}")

        elif goal == "find_top_recipient":
            parts.append(f"Tìm người nhận tiền nhiều nhất của user {user_id}")
            if period:
                parts.append(f"trong khoảng {period}")
            if metric == "total_amount":
                parts.append("theo tổng số tiền")
            elif metric == "frequency":
                parts.append("theo số lần giao dịch")

        else:
            # Free text or generic fallback — pass question directly
            question = constraints.get("question")
            if question:
                parts.append(question)
            else:
                parts.append(f"Query for user {user_id}: {goal}")
                if recipient_hint:
                    parts.append(f"recipient={recipient_hint}")
                if period:
                    parts.append(f"period={period}")

        return " ".join(parts)

    def _map_response(self, data: dict) -> AgentTaskResult:
        """Map text2sql-agent QueryResponse to AgentTaskResult."""
        status = data.get("status")

        if status == "success":
            rows = data.get("results") or []
            return AgentTaskResult(
                status="success",
                result={
                    "rows": rows,
                    "results": rows,
                    "sql": data.get("sql", ""),
                    "row_count": data.get("row_count", len(rows)),
                },
                confidence=0.75,
            )

        elif status == "needs_clarification":
            return AgentTaskResult(
                status="needs_clarification",
                result={
                    "message": "\n".join(data.get("questions", ["Cần thêm thông tin."])),
                    "questions": data.get("questions", []),
                },
                confidence=0.0,
            )

        elif status == "blocked":
            return AgentTaskResult(
                status="failed",
                result={"error": data.get("reason", "Query blocked")},
                confidence=0.0,
            )

        else:  # error or unknown
            return AgentTaskResult(
                status="failed",
                result={"error": data.get("error", "Unknown error from text2sql-agent")},
                confidence=0.0,
            )
