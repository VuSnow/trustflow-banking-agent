# backend/models.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
import uuid


class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str


class ChatResponse(BaseModel):
    """Stable API contract — fields added once, never removed.
    Unused fields stay None until the phase that needs them."""
    status: str
    message: str
    data: dict | None = None
    pending_action_id: str | None = None
    action_preview: dict | None = None
    risk_tier: str | None = None
    auth_required: str | None = None


class ChatSessionCreateRequest(BaseModel):
    user_id: str
    title: str | None = None


class ChatSessionUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None


class ChatMessageRecord(BaseModel):
    id: int | None = None
    session_id: str
    user_id: str
    role: Literal["user", "assistant", "system"]
    message: str
    data: dict | None = None
    created_at: str


class ChatSessionRecord(BaseModel):
    session_id: str
    user_id: str
    title: str | None = None
    status: str = "active"
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message_at: str | None = None


class ChatSessionDetail(ChatSessionRecord):
    messages: list[ChatMessageRecord] = Field(default_factory=list)


class IntentResult(BaseModel):
    status: Literal["complete", "error"]
    task_type: Literal["QA", "DATA_QUERY", "TRANSACTION",
                       "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION",
                       "FINANCE_ADVICE", "FRAUD_REPORT", "ERROR"]
    operation: Optional[str] = None
    confidence: float
    reason: str


class TransactionExtraction(BaseModel):
    """Typed extraction from user message — core banking entity parsing.
    Maps 1:1 with the LLM extraction prompt output schema."""
    action: Literal["TRANSFER_MONEY", "BILL_PAYMENT", "TOP_UP", "UNKNOWN"]
    amount: int | None = None
    currency: str = "VND"
    recipient_hint: str | None = None
    recipient_account: str | None = None
    recipient_bank: str | None = None
    bill_provider: str | None = None
    customer_code: str | None = None
    topup_target: str | None = None
    source_account_hint: str | None = None
    purpose_hint: str | None = None
    note: str | None = None
    reference_context: dict | None = None
    missing_fields: list[str] = Field(default_factory=list)
    resolvable_fields: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_reason: str | None = None
    confidence: float = 0.0


class ActionDraft(BaseModel):
    """Typed draft for Guardian input — never raw dict at boundaries.
    This is what gets stored as PendingAction.draft later."""
    action_type: str          # "TRANSACTION", "CARD_OPERATION", etc.
    operation: str            # "TRANSFER_MONEY", "LOCK_CARD", etc.
    amount: int | None = None
    currency: str = "VND"
    recipient_name: str | None = None
    recipient_account: str | None = None
    recipient_bank: str | None = None
    bank_name: str | None = None
    transfer_type: Literal["intrabank", "interbank"] | None = None
    note: str | None = None
    resolution_source: str | None = None
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


class FraudReportExtraction(BaseModel):
    """Typed extraction for fraud-report intake."""
    operation: Literal["REPORT_FRAUD", "CHECK_FRAUD_STATUS", "CHECK_ACCOUNT_RISK"] = "REPORT_FRAUD"
    fraud_type: str | None = None
    reported_account_no: str | None = None
    reported_bank_code: str | None = None
    transaction_ref: str | None = None
    contact_channel: str | None = None
    aftermath: str | None = None
    reason_text: str | None = None
    has_evidence: bool | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class FraudReportDetails(BaseModel):
    """Draft payload for a fraud report. This is not persisted in this phase."""
    reporter_cif_no: str
    transaction_ref: str | None = None
    reported_account_no: str
    reported_bank_code: str
    reported_customer_cif: str | None = None
    fraud_type: str
    contact_channel: str
    aftermath: str
    reason_text: str
    has_evidence: bool
    confidence_score: int
    status: Literal["VALIDATED", "SUBMITTED"]


class FraudReportDraft(BaseModel):
    """Top-level draft returned by FraudReportAgent."""
    action_type: Literal["FRAUD_REPORT"] = "FRAUD_REPORT"
    cif_no: str
    api_name: Literal["fraud_report_service"] = "fraud_report_service"
    report_draft: FraudReportDetails
    verification_evidence: dict = Field(default_factory=dict)


class AgentTask(BaseModel):
    """Generic task request from domain agent to sub-agent."""
    task_type: str                                    # e.g. "resolve_by_name", "resolve_by_account"
    context: dict = Field(default_factory=dict)       # shared context
    constraints: dict = Field(default_factory=dict)   # task-specific params


class AgentTaskResult(BaseModel):
    """Generic task response from sub-agent back to domain agent."""
    status: Literal["success", "failed", "needs_clarification"]
    result: dict = Field(default_factory=dict)
    confidence: float = 1.0


class PlanStep(BaseModel):
    """A single resolution step in an agent plan."""
    agent: str                        # registry key: "text2sql", "fraud_screening"
    task_type: str                    # "resolve_by_name", "query_evidence", etc.
    input_from: str | None = None     # "extraction" | "step_0" | "step_1"
    constraints: dict = Field(default_factory=dict)
    reason: str                       # why this step is needed


class AgentPlan(BaseModel):
    """LLM-generated resolution plan for domain agent."""
    steps: list[PlanStep] = Field(default_factory=list)
    fallback: Literal["clarify", "proceed_partial"] = "clarify"
    confidence: float = 0.0


class DomainAgentOutput(BaseModel):
    """Standard output of any domain agent. Orchestrator doesn't care
    which agent produced it — same shape regardless."""
    status: Literal["draft_ready", "clarification_needed", "needs_otp", "info_response"]
    action_draft: ActionDraft | None = None
    clarification_message: str | None = None
    info_response: str | None = None
    response_data: dict | None = None
    delegation_trace: list[str] = Field(default_factory=list)


# ─── Pipeline models ─────────────────────────────────────────────────────────


class PipelineStep(BaseModel):
    """A single step in a multi-agent pipeline."""
    agent: str                       # "QA", "DATA_QUERY", "TRANSACTION", etc.
    message: str                     # the sub-message for this agent
    depends_on_previous: bool = False  # True if this step needs output from prior step
    condition: Literal["always", "previous_success", "previous_safe"] | None = None
    reason: str = ""                 # why this step is needed


class PipelinePlan(BaseModel):
    """Multi-step plan produced by orchestrator."""
    steps: list[PipelineStep] = Field(default_factory=list)
    is_multi_intent: bool = False
    confidence: float = 0.9


class PipelineState(BaseModel):
    """Persisted state for a multi-turn pipeline execution.

    Tracks which steps have completed, which step is currently active,
    and accumulated context across steps. Stored in session metadata.
    """
    plan: PipelinePlan
    current_step_index: int = 0
    step_results: list[dict] = Field(default_factory=list)
    status: Literal["running", "waiting_user", "completed", "failed"] = "running"
    waiting_reason: str | None = None  # clarification/confirmation message


class TransactionState(BaseModel):
    """Persistent state for transaction workflow (FSM + draft snapshot).

    Saved when agent produces a draft and OTP is required.
    Used to guarantee draft integrity when user provides OTP —
    backend uses this saved draft instead of trusting LLM reconstruction.
    """
    session_id: str
    user_id: str
    fsm_state: Literal[
        "WAITING_CONFIRMATION",
        "WAITING_OTP",
        "OTP_VERIFIED",
        "CANCELLED",
        "BLOCKED",
    ] = "WAITING_CONFIRMATION"

    # Frozen draft snapshot from verified tools
    draft: dict = Field(default_factory=dict)

    # Fraud screening result (frozen from check_fraud_risk tool)
    fraud_screening: dict | None = None
    risk_level: str | None = None
    warning_message: str | None = None

    # OTP tracking
    otp_attempts: int = 0
    max_otp_attempts: int = 3
    otp_created_at: str | None = None
    otp_expires_seconds: int = 300  # 5 minutes
