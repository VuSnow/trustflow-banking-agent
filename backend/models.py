from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
import uuid


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str
