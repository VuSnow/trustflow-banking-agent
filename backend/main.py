import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.agents.qa import QAAgent
from backend.agents.data_query import DataQueryAgent
from backend.agents.finance_advisor import FinanceAdvisorAgent
from backend.agents.fraud_report import FraudReportAgent
from backend.agents.transaction import TransactionAgent
from backend.agents.card_operation import CardOperationAgent
from backend.agents.account_operation import AccountOperationAgent
from backend.services.chat_session_store import ChatSessionStore
from backend.routes import router as sessions_router, init as init_sessions
from backend.routes.chat import router as chat_router, init as init_chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="TrustFlow Guardian", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Domain agent registry ────────────────────────────────────────────────────

chat_session_store = ChatSessionStore()
DOMAIN_AGENT_MAP = {
    "QA": QAAgent(),
    "TRANSACTION": TransactionAgent(),
    "DATA_QUERY": DataQueryAgent(),
    "FINANCE_ADVICE": FinanceAdvisorAgent(),
    "FRAUD_REPORT": FraudReportAgent(),
    "CARD_OPERATION": CardOperationAgent(),
    "ACCOUNT_OPERATION": AccountOperationAgent(),
}

# ─── Initialize route modules ────────────────────────────────────────────────

init_sessions(chat_session_store)
init_chat(chat_session_store, DOMAIN_AGENT_MAP)

app.include_router(sessions_router)
app.include_router(chat_router)

# ─── Static / frontend ───────────────────────────────────────────────────────

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

