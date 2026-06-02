# TrustFlow Guardian — Architecture

> Natural-language banking assistant with adversarial safety built in.

---

## 1. Core Message

Users can query, look up, and transact using natural language. Every critical action is validated by the Guardian Layer. Domain Agents can plan and delegate to sub-agents for context resolution, but they never execute side effects and never bypass Guardian.

---

## 2. Core Principles

```text
User → Orchestrator classifies domain
→ Domain Agent plans and delegates
→ Sub-agents resolve missing context (evidence-backed)
→ Domain Agent builds action draft
→ Guardian validates
→ Friction/Auth gates execution
→ Executor performs side effect
→ Audit logs full trace
```

1. **LLM prepares, never executes.** Agents create drafts/payloads only.
2. **Agents can plan and delegate.** Domain Agents own workflow policy and call sub-agents.
3. **Sub-agents retrieve/prepare only.** They return evidence-backed outputs, never side effects.
4. **Guardian is external and final.** No agent can bypass or override Guardian.
5. **Executor is the only side-effect layer.** Runs only after Guardian + auth.
6. **Hard rules first, model second.** Deterministic safety before probabilistic scoring.
7. **Text2SQL is guarded and read-only.** SQL generation separate from SQL execution.
8. **Evidence-backed resolution.** Transaction-critical fields resolved from history must include source/confidence.
9. **Confidence-gated confirmation.** Low confidence or multiple candidates → ask user.
10. **Immutable audit trail.** Append-only, every decision explained.

---

## 3. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                              USER                                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ POST /chat
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR                                                         │
│ • Classify intent (1 LLM call → task_type + confidence)              │
│ • Route to Domain Agent by task_type                                 │
│ • Does NOT extract entities or resolve business details              │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ DOMAIN AGENT (TransactionAgent / CardAgent / DataQueryAgent / ...)   │
│ • Parse user request (LLM extract structured fields)                 │
│ • Detect missing fields                                              │
│ • Plan resolution: which sub-agents to call                          │
│ • Delegate to approved sub-agents/tools                              │
│ • Collect evidence-backed outputs                                    │
│ • Build and return action_draft (does NOT call Guardian directly)    │
└─────────────┬────────────────────────────────────────┬───────────────┘
              │ delegate                               │ return draft
              ▼                                        ▼
┌─────────────────────────────┐    ┌───────────────────────────────────┐
│ SUB-AGENTS / TOOLS          │    │ AGENT RUNTIME                     │
│ • RecipientResolutionAgent  │    │ • Receives DomainAgentOutput      │
│ • TransactionHistoryAgent   │    │ • Sends action_draft to Guardian  │
│ • BeneficiaryAgent          │    │ • Calls FrictionRouter            │
│ • CardResolverAgent         │    │ • Stores PendingAction            │
│ • PolicyRetrieverAgent      │    │ • Routes to correct Executor      │
│ • Text2SQLAgent             │    └───────────────────┬───────────────┘
│   → SQLGuardian → SQLExec   │                        │
└─────────────────────────────┘                        ▼
                               ┌───────────────────────────────────────┐
                               │ GUARDIAN                              │
                               │ • Hard rules (block immediately)      │
                               │ • Scoring (anomaly, scam, amount)     │
                               │ • Risk tier → GREEN/YELLOW/ORANGE/RED │
                               │ • Decision: ALLOW or BLOCK only       │
                               │ • Never generates missing fields      │
                               └───────────────────┬───────────────────┘
                                                   │
                                                   ▼
                               ┌───────────────────────────────────────┐
                               │ FRICTION / AUTH                       │
                               │ • GREEN  → bank confirm               │
                               │ • YELLOW → OTP                        │
                               │ • ORANGE → challenge + cooldown + OTP │
                               │ • RED    → hard block                 │
                               └───────────────────────┬───────────────┘
                                                       │ after auth
                                                       ▼
                               ┌───────────────────────────────────────────────────┐
                               │ EXECUTOR (routed by PendingAction.executor_type)  │
                               │ • TransactionExecutor / CardExecutor / etc.       │
                               │ • Perform side effect (mock/real)                 │
                               │ • Idempotency key prevents double-exec            │
                               └───────────────────────┬───────────────────────────┘
                                                       │
                                                       ▼
                               ┌───────────────────────────────────────┐
                               │ AUDIT                                 │
                               │ • Append-only trace log               │
                               │ • Agent delegation chain recorded     │
                               │ • Guardian decision + reasons         │
                               └───────────────────────────────────────┘
```

---

## 4. Agent-to-Agent Orchestration Model

Domain Agents are not passive parsers. They are **planning agents** that own a workflow policy and can delegate context resolution to sub-agents.

```text
TransactionAgent
  → parse user message → structured extraction
  → detect missing fields (recipient_account, bank, etc.)
  → plan: "I need to resolve recipient from history"
  → delegate to TransactionHistoryAgent (structured task, scoped constraints)
  → receive evidence-backed candidates
  → if confident → build draft
  → if ambiguous → ask user clarification
  → return action_draft to agent runtime
  → agent runtime sends draft to Guardian
```

Key constraints on delegation:
- Domain Agent sends **structured tasks** (not free-form prompts) to sub-agents
- Sub-agent output is **schema-constrained** (allowed_output fields defined upfront)
- Domain Agent **never auto-executes** based on sub-agent results for high-risk fields
- Evidence must include **source reference + confidence score**

```text
AgentTask {
  task_type: str                    // "resolve_recipient", "search_history"
  constraints: {                    // scoped input
    current_user_id: str
    recipient_name: str
    amount: int
    time_range: str
  }
  allowed_output: [str]             // what sub-agent may return
}

AgentTaskResult {
  candidates: [{...}]
  evidence: [str]                   // transaction_ids, source refs
  confidence: float
  source_agent: str
}
```

---

## 5. Intent and Domain Agent Routing

Orchestrator classifies **one** high-level `task_type` and routes to the correct Domain Agent.

| task_type | Domain Agent | Subtypes |
|-----------|-------------|----------|
| QA | QAAgent | policy questions, fees, rates, products, documents, guidance |
| DATA_QUERY | DataQueryAgent | balance, spending, income, history, recipients, budget |
| TRANSACTION | TransactionAgent | TRANSFER_MONEY, BILL_PAYMENT, TOP_UP |
| CARD_OPERATION | CardAgent | LOCK_CARD, UNLOCK_CARD, ACTIVATE_CARD, REISSUE_CARD, CHANGE_CARD_LIMIT, VIEW_CARD_INFO |
| ACCOUNT_OPERATION | AccountAgent | OPEN_ACCOUNT, CLOSE_ACCOUNT, UPDATE_ACCOUNT_INFO, MANAGE_BENEFICIARY, VIEW_ACCOUNT_INFO |
| LOAN_OPERATION | LoanAgent | APPLY_LOAN, CHECK_LOAN_STATUS, REPAY_LOAN, VIEW_LOAN_INFO |
| FRAUD_REPORT | FraudReportAgent | REPORT_FRAUD_ACCOUNT |

Orchestrator does **not**:
- Extract entities from the message
- Call low-level extractors like `transaction_extractor`
- Resolve business details
- Make risk decisions

---

## 6. Component Responsibilities

### Orchestrator

| Can do | Cannot do |
|--------|-----------|
| Classify intent (1 LLM call) | Extract entities |
| Route to Domain Agent | Resolve business details |
| Return Domain Agent response | Make risk decisions |
| Handle unknown intent gracefully | Call sub-agents directly |

### Domain Agents (TransactionAgent, CardAgent, AccountAgent, LoanAgent, DataQueryAgent, QAAgent)

| Can do | Cannot do |
|--------|-----------|
| Parse user request (LLM extract) | Execute transactions |
| Identify missing fields | Run SQL directly |
| Create a resolution plan | Bypass Guardian |
| Delegate to approved sub-agents | Approve their own risk |
| Collect evidence-backed outputs | Call banking/payment APIs |
| Build and return action draft | Override Guardian decision |
| | Auto-fill high-risk fields without evidence |
| | Call Guardian directly (runtime handles this) |

### Sub-agents (RecipientResolutionAgent, TransactionHistoryAgent, BeneficiaryAgent, etc.)

| Can do | Cannot do |
|--------|-----------|
| Accept structured tasks | Execute side effects |
| Query scoped data | Approve risk |
| Return candidates with evidence | Override Guardian |
| Return confidence scores | Return unscoped data |
| Explain resolution source | Silently fill high-risk fields |

### Text2SQLAgent

| Can do | Cannot do |
|--------|-----------|
| Generate SQL templates | Execute SQL |
| Generate query parameters | Perform UPDATE/DELETE/INSERT/DROP |
| Explain the query | Access data outside user scope |
| | Decide business action |
| | Directly approve transaction-critical fields |

Required flow:
```text
Calling Agent (Domain Agent or sub-agent)
→ Text2SQLAgent generates SQL template + params
  (may include :user_id placeholder; any LLM-generated user_id value is ignored)
→ SQLGuardian validates:
   • SELECT only (no DML/DDL)
   • Table in allowlist
   • user_id scope enforced (WHERE user_id = ?)
   • LIMIT present where appropriate
→ SQLExecutor executes validated query (parameterized)
  (injects actual user_id from auth context, never from LLM output)
→ Result returned to calling agent with evidence
```

### SQLGuardian

| Can do | Cannot do |
|--------|-----------|
| Validate SQL is read-only | Infer business intent |
| Enforce table allowlist | Execute SQL |
| Enforce user_id scoping | Modify query semantics |
| Reject DML/DDL | Approve transactions |
| Enforce LIMIT | |

### SQLExecutor

| Can do | Cannot do |
|--------|-----------|
| Execute validated read-only SQL | Run unvalidated SQL |
| Inject user_id from auth context | Trust user_id from LLM SQL |
| Return result rows | Perform write operations |
| | Execute without SQLGuardian approval |

### Guardian

| Can do | Cannot do |
|--------|-----------|
| Validate action drafts | Generate missing fields |
| Apply hard rules (block immediately) | Resolve business entities |
| Score risk (anomaly, scam, amount) | Execute transactions |
| Assign risk tier (GREEN/YELLOW/ORANGE/RED) | Override user auth |
| Output decision: ALLOW or BLOCK | Decide auth type (FrictionRouter does this) |
| Explain decision with reasons | |

### Friction / Auth

| Can do | Cannot do |
|--------|-----------|
| Map risk tier to auth requirement | Make risk decisions |
| Require confirm/OTP/challenge | Execute without auth |
| Enforce cooldown periods | Bypass Guardian |

### Executors

| Can do | Cannot do |
|--------|-----------|
| Execute approved action | Execute without Guardian approval |
| Enforce idempotency | Decide risk |
| Return execution result | Approve their own actions |
| | Execute blocked actions |

### Audit

| Can do | Cannot do |
|--------|-----------|
| Log full agent trace | Edit/delete logs |
| Log Guardian decisions + reasons | |
| Log delegation chain | |
| Record timestamps and user_id | |

---

## 7. Hackathon Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Streamlit)                        │
│  • Chat UI + risk badges (🟢🟡🟠🔴)                                 │
│  • Bank confirmation modal (GREEN)                                  │
│  • OTP step-up modal (YELLOW)                                       │
│  • Scam alert modal (RED)                                           │
│  • Audit trail viewer (expandable per message)                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GATEWAY (FastAPI) — THIS REPO                    │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ ORCHESTRATOR                                                  │  │
│  │ • Intent classification (1 LLM call → task_type)              │  │
│  │ • Route to Domain Agent                                       │  │
│  │ • Return Domain Agent response to frontend                    │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ DOMAIN AGENTS (plan + delegate + build draft)                 │  │
│  │                                                               │  │
│  │ • TransactionAgent:                                           │  │
│  │   → Parse message (LLM extract)                               │  │
│  │   → Detect missing fields                                     │  │
│  │   → Delegate to RecipientResolutionAgent / HistoryAgent       │  │
│  │   → Build transaction draft                                   │  │
│  │   → Return draft to agent runtime                             │  │
│  │                                                               │  │
│  │ • CardAgent:                                                  │  │
│  │   → Parse card operation                                      │  │
│  │   → Delegate to CardResolverAgent                             │  │
│  │   → Build card_action_draft                                   │  │
│  │   → Return draft to agent runtime                             │  │
│  │                                                               │  │
│  │ • DataQueryAgent:                                             │  │
│  │   → Plan read-only query                                      │  │
│  │   → Delegate to Text2SQLAgent → SQLGuardian → SQLExecutor     │  │
│  │   → Summarize result in natural language                      │  │
│  │                                                               │  │
│  │ • QAAgent:                                                    │  │
│  │   → Delegate to PolicyRetrieverAgent                          │  │
│  │   → Generate grounded answer with citation                    │  │
│  │                                                               │  │
│  │ • FraudReportAgent:                                           │  │
│  │   → Parse fraud report info (LLM extract)                     │  │
│  │   → Delegate to FraudVerificationAgent (check transactions)   │  │
│  │   → Multi-turn: ask fraud context questions                   │  │
│  │   → Calculate confidence score (rule-based)                   │  │
│  │   → Build fraud_report_draft                                  │  │
│  │   → Return draft to agent runtime                             │  │
│  │                                                               │  │
│  │ • AccountAgent / LoanAgent (same pattern)                     │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ SUB-AGENTS / TOOLS (retrieve + prepare, never execute)        │  │
│  │                                                               │  │
│  │ • RecipientResolutionAgent  → resolve saved beneficiary       │  │
│  │ • TransactionHistoryAgent   → search past txns (via Text2SQL) │  │
│  │ • BeneficiaryAgent          → manage beneficiary list         │  │
│  │ • CardResolverAgent         → resolve target card             │  │
│  │ • AccountProfileAgent       → resolve account info            │  │
│  │ • LoanInfoAgent             → lookup loan details             │  │
│  │ • PolicyRetrieverAgent      → retrieve policy docs + version  │  │
│  │ • FraudVerificationAgent    → verify user has txn with STK    │  │
│  │ • Text2SQLAgent             → generate SQL only               │  │
│  │                                                               │  │
│  │ ⚠️  Sub-agents prepare/retrieve only.                         │  │
│  │ ⚠️  They return evidence + confidence.                        │  │
│  │ ⚠️  They never execute side effects.                          │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ TEXT2SQL PIPELINE (inside sub-agent flow)                     │  │
│  │                                                               │  │
│  │ Text2SQLAgent generates SQL template                          │  │
│  │ → SQLGuardian validates:                                      │  │
│  │   • SELECT only (no DML/DDL)                                  │  │
│  │   • Table in allowlist                                        │  │
│  │   • user_id scope enforced                                    │  │
│  │   • LIMIT present where appropriate                           │  │
│  │ → SQLExecutor executes (parameterized, user_id from auth)     │  │
│  │ → Result returned to calling agent with evidence              │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ GUARDIAN                                                      │  │
│  │                                                               │  │
│  │ Layer 1: HARD RULES (deterministic, instant decision)         │  │
│  │   • Recipient in reported_accounts → RED                      │  │
│  │   • Recipient risk_level = CRITICAL → RED                     │  │
│  │   • Recipient risk_level = HIGH → ORANGE minimum              │  │
│  │   • Amount > daily_limit → BLOCK                              │  │
│  │   • Pressure/threat keywords → ORANGE minimum                 │  │
│  │   • SQL contains DML/DDL → REJECT                             │  │
│  │   • Consent scope violated → BLOCK                            │  │
│  │   → If triggered: SKIP Layer 2, go to decision                │  │
│  │                                                               │  │
│  │ Layer 2: MODEL-BASED (only if no hard rule triggered)         │  │
│  │   • Anomaly Detector (amount/recipient/urgency/time)          │  │
│  │   • Scam Pattern Matcher (rules + LLM advisory)               │  │
│  │   • Risk Scorer → tier                                        │  │
│  │                                                               │  │
│  │ Friction Router: tier → auth requirement                      │  │
│  │   GREEN(0–0.3)  → bank-native confirm                         │  │
│  │   YELLOW(0.3–0.6) → warn + OTP/PIN                            │  │
│  │   ORANGE(0.6–0.8) → challenge + cooldown + OTP                │  │
│  │   RED(0.8–1.0) → hard block, no bypass                        │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ EXECUTORS (post-guardian, separate from agents)               │  │
│  │                                                               │  │
│  │ • TransactionExecutor → call bank API (mock in hackathon)     │  │
│  │ • CardExecutor        → lock/unlock/reissue card              │  │
│  │ • SQLExecutor         → run parameterized read-only query     │  │
│  │ • AccountExecutor     → account operations                    │  │
│  │ • LoanExecutor        → loan operations                       │  │
│  │ • FraudReportExecutor → insert fraud_reports, update risk     │  │
│  │                                                               │  │
│  │ ⚠️  Executors ONLY run after Guardian approves + auth passes. │  │
│  │ ⚠️  Idempotency key prevents double-execution.                │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ AUDIT (append-only)                                           │  │
│  │ • Immutable trace per request                                 │  │
│  │ • Agent delegation chain recorded                             │  │
│  │ • Guardian decision + reasons                                 │  │
│  │ • Sub-agent calls + evidence                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ DATA (mock)                                                   │  │
│  │ • users.json (profiles + behavioral baselines)                │  │
│  │ • beneficiaries.json (saved recipients per user)              │  │
│  │ • reported_accounts.json (scam registry)                      │  │
│  │ • fraud_reports (user fraud reports with evidence)             │  │
│  │ • reported_customers (customer-level fraud risk signals)       │  │
│  │ • transactions.db (SQLite, pre-seeded)                        │  │
│  │ • policies/*.md (versioned policy docs)                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Production Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT APPS                                        │
│  Mobile Banking │ Web Banking │ Internal CRM                                    │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ HTTPS + JWT
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY (Kong / Envoy)                              │
│  • Rate limiting • JWT validation • Request routing                             │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│           TRUSTFLOW ORCHESTRATOR SERVICE                                        │
│                                                                                 │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────┐     │
│  │ Orchestrator       │  │ Guardian Service   │  │ Executor Service       │     │
│  │ • Intent classify  │  │ • Hard Rules (DB)  │  │ • TransactionExecutor  │     │
│  │ • Domain routing   │  │ • Anomaly (ML)     │  │ • CardExecutor         │     │
│  │ • Agent registry   │  │ • Scam (classifier)│  │ • Payment Gateway      │     │
│  │                    │  │ • Risk Scorer      │  │ • Idempotency enforced │     │
│  └────────────────────┘  └────────────────────┘  └────────────────────────┘     │
│                                                                                 │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────────┐     │
│  │ Session (Redis)    │  │ Audit (Kafka)      │  │ Agent Registry         │     │
│  │ • Conversation     │  │ • Immutable events │  │ • Domain Agent configs │     │
│  │ • Pending actions  │  │ • Delegation traces│  │ • Sub-agent allowlist  │     │
│  │ • Cooldown timers  │  │ • Structured schema│  │ • Policy enforcement   │     │
│  └────────────────────┘  └────────────────────┘  └────────────────────────┘     │
└──────────────────────────────┬──────────────────────────────────────────────────┘
                               │ gRPC / HTTP
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│ DOMAIN AGENT     │ │ TEXT2SQL         │ │ QA/RAG               │
│ SERVICES         │ │ AGENT SERVICE    │ │ AGENT SERVICE        │
│ (separate repos) │ │ (separate repo)  │ │ (separate repo)      │
│                  │ │                  │ │                      │
│ • Transaction    │ │ • NL → SQL       │ │ • Query → answer     │
│ • Card           │ │ • Schema-aware   │ │ • Vector search      │
│ • Account        │ │ • Multi-dialect  │ │ • Citation + version │
│ • Loan           │ │                  │ │                      │
│                  │ │ ⚠️ NO execution  │ │ ⚠️ Prepare only      │
│ ⚠️ NO side       │ │   of SQL here    │ │                      │
│   effects here   │ │                  │ │                      │
└──────────────────┘ └──────────────────┘ └──────────────────────┘
```

**Agent-to-Agent governance in production:**

```text
• Agent Registry controls which sub-agents each Domain Agent may call (policy allowlist).
• Domain Agent Services call approved Sub-agent/Tool Services only via registered endpoints.
• Sub-agent outputs are schema-constrained (AgentTaskResult) and audited.
• No Domain Agent can dynamically discover or invoke unregistered sub-agents.
• All delegation calls pass through Agent Registry for access control + audit.
```

```text
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SHARED INFRASTRUCTURE                                 │
│                                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐   │
│  │ PostgreSQL     │  │ Kafka          │  │ Elasticsearch  │  │ Prometheus   │   │
│  │ • User profiles│  │ • Audit events │  │ • Audit search │  │ + Grafana    │   │
│  │ • Rules config │  │ • Agent events │  │ • Log search   │  │ • Metrics    │   │
│  │ • Scam registry│  │ • Alerts       │  │                │  │ • Alerting   │   │
│  └────────────────┘  └────────────────┘  └────────────────┘  └──────────────┘   │
│                                                                                 │
│  ┌────────────────┐  ┌────────────────┐                                         │
│  │ Bank IAM       │  │ Vault/KMS      │                                         │
│  │ • OTP service  │  │ • API keys     │                                         │
│  │ • Biometric    │  │ • Secrets      │                                         │
│  │ • Step-up auth │  │ • Encryption   │                                         │
│  └────────────────┘  └────────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. TransactionAgent Flow

### Example: "Chuyển cho Minh 2 triệu tiền ăn như tháng trước"

```text
1. Orchestrator classifies:
   task_type = TRANSACTION
   route → TransactionAgent

2. TransactionAgent parses (LLM call):
   action = TRANSFER_MONEY
   amount = 2,000,000
   recipient_hint = "Minh"
   purpose = "tiền ăn"
   reference_time = "last_month"
   missing = [recipient_account, recipient_bank]

3. TransactionAgent loads workflow policy:
   required_fields = [amount, recipient_account, recipient_bank]
   allowed_sub_agents = [beneficiary, transaction_history]
   confirmation_required_fields = [recipient_account, recipient_bank]

4. TransactionAgent creates resolution plan:
   Plan: [
     {target: "beneficiary", task: "resolve_by_name",
      constraints: {name: "Minh", user_id: "u1"}},
     {target: "transaction_history", task: "resolve_previous_recipient",
      constraints: {recipient_name: "Minh", amount: 2000000,
                    purpose_hint: "tiền ăn", time_range: "last_month",
                    user_id: "u1"}}
   ]

5. Delegation to sub-agents:

   BeneficiaryAgent:
   → lookup saved beneficiaries for user u1 where name matches "Minh"
   → result: [{name: "Nguyễn Văn Minh", account: "0123456789", bank: "VCB"}]

   TransactionHistoryAgent:
   → needs to search past transactions
   → calls Text2SQLAgent internally:
     Text2SQLAgent generates:
       SELECT recipient_name, recipient_account, recipient_bank, amount, date, id
       FROM transactions
       WHERE user_id = :user_id
         AND recipient_name LIKE :recipient_pattern
         AND amount BETWEEN :amount_low AND :amount_high
         AND date >= :start_date
       ORDER BY date DESC LIMIT 5
     params: {recipient_pattern: "%Minh%", amount_low: 1500000,
              amount_high: 2500000, start_date: "2026-04-01"}
   → SQLGuardian validates: SELECT only ✓, table allowed ✓, user_id scoped ✓
   → SQLExecutor runs (injects user_id from auth context)
   → TransactionHistoryAgent returns:
     {candidates: [{
       recipient_name: "Nguyễn Văn Minh",
       account: "0123456789",
       bank: "VCB",
       matched_transaction_id: "txn_123",
       matched_amount: 2000000,
       matched_date: "2026-04-12",
       confidence: 0.86
     }]}

6. TransactionAgent merges evidence:
   - BeneficiaryAgent confirms same recipient
   - TransactionHistoryAgent provides evidence from past txn
   - Combined confidence: high (single candidate, both sources agree)

7. TransactionAgent builds draft:
   {
     amount: 2000000,
     recipient_name: "Nguyễn Văn Minh",
     recipient_account: "0123456789",
     recipient_bank: "VCB",
     note: "tiền ăn",
     resolution_source: "beneficiary + past_transaction",
     evidence_transaction_id: "txn_123"
   }

8. Guardian validates:
   - recipient not in reported_accounts ✓
   - amount within limit ✓
   - known recipient ✓
   - score = 0.05 → GREEN

9. FrictionRouter: bank_confirm required

10. Response to user:
    "Tôi tìm thấy người nhận khớp yêu cầu:
     Nguyễn Văn Minh - VCB - ****6789
     (dựa trên giao dịch 2,000,000đ ngày 12/04/2026)
     Bạn muốn chuyển 2,000,000đ cho người này?"

11. User confirms → POST /actions/{id}/confirm
    → TransactionExecutor.execute()
    → Audit.log(full delegation trace)
```

### Multi-candidate scenario:

```text
If TransactionHistoryAgent returns 2 candidates:
  [{name: "Nguyễn Văn Minh", account: "012...", bank: "VCB", confidence: 0.65},
   {name: "Trần Đức Minh", account: "987...", bank: "TCB", confidence: 0.55}]

TransactionAgent does NOT auto-select.
Response:
  "Tôi tìm thấy 2 người tên Minh từng nhận tiền ăn. Bạn muốn chuyển cho ai?
   1. Nguyễn Văn Minh - VCB - ****6789
   2. Trần Đức Minh - TCB - ****3210"
```

---

## 10. CardAgent Flow

### Example 1: "Khóa thẻ tín dụng của tôi"

```text
1. Orchestrator: task_type = CARD_OPERATION → CardAgent

2. CardAgent parses:
   operation = LOCK_CARD
   card_hint = "thẻ tín dụng"

3. CardAgent delegates to CardResolverAgent:
   task: "resolve_card"
   constraints: {user_id: "u1", card_type: "credit"}

4. CardResolverAgent:
   → lookup user's cards
   → if 1 credit card found: return {card_id: "card_001", last4: "5678",
     card_type: "credit", status: "active", confidence: 1.0}
   → if multiple: return candidates for clarification

5. CardAgent checks card status:
   → if already locked: return "Thẻ tín dụng ****5678 đã được khóa trước đó."
   → if active: proceed

6. CardAgent builds draft:
   {operation: "LOCK_CARD", card_id: "card_001", last4: "5678", reason: "user_request"}

7. Guardian validates:
   - LOCK_CARD is protective → low friction
   - Card ownership verified ✓
   - score = 0.0 → GREEN

8. FrictionRouter: bank_confirm (LOCK is protective, minimal friction)

9. Response: "Bạn muốn khóa thẻ tín dụng ****5678?"
   → User confirms → CardExecutor locks card
```

### Example 2: "Mở lại thẻ Visa đuôi 1234"

```text
1. Orchestrator: task_type = CARD_OPERATION → CardAgent

2. CardAgent parses:
   operation = UNLOCK_CARD
   card_hint = "Visa đuôi 1234"

3. CardResolverAgent resolves:
   → match by brand "Visa" + last4 "1234"
   → return {card_id: "card_002", last4: "1234", brand: "Visa",
     status: "locked", confidence: 1.0}

4. CardAgent builds draft:
   {operation: "UNLOCK_CARD", card_id: "card_002", last4: "1234"}

5. Guardian validates:
   - UNLOCK_CARD requires higher auth than LOCK
   - score = 0.35 → YELLOW

6. FrictionRouter: OTP required

7. Response: "Để mở khóa thẻ Visa ****1234, vui lòng nhập mã OTP."
   → User enters OTP → verified → CardExecutor unlocks card
```

### Card operation friction policy:

| Operation | Default Friction | Rationale |
|-----------|-----------------|-----------|
| LOCK_CARD | GREEN (confirm) | Protective action, low risk |
| UNLOCK_CARD | YELLOW (OTP) | Enables spending, moderate risk |
| ACTIVATE_CARD | YELLOW (OTP) | New card activation |
| REISSUE_CARD | YELLOW (OTP) | Address verification if applicable |
| CHANGE_CARD_LIMIT | ORANGE (challenge + OTP) | High impact on spending |
| VIEW_CARD_INFO | GREEN (session-authenticated, masked output only) | Read-only |

---

## 10b. FraudReportAgent Flow

### Example: "Tôi muốn báo cáo số tài khoản 123456789 tại ngân hàng VCB lừa đảo tôi"

```text
1. Orchestrator classifies:
   task_type = FRAUD_REPORT
   route → FraudReportAgent

2. FraudReportAgent parses (LLM extract):
   operation = REPORT_FRAUD_ACCOUNT
   reported_account_no = "123456789"
   reported_bank_code = "VCB"
   reason_hint = "lừa đảo"

3. FraudReportAgent delegates to FraudVerificationAgent:
   task: "verify_transaction_relationship"
   constraints: {
     user_id: "u1",
     counterparty_account_no: "123456789",
     counterparty_bank_code: "VCB"
   }

4. FraudVerificationAgent:
   → Query transactions WHERE cif_no = :user_cif
     AND counterparty_account_no = :reported_account
     AND counterparty_bank_code = :reported_bank
     AND direction = 'OUT'
     AND status = 'SUCCESS'
   → If 0 results: return {status: "no_relationship"}
   → If results found: return {status: "verified", transactions: [...]}

5. If no_relationship:
   FraudReportAgent returns:
   "Không tìm thấy giao dịch nào giữa bạn và tài khoản 123456789 (VCB).
    Chưa thể tạo báo cáo gian lận chính thức."
   → End flow.

6. If verified (has transactions):
   FraudReportAgent shows matching transactions:
   "Tôi tìm thấy 2 giao dịch đến tài khoản này:
    1. 15,000,000đ ngày 20/05/2026 - 'Đặt cọc mua hàng'
    2. 5,000,000đ ngày 22/05/2026 - 'Chuyển thêm phí ship'
    Bạn muốn report giao dịch nào? (1, 2, hoặc cả hai)"

7. User selects → FraudReportAgent asks fraud context (multi-turn):

   Q1: "Bạn chuyển tiền vì lý do gì?"
       Options: Mua hàng / Đặt cọc / Đầu tư / Vay tiền / Người quen giả danh / Khác
   → User: "Mua hàng"

   Q2: "Bạn bị liên hệ qua kênh nào?"
       Options: Facebook / Zalo / Telegram / Website / Điện thoại / Khác
   → User: "Facebook"

   Q3: "Sau khi chuyển tiền, chuyện gì xảy ra?"
       Options: Bị chặn liên lạc / Không nhận được hàng / Bị yêu cầu thêm tiền / Link biến mất / Khác
   → User: "Bị chặn liên lạc"

   Q4: "Bạn có bằng chứng không?"
       Options: Có ảnh tin nhắn / Có số điện thoại-link / Không có
   → User: "Có ảnh tin nhắn"

8. FraudReportAgent calculates confidence_score:
   +40: has verified transaction
   +20: transaction within 30 days
   +15: fraud_type clear (SHOPPING_SCAM)
   +15: aftermath clear (BLOCKED_CONTACT)
   +10: has evidence
   = 100 → CRITICAL confidence

9. FraudReportAgent builds fraud_report_draft:
   {
     operation: "REPORT_FRAUD_ACCOUNT",
     reported_account_no: "123456789",
     reported_bank_code: "VCB",
     transaction_ref: "TXN202605150001",
     fraud_type: "SHOPPING_SCAM",
     contact_channel: "FACEBOOK",
     aftermath: "BLOCKED_CONTACT",
     has_evidence: true,
     confidence_score: 100,
     reason_text: "Mua hàng qua Facebook, chuyển 15tr đặt cọc, bị chặn liên lạc"
   }

10. Guardian validates:
    - FRAUD_REPORT is a protective action
    - confidence_score >= 40 (has real transaction evidence)
    - score = 0.0 → GREEN

11. FrictionRouter: bank_confirm (protective action, minimal friction)

12. User confirms → FraudReportExecutor:
    a. INSERT fraud_reports (status = VALIDATED)
    b. UPSERT reported_accounts:
       - Increment valid_report_count, unique_reporter_count
       - Add to total_reported_amount
       - Recalculate risk_score and risk_level
    c. IF same-bank (reported_bank = our bank):
       - Lookup customer by account → get cif_no
       - UPSERT reported_customers
    d. INSERT fraud_decisions log

13. Response:
    "Báo cáo gian lận đã được ghi nhận. Tài khoản 123456789 (VCB) đã được
     đánh dấu để bảo vệ người dùng khác. Cảm ơn bạn đã báo cáo."

14. Audit.log(full fraud report trace)
```

### Transaction Screening (integrated with Guardian):

When any TRANSFER action is evaluated by Guardian:

```text
Guardian.evaluate(draft):
  1. Check reported_accounts:
     SELECT risk_level, valid_report_count, status
     FROM reported_accounts
     WHERE account_no = draft.recipient_account
       AND bank_code = draft.recipient_bank
       AND status = 'ACTIVE'

  2. If found:
     - risk_level = LOW (1-2 reports) → WARN (+0.3 to risk_score)
     - risk_level = MEDIUM (3-4 reports) → STEP_UP_AUTH (+0.5)
     - risk_level = HIGH (5+ reports) → ORANGE minimum (+0.7)
     - risk_level = CRITICAL (confirmed) → RED (hard block)

  3. Check reported_customers (if same-bank):
     SELECT risk_level FROM reported_customers
     WHERE cif_no = (SELECT cif_no FROM accounts WHERE account_no = draft.recipient_account)

  4. Log fraud_decisions:
     INSERT INTO fraud_decisions (decision, risk_level, reason_codes, ...)

  5. If WARN decision:
     Message: "⚠️ Cảnh báo: Tài khoản này từng bị báo cáo lừa đảo bởi
              người dùng khác. Bạn có chắc chắn muốn tiếp tục?"
```

### Fraud risk_level calculation rules (hackathon):

```text
reported_accounts.risk_level:
  1 valid report                    → LOW
  2 valid reports                   → MEDIUM
  3-4 valid reports from 3+ users   → HIGH
  5+ valid reports OR confirmed     → CRITICAL

reported_customers.risk_level:
  1 reported account                → WATCH
  2+ reported accounts              → FROZEN (auto-freeze)
  Confirmed fraud on any account    → BLOCKED
```

---

## 11. AccountAgent Flow

### Example: "Thêm người nhận mới tên Hà, số tài khoản 111222333, ngân hàng VPBank"

```text
1. Orchestrator: task_type = ACCOUNT_OPERATION → AccountAgent

2. AccountAgent parses:
   operation = MANAGE_BENEFICIARY
   sub_operation = ADD
   beneficiary_name = "Hà"
   beneficiary_account = "111222333"
   beneficiary_bank = "VPBank"

3. AccountAgent validates completeness:
   - All required fields present ✓

4. AccountAgent builds draft:
   {operation: "ADD_BENEFICIARY", name: "Hà",
    account: "111222333", bank: "VPBank"}

5. Guardian validates:
   - Account not in reported list ✓
   - score = 0.1 → GREEN

6. FrictionRouter: OTP (adding beneficiary requires OTP)

7. Response + OTP → AccountExecutor saves beneficiary
```

### Account operation friction policy:

| Operation | Default Friction |
|-----------|-----------------|
| VIEW_ACCOUNT_INFO | GREEN (no auth) |
| MANAGE_BENEFICIARY (add) | YELLOW (OTP) |
| MANAGE_BENEFICIARY (remove) | GREEN (confirm) |
| UPDATE_ACCOUNT_INFO | YELLOW (OTP) |
| OPEN_ACCOUNT | ORANGE (full verification) |
| CLOSE_ACCOUNT | RED (requires branch / special flow) |

---

## 12. LoanAgent Flow

### Example: "Kiểm tra trạng thái khoản vay của tôi"

```text
1. Orchestrator: task_type = LOAN_OPERATION → LoanAgent

2. LoanAgent parses:
   operation = CHECK_LOAN_STATUS

3. LoanAgent delegates to LoanInfoAgent:
   task: "get_active_loans"
   constraints: {user_id: "u1"}

4. LoanInfoAgent returns:
   [{loan_id: "loan_001", type: "personal", principal: 50000000,
     remaining: 35000000, monthly_payment: 5200000, next_due: "2026-06-01",
     status: "active"}]

5. LoanAgent builds response (read-only, no draft needed):
   "Khoản vay cá nhân của bạn:
    - Gốc: 50,000,000đ
    - Còn lại: 35,000,000đ
    - Trả hàng tháng: 5,200,000đ
    - Kỳ tiếp theo: 01/06/2026"

6. No action Guardian/Friction needed because this is read-only.
   However, ownership/scope validation is still required before returning loan data.
```

### Example: "Trả trước 10 triệu khoản vay"

```text
1. LoanAgent parses: operation = REPAY_LOAN, amount = 10,000,000

2. LoanInfoAgent resolves active loan

3. LoanAgent builds draft:
   {operation: "REPAY_LOAN", loan_id: "loan_001", amount: 10000000,
    type: "early_repayment"}

4. Guardian validates → YELLOW (financial impact)

5. OTP → LoanExecutor processes early repayment
```

### Loan operation friction policy:

| Operation | Default Friction |
|-----------|-----------------|
| VIEW_LOAN_INFO | GREEN (no auth) |
| CHECK_LOAN_STATUS | GREEN (no auth) |
| REPAY_LOAN | YELLOW (OTP) |
| APPLY_LOAN | ORANGE (full verification + documents) |

---

## 13. DataQueryAgent Flow

### Example: "Tháng này tôi tiêu bao nhiêu cho ăn uống?"

```text
1. Orchestrator: task_type = DATA_QUERY → DataQueryAgent

2. DataQueryAgent plans query:
   query_type = "spending_summary"
   filters: {category: "food", time_range: "this_month"}

3. DataQueryAgent delegates to Text2SQLAgent:
   task: "generate_query"
   constraints: {
     intent: "sum spending by category",
     category: "food/dining",
     time_range: "2026-05-01 to 2026-05-19",
     user_id: "u1"  // for scoping only, not in SQL params
   }

4. Text2SQLAgent generates:
   sql_template: "SELECT SUM(amount) as total, COUNT(*) as count
                  FROM transactions
                  WHERE user_id = :user_id
                    AND category IN (:categories)
                    AND date >= :start_date AND date <= :end_date
                    AND transaction_type = 'debit'
                  LIMIT 1"
   params: {categories: ["food", "dining"], start_date: "2026-05-01",
            end_date: "2026-05-19"}

5. SQLGuardian validates:
   - SELECT only ✓
   - Table "transactions" in allowlist ✓
   - user_id scope present ✓
   - LIMIT present ✓
   - No subqueries to unauthorized tables ✓

6. SQLExecutor executes (injects user_id from auth context):
   NOTE: Text2SQL may generate a :user_id placeholder, but SQLExecutor
   always injects actual user_id from auth context. Any user_id value
   in LLM-generated params is ignored.
   result: {total: 8500000, count: 23}

7. DataQueryAgent summarizes:
   "Tháng này bạn đã chi 8,500,000đ cho ăn uống (23 giao dịch)."

8. No action Guardian/Friction needed (read-only, no side effect).
   However, SQLGuardian validation is MANDATORY for all generated SQL.

9. Audit.log(query executed, no sensitive data in log)
```

### DATA_QUERY is the primary use case for Text2SQL.

Other DATA_QUERY examples:
- "Tháng trước thu nhập bao nhiêu?" → SUM income transactions
- "Ai gửi tiền cho tôi tuần này?" → LIST incoming transfers
- "Chi tiêu thẻ Visa tháng 4?" → SUM card transactions by card
- "So sánh chi tiêu tháng này với tháng trước?" → comparative query

---

## 14. QAAgent Flow

### Example: "Lãi suất tiết kiệm 6 tháng là bao nhiêu?"

```text
1. Orchestrator: task_type = QA → QAAgent

2. QAAgent delegates to PolicyRetrieverAgent:
   task: "retrieve_policy"
   constraints: {
     topic: "savings_interest_rate",
     term: "6_months",
     product_type: "savings"
   }

3. PolicyRetrieverAgent:
   → Search policy documents (vector search or keyword match)
   → Return:
     {chunks: ["Lãi suất tiết kiệm kỳ hạn 6 tháng: 5.5%/năm (áp dụng từ 01/05/2026)"],
      policy_version: "v2026.05",
      effective_date: "2026-05-01",
      source: "policies/savings_rates.md",
      confidence: 0.95}

4. QAAgent generates grounded answer:
   "Lãi suất tiết kiệm kỳ hạn 6 tháng hiện tại là 5.5%/năm.
    (Theo biểu lãi suất v2026.05, áp dụng từ 01/05/2026)"

5. Citation/Grounding validation (MANDATORY for QA):
   - Answer matches retrieved chunk ✓
   - Version/date included ✓
   - No hallucinated rates ✓

6. No action Guardian/Friction needed (informational, no side effect).
   However, citation/grounding validation is MANDATORY for all QA answers.
```

### QAAgent constraints:
- Must cite source policy document and version
- Must not hallucinate rates, fees, or product details
- If no matching policy found → say "Tôi không tìm thấy thông tin này" (don't guess)
- Production: vector DB + semantic search over versioned policy docs

---

## 15. Safety Boundaries

```text
┌──────────────────────────────────────────────────────────────────┐
│ SAFETY BOUNDARY ENFORCEMENT                                      │
│                                                                  │
│ 1. LLM prepares, never executes.                                 │
│    → All LLM outputs are drafts/templates. No side effects.      │
│                                                                  │
│ 2. Domain Agents can plan and delegate, cannot execute.          │
│    → TransactionAgent builds draft, never calls bank API.        │
│                                                                  │
│ 3. Sub-agents retrieve/prepare only.                             │
│    → TransactionHistoryAgent returns candidates, not decisions.  │
│                                                                  │
│ 4. Guardian is external and has final authority.                 │
│    → No agent can bypass. Guardian output is immutable.          │
│                                                                  │
│ 5. Executor is the ONLY side-effect layer.                       │
│    → Runs after Guardian approval + user auth.                   │
│                                                                  │
│ 6. Text2SQL is guarded and read-only.                            │
│    → SQLGuardian validates every generated query.                │
│    → No DML/DDL. No unscoped queries. No execution without       │
│      validation.                                                 │
│                                                                  │
│ 7. Transaction-critical fields must be evidence-backed.          │
│    → recipient_account resolved from history/beneficiary         │
│      must include source_transaction_id + confidence.            │
│                                                                  │
│ 8. Low confidence → ask user.                                    │
│    → If confidence < threshold or multiple candidates,           │
│      Domain Agent MUST ask for clarification.                    │
│                                                                  │
│ 9. High-risk actions require step-up auth.                       │
│    → GREEN=confirm, YELLOW=OTP, ORANGE=challenge+OTP,            │
│      RED=blocked (no bypass).                                    │
│                                                                  │
│ 10. Audit logs the full agent trace.                             │
│     → Every delegation, every sub-agent call, every Guardian     │
│       decision is recorded. Append-only, no delete.              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 16. API Endpoints

```text
POST /chat                              # Main conversation endpoint
     Request:  ChatRequest {user_id, message, session_id}
     Response: ChatResponse {status, response, risk_tier, pending_action_id,
               requires_auth, action_preview, audit_id}

POST /actions/{action_id}/confirm       # Bank-native confirm (GREEN tier)
     Request:  ConfirmRequest {user_id}
     Response: ActionResponse {status: "executed", message, transaction_id}
     Routing:  PendingAction.executor_type determines which Executor to call

POST /actions/{action_id}/otp           # OTP verification (YELLOW/ORANGE tier)
     Request:  OTPRequest {user_id, otp_code}
     Response: ActionResponse {status: "executed", message, transaction_id}
     Routing:  PendingAction.executor_type determines which Executor to call

GET  /health                            # Health check
     Response: {status: "ok"}
```

Error responses:
- 404: action_id not found
- 401: user_id mismatch
- 403: action blocked / auth type mismatch
- 409: action already executed (idempotency)

---

## 17. Data Flow per Request

```text
1. User sends message → POST /chat
2. Orchestrator classifies intent (1 LLM call → task_type only)
3. Orchestrator routes to Domain Agent by task_type
4. Domain Agent executes:
   4a. Parse user message (LLM extract structured fields)
   4b. Detect missing fields
   4c. Plan resolution: which sub-agents to call
   4d. Delegate to sub-agents (structured tasks):
       ↳ Sub-agent may call Text2SQL → SQLGuardian → SQLExecutor internally
       ↳ Sub-agent returns candidates + evidence + confidence
   4e. If low confidence / multiple candidates → return {status: clarification_needed}
   4f. If confident → build action draft → return to agent runtime
   4g. Agent runtime sends draft to Guardian:
       ↳ Layer 1: hard rules (instant block if triggered)
       ↳ Layer 2: scoring (if no hard rule)
       ↳ If BLOCK → return {status: blocked} immediately
   4h. Agent runtime calls FrictionRouter: risk tier → auth requirement
   4i. PendingActionStore saves action:
       ↳ Return {status: pending_auth, pending_action_id, preview}
5. User confirms/OTP → POST /actions/{id}/confirm or /otp
6. Executor runs after auth verified
7. Audit.log(full agent delegation trace)
8. Response compiled → Frontend
```

---

## 18. Folder Structure

```text
trustflow-banking-agent/
├── .env.example
├── requirements.txt
├── README.md
├── docs/
│   ├── ARCHITECTURE_EN.md
│   ├── ARCHITECTURE_VI.md
│   ├── README_VI.md
│   └── plan.md
│
├── backend/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, endpoints
│   ├── config.py                        # Env vars
│   ├── models.py                        # Pydantic schemas (all models)
│   │
│   ├── agents/                          # Domain Agents + Sub-agents
│   │   ├── __init__.py
│   │   ├── base.py                      # SubAgent ABC, AgentTask, AgentTaskResult
│   │   ├── orchestrator.py              # Thin: classify intent → route to domain agent
│   │   ├── transaction.py              # TransactionAgent (plan + delegate + draft)
│   │   ├── card.py                     # CardAgent
│   │   ├── account.py                  # AccountAgent
│   │   ├── loan.py                     # LoanAgent
│   │   ├── data_query.py              # DataQueryAgent
│   │   ├── qa.py                       # QAAgent
│   │   ├── fraud_report.py            # FraudReportAgent (multi-turn fraud reporting)
│   │   │
│   │   └── sub_agents/                 # Sub-agents (retrieve/prepare only)
│   │       ├── __init__.py
│   │       ├── recipient_resolution.py # RecipientResolutionAgent
│   │       ├── transaction_history.py  # TransactionHistoryAgent
│   │       ├── beneficiary.py          # BeneficiaryAgent
│   │       ├── card_resolver.py        # CardResolverAgent
│   │       ├── account_profile.py      # AccountProfileAgent
│   │       ├── loan_info.py            # LoanInfoAgent
│   │       ├── policy_retriever.py     # PolicyRetrieverAgent
│   │       ├── fraud_verification.py   # FraudVerificationAgent (verify txn relationship)
│   │       └── text2sql.py             # Text2SQLAgent (generate SQL only)
│   │
│   ├── services/                        # Infrastructure services
│   │   ├── __init__.py
│   │   ├── guardian.py                 # Guardian: hard rules + scoring → decision
│   │   ├── sql_guardian.py             # SQLGuardian: validate SQL queries
│   │   ├── friction.py                 # FrictionRouter: tier → auth requirement
│   │   ├── session.py                  # SessionStore: pending actions
│   │   └── audit.py                    # AuditLogger: append-only trace
│   │
│   ├── executors/                       # Side-effect layer (post-Guardian only)
│   │   ├── __init__.py
│   │   ├── transaction.py             # TransactionExecutor
│   │   ├── card.py                    # CardExecutor
│   │   ├── account.py                 # AccountExecutor
│   │   ├── loan.py                    # LoanExecutor
│   │   ├── fraud_report.py            # FraudReportExecutor (insert report + update risk)
│   │   └── sql.py                     # SQLExecutor (read-only query execution)
│   │
│   ├── policies/                        # Workflow policies (what agents can do)
│   │   ├── __init__.py
│   │   ├── transfer.py                # TransferWorkflowPolicy
│   │   ├── card.py                    # CardWorkflowPolicy
│   │   └── base.py                    # BaseWorkflowPolicy
│   │
│   ├── prompts/                         # LLM prompt templates
│   │   ├── __init__.py
│   │   ├── intent.py                  # Intent classification
│   │   ├── transaction.py             # Transaction entity extraction
│   │   ├── card.py                    # Card operation extraction
│   │   └── data_query.py             # Data query understanding
│   │
│   └── data/                            # Mock data (hackathon)
│       ├── reported_accounts.json      # Scam registry
│       ├── beneficiaries.json          # Saved recipients per user
│       ├── users.json                  # User profiles + baselines
│       ├── cards.json                  # User cards
│       ├── loans.json                  # User loans
│       └── policies/                   # Policy documents for QA
│           ├── savings_rates.md
│           ├── transfer_limits.md
│           └── fees.md
│
├── frontend/                            # Streamlit demo UI
│   ├── app.py
│   ├── components/
│   │   ├── chat.py
│   │   ├── bank_confirm.py
│   │   ├── otp_modal.py
│   │   └── audit_viewer.py
│   └── static/
│
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_orchestrator.py
    ├── test_transaction_agent.py
    ├── test_card_agent.py
    ├── test_data_query_agent.py
    ├── test_guardian.py
    ├── test_sql_guardian.py
    └── test_api.py
```

### Hackathon Minimal Implementation

Files required for MUST HAVE scope:

```text
backend/
├── main.py
├── config.py
├── models.py
├── agents/
│   ├── base.py                      # AgentTask, AgentTaskResult, DomainAgentOutput
│   ├── orchestrator.py              # classify + route
│   ├── transaction.py              # TransactionAgent
│   └── sub_agents/
│       └── beneficiary.py          # BeneficiaryAgent
├── services/
│   ├── guardian.py                 # hard rules + scoring
│   ├── friction.py                 # risk_tier → auth_type
│   ├── session.py                  # pending actions
│   └── agent_runtime.py            # draft → Guardian → Friction → store
├── executors/
│   └── transaction.py             # TransactionExecutor (mock)
├── prompts/
│   ├── intent.py
│   └── transaction.py
└── data/
    ├── reported_accounts.json
    └── beneficiaries.json
```

Extension files (SHOULD HAVE):

```text
agents/card.py
agents/data_query.py
agents/sub_agents/transaction_history.py
agents/sub_agents/card_resolver.py
agents/sub_agents/text2sql.py
services/sql_guardian.py
executors/card.py
executors/sql.py
```

Bonus files:

```text
agents/qa.py
agents/account.py
agents/loan.py
agents/sub_agents/policy_retriever.py
agents/sub_agents/loan_info.py
executors/account.py
executors/loan.py
policies/
```

---

## 19. Pydantic Models

```python
# === Core Request/Response ===

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: str

class ChatResponse(BaseModel):
    status: str                        # completed | pending_auth | blocked | clarification_needed
    response: str                      # Natural language to user
    risk_tier: Optional[str] = None    # GREEN | YELLOW | ORANGE | RED
    requires_auth: Optional[str] = None  # bank_confirm | otp | challenge | blocked
    pending_action_id: Optional[str] = None
    action_preview: Optional[dict] = None  # generic preview for any domain (transaction/card/loan/...)
    audit_id: Optional[str] = None

class ActionResponse(BaseModel):
    status: Literal["executed"]
    message: str
    execution_id: Optional[str] = None  # generic ID for any executed action (txn/card/account/loan)

# === Intent ===

class IntentResult(BaseModel):
    task_type: Literal[
        "QA", "DATA_QUERY", "TRANSACTION",
        "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION"
    ]
    operation: Optional[str] = None   # TRANSFER_MONEY, LOCK_CARD, etc.
    risk_hint: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    route: Optional[str] = None       # domain agent route hint
    confidence: float
    reason: str

# === Agent-to-Agent Communication ===

class AgentTask(BaseModel):
    task_type: str             # "resolve_recipient", "search_history", "resolve_card"
    constraints: dict          # scoped input for sub-agent
    allowed_output: list[str]  # schema constraint on response

class AgentTaskResult(BaseModel):
    candidates: list[dict]     # matched results
    evidence: list[str]        # transaction_ids, source references
    confidence: float          # 0.0 – 1.0
    source_agent: str          # which sub-agent produced this

# === Domain Agent Output ===

class DomainAgentOutput(BaseModel):
    status: str                # draft_ready | clarification_needed | info_response
    action_draft: Optional[dict] = None
    clarification_message: Optional[str] = None
    info_response: Optional[str] = None
    delegation_trace: list[dict] = Field(default_factory=list)  # [{agent, task, result_summary}]

# === Guardian ===

class GuardianDecision(BaseModel):
    decision: Literal["ALLOW", "BLOCK"]   # Guardian only decides allow/block
    risk_tier: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    risk_score: float          # 0.0 – 1.0
    triggered_by: Literal["HARD_RULE", "MODEL"]
    reasons: list[str]
    hard_rule_name: Optional[str] = None
    # NOTE: Guardian does NOT decide auth type.
    # FrictionRouter maps risk_tier → auth_type separately.

# === Friction ===

class FrictionResult(BaseModel):
    auth_type: str             # bank_confirm | otp | challenge | blocked
    message: str               # explanation to user

# === Pending Action ===

class PendingAction(BaseModel):
    action_id: str
    user_id: str
    session_id: str
    action_type: str           # TRANSACTION | CARD_OPERATION | ACCOUNT_OPERATION | LOAN_OPERATION
    operation: Optional[str] = None  # TRANSFER_MONEY, LOCK_CARD, etc.
    executor_type: str         # transaction | card | account | loan
    draft: dict
    risk_tier: str
    auth_required: str
    created_at: str
    executed: bool = False

# === Audit ===

class AuditEntry(BaseModel):
    request_id: str
    session_id: str
    user_id: str
    timestamp: str
    input_message: str
    intent: IntentResult
    domain_agent: str
    delegation_trace: list[dict]
    action_draft: Optional[dict]
    guardian_decision: Optional[GuardianDecision]
    friction_result: Optional[FrictionResult]
    auth_method: Optional[str]
    auth_verified: bool = False
    executor_result: Optional[dict]
    final_status: str          # executed | blocked | clarification_needed | completed
```

---

## 20. Guardian Decision Matrix

| Scenario | Layer 1 (Hard Rules) | Layer 2 (Scoring) | Risk Tier | Auth |
|----------|---------------------|-------------------|-----------|------|
| Known recipient, low amount | — | score < 0.3 | GREEN | confirm |
| Unknown recipient, medium amount | — | 0.3 ≤ score < 0.6 | YELLOW | OTP |
| Pressure keywords detected | ORANGE minimum | score 0.6–0.8 | ORANGE | challenge + OTP |
| Reported account | instant RED | skip | RED | blocked |
| Amount > 500M | instant RED | skip | RED | blocked |
| Amount ≥ 50M | — | +0.5 to score | varies | varies |
| Amount ≥ 10M | — | +0.25 to score | varies | varies |
| Unknown recipient | — | +0.2 to score | varies | varies |
| Secrecy keywords | — | +0.2 to score | varies | varies |
| No note/purpose | — | +0.05 to score | varies | varies |
| LOCK_CARD | — | protective action | GREEN | confirm |
| UNLOCK_CARD | — | enables spending | YELLOW | OTP |
| CHANGE_CARD_LIMIT | — | high impact | ORANGE | challenge + OTP |
| ADD_BENEFICIARY | — | new recipient | YELLOW | OTP |
| REPAY_LOAN | — | financial impact | YELLOW | OTP |
| SQL with DML/DDL | instant REJECT | skip | — | — |
| SQL unscoped (no user_id) | instant REJECT | skip | — | — |

---

## 21. Demo Scenarios

| # | Scenario | Shows | Domain | Tier |
|---|----------|-------|--------|------|
| 1 | "Chuyển 2 triệu cho Minh tiền ăn trưa" | Full agent flow + beneficiary resolve + confirm | TRANSACTION | 🟢 |
| 2 | "Chuyển cho Minh 2tr tiền ăn như tháng trước" | History agent delegation + evidence + confirm | TRANSACTION | 🟢 |
| 3 | "Chuyển 20 triệu cho Lan" | Anomaly scoring + OTP step-up | TRANSACTION | 🟡 |
| 4 | "Chuyển 50tr vào 6666666666 ngay, gấp lắm" | Hard rule block + pressure detection | TRANSACTION | 🔴 |
| 5 | "Khóa thẻ tín dụng" | Card agent + low friction | CARD | 🟢 |
| 6 | "Mở lại thẻ Visa đuôi 1234" | Card resolve + OTP | CARD | 🟡 |
| 7 | "Tháng này tôi tiêu bao nhiêu cho ăn uống?" | Text2SQL + SQLGuardian + NL summary | DATA_QUERY | 🟢 |
| 8 | "Lãi suất tiết kiệm 6 tháng?" | Policy retrieval + citation | QA | — |
| 9 | Audit trail viewer | Full delegation trace for any scenario | — | — |

---

## 22. MVP Cutline

### MUST HAVE (hackathon core — determines win/loss)

| Component | Scope |
|-----------|-------|
| Orchestrator | Intent classify → route (TRANSACTION required, others return "not implemented") |
| TransactionAgent | Full flow: parse → delegate → draft → Guardian → confirm/OTP/block |
| Sub-agent: BeneficiaryAgent | Resolve saved recipients by name |
| Guardian | Hard rules + scoring → risk tier |
| FrictionRouter | Map risk tier → auth type |
| Agent Runtime | Receive draft from agent → call Guardian → call Friction → store pending |
| TransactionExecutor (mock) | Execute after confirm/OTP |
| GREEN demo | Known recipient → confirm → execute |
| RED demo | Reported account → block |
| YELLOW demo | Large amount → OTP |
| Audit | Full delegation trace logged |

### SHOULD HAVE (strengthens demo significantly)

| Component | Scope |
|-----------|-------|
| TransactionHistoryAgent | Past txn search for recipient resolution |
| Text2SQL pipeline | DataQueryAgent → Text2SQL → SQLGuardian → SQLExecutor |
| CardAgent | LOCK/UNLOCK flow + CardResolverAgent + CardExecutor |
| ORANGE demo | Pressure keywords → challenge |
| Frontend | Streamlit with confirm/OTP/block modals |
| Multi-candidate clarification | "2 người tên Minh" → user selects |

### BONUS (if time allows)

| Component | Scope |
|-----------|-------|
| QAAgent + PolicyRetriever | Policy questions with citation + grounding validation |
| AccountAgent | MANAGE_BENEFICIARY, VIEW_ACCOUNT_INFO |
| LoanAgent | CHECK_LOAN_STATUS, REPAY_LOAN |
| Agent delegation trace viewer | Visual sub-agent call chain in UI |

---

## 23. Hackathon to Production Migration

| Component | Hackathon | Production | Migration |
|-----------|-----------|------------|-----------|
| Domain Agents | Local classes, same process | Separate services (gRPC/HTTP) | Extract to service, keep interface |
| Sub-agents | Local classes | Internal microservices or tools | Same extraction pattern |
| Agent Registry | Hardcoded dict | Database + config service | Add DB adapter |
| Workflow Policy | Python dataclass | Policy-as-code + hot reload | Add policy engine |
| Guardian | Rule-based + simple scoring | ML anomaly model + fraud classifier | Train models, keep interface |
| Text2SQL | Single LLM call | Fine-tuned model + schema cache | Swap model, keep pipeline |
| SQLGuardian | Regex + simple AST | sqlglot full AST + query plan analysis | Upgrade validation |
| Auth | Mock OTP="123456" | Bank IAM + biometric + device binding | Replace auth adapter |
| Session | In-memory dict | Redis cluster | Swap store |
| Audit | JSON file | Kafka → Elasticsearch | Replace logger |
| Executor | Mock (return success) | Real bank API + payment gateway | Real impl |
| Data | JSON files + SQLite | PostgreSQL + read replicas | Migration scripts |
| Frontend | Streamlit | React + bank-native SDK | Full rewrite |
| Deployment | docker-compose | Kubernetes + Helm | New infra layer |
| Monitoring | Print logs | Prometheus + Grafana + PagerDuty | Add instrumentation |
| Agent tracing | In-memory trace list | OpenTelemetry + Jaeger | Add spans |

---

## 24. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent-to-agent over static workflow | Domain Agents plan + delegate | Flexible for edge cases, extensible with new sub-agents |
| Orchestrator is thin | Classify + route only | Domain logic stays in domain agents, not orchestrator |
| Sub-agents use structured tasks | AgentTask schema, not free-form prompts | Reduces ambiguity, constrains output, improves safety |
| Text2SQL is sub-agent, not top-level | Inside TransactionHistoryAgent / DataQueryAgent | Business semantics handled by domain agent, not SQL agent |
| Evidence-backed resolution | Sub-agents return source + confidence | Enables confidence-gated confirmation |
| Policy objects control agents | TransferWorkflowPolicy defines allowed actions | Agents are governed, not autonomous |
| Guardian is external to agents | Agents cannot approve themselves | Clear safety boundary |
| Confirmation required for resolved fields | recipient_account from history → must confirm | Safety over convenience for transaction-critical data |
| All money-moving actions require explicit user approval | GREEN requires bank confirm; higher tiers require OTP/challenge | No silent money movement |
| Executor separate from everything | Only layer with side effects | Clear audit boundary |
| Audit includes delegation trace | Every sub-agent call recorded | Full explainability |
| LLM calls bounded | Intent(1) + parse(1) + sub-agent LLM if needed | Latency predictable |
| Transaction fields NEVER auto-repaired | Missing → clarification | Safety |
| Protective actions (LOCK) get low friction | User doing LOCK is self-protecting | Don't add friction to safety actions |
| UNLOCK/ACTIVATE get higher friction | Enables spending/access | Higher risk than locking |
