"""Session CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models import (
    ChatMessageRecord,
    ChatSessionCreateRequest,
    ChatSessionDetail,
    ChatSessionRecord,
    ChatSessionUpdateRequest,
)
from backend.services.chat_session_store import ChatSessionStore

router = APIRouter(tags=["sessions"])

chat_session_store: ChatSessionStore  # injected at startup


def init(store: ChatSessionStore):
    global chat_session_store
    chat_session_store = store


@router.get("/sessions", response_model=list[ChatSessionRecord])
async def list_sessions(user_id: str):
    return chat_session_store.list_sessions(user_id)


@router.post("/sessions", response_model=ChatSessionRecord)
async def create_session(request: ChatSessionCreateRequest):
    return chat_session_store.create_session(user_id=request.user_id, title=request.title)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(session_id: str):
    session = chat_session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = chat_session_store.get_messages(session_id)
    return ChatSessionDetail(**session, messages=[ChatMessageRecord(**msg) for msg in messages])


@router.patch("/sessions/{session_id}", response_model=ChatSessionRecord)
async def update_session(session_id: str, request: ChatSessionUpdateRequest):
    session = chat_session_store.update_session(session_id, title=request.title, status=request.status)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if not chat_session_store.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    chat_session_store.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}
