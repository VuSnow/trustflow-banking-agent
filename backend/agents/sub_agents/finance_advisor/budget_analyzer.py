from __future__ import annotations

from collections import defaultdict

from backend.agents.sub_agents.finance_advisor.common import (
    DEFAULT_BUDGET_RATIOS,
    format_currency,
    to_int,
)
from backend.models import AgentTask, AgentTaskResult


class BudgetAnalyzerAgent:
    """Estimate budget pressure from observed income and spending."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "analyze_budget":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        transactions = task.constraints.get("categorized_transactions", [])
        subscriptions = task.constraints.get("subscriptions", [])

        income_total = 0
        spend_by_category = defaultdict(int)
        spend_total = 0

        for tx in transactions:
            amount = to_int(tx.get("amount"))
            if tx.get("flow") == "income":
                income_total += amount
                continue

            category = tx.get("normalized_category") or "other"
            spend_by_category[category] += amount
            spend_total += amount

        budget_base = income_total if income_total > 0 else spend_total * 1.15
        budget_by_category = {
            category: round(budget_base * ratio)
            for category, ratio in DEFAULT_BUDGET_RATIOS.items()
        }

        category_budget_status = []
        overspend_categories = []
        for category, budget_amount in budget_by_category.items():
            spent = spend_by_category.get(category, 0)
            variance = spent - budget_amount
            status = "within_budget" if variance <= 0 else "over_budget"
            entry = {
                "category": category,
                "spent": spent,
                "spent_label": format_currency(spent),
                "budget": budget_amount,
                "budget_label": format_currency(budget_amount),
                "variance": variance,
                "variance_label": format_currency(abs(variance)),
                "status": status,
            }
            category_budget_status.append(entry)
            if variance > 0:
                overspend_categories.append(entry)

        for category, spent in spend_by_category.items():
            if category in budget_by_category:
                continue
            entry = {
                "category": category,
                "spent": spent,
                "spent_label": format_currency(spent),
                "budget": 0,
                "budget_label": format_currency(0),
                "variance": spent,
                "variance_label": format_currency(spent),
                "status": "over_budget",
            }
            category_budget_status.append(entry)
            overspend_categories.append(entry)

        savings_rate = None
        if income_total > 0:
            savings_rate = max(0.0, (income_total - spend_total) / income_total)

        total_subscription_cost = sum(to_int(item.get("estimated_monthly_cost")) for item in subscriptions)

        return AgentTaskResult(
            status="success",
            result={
                "income_total": income_total,
                "income_total_label": format_currency(income_total),
                "spend_total": spend_total,
                "spend_total_label": format_currency(spend_total),
                "net_after_spend": income_total - spend_total,
                "net_after_spend_label": format_currency(income_total - spend_total),
                "savings_rate": savings_rate,
                "spend_by_category": dict(spend_by_category),
                "category_budget_status": category_budget_status,
                "overspend_categories": overspend_categories,
                "budget_base": round(budget_base),
                "subscription_monthly_total": total_subscription_cost,
            },
            confidence=0.92,
        )
