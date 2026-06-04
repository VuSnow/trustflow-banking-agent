import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.models import (
    ChatMessageRecord,
    ChatRequest,
    ChatResponse,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionRecord,
    ChatSessionUpdateRequest,
)
from backend.agents.orchestrator import orchestrator
from backend.agents.qa import QAAgent
from backend.agents.finance_advisor import FinanceAdvisorAgent
from backend.agents.fraud_report import FraudReportAgent
from backend.agents.transaction import TransactionAgent
from backend.services.chat_session_store import ChatSessionStore

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
qa_agent = QAAgent()
finance_advisor_agent = FinanceAdvisorAgent()
fraud_report_agent = FraudReportAgent()
chat_session_store = ChatSessionStore()
DOMAIN_AGENT_MAP = {
    "QA": qa_agent,
    "TRANSACTION": transaction_agent,
    "FINANCE_ADVICE": finance_advisor_agent,
    "FRAUD_REPORT": fraud_report_agent,
}

FRONTEND_INDEX_PATH = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
FRONTEND_ROOT = FRONTEND_INDEX_PATH.parent

if FRONTEND_ROOT.exists():
    app.mount("/web_ui/static", StaticFiles(directory=FRONTEND_ROOT), name="web_ui_static")


@app.get("/health")
async def health():
    return {"status": "OK"}


@app.get("/")
async def root():
    return RedirectResponse(url="/web_ui", status_code=307)


@app.get("/web_ui", response_class=HTMLResponse)
async def web_ui():
    if not FRONTEND_INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(FRONTEND_INDEX_PATH.read_text(encoding="utf-8"))


@app.get("/web_ui/", response_class=HTMLResponse)
async def web_ui_slash():
    return await web_ui()


@app.get("/sessions", response_model=list[ChatSessionRecord])
async def list_sessions(user_id: str):
    return chat_session_store.list_sessions(user_id)


@app.post("/sessions", response_model=ChatSessionRecord)
async def create_session(request: ChatSessionCreateRequest):
    return chat_session_store.create_session(user_id=request.user_id, title=request.title)


@app.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(session_id: str):
    session = chat_session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = chat_session_store.get_messages(session_id)
    return ChatSessionDetail(**session, messages=[ChatMessageRecord(**msg) for msg in messages])


@app.patch("/sessions/{session_id}", response_model=ChatSessionRecord)
async def update_session(session_id: str, request: ChatSessionUpdateRequest):
    session = chat_session_store.update_session(session_id, title=request.title, status=request.status)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if not chat_session_store.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    chat_session_store.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"[RECEIVED] user={request.user_id} msg={request.message}")
    try:
        chat_session_store.ensure_session(request.user_id, request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    chat_session_store.add_message(
        session_id=request.session_id,
        user_id=request.user_id,
        role="user",
        message=request.message,
    )

    # 1. Classify intent
    intent = await orchestrator.classify_intent(request.message)
    logger.info(
        f"[INTENT] {intent.task_type} | {intent.operation} | conf={intent.confidence}")

    # 2. Route to domain agent
    agent = DOMAIN_AGENT_MAP.get(intent.task_type)
    if agent:
        output = await agent.run(request.message, request.user_id, request.session_id)
        response = ChatResponse(
            status=output.status,
            message=output.clarification_message or output.info_response or "Response ready",
            data=output.response_data or (output.action_draft.model_dump() if output.action_draft else None),
        )
        chat_session_store.add_message(
            session_id=request.session_id,
            user_id=request.user_id,
            role="assistant",
            message=response.message,
            data=response.model_dump(),
        )
        return response

    # 3. Fallback: return classification only
    response = ChatResponse(
        status="classified",
        message=f"Intent: {intent.task_type} | {intent.operation}",
        data=intent.model_dump(),
    )
    chat_session_store.add_message(
        session_id=request.session_id,
        user_id=request.user_id,
        role="assistant",
        message=response.message,
        data=response.model_dump(),
    )
    return response
