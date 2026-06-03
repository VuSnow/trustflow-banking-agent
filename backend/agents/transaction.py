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
    AgentPlan,
    AgentTaskResult,
    DomainAgentOutput,
)
from backend.prompts.transaction import TRANSACTION_SYSTEM_PROMPT, TRANSACTION_USER_TEMPLATE
from backend.prompts.planning import (
    PLANNING_SYSTEM_PROMPT,
    PLANNING_USER_TEMPLATE,
    AGENT_DESCRIPTIONS,
)
from backend.agents.registry import AgentRegistry
from backend.agents.sub_agents.recipient_resolution import RecipientResolutionAgent
from backend.agents.sub_agents.text2sql_client import Text2SQLSubAgent
from backend.services.plan_validator import PlanValidator, PlanValidationError
from backend.services.plan_executor import PlanExecutor

logger = logging.getLogger(__name__)

# Allowlisted agents for TransactionAgent planning
TRANSACTION_ALLOWED_AGENTS = {"recipient_resolution", "text2sql"}


class TransactionAgent:
    """Domain agent for TRANSACTION intent.

    Uses LLM to generate a resolution plan, validates it, then executes
    sub-agents to resolve missing fields before building ActionDraft.
    """

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)

        # Build registry
        self.registry = AgentRegistry()
        self.registry.register("recipient_resolution", RecipientResolutionAgent())
        self.registry.register("text2sql", Text2SQLSubAgent())

        self.plan_validator = PlanValidator()
        self.plan_executor = PlanExecutor(self.registry)

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

        # 3. Generate resolution plan (LLM)
        plan = await self._generate_plan(extraction)
        trace.append("generate_plan")
        logger.info(f"[TX PLAN] {plan.model_dump_json()}")

        # 4. Validate plan (fixed safety)
        try:
            plan = self.plan_validator.validate(plan, TRANSACTION_ALLOWED_AGENTS)
            trace.append("validate_plan")
        except PlanValidationError as e:
            logger.error(f"[TX PLAN] Validation failed: {e}")
            # Fallback: return clarification
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message="Không thể xử lý yêu cầu. Vui lòng thử lại.",
                delegation_trace=trace,
            )

        # 5. Execute plan (dynamic)
        if plan.steps:
            results = await self.plan_executor.execute(
                plan, {"user_id": user_id, "extraction": extraction.model_dump()}
            )
            trace.append("execute_plan")

            # Check for clarification in any step result
            for step_key, result in results.items():
                if result.status == "needs_clarification":
                    return DomainAgentOutput(
                        status="clarification_needed",
                        clarification_message=result.result.get("message", "Cần thêm thông tin."),
                        delegation_trace=trace,
                    )

            # Merge resolved data back into extraction
            extraction = self._merge_results(extraction, results)

        # 6. Validate required fields after resolution
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

        # 7. Build typed ActionDraft
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

    async def _generate_plan(self, extraction: TransactionExtraction) -> AgentPlan:
        """Call LLM to generate a resolution plan based on extraction."""
        try:
            system_prompt = PLANNING_SYSTEM_PROMPT.replace(
                "__AGENTS__", AGENT_DESCRIPTIONS
            )
            user_prompt = PLANNING_USER_TEMPLATE.replace(
                "__EXTRACTION__", extraction.model_dump_json(indent=2)
            )

            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            logger.info(f"[TX PLAN RAW] {raw}")
            data = json.loads(raw)
            return AgentPlan(**data)
        except Exception as e:
            logger.error(f"Planning error: {e}", exc_info=True)
            # Fallback: empty plan (proceed with what we have)
            return AgentPlan(steps=[], confidence=0.0)

    def _merge_results(
        self, extraction: TransactionExtraction, results: dict[str, AgentTaskResult]
    ) -> TransactionExtraction:
        """Merge successful resolution results back into extraction."""
        for step_key, result in results.items():
            if result.status != "success":
                continue

            data = result.result
            # Merge recipient fields if resolved
            if "account_number" in data:
                extraction.recipient_account = data["account_number"]
            if "bank_name" in data:
                extraction.recipient_bank = data["bank_name"]
            if "recipient_name" in data:
                extraction.recipient_hint = data["recipient_name"]

        return extraction
