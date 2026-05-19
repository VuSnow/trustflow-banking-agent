from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
import uuid


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str


class ChatResponse(BaseModel):
    status: str  # completed | pending_auth | blocked | clarification_needed
    response: str
    risk_tier: Optional[str] = None
    requires_auth: Optional[str] = None
    pending_action_id: Optional[str] = None
    transaction_preview: Optional[dict] = None
    audit_id: Optional[str] = None


class IntentResult(BaseModel):
    task_type: str        # QA | DATA_QUERY | TRANSACTION
    risk_hint: str = "LOW"
    route: str = ""       # qa_handler | data_query_extractor | transaction_extractor
    confidence: float = 0.0
    reason: str = ""
