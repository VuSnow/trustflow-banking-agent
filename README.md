# TrustFlow Guardian

> Natural-language banking assistant with adversarial safety built in.

Users can query, look up, and transact using natural language — but every critical action is validated by the **Guardian Layer** to prevent risky transactions and scams.

## Core Principle

```text
User → Orchestrator classifies intent
→ Domain Agent plans + delegates to Sub-agents
→ Domain Agent builds action draft
→ Agent Runtime sends draft to Guardian
→ Guardian validates → ALLOW/BLOCK
→ FrictionRouter applies auth
→ Executor performs side effect
→ Audit logs full trace
```

1. **LLM prepares, never executes.** Agents create drafts only.
2. **Domain Agents plan and delegate.** Own workflow, call sub-agents for context.
3. **Guardian is external and final.** No agent can bypass.
4. **Executor is the only side-effect layer.** Runs after Guardian + auth.
5. **Immutable audit trail.** Append-only, every decision explained.

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
GET  /health                       → Health check
```

## Demo Scenarios

| # | Message | Expected | Tier |
|---|---------|----------|------|
| 1 | "Chuyển 2 triệu cho Minh tiền ăn trưa" | Confirm → success | 🟢 GREEN |
| 2 | "Chuyển 20 triệu cho Lan" | Anomaly → OTP → success | 🟡 YELLOW |
| 3 | "Chuyển 50tr vào 6666666666 ngay, gấp lắm" | Hard block | 🔴 RED |
| 4 | "Tháng này tôi tiêu bao nhiêu cho ăn uống?" | SQL validated → NL answer | 🟢 GREEN |

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/ARCHITECTURE_VI.md](docs/ARCHITECTURE_VI.md) | Kiến trúc chi tiết (tiếng Việt) |
| [docs/ARCHITECTURE_EN.md](docs/ARCHITECTURE_EN.md) | Architecture specification (English) |
| [docs/README_VI.md](docs/README_VI.md) | README tiếng Việt |
| [docs/plan.md](docs/plan.md) | Implementation plan (9 phases) |

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI |
| LLM | GPT-4o-mini |
| SQL Parsing | sqlglot |
| DB | SQLite (hackathon) |
| Frontend | Streamlit |
| Deployment | Docker Compose |

## Project Structure

```text
trustflow-banking-agent/
├── backend/
│   ├── main.py                 # FastAPI app + endpoints
│   ├── config.py               # Env vars
│   ├── models.py               # Pydantic schemas
│   ├── agents/                 # Domain Agents + Sub-agents
│   │   ├── orchestrator.py     # Classify intent → route
│   │   ├── transaction.py      # TransactionAgent
│   │   └── sub_agents/         # BeneficiaryAgent, CardResolver, etc.
│   ├── services/               # Guardian, Friction, Session, AgentRuntime
│   ├── executors/              # Side-effect layer (post-Guardian)
│   ├── prompts/                # LLM prompt templates
│   └── data/                   # Mock data (JSON + SQLite)
├── frontend/
│   ├── app.py
│   └── components/
├── docs/                       # Architecture & planning docs
└── tests/
```

## License

Private — Hackathon project.
