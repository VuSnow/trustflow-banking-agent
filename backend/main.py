from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.models import ChatRequest
from backend.agents import orchestrator
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="TrustFlow Guardian", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "OK"}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    logger.info(f"[RECEIVED] user={request.user_id} msg={request.message}")
    intent = await orchestrator.classify_intent(request.message)
    return {"status": "classified", "data": intent.model_dump()}
