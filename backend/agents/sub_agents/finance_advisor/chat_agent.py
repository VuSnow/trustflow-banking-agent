from __future__ import annotations

import json

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import AgentTask, AgentTaskResult
from backend.prompts.finance_advice import (
    FINANCE_CHAT_SYSTEM_PROMPT,
    FINANCE_CHAT_USER_TEMPLATE,
)


class ChatAgent:
    """Turn finance analysis into a readable advisory response."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or (
            AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        )

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type != "compose_advice":
            return AgentTaskResult(
                status="failed",
                result={"error": f"Unknown task_type: {task.task_type}"},
            )

        message = task.constraints.get("message", "")
        lookback_days = task.constraints.get("lookback_days", 30)
        analysis = task.constraints.get("analysis", {})

        if self.client is not None:
            try:
                response = await self.client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": FINANCE_CHAT_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": FINANCE_CHAT_USER_TEMPLATE.format(
                                message=message,
                                lookback_days=lookback_days,
                                analysis_json=json.dumps(
                                    analysis, ensure_ascii=False, indent=2
                                ),
                            ),
                        },
                    ],
                    temperature=0.2,
                )
                advice = response.choices[0].message.content.strip()
                return AgentTaskResult(
                    status="success",
                    result={"advice": advice, "mode": "llm"},
                    confidence=0.92,
                )
            except Exception:
                pass

        advice_lines = [
            "Tôi đã phân tích chi tiêu gần đây của bạn.",
        ]

        if analysis.get("transaction_count", 0) == 0:
            advice_lines.append(
                "- Không tìm thấy giao dịch nào trong khoảng thời gian này."
            )
            advice_lines.append(
                "- Bạn có thể thử mở rộng khung phân tích lên 2-3 tháng để có cái nhìn rõ hơn."
            )

        if analysis.get("income_total", 0) > 0:
            advice_lines.append(
                f"- Thu nhập ước tính: {analysis.get('income_total_label', '0 VND')}"
            )
        advice_lines.append(
            f"- Tổng chi tiêu: {analysis.get('spend_total_label', '0 VND')}"
        )

        top_categories = analysis.get("top_categories", [])
        if top_categories:
            advice_lines.append("- Nhóm chi tiêu nổi bật:")
            for item in top_categories[:3]:
                advice_lines.append(
                    f"  - {item.get('category')}: {item.get('amount_label')}"
                )

        opportunities = task.constraints.get("opportunities", [])
        if opportunities:
            advice_lines.append("- Cơ hội tiết kiệm:")
            for item in opportunities[:3]:
                advice_lines.append(
                    f"  - {item.get('title')} (ước tính {item.get('estimated_monthly_savings_label')})"
                )

        advice_lines.append(
            "Gợi ý tiếp theo: xem lại các khoản lặp lại, đặt trần cho nhóm chi tiêu lớn, "
            "và tự động chuyển một phần thu nhập sang tiết kiệm ngay khi nhận lương."
        )

        return AgentTaskResult(
            status="success",
            result={"advice": "\n".join(advice_lines), "mode": "fallback"},
            confidence=0.88,
        )
