# Implementation Plan: TrustFlow Guardian

## Overview

Incremental implementation following the agent-to-agent architecture.
Each step only codes what is needed to test THAT step. No pre-creating models/endpoints/files for later use.

**Current state:** Basic FastAPI server + intent classification + transaction extraction (old design).
**Target state:** Full agent-to-agent with Guardian + Friction + Executor (MUST HAVE scope).

**Rule:** Nếu step X không cần model Y, thì model Y chưa tồn tại. Code đúng minimum cần để test pass.

---

## Phase 1: Server Skeleton

> Goal: Xóa code cũ, server nhận request đúng format, echo lại.

### Step 1.1: `backend/models.py` — chỉ ChatRequest

Xóa hết models cũ. Chỉ tạo:
```python
class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str
```

Không có ChatResponse, không có IntentResult, không có gì khác.

**File thay đổi:** `backend/models.py`

### Step 1.2: `backend/main.py` — echo endpoint

- `/health` giữ nguyên
- `/chat` nhận `ChatRequest`, print ra terminal, return plain dict:
  ```python
  @app.post("/chat")
  async def chat(request: ChatRequest):
      print(f"[RECEIVED] user={request.user_id} msg={request.message}")
      return {"status": "received", "echo": request.message}
  ```
- Xóa hết import cũ (orchestrator, agents)
- Không có `/actions/...` endpoint

**Test:**
```bash
uvicorn backend.main:app --reload
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh","session_id":"s1"}'
# → {"status":"received","echo":"Chuyển 2tr cho Minh"}
```

### Step 1.3: Xóa code cũ không dùng

- Xóa `backend/agents/orchestrator.py` content (giữ file trống hoặc `pass`)
- Xóa `backend/agents/transaction.py` content
- Xóa `backend/prompts/intent.py` content
- Xóa `backend/prompts/transaction.py` content
- Xóa tests cũ không pass

**Test:** `python -c "from backend.main import app"` — no import error.

---

## Phase 2: Intent Classification

> Goal: LLM classify intent, trả kết quả cho user. Chưa route đi đâu cả.

### Step 2.1: Thêm models cần cho phase này

**File:** `backend/models.py` — thêm:
```python
class IntentResult(BaseModel):
    task_type: Literal["QA", "DATA_QUERY", "TRANSACTION", "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION"]
    operation: Optional[str] = None
    risk_hint: Literal["LOW", "MEDIUM", "HIGH"]
    route: str
    confidence: float
    reason: str

class ChatResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None
```

### Step 2.2: `backend/prompts/intent.py` — classification prompt

Viết prompt để LLM trả về JSON match IntentResult schema.

**Test:** Gọi thử với OpenAI, print raw response.

### Step 2.3: `backend/agents/orchestrator.py` — classify_intent()

```python
async def classify_intent(message: str) -> IntentResult:
    # gọi LLM với prompt từ step 2.2
    # parse response → IntentResult
    ...
```

### Step 2.4: Wire vào `/chat`

**File:** `backend/main.py`:
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    intent = await classify_intent(request.message)
    return ChatResponse(
        status="classified",
        message=f"Intent: {intent.task_type} | Operation: {intent.operation}",
        data=intent.model_dump()
    )
```

**Test:**
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh","session_id":"s1"}'
# → {"status":"classified","message":"Intent: TRANSACTION | Operation: TRANSFER_MONEY","data":{...}}

curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Lãi suất tiết kiệm?","session_id":"s1"}'
# → {"status":"classified","message":"Intent: QA | Operation: null","data":{...}}
```

---

## Phase 3: TransactionAgent (Domain Agent)

> Goal: Nếu intent=TRANSACTION → TransactionAgent parse entity + resolve recipient → trả draft.

### Step 3.1: Thêm models cần cho phase này

**File:** `backend/models.py` — thêm:
```python
class AgentTask(BaseModel):
    task_type: str
    context: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    allowed_output: list[str] = Field(default_factory=list)

class AgentTaskResult(BaseModel):
    status: Literal["success", "failed", "needs_clarification"]
    result: dict = Field(default_factory=dict)
    confidence: float = 1.0

class DomainAgentOutput(BaseModel):
    status: Literal["draft_ready", "clarification_needed", "info_response"]
    action_draft: Optional[dict] = None
    clarification_message: Optional[str] = None
    info_response: Optional[str] = None
    delegation_trace: list[str] = Field(default_factory=list)
```

### Step 3.2: Create mock data

- `backend/data/beneficiaries.json` — tạo lúc này vì BeneficiaryAgent cần

### Step 3.3: `backend/prompts/transaction.py` — extraction prompt

LLM extract: action, amount, recipient_hint, recipient_account, recipient_bank, note, missing_fields.

**Test:** Gọi LLM, print parsed result.

### Step 3.4: `backend/agents/sub_agents/beneficiary.py`

```python
class BeneficiaryAgent:
    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        # load beneficiaries.json
        # match name/nickname
        # return candidates
```

Tạo `backend/agents/sub_agents/__init__.py`.

**Test:**
```python
result = await agent.execute_task(AgentTask(task_type="resolve_by_name", constraints={"name":"Minh","user_id":"u1"}))
assert result.result["account"] == "0123456789"
```

### Step 3.5: `backend/agents/transaction.py` — TransactionAgent.run()

```python
class TransactionAgent:
    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        # 1. LLM extract
        # 2. If missing recipient_account → BeneficiaryAgent
        # 3. If 0 match → clarification_needed
        # 4. If 1 match → build draft
        # 5. Return DomainAgentOutput
```

### Step 3.6: Wire vào `/chat`

**File:** `backend/main.py` — sau classify_intent:
```python
if intent.task_type == "TRANSACTION":
    agent_output = await transaction_agent.run(request.message, request.user_id, request.session_id)
    return ChatResponse(
        status=agent_output.status,
        message=agent_output.clarification_message or "Draft ready",
        data=agent_output.action_draft
    )
else:
    return ChatResponse(status="classified", message=f"Intent: {intent.task_type}", data=intent.model_dump())
```

**Test:**
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh tiền ăn trưa","session_id":"s1"}'
# → {"status":"draft_ready","message":"Draft ready","data":{"action":"TRANSFER_MONEY","amount":2000000,"recipient_name":"Nguyễn Văn Minh",...}}

curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 5 triệu","session_id":"s1"}'
# → {"status":"clarification_needed","message":"Bạn muốn chuyển cho ai?","data":null}
```

---

## Phase 4: Guardian + Friction + Session

> Goal: Draft từ Phase 3 giờ đi qua Guardian → xác định risk → tạo PendingAction. User thấy được risk tier.

### Step 4.1: Thêm models cần cho phase này

**File:** `backend/models.py` — thêm:
```python
class GuardianDecision(BaseModel):
    decision: Literal["ALLOW", "BLOCK"]
    risk_tier: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    risk_score: float
    reasons: list[str] = Field(default_factory=list)

class FrictionResult(BaseModel):
    auth_type: Literal["bank_confirm", "otp", "challenge", "blocked"]
    message: str

class PendingAction(BaseModel):
    action_id: str
    user_id: str
    session_id: str
    action_type: str
    operation: str
    executor_type: str
    draft: dict
    risk_tier: str
    auth_required: str
    created_at: str
    executed: bool = False
```

### Step 4.2: Tạo `backend/data/reported_accounts.json`

Tạo lúc này vì Guardian cần.

### Step 4.3: `backend/services/guardian.py`

Guardian.evaluate() — hard rules + soft scoring → GuardianDecision.

**Test:**
```python
decision = guardian.evaluate({"recipient_account": "6666666666", "amount": 5000000}, "u1", "...")
assert decision.decision == "BLOCK"
assert decision.risk_tier == "RED"
```

### Step 4.4: `backend/services/friction.py`

FrictionRouter.route(decision) → FrictionResult.

**Test:** Unit test 4 tiers.

### Step 4.5: `backend/services/session.py`

SessionStore: store_pending(), get_pending(), mark_executed().

**Test:** Store → get → verify fields.

### Step 4.6: `backend/services/agent_runtime.py`

AgentRuntime.process():
- clarification_needed → pass through
- draft_ready → Guardian → Friction → SessionStore → return pending_auth

### Step 4.7: Wire vào `/chat`

**File:** `backend/main.py` — thay thế logic Phase 3:
```python
if intent.task_type == "TRANSACTION":
    agent_output = await transaction_agent.run(request.message, request.user_id, request.session_id)
    response = await agent_runtime.process(agent_output, request, intent)
    return response
```

Cập nhật ChatResponse thêm fields cần thiết:
```python
class ChatResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None
    pending_action_id: Optional[str] = None
    action_preview: Optional[dict] = None
    risk_tier: Optional[str] = None
    auth_required: Optional[str] = None
```

**Test:**
```bash
# GREEN — known recipient, low amount
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh tiền ăn trưa","session_id":"s1"}'
# → {"status":"pending_auth","risk_tier":"GREEN","auth_required":"bank_confirm","pending_action_id":"...","action_preview":{...}}

# RED — scam account
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 50tr vào 6666666666","session_id":"s1"}'
# → {"status":"blocked","risk_tier":"RED","message":"..."}
```

---

## Phase 5: Executor + Confirm/OTP Endpoints

> Goal: User confirm/OTP pending action → execute. Lúc này mới tạo endpoint mới.

### Step 5.1: Thêm models cần cho phase này

**File:** `backend/models.py` — thêm:
```python
class ConfirmRequest(BaseModel):
    user_id: str

class OTPRequest(BaseModel):
    user_id: str
    otp_code: str

class ActionResponse(BaseModel):
    status: Literal["executed", "failed"]
    message: str
    execution_id: Optional[str] = None
```

### Step 5.2: `backend/executors/__init__.py` + `backend/executors/transaction.py`

Tạo folder + TransactionExecutor (mock: always succeed).

### Step 5.3: `POST /actions/{action_id}/confirm`

**File:** `backend/main.py` — thêm endpoint:
- Load pending → verify user + auth_type == "bank_confirm" → execute → mark_executed

### Step 5.4: `POST /actions/{action_id}/otp`

**File:** `backend/main.py` — thêm endpoint:
- Load pending → verify user + OTP ("123456") → execute → mark_executed

### Step 5.5: Error handling

- 404: not found
- 401: user mismatch
- 403: wrong auth type / blocked
- 409: already executed

**Test:**
```bash
# Full flow: chat → get action_id → confirm
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh tiền ăn","session_id":"s1"}'
# Copy action_id

curl -X POST http://localhost:8000/actions/{action_id}/confirm \
  -H "Content-Type: application/json" -d '{"user_id":"u1"}'
# → {"status":"executed","message":"...","execution_id":"txn_xxx"}

# OTP flow
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 15 triệu cho Lan","session_id":"s1"}'

curl -X POST http://localhost:8000/actions/{action_id}/otp \
  -H "Content-Type: application/json" -d '{"user_id":"u1","otp_code":"123456"}'
# → {"status":"executed",...}
```

- 404: action not found
- 401: user_id mismatch
- 403: wrong auth type or blocked
- 409: already executed

**Test:** `pytest tests/test_api.py` — cover all error cases.

---

## Phase 6: Audit + Integration Tests

> Goal: Thêm audit logging (lúc này mới cần AuditEntry model). Chạy full 5 demo scenarios.

### Step 6.1: Thêm model `AuditEntry`

**File:** `backend/models.py` — thêm:
```python
class AuditEntry(BaseModel):
    request_id: str
    user_id: str
    timestamp: str
    intent: Optional[dict] = None
    domain_agent: Optional[str] = None
    delegation_trace: list[str] = Field(default_factory=list)
    draft: Optional[dict] = None
    guardian_decision: Optional[dict] = None
    friction_result: Optional[dict] = None
    final_status: str
```

### Step 6.2: `backend/services/audit.py`

AuditLogger: log() + get_trace().

### Step 6.3: Wire audit vào agent_runtime

Sau mỗi process() → log AuditEntry.

### Step 6.4: E2E tests — 5 demo scenarios

```bash
# Scenario 1: GREEN — chat → confirm → executed
# Scenario 2: YELLOW — chat → otp → executed
# Scenario 3: RED — chat → blocked
# Scenario 4: missing info → clarification_needed
# Scenario 5: QA → classified, not implemented
```

**Test:** `pytest tests/test_e2e.py -v` — all 5 pass.

---

## Phase 7: CardAgent (SHOULD HAVE)

> Goal: LOCK_CARD and UNLOCK_CARD work end-to-end.

### Step 7.1: Create `backend/data/cards.json`

```json
{
  "u1": [
    {"card_id": "card_001", "type": "credit", "brand": "Visa", "last4": "5678", "status": "active"},
    {"card_id": "card_002", "type": "debit", "brand": "Visa", "last4": "1234", "status": "locked"}
  ]
}
```

### Step 7.2: Write `backend/agents/sub_agents/card_resolver.py`

- Resolve card by type/brand/last4 hint
- Return single card or multiple candidates for clarification

### Step 7.3: Write `backend/agents/card.py`

- Parse: operation (LOCK/UNLOCK) + card_hint
- Delegate to CardResolverAgent
- Build card_action_draft
- Return DomainAgentOutput

### Step 7.4: Write `backend/executors/card.py`

- Mock: update card status in memory

### Step 7.5: Wire CardAgent into orchestrator

- task_type == CARD_OPERATION → CardAgent.run()
- agent_runtime handles Guardian + Friction (LOCK=GREEN confirm, UNLOCK=YELLOW OTP)

**Test:**
```bash
# Lock card
curl -X POST http://localhost:8000/chat \
  -d '{"user_id":"u1","message":"Khóa thẻ tín dụng","session_id":"s1"}'
# → pending_auth, GREEN

# Unlock card
curl -X POST http://localhost:8000/chat \
  -d '{"user_id":"u1","message":"Mở lại thẻ Visa đuôi 1234","session_id":"s1"}'
# → pending_auth, YELLOW, otp
```

---

## Phase 8: DataQueryAgent + Text2SQL (SHOULD HAVE)

> Goal: User can ask spending questions, get NL answers backed by SQL.

### Step 8.1: Create `backend/data/transactions.db` (SQLite)

- Seed with 50-100 sample transactions for user u1
- Columns: id, user_id, recipient_name, recipient_account, recipient_bank, amount, category, date, transaction_type, note

### Step 8.2: Write `backend/agents/sub_agents/text2sql.py`

- LLM generates SQL template + params from natural language query
- Returns sql_template + params (never executes)

### Step 8.3: Write `backend/services/sql_guardian.py`

- Validate: SELECT only, table allowlist, user_id scoped, LIMIT present
- Reject DML/DDL

### Step 8.4: Write `backend/executors/sql.py`

- Execute validated SQL against SQLite
- Inject user_id from auth context (ignore LLM-generated user_id)
- Return result rows

### Step 8.5: Write `backend/agents/data_query.py`

- Plan query → delegate to Text2SQLAgent → SQLGuardian → SQLExecutor
- Summarize result in natural language (LLM call)
- Return DomainAgentOutput(status="info_response", info_response="...")

### Step 8.6: Wire into orchestrator

- task_type == DATA_QUERY → DataQueryAgent.run()

**Test:**
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"user_id":"u1","message":"Tháng này tôi tiêu bao nhiêu cho ăn uống?","session_id":"s1"}'
# → completed, "Tháng này bạn đã chi X đồng cho ăn uống (Y giao dịch)."
```

---

## Phase 9: Frontend (SHOULD HAVE)

> Goal: Streamlit UI with chat + confirm/OTP/block modals + audit viewer.

### Step 9.1: `frontend/app.py` — main layout
### Step 9.2: `frontend/components/chat.py` — chat interface
### Step 9.3: `frontend/components/bank_confirm.py` — confirm modal (GREEN)
### Step 9.4: `frontend/components/otp_modal.py` — OTP input (YELLOW)
### Step 9.5: `frontend/components/audit_viewer.py` — expandable trace

**Test:** `streamlit run frontend/app.py` → all demo scenarios work visually.

---

## Summary: What each phase delivers

| Phase | Deliverable | Can demo |
|-------|-------------|----------|
| 1 | ChatRequest + echo endpoint | Server starts, nhận đúng request |
| 2 | IntentResult + ChatResponse + LLM classify | "Chuyển 2tr" → TRANSACTION |
| 3 | DomainAgentOutput + TransactionAgent + BeneficiaryAgent | Draft built từ NL |
| 4 | GuardianDecision + FrictionResult + PendingAction + AgentRuntime | Risk tiers, block/allow |
| 5 | ActionResponse + Confirm/OTP endpoints + Executor | Full lifecycle |
| 6 | AuditEntry + full trace | 5 scenarios pass |
| 7 | CardAgent | Lock/unlock card |
| 8 | DataQueryAgent + Text2SQL | NL → SQL → NL answer |
| 9 | Frontend | Visual demo |

---

## Rules

1. **Mỗi step chỉ code đúng những gì cần để test step đó** — không tạo trước
2. Model mới chỉ xuất hiện ở phase nào cần nó lần đầu
3. Endpoint mới chỉ tạo khi có logic xử lý, không tạo stub endpoint
4. File/folder mới chỉ tạo khi step đó import từ nó
5. Run server sau mỗi step để verify no import error
6. Guardian luôn được gọi cho mọi action — kể cả GREEN
