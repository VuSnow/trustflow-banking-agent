# TrustFlow Guardian

> Natural-language banking assistant with adversarial safety built in.

**Core Message:** Users can query, look up, open accounts, and transact using natural language — but every critical action is validated by the Guardian Layer to prevent bad queries, risky transactions, and scams.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        USER INPUT (Natural Language)                          │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  0. USER AUTH + SESSION CONTEXT                                              │
│                                                                              │
│  • Authenticated user_id (pre-verified session)                             │
│  • Account access scope (which accounts user can operate on)                │
│  • Consent scope (granular):                                                │
│      - read_account_data                                                    │
│      - analyze_spending                                                     │
│      - prepare_transfer                                                     │
│      - execute_transfer                                                     │
│      - submit_onboarding_application                                        │
│  • Session history (previous messages in conversation)                      │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. INTENT & TASK DECOMPOSITION                                              │
│                                                                              │
│  • Detect single or multi-intent from NL input                              │
│  • Decompose into atomic tasks, each with:                                  │
│      - task_type: QA | DATA_QUERY | TRANSACTION | ACCOUNT_OPENING           │
│      - entities: amount, recipient, time_range, category, account_type      │
│      - risk_hint: LOW | MEDIUM | HIGH (pre-screening)                       │
│  • Order tasks: sequential (dependent) or parallel (independent)            │
│                                                                              │
│  Example: "I spent too much this month, transfer 5M to savings"             │
│  → Task 1: DATA_QUERY (spending this month)                                │
│  → Task 2: TRANSACTION (transfer 5M to savings) — depends on Task 1        │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. WORKFLOW PLANNER                                                         │
│                                                                              │
│  • Route each atomic task to appropriate specialist                         │
│  • Manage task dependencies (Task 2 waits for Task 1 result)               │
│  • Aggregate final response from all tasks                                  │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. SPECIALIST PREPARES (does not execute)                                    │
│                                                                              │
│  QA Agent          → answer draft + cited policy chunk + policy version     │
│  Text2SQL Agent    → generated SQL statement + NL explanation               │
│  Transaction Agent → transfer payload (from, to, amount, note)              │
│  Onboarding Agent  → eligibility result + KYC completeness + next step      │
│                                                                              │
│  ⚠️ Specialist ONLY prepares. Never calls external APIs or executes.        │
│  ⚠️ Transaction-critical fields (amount, recipient, source account)         │
│     are NEVER auto-repaired or auto-guessed.                                │
│     If missing/ambiguous → ask user to clarify.                             │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. GUARDIAN VALIDATES                                                        │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │ LAYER 1: DETERMINISTIC HARD RULES (always first)              │   │    │
│  │  │                                                                │   │    │
│  │  │ • Recipient in reported_accounts → instant RED                │   │    │
│  │  │ • Amount > account_daily_limit → instant BLOCK                │   │    │
│  │  │ • User mentions being pressured/threatened → ORANGE minimum   │   │    │
│  │  │ • Invalid beneficiary / account mismatch → BLOCK              │   │    │
│  │  │ • SQL contains INSERT/UPDATE/DELETE/DROP → instant REJECT      │   │    │
│  │  │ • Consent scope violated → BLOCK                              │   │    │
│  │  │                                                                │   │    │
│  │  │ If hard rule triggers → SKIP Layer 2, go directly to decision │   │    │
│  │  └──────────────────────────────────┬─────────────────────────────┘   │    │
│  │                                     │                                 │    │
│  │                    (no hard rule triggered)                           │    │
│  │                                     ▼                                 │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │ LAYER 2: MODEL-BASED CHECKS (per action type)                 │   │    │
│  │  │                                                                │   │    │
│  │  │ ── QA Answer ──────────────────────────────────────────────── │   │    │
│  │  │ • Has cited policy chunk? (not just "source exists")          │   │    │
│  │  │ • Answer uses ONLY retrieved policy content?                  │   │    │
│  │  │ • Source confidence above threshold?                          │   │    │
│  │  │ • Policy version / effective date attached?                   │   │    │
│  │  │ → LOW confidence: refuse, say "I don't have enough info"     │   │    │
│  │  │                                                                │   │    │
│  │  │ ── SQL Statement ─────────────────────────────────────────── │   │    │
│  │  │ • AST parse (sqlglot): validate structure                     │   │    │
│  │  │ • Table allowlist: only permitted tables                      │   │    │
│  │  │ • Column allowlist: no sensitive columns                      │   │    │
│  │  │ • WHERE user_id = ? enforced (scoped)                        │   │    │
│  │  │ • LIMIT enforced (bounded)                                    │   │    │
│  │  │ • No subquery leaking other users' data                      │   │    │
│  │  │ → REJECT: attempt auto-repair once, re-validate              │   │    │
│  │  │                                                                │   │    │
│  │  │ ── Transaction ───────────────────────────────────────────── │   │    │
│  │  │                                                                │   │    │
│  │  │  ┌─────────────────────┐                                      │   │    │
│  │  │  │ Anomaly Detector    │                                      │   │    │
│  │  │  │ • Amount vs user avg│                                      │   │    │
│  │  │  │ • Recipient: new?   │                                      │   │    │
│  │  │  │ • Urgency keywords  │                                      │   │    │
│  │  │  │ • Time-of-day       │                                      │   │    │
│  │  │  └────────┬────────────┘                                      │   │    │
│  │  │  ┌────────▼────────────┐                                      │   │    │
│  │  │  │ Scam Pattern Match  │                                      │   │    │
│  │  │  │ • Rule-based first  │                                      │   │    │
│  │  │  │ • LLM advisory:     │                                      │   │    │
│  │  │  │   explain + soft    │                                      │   │    │
│  │  │  │   match only        │                                      │   │    │
│  │  │  │ • LLM NEVER over-   │                                      │   │    │
│  │  │  │   rides hard rules  │                                      │   │    │
│  │  │  └────────┬────────────┘                                      │   │    │
│  │  │  ┌────────▼────────────┐                                      │   │    │
│  │  │  │ Risk Scorer         │                                      │   │    │
│  │  │  │ score = weighted(   │                                      │   │    │
│  │  │  │  anomaly   ×0.35, │                                      │   │    │
│  │  │  │  scam      ×0.35, │                                      │   │    │
│  │  │  │  amount    ×0.15, │                                      │   │    │
│  │  │  │  recipient ×0.15  │                                      │   │    │
│  │  │  │ )                   │                                      │   │    │
│  │  │  └────────┬────────────┘                                      │   │    │
│  │  │           ▼                                                    │   │    │
│  │  │  OUTPUT: risk_tier + score + reasons[]                        │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  │                                                                      │    │
│  │  FINAL: {risk_tier, score, reasons[], triggered_by: HARD|MODEL}      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. RESPONSE STRATEGY + STEP-UP AUTH                                         │
│                                                                              │
│  GREEN  (0–0.3)   → Show EXACT transaction preview                         │
│                    → Bank-native confirmation (not just chat text)           │
│                    → Execute                                                 │
│                                                                              │
│  YELLOW (0.3–0.6) → Soft warning + explain concern                         │
│                    → Show exact transaction details                          │
│                    → Step-up: OTP/PIN/biometric or bank-native signing      │
│                    → Execute if verified                                     │
│                                                                              │
│  ORANGE (0.6–0.8) → Challenge questions (2-3 verification Qs)              │
│                    → Cooldown period                                         │
│                    → Step-up: OTP/PIN/biometric + re-confirm                │
│                    → Execute ONLY if all verification passes                │
│                    → Otherwise: block or escalate to manual review          │
│                                                                              │
│  RED    (0.8–1.0) → Hard block                                              │
│                    → Explain WHY (transparent reasoning)                    │
│                    → Suggest alternatives (hotline, visit branch)           │
│                    → No auth bypass possible. No exception.                 │
│                                                                              │
│  RULE: Transaction-critical fields (amount, recipient, source account)      │
│        are NEVER auto-repaired. If wrong/missing → ask user.               │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6. EXECUTION (only if step 5 allows)                                        │
│                                                                              │
│  QA          → return grounded answer + citation + policy version           │
│  SQL         → execute parameterized read-only query (row-level enforced)   │
│  Transaction → call bank API with idempotency_key                           │
│               (prevents double-execution on retry/double-click)             │
│  Onboarding  → eligibility + KYC completeness check + submit               │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  7. RESPONSE + PROACTIVE INSIGHT + APPEND-ONLY AUDIT                         │
│                                                                              │
│  • Deliver result to user                                                    │
│  • Proactive insight (descriptive only, never financial advice):            │
│    ✅ "Your food spending this month is up 25% vs last month"              │
│    ❌ "You should move money into product X"                                │
│  • Append-only audit log (immutable, no edit/delete):                       │
│    request_id → user_id → session_id → tasks[]                             │
│    → agent_output → guardian_decision (hard_rule | model)                   │
│    → risk_score → auth_method → idempotency_key                            │
│    → final_action → timestamp                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LLM Role Boundaries

| LLM IS ALLOWED TO | LLM IS NEVER ALLOWED TO |
|--------------------|-------------------------|
| Extract intent & entities | Execute transactions |
| Decompose multi-intent into atomic tasks | Override hard rules |
| Generate answers from retrieved policy (with citation) | Be the sole decision-maker for block/allow |
| Generate SQL from NL | Give financial product recommendations |
| Explain Guardian decisions in natural language | Access data outside user's scope |
| Soft-match scam patterns (advisory signal only) | Bypass step-up authentication |
| Generate proactive insights (descriptive only) | Auto-repair transaction-critical fields |

---

## Use Case Flows

### A. Banking Q&A

```text
User → Auth(consent: read) → Decompose(1 task: QA)
→ QA Agent prepares answer + cited policy chunk + version
→ Guardian L1: no hard rule
→ Guardian L2: citation exists? confidence OK? version attached?
→ Execute: return "Per Savings Policy (v2.1, 01/2026): ..."
→ Audit
```

### B. Text2SQL Spending Query

```text
User → Auth(consent: analyze_spending) → Decompose(1 task: DATA_QUERY)
→ Text2SQL Agent prepares SQL
→ Guardian L1: no DML/DDL? ✓
→ Guardian L2: AST parse → table allowlist → column allowlist
  → WHERE user_id → LIMIT → no subquery leak
→ IF PASS: execute parameterized read-only → NL answer + insight
→ IF REJECT: auto-repair once → re-validate → or reject with explanation
→ Audit
```

### C. Safe Transfer

```text
User → Auth(consent: execute_transfer) → Decompose(1 task: TRANSACTION)
→ Transaction Agent prepares payload
→ Guardian L1: recipient not reported ✓, within limit ✓, consent OK ✓
→ Guardian L2: anomaly(0.12) + scam(0.05) → score=0.10 GREEN
→ Response: exact preview → bank-native confirm → execute with idempotency_key
→ Result + proactive nudge → Audit
```

### D. Scam Transfer

```text
User → Auth(consent: execute_transfer) → Decompose(1 task: TRANSACTION)
→ Transaction Agent prepares payload
→ Guardian L1: recipient in reported_accounts → instant RED
→ SKIP Layer 2
→ Response: hard block → explain ("This account has been reported by 8 users")
→ Suggest hotline → Audit
```

### E. Multi-Intent

```text
User: "I spent too much this month, transfer 5M to savings"
→ Auth → Decompose(2 tasks):
  Task 1: DATA_QUERY (spending summary) — independent
  Task 2: TRANSACTION (transfer 5M) — depends on Task 1
→ Task 1: Text2SQL → Guardian → Execute → "You spent 22M this month"
→ Task 2: Transaction → Guardian(GREEN) → Preview → Confirm → Execute
→ Combined response → Audit
```

---

## Guardian Decision Matrix

| Action | Layer 1 (Hard Rules) | Layer 2 (Model) | Auth Required | Auto-repair? |
|--------|---------------------|-----------------|---------------|-------------|
| **QA** | N/A | Citation? Confidence? Version? | None | N/A |
| **Text2SQL** | No DML/DDL | AST + allowlist + scope + LIMIT | None | SQL: 1 attempt |
| **Txn GREEN** | Not reported, within limit | Score < 0.3 | Bank-native confirm | Fields: NEVER |
| **Txn YELLOW** | — | Score 0.3–0.6 | OTP/PIN/biometric | Fields: NEVER |
| **Txn ORANGE** | Pressure detected | Score 0.6–0.8 | Challenge + Cooldown + OTP | Fields: NEVER |
| **Txn RED** | Reported / over limit | Score 0.8+ | BLOCKED (no bypass) | N/A |

---

## Folder Structure

```text
trustflow-guardian/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── backend/
│   ├── main.py                      # FastAPI app + /chat endpoint
│   ├── config.py                    # Thresholds, allowlists, API keys
│   ├── orchestrator.py              # Task decomposition + routing + coordination
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── qa.py                    # RAG Q&A — prepares answer + citation + version
│   │   ├── text2sql.py             # NL → SQL — prepares SQL + explanation
│   │   └── transaction.py          # Parse + prepare transfer payload
│   │
│   ├── guardian/
│   │   ├── __init__.py
│   │   ├── engine.py               # Entry: hard rules → model checks → decision
│   │   ├── hard_rules.py           # Deterministic instant decisions
│   │   ├── risk_scorer.py          # Weighted aggregation → tier
│   │   ├── anomaly.py              # Amount/recipient/urgency/time signals
│   │   ├── scam_rules.py           # Pattern match + LLM advisory (explain only)
│   │   ├── sql_validator.py        # AST parse (sqlglot) + allowlist + scope + LIMIT
│   │   └── friction.py             # Response strategy + step-up auth routing
│   │
│   ├── prompts/
│   │   ├── intent.py               # Task decomposition prompt
│   │   ├── qa.py                   # RAG answering prompt (cite + version)
│   │   ├── text2sql.py             # SQL generation prompt with schema
│   │   └── scam_check.py           # Advisory explanation prompt (never decides)
│   │
│   └── data/
│       ├── users.json              # User profiles + behavioral baselines
│       ├── transactions.json       # Transaction history
│       ├── reported_accounts.json  # Hard-block registry
│       ├── scam_templates.json     # Known scam patterns
│       ├── table_allowlist.json    # Permitted tables + columns for Text2SQL
│       ├── consent_scopes.json     # Granular consent per user
│       └── policies/
│           ├── savings.md          # version: 2.1, effective: 2026-01-01
│           ├── credit_card.md      # version: 1.3, effective: 2025-09-01
│           └── account_opening.md  # version: 1.5, effective: 2025-11-01
│
├── frontend/
│   ├── app.py                      # Streamlit main
│   └── components/
│       ├── chat.py                 # Messages + risk badges
│       ├── scam_alert.py           # RED tier warning modal
│       ├── bank_confirm.py         # Bank-native confirmation modal (mock)
│       ├── otp_modal.py            # Step-up auth OTP input (mock)
│       └── insight_card.py         # Proactive insight (descriptive only)
│
└── tests/
    ├── test_hard_rules.py          # Hard rules unit tests
    ├── test_guardian.py            # Full guardian pipeline
    ├── test_sql_validator.py       # AST + allowlist tests
    └── scenarios/
        ├── safe_transfer.json
        ├── scam_reported_account.json
        ├── scam_impersonation.json
        ├── sql_injection.json
        └── multi_intent.json
```

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI | Async, fast, type-safe |
| LLM | GPT-4o (or 4o-mini) | Switchable via config |
| RAG | ChromaDB + embeddings | Or keyword match for speed |
| DB | SQLite | Text2SQL can query directly |
| Frontend | Streamlit | Ship fast, good enough for demo |
| Session | In-memory dict | Hackathon scope |
| SQL Parsing | sqlglot | AST-based validation |

---

## 4 Key Messages

1. **LLM prepares, never executes.** Specialist agents only create drafts.
2. **Hard rules first, model second.** Deterministic safety before probabilistic scoring.
3. **Every transaction has friction + auth.** Even GREEN requires bank-native confirmation. Transaction fields never auto-guessed.
4. **Immutable audit trail.** Append-only, every decision explained, idempotency-protected.

---

## Implementation Plan

> **Principle**: Core demo = Transaction safety + Guardian + Audit. Text2SQL/QA = priority 1 (build when core is stable). Multi-intent = bonus.

### Priority Map

| Priority | Components | Reason |
|----------|-----------|--------|
| **P0 — Must have** | Transaction Agent, Guardian (hard rules + anomaly + scam + risk scorer + friction), Bank confirm, Scam block, Audit trail | Core differentiator. Without this = demo is dead |
| **P1 — Should have** | Text2SQL Agent, SQL Validator, SQLite query execution | Problem statement requires "NL data queries". Missing = weak alignment with requirements |
| **P2 — Nice to have** | QA RAG (keyword search), Proactive insight, Multi-intent | Adds depth but doesn't determine win/loss |

---

### Phase 1: Scaffold + Transaction + Guardian Core (Day 1)

| Task | File(s) | Description |
|------|---------|-------------|
| **T1.1** Scaffold | Full folder structure | Create folders, `__init__.py`, `docker-compose.yml`, `.env.example` |
| **T1.2** Config | `backend/config.py` | Load env, thresholds (GREEN<0.3, YELLOW<0.6, ORANGE<0.8, RED≥0.8), allowlists, consent scopes |
| **T1.3** FastAPI entry | `backend/main.py` | POST `/chat`: accepts `{user_id, message, session_id}`, returns `{response, risk_tier, audit}` |
| **T1.4** Mock data | `backend/data/*` | `users.json` (3 users + baselines), `transactions.json` (50+ records), `reported_accounts.json`, `scam_templates.json`, `consent_scopes.json` |
| **T1.5** Orchestrator | `backend/orchestrator.py` | Single-intent routing (multi-intent = later). Loop: `classify → agent.prepare() → guardian.validate() → execute if allowed → response` |
| **T1.6** Intent prompt | `backend/prompts/intent.py` | LLM prompt: detect single intent, extract entities, assign risk_hint |
| **T1.7** Transaction Agent | `backend/agents/transaction.py` | Parse NL → transfer payload `{from, to, to_name, amount, note}`. NEVER auto-fill critical fields. If ambiguous → `{needs_clarification: true}` |
| **T1.8** Guardian hard rules | `backend/guardian/hard_rules.py` | Reported recipient → RED, over limit → BLOCK, consent violated → BLOCK, pressure keywords → ORANGE min |
| **T1.9** Anomaly detector | `backend/guardian/anomaly.py` | Score 0–1: amount_vs_avg, recipient_is_new, urgency_keywords, time_of_day |
| **T1.10** Risk scorer | `backend/guardian/risk_scorer.py` | Weighted sum → tier mapping |
| **T1.11** Friction strategy | `backend/guardian/friction.py` | GREEN={confirm}, YELLOW={warn+otp}, ORANGE={challenge+cooldown+otp}, RED={block+explain} |
| **T1.12** Guardian engine | `backend/guardian/engine.py` | Wire: hard_rules → anomaly + scam → risk_scorer → friction.decide() |

**Checkpoint (end of Day 1)**:
- `POST /chat "Transfer 2M to Minh"` → GREEN → confirm prompt
- `POST /chat "Transfer 50M immediately to account 0391234567"` → RED → block + explain

---

### Phase 2: Guardian Polish + Text2SQL (Day 2)

| Task | File(s) | Description |
|------|---------|-------------|
| **T2.1** Scam rules | `backend/guardian/scam_rules.py` | Rule-based template matching + LLM advisory explanation (never decides) |
| **T2.2** Scam prompt | `backend/prompts/scam_check.py` | "If this were a scam, which pattern fits and why? Advisory only." |
| **T2.3** Text2SQL Agent | `backend/agents/text2sql.py`, `backend/prompts/text2sql.py` | LLM generates SQL from NL + schema + user_id. `prepare(query, user_id)` → `{sql, explanation}` |
| **T2.4** SQL Validator | `backend/guardian/sql_validator.py` | `sqlglot` AST parse: SELECT-only, table allowlist, column allowlist, WHERE user_id, LIMIT. Auto-repair: add LIMIT only if missing |
| **T2.5** SQLite setup | `backend/data/init_db.py` | Create SQLite from `transactions.json` for real query execution |
| **T2.6** Table allowlist | `backend/data/table_allowlist.json` | Permitted tables + columns |
| **T2.7** Integration test | E2E via API | Transaction safe + scam + Text2SQL all working through `/chat` |

**Checkpoint (end of Day 2)**:
- Scam transfer → RED with LLM explanation of matched pattern
- "How much did I spend on food this month?" → SQL validated → executed → NL answer
- "SELECT * FROM users" → SQL validator REJECT (table not in allowlist)

---

### Phase 3: Frontend + Demo Flow (Day 3)

| Task | File(s) | Description |
|------|---------|-------------|
| **T3.1** Streamlit chat UI | `frontend/app.py`, `frontend/components/chat.py` | Chat interface + risk badges (🟢🟡🟠🔴) |
| **T3.2** Bank confirm | `frontend/components/bank_confirm.py` | Exact transaction preview + confirm button (mock bank-native) |
| **T3.3** OTP modal | `frontend/components/otp_modal.py` | OTP input for YELLOW+ (mock: accept "123456") |
| **T3.4** Scam alert | `frontend/components/scam_alert.py` | RED tier: full warning with reasons + alternatives |
| **T3.5** Audit trail | Expandable section in chat | Shows: intent → agent output → guardian decision → score → action |
| **T3.6** Demo data tuning | `backend/data/*` | Tune user baselines + reported accounts for demo scenarios |

**Checkpoint (end of Day 3)**: Full UI flow works for safe transfer + scam block + Text2SQL query.

---

### Phase 4: QA + Polish + Rehearsal (Day 4)

| Task | File(s) | Description |
|------|---------|-------------|
| **T4.1** QA Agent | `backend/agents/qa.py`, `backend/prompts/qa.py` | Keyword search over `policies/*.md`. Returns `{answer, cited_chunk, policy_version, confidence}`. No ChromaDB needed — 3 docs, simple search suffices |
| **T4.2** Policy docs | `backend/data/policies/*.md` | Add version headers (version, effective_date) to each doc |
| **T4.3** Proactive insight | `frontend/components/insight_card.py` | Descriptive spending nudge after transactions (never financial advice) |
| **T4.4** Docker compose | `docker-compose.yml` | One-command `docker-compose up`: backend (8000) + frontend (8501) |
| **T4.5** Demo rehearsal | Manual | Run all scenarios 3x, fix any issues |
| **T4.6** Multi-intent (bonus) | `backend/orchestrator.py` | If time: detect 2 intents, route sequentially. Hardcoded demo path OK |

**Checkpoint (Demo Day)**: `docker-compose up` → 3 scenarios seamlessly, 5–8 minutes.

---

### Dependency Graph

```text
Day 1 (P0 — Core Safety):
T1.1 → T1.2 → T1.3 → T1.4 → T1.5/T1.6 → T1.7
                                              ↓
                              T1.8 → T1.9 → T1.10 → T1.11 → T1.12

Day 2 (P0 polish + P1):
T1.12 → T2.1/T2.2 (scam enhancement)
T1.12 → T2.3 → T2.4 → T2.5 (Text2SQL track, parallel with scam)
                              ↓
                            T2.7 (integration test)

Day 3 (Frontend):
T2.7 → T3.1 → T3.2/T3.3/T3.4/T3.5 (all UI components parallel)
                              ↓
                            T3.6 (data tuning)

Day 4 (P2 + Polish):
T3.6 → T4.1/T4.2 (QA, parallel with polish)
        T4.3/T4.4 (insight + docker)
                    ↓
                  T4.5 (rehearsal)
                    ↓
                  T4.6 (multi-intent if time)
```

---

### Key Implementation Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent priority | Transaction first, Text2SQL second, QA last | Core demo = safety. Text2SQL = aligns with requirements. QA = bonus |
| Guardian priority | Hard rules + anomaly Day 1, scam LLM Day 2 | Hard rules alone already demo-able |
| RAG for QA | Keyword search (no ChromaDB) | 3 docs, embeddings are overkill. Add ChromaDB later if needed |
| SQL DB | SQLite | Text2SQL executes real queries, zero setup |
| SQL validation | `sqlglot` AST parse | SELECT-only + allowlist + scope. Skip complex subquery detection for MVP |
| SQL auto-repair | Add LIMIT only | Don't auto-repair WHERE user_id — too risky to get wrong in demo |
| LLM calls | GPT-4o-mini (intent/SQL), GPT-4o (scam advisory) | Cost vs quality |
| Session state | In-memory dict | Hackathon scope |
| Auth mock | OTP = "123456", bank confirm = button click | Demo flow, not real auth |
| Idempotency | UUID per transaction request | Prevent double-exec |
| Multi-intent | Single-intent default. Multi = bonus Day 4 | Don't over-engineer core path |

---

### Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM latency in demo | GPT-4o-mini for speed, pre-warm connections, cache intent results |
| Guardian not done by Day 2 | Hard rules alone can carry demo (reported account → RED). Scam LLM is enhancement |
| Text2SQL SQL errors | Validator catches bad SQL. If Text2SQL fails, demo still has transaction safety |
| Demo data doesn't trigger flows | Pre-script exact messages + seed user with known baselines + known reported accounts |
| Time runs out | Cut order: multi-intent → QA → insight → Text2SQL. Transaction + Guardian + Audit = non-negotiable |

---

### Verification Checklist (Demo Day)

| # | Scenario | Expected | Priority |
|---|----------|----------|----------|
| 1 | "Transfer 2M to Minh for food" | GREEN → preview → confirm → success + nudge | P0 |
| 2 | "Transfer 50M immediately to account 0391234567" | RED → block → explain → suggest hotline | P0 |
| 3 | Audit trail visible | Expandable decision log per interaction | P0 |
| 4 | "How much did I spend on food this month?" | SQL → validate → execute → NL answer | P1 |
| 5 | "What's the 6-month savings interest rate?" | Answer + citation + policy version | P2 |
