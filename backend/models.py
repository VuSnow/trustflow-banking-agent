from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
import uuid


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str

class IntentResult(BaseModel):
    status: Literal["complete", "error"]
    task_type: Literal["QA", "DATA_QUERY", "TRANSACTION", "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION", "ERROR"]
    operation: Optional[str] = None
    confidence: float
    reason: str    
