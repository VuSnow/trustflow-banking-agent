# TrustFlow Guardian

> Trợ lý ngân hàng bằng ngôn ngữ tự nhiên với lớp bảo vệ chống gian lận.

Người dùng có thể tra cứu, hỏi đáp và giao dịch bằng ngôn ngữ tự nhiên — nhưng mọi hành động quan trọng đều được **Guardian Layer** kiểm tra để ngăn giao dịch rủi ro và scam.

## Nguyên tắc cốt lõi

```text
User → Orchestrator phân loại intent
→ Domain Agent lên kế hoạch + ủy quyền cho Sub-agent
→ Sub-agent trả kết quả có bằng chứng
→ Domain Agent xây dựng action draft
→ Agent Runtime gửi draft cho Guardian
→ Guardian đánh giá risk → ALLOW/BLOCK
→ FrictionRouter áp xác thực phù hợp
→ Executor thực thi (sau auth)
→ Audit ghi trace
```

1. **LLM chỉ chuẩn bị, không bao giờ thực thi.** Agent tạo draft, không gọi side effect.
2. **Domain Agent lên kế hoạch và ủy quyền.** Sở hữu workflow, gọi sub-agent khi thiếu context.
3. **Sub-agent chỉ truy xuất/chuẩn bị.** Trả kết quả có evidence + confidence, không side effect.
4. **Guardian là external và final.** Không agent nào bypass được Guardian.
5. **Executor là tầng side-effect duy nhất.** Chỉ chạy sau Guardian + auth.
6. **Hard rules trước, model sau.** Deterministic trước, probabilistic sau.
7. **Audit trail bất biến.** Chỉ ghi thêm, không sửa/xóa.

## Kiến trúc tổng quan

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

## Khởi chạy nhanh

```bash
docker-compose up
```

- Backend: http://localhost:8000
- Frontend: http://localhost:8501

## API

```text
POST /chat                         → Endpoint hội thoại chính
POST /actions/{action_id}/confirm  → Xác nhận giao dịch (GREEN tier)
POST /actions/{action_id}/otp      → Xác thực OTP (YELLOW/ORANGE tier)
GET  /audit/{audit_id}             → Xem audit trail
```

## Demo Scenarios

| # | Tin nhắn | Kết quả | Tier |
|---|----------|---------|------|
| 1 | "Chuyển 2 triệu cho Minh tiền ăn trưa" | Xác nhận → thành công | 🟢 GREEN |
| 2 | "Chuyển 20 triệu cho Lan" | Cảnh báo bất thường → OTP → thành công | 🟡 YELLOW |
| 3 | "Chuyển 50 triệu vào tài khoản 0391234567" | Chặn → giải thích → gợi ý hotline | 🔴 RED |
| 4 | "Tháng này tôi tiêu bao nhiêu cho ăn uống?" | SQL validated → trả lời bằng NL | 🟢 GREEN |

## Guardian Matrix

| Risk Tier | Điều kiện | Hành động |
|-----------|-----------|-----------|
| 🟢 GREEN | Recipient quen, số tiền nhỏ | Bank confirm |
| 🟡 YELLOW | Số tiền lớn hoặc recipient lạ | OTP |
| 🟠 ORANGE | Nhiều tín hiệu rủi ro cộng dồn | Challenge + cooldown + OTP |
| 🔴 RED | Scam account hoặc vượt ngưỡng cứng | Hard block |

## Tech Stack

| Layer | Lựa chọn |
|-------|----------|
| Backend | FastAPI |
| LLM | GPT-4o-mini |
| SQL Parsing | sqlglot |
| DB | SQLite (hackathon) |
| Frontend | Streamlit |
| Deployment | Docker Compose |

## Cấu trúc dự án

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
└── tests/
```

## Tài liệu chi tiết

- [ARCHITECTURE_VI.md](ARCHITECTURE_VI.md) — Kiến trúc chi tiết (tiếng Việt)
- [ARCHITECTURE_EN.md](ARCHITECTURE_EN.md) — Architecture specification (English)

## License

Private — Hackathon project.
