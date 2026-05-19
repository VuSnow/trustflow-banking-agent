from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
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


class AgentOutput(BaseModel):
    agent_type: str  
    action: str 
    detail: dict = {}  
    # ["large_amount", "unknown_recipient", ...]
    risk_signals: list[str] = Field(default_factory=list)
    clarification: Optional[str] = None 
    raw_message: str = ""  

class TransactionExtractionResult(BaseModel):
    transaction_type: Literal[
        "transfer",
        "bill_payment",
        "top_up",
        "card_lock",
        "card_unlock",
        "account_opening",
        "loan_application",
        "unknown",
    ]
    details: dict[str, Any]
    raw_text: str
    needs_clarification: bool = False
    missing_info: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
