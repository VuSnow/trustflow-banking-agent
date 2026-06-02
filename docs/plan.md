# Implementation Plan: TrustFlow Guardian

## Overview

Incremental implementation following agent-to-agent architecture with **hybrid control**:
- **Fixed outer control plane** for safety-critical flow (Guardian, Friction, Executor)
- **Dynamic inner agent planning** for domain-level resolution (sub-agent orchestration)
- **Constrained Text2SQL** for evidence retrieval only — never for execution

**Architecture principle:**
```
The system uses a fixed safety-critical control plane and dynamic domain-level planning.
The orchestrator only routes to the correct domain agent.
Each domain agent generates and executes its own validated resolution plan
through an allowlisted agent registry.
Text2SQL is allowed only as an evidence-retrieval sub-agent — constrained SELECT queries,
validated by SQLGuardian, executed with injected user_id from backend context.
Execution, Guardian checks, authentication friction, and final action execution
remain outside LLM planning scope.
```

**Current state:** Basic FastAPI server + intent classification (Phase 2 complete).
**Target state:** Full agent-to-agent with realistic banking DB, dynamic planning, Guardian + Friction + Executor.

**Rule:** Nếu step X không cần model Y, thì model Y chưa tồn tại. Code đúng minimum cần để test pass.

---

## Architecture: Fixed Outer + Dynamic Inner

```text
/chat
→ IntentClassifier                     # fixed
→ DomainAgentRouter                    # fixed (thin map, no business logic)
→ DomainAgent.extract()                # domain-specific LLM extraction
→ DomainAgent.plan()                   # DYNAMIC — LLM generates resolution plan
→ PlanValidator                        # fixed safety — allowlist, max steps, resolution-only
→ PlanExecutor                         # executes allowed sub-agents sequentially
    ├── RecipientResolutionAgent       # queries DB: saved beneficiaries + transaction history
    ├── Text2SQLAgent                  # LLM → constrained SELECT → SQLGuardian → SQLExecutor
    └── (other sub-agents)
→ DomainAgent.build_output()           # builds typed ActionDraft from resolved data
→ Guardian                             # fixed mandatory — hard rules + risk scoring
→ FrictionRouter                       # fixed mandatory — maps risk tier to auth method
→ PendingAction / Response
→ [User confirms/OTP]
→ Executor                             # fixed — only runs after auth succeeds
```

**Key constraints:**
1. LLM planner generates **resolution plans only** (resolve recipient, lookup history)
2. LLM planner **CANNOT** generate execution steps (transfer, approve, bypass)
3. Text2SQL generates **SELECT only** — validated by SQLGuardian before execution
4. SQLExecutor **injects user_id from backend context** — never trusts LLM-generated user_id
5. RecipientResolutionAgent may **auto-resolve only when there is exactly one high-confidence verified candidate**. If multiple plausible candidates or low confidence → must return clarification_needed

---

## Summary Flow

```text
TrustFlow Guardian uses a fixed safety-critical outer control plane and dynamic inner domain planning.

The outer control plane is deterministic:
IntentClassifier → DomainAgentRouter → Guardian → FrictionRouter → PendingAction → Human Confirm/OTP → Executor.

The inner domain flow is agentic:
TransactionAgent extracts structured transaction intent, generates a validated resolution plan, and calls allowlisted sub-agents such as RecipientResolutionAgent and Text2SQLAgent.

Text2SQLAgent is used only when historical banking evidence is needed, such as "like last month" or "the person I sent the most money to". It can only generate constrained SELECT queries. SQLGuardian validates the query, and SQLExecutor injects user_id from backend context.

RecipientResolutionAgent converts evidence into verified recipient candidates. It may auto-resolve only when there is exactly one high-confidence verified candidate. Otherwise, it returns clarification_needed.

TransactionAgent builds an ActionDraft only after required fields are resolved. Every ActionDraft must pass through Guardian. Execution happens only after human confirmation or OTP.
```

---

## Data Foundation: banking.db

Created at Phase 3. Used by RecipientResolutionAgent, Text2SQLAgent, and DataQueryAgent.

**Schema:**
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    created_at TEXT
);

CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    account_number TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    account_type TEXT DEFAULT 'checking',  -- checking, savings
    balance INTEGER DEFAULT 0,
    currency TEXT DEFAULT 'VND',
    status TEXT DEFAULT 'active'
);

CREATE TABLE beneficiaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL,
    nicknames TEXT,              -- JSON array: ["Minh", "anh Minh"]
    account_number TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    created_at TEXT,
    last_used_at TEXT
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    source_account TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_account TEXT NOT NULL,
    recipient_bank TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'VND',
    category TEXT,              -- food, bills, transfer, salary, etc.
    transaction_type TEXT,      -- transfer, bill_payment, top_up
    note TEXT,
    status TEXT DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE TABLE reported_accounts (
    account_number TEXT PRIMARY KEY,
    bank_name TEXT,
    reason TEXT,                -- scam, fraud, suspicious
    reported_at TEXT,
    severity TEXT DEFAULT 'high'  -- high, medium
);
```

**Fraud detection tables (Phase 10):**
```sql
CREATE TABLE fraud_reports (
    report_id TEXT PRIMARY KEY,
    reporter_cif_no TEXT NOT NULL REFERENCES users(user_id),
    transaction_ref TEXT,
    reported_account_no TEXT NOT NULL,
    reported_bank_code TEXT NOT NULL,
    reported_customer_cif TEXT,
    fraud_type TEXT CHECK(fraud_type IN ('SHOPPING_SCAM','INVESTMENT_SCAM','IMPERSONATION','DEPOSIT_SCAM','LOAN_SCAM','OTHER')),
    contact_channel TEXT CHECK(contact_channel IN ('FACEBOOK','ZALO','TELEGRAM','WEBSITE','PHONE','OTHER')),
    aftermath TEXT CHECK(aftermath IN ('BLOCKED_CONTACT','NO_GOODS','ASKED_MORE_MONEY','DISAPPEARED','OTHER')),
    reason_text TEXT,
    has_evidence INTEGER DEFAULT 0,
    confidence_score INTEGER DEFAULT 0,
    status TEXT CHECK(status IN ('SUBMITTED','VALIDATED','CONFIRMED','REJECTED')),
    created_at TEXT
);

CREATE TABLE reported_accounts_v2 (
    reported_account_id TEXT PRIMARY KEY,
    account_no TEXT NOT NULL,
    bank_code TEXT NOT NULL,
    linked_customer_cif TEXT,
    valid_report_count INTEGER DEFAULT 0,
    unique_reporter_count INTEGER DEFAULT 0,
    total_reported_amount INTEGER DEFAULT 0,
    avg_confidence_score INTEGER DEFAULT 0,
    risk_score REAL DEFAULT 0.0,
    risk_level TEXT CHECK(risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    status TEXT CHECK(status IN ('ACTIVE','UNDER_REVIEW','CLEARED')),
    first_reported_at TEXT,
    last_reported_at TEXT,
    UNIQUE(account_no, bank_code)
);

CREATE TABLE reported_customers (
    reported_customer_id TEXT PRIMARY KEY,
    cif_no TEXT NOT NULL REFERENCES users(user_id),
    reported_account_count INTEGER DEFAULT 0,
    valid_report_count INTEGER DEFAULT 0,
    total_reported_amount INTEGER DEFAULT 0,
    risk_score REAL DEFAULT 0.0,
    risk_level TEXT CHECK(risk_level IN ('WATCH','FROZEN','BLOCKED','CLEARED')),
    status TEXT CHECK(status IN ('ACTIVE','UNDER_REVIEW','CLEARED')),
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE fraud_decisions (
    decision_id TEXT PRIMARY KEY,
    action_id TEXT,
    receiver_account_no TEXT NOT NULL,
    receiver_bank_code TEXT NOT NULL,
    matched_report_count INTEGER DEFAULT 0,
    risk_score REAL,
    risk_level TEXT,
    decision TEXT CHECK(decision IN ('ALLOW','WARN','STEP_UP_AUTH','HOLD','BLOCK')),
    reason_codes TEXT,  -- JSON array
    created_at TEXT
);
```

**Seed data:** 2 users, 3-5 beneficiaries per user, 50-100 transactions, 3-5 reported accounts, 2-3 fraud_reports (seeded for screening demo), 2-3 reported_accounts_v2 entries with varied risk_levels.

---

## Demo Scenarios (target)

These 5 scenarios drive the implementation:

### Scenario 1: "Chuyển 2tr cho Minh"
```text
Extract: action=TRANSFER_MONEY, amount=2000000, recipient_hint="Minh"
Plan: [recipient_resolution.resolve_by_name(name="Minh")]
Resolution: query beneficiaries → 1 match "Nguyễn Văn Minh" (VCB 012xxx)
Draft: ActionDraft(amount=2000000, recipient_name="Nguyễn Văn Minh", recipient_account="0123456789")
Guardian: GREEN (known recipient, low amount)
Friction: bank_confirm
→ User confirms → Executed
```

### Scenario 2: "Chuyển cho Minh 2 triệu như tháng trước"
```text
Extract: action=TRANSFER_MONEY, amount=2000000, recipient_hint="Minh", reference_context={has_reference:true, reference_time:"last_month"}
Plan: [
  text2sql.query_evidence(query_goal="find_previous_transfer", recipient_hint="Minh", period="last_month", amount=2000000),
  recipient_resolution.resolve_with_evidence(input_from="step_0")
]
Resolution: text2sql generates SELECT → SQLGuardian validates → execute → returns row
  → RecipientResolution confirms match
Draft: ActionDraft with full details from history
Guardian: GREEN
→ confirm → executed
```

### Scenario 3: "Chuyển cho người tôi gửi nhiều nhất tháng trước 2 triệu"
```text
Extract: action=TRANSFER_MONEY, amount=2000000, recipient_hint=null, reference_context={has_reference:true, reference_type:"previous_recipient", reference_text:"người tôi gửi nhiều nhất tháng trước"}
Plan: [
  text2sql.query_evidence(query_goal="find_top_recipient", period="last_month", metric="total_amount"),
  recipient_resolution.resolve_with_evidence(input_from="step_0")
]
Resolution: text2sql → SELECT recipient_account, SUM(amount) ... GROUP BY ... ORDER BY ... LIMIT 1
  → RecipientResolution verifies account in beneficiaries
Draft: ActionDraft with resolved recipient
Guardian: YELLOW (indirect historical reference + medium resolution confidence)
Friction: OTP
→ OTP → executed
```

### Scenario 4: Ambiguous "Minh" — multiple candidates
```text
Extract: action=TRANSFER_MONEY, amount=500000, recipient_hint="Minh"
Plan: [recipient_resolution.resolve_by_name(name="Minh")]
Resolution: query beneficiaries + transactions → 2 matches:
  - "Nguyễn Văn Minh" (VCB 012xxx)
  - "Trần Minh Đức" (TCB 555xxx)
→ RecipientResolution returns needs_clarification with candidates
Output: DomainAgentOutput(status="clarification_needed",
  clarification_message="Tìm thấy 2 người tên Minh. Bạn muốn chuyển cho ai?\n1. Nguyễn Văn Minh - VCB ...2789\n2. Trần Minh Đức - TCB ...5xxx")
```

### Scenario 5: Recipient linked to scam account
```text
Extract: action=TRANSFER_MONEY, amount=50000000, recipient_account="6666666666"
Plan: [] (account already provided, no resolution needed)
Draft: ActionDraft(amount=50000000, recipient_account="6666666666")
Guardian: checks reported_accounts table → RED (scam account + high amount)
→ BLOCKED. User cannot confirm.
```

### Scenario 6: User reports a fraud account
```text
User: "Tôi muốn báo cáo STK 9876543210 ngân hàng TCB lừa đảo tôi"
Extract: operation=REPORT_FRAUD_ACCOUNT, reported_account_no="9876543210", reported_bank_code="TCB"
FraudVerificationAgent: query transactions → found 1 matching txn (15M, 3 days ago)
Multi-turn: fraud_type=SHOPPING_SCAM, channel=FACEBOOK, aftermath=BLOCKED_CONTACT, evidence=yes
Confidence: 100 (has txn + recent + clear type + clear aftermath + has evidence)
Draft: FraudReportDraft(...)
Guardian: GREEN (protective action)
Friction: bank_confirm
→ User confirms → FraudReportExecutor inserts report + updates risk
```

### Scenario 7: Transfer to previously-reported account (screening)
```text
User: "Chuyển 10tr cho TK 9876543210 TCB"
Extract: action=TRANSFER_MONEY, amount=10000000, recipient_account="9876543210", recipient_bank="TCB"
Plan: [] (account provided)
Draft: ActionDraft(amount=10000000, recipient_account="9876543210", recipient_bank="TCB")
Guardian: checks reported_accounts_v2 → risk_level=MEDIUM (2 valid reports)
→ WARN + STEP_UP_AUTH
Message: "⚠️ Tài khoản này từng bị báo cáo lừa đảo. Bạn có chắc chắn?"
→ User confirms + OTP → Executed (with fraud_decisions logged)
```

---

## Phase 1: Server Skeleton

> Goal: Clean slate, server nhận request đúng format, echo lại.

### Step 1.1: `backend/models.py` — ChatRequest + stable ChatResponse envelope

```python
class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    """Stable API contract — fields added once, never removed."""
    status: str
    message: str
    data: dict | None = None
    pending_action_id: str | None = None
    action_preview: dict | None = None
    risk_tier: str | None = None
    auth_required: str | None = None
```

ChatResponse defined early as **API contract**. Not all fields used immediately — unused fields stay None.

**File thay đổi:** `backend/models.py`

### Step 1.2: `backend/main.py` — echo endpoint

- `/health` giữ nguyên
- `/chat` nhận `ChatRequest`, return ChatResponse:
  ```python
  @app.post("/chat")
  async def chat(request: ChatRequest):
      print(f"[RECEIVED] user={request.user_id} msg={request.message}")
      return ChatResponse(status="received", message=request.message)
  ```
- Xóa hết import cũ (orchestrator, agents)
- Không có `/actions/...` endpoint

**Test:**
```bash
uvicorn backend.main:app --reload
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh","session_id":"s1"}'
# → {"status":"received","message":"Chuyển 2tr cho Minh","data":null,...}
```

### Step 1.3: Xóa code cũ không dùng

Ensure git commit trước khi xóa. Dùng feature branch:
```bash
git checkout -b trustflow-guardian-v2
```

- Xóa `backend/agents/orchestrator.py` content (giữ file trống hoặc `pass`)
- Xóa `backend/prompts/intent.py` content
- Xóa `backend/prompts/transaction.py` content
- Xóa tests cũ không pass

**Test:** `python -c "from backend.main import app"` — no import error.

---

## Phase 2: Intent Classification

> Goal: LLM classify intent, trả kết quả cho user. Chưa route đi đâu cả.

### Step 2.1: Thêm model IntentResult

**File:** `backend/models.py` — thêm:
```python
class IntentResult(BaseModel):
    task_type: Literal["QA", "DATA_QUERY", "TRANSACTION", "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION"]
    operation: str | None = None
    route: str
    confidence: float
    reason: str
```

### Step 2.2: `backend/prompts/intent.py` — classification prompt

Viết prompt để LLM trả về JSON match IntentResult schema.

### Step 2.3: `backend/agents/orchestrator.py` — classify_intent()

```python
async def classify_intent(message: str) -> IntentResult:
    # gọi LLM với prompt từ step 2.2
    # parse response → IntentResult
```

### Step 2.4: Wire vào `/chat`

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
```

---

## Phase 3: Mock Banking Database + TransactionAgent Baseline

> Goal: Tạo banking.db realistic, TransactionAgent extract + hardcoded recipient resolution → draft.
> Hardcoded flow trước để có baseline chạy được. Phase 6 refactor sang dynamic planning.

### Step 3.1: Thêm typed extraction + draft models

**File:** `backend/models.py` — thêm:
```python
class TransactionExtraction(BaseModel):
    """Typed extraction from user message — core banking entity parsing."""
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
    """Typed draft for Guardian input — never raw dict at boundaries."""
    action_type: str          # "TRANSACTION", "CARD_OPERATION"
    operation: str            # "TRANSFER_MONEY", "LOCK_CARD"
    amount: int | None = None
    currency: str = "VND"
    recipient_name: str | None = None
    recipient_account: str | None = None
    recipient_bank: str | None = None
    note: str | None = None
    resolution_source: str | None = None       # "saved_beneficiary", "transaction_history", "text2sql_evidence"
    resolution_confidence: float | None = None  # 0.95 (beneficiary), 0.8 (history), 0.75 (text2sql)

class AgentTask(BaseModel):
    """Generic task request from domain agent to sub-agent."""
    task_type: str
    context: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)

class AgentTaskResult(BaseModel):
    """Generic task response from sub-agent back to domain agent."""
    status: Literal["success", "failed", "needs_clarification"]
    result: dict = Field(default_factory=dict)
    confidence: float = 1.0

class DomainAgentOutput(BaseModel):
    """Standard output of any domain agent."""
    status: Literal["draft_ready", "clarification_needed", "info_response"]
    action_draft: ActionDraft | None = None
    clarification_message: str | None = None
    info_response: str | None = None
    delegation_trace: list[str] = Field(default_factory=list)
```

### Step 3.2: Create banking.db + seed script

**File:** `backend/data/seed_banking_db.py`

Creates SQLite database with schema (users, accounts, beneficiaries, transactions, reported_accounts) and seeds realistic data:
- 2 users (u1, u2)
- 2-3 accounts per user
- 3-5 saved beneficiaries per user (with nicknames JSON array)
- 50-100 transactions spanning 3 months (varied categories, amounts, recipients)
- 3-5 reported/scam accounts

**File output:** `backend/data/banking.db`

```bash
# Run once:
python -m backend.data.seed_banking_db
sqlite3 backend/data/banking.db "SELECT COUNT(*) FROM transactions;"
# → 50+
sqlite3 backend/data/banking.db "SELECT name, nicknames FROM beneficiaries WHERE user_id='u1';"
# → shows saved beneficiaries with nicknames
```

### Step 3.3: `backend/prompts/transaction.py` — extraction prompt

LLM extract → `TransactionExtraction` (typed). Prompt đã có sẵn, ensure output matches model schema. Add user template.

**Test:** Gọi LLM, parse vào TransactionExtraction model.

### Step 3.4: `backend/agents/sub_agents/recipient_resolution.py` (Phase 3 version)

Phase 3 version: **direct DB queries only** (no Text2SQL, no LLM).

```python
class RecipientResolutionAgent:
    """Resolves recipient_hint to verified recipient candidate(s).

    Data sources (direct SQL, no LLM):
    1. beneficiaries table — saved recipients with nicknames
    2. transactions table — historical recipients (fallback)

    Outcomes:
    - 1 match → success (verified candidate)
    - 0 matches → needs_clarification
    - 2+ matches → needs_clarification with candidates list
    """

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        if task.task_type == "resolve_by_name":
            return self._resolve_by_name(task)
        elif task.task_type == "resolve_by_account":
            return self._resolve_by_account(task)

    def _resolve_by_name(self, task: AgentTask) -> AgentTaskResult:
        """
        1. Query beneficiaries WHERE user_id=? AND (name LIKE ? OR nicknames LIKE ?)
        2. If 0 results → query transactions for DISTINCT recipients matching name
        3. Deduplicate by account_number
        4. Return candidates
        """
        user_id = task.constraints["user_id"]
        name = task.constraints["name"]
        # ... structured SQL queries against banking.db ...

    def _resolve_by_account(self, task: AgentTask) -> AgentTaskResult:
        """Exact match by account number in beneficiaries or transaction history."""
        ...
```

Tạo `backend/agents/sub_agents/__init__.py`.

**Test:**
```python
result = await agent.execute_task(AgentTask(
    task_type="resolve_by_name",
    constraints={"name": "Minh", "user_id": "u1"}
))
assert result.status == "success"
assert result.result["account_number"] == "0123456789"
```

### Step 3.5: `backend/agents/transaction.py` — TransactionAgent.run() (hardcoded baseline)

```python
class TransactionAgent:
    """Domain agent for TRANSACTION intent.
    Phase 3: hardcoded resolution flow.
    Phase 6: refactored to dynamic planning.
    """

    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        trace = []

        # 1. LLM extract → TransactionExtraction (typed)
        extraction = await self._extract_entities(message)
        trace.append("extract_entities")

        # 2. Early exit if extraction needs clarification
        if extraction.needs_clarification:
            return DomainAgentOutput(status="clarification_needed", ...)

        # 3. Resolve recipient (hardcoded — Phase 6 replaces with planning)
        if extraction.recipient_hint and not extraction.recipient_account:
            result = await self.recipient_agent.execute_task(
                AgentTask(task_type="resolve_by_name",
                          constraints={"name": extraction.recipient_hint, "user_id": user_id})
            )
            trace.append("resolve_recipient")
            if result.status == "success":
                # merge resolved data into extraction
                ...
            elif result.status == "needs_clarification":
                return DomainAgentOutput(status="clarification_needed", clarification_message=result.result["message"])

        # 4. Validate required fields (amount, recipient)
        if not extraction.amount:
            return DomainAgentOutput(status="clarification_needed", clarification_message="Bạn muốn chuyển bao nhiêu?")
        if not extraction.recipient_account and not extraction.recipient_hint:
            return DomainAgentOutput(status="clarification_needed", clarification_message="Bạn muốn chuyển cho ai?")

        # 5. Build typed ActionDraft
        draft = ActionDraft(action_type="TRANSACTION", operation=extraction.action, ...)
        trace.append("build_draft")

        return DomainAgentOutput(status="draft_ready", action_draft=draft, delegation_trace=trace)
```

### Step 3.6: Wire vào `/chat` via thin DomainAgentRouter

**File:** `backend/main.py`:
```python
DOMAIN_AGENT_MAP = {
    "TRANSACTION": transaction_agent,
}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    intent = await classify_intent(request.message)
    agent = DOMAIN_AGENT_MAP.get(intent.task_type)
    if agent:
        output = await agent.run(request.message, request.user_id, request.session_id)
        return ChatResponse(
            status=output.status,
            message=output.clarification_message or "Draft ready",
            data=output.action_draft.model_dump() if output.action_draft else None,
        )
    else:
        return ChatResponse(status="classified", message=f"Intent: {intent.task_type}", data=intent.model_dump())
```

**Test:**
```bash
# Scenario 1: known recipient → draft_ready
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh tiền ăn trưa","session_id":"s1"}'
# → {"status":"draft_ready","data":{"operation":"TRANSFER_MONEY","amount":2000000,"recipient_name":"Nguyễn Văn Minh",...}}

# Missing recipient → clarification
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 5 triệu","session_id":"s1"}'
# → {"status":"clarification_needed","message":"Bạn muốn chuyển cho ai?"}

# Ambiguous → clarification with candidates (Scenario 4)
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 500k cho Minh","session_id":"s1"}'
# → {"status":"clarification_needed","message":"Tìm thấy 2 người tên Minh..."}
# (depends on seed data having 2 "Minh" entries)
```

---

## Phase 4: RecipientResolutionAgent Core

> Goal: Add `resolve_with_evidence` task_type to RecipientResolutionAgent.
> This phase only adds deterministic resolution capabilities. Historical/analytical queries
> ("người tôi gửi nhiều nhất", "như tháng trước") are handled by Text2SQL in Phase 5/6.

### Step 4.1: Add resolve_with_evidence task_type

```python
class RecipientResolutionAgent:
    """
    Supported task_types:
    - resolve_by_name: beneficiaries + transaction history name match (Phase 3)
    - resolve_by_account: exact account match (Phase 3)
    - resolve_with_evidence: inspect upstream evidence rows and verify (NEW)

    Auto-resolve rule:
    - Exactly 1 high-confidence verified candidate → auto-resolve (success)
    - Multiple plausible candidates → needs_clarification with candidate list
    - 0 candidates → needs_clarification
    """

    def _resolve_with_evidence(self, task: AgentTask) -> AgentTaskResult:
        """Inspect evidence rows from upstream step (Text2SQL).
        Verifies account in beneficiaries or past transactions for this user.

        constraints: {user_id, evidence_rows: [...]}

        Logic:
        1. Extract account_number/recipient_name from evidence rows
        2. Verify account exists in beneficiaries or past transactions for this user
        3. If exactly 1 verified match → success
        4. If multiple or unverified → needs_clarification
        """
        ...
```

### Step 4.2: Test resolution paths

```python
# Test: resolve_by_name → single match → auto-resolve
# Test: resolve_by_name → multiple candidates → clarification (Scenario 4)
# Test: resolve_by_account → exact match
# Test: resolve_by_account → not found → clarification
# Test: resolve_with_evidence → valid evidence → success
# Test: resolve_with_evidence → unverified evidence → clarification
```

**Test:**
```bash
# Phase 4 does not change /chat behavior yet.
# RecipientResolutionAgent gains resolve_with_evidence for Phase 5/6 to use.
pytest tests/test_recipient_resolution.py -v
```

---

## Phase 5: Text2SQLAgent — Constrained Evidence Retrieval

> Goal: Add Text2SQLAgent as optional evidence sub-agent for complex queries that
> structured code alone can't handle well. Constrained SELECT only.

### Step 5.1: `backend/agents/sub_agents/text2sql.py`

```python
class Text2SQLAgent:
    """Evidence retrieval sub-agent. Generates constrained SELECT queries.

    ALLOWED:
    - SELECT queries against allowlisted tables
    - WHERE clause must include user_id filter
    - Must have LIMIT clause
    - Aggregations (SUM, COUNT, AVG, MAX, MIN)
    - GROUP BY, ORDER BY, JOINs between allowed tables

    FORBIDDEN:
    - INSERT, UPDATE, DELETE, DROP, ALTER, CREATE
    - Queries without user_id scope
    - Queries without LIMIT
    - Subqueries referencing non-allowed tables
    - Any action/execution language

    Flow: natural language → LLM → SQL → SQLGuardian → SQLExecutor → evidence rows
    """

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        """
        task_type: "query_evidence"
        constraints: {
            "query_goal": str,        # e.g. "find_previous_transfer", "find_top_recipient"
            "user_id": str,           # injected by PlanExecutor from backend context
            "recipient_hint": str | None,
            "period": str | None,     # "last_month", "last_week", etc.
            "metric": str | None,     # "total_amount", "frequency"
            "amount": int | None
        }

        1. Build structured prompt from query_goal + constraints (not free-form question)
        2. Generate SQL via LLM (strict system prompt)
        3. SQLGuardian.validate(sql, user_id) — reject if invalid
        4. SQLExecutor.execute(validated_sql, params) — user_id injected from backend context
        5. Return {"sql": str, "params": dict, "rows": list, "explanation": str} for auditability
        """
        ...
```

### Step 5.2: `backend/services/sql_guardian.py`

```python
class SQLGuardian:
    """Validates LLM-generated SQL before execution.

    Checks:
    1. Statement type is SELECT only (parse first token / use sqlparse)
    2. Tables referenced are in allowlist: {users, accounts, beneficiaries, transactions}
    3. WHERE clause contains user_id = :user_id (parameterized)
    4. LIMIT clause present (max 100)
    5. No dangerous functions (LOAD_FILE, INTO OUTFILE, etc.)
    6. No UNION with non-allowed tables

    Returns: (validated_sql, params) or raises SQLValidationError
    """

    ALLOWED_TABLES = {"users", "accounts", "beneficiaries", "transactions"}
    MAX_LIMIT = 100

    def validate(self, sql: str, user_id: str) -> tuple[str, dict]:
        ...
```

### Step 5.3: `backend/services/sql_executor.py`

```python
class SQLExecutor:
    """Executes validated SQL against banking.db.

    Security:
    - Only accepts SQL that passed SQLGuardian
    - Injects user_id from backend context (task.constraints["user_id"])
    - NEVER uses user_id from LLM output
    - Returns results as list[dict]
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def execute(self, sql: str, params: dict) -> list[dict]:
        # params["user_id"] always comes from backend auth context
        ...
```

### Step 5.4: `backend/prompts/text2sql.py`

```text
You are not answering the user directly.
You generate SQL only for the query_goal provided by the transaction planner.
Use the structured fields (recipient_hint, period, metric, amount) as query constraints.
Do not infer user_id — it will be injected by the system.
Do not infer execution intent — you are only retrieving evidence.

RULES:
- Generate SELECT statements ONLY. No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE.
- ALWAYS include WHERE user_id = :user_id
- ALWAYS include LIMIT (max 100)
- Available tables: users, accounts, beneficiaries, transactions
- Available columns: [full schema listing]
- Use query_goal and structured constraints to build precise SQL.

Return JSON:
{
  "sql": "SELECT ... FROM ... WHERE user_id = :user_id AND ... LIMIT ...",
  "explanation": "brief explanation of what this query finds"
}
```

### Step 5.5: Register Text2SQLAgent

Not yet wired into TransactionAgent (that's Phase 6).
Registered in AgentRegistry for availability.

```python
registry.register("text2sql", Text2SQLAgent(sql_guardian, sql_executor))
```

### Step 5.6: Test Text2SQL pipeline in isolation

```python
# Test: structured goal → valid SQL → returns rows
task = AgentTask(task_type="query_evidence", constraints={
    "query_goal": "find_top_recipient",
    "period": "last_month",
    "metric": "total_amount",
    "user_id": "u1"
})
result = await text2sql_agent.execute_task(task)
assert result.status == "success"
assert "rows" in result.result

# Test: find previous transfer
task = AgentTask(task_type="query_evidence", constraints={
    "query_goal": "find_previous_transfer",
    "recipient_hint": "Minh",
    "period": "last_month",
    "user_id": "u1"
})
result = await text2sql_agent.execute_task(task)
assert result.status == "success"

# Test: SQLGuardian rejects DELETE statement
# Test: SQLGuardian rejects query without user_id
# Test: SQLGuardian rejects query without LIMIT
# Test: SQLGuardian rejects non-allowed table
```

---

## Phase 6: Dynamic Planning Inside TransactionAgent

> Goal: Refactor TransactionAgent from hardcoded if/else to LLM-generated resolution plan.
> This is the core agentic layer — proves agent-to-agent autonomous orchestration.
>
> **MVP scope:** Planner only needs to support 3 planning patterns:
> 1. Direct name → `recipient_resolution.resolve_by_name`
> 2. Direct account → `recipient_resolution.resolve_by_account`
> 3. Historical reference → `text2sql.query_evidence` → `recipient_resolution.resolve_with_evidence`
>
> Do not over-engineer a generic planner. These 3 patterns are sufficient to prove agent-to-agent.

### Step 6.1: Planning models

**File:** `backend/models.py` — thêm:
```python
class PlanStep(BaseModel):
    agent: str                        # registry key: "recipient_resolution", "text2sql"
    task_type: str                    # "resolve_by_name", "query_evidence", etc.
    input_from: str | None = None     # "extraction" | "step_0" | "step_1"
    constraints: dict = Field(default_factory=dict)
    reason: str                       # why this step is needed

class AgentPlan(BaseModel):
    steps: list[PlanStep] = Field(default_factory=list)
    fallback: Literal["clarify", "proceed_partial"] = "clarify"
    confidence: float = 0.0
```

### Step 6.2: Agent Registry

**File:** `backend/agents/registry.py`

```python
class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, Any] = {}

    def register(self, name: str, agent: Any):
        self._agents[name] = agent

    def get(self, name: str) -> Any:
        return self._agents.get(name)

    def available(self) -> list[str]:
        return list(self._agents.keys())
```

Register:
```python
registry = AgentRegistry()
registry.register("recipient_resolution", RecipientResolutionAgent())
registry.register("text2sql", Text2SQLAgent(sql_guardian, sql_executor))
```

### Step 6.3: Planning prompt

**File:** `backend/prompts/planning.py`

```text
You are a RESOLUTION planner for banking transactions.

Given:
- extraction result (fields already known from user message)
- available sub-agents and their capabilities
- user_id for scoping queries

Generate a resolution plan to fill missing or referenced information ONLY.

RULES:
1. Only generate RESOLUTION steps: resolve recipient, lookup history, query evidence, verify account.
2. NEVER generate EXECUTION steps: transfer_money, send_otp, approve, bypass_guardian, execute, confirm.
3. Only use agents from the provided allowlist.
4. Maximum 5 steps.
5. If ALL required fields are already present, return empty plan: {"steps": [], "confidence": 1.0}
6. Each step must have a "reason" explaining why it's needed.
7. Prefer deterministic RecipientResolutionAgent for direct name/account resolution.
8. Use Text2SQLAgent ONLY when the user refers to historical or analytical banking data
   (e.g. "last month", "most transferred", "last time", "same as before", spending history).
9. If recipient_hint is present and NO reference_context → use recipient_resolution.resolve_by_name
10. If reference_context exists with time/history reference → text2sql.query_evidence then recipient_resolution.resolve_with_evidence
11. If account is provided but name unknown → use recipient_resolution.resolve_by_account

Available agents:
{available_agents_description}

Extraction context:
{extraction_json}
```

### Step 6.4: Plan Validator

**File:** `backend/services/plan_validator.py`

```python
EXECUTION_BLOCKLIST = {
    "transfer_money", "execute_transfer", "send_otp",
    "approve_transaction", "bypass_guardian", "execute",
    "confirm", "block", "unblock", "send_money",
}

ALLOWED_TASKS_PER_AGENT = {
    "recipient_resolution": {"resolve_by_name", "resolve_by_account", "resolve_with_evidence"},
    "text2sql": {"query_evidence"},
}

class PlanValidator:
    def validate(self, plan: AgentPlan, allowed_agents: set[str]) -> AgentPlan:
        if len(plan.steps) > 5:
            raise PlanValidationError("Plan exceeds max 5 steps")
        for i, step in enumerate(plan.steps):
            if step.agent not in allowed_agents:
                raise PlanValidationError(f"Agent '{step.agent}' not in allowlist: {allowed_agents}")
            if step.task_type.lower() in EXECUTION_BLOCKLIST:
                raise PlanValidationError(f"Execution task_type '{step.task_type}' forbidden in resolution plan")
            # Validate task_type is allowed for this specific agent
            allowed_tasks = ALLOWED_TASKS_PER_AGENT.get(step.agent, set())
            if allowed_tasks and step.task_type not in allowed_tasks:
                raise PlanValidationError(f"task_type '{step.task_type}' not allowed for agent '{step.agent}'. Allowed: {allowed_tasks}")
            if step.input_from == f"step_{i}":
                raise PlanValidationError(f"Circular reference: step_{i} references itself")
        return plan
```

### Step 6.5: Plan Executor

**File:** `backend/services/plan_executor.py`

```python
class PlanExecutor:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    async def execute(self, plan: AgentPlan, context: dict) -> dict[str, AgentTaskResult]:
        results = {}
        for i, step in enumerate(plan.steps):
            agent = self.registry.get(step.agent)
            if not agent:
                results[f"step_{i}"] = AgentTaskResult(status="failed", result={"error": f"Agent '{step.agent}' not found"})
                continue

            # Build constraints: merge step constraints + user_id from context
            task_constraints = {**step.constraints, "user_id": context["user_id"]}

            # Chain: if input_from references previous step, merge its result
            if step.input_from and step.input_from.startswith("step_"):
                prev = results.get(step.input_from)
                if prev and prev.status == "success":
                    task_constraints["evidence_rows"] = prev.result.get("rows", [])
                    task_constraints.update(prev.result)

            task = AgentTask(task_type=step.task_type, constraints=task_constraints)
            results[f"step_{i}"] = await agent.execute_task(task)
        return results
```

### Step 6.6: Domain agent allowlist

```python
TRANSACTION_ALLOWED_AGENTS = {
    "recipient_resolution",
    "text2sql",
}
```

TransactionAgent CANNOT call: executor, guardian, card_resolver.

### Step 6.7: Refactor TransactionAgent.run()

```python
class TransactionAgent:
    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        trace = []

        # 1. Extract
        extraction = await self._extract_entities(message)
        trace.append("extract_entities")

        if extraction.needs_clarification:
            return DomainAgentOutput(status="clarification_needed", ...)

        # 2. Generate resolution plan (LLM)
        plan = await self._generate_plan(extraction)
        trace.append("generate_plan")

        # 3. Validate plan (fixed safety)
        plan = self.plan_validator.validate(plan, TRANSACTION_ALLOWED_AGENTS)
        trace.append("validate_plan")

        # 4. Execute plan (dynamic)
        if plan.steps:
            results = await self.plan_executor.execute(plan, {"user_id": user_id, "extraction": extraction.model_dump()})
            trace.append("execute_plan")
            extraction = self._merge_results(extraction, results)

        # 5. Check if resolution succeeded — still missing required fields?
        if self._still_missing_required(extraction):
            return DomainAgentOutput(status="clarification_needed", clarification_message=self._missing_message(extraction))

        # 6. Build ActionDraft
        draft = self._build_draft(extraction)
        trace.append("build_draft")

        return DomainAgentOutput(status="draft_ready", action_draft=draft, delegation_trace=trace)
```

### Step 6.8: Test all 5 scenarios with dynamic planning

```bash
# Scenario 1: "Chuyển 2tr cho Minh"
# Plan: [recipient_resolution.resolve_by_name(name="Minh")]
# → draft_ready
# delegation_trace: [extract_entities, generate_plan, validate_plan, execute_plan, build_draft]

# Scenario 2: "Chuyển cho Minh 2 triệu như tháng trước"
# Plan: [text2sql.query_evidence(...), recipient_resolution.resolve_with_evidence(input_from=step_0)]
# → draft_ready

# Scenario 3: "Chuyển cho người tôi gửi nhiều nhất tháng trước 2 triệu"
# Plan: [text2sql.query_evidence(find top recipient), recipient_resolution.resolve_with_evidence(input_from=step_0)]
# → draft_ready

# Scenario 4: Ambiguous "Minh"
# Plan: [recipient_resolution.resolve_by_name(name="Minh")]
# → clarification_needed (multiple candidates)

# All Phase 3/4 test cases still pass (no regression)
pytest tests/ -v
```

---

## Phase 7: Guardian + Friction + PendingAction + Minimal Audit

> Goal: Every ActionDraft goes through Guardian → risk tier → Friction → PendingAction.
> Minimal structured audit logging starts here.

### Step 7.1: Thêm models

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
    draft: dict              # serialized ActionDraft
    risk_tier: str
    auth_required: str
    created_at: str
    executed: bool = False
```

### Step 7.2: `backend/services/guardian.py`

Guardian.evaluate() nhận **typed ActionDraft** + queries `reported_accounts` from banking.db:

```python
class Guardian:
    """Deterministic risk assessment. No LLM involved.

    Hard rules (instant BLOCK / RED):
    - recipient_account in reported_accounts → RED
    - amount > 100,000,000 VND → RED

    Soft scoring (additive):
    - amount > 50,000,000 → +0.3
    - recipient not in user's beneficiaries → +0.2
    - first-time recipient + high amount → +0.3
    - unusual time (2am-5am) → +0.1
    - amount > 3x user's average transfer → +0.2
    - resolution_confidence < 0.8 → +0.2
    - resolution_source == "text2sql_evidence" (indirect reference) → +0.15

    Tier mapping:
    - score < 0.2 → GREEN
    - 0.2 ≤ score < 0.5 → YELLOW
    - 0.5 ≤ score < 0.8 → ORANGE
    - score ≥ 0.8 or hard rule → RED
    """

    def evaluate(self, draft: ActionDraft, user_id: str, session_id: str) -> GuardianDecision:
        ...
```

### Step 7.3: `backend/services/friction.py`

```python
FRICTION_MAP = {
    "GREEN": FrictionResult(auth_type="bank_confirm", message="Xác nhận giao dịch"),
    "YELLOW": FrictionResult(auth_type="otp", message="Nhập mã OTP để xác nhận"),
    "ORANGE": FrictionResult(auth_type="challenge", message="Trả lời câu hỏi bảo mật"),
    "RED": FrictionResult(auth_type="blocked", message="Giao dịch bị từ chối vì lý do bảo mật"),
}
```

### Step 7.4: `backend/services/session.py`

```python
# MVP: in-memory dict. Single worker (uvicorn --workers 1).
# Production: Redis or Postgres.
class SessionStore:
    def store_pending(self, action: PendingAction) -> None: ...
    def get_pending(self, action_id: str) -> PendingAction | None: ...
    def mark_executed(self, action_id: str) -> None: ...
```

### Step 7.5: `backend/services/agent_runtime.py`

```python
class AgentRuntime:
    """Fixed control plane: DomainAgentOutput → Guardian → Friction → PendingAction → Response"""

    async def process(self, agent_output: DomainAgentOutput, request: ChatRequest, intent: IntentResult) -> ChatResponse:
        # clarification → pass through
        if agent_output.status == "clarification_needed":
            return ChatResponse(status="clarification_needed", message=agent_output.clarification_message)

        # info_response → pass through
        if agent_output.status == "info_response":
            return ChatResponse(status="completed", message=agent_output.info_response)

        # draft_ready → Guardian → Friction → PendingAction
        draft = agent_output.action_draft
        decision = self.guardian.evaluate(draft, request.user_id, request.session_id)

        if decision.decision == "BLOCK":
            self._log_trace(request, intent, draft, decision, None, "blocked")
            return ChatResponse(status="blocked", message=decision.reasons[0] if decision.reasons else "Giao dịch bị từ chối.", risk_tier=decision.risk_tier)

        friction = self.friction_router.route(decision)
        pending = PendingAction(action_id=str(uuid4()), ...)
        self.session_store.store_pending(pending)
        self._log_trace(request, intent, draft, decision, friction, "pending_auth")

        return ChatResponse(
            status="pending_auth",
            pending_action_id=pending.action_id,
            action_preview=draft.model_dump(),
            risk_tier=decision.risk_tier,
            auth_required=friction.auth_type,
            message=friction.message,
        )
```

### Step 7.6: Minimal audit logging

```python
# backend/services/audit.py
import logging
logger = logging.getLogger("trustflow.audit")

def log_request_trace(request_id, user_id, intent, draft, guardian_decision, friction_result, final_status):
    logger.info("AUDIT_TRACE", extra={
        "request_id": request_id,
        "user_id": user_id,
        "intent": intent,
        "draft": draft,
        "guardian_decision": guardian_decision,
        "friction_result": friction_result,
        "final_status": final_status,
    })
```

### Step 7.7: Wire vào `/chat`

```python
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    intent = await classify_intent(request.message)
    agent = DOMAIN_AGENT_MAP.get(intent.task_type)
    if agent:
        output = await agent.run(request.message, request.user_id, request.session_id)
        return await agent_runtime.process(output, request, intent)
    else:
        return ChatResponse(status="classified", message=f"Intent: {intent.task_type}", data=intent.model_dump())
```

**Test:**
```bash
# Scenario 1: GREEN
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh tiền ăn trưa","session_id":"s1"}'
# → {"status":"pending_auth","risk_tier":"GREEN","auth_required":"bank_confirm","pending_action_id":"..."}

# Scenario 5: RED — scam account
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 50tr vào 6666666666","session_id":"s1"}'
# → {"status":"blocked","risk_tier":"RED","message":"..."}
```

---

## Phase 8: Confirm/OTP Endpoints + Executor

> Goal: User confirm/OTP pending action → execute.

### Step 8.1: Thêm models

**File:** `backend/models.py`:
```python
class ConfirmRequest(BaseModel):
    user_id: str
    session_id: str | None = None
    # Demo only: user_id from body. Production: from JWT.

class OTPRequest(BaseModel):
    user_id: str
    otp_code: str
    session_id: str | None = None

class ActionResponse(BaseModel):
    status: Literal["executed", "failed"]
    message: str
    execution_id: str | None = None
```

### Step 8.2: `backend/executors/transaction.py`

TransactionExecutor (mock: always succeed, log details).

### Step 8.3: Endpoints

```python
@app.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, req: ConfirmRequest):
    # Load pending → verify user_id → verify auth_type == "bank_confirm"
    # → execute → mark_executed → audit log → return ActionResponse

@app.post("/actions/{action_id}/otp")
async def otp_action(action_id: str, req: OTPRequest):
    # Load pending → verify user_id → verify OTP ("123456" for demo)
    # → execute → mark_executed → audit log → return ActionResponse
```

### Step 8.4: Error handling

- 404: action not found
- 401: user_id mismatch
- 403: wrong auth type / action was blocked
- 409: already executed

**Test:**
```bash
# Full lifecycle: chat → confirm
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 2tr cho Minh","session_id":"s1"}'
# Get action_id

curl -X POST http://localhost:8000/actions/{action_id}/confirm \
  -H "Content-Type: application/json" -d '{"user_id":"u1"}'
# → {"status":"executed","execution_id":"txn_..."}

# OTP flow (YELLOW — higher amount)
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"u1","message":"Chuyển 15 triệu cho Lan","session_id":"s1"}'

curl -X POST http://localhost:8000/actions/{action_id}/otp \
  -H "Content-Type: application/json" -d '{"user_id":"u1","otp_code":"123456"}'
# → {"status":"executed"}

# Error: wrong user
curl -X POST http://localhost:8000/actions/{action_id}/confirm \
  -H "Content-Type: application/json" -d '{"user_id":"u2"}'
# → 401
```

---

## Phase 9: Full Audit + E2E Tests

> Goal: Full AuditEntry model + viewer endpoint. All 5 demo scenarios pass end-to-end.
>
> **Note:** If time is short, audit can be simplified to just: `delegation_trace`, `plan`, `guardian_decision`, `final_status`.
> The full AuditEntry below is the ideal; the minimal version still demonstrates observability.

### Step 9.1: `AuditEntry` model

```python
class AuditEntry(BaseModel):
    request_id: str
    user_id: str
    timestamp: str
    intent: dict | None = None
    domain_agent: str | None = None
    delegation_trace: list[str] = Field(default_factory=list)
    plan: dict | None = None
    plan_execution: dict | None = None
    draft: dict | None = None
    guardian_decision: dict | None = None
    friction_result: dict | None = None
    execution_result: dict | None = None
    final_status: str
```

### Step 9.2: `backend/services/audit.py` — full implementation

AuditLogger: log() + get_trace(session_id) + get_recent(user_id).

### Step 9.3: `GET /audit/{session_id}` endpoint

### Step 9.4: E2E tests — all 5 scenarios

```bash
pytest tests/test_e2e.py -v
# Scenario 1: GREEN flow → confirm → executed ✓
# Scenario 2: reference context → Text2SQL evidence → resolve → confirm ✓
# Scenario 3: top recipient → Text2SQL → resolve → OTP → executed ✓
# Scenario 4: ambiguous recipient → clarification ✓
# Scenario 5: scam account → blocked ✓
```

---

## Phase 10: Fraud Report Agent

> Goal: User can report fraud accounts via conversational chat. Multi-turn flow with
> verification, context questions, confidence scoring, and risk update.

### Step 10.1: Intent — add FRAUD_REPORT

**File:** `backend/models.py` — update IntentResult.task_type:
```python
task_type: Literal["QA", "DATA_QUERY", "TRANSACTION", "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION", "FRAUD_REPORT"]
```

**File:** `backend/prompts/intent.py` — add FRAUD_REPORT classification examples.

### Step 10.2: Fraud-specific models

**File:** `backend/models.py` — thêm:
```python
class FraudReportExtraction(BaseModel):
    """Extracted from user message when reporting fraud."""
    operation: Literal["REPORT_FRAUD_ACCOUNT"] = "REPORT_FRAUD_ACCOUNT"
    reported_account_no: str | None = None
    reported_bank_code: str | None = None
    reason_hint: str | None = None
    missing_fields: list[str] = Field(default_factory=list)

class FraudContextAnswers(BaseModel):
    """Collected during multi-turn fraud context questions."""
    fraud_type: str | None = None        # SHOPPING_SCAM, INVESTMENT_SCAM, etc.
    contact_channel: str | None = None   # FACEBOOK, ZALO, etc.
    aftermath: str | None = None         # BLOCKED_CONTACT, NO_GOODS, etc.
    has_evidence: bool = False
    selected_transaction_ref: str | None = None

class FraudReportDraft(BaseModel):
    """Draft for FraudReportExecutor."""
    operation: str = "REPORT_FRAUD_ACCOUNT"
    reported_account_no: str
    reported_bank_code: str
    transaction_ref: str | None = None
    fraud_type: str | None = None
    contact_channel: str | None = None
    aftermath: str | None = None
    has_evidence: bool = False
    confidence_score: int = 0
    reason_text: str | None = None
```

### Step 10.3: FraudVerificationAgent (sub-agent)

**File:** `backend/agents/sub_agents/fraud_verification.py`

```python
class FraudVerificationAgent:
    """Verifies user has real transactions with reported account.

    task_type: "verify_transaction_relationship"
    constraints: {user_id, counterparty_account_no, counterparty_bank_code}

    Logic:
    1. Query transactions WHERE user_id = ? AND counterparty_account_no = ?
       AND counterparty_bank_code = ? AND direction = 'OUT' AND status = 'SUCCESS'
    2. If 0 results → status="no_relationship"
    3. If results → status="verified", returns list of matching transactions
    """

    async def execute_task(self, task: AgentTask) -> AgentTaskResult:
        ...
```

### Step 10.4: FraudReportAgent (domain agent)

**File:** `backend/agents/fraud_report.py`

```python
class FraudReportAgent:
    """Domain agent for FRAUD_REPORT intent.

    Multi-turn conversational flow:
    Turn 1: Extract reported_account_no + bank_code → verify transaction relationship
    Turn 2: Show matching transactions, ask user to select
    Turn 3-4: Ask fraud context questions (fraud_type, contact_channel, aftermath, evidence)
    Turn 5: Calculate confidence, build draft

    Uses session store to track multi-turn state.
    """

    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        # 1. Check session for in-progress fraud report
        # 2. If new: extract → verify → show transactions
        # 3. If in-progress: collect next answer → advance state
        # 4. When all context collected: calculate confidence → build draft
        ...

    def _calculate_confidence(self, context: FraudContextAnswers, transaction_age_days: int) -> int:
        """Rule-based confidence scoring.
        +40: has verified transaction
        +20: transaction within 30 days
        +15: fraud_type is clear (not OTHER)
        +15: aftermath is clear (not OTHER)
        +10: has evidence
        """
        score = 40  # base: verified transaction exists
        if transaction_age_days <= 30:
            score += 20
        if context.fraud_type and context.fraud_type != "OTHER":
            score += 15
        if context.aftermath and context.aftermath != "OTHER":
            score += 15
        if context.has_evidence:
            score += 10
        return min(score, 100)
```

### Step 10.5: FraudReportExecutor

**File:** `backend/executors/fraud_report.py`

```python
class FraudReportExecutor:
    """Executes fraud report: insert report + update risk signals.

    Steps:
    1. INSERT into fraud_reports (status=VALIDATED)
    2. UPSERT reported_accounts_v2:
       - Increment valid_report_count, unique_reporter_count
       - Add transaction amount to total_reported_amount
       - Recalculate avg_confidence_score
       - Recalculate risk_level based on rules
    3. IF same-bank (reported_bank = our bank):
       - Lookup customer by account
       - UPSERT reported_customers (increment counters, recalculate risk)
    """

    def execute(self, draft: FraudReportDraft, user_id: str) -> dict:
        ...

    def _calculate_account_risk_level(self, report_count: int, unique_reporters: int) -> str:
        """
        1 report → LOW
        2 reports → MEDIUM
        3-4 reports from 3+ users → HIGH
        5+ reports OR avg_confidence >= 80 → CRITICAL
        """
        ...
```

### Step 10.6: Wire into /chat + multi-turn session

**File:** `backend/main.py` — add to DOMAIN_AGENT_MAP:
```python
DOMAIN_AGENT_MAP = {
    "TRANSACTION": transaction_agent,
    "FRAUD_REPORT": fraud_report_agent,
}
```

Multi-turn state stored in SessionStore (session_id scoped).

### Step 10.7: Tests

```bash
# Test: report with verified transaction → confidence 100
# Test: report without transaction → rejected
# Test: multi-turn context collection
# Test: FraudReportExecutor updates reported_accounts risk
pytest tests/test_fraud_report.py -v
```

---

## Phase 11: Transaction Screening (Guardian Fraud Check)

> Goal: When Guardian evaluates a TRANSFER ActionDraft, check fraud risk of receiver
> using reported_accounts_v2 and reported_customers. Log fraud_decisions.

### Step 11.1: Update Guardian with fraud screening

**File:** `backend/services/guardian.py` — add to evaluate():

```python
# After existing hard rules, before soft scoring:

# Fraud screening: check receiver against reported_accounts_v2
reported = self._check_reported_account(
    draft.recipient_account, draft.recipient_bank
)
if reported:
    if reported["risk_level"] == "CRITICAL":
        return GuardianDecision(decision="BLOCK", risk_tier="RED",
            reasons=[f"Tài khoản nhận đã bị xác nhận lừa đảo ({reported['valid_report_count']} báo cáo)"])
    elif reported["risk_level"] == "HIGH":
        score += 0.7
        reasons.append(f"Tài khoản nhận có {reported['valid_report_count']} báo cáo lừa đảo")
    elif reported["risk_level"] == "MEDIUM":
        score += 0.5
        reasons.append(f"Tài khoản nhận từng bị báo cáo ({reported['valid_report_count']} lần)")
    elif reported["risk_level"] == "LOW":
        score += 0.3
        reasons.append("Tài khoản nhận có 1 báo cáo lừa đảo chưa xác nhận")

# Also check reported_customers if same-bank
reported_customer = self._check_reported_customer(draft.recipient_account)
if reported_customer and reported_customer["risk_level"] in ("FROZEN", "BLOCKED"):
    return GuardianDecision(decision="BLOCK", risk_tier="RED",
        reasons=["Chủ tài khoản nhận đang bị đóng băng/chặn do nhiều báo cáo gian lận"])
```

### Step 11.2: Log fraud_decisions

```python
# In Guardian or AgentRuntime, after screening:
def _log_fraud_decision(self, action_id, receiver_account, receiver_bank, risk_level, decision):
    # INSERT INTO fraud_decisions (...)
    ...
```

### Step 11.3: ChatResponse fraud warning

When decision = WARN:
```python
ChatResponse(
    status="pending_auth",
    message="⚠️ Cảnh báo: Tài khoản này từng bị báo cáo lừa đảo bởi người dùng khác. Bạn có chắc chắn muốn tiếp tục?",
    risk_tier="YELLOW",
    auth_required="otp",
    ...
)
```

### Step 11.4: Tests

```bash
# Test: transfer to CRITICAL account → BLOCK
# Test: transfer to HIGH account → ORANGE + OTP
# Test: transfer to MEDIUM account → WARN + STEP_UP
# Test: transfer to LOW account → WARN only
# Test: transfer to clean account → no fraud warning
# Test: fraud_decisions logged for every screened transfer
pytest tests/test_fraud_screening.py -v
```

---

## Phase 12: Frontend

> Goal: Streamlit UI with chat + confirm/OTP/block modals + audit trace viewer + fraud report flow.

### Step 12.1: `frontend/app.py` — main layout
### Step 12.2: `frontend/components/chat.py` — chat interface
### Step 12.3: `frontend/components/bank_confirm.py` — confirm modal (GREEN)
### Step 12.4: `frontend/components/otp_modal.py` — OTP input (YELLOW)
### Step 12.5: `frontend/components/blocked_warning.py` — block explanation (RED)
### Step 12.6: `frontend/components/fraud_report.py` — fraud report multi-turn UI
### Step 12.7: `frontend/components/audit_viewer.py` — expandable trace: plan → execution → guardian → friction

**Test:** `streamlit run frontend/app.py` → all 7 demo scenarios work visually.

---

## Later: CardAgent + DataQueryAgent

> Reuse the same planning/runtime pattern established in Phase 6.

### CardAgent
```python
CARD_ALLOWED_AGENTS = {"card_resolver"}

class CardAgent:
    # Uses same: extract → plan → validate → execute → build_draft → Guardian → Friction
    # card_resolver queries banking.db (future: cards table) or mock JSON
```

### DataQueryAgent
```python
DATA_QUERY_ALLOWED_AGENTS = {"text2sql"}

class DataQueryAgent:
    # Uses same: extract → plan → validate → execute → summarize
    # Returns DomainAgentOutput(status="info_response") — no ActionDraft
    # Guardian not required for read-only queries
```

---

## Summary: What each phase delivers

| Phase | Deliverable | Can demo |
|-------|-------------|----------|
| 1 | ChatRequest + ChatResponse envelope + echo | Server starts, stable API |
| 2 | IntentResult + LLM classify | "Chuyển 2tr" → TRANSACTION |
| 3 | banking.db + TransactionAgent + RecipientResolution (hardcoded) | Draft from NL, realistic DB |
| 4 | RecipientResolution + resolve_with_evidence | Evidence-based verification |
| 5 | Text2SQLAgent + SQLGuardian + SQLExecutor | Complex evidence queries |
| 6 | Dynamic planning (AgentPlan + Registry + Validator + Executor) | **Agent-to-agent tự động** |
| 7 | Guardian + Friction + PendingAction + minimal audit | Risk tiers, block/allow |
| 8 | Confirm/OTP + Executor | Full lifecycle |
| 9 | Full AuditEntry + E2E tests | 5 scenarios pass |
| 10 | FraudReportAgent + FraudVerificationAgent + FraudReportExecutor | **Fraud report flow** |
| 11 | Transaction Screening (Guardian fraud check + fraud_decisions) | **Real-time fraud protection** |
| 12 | Frontend | Visual demo |

---

## Architecture Invariants

1. **Orchestrator is a thin router.** Only maps intent → domain agent. No business logic.
2. **Dynamic planning is resolution-only.** LLM planner CANNOT generate execution/approval steps.
3. **Each domain agent has an allowlist.** TransactionAgent can only call: recipient_resolution, text2sql. FraudReportAgent can only call: fraud_verification.
4. **Text2SQL is evidence-retrieval only.** SELECT only. Validated by SQLGuardian. user_id injected by backend.
5. **RecipientResolutionAgent auto-resolves only with exactly 1 high-confidence verified candidate.** Multiple candidates or low confidence → clarification_needed.
6. **Guardian is mandatory for all ActionDrafts.** No bypass, even for GREEN tier.
7. **Typed models at boundaries.** TransactionExtraction, ActionDraft, FraudReportDraft, GuardianDecision — never raw dict.
8. **Fixed outer control plane.** Guardian → Friction → PendingAction → Executor is never LLM-controlled.
9. **Never trust LLM-generated user_id.** SQLExecutor always injects from backend auth context.
10. **Text2SQL must not:** execute money movement, approve transactions, choose recipients, bypass Guardian, generate DML/DDL.
11. **Fraud report requires verified transaction.** Agent MUST verify user has real outgoing transaction to reported account before creating report. No report without evidence.
12. **Transaction screening is mandatory.** Every TRANSFER ActionDraft must check reported_accounts_v2 before Guardian decision. fraud_decisions logged for every screened transfer.

---

## Rules

1. **Mỗi step chỉ code đúng những gì cần để test step đó** — không tạo trước
2. Model mới chỉ xuất hiện ở phase nào cần nó lần đầu (exception: ChatResponse Phase 1 as API contract)
3. Endpoint mới chỉ tạo khi có logic xử lý, không tạo stub endpoint
4. File/folder mới chỉ tạo khi step đó import từ nó
5. Run server sau mỗi step để verify no import error
6. banking.db created once at Phase 3, reused by all subsequent phases
