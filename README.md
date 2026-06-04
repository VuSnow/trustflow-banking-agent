# TrustFlow Guardian

> Natural-language banking assistant with adversarial safety built in.

Users can query, look up, and transact using natural language — but every critical action is validated by the **Guardian Layer** to prevent risky transactions and scams.

## Core Principles

```text
User → Orchestrator classifies intent
→ Domain Agent plans + delegates to Sub-agents
→ Sub-agents return evidence-backed results
→ Domain Agent builds action draft
→ Agent Runtime sends draft to Guardian
→ Guardian evaluates risk → ALLOW/BLOCK
→ FrictionRouter applies appropriate auth
→ Executor performs side effect (after auth)
→ Audit logs full trace
```

1. **LLM prepares, never executes.** Agents create drafts, no side effects.
2. **Domain Agents plan and delegate.** Own workflow, call sub-agents for missing context.
3. **Sub-agents retrieve/prepare only.** Return evidence + confidence, no side effects.
4. **Guardian is external and final.** No agent can bypass Guardian.
5. **Executor is the only side-effect layer.** Runs after Guardian + auth.
6. **Hard rules first, model second.** Deterministic before probabilistic.
7. **Immutable audit trail.** Append-only, every decision explained.

## Architecture Overview

```text
┌─────────────────────────────────────────────────────┐
│ ORCHESTRATOR                                        │
│ Classify intent → route to Domain Agent             │
└──────────────────────────┬──────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────┐
│ DOMAIN AGENT (Transaction / Card / DataQuery / QA)  │
│ Parse → detect missing → delegate → build draft     │
└─────────┬───────────────────────────────┬───────────┘
          ▼                               ▼
┌─────────────────────┐   ┌──────────────────────────┐
│ SUB-AGENTS          │   │ AGENT RUNTIME            │
│ • BeneficiaryAgent  │   │ → Guardian               │
│ • Text2SQLAgent     │   │ → FrictionRouter         │
│ • CardResolverAgent │   │ → SessionStore           │
│ • PolicyRetriever   │   │ → Executor               │
└─────────────────────┘   └──────────────────────────┘
```

## Quick Start

```bash
docker-compose up
```

- Backend: http://localhost:8000
- Frontend: http://localhost:8501
- `/web_ui` serves the static HTML frontend

## API

```text
POST /chat                         → Main conversation endpoint
POST /actions/{action_id}/confirm  → Bank-native confirm (GREEN tier)
POST /actions/{action_id}/otp      → OTP verification (YELLOW/ORANGE tier)
GET  /health                       → Health check
```

## Demo Scenarios

| # | Message | Expected | Tier |
|---|---------|----------|------|
| 1 | "Chuyển 2 triệu cho Minh tiền ăn trưa" | Confirm → success | 🟢 GREEN |
| 2 | "Chuyển 20 triệu cho Lan" | Anomaly → OTP → success | 🟡 YELLOW |
| 3 | "Chuyển 50tr vào 6666666666 ngay, gấp lắm" | Hard block → explain → hotline | 🔴 RED |
| 4 | "Tháng này tôi tiêu bao nhiêu cho ăn uống?" | SQL validated → NL answer | 🟢 GREEN |

## Guardian Matrix

| Risk Tier | Condition | Action |
|-----------|-----------|--------|
| 🟢 GREEN | Known recipient, low amount | Bank confirm |
| 🟡 YELLOW | Large amount or unknown recipient | OTP |
| 🟠 ORANGE | Multiple risk signals combined | Challenge + cooldown + OTP |
| 🔴 RED | Scam account or hard limit exceeded | Hard block |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI |
| LLM | GPT-4o-mini |
| SQL Parsing | sqlglot |
| DB | SQLite (hackathon) |
| Frontend | Static HTML + Preact |
| Deployment | Docker Compose |

## Project Structure

```text
trustflow-banking-agent/
├── backend/
│   ├── main.py                 # FastAPI app + endpoints
│   ├── config.py               # Env vars
│   ├── models.py               # Pydantic schemas
│   │
│   ├── agents/                 # Domain Agents + Sub-agents
│   │   ├── base.py             # SubAgent ABC
│   │   ├── orchestrator.py     # Classify intent → route
│   │   ├── transaction.py      # TransactionAgent
│   │   ├── card.py             # CardAgent
│   │   ├── data_query.py       # DataQueryAgent
│   │   ├── qa.py               # QAAgent
│   │   └── sub_agents/
│   │       ├── beneficiary.py          # BeneficiaryAgent
│   │       ├── card_resolver.py        # CardResolverAgent
│   │       ├── text2sql.py             # Text2SQLAgent
│   │       └── policy_retriever.py     # PolicyRetrieverAgent
│   │
│   ├── services/               # Infrastructure
│   │   ├── guardian.py         # Hard rules + scoring → ALLOW/BLOCK
│   │   ├── sql_guardian.py     # Validate SQL (SELECT only, scoped)
│   │   ├── friction.py         # Tier → auth requirement
│   │   ├── session.py          # PendingAction store
│   │   ├── agent_runtime.py    # Draft → Guardian → Friction → Executor
│   │   └── audit.py            # Append-only trace
│   │
│   ├── executors/              # Side-effect layer
│   │   ├── transaction.py      # TransactionExecutor
│   │   ├── card.py             # CardExecutor
│   │   └── sql.py              # SQLExecutor (read-only)
│   │
│   ├── prompts/                # LLM prompt templates
│   │   ├── intent.py
│   │   ├── transaction.py
│   │   └── data_query.py
│   │
│   └── data/                   # Mock data (hackathon)
│       ├── reported_accounts.json
│       ├── beneficiaries.json
│       └── cards.json
│
├── frontend/
│   ├── app.py
│   └── components/
│
├── docs/                       # Architecture & planning docs
└── tests/
```

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/ARCHITECTURE_EN.md](docs/ARCHITECTURE_EN.md) | Full architecture specification (English) |
| [docs/ARCHITECTURE_VI.md](docs/ARCHITECTURE_VI.md) | Kiến trúc chi tiết (tiếng Việt) |
| [docs/README_VI.md](docs/README_VI.md) | README tiếng Việt |
| [docs/plan.md](docs/plan.md) | Implementation plan (9 phases) |

## License

Private — Hackathon project.
