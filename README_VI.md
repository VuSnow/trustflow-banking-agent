# TrustFlow Guardian

> Trợ lý ngân hàng bằng ngôn ngữ tự nhiên với lớp bảo vệ chống gian lận.

Người dùng có thể tra cứu, hỏi đáp và giao dịch bằng ngôn ngữ tự nhiên — nhưng mọi hành động quan trọng đều được **Guardian Layer** kiểm tra để ngăn truy vấn sai, giao dịch rủi ro và scam.

## Nguyên tắc cốt lõi

```text
Orchestrator điều phối → AgentClient chuẩn bị → Guardian kiểm tra → Executor thực thi → Audit ghi log
```

- **LLM chỉ chuẩn bị, không bao giờ thực thi.** Agent chỉ tạo draft/payload.
- **Hard rules trước, model sau.** An toàn xác định trước, scoring xác suất sau.
- **Executor tách biệt khỏi Agent.** Agent chuẩn bị; Executor hành động sau khi Guardian duyệt.
- **Audit trail bất biến.** Chỉ ghi thêm, không sửa/xóa, mọi quyết định đều giải thích được.

## Repo này làm gì

Repo này là **Orchestrator + Guardian + Executors + Frontend** — bộ não điều phối và lớp an toàn.

Các specialist agents (Text2SQL, QA RAG, Transaction Parser) nằm sau `AgentClient` interface. Hackathon dùng mock implementation; production swap sang HTTP/gRPC client gọi service riêng.

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

## Kiến trúc

Xem [README_ARCHITECTURE.md](README_ARCHITECTURE.md) để biết chi tiết kiến trúc, folder structure, models, production roadmap và timeline triển khai.

## Tech Stack

| Layer | Lựa chọn |
|-------|----------|
| Backend | FastAPI |
| LLM | GPT-4o / GPT-4o-mini |
| SQL Parsing | sqlglot |
| DB | SQLite |
| Frontend | Streamlit |
| Deployment | Docker Compose |

## Cấu trúc dự án

```text
trustflow-banking-agent/
├── backend/
│   ├── main.py              # FastAPI app + routes
│   ├── config.py            # Thresholds, env vars
│   ├── models.py            # Pydantic schemas
│   ├── orchestrator.py      # Intent → route → guardian → executor → audit
│   ├── agents/              # AgentClient interface + mock impls
│   ├── guardian/            # Kiểm tra an toàn (hard rules + model checks)
│   ├── executors/           # Thực thi sau guardian
│   ├── session/             # Quản lý pending action state
│   ├── auth/                # Mock auth (OTP, bank confirm)
│   ├── audit/               # Ghi log bất biến
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
