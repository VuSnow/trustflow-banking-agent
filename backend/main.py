from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.models import ChatRequest, ChatResponse
from backend.orchestrator import orchestrator
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

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

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    return await orchestrator.handle_chat(request)