from __future__ import annotations

from collections import defaultdict

from backend.agents.sub_agents.finance_advisor.common import (
    format_currency,
    infer_category,
    is_income_transaction,
    to_int,
)
from backend.models import AgentTask, AgentTaskResult


class CategorizerAgent:
    """Normalize raw transactions into finance-friendly categories."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "categorize_transactions":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        transactions = task.constraints.get("transactions", [])
        categorized_transactions = []
        category_totals = defaultdict(int)
        income_total = 0
        expense_total = 0

        for tx in transactions:
            amount = to_int(tx.get("amount"))
            category = infer_category(tx)
            flow = "income" if is_income_transaction(tx) else "expense"

            if flow == "income":
                income_total += amount
            else:
                expense_total += amount

            category_totals[category] += amount
            categorized_transactions.append(
                {
                    **tx,
                    "normalized_category": category,
                    "flow": flow,
                    "counterparty": tx.get("recipient_name") or tx.get("note") or "Unknown",
                    "amount_vnd": amount,
                }
            )

        top_categories = sorted(
            category_totals.items(), key=lambda item: item[1], reverse=True
        )

        return AgentTaskResult(
            status="success",
            result={
                "categorized_transactions": categorized_transactions,
                "category_totals": dict(category_totals),
                "top_categories": [
                    {"category": category, "amount": amount, "amount_label": format_currency(amount)}
                    for category, amount in top_categories[:5]
                ],
                "income_total": income_total,
                "income_total_label": format_currency(income_total),
                "expense_total": expense_total,
                "expense_total_label": format_currency(expense_total),
                "net_cashflow": income_total - expense_total,
                "net_cashflow_label": format_currency(income_total - expense_total),
            },
            confidence=0.98,
        )
