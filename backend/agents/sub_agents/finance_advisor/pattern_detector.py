from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from backend.agents.sub_agents.finance_advisor.common import (
    counterparty_key,
    format_currency,
    parse_created_at,
    to_int,
)
from backend.models import AgentTask, AgentTaskResult


class PatternDetectorAgent:
    """Detect concentration, repeated spend, and unusual shifts."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "detect_patterns":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        transactions = task.constraints.get("categorized_transactions", [])
        if not transactions:
            return AgentTaskResult(
                status="success",
                result={
                    "patterns": [],
                    "top_counterparties": [],
                    "spike_flags": [],
                    "concentration_note": "Không có giao dịch để phân tích mẫu.",
                },
                confidence=0.9,
            )

        count_by_counterparty = defaultdict(int)
        amount_by_counterparty = defaultdict(int)
        timeline = []

        for tx in transactions:
            key = counterparty_key(tx)
            amount = to_int(tx.get("amount"))
            count_by_counterparty[key] += 1
            amount_by_counterparty[key] += amount
            parsed = parse_created_at(tx)
            if parsed:
                timeline.append((parsed, amount, tx))

        top_counterparties = sorted(
            amount_by_counterparty.items(), key=lambda item: item[1], reverse=True
        )[:5]
        total_spend = sum(
            to_int(tx.get("amount"))
            for tx in transactions
            if tx.get("flow") != "income"
        )
        top_share = (
            top_counterparties[0][1] / total_spend if top_counterparties and total_spend else 0
        )

        patterns = []
        if top_share >= 0.25:
            patterns.append(
                {
                    "type": "spending_concentration",
                    "message": f"Một đối tượng chiếm {top_share:.0%} tổng chi tiêu gần đây.",
                }
            )

        for key, count in sorted(count_by_counterparty.items(), key=lambda item: item[1], reverse=True)[:3]:
            if count >= 2:
                patterns.append(
                    {
                        "type": "repeated_counterparty",
                        "counterparty": key,
                        "message": f"{key} xuất hiện {count} lần trong khoảng phân tích.",
                    }
                )

        spike_flags = []
        now = datetime.now()
        recent_window = now - timedelta(days=7)
        recent_spend = sum(
            amount
            for parsed, amount, tx in timeline
            if parsed >= recent_window and tx.get("flow") != "income"
        )
        previous_spend = sum(
            amount
            for parsed, amount, tx in timeline
            if parsed < recent_window and tx.get("flow") != "income"
        )

        if previous_spend > 0 and recent_spend > previous_spend * 1.5:
            spike_flags.append(
                {
                    "type": "weekly_spike",
                    "message": (
                        f"Chi tiêu 7 ngày gần nhất ({format_currency(recent_spend)}) "
                        f"cao hơn đáng kể so với phần còn lại ({format_currency(previous_spend)})."
                    ),
                }
            )

        return AgentTaskResult(
            status="success",
            result={
                "patterns": patterns,
                "top_counterparties": [
                    {
                        "counterparty": key,
                        "amount": amount,
                        "amount_label": format_currency(amount),
                        "count": count_by_counterparty[key],
                    }
                    for key, amount in top_counterparties
                ],
                "spike_flags": spike_flags,
                "total_spend": total_spend,
            },
            confidence=0.9,
        )
