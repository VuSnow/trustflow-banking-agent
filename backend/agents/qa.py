from __future__ import annotations

import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import DomainAgentOutput
from backend.prompts.qa import QA_SYSTEM_PROMPT, QA_USER_TEMPLATE

logger = logging.getLogger(__name__)


class QAAgent:
    """Domain agent for QA intent. Returns a direct natural-language answer."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or (
            AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        )

    async def run(self, message: str, user_id: str, session_id: str, history: list[dict] | None = None, pipeline_context: dict | None = None) -> DomainAgentOutput:
        if self.client is not None:
            try:
                response = await self.client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": QA_SYSTEM_PROMPT},
                        {"role": "user", "content": QA_USER_TEMPLATE.format(message=message)},
                    ],
                    temperature=0.2,
                )
                answer = (response.choices[0].message.content or "").strip()
                if answer:
                    return DomainAgentOutput(
                        status="info_response",
                        info_response=answer,
                        response_data={
                            "answer": answer,
                            "mode": "llm",
                            "task_type": "QA",
                        },
                    )
            except Exception:
                logger.warning("[QA] LLM generation failed; using fallback", exc_info=False)

        fallback = _fallback_answer(message)
        return DomainAgentOutput(
            status="info_response",
            info_response=fallback,
            response_data={
                "answer": fallback,
                "mode": "fallback",
                "task_type": "QA",
            },
        )


def _fallback_answer(message: str) -> str:
    text = message.strip().lower()
    if not text:
        return "Tôi có thể giúp gì cho câu hỏi ngân hàng của bạn?"
    if text in {"hi", "hello", "hey", "xin chao", "xin chào"}:
        return "Xin chào. Tôi có thể giúp gì cho bạn?"
    return "Tôi có thể hỗ trợ các câu hỏi về ngân hàng, phí, chính sách và thông tin sản phẩm. Bạn muốn hỏi gì?"
