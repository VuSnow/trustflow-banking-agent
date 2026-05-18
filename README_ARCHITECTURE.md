# TrustFlow Guardian

> Natural-language banking assistant with adversarial safety built in.

**Core Message:** Users can query, look up, and transact using natural language — but every critical action is validated by the Guardian Layer to prevent bad queries, risky transactions, and scams.

**Core Principle:**

```text
Orchestrator routes → AgentClient prepares → Guardian validates → Executor executes → Audit logs
```

- **LLM prepares, never executes.** Agent only creates drafts/payloads.
- **Hard rules first, model second.** Deterministic safety before probabilistic scoring.
- **Executor is separate from Agent.** Agent prepares; Executor acts after Guardian approves.
- **Immutable audit trail.** Append-only, every decision explained.

---

## Repo Scope

This repo is **Orchestrator + Guardian + Executors + Frontend**.

Specialist agents (Text2SQL, QA RAG, Transaction Parser) are designed behind an `AgentClient` interface. In hackathon: mock implementations live here. In production: swap to HTTP/gRPC clients calling separate services.

```text
┌─────────────────────────────────────┐
│  THIS REPO                           │
│  • Orchestrator (routing + wiring)  │
│  • Guardian (safety layer)          │
│  • Executors (post-guardian action) │
│  • Frontend (demo UI)              │
│  • AgentClient mocks               │
└─────────────────────────────────────┘
         │
         │ Interface call (hackathon: local, production: HTTP/gRPC)
         ▼
┌─────────────────────────────────────┐
│  SEPARATE REPOS (production)         │
│  • Transaction Agent Service        │
│  • Text2SQL Agent Service           │
│  • QA/RAG Agent Service             │
└─────────────────────────────────────┘
```

---

## Hackathon Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Streamlit)                      │
│  • Chat UI + risk badges (🟢🟡🟠🔴)                              │
│  • Bank confirmation modal (GREEN)                               │
│  • OTP step-up modal (YELLOW)                                    │
│  • Scam alert modal (RED)                                        │
│  • Audit trail viewer (expandable per message)                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY (FastAPI) — THIS REPO                  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ORCHESTRATOR                                               │  │
│  │ • Intent classification (1 LLM call)                      │  │
│  │ • Route to AgentClient (via interface)                    │  │
│  │ • Pass agent output → Guardian                            │  │
│  │ • If Guardian approves → Executor                         │  │
│  │ • Compile response → Frontend                             │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │ AGENT CLIENTS (interface + mock implementations)           │  │
│  │                                                            │  │
│  │ Interface: prepare(input, context) → AgentOutput          │  │
│  │                                                            │  │
│  │ • TransactionAgentClient  → mock: LLM parse NL→payload   │  │
│  │ • Text2SQLAgentClient     → mock: LLM NL→SQL + explain   │  │
│  │ • QAAgentClient           → mock: keyword search policies │  │
│  │                                                            │  │
│  │ ⚠️  Agents ONLY prepare. Never execute. Never call APIs.  │  │
│  │ ⚠️  Transaction-critical fields NEVER auto-guessed.       │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │ GUARDIAN                                                    │  │
│  │                                                            │  │
│  │ Layer 1: HARD RULES (deterministic, instant decision)      │  │
│  │   • Recipient in reported_accounts → RED                  │  │
│  │   • Amount > daily_limit → BLOCK                          │  │
│  │   • Pressure/threat keywords → ORANGE minimum             │  │
│  │   • SQL contains DML/DDL → REJECT                         │  │
│  │   • Consent scope violated → BLOCK                        │  │
│  │   → If triggered: SKIP Layer 2, go to decision            │  │
│  │                                                            │  │
│  │ Layer 2: MODEL-BASED (only if no hard rule triggered)      │  │
│  │   • Anomaly Detector (amount/recipient/urgency/time)      │  │
│  │   • Scam Pattern Matcher (rules + LLM advisory)           │  │
│  │   • SQL Validator (AST + allowlist + scope + LIMIT)       │  │
│  │   • QA Validator (citation? confidence? version?)         │  │
│  │                                                            │  │
│  │ Risk Scorer: weighted(anomaly×0.35, scam×0.35,            │  │
│  │              amount×0.15, recipient×0.15) → tier           │  │
│  │                                                            │  │
│  │ Friction Router: tier → auth requirement                  │  │
│  │   GREEN(0–0.3)  → bank-native confirm                    │  │
│  │   YELLOW(0.3–0.6) → warn + OTP/PIN                       │  │
│  │   ORANGE(0.6–0.8) → challenge + cooldown + OTP            │  │
│  │   RED(0.8–1.0) → hard block, no bypass                   │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │ EXECUTORS (post-guardian, separate from agents)            │  │
│  │                                                            │  │
│  │ • TransactionExecutor → call bank API (mock in hackathon) │  │
│  │ • SQLExecutor → run parameterized read-only query         │  │
│  │ • QAResponseExecutor → return grounded answer             │  │
│  │                                                            │  │
│  │ ⚠️  Executors ONLY run after Guardian approves.           │  │
│  │ ⚠️  Idempotency key prevents double-execution.           │  │
│  │ ⚠️  SQLExecutor injects user_id from auth context,       │  │
│  │     NEVER trusts user_id from LLM-generated SQL.          │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                    │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │ AUDIT (append-only)                                        │  │
│  │ • Immutable JSON log per request                          │  │
│  │ • Schema defined upfront (see models.py)                  │  │
│  │ • No edit, no delete                                      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ DATA (mock)                                                │  │
│  │ • users.json (profiles + behavioral baselines)            │  │
│  │ • reported_accounts.json (scam registry)                  │  │
│  │ • scam_patterns.json (known patterns)                     │  │
│  │ • transactions.db (SQLite, pre-seeded)                    │  │
│  │ • policies/*.md (versioned policy docs)                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

```text
POST /chat                              # Main conversation endpoint
     Request:  ChatRequest {user_id, message, session_id}
     Response: ChatResponse {status, response, risk_tier, pending_action_id, ...}

POST /actions/{action_id}/confirm       # Bank-native confirm (GREEN tier)
     Request:  ActionConfirmRequest {action_id, user_id}
     Response: ChatResponse {status: completed, ...}

POST /actions/{action_id}/otp           # OTP verification (YELLOW/ORANGE tier)
     Request:  OTPVerifyRequest {action_id, user_id, otp_code}
     Response: ChatResponse {status: completed, ...}

GET  /audit/{audit_id}                  # Retrieve audit trail for a request
     Response: AuditEntry
```

---

## Data Flow (per request)

```text
1. User sends message → POST /chat
2. Orchestrator classifies intent + extracts entities (1 LLM call)
3. Orchestrator routes to appropriate AgentClient
4. AgentClient.prepare() → AgentOutput (payload/SQL/answer draft)
     ↳ If missing critical fields → return {needs_clarification: true}
5. Guardian.validate(agent_output, user_context)
     ↳ Layer 1: hard rules check
     ↳ Layer 2: model-based scoring (if no hard rule triggered)
     ↳ Output: {risk_tier, score, reasons[], triggered_by}
6. Friction Router decides auth requirement based on tier
7. If pending_auth (GREEN needs confirm, YELLOW/ORANGE needs OTP):
     ↳ Store pending action in SessionStore
     ↳ Return {status: pending_auth, pending_action_id, transaction_preview}
     ↳ User confirms → POST /actions/{id}/confirm or /otp
8. If approved:
     ↳ Executor.execute(agent_output, auth_context) → result
     ↳ NOTE: SQLExecutor injects user_id from auth context, NEVER from LLM output
9. Audit.log(full trace)
10. Response compiled → Frontend
```

---

## Folder Structure

```text
trustflow-banking-agent/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── README_ARCHITECTURE.md
│
├── backend/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, routes (see API below)
│   ├── config.py                        # Thresholds, env vars, feature flags
│   ├── models.py                        # Pydantic schemas (see below)
│   ├── orchestrator.py                  # Intent → route → guardian → executor → audit
│   │
│   ├── agents/                          # AgentClient interface + mock impls
│   │   ├── __init__.py
│   │   ├── base.py                      # AgentClient ABC: prepare(input, ctx) → AgentOutput
│   │   ├── transaction_client.py        # Mock: LLM parse NL → transfer payload
│   │   ├── text2sql_client.py           # Mock: LLM NL → SQL + explanation
│   │   └── qa_client.py                 # Mock: keyword search over policies
│   │
│   ├── guardian/                         # Safety validation layer
│   │   ├── __init__.py
│   │   ├── engine.py                    # Entry: hard_rules → model_checks → score → friction
│   │   ├── hard_rules.py               # Deterministic instant decisions
│   │   ├── anomaly.py                   # Amount/recipient/urgency/time scoring
│   │   ├── scam_detector.py            # Pattern match + LLM advisory (never decides)
│   │   ├── sql_validator.py            # AST parse (sqlglot) + allowlist + scope
│   │   ├── risk_scorer.py              # Weighted aggregation → tier mapping
│   │   └── friction.py                 # Tier → auth requirement → response strategy
│   │
│   ├── executors/                        # Post-guardian execution
│   │   ├── __init__.py
│   │   ├── base.py                      # Executor ABC
│   │   ├── transaction_executor.py      # Call bank API (mock: return success)
│   │   ├── sql_executor.py             # Run parameterized read-only SQL
│   │   └── qa_executor.py              # Return grounded answer + citation
│   │
│   ├── session/                          # Pending action state management
│   │   ├── __init__.py
│   │   └── store.py                     # In-memory pending actions + challenge state
│   │
│   ├── auth/                             # Auth verification (mock for hackathon)
│   │   ├── __init__.py
│   │   └── mock_auth.py                 # Mock OTP="123456", mock bank confirm
│   │
│   ├── audit/                            # Immutable logging
│   │   ├── __init__.py
│   │   └── logger.py                    # Append-only JSON file writer
│   │
│   ├── prompts/                          # LLM prompt templates
│   │   ├── __init__.py
│   │   ├── intent.py                    # Intent classification + entity extraction
│   │   ├── transaction_parse.py         # NL → transfer payload
│   │   └── scam_advisory.py            # "If this were a scam, which pattern?" (advisory only)
│   │
│   └── data/                             # Mock data for hackathon
│       ├── users.json                   # 3 users + behavioral baselines
│       ├── reported_accounts.json       # Hard-block scam registry
│       ├── scam_patterns.json           # Known scam templates
│       ├── table_allowlist.json         # Permitted tables + columns for SQL
│       ├── transactions.db              # SQLite (pre-seeded from seed script)
│       ├── seed_db.py                   # Script to create SQLite from JSON
│       └── policies/
│           ├── savings.md               # version: 2.1, effective: 2026-01-01
│           ├── credit_card.md           # version: 1.3, effective: 2025-09-01
│           └── account_opening.md       # version: 1.5, effective: 2025-11-01
│
├── frontend/
│   ├── app.py                           # Streamlit main
│   └── components/
│       ├── chat.py                      # Messages + risk tier badges
│       ├── bank_confirm.py             # Transaction preview + confirm (GREEN)
│       ├── otp_modal.py                # OTP input for YELLOW+ (mock: "123456")
│       ├── scam_alert.py              # RED tier warning + alternatives
│       └── audit_viewer.py            # Expandable audit trail per message
│
└── tests/
    ├── test_guardian.py                 # Full guardian pipeline tests
    ├── test_hard_rules.py              # Hard rules unit tests
    ├── test_executors.py               # Executor unit tests
    └── scenarios/
        ├── safe_transfer.json
        ├── scam_reported_account.json
        ├── high_amount_transfer.json
        ├── sql_injection_attempt.json
        └── text2sql_query.json
```

---

## Models (Pydantic Schemas)

```python
# backend/models.py — defined upfront

# === Request/Response ===
class ChatRequest:
    user_id: str
    message: str
    session_id: str

class ChatResponse:
    response: str              # Natural language response to user
    status: str                # completed | pending_auth | blocked | clarification_needed
    risk_tier: str | None      # GREEN | YELLOW | ORANGE | RED (None for non-transaction)
    requires_auth: str | None  # "otp" | "bank_confirm" | "challenge" | None
    pending_action_id: str | None  # ID to confirm/otp if status=pending_auth
    transaction_preview: dict | None
    audit_id: str

class ActionConfirmRequest:
    action_id: str
    user_id: str

class OTPVerifyRequest:
    action_id: str
    user_id: str
    otp_code: str

# === Intent ===
class IntentResult:
    task_type: str             # QA | DATA_QUERY | TRANSACTION
    entities: dict             # amount, recipient, time_range, etc.
    risk_hint: str             # LOW | MEDIUM | HIGH
    needs_clarification: bool
    clarification_message: str | None

# === Agent Output ===
class AgentOutput:
    agent_type: str            # transaction | text2sql | qa
    payload: dict              # Agent-specific prepared output
    confidence: float
    needs_clarification: bool
    clarification_message: str | None

# Agent Output payload examples:
# Transaction: {from_account, to_account, to_name, amount, currency, note}
# Text2SQL:    {sql_template, params}  ← user_id NOT in params, injected by executor
#              e.g. {sql_template: "SELECT ... WHERE user_id = :user_id AND category = :category",
#                    params: {category: "food"}}
# QA:          {answer, cited_chunk, policy_version, confidence}

# === Guardian Decision ===
class GuardianDecision:
    risk_tier: str             # GREEN | YELLOW | ORANGE | RED
    risk_score: float          # 0.0 – 1.0
    triggered_by: str          # HARD_RULE | MODEL
    reasons: list[str]
    hard_rule_name: str | None
    auth_required: str | None  # otp | bank_confirm | challenge | blocked

# === Audit Entry ===
class AuditEntry:
    request_id: str
    session_id: str
    user_id: str
    timestamp: str             # ISO 8601
    input_message: str
    intent: IntentResult
    agent_output: AgentOutput
    guardian_decision: GuardianDecision
    auth_method: str | None
    auth_verified: bool
    executor_result: dict | None
    final_action: str          # executed | blocked | clarification_needed
    idempotency_key: str | None
```

---

## MVP Cutline

### MUST HAVE (Core — determines win/loss)

| Component | Description |
|-----------|-------------|
| Transaction flow | NL → payload → validate → execute → response |
| Guardian full pipeline | Hard rules + anomaly + scam pattern + risk scorer + friction |
| GREEN demo | Safe transfer → preview → confirm → success |
| RED demo | Scam/reported account → hard block → explain → suggest hotline |
| YELLOW demo | Unusual amount → warn → OTP step-up → execute |
| Audit trail | Full decision trace viewable in UI |
| Bank confirm modal | Visual transaction preview (not just chat text) |

### SHOULD HAVE (Strengthens demo)

| Component | Description |
|-----------|-------------|
| Text2SQL | "How much did I spend on food?" → SQL → result (2-3 demo queries) |
| ORANGE demo | Pressure keywords → challenge questions → cooldown |
| Proactive insight | "Spending up 25% vs last month" (descriptive only) |

### BONUS (If time allows)

| Component | Description |
|-----------|-------------|
| QA/RAG | Policy questions → answer + citation + version |
| Multi-intent | "Spent too much, transfer 5M to savings" → 2 tasks |

---

## Consent Scopes (Hackathon — simplified)

```text
read_data          → allows QA, Text2SQL, account lookup
execute_transfer   → allows transaction preparation + execution
```

Production adds: `analyze_spending`, `submit_onboarding`, `manage_beneficiaries`, etc.

---

## LLM Role Boundaries

| LLM IS ALLOWED TO | LLM IS NEVER ALLOWED TO |
|--------------------|-------------------------|
| Extract intent & entities | Execute transactions |
| Generate transfer payload (prepare only) | Override hard rules |
| Generate SQL from NL (prepare only) | Be sole decision-maker for block/allow |
| Explain Guardian decisions in NL | Give financial product recommendations |
| Soft-match scam patterns (advisory only) | Access data outside user's scope |
| Generate proactive insights (descriptive) | Auto-repair transaction-critical fields |

---

## Guardian Decision Matrix

| Action | Layer 1 (Hard Rules) | Layer 2 (Model) | Auth Required | Auto-repair? |
|--------|---------------------|-----------------|---------------|-------------|
| **Transaction GREEN** | Not reported, within limit | Score < 0.3 | Bank-native confirm | Fields: NEVER |
| **Transaction YELLOW** | — | Score 0.3–0.6 | OTP/PIN | Fields: NEVER |
| **Transaction ORANGE** | Pressure detected | Score 0.6–0.8 | Challenge + Cooldown + OTP | Fields: NEVER |
| **Transaction RED** | Reported / over limit | Score 0.8+ | BLOCKED (no bypass) | N/A |
| **Text2SQL** | No DML/DDL | AST + allowlist + scope + LIMIT | None | SQL LIMIT: 1 attempt |
| **QA** | N/A | Citation? Confidence? Version? | None | N/A |

---

## Use Case Flows

### A. Safe Transfer (GREEN)

```text
User: "Transfer 2M to Minh for lunch"
→ Orchestrator: intent=TRANSACTION, entities={amount:2M, recipient:"Minh", note:"lunch"}
→ TransactionAgentClient.prepare() → {from:"user_account", to:"minh_account", amount:2000000, note:"lunch"}
→ Guardian L1: recipient not reported ✓, within limit ✓, consent OK ✓
→ Guardian L2: anomaly(0.08) + scam(0.02) → score=0.06 → GREEN
→ Friction: bank-native confirm required
→ Frontend: show exact preview → user confirms
→ TransactionExecutor.execute() → success
→ Audit.log(full trace)
→ Response: "Transferred 2,000,000₫ to Minh. Your balance: 48,000,000₫"
```

### B. Scam Block (RED)

```text
User: "Transfer 50M to account 0391234567"
→ Orchestrator: intent=TRANSACTION, entities={amount:50M, recipient:"0391234567"}
→ TransactionAgentClient.prepare() → {to:"0391234567", amount:50000000}
→ Guardian L1: recipient IN reported_accounts → instant RED
→ SKIP Layer 2
→ Friction: BLOCKED, no bypass
→ Response: "This account has been reported by multiple users for fraud.
             Transaction blocked. Please contact hotline 1900-xxxx or visit your branch."
→ Audit.log(hard_rule="reported_recipient")
```

### C. Unusual Transfer (YELLOW)

```text
User: "Transfer 20M to Lan"
→ Orchestrator: intent=TRANSACTION, entities={amount:20M, recipient:"Lan"}
→ TransactionAgentClient.prepare() → {to:"lan_account", amount:20000000}
→ Guardian L1: no hard rule triggered
→ Guardian L2: anomaly(0.45, reason:"amount 4x user average") + scam(0.10) → score=0.38 → YELLOW
→ Friction: warn + OTP required
→ Frontend: "This amount is higher than your usual transfers. Please verify with OTP."
→ User enters OTP → verified
→ TransactionExecutor.execute() → success
→ Audit.log(auth_method="otp", auth_verified=true)
```

### D. Text2SQL Query

```text
User: "How much did I spend on food this month?"
→ Orchestrator: intent=DATA_QUERY, entities={category:"food", time:"this month"}
→ Text2SQLAgentClient.prepare() → {sql:"SELECT SUM(amount)...", explanation:"..."}
→ Guardian L1: no DML/DDL ✓
→ Guardian L2: AST valid, tables in allowlist, WHERE user_id enforced, LIMIT present ✓
→ SQLExecutor.execute() → {result: 8500000}
→ Response: "You spent 8,500,000₫ on food this month."
→ Audit.log()
```

---

## Tech Stack

| Layer | Hackathon | Production |
|-------|-----------|------------|
| Backend | FastAPI | FastAPI + async workers |
| LLM | GPT-4o-mini (fast) / GPT-4o (scam advisory) | Switchable, latency-optimized |
| Agent communication | Local mock (same process) | HTTP/gRPC to separate services |
| Session | In-memory dict | Redis |
| DB | SQLite | PostgreSQL |
| Audit | Append-only JSON file | Kafka → Elasticsearch |
| SQL Parsing | sqlglot | sqlglot |
| Frontend | Streamlit | React / bank-native SDK |
| Auth mock | OTP="123456", confirm=button | Bank IAM + biometric |
| Deployment | docker-compose | Kubernetes |
| Monitoring | Logs | Prometheus + Grafana |

---

## Production Architecture (Post-hackathon)

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT APPS                                          │
│  Mobile Banking │ Web Banking │ Internal CRM                                    │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ HTTPS + JWT
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY (Kong / Envoy)                                │
│  • Rate limiting • JWT validation • Request routing                              │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│           TRUSTFLOW ORCHESTRATOR SERVICE (this repo, evolved)                     │
│                                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────┐    │
│  │ Orchestrator        │  │ Guardian Service    │  │ Executor Service       │    │
│  │ • Intent classify  │→│ • Hard Rules (DB)  │→│ • TransactionExecutor  │    │
│  │ • Task decompose   │  │ • Anomaly (ML)     │  │ • SQLExecutor          │    │
│  │ • Multi-intent     │  │ • Scam (classifier)│  │ • Payment Gateway call │    │
│  │ • Agent routing    │  │ • Risk Scorer      │  │ • Idempotency enforced │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────────┘    │
│                                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                                 │
│  │ Session (Redis)     │  │ Audit (Kafka)      │                                 │
│  │ • History          │  │ • Immutable events │                                 │
│  │ • Cooldown timers  │  │ • Structured schema│                                 │
│  └────────────────────┘  └────────────────────┘                                 │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ gRPC / HTTP
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ TRANSACTION      │ │ TEXT2SQL          │ │ QA/RAG           │
│ AGENT SERVICE    │ │ AGENT SERVICE    │ │ AGENT SERVICE    │
│ (separate repo)  │ │ (separate repo)  │ │ (separate repo)  │
│                  │ │                  │ │                  │
│ • NL → payload  │ │ • NL → SQL       │ │ • Query → answer │
│ • Field valid.  │ │ • Schema-aware   │ │ • Vector search  │
│ • Beneficiary   │ │ • Multi-dialect  │ │ • Citation+ver.  │
│   validation    │ │                  │ │                  │
│                  │ │                  │ │                  │
│ ⚠️ NO Bank API  │ │ ⚠️ NO execution  │ │ ⚠️ Prepare only  │
│   call here     │ │   of SQL here    │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SHARED INFRASTRUCTURE                                   │
│                                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ PostgreSQL      │  │ Kafka          │  │ Elasticsearch  │  │ Prometheus   │  │
│  │ • User profiles│  │ • Audit events │  │ • Audit search │  │ + Grafana    │  │
│  │ • Rules config │  │ • Agent events │  │ • Log search   │  │ • Metrics    │  │
│  │ • Scam registry│  │ • Alerts       │  │                │  │ • Alerting   │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  └──────────────┘  │
│                                                                                   │
│  ┌────────────────┐  ┌────────────────┐                                         │
│  │ Bank IAM       │  │ Vault/KMS      │                                         │
│  │ • OTP service  │  │ • API keys     │                                         │
│  │ • Biometric    │  │ • Secrets      │                                         │
│  │ • Step-up auth │  │ • Encryption   │                                         │
│  └────────────────┘  └────────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Hackathon → Production Migration

| Component | Hackathon | Production | Migration effort |
|-----------|-----------|------------|-----------------|
| AgentClient | Mock (local) | HTTP/gRPC client | Swap implementation, keep interface |
| Guardian rules | Hardcoded JSON | PostgreSQL + hot-reload | Add DB adapter |
| Scam detection | Pattern match + LLM prompt | Fine-tuned classifier | Train model, keep interface |
| Anomaly | Simple heuristics | ML model on user history | Replace scorer impl |
| Auth | Mock OTP="123456" | Bank IAM integration | Replace auth adapter |
| Session | In-memory dict | Redis | Swap store backend |
| Audit | JSON file | Kafka → Elasticsearch | Replace logger impl |
| Executor | Mock (return success) | Real bank API + payment gateway | Real impl behind same interface |
| DB | SQLite | PostgreSQL | Migration script |
| Deployment | docker-compose | Kubernetes + Helm | New infra layer |

---

## Implementation Timeline (3-4 person team, 2-3 weeks)

### Week 1: Backend Core

| Person | Focus | Deliverable |
|--------|-------|-------------|
| **A** | Guardian | hard_rules.py, anomaly.py, scam_detector.py, risk_scorer.py, friction.py, engine.py |
| **B** | Orchestrator + Agents | orchestrator.py, base.py, transaction_client.py, intent prompt |
| **C** | Executors + Infra | transaction_executor.py, sql_executor.py, models.py, config.py, main.py |
| **D** | Data + Tests | users.json, reported_accounts.json, scam_patterns.json, seed_db.py, test scenarios |

**Week 1 checkpoint:** `POST /chat "Transfer 2M to Minh"` → GREEN. `POST /chat "Transfer to 0391234567"` → RED.

### Week 2: Text2SQL + Frontend

| Person | Focus | Deliverable |
|--------|-------|-------------|
| **A** | SQL Guardian | sql_validator.py (sqlglot AST), table_allowlist.json |
| **B** | Text2SQL agent | text2sql_client.py, sql_executor.py integration |
| **C** | Frontend core | app.py, chat.py, bank_confirm.py, otp_modal.py, scam_alert.py |
| **D** | Audit + Integration | audit logger, audit_viewer.py, E2E test all flows |

**Week 2 checkpoint:** Full UI flow works. 5 demo scenarios pass through API + UI.

### Week 3: Polish + Demo Ready

| Person | Focus | Deliverable |
|--------|-------|-------------|
| **A** | Edge cases + QA agent (bonus) | qa_client.py if time, edge case handling |
| **B** | Multi-intent (bonus) | orchestrator multi-task if time |
| **C** | UI polish + demo flow | Smooth transitions, error states, loading states |
| **D** | Docker + rehearsal | docker-compose.yml, demo data tuning, rehearsal 3x |

**Week 3 checkpoint:** `docker-compose up` → 3-5 scenarios demo perfectly in 5-8 minutes.

---

## Demo Scenarios (ordered for presentation)

| # | Scenario | Shows | Tier |
|---|----------|-------|------|
| 1 | Safe transfer: "Transfer 2M to Minh for lunch" | Normal flow + bank confirm + audit | 🟢 GREEN |
| 2 | Unusual amount: "Transfer 20M to Lan" | Anomaly detection + OTP step-up | 🟡 YELLOW |
| 3 | Scam block: "Transfer 50M to 0391234567" | Hard rule + block + explain + alternatives | 🔴 RED |
| 4 | SQL query: "How much did I spend on food?" | Text2SQL + SQL validation + NL answer | 🟢 GREEN |
| 5 | Audit trail | Show full decision trace for any above | — |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Executor separate from Agent | Yes | Agent prepares, Guardian validates, Executor acts. Clean separation of concerns |
| Agent = interface | ABC with `prepare()` | Swap mock ↔ HTTP client without changing orchestrator |
| Scam in Phase 1 | Yes (pattern match) | Risk scorer needs all inputs from Day 1. LLM advisory added later |
| Consent scopes | 2 for hackathon | `read_data` + `execute_transfer`. More in production |
| LLM calls per request | 1-2 max | Intent(1) + scam advisory only if score>threshold(conditional) |
| Transaction fields | NEVER auto-repair | If missing/ambiguous → ask user. Safety over convenience |
| Idempotency | UUID per transaction | Prevent double-execution on retry/network issues |
| Audit schema | Defined Day 1 | Prevents ad-hoc logging, enables consistent audit viewer |
