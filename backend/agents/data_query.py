"""DataQueryAgent — domain agent for DATA_QUERY intent.

Delegates natural language data questions to the external text2sql-agent
service. Handles clarification flow and returns structured results.
"""
from __future__ import annotations

import logging

from backend.agents.sub_agents.text2sql_client import Text2SQLSubAgent
from backend.models import AgentTask, AgentTaskResult, DomainAgentOutput

logger = logging.getLogger(__name__)


class DataQueryAgent:
    """Domain agent that translates user data questions into SQL via text2sql-agent."""

    def __init__(self):
        self.text2sql = Text2SQLSubAgent()

    async def run(
        self,
        message: str,
        user_id: str,
        session_id: str,
        history: list[dict] | None = None,
        pipeline_context: dict | None = None,
    ) -> DomainAgentOutput:
        """Run data query via text2sql-agent.

        Args:
            message: User's natural language question.
            user_id: Customer identifier (injected into query context).
            session_id: Chat session ID.
            history: Recent chat history.
            pipeline_context: Context from previous pipeline steps.
        """
        trace = ["data_query_agent"]

        # Build the question with user context
        question = self._build_question(message, user_id, pipeline_context)

        task = AgentTask(
            task_type="query_evidence",
            context={"user_id": user_id, "session_id": session_id},
            constraints={
                "query_goal": "free_text",
                "user_id": user_id,
                "question": question,
            },
        )

        result: AgentTaskResult = await self.text2sql.execute_task(task)
        trace.append(f"text2sql:{result.status}")

        if result.status == "needs_clarification":
            questions = result.result.get("questions", [])
            msg = "\n".join(f"- {q}" for q in questions) if questions else "Bạn có thể mô tả rõ hơn được không?"
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=msg,
                delegation_trace=trace,
            )

        if result.status == "failed":
            error = result.result.get("error", "Không thể truy vấn dữ liệu.")
            return DomainAgentOutput(
                status="info_response",
                info_response=f"Xin lỗi, tôi không thể lấy dữ liệu: {error}",
                response_data={"error": error, "task_type": "DATA_QUERY"},
                delegation_trace=trace,
            )

        # Success
        query_results = result.result.get("results", [])
        sql = result.result.get("sql", "")
        row_count = result.result.get("row_count", len(query_results) if query_results else 0)

        # Format response
        summary = self._format_results(query_results, message)

        return DomainAgentOutput(
            status="info_response",
            info_response=summary,
            response_data={
                "task_type": "DATA_QUERY",
                "sql": sql,
                "results": query_results,
                "row_count": row_count,
            },
            delegation_trace=trace,
        )

    def _build_question(self, message: str, user_id: str, pipeline_context: dict | None) -> str:
        """Enrich question with user context and pipeline data."""
        parts = [f"Với customer có cif_no = '{user_id}': {message}"]
        if pipeline_context:
            prev_data = pipeline_context.get("previous_results")
            if prev_data:
                parts.append(f"\nContext từ bước trước: {prev_data}")
        return "\n".join(parts)

    def _format_results(self, results: list[dict], original_question: str) -> str:
        """Format query results into user-friendly Vietnamese text."""
        if not results:
            return "Không tìm thấy dữ liệu phù hợp với yêu cầu của bạn."

        if len(results) == 1:
            row = results[0]
            parts = []
            for key, value in row.items():
                parts.append(f"- {key}: {value}")
            return "Kết quả:\n" + "\n".join(parts)

        # Multiple rows — summarize
        header = f"Tìm thấy {len(results)} kết quả:\n"
        rows = []
        for i, row in enumerate(results[:10], 1):
            row_str = ", ".join(f"{k}: {v}" for k, v in row.items())
            rows.append(f"{i}. {row_str}")

        summary = header + "\n".join(rows)
        if len(results) > 10:
            summary += f"\n... và {len(results) - 10} kết quả khác."
        return summary
