"""TransactionAgent — domain agent for TRANSACTION intent.

Phase 3: hardcoded resolution flow (extract → resolve → build draft).
Phase 6: refactored to dynamic LLM planning.
"""
import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import (
    TransactionExtraction,
    ActionDraft,
    AgentTask,
    DomainAgentOutput,
)
from backend.prompts.transaction import TRANSACTION_SYSTEM_PROMPT, TRANSACTION_USER_TEMPLATE
from backend.agents.sub_agents.recipient_resolution import RecipientResolutionAgent

logger = logging.getLogger(__name__)


class TransactionAgent:
    """Domain agent for TRANSACTION intent."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.recipient_agent = RecipientResolutionAgent()

    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        trace = []

        # 1. LLM extract → TransactionExtraction
        extraction = await self._extract_entities(message)
        trace.append("extract_entities")
        logger.info(f"[TX EXTRACT] {extraction.model_dump_json()}")

        # 2. Early exit if extraction needs clarification (unresolvable)
        if extraction.needs_clarification and not extraction.resolvable_fields:
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=extraction.clarification_reason or "Vui lòng cung cấp thêm thông tin.",
                delegation_trace=trace,
            )

        # 3. Resolve recipient
        if extraction.recipient_hint and not extraction.recipient_account:
            result = await self.recipient_agent.execute_task(
                AgentTask(
                    task_type="resolve_by_name",
                    constraints={
                        "name": extraction.recipient_hint, "user_id": user_id},
                )
            )
            trace.append("resolve_recipient")

            if result.status == "success":
                extraction.recipient_account = result.result["account_number"]
                extraction.recipient_bank = result.result["bank_name"]
                extraction.recipient_hint = result.result["recipient_name"]
            elif result.status == "needs_clarification":
                return DomainAgentOutput(
                    status="clarification_needed",
                    clarification_message=result.result["message"],
                    delegation_trace=trace,
                )
        elif extraction.recipient_account and not extraction.recipient_bank:
            result = await self.recipient_agent.execute_task(
                AgentTask(
                    task_type="resolve_by_account",
                    constraints={
                        "account_number": extraction.recipient_account, "user_id": user_id},
                )
            )
            trace.append("resolve_by_account")
            if result.status == "success":
                extraction.recipient_bank = result.result["bank_name"]
                extraction.recipient_hint = result.result["recipient_name"]

        # 4. Validate required fields
        if not extraction.amount:
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message="Bạn muốn chuyển bao nhiêu?",
                delegation_trace=trace,
            )
        if not extraction.recipient_account and not extraction.recipient_hint:
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message="Bạn muốn chuyển cho ai?",
                delegation_trace=trace,
            )

        # 5. Build typed ActionDraft
        draft = ActionDraft(
            action_type="TRANSACTION",
            operation=extraction.action,
            amount=extraction.amount,
            currency=extraction.currency,
            recipient_name=extraction.recipient_hint,
            recipient_account=extraction.recipient_account,
            recipient_bank=extraction.recipient_bank,
            note=extraction.note,
        )
        trace.append("build_draft")

        return DomainAgentOutput(
            status="draft_ready",
            action_draft=draft,
            delegation_trace=trace,
        )

    async def _extract_entities(self, message: str) -> TransactionExtraction:
        """Call LLM to extract transaction entities."""
        try:
            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": TRANSACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": TRANSACTION_USER_TEMPLATE.format(
                        message=message)},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            logger.info(f"[TX EXTRACT RAW] {raw}")
            data = json.loads(raw)
            return TransactionExtraction(**data)
        except Exception as e:
            logger.error(f"Extraction error: {e}", exc_info=True)
            return TransactionExtraction(
                action="UNKNOWN",
                needs_clarification=True,
                clarification_reason="Không thể phân tích yêu cầu. Vui lòng thử lại.",
                confidence=0.0,
            )
