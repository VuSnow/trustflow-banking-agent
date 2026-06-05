"""Orchestrator — conversational router with history context.

Uses chat history to understand multi-turn context and route to the
appropriate domain agent. LLM reasons about continuation vs new intent.
Supports multi-intent detection and pipeline planning.
"""
import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import IntentResult, PipelinePlan, PipelineStep
from backend.prompts.intent import (
    INTENT_SYSTEM_PROMPT,
    INTENT_USER_TEMPLATE,
    PIPELINE_SYSTEM_PROMPT,
    PIPELINE_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Max recent messages to include in context for routing
MAX_HISTORY_MESSAGES = 10


class Orchestrator:
    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def classify_intent(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> IntentResult:
        """Use LLM to classify intent with conversation history context.

        Args:
            message: Current user message.
            history: Recent chat messages [{"role": "user"|"assistant", "message": "..."}].
        """
        try:
            messages = [{"role": "system", "content": INTENT_SYSTEM_PROMPT}]

            # Inject recent history for multi-turn context
            if history:
                recent = history[-MAX_HISTORY_MESSAGES:]
                for msg in recent:
                    role = msg.get("role", "user")
                    content = msg.get("message", "")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})

            # Current message
            messages.append({
                "role": "user",
                "content": INTENT_USER_TEMPLATE.format(message=message),
            })

            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            logger.info(f"[INTENT RAW]: {raw}")

            data = json.loads(raw)
            logger.info(f"[INTENT JSON]: {data}")
            return IntentResult(
                status="complete",
                task_type=data["task_type"],
                operation=data.get("operation"),
                confidence=data.get("confidence", 0.0),
                reason=data.get("reason", ""),
            )
        except Exception as e:
            logger.error(f"Error in classify intent: {e}", exc_info=True)
            return IntentResult(
                status="error",
                task_type="ERROR",
                operation="",
                confidence=0.0,
                reason="",
            )

    async def plan_pipeline(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> PipelinePlan:
        """Detect multi-intent and plan a pipeline of agent steps.

        Returns a PipelinePlan with one or more steps. Single-intent messages
        return a plan with exactly one step.
        """
        try:
            messages = [{"role": "system", "content": PIPELINE_SYSTEM_PROMPT}]

            if history:
                recent = history[-MAX_HISTORY_MESSAGES:]
                for msg in recent:
                    role = msg.get("role", "user")
                    content = msg.get("message", "")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})

            messages.append({
                "role": "user",
                "content": PIPELINE_USER_TEMPLATE.format(message=message),
            })

            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            logger.info(f"[PIPELINE PLAN RAW]: {raw}")

            data = json.loads(raw)
            steps = []
            for step_data in data.get("steps", []):
                steps.append(PipelineStep(
                    agent=step_data["agent"],
                    message=step_data.get("message", message),
                    depends_on_previous=step_data.get("depends_on_previous", False),
                    condition=step_data.get("condition"),
                    reason=step_data.get("reason", ""),
                ))

            if not steps:
                # Fallback: single-step plan from intent classification
                intent = await self.classify_intent(message, history=history)
                steps = [PipelineStep(
                    agent=intent.task_type,
                    message=message,
                    depends_on_previous=False,
                    reason=intent.reason,
                )]

            return PipelinePlan(
                steps=steps,
                is_multi_intent=len(steps) > 1,
                confidence=data.get("confidence", 0.9),
            )

        except Exception as e:
            logger.error(f"Error in plan_pipeline: {e}", exc_info=True)
            # Fallback: classify single intent
            intent = await self.classify_intent(message, history=history)
            return PipelinePlan(
                steps=[PipelineStep(
                    agent=intent.task_type,
                    message=message,
                    depends_on_previous=False,
                    reason=intent.reason,
                )],
                is_multi_intent=False,
                confidence=intent.confidence,
            )


orchestrator = Orchestrator()
