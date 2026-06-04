from __future__ import annotations

from backend.agents.sub_agents.finance_advisor.common import format_currency, to_int
from backend.models import AgentTask, AgentTaskResult


class SavingsOpportunityAgent:
    """Turn analysis findings into concrete savings actions."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "find_savings_opportunities":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        budget_analysis = task.constraints.get("budget_analysis", {})
        subscriptions = task.constraints.get("subscriptions", [])
        patterns = task.constraints.get("patterns", [])

        opportunities = []
        estimated_monthly_savings = 0

        for sub in subscriptions[:5]:
            amount = to_int(sub.get("estimated_monthly_cost"))
            if amount <= 0:
                continue
            estimated_monthly_savings += amount
            opportunities.append(
                {
                    "type": "subscription_review",
                    "title": f"Rà soát {sub.get('name')}",
                    "estimated_monthly_savings": amount,
                    "estimated_monthly_savings_label": format_currency(amount),
                    "action": "Hủy hoặc thay thế nếu không còn dùng thường xuyên.",
                }
            )

        for overspend in budget_analysis.get("overspend_categories", [])[:3]:
            variance = to_int(overspend.get("variance"))
            if variance <= 0:
                continue
            category = str(overspend.get("category") or "").lower()
            multiplier = 0.05 if category == "transfers" else 0.2
            estimated_cut = round(variance * multiplier)
            estimated_monthly_savings += estimated_cut
            opportunities.append(
                {
                    "type": "budget_trim",
                    "title": f"Giảm chi tiêu ở {overspend.get('category')}",
                    "estimated_monthly_savings": estimated_cut,
                    "estimated_monthly_savings_label": format_currency(estimated_cut),
                    "action": "Đặt trần chi tiêu thấp hơn và cắt 20% phần vượt ngân sách.",
                }
            )

        if patterns:
            concentration = next(
                (pattern for pattern in patterns if pattern.get("type") == "spending_concentration"),
                None,
            )
            if concentration:
                opportunities.append(
                    {
                        "type": "spending_concentration",
                        "title": "Giảm phụ thuộc vào một nhóm chi tiêu lớn",
                        "estimated_monthly_savings": 0,
                        "estimated_monthly_savings_label": format_currency(0),
                        "action": concentration.get("message"),
                    }
                )

        if not opportunities:
            opportunities.append(
                {
                    "type": "maintenance",
                    "title": "Thiết lập chuyển tiền tự động sang tiết kiệm",
                    "estimated_monthly_savings": round(max(0, budget_analysis.get("income_total", 0) * 0.1)),
                    "estimated_monthly_savings_label": format_currency(
                        round(max(0, budget_analysis.get("income_total", 0) * 0.1))
                    ),
                    "action": "Tự động chuyển 5-10% thu nhập sang tài khoản tiết kiệm ngay khi nhận lương.",
                }
            )

        opportunities = sorted(
            opportunities,
            key=lambda item: item["estimated_monthly_savings"],
            reverse=True,
        )

        return AgentTaskResult(
            status="success",
            result={
                "opportunities": opportunities,
                "total_estimated_monthly_savings": estimated_monthly_savings,
                "total_estimated_monthly_savings_label": format_currency(
                    estimated_monthly_savings
                ),
            },
            confidence=0.9,
        )
