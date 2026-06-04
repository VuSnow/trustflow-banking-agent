from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.models import ChatRequest, ChatResponse
from backend.agents.orchestrator import orchestrator
from backend.agents.finance_advisor import FinanceAdvisorAgent
from backend.agents.transaction import TransactionAgent
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="TrustFlow Guardian", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain agent registry
transaction_agent = TransactionAgent()
finance_advisor_agent = FinanceAdvisorAgent()
DOMAIN_AGENT_MAP = {
    "TRANSACTION": transaction_agent,
    "FINANCE_ADVICE": finance_advisor_agent,
}


@app.get("/health")
async def health():
    return {"status": "OK"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"[RECEIVED] user={request.user_id} msg={request.message}")

    # 1. Classify intent
    intent = await orchestrator.classify_intent(request.message)
    logger.info(
        f"[INTENT] {intent.task_type} | {intent.operation} | conf={intent.confidence}")

    # 2. Route to domain agent
    agent = DOMAIN_AGENT_MAP.get(intent.task_type)
    if agent:
        output = await agent.run(request.message, request.user_id, request.session_id)
        return ChatResponse(
            status=output.status,
            message=output.clarification_message or output.info_response or "Draft ready for review",
            data=output.response_data or (output.action_draft.model_dump() if output.action_draft else None),
        )

    # 3. Fallback: return classification only
    return ChatResponse(
        status="classified",
        message=f"Intent: {intent.task_type} | {intent.operation}",
        data=intent.model_dump(),
    )
