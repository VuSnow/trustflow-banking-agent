# TrustFlow Guardian

> Natural-language banking assistant with adversarial safety built in.

Users can query, look up, and transact using natural language — but every critical action is validated by the **Guardian Layer** to prevent bad queries, risky transactions, and scams.

## Core Principle

```text
Orchestrator routes → AgentClient prepares → Guardian validates → Executor executes → Audit logs
```

- **LLM prepares, never executes.** Agents only create drafts/payloads.
- **Hard rules first, model second.** Deterministic safety before probabilistic scoring.
- **Executor is separate from Agent.** Agents prepare; Executors act after Guardian approves.
- **Immutable audit trail.** Append-only, every decision explained.

## What This Repo Does

This repo is the **Orchestrator + Guardian + Executors + Frontend** — the brain and safety layer.

Specialist agents (Text2SQL, QA RAG, Transaction Parser) live behind an `AgentClient` interface. Hackathon uses mock implementations; production swaps to HTTP/gRPC clients calling separate services.

## Quick Start

```bash
docker-compose up
```

- Backend: http://localhost:8000
- Frontend: http://localhost:8501

## API

```text
POST /chat                         → Main conversation endpoint
POST /actions/{action_id}/confirm  → Bank-native confirm (GREEN tier)
POST /actions/{action_id}/otp      → OTP verification (YELLOW/ORANGE tier)
GET  /audit/{audit_id}             → Retrieve audit trail
```

## Demo Scenarios

| # | Message | Expected | Tier |
|---|---------|----------|------|
| 1 | "Transfer 2M to Minh for lunch" | Confirm → success | 🟢 GREEN |
| 2 | "Transfer 20M to Lan" | Anomaly warning → OTP → success | 🟡 YELLOW |
| 3 | "Transfer 50M to 0391234567" | Hard block → explain → hotline | 🔴 RED |
| 4 | "How much did I spend on food this month?" | SQL validated → NL answer | 🟢 GREEN |

## Architecture

See [README_ARCHITECTURE.md](README_ARCHITECTURE.md) for full architecture, folder structure, models, production roadmap, and implementation timeline.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI |
| LLM | GPT-4o / GPT-4o-mini |
| SQL Parsing | sqlglot |
| DB | SQLite |
| Frontend | Streamlit |
| Deployment | Docker Compose |

## Project Structure

```text
trustflow-banking-agent/
├── backend/
│   ├── main.py              # FastAPI app + routes
│   ├── config.py            # Thresholds, env vars
│   ├── models.py            # Pydantic schemas
│   ├── orchestrator.py      # Intent → route → guardian → executor → audit
│   ├── agents/              # AgentClient interface + mock impls
│   ├── guardian/            # Safety validation (hard rules + model checks)
│   ├── executors/           # Post-guardian execution
│   ├── session/             # Pending action state
│   ├── auth/                # Mock auth (OTP, bank confirm)
│   ├── audit/               # Append-only logging
│   ├── prompts/             # LLM prompt templates
│   └── data/                # Mock data + SQLite
├── frontend/
│   ├── app.py               # Streamlit main
│   └── components/          # Chat, modals, audit viewer
└── tests/
    ├── test_guardian.py
    ├── test_hard_rules.py
    └── scenarios/
```

## License

Private — Hackathon project.
