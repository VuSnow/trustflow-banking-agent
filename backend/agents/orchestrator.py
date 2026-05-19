import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import IntentResult
from backend.prompts.intent import INTENT_SYSTEM_PROMPT, INTENT_USER_TEMPLATE

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def classify_intent(self, message: str) -> IntentResult:
        """Use LLM to classify intent."""
        try:
            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": INTENT_USER_TEMPLATE.format(
                        message=message
                    )}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
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
                reason=data.get("reason", "")
            )
        except Exception as e:
            logger.error(f"Error in classify intent: {e}", exc_info=True)
            return IntentResult(
                status="error",
                task_type="ERROR",
                operation="",
                confidence=0.0,
                reason=""
            )

orchestrator = Orchestrator()
