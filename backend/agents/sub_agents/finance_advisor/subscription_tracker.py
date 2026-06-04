from __future__ import annotations

from collections import defaultdict
from statistics import mean

from backend.agents.sub_agents.finance_advisor.common import (
    counterparty_key,
    format_currency,
    normalize_text,
    parse_created_at,
    to_int,
)
from backend.models import AgentTask, AgentTaskResult


class SubscriptionTrackerAgent:
    """Identify recurring payment patterns that look like subscriptions."""

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "track_subscriptions":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        transactions = task.constraints.get("categorized_transactions", [])
        grouped = defaultdict(list)
        for tx in transactions:
            if tx.get("flow") == "income":
                continue
            normalized_category = normalize_text(tx.get("normalized_category"))
            raw_text = normalize_text(
                " ".join(
                    [
                        tx.get("transaction_type") or "",
                        tx.get("category") or "",
                        tx.get("note") or "",
                    ]
                )
            )
            eligible = normalized_category in {"bills", "subscriptions", "entertainment"} or any(
                keyword in raw_text
                for keyword in (
                    "subscription",
                    "membership",
                    "netflix",
                    "spotify",
                    "youtube premium",
                    "bill",
                    "electricity",
                    "water",
                    "internet",
                    "phone",
                    "topup",
                )
            )
            if not eligible:
                continue
            key = counterparty_key(tx)
            if key == "unknown":
                continue
            grouped[key].append(tx)

        subscriptions = []
        for key, items in grouped.items():
            if len(items) < 2:
                continue

            items_with_dates = [
                (parse_created_at(tx), to_int(tx.get("amount")), tx)
                for tx in items
                if parse_created_at(tx) is not None
            ]
            if len(items_with_dates) < 2:
                continue

            items_with_dates.sort(key=lambda item: item[0])
            intervals = []
            for idx in range(1, len(items_with_dates)):
                intervals.append((items_with_dates[idx][0] - items_with_dates[idx - 1][0]).days)

            average_interval = mean(intervals) if intervals else None
            amounts = [amount for _, amount, _ in items_with_dates]
            average_amount = mean(amounts) if amounts else 0
            amount_variance = (
                max(amounts) - min(amounts)
                if amounts
                else 0
            )

            looks_recurring = False
            cadence = "irregular"
            if average_interval is not None:
                if 25 <= average_interval <= 35:
                    looks_recurring = True
                    cadence = "monthly"
                elif 6 <= average_interval <= 8:
                    looks_recurring = True
                    cadence = "weekly"
                elif 13 <= average_interval <= 18:
                    looks_recurring = True
                    cadence = "biweekly"

            if looks_recurring or (len(items_with_dates) >= 3 and amount_variance <= average_amount * 0.15):
                subscriptions.append(
                    {
                        "name": key,
                        "count": len(items_with_dates),
                        "cadence": cadence,
                        "average_amount": round(average_amount),
                        "average_amount_label": format_currency(average_amount),
                        "last_seen": items_with_dates[-1][0].isoformat(sep=" ", timespec="seconds"),
                        "estimated_monthly_cost": round(
                            average_amount
                            * (1 if cadence == "monthly" else 4.33 if cadence == "weekly" else 2.15 if cadence == "biweekly" else 1)
                        ),
                    }
                )

        subscriptions.sort(key=lambda item: item["estimated_monthly_cost"], reverse=True)

        return AgentTaskResult(
            status="success",
            result={
                "subscriptions": subscriptions,
                "subscription_count": len(subscriptions),
                "subscription_monthly_total": sum(
                    item["estimated_monthly_cost"] for item in subscriptions
                ),
            },
            confidence=0.87,
        )
