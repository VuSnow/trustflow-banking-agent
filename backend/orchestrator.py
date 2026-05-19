import json
from openai import AsyncOpenAI
import logging

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import ChatRequest, ChatResponse, IntentResult
from backend.prompts.intent import INTENT_SYSTEM_PROMPT, INTENT_USER_TEMPLATE

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.llm = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    async def classify_intent(self, message: str) -> IntentResult:
        """Use LLM to classify intent."""
        try:
            response = await self.llm.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": INTENT_USER_TEMPLATE.format(
                        message=message)},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            logger.info(f"Data parse from response: {data}")
            return IntentResult(
                task_type=data.get("task_type", "QA"),
                risk_hint=data.get("risk_hint", "LOW"),
                route=data.get("route", "qa_handler"),
                confidence=data.get("confidence", 0.0),
                reason=data.get("reason", ""),
            )
        except Exception as e:
            logger.error(f"Error in classify intent of query: {e}", exc_info=True)
            raise
        
    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        logger.info(f"Chat request from user={request.user_id}, session={request.session_id}")
        intent = await self.classify_intent(request.message)
        return ChatResponse(
            status="completed",
            response=f"[Router] task_type={intent.task_type}, risk={intent.risk_hint}, "
            f"route={intent.route}, confidence={intent.confidence}, reason={intent.reason}",
        )


orchestrator = Orchestrator()
