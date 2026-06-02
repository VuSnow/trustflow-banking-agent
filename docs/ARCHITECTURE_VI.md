# TrustFlow Guardian — Kiến trúc

> Trợ lý ngân hàng bằng ngôn ngữ tự nhiên với lớp an toàn chống gian lận.

---

## 1. Thông điệp cốt lõi

Người dùng có thể tra cứu, hỏi đáp và giao dịch bằng ngôn ngữ tự nhiên. Mọi hành động quan trọng đều được Guardian Layer kiểm tra. Domain Agent có thể lên kế hoạch và ủy quyền cho sub-agent để thu thập context, nhưng không bao giờ thực thi side effect và không bao giờ bỏ qua Guardian.

---

## 2. Nguyên tắc cốt lõi

```text
User → Orchestrator phân loại domain
→ Domain Agent lên kế hoạch và ủy quyền
→ Sub-agent thu thập context thiếu (có bằng chứng)
→ Domain Agent xây dựng action draft
→ Guardian kiểm tra
→ Friction/Auth gate trước khi thực thi
→ Executor thực hiện side effect
→ Audit ghi toàn bộ trace
```

1. **LLM chuẩn bị, không bao giờ thực thi.** Agent chỉ tạo draft/payload.
2. **Agent có thể lên kế hoạch và ủy quyền.** Domain Agent sở hữu workflow policy và gọi sub-agent.
3. **Sub-agent chỉ truy xuất/chuẩn bị.** Trả kết quả có bằng chứng, không side effect.
4. **Guardian là external và có quyền tối cao.** Không agent nào bypass được Guardian.
5. **Executor là tầng side-effect duy nhất.** Chỉ chạy sau Guardian + auth.
6. **Hard rules trước, model sau.** An toàn xác định trước, scoring xác suất sau.
7. **Text2SQL được bảo vệ và chỉ đọc.** Sinh SQL tách biệt khỏi thực thi SQL.
8. **Giải quyết dựa trên bằng chứng.** Trường quan trọng phải có source/confidence.
9. **Xác nhận theo ngưỡng confidence.** Confidence thấp hoặc nhiều ứng viên → hỏi user.
10. **Audit trail bất biến.** Chỉ ghi thêm, mọi quyết định đều giải thích được.

---

## 3. Kiến trúc tổng quan

```text
┌──────────────────────────────────────────────────────────────────────┐
│                              USER                                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ POST /chat
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR                                                         │
│ • Phân loại intent (1 LLM call → task_type + confidence)             │
│ • Route đến Domain Agent theo task_type                              │
│ • KHÔNG extract entity hay resolve business detail                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ DOMAIN AGENT (TransactionAgent / CardAgent / DataQueryAgent / ...)   │
│ • Parse request (LLM extract structured fields)                      │
│ • Phát hiện trường thiếu                                             │
│ • Lên kế hoạch: gọi sub-agent nào                                    │
│ • Ủy quyền cho sub-agent/tool đã approve                             │
│ • Thu thập kết quả có bằng chứng                                     │
│ • Xây dựng và trả về action_draft (KHÔNG gọi Guardian trực tiếp)     │
└─────────────┬────────────────────────────────────────┬───────────────┘
              │ ủy quyền                               │ trả draft
              ▼                                        ▼
┌─────────────────────────────┐    ┌───────────────────────────────────┐
│ SUB-AGENTS / TOOLS          │    │ AGENT RUNTIME                     │
│ • RecipientResolutionAgent  │    │ • Nhận DomainAgentOutput          │
│ • TransactionHistoryAgent   │    │ • Gửi action_draft cho Guardian   │
│ • BeneficiaryAgent          │    │ • Gọi FrictionRouter              │
│ • CardResolverAgent         │    │ • Lưu PendingAction               │
│ • PolicyRetrieverAgent      │    │ • Route đến Executor đúng         │
│ • Text2SQLAgent             │    └───────────────────┬───────────────┘
│   → SQLGuardian → SQLExec   │                        │
└─────────────────────────────┘                        ▼
                               ┌───────────────────────────────────────┐
                               │ GUARDIAN                              │
                               │ • Hard rules (block ngay lập tức)     │
                               │ • Scoring (anomaly, scam, amount)     │
                               │ • Risk tier → GREEN/YELLOW/ORANGE/RED │
                               │ • Quyết định: ALLOW hoặc BLOCK        │
                               │ • Không bao giờ sinh trường thiếu     │
                               └───────────────────┬───────────────────┘
                                                   │
                                                   ▼
                               ┌───────────────────────────────────────┐
                               │ FRICTION / AUTH                       │
                               │ • GREEN  → xác nhận ngân hàng         │
                               │ • YELLOW → OTP                        │
                               │ • ORANGE → challenge + cooldown + OTP │
                               │ • RED    → chặn hoàn toàn             │
                               └───────────────────────┬───────────────┘
                                                       │ sau auth
                                                       ▼
                               ┌───────────────────────────────────────────────────┐
                               │ EXECUTOR (route bởi PendingAction.executor_type)  │
                               │ • TransactionExecutor / CardExecutor / ...        │
                               │ • Thực hiện side effect (mock/thật)               │
                               │ • Idempotency key chống double-exec               │
                               └───────────────────────┬───────────────────────────┘
                                                       │
                                                       ▼
                               ┌───────────────────────────────────────┐
                               │ AUDIT                                 │
                               │ • Trace log chỉ ghi thêm              │
                               │ • Ghi chuỗi delegation giữa agent     │
                               │ • Quyết định Guardian + lý do         │
                               └───────────────────────────────────────┘
```

---

## 4. Mô hình Agent-to-Agent

Domain Agent không phải parser thụ động. Chúng là **planning agent** sở hữu workflow policy và có thể ủy quyền cho sub-agent.

```text
TransactionAgent
  → parse tin nhắn user → structured extraction
  → phát hiện trường thiếu (recipient_account, bank, v.v.)
  → lên kế hoạch: "Tôi cần resolve recipient từ lịch sử"
  → ủy quyền cho TransactionHistoryAgent (structured task, scoped constraints)
  → nhận candidates có bằng chứng
  → nếu confident → xây draft
  → nếu mơ hồ → hỏi user
  → trả action_draft cho agent runtime
  → agent runtime gửi draft cho Guardian
```

Ràng buộc delegation:
- Domain Agent gửi **structured tasks** (không phải free-form prompts) cho sub-agent
- Output của sub-agent bị **ràng buộc schema** (allowed_output được định trước)
- Domain Agent **không bao giờ tự execute** dựa trên kết quả sub-agent cho trường high-risk
- Bằng chứng phải bao gồm **source reference + confidence score**

```text
AgentTask {
  task_type: str                    // "resolve_recipient", "search_history"
  constraints: {                    // scoped input
    current_user_id: str
    recipient_name: str
    amount: int
    time_range: str
  }
  allowed_output: [str]             // sub-agent được phép trả gì
}

AgentTaskResult {
  candidates: [{...}]
  evidence: [str]                   // transaction_ids, source refs
  confidence: float
  source_agent: str
}
```

---

## 5. Phân loại Intent và Routing

Orchestrator phân loại **một** `task_type` cấp cao và route đến Domain Agent đúng.

| task_type | Domain Agent | Subtypes |
|-----------|-------------|----------|
| QA | QAAgent | câu hỏi policy, phí, lãi suất, sản phẩm, tài liệu |
| DATA_QUERY | DataQueryAgent | số dư, chi tiêu, thu nhập, lịch sử, người nhận |
| TRANSACTION | TransactionAgent | TRANSFER_MONEY, BILL_PAYMENT, TOP_UP |
| CARD_OPERATION | CardAgent | LOCK_CARD, UNLOCK_CARD, ACTIVATE_CARD, REISSUE_CARD, CHANGE_CARD_LIMIT, VIEW_CARD_INFO |
| ACCOUNT_OPERATION | AccountAgent | OPEN_ACCOUNT, CLOSE_ACCOUNT, UPDATE_ACCOUNT_INFO, MANAGE_BENEFICIARY, VIEW_ACCOUNT_INFO |
| LOAN_OPERATION | LoanAgent | APPLY_LOAN, CHECK_LOAN_STATUS, REPAY_LOAN, VIEW_LOAN_INFO |
| FRAUD_REPORT | FraudReportAgent | REPORT_FRAUD_ACCOUNT |

Orchestrator **KHÔNG**:
- Extract entity từ tin nhắn
- Gọi extractor cấp thấp
- Resolve business detail
- Ra quyết định risk

---

## 6. Trách nhiệm từng thành phần

### Orchestrator

| Được làm | Không được làm |
|----------|----------------|
| Phân loại intent (1 LLM call) | Extract entity |
| Route đến Domain Agent | Resolve business detail |
| Trả response từ Domain Agent | Ra quyết định risk |
| Xử lý intent không xác định | Gọi sub-agent trực tiếp |

### Domain Agents (TransactionAgent, CardAgent, AccountAgent, LoanAgent, DataQueryAgent, QAAgent)

| Được làm | Không được làm |
|----------|----------------|
| Parse request (LLM extract) | Thực thi giao dịch |
| Xác định trường thiếu | Chạy SQL trực tiếp |
| Tạo kế hoạch resolution | Bypass Guardian |
| Ủy quyền cho sub-agent đã approve | Tự approve risk |
| Thu thập output có bằng chứng | Gọi banking/payment API |
| Xây dựng và trả action draft | Override quyết định Guardian |
| | Tự điền trường high-risk không có bằng chứng |
| | Gọi Guardian trực tiếp (runtime lo việc này) |

### Sub-agents (RecipientResolutionAgent, TransactionHistoryAgent, BeneficiaryAgent, v.v.)

| Được làm | Không được làm |
|----------|----------------|
| Nhận structured task | Thực thi side effect |
| Query dữ liệu có scope | Approve risk |
| Trả candidates có bằng chứng | Override Guardian |
| Trả confidence score | Trả dữ liệu không scoped |
| Giải thích nguồn resolution | Tự điền trường high-risk |

### Text2SQLAgent

| Được làm | Không được làm |
|----------|----------------|
| Sinh SQL template | Thực thi SQL |
| Sinh query parameters | UPDATE/DELETE/INSERT/DROP |
| Giải thích query | Truy cập dữ liệu ngoài scope user |
| | Ra quyết định business |

Flow bắt buộc:
```text
Agent gọi (Domain Agent hoặc sub-agent)
→ Text2SQLAgent sinh SQL template + params
  (có thể chứa :user_id placeholder; giá trị user_id từ LLM bị bỏ qua)
→ SQLGuardian validate:
   • Chỉ SELECT (không DML/DDL)
   • Table trong allowlist
   • user_id scope bắt buộc (WHERE user_id = ?)
   • LIMIT có mặt khi cần
→ SQLExecutor thực thi (parameterized)
  (inject user_id thật từ auth context, không bao giờ từ LLM)
→ Kết quả trả về agent gọi kèm bằng chứng
```

### Guardian

| Được làm | Không được làm |
|----------|----------------|
| Validate action draft | Sinh trường thiếu |
| Áp dụng hard rules (block ngay) | Resolve business entity |
| Chấm điểm risk (anomaly, scam, amount) | Thực thi giao dịch |
| Gán risk tier (GREEN/YELLOW/ORANGE/RED) | Override user auth |
| Output: ALLOW hoặc BLOCK | Quyết định auth type (FrictionRouter lo) |
| Giải thích quyết định kèm lý do | |

### Friction / Auth

| Được làm | Không được làm |
|----------|----------------|
| Map risk tier → auth requirement | Ra quyết định risk |
| Yêu cầu confirm/OTP/challenge | Thực thi không auth |
| Áp dụng cooldown | Bypass Guardian |

### Executor

| Được làm | Không được làm |
|----------|----------------|
| Thực thi action đã approve | Thực thi không qua Guardian |
| Đảm bảo idempotency | Quyết định risk |
| Trả kết quả thực thi | Tự approve action |
| | Thực thi action bị block |

### Audit

| Được làm | Không được làm |
|----------|----------------|
| Ghi toàn bộ agent trace | Sửa/xóa log |
| Ghi quyết định Guardian + lý do | |
| Ghi chuỗi delegation | |
| Ghi timestamp và user_id | |

---

## 7. Kiến trúc Hackathon

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Streamlit)                        │
│  • Chat UI + risk badges (🟢🟡🟠🔴)                                 │
│  • Modal xác nhận ngân hàng (GREEN)                                 │
│  • Modal OTP (YELLOW)                                               │
│  • Modal cảnh báo scam (RED)                                        │
│  • Audit trail viewer (mở rộng theo message)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GATEWAY (FastAPI) — REPO NÀY                     │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ ORCHESTRATOR                                                  │  │
│  │ • Phân loại intent (1 LLM call → task_type)                   │  │
│  │ • Route đến Domain Agent                                      │  │
│  │ • Trả response Domain Agent cho frontend                      │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ DOMAIN AGENTS (lên kế hoạch + ủy quyền + xây draft)           │  │
│  │                                                               │  │
│  │ • TransactionAgent:                                           │  │
│  │   → Parse message (LLM extract)                               │  │
│  │   → Phát hiện trường thiếu                                    │  │
│  │   → Ủy quyền cho RecipientResolutionAgent / HistoryAgent      │  │
│  │   → Xây transaction draft                                     │  │
│  │   → Trả draft cho agent runtime                               │  │
│  │                                                               │  │
│  │ • CardAgent:                                                  │  │
│  │   → Parse card operation                                      │  │
│  │   → Ủy quyền cho CardResolverAgent                            │  │
│  │   → Xây card_action_draft                                     │  │
│  │   → Trả draft cho agent runtime                               │  │
│  │                                                               │  │
│  │ • DataQueryAgent:                                             │  │
│  │   → Lên kế hoạch read-only query                              │  │
│  │   → Ủy quyền cho Text2SQLAgent → SQLGuardian → SQLExecutor    │  │
│  │   → Tóm tắt kết quả bằng ngôn ngữ tự nhiên                    │  │
│  │                                                               │  │
│  │ • QAAgent:                                                    │  │
│  │   → Ủy quyền cho PolicyRetrieverAgent                         │  │
│  │   → Sinh câu trả lời có trích dẫn                             │  │
│  │                                                               │  │
│  │ • FraudReportAgent:                                           │  │
│  │   → Parse thông tin báo cáo gian lận (LLM extract)            │  │
│  │   → Ủy quyền cho FraudVerificationAgent (kiểm tra giao dịch)  │  │
│  │   → Multi-turn: hỏi context gian lận                          │  │
│  │   → Tính confidence score (rule-based)                        │  │
│  │   → Xây fraud_report_draft                                    │  │
│  │   → Trả draft cho agent runtime                               │  │
│  │                                                               │  │
│  │ • AccountAgent / LoanAgent (cùng pattern)                     │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ SUB-AGENTS / TOOLS (truy xuất + chuẩn bị, không thực thi)     │  │
│  │                                                               │  │
│  │ • RecipientResolutionAgent  → resolve người nhận đã lưu       │  │
│  │ • TransactionHistoryAgent   → tìm giao dịch cũ (qua Text2SQL) │  │
│  │ • BeneficiaryAgent          → quản lý danh sách người nhận    │  │
│  │ • CardResolverAgent         → resolve thẻ mục tiêu            │  │
│  │ • AccountProfileAgent       → resolve thông tin tài khoản     │  │
│  │ • LoanInfoAgent             → tra cứu chi tiết khoản vay      │  │
│  │ • PolicyRetrieverAgent      → truy xuất policy docs + version │  │
│  │ • FraudVerificationAgent    → xác minh user có GD với STK     │  │
│  │ • Text2SQLAgent             → chỉ sinh SQL                    │  │
│  │                                                               │  │
│  │ ⚠️  Sub-agent chỉ chuẩn bị/truy xuất.                         │  │
│  │ ⚠️  Trả bằng chứng + confidence.                              │  │
│  │ ⚠️  Không bao giờ thực thi side effect.                       │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ TEXT2SQL PIPELINE (bên trong flow sub-agent)                  │  │
│  │                                                               │  │
│  │ Text2SQLAgent sinh SQL template                               │  │
│  │ → SQLGuardian validate:                                       │  │
│  │   • Chỉ SELECT (không DML/DDL)                                │  │
│  │   • Table trong allowlist                                     │  │
│  │   • user_id scope bắt buộc                                    │  │
│  │   • LIMIT có mặt khi cần                                      │  │
│  │ → SQLExecutor thực thi (parameterized, user_id từ auth)       │  │
│  │ → Kết quả trả về agent gọi kèm bằng chứng                     │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ GUARDIAN                                                      │  │
│  │                                                               │  │
│  │ Layer 1: HARD RULES (deterministic, quyết định ngay)          │  │
│  │   • Recipient trong reported_accounts → RED                   │  │
│  │   • Recipient risk_level = CRITICAL → RED                     │  │
│  │   • Recipient risk_level = HIGH → ORANGE tối thiểu             │  │
│  │   • Số tiền > daily_limit → BLOCK                             │  │
│  │   • Từ khóa áp lực/đe dọa → ORANGE tối thiểu                  │  │
│  │   • SQL chứa DML/DDL → REJECT                                 │  │
│  │   → Nếu trigger: BỎ QUA Layer 2, đi thẳng decision            │  │
│  │                                                               │  │
│  │ Layer 2: MODEL-BASED (chỉ khi không hard rule nào trigger)    │  │
│  │   • Anomaly Detector (số tiền/người nhận/urgency/thời gian)   │  │
│  │   • Scam Pattern Matcher (rules + LLM advisory)               │  │
│  │   • Risk Scorer → tier                                        │  │
│  │                                                               │  │
│  │ Friction Router: tier → auth requirement                      │  │
│  │   GREEN(0–0.3)  → xác nhận ngân hàng                          │  │
│  │   YELLOW(0.3–0.6) → cảnh báo + OTP/PIN                        │  │
│  │   ORANGE(0.6–0.8) → challenge + cooldown + OTP                │  │
│  │   RED(0.8–1.0) → chặn hoàn toàn, không bypass                 │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ EXECUTORS (sau guardian, tách biệt khỏi agent)                │  │
│  │                                                               │  │
│  │ • TransactionExecutor → gọi bank API (mock trong hackathon)   │  │
│  │ • CardExecutor        → khóa/mở khóa/cấp lại thẻ              │  │
│  │ • SQLExecutor         → chạy read-only query đã validate      │  │
│  │ • AccountExecutor     → thao tác tài khoản                    │  │
│  │ • LoanExecutor        → thao tác khoản vay                    │  │
│  │ • FraudReportExecutor → insert fraud_reports, cập nhật risk   │  │
│  │                                                               │  │
│  │ ⚠️  Executor CHỈ chạy sau khi Guardian approve + auth pass.   │  │
│  │ ⚠️  Idempotency key chống double-execution.                   │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ AUDIT (chỉ ghi thêm)                                          │  │
│  │ • Trace bất biến mỗi request                                  │  │
│  │ • Chuỗi delegation giữa agent được ghi lại                    │  │
│  │ • Quyết định Guardian + lý do                                 │  │
│  │ • Các cuộc gọi sub-agent + bằng chứng                         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ DATA (mock)                                                   │  │
│  │ • users.json (profile + behavioral baselines)                 │  │
│  │ • beneficiaries.json (người nhận đã lưu theo user)            │  │
│  │ • reported_accounts.json (registry scam)                      │  │
│  │ • fraud_reports (báo cáo gian lận có bằng chứng)              │  │
│  │ • reported_customers (tín hiệu risk cấp khách hàng)           │  │
│  │ • transactions.db (SQLite, pre-seeded)                        │  │
│  │ • policies/*.md (tài liệu policy có version)                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Kiến trúc Production

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
│ (repo riêng)     │ │ (repo riêng)     │ │ (repo riêng)         │
│                  │ │                  │ │                      │
│ • Transaction    │ │ • NL → SQL       │ │ • Query → answer     │
│ • Card           │ │ • Schema-aware   │ │ • Vector search      │
│ • Account        │ │ • Multi-dialect  │ │ • Citation + version │
│ • Loan           │ │                  │ │                      │
│                  │ │ ⚠️ KHÔNG thực    │ │ ⚠️ Chỉ chuẩn bị      │
│ ⚠️ KHÔNG side    │ │   thi SQL ở đây  │ │                      │
│   effect ở đây   │ │                  │ │                      │
└──────────────────┘ └──────────────────┘ └──────────────────────┘
```

**Quản trị Agent-to-Agent trong production:**

```text
• Agent Registry kiểm soát sub-agent nào mỗi Domain Agent được gọi (policy allowlist).
• Domain Agent Service chỉ gọi Sub-agent/Tool Service đã đăng ký.
• Output sub-agent bị ràng buộc schema (AgentTaskResult) và được audit.
• Không Domain Agent nào tự phát hiện hoặc gọi sub-agent chưa đăng ký.
• Mọi delegation call đi qua Agent Registry để access control + audit.
```

---

## 9. Flow TransactionAgent

### Ví dụ: "Chuyển cho Minh 2 triệu tiền ăn như tháng trước"

```text
1. Orchestrator phân loại:
   task_type = TRANSACTION
   route → TransactionAgent

2. TransactionAgent parse (LLM call):
   action = TRANSFER_MONEY
   amount = 2,000,000
   recipient_hint = "Minh"
   purpose = "tiền ăn"
   reference_time = "tháng trước"
   missing = [recipient_account, recipient_bank]

3. TransactionAgent load workflow policy:
   required_fields = [amount, recipient_account, recipient_bank]
   allowed_sub_agents = [beneficiary, transaction_history]
   confirmation_required_fields = [recipient_account, recipient_bank]

4. TransactionAgent tạo kế hoạch resolution:
   Plan: [
     {target: "beneficiary", task: "resolve_by_name",
      constraints: {name: "Minh", user_id: "u1"}},
     {target: "transaction_history", task: "resolve_previous_recipient",
      constraints: {recipient_name: "Minh", amount: 2000000,
                    purpose_hint: "tiền ăn", time_range: "last_month",
                    user_id: "u1"}}
   ]

5. Ủy quyền cho sub-agent:

   BeneficiaryAgent:
   → tra cứu người nhận đã lưu của user u1 có tên khớp "Minh"
   → kết quả: [{name: "Nguyễn Văn Minh", account: "0123456789", bank: "VCB"}]

   TransactionHistoryAgent:
   → cần tìm giao dịch cũ
   → gọi Text2SQLAgent nội bộ:
     Text2SQLAgent sinh:
       SELECT recipient_name, recipient_account, recipient_bank, amount, date, id
       FROM transactions
       WHERE user_id = :user_id
         AND recipient_name LIKE :recipient_pattern
         AND amount BETWEEN :amount_low AND :amount_high
         AND date >= :start_date
       ORDER BY date DESC LIMIT 5
     params: {recipient_pattern: "%Minh%", amount_low: 1500000,
              amount_high: 2500000, start_date: "2026-04-01"}
   → SQLGuardian validate: SELECT only ✓, table allowed ✓, user_id scoped ✓
   → SQLExecutor chạy (inject user_id từ auth context)
   → TransactionHistoryAgent trả:
     {candidates: [{
       recipient_name: "Nguyễn Văn Minh",
       account: "0123456789",
       bank: "VCB",
       matched_transaction_id: "txn_123",
       matched_amount: 2000000,
       matched_date: "2026-04-12",
       confidence: 0.86
     }]}

6. TransactionAgent merge bằng chứng:
   - BeneficiaryAgent xác nhận cùng người nhận
   - TransactionHistoryAgent cung cấp bằng chứng từ giao dịch cũ
   - Confidence tổng hợp: cao (1 candidate, cả 2 source đồng ý)

7. TransactionAgent xây draft:
   {
     amount: 2000000,
     recipient_name: "Nguyễn Văn Minh",
     recipient_account: "0123456789",
     recipient_bank: "VCB",
     note: "tiền ăn",
     resolution_source: "beneficiary + past_transaction",
     evidence_transaction_id: "txn_123"
   }

8. Guardian validate:
   - recipient không trong reported_accounts ✓
   - amount trong limit ✓
   - known recipient ✓
   - score = 0.05 → GREEN

9. FrictionRouter: cần bank_confirm

10. Response cho user:
    "Tôi tìm thấy người nhận khớp yêu cầu:
     Nguyễn Văn Minh - VCB - ****6789
     (dựa trên giao dịch 2,000,000đ ngày 12/04/2026)
     Bạn muốn chuyển 2,000,000đ cho người này?"

11. User xác nhận → POST /actions/{id}/confirm
    → TransactionExecutor.execute()
    → Audit.log(toàn bộ delegation trace)
```

### Trường hợp nhiều candidate:

```text
Nếu TransactionHistoryAgent trả 2 candidate:
  [{name: "Nguyễn Văn Minh", account: "012...", bank: "VCB", confidence: 0.65},
   {name: "Trần Đức Minh", account: "987...", bank: "TCB", confidence: 0.55}]

TransactionAgent KHÔNG tự chọn.
Response:
  "Tôi tìm thấy 2 người tên Minh từng nhận tiền ăn. Bạn muốn chuyển cho ai?
   1. Nguyễn Văn Minh - VCB - ****6789
   2. Trần Đức Minh - TCB - ****3210"
```

---

## 10. Flow CardAgent

### Ví dụ 1: "Khóa thẻ tín dụng của tôi"

```text
1. Orchestrator: task_type = CARD_OPERATION → CardAgent

2. CardAgent parse:
   operation = LOCK_CARD
   card_hint = "thẻ tín dụng"

3. CardAgent ủy quyền cho CardResolverAgent:
   task: "resolve_card"
   constraints: {user_id: "u1", card_type: "credit"}

4. CardResolverAgent:
   → tra cứu thẻ của user
   → nếu 1 thẻ credit: trả {card_id: "card_001", last4: "5678",
     card_type: "credit", status: "active", confidence: 1.0}
   → nếu nhiều: trả candidates để hỏi

5. CardAgent kiểm tra trạng thái thẻ:
   → nếu đã khóa: trả "Thẻ tín dụng ****5678 đã được khóa trước đó."
   → nếu active: tiếp tục

6. CardAgent xây draft:
   {operation: "LOCK_CARD", card_id: "card_001", last4: "5678", reason: "user_request"}

7. Guardian validate:
   - LOCK_CARD là hành động bảo vệ → friction thấp
   - Quyền sở hữu thẻ đã verify ✓
   - score = 0.0 → GREEN

8. FrictionRouter: bank_confirm (LOCK là bảo vệ, friction tối thiểu)

9. Response: "Bạn muốn khóa thẻ tín dụng ****5678?"
   → User xác nhận → CardExecutor khóa thẻ
```

### Ví dụ 2: "Mở lại thẻ Visa đuôi 1234"

```text
1. Orchestrator: task_type = CARD_OPERATION → CardAgent

2. CardAgent parse:
   operation = UNLOCK_CARD
   card_hint = "Visa đuôi 1234"

3. CardResolverAgent resolve:
   → match theo brand "Visa" + last4 "1234"
   → trả {card_id: "card_002", last4: "1234", brand: "Visa",
     status: "locked", confidence: 1.0}

4. CardAgent xây draft:
   {operation: "UNLOCK_CARD", card_id: "card_002", last4: "1234"}

5. Guardian validate:
   - UNLOCK_CARD cần auth cao hơn LOCK
   - score = 0.35 → YELLOW

6. FrictionRouter: cần OTP

7. Response: "Để mở khóa thẻ Visa ****1234, vui lòng nhập mã OTP."
   → User nhập OTP → verify → CardExecutor mở khóa thẻ
```

### Policy friction cho thao tác thẻ:

| Thao tác | Friction mặc định | Lý do |
|----------|-------------------|-------|
| LOCK_CARD | GREEN (xác nhận) | Hành động bảo vệ, rủi ro thấp |
| UNLOCK_CARD | YELLOW (OTP) | Cho phép chi tiêu, rủi ro trung bình |
| ACTIVATE_CARD | YELLOW (OTP) | Kích hoạt thẻ mới |
| REISSUE_CARD | YELLOW (OTP) | Xác minh địa chỉ nếu cần |
| CHANGE_CARD_LIMIT | ORANGE (challenge + OTP) | Ảnh hưởng lớn đến chi tiêu |
| VIEW_CARD_INFO | GREEN (đã auth session, output bị mask) | Chỉ đọc |

---

## 10b. Flow FraudReportAgent

### Ví dụ: "Tôi muốn báo cáo số tài khoản 123456789 tại ngân hàng VCB lừa đảo tôi"

```text
1. Orchestrator phân loại:
   task_type = FRAUD_REPORT
   route → FraudReportAgent

2. FraudReportAgent parse (LLM extract):
   operation = REPORT_FRAUD_ACCOUNT
   reported_account_no = "123456789"
   reported_bank_code = "VCB"
   reason_hint = "lừa đảo"

3. FraudReportAgent ủy quyền cho FraudVerificationAgent:
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
   → Nếu 0 kết quả: trả {status: "no_relationship"}
   → Nếu có kết quả: trả {status: "verified", transactions: [...]}

5. Nếu no_relationship:
   FraudReportAgent trả:
   "Không tìm thấy giao dịch nào giữa bạn và tài khoản 123456789 (VCB).
    Chưa thể tạo báo cáo gian lận chính thức."
   → Kết thúc flow.

6. Nếu verified (có giao dịch):
   FraudReportAgent hiển thị giao dịch khớp:
   "Tôi tìm thấy 2 giao dịch đến tài khoản này:
    1. 15,000,000đ ngày 20/05/2026 - 'Đặt cọc mua hàng'
    2. 5,000,000đ ngày 22/05/2026 - 'Chuyển thêm phí ship'
    Bạn muốn report giao dịch nào? (1, 2, hoặc cả hai)"

7. User chọn → FraudReportAgent hỏi context gian lận (multi-turn):

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

8. FraudReportAgent tính confidence_score:
   +40: có giao dịch đã xác minh
   +20: giao dịch trong 30 ngày
   +15: fraud_type rõ ràng (SHOPPING_SCAM)
   +15: aftermath rõ ràng (BLOCKED_CONTACT)
   +10: có bằng chứng
   = 100 → CRITICAL confidence

9. FraudReportAgent xây fraud_report_draft:
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

10. Guardian validate:
    - FRAUD_REPORT là hành động bảo vệ
    - confidence_score >= 40 (có bằng chứng giao dịch thật)
    - score = 0.0 → GREEN

11. FrictionRouter: bank_confirm (hành động bảo vệ, friction tối thiểu)

12. User xác nhận → FraudReportExecutor:
    a. INSERT fraud_reports (status = VALIDATED)
    b. UPSERT reported_accounts:
       - Tăng valid_report_count, unique_reporter_count
       - Cộng vào total_reported_amount
       - Tính lại risk_score và risk_level
    c. NẾU cùng ngân hàng (reported_bank = bank của mình):
       - Tra cứu customer bằng account → lấy cif_no
       - UPSERT reported_customers
    d. INSERT fraud_decisions log

13. Response:
    "Báo cáo gian lận đã được ghi nhận. Tài khoản 123456789 (VCB) đã được
     đánh dấu để bảo vệ người dùng khác. Cảm ơn bạn đã báo cáo."

14. Audit.log(toàn bộ fraud report trace)
```

### Transaction Screening (tích hợp với Guardian):

Khi bất kỳ hành động TRANSFER nào được Guardian đánh giá:

```text
Guardian.evaluate(draft):
  1. Kiểm tra reported_accounts:
     SELECT risk_level, valid_report_count, status
     FROM reported_accounts
     WHERE account_no = draft.recipient_account
       AND bank_code = draft.recipient_bank
       AND status = 'ACTIVE'

  2. Nếu tìm thấy:
     - risk_level = LOW (1-2 report) → WARN (+0.3 vào risk_score)
     - risk_level = MEDIUM (3-4 report) → STEP_UP_AUTH (+0.5)
     - risk_level = HIGH (5+ report) → ORANGE tối thiểu (+0.7)
     - risk_level = CRITICAL (đã xác nhận) → RED (chặn hoàn toàn)

  3. Kiểm tra reported_customers (nếu cùng ngân hàng):
     SELECT risk_level FROM reported_customers
     WHERE cif_no = (SELECT cif_no FROM accounts WHERE account_no = draft.recipient_account)

  4. Ghi fraud_decisions:
     INSERT INTO fraud_decisions (decision, risk_level, reason_codes, ...)

  5. Nếu quyết định WARN:
     Message: "⚠️ Cảnh báo: Tài khoản này từng bị báo cáo lừa đảo bởi
              người dùng khác. Bạn có chắc chắn muốn tiếp tục?"
```

### Quy tắc tính risk_level (hackathon):

```text
reported_accounts.risk_level:
  1 báo cáo hợp lệ                    → LOW
  2 báo cáo hợp lệ                    → MEDIUM
  3-4 báo cáo từ 3+ user khác nhau    → HIGH
  5+ báo cáo HOẶC đã xác nhận         → CRITICAL

reported_customers.risk_level:
  1 tài khoản bị report               → WATCH
  2+ tài khoản bị report              → FROZEN (tự đóng băng)
  Xác nhận gian lận trên bất kỳ TK    → BLOCKED
```

---

## 11. Flow AccountAgent

### Ví dụ: "Thêm người nhận mới tên Hà, số tài khoản 111222333, ngân hàng VPBank"

```text
1. Orchestrator: task_type = ACCOUNT_OPERATION → AccountAgent

2. AccountAgent parse:
   operation = MANAGE_BENEFICIARY
   sub_operation = ADD
   beneficiary_name = "Hà"
   beneficiary_account = "111222333"
   beneficiary_bank = "VPBank"

3. AccountAgent validate đầy đủ:
   - Tất cả trường bắt buộc có ✓

4. AccountAgent xây draft:
   {operation: "ADD_BENEFICIARY", name: "Hà",
    account: "111222333", bank: "VPBank"}

5. Guardian validate:
   - Account không trong danh sách report ✓
   - score = 0.1 → GREEN

6. FrictionRouter: OTP (thêm beneficiary cần OTP)

7. Response + OTP → AccountExecutor lưu beneficiary
```

### Policy friction cho thao tác tài khoản:

| Thao tác | Friction mặc định |
|----------|-------------------|
| VIEW_ACCOUNT_INFO | GREEN (không auth) |
| MANAGE_BENEFICIARY (thêm) | YELLOW (OTP) |
| MANAGE_BENEFICIARY (xóa) | GREEN (xác nhận) |
| UPDATE_ACCOUNT_INFO | YELLOW (OTP) |
| OPEN_ACCOUNT | ORANGE (xác minh đầy đủ) |
| CLOSE_ACCOUNT | RED (cần đến chi nhánh / flow đặc biệt) |

---

## 12. Flow LoanAgent

### Ví dụ: "Kiểm tra trạng thái khoản vay của tôi"

```text
1. Orchestrator: task_type = LOAN_OPERATION → LoanAgent

2. LoanAgent parse:
   operation = CHECK_LOAN_STATUS

3. LoanAgent ủy quyền cho LoanInfoAgent:
   task: "get_active_loans"
   constraints: {user_id: "u1"}

4. LoanInfoAgent trả:
   [{loan_id: "loan_001", type: "personal", principal: 50000000,
     remaining: 35000000, monthly_payment: 5200000, next_due: "2026-06-01",
     status: "active"}]

5. LoanAgent xây response (chỉ đọc, không cần draft):
   "Khoản vay cá nhân của bạn:
    - Gốc: 50,000,000đ
    - Còn lại: 35,000,000đ
    - Trả hàng tháng: 5,200,000đ
    - Kỳ tiếp theo: 01/06/2026"

6. Không cần Guardian/Friction vì chỉ đọc.
   Tuy nhiên, vẫn cần validate ownership/scope trước khi trả dữ liệu.
```

### Ví dụ: "Trả trước 10 triệu khoản vay"

```text
1. LoanAgent parse: operation = REPAY_LOAN, amount = 10,000,000

2. LoanInfoAgent resolve khoản vay active

3. LoanAgent xây draft:
   {operation: "REPAY_LOAN", loan_id: "loan_001", amount: 10000000,
    type: "early_repayment"}

4. Guardian validate → YELLOW (ảnh hưởng tài chính)

5. OTP → LoanExecutor xử lý trả trước
```

### Policy friction cho thao tác khoản vay:

| Thao tác | Friction mặc định |
|----------|-------------------|
| VIEW_LOAN_INFO | GREEN (không auth) |
| CHECK_LOAN_STATUS | GREEN (không auth) |
| REPAY_LOAN | YELLOW (OTP) |
| APPLY_LOAN | ORANGE (xác minh đầy đủ + tài liệu) |

---

## 13. Flow DataQueryAgent

### Ví dụ: "Tháng này tôi tiêu bao nhiêu cho ăn uống?"

```text
1. Orchestrator: task_type = DATA_QUERY → DataQueryAgent

2. DataQueryAgent lên kế hoạch query:
   query_type = "spending_summary"
   filters: {category: "food", time_range: "this_month"}

3. DataQueryAgent ủy quyền cho Text2SQLAgent:
   task: "generate_query"
   constraints: {
     intent: "sum spending by category",
     category: "food/dining",
     time_range: "2026-05-01 to 2026-05-19",
     user_id: "u1"  // chỉ để scoping, không trong SQL params
   }

4. Text2SQLAgent sinh:
   sql_template: "SELECT SUM(amount) as total, COUNT(*) as count
                  FROM transactions
                  WHERE user_id = :user_id
                    AND category IN (:categories)
                    AND date >= :start_date AND date <= :end_date
                    AND transaction_type = 'debit'
                  LIMIT 1"
   params: {categories: ["food", "dining"], start_date: "2026-05-01",
            end_date: "2026-05-19"}

5. SQLGuardian validate:
   - Chỉ SELECT ✓
   - Table "transactions" trong allowlist ✓
   - user_id scope có ✓
   - LIMIT có ✓
   - Không subquery đến table không phép ✓

6. SQLExecutor thực thi (inject user_id từ auth context):
   LƯU Ý: Text2SQL có thể sinh :user_id placeholder, nhưng SQLExecutor
   luôn inject user_id thật từ auth context. Mọi giá trị user_id
   trong params LLM sinh ra đều bị bỏ qua.
   Kết quả: {total: 8500000, count: 23}

7. DataQueryAgent tóm tắt:
   "Tháng này bạn đã chi 8,500,000đ cho ăn uống (23 giao dịch)."

8. Không cần Guardian/Friction (chỉ đọc, không side effect).
   Tuy nhiên, SQLGuardian validation là BẮT BUỘC cho mọi SQL sinh ra.

9. Audit.log(query đã thực thi, không log sensitive data)
```

### DATA_QUERY là use case chính của Text2SQL.

Ví dụ khác:
- "Tháng trước thu nhập bao nhiêu?" → SUM income transactions
- "Ai gửi tiền cho tôi tuần này?" → LIST incoming transfers
- "Chi tiêu thẻ Visa tháng 4?" → SUM card transactions by card
- "So sánh chi tiêu tháng này với tháng trước?" → comparative query

---

## 14. Flow QAAgent

### Ví dụ: "Lãi suất tiết kiệm 6 tháng là bao nhiêu?"

```text
1. Orchestrator: task_type = QA → QAAgent

2. QAAgent ủy quyền cho PolicyRetrieverAgent:
   task: "retrieve_policy"
   constraints: {
     topic: "savings_interest_rate",
     term: "6_months",
     product_type: "savings"
   }

3. PolicyRetrieverAgent:
   → Tìm tài liệu policy (vector search hoặc keyword match)
   → Trả:
     {chunks: ["Lãi suất tiết kiệm kỳ hạn 6 tháng: 5.5%/năm (áp dụng từ 01/05/2026)"],
      policy_version: "v2026.05",
      effective_date: "2026-05-01",
      source: "policies/savings_rates.md",
      confidence: 0.95}

4. QAAgent sinh câu trả lời có trích dẫn:
   "Lãi suất tiết kiệm kỳ hạn 6 tháng hiện tại là 5.5%/năm.
    (Theo biểu lãi suất v2026.05, áp dụng từ 01/05/2026)"

5. Validation trích dẫn/grounding (BẮT BUỘC cho QA):
   - Câu trả lời khớp chunk truy xuất ✓
   - Version/date được include ✓
   - Không hallucinate lãi suất ✓

6. Không cần Guardian/Friction (thông tin, không side effect).
   Tuy nhiên, citation/grounding validation là BẮT BUỘC cho mọi QA answer.
```

### Ràng buộc QAAgent:
- Phải trích dẫn source policy document và version
- Không được hallucinate lãi suất, phí, hoặc chi tiết sản phẩm
- Nếu không tìm thấy policy khớp → nói "Tôi không tìm thấy thông tin này" (không đoán)
- Production: vector DB + semantic search trên versioned policy docs

---

## 15. Ranh giới An toàn

```text
┌──────────────────────────────────────────────────────────────────┐
│ THỰC THI RANH GIỚI AN TOÀN                                       │
│                                                                  │
│ 1. LLM chuẩn bị, không bao giờ thực thi.                         │
│    → Mọi output LLM là draft/template. Không side effect.        │
│                                                                  │
│ 2. Domain Agent lên kế hoạch và ủy quyền, không thực thi.        │
│    → TransactionAgent xây draft, không gọi bank API.             │
│                                                                  │
│ 3. Sub-agent chỉ truy xuất/chuẩn bị.                             │
│    → TransactionHistoryAgent trả candidates, không decisions.    │
│                                                                  │
│ 4. Guardian là external và có quyền tối cao.                     │
│    → Không agent nào bypass. Output Guardian bất biến.           │
│                                                                  │
│ 5. Executor là tầng side-effect DUY NHẤT.                        │
│    → Chạy sau Guardian approval + user auth.                     │
│                                                                  │
│ 6. Text2SQL được bảo vệ và chỉ đọc.                              │
│    → SQLGuardian validate mọi query sinh ra.                     │
│    → Không DML/DDL. Không query unscoped. Không execute          │
│      mà không validate.                                          │
│                                                                  │
│ 7. Trường giao dịch quan trọng phải có bằng chứng.               │
│    → recipient_account resolve từ history/beneficiary            │
│      phải gồm source_transaction_id + confidence.                │
│                                                                  │
│ 8. Confidence thấp → hỏi user.                                   │
│    → Nếu confidence < threshold hoặc nhiều candidate,            │
│      Domain Agent BẮT BUỘC hỏi clarification.                    │
│                                                                  │
│ 9. Hành động high-risk cần step-up auth.                         │
│    → GREEN=confirm, YELLOW=OTP, ORANGE=challenge+OTP,            │
│      RED=blocked (không bypass).                                 │
│                                                                  │
│ 10. Audit log toàn bộ agent trace.                               │
│     → Mọi delegation, mọi sub-agent call, mọi quyết định         │
│       Guardian đều được ghi. Chỉ ghi thêm, không xóa.            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 16. API Endpoints

```text
POST /chat                              # Endpoint hội thoại chính
     Request:  ChatRequest {user_id, message, session_id}
     Response: ChatResponse {status, response, risk_tier, pending_action_id,
               requires_auth, action_preview, audit_id}

POST /actions/{action_id}/confirm       # Xác nhận ngân hàng (GREEN tier)
     Request:  ConfirmRequest {user_id}
     Response: ActionResponse {status: "executed", message, execution_id}
     Routing:  PendingAction.executor_type xác định Executor nào được gọi

POST /actions/{action_id}/otp           # Xác thực OTP (YELLOW/ORANGE tier)
     Request:  OTPRequest {user_id, otp_code}
     Response: ActionResponse {status: "executed", message, execution_id}
     Routing:  PendingAction.executor_type xác định Executor nào được gọi

GET  /health                            # Health check
     Response: {status: "ok"}
```

Error responses:
- 404: action_id không tìm thấy
- 401: user_id không khớp
- 403: action bị block / auth type không khớp
- 409: action đã execute (idempotency)

---

## 17. Luồng dữ liệu mỗi Request

```text
1. User gửi tin nhắn → POST /chat
2. Orchestrator phân loại intent (1 LLM call → chỉ task_type)
3. Orchestrator route đến Domain Agent theo task_type
4. Domain Agent thực hiện:
   4a. Parse tin nhắn user (LLM extract structured fields)
   4b. Phát hiện trường thiếu
   4c. Lên kế hoạch resolution: gọi sub-agent nào
   4d. Ủy quyền cho sub-agent (structured task):
       ↳ Sub-agent có thể gọi Text2SQL → SQLGuardian → SQLExecutor nội bộ
       ↳ Sub-agent trả candidates + evidence + confidence
   4e. Nếu confidence thấp / nhiều candidate → trả {status: clarification_needed}
   4f. Nếu confident → xây action draft → trả cho agent runtime
   4g. Agent runtime gửi draft cho Guardian:
       ↳ Layer 1: hard rules (block ngay nếu trigger)
       ↳ Layer 2: scoring (nếu không hard rule)
       ↳ Nếu BLOCK → trả {status: blocked} ngay
   4h. Agent runtime gọi FrictionRouter: risk tier → auth requirement
   4i. PendingActionStore lưu action:
       ↳ Trả {status: pending_auth, pending_action_id, preview}
5. User xác nhận/OTP → POST /actions/{id}/confirm hoặc /otp
6. Executor chạy sau khi auth verified
7. Audit.log(toàn bộ agent delegation trace)
8. Response compiled → Frontend
```

---

## 18. Cấu trúc Folder

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
│   ├── models.py                        # Pydantic schemas (tất cả models)
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
│   │   │
│   │   └── sub_agents/                 # Sub-agents (chỉ truy xuất/chuẩn bị)
│   │       ├── __init__.py
│   │       ├── recipient_resolution.py # RecipientResolutionAgent
│   │       ├── transaction_history.py  # TransactionHistoryAgent
│   │       ├── beneficiary.py          # BeneficiaryAgent
│   │       ├── card_resolver.py        # CardResolverAgent
│   │       ├── account_profile.py      # AccountProfileAgent
│   │       ├── loan_info.py            # LoanInfoAgent
│   │       ├── policy_retriever.py     # PolicyRetrieverAgent
│   │       └── text2sql.py             # Text2SQLAgent (chỉ sinh SQL)
│   │
│   ├── services/                        # Infrastructure services
│   │   ├── __init__.py
│   │   ├── guardian.py                 # Guardian: hard rules + scoring → decision
│   │   ├── sql_guardian.py             # SQLGuardian: validate SQL queries
│   │   ├── friction.py                 # FrictionRouter: tier → auth requirement
│   │   ├── session.py                  # SessionStore: pending actions
│   │   ├── agent_runtime.py            # AgentRuntime: draft → Guardian → Friction → store
│   │   └── audit.py                    # AuditLogger: append-only trace
│   │
│   ├── executors/                       # Tầng side-effect (chỉ sau Guardian)
│   │   ├── __init__.py
│   │   ├── transaction.py             # TransactionExecutor
│   │   ├── card.py                    # CardExecutor
│   │   ├── account.py                 # AccountExecutor
│   │   ├── loan.py                    # LoanExecutor
│   │   ├── fraud_report.py            # FraudReportExecutor
│   │   └── sql.py                     # SQLExecutor (chỉ đọc)
│   │
│   ├── policies/                        # Workflow policies (agent được làm gì)
│   │   ├── __init__.py
│   │   ├── transfer.py                # TransferWorkflowPolicy
│   │   ├── card.py                    # CardWorkflowPolicy
│   │   └── base.py                    # BaseWorkflowPolicy
│   │
│   ├── prompts/                         # LLM prompt templates
│   │   ├── __init__.py
│   │   ├── intent.py                  # Phân loại intent
│   │   ├── transaction.py             # Transaction entity extraction
│   │   ├── card.py                    # Card operation extraction
│   │   └── data_query.py             # Data query understanding
│   │
│   └── data/                            # Mock data (hackathon)
│       ├── reported_accounts.json      # Registry scam
│       ├── beneficiaries.json          # Người nhận đã lưu theo user
│       ├── users.json                  # User profiles + baselines
│       ├── cards.json                  # Thẻ user
│       ├── loans.json                  # Khoản vay user
│       └── policies/                   # Tài liệu policy cho QA
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

File bắt buộc cho MUST HAVE scope:

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

File mở rộng (SHOULD HAVE):

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

File bonus:

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
    response: str                      # Ngôn ngữ tự nhiên cho user
    risk_tier: Optional[str] = None    # GREEN | YELLOW | ORANGE | RED
    requires_auth: Optional[str] = None  # bank_confirm | otp | challenge | blocked
    pending_action_id: Optional[str] = None
    action_preview: Optional[dict] = None  # preview chung cho mọi domain (transaction/card/loan/...)
    audit_id: Optional[str] = None

class ActionResponse(BaseModel):
    status: Literal["executed"]
    message: str
    execution_id: Optional[str] = None  # ID chung cho action đã execute (txn/card/account/loan)

# === Intent ===

class IntentResult(BaseModel):
    task_type: Literal[
        "QA", "DATA_QUERY", "TRANSACTION",
        "CARD_OPERATION", "ACCOUNT_OPERATION", "LOAN_OPERATION",
        "FRAUD_REPORT"
    ]
    operation: Optional[str] = None   # TRANSFER_MONEY, LOCK_CARD, v.v.
    risk_hint: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    route: Optional[str] = None       # domain agent route hint
    confidence: float
    reason: str

# === Giao tiếp Agent-to-Agent ===

class AgentTask(BaseModel):
    task_type: str             # "resolve_recipient", "search_history", "resolve_card"
    constraints: dict          # scoped input cho sub-agent
    allowed_output: list[str]  # ràng buộc schema cho response

class AgentTaskResult(BaseModel):
    candidates: list[dict]     # kết quả khớp
    evidence: list[str]        # transaction_ids, source references
    confidence: float          # 0.0 – 1.0
    source_agent: str          # sub-agent nào tạo ra

# === Domain Agent Output ===

class DomainAgentOutput(BaseModel):
    status: str                # draft_ready | clarification_needed | info_response
    action_draft: Optional[dict] = None
    clarification_message: Optional[str] = None
    info_response: Optional[str] = None
    delegation_trace: list[dict] = Field(default_factory=list)  # [{agent, task, result_summary}]

# === Guardian ===

class GuardianDecision(BaseModel):
    decision: Literal["ALLOW", "BLOCK"]   # Guardian chỉ quyết định allow/block
    risk_tier: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    risk_score: float          # 0.0 – 1.0
    triggered_by: Literal["HARD_RULE", "MODEL"]
    reasons: list[str]
    hard_rule_name: Optional[str] = None
    # LƯU Ý: Guardian KHÔNG quyết định auth type.
    # FrictionRouter map risk_tier → auth_type riêng.

# === Friction ===

class FrictionResult(BaseModel):
    auth_type: str             # bank_confirm | otp | challenge | blocked
    message: str               # giải thích cho user

# === Pending Action ===

class PendingAction(BaseModel):
    action_id: str
    user_id: str
    session_id: str
    action_type: str           # TRANSACTION | CARD_OPERATION | ACCOUNT_OPERATION | LOAN_OPERATION
    operation: Optional[str] = None  # TRANSFER_MONEY, LOCK_CARD, v.v.
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

## 20. Ma trận Guardian Decision

| Scenario | Layer 1 (Hard Rules) | Layer 2 (Scoring) | Risk Tier | Auth |
|----------|---------------------|-------------------|-----------|------|
| Người nhận quen, số tiền nhỏ | — | score < 0.3 | GREEN | confirm |
| Người nhận lạ, số tiền trung bình | — | 0.3 ≤ score < 0.6 | YELLOW | OTP |
| Phát hiện từ khóa áp lực | ORANGE tối thiểu | score 0.6–0.8 | ORANGE | challenge + OTP |
| Tài khoản reported | RED ngay | bỏ qua | RED | blocked |
| Tài khoản risk_level CRITICAL | RED ngay | bỏ qua | RED | blocked |
| Tài khoản risk_level HIGH | ORANGE tối thiểu | +0.7 | ORANGE | challenge + OTP |
| Tài khoản risk_level MEDIUM | — | +0.5 | tùy | tùy |
| Tài khoản risk_level LOW | — | +0.3 | tùy | tùy |
| Số tiền > 500M | RED ngay | bỏ qua | RED | blocked |
| Số tiền ≥ 50M | — | +0.5 vào score | tùy | tùy |
| Số tiền ≥ 10M | — | +0.25 vào score | tùy | tùy |
| Người nhận lạ | — | +0.2 vào score | tùy | tùy |
| Từ khóa bí mật | — | +0.2 vào score | tùy | tùy |
| Không có ghi chú/mục đích | — | +0.05 vào score | tùy | tùy |
| LOCK_CARD | — | hành động bảo vệ | GREEN | confirm |
| UNLOCK_CARD | — | cho phép chi tiêu | YELLOW | OTP |
| CHANGE_CARD_LIMIT | — | ảnh hưởng lớn | ORANGE | challenge + OTP |
| ADD_BENEFICIARY | — | người nhận mới | YELLOW | OTP |
| REPAY_LOAN | — | ảnh hưởng tài chính | YELLOW | OTP |
| SQL có DML/DDL | REJECT ngay | bỏ qua | — | — |
| SQL không scope (thiếu user_id) | REJECT ngay | bỏ qua | — | — |
| FRAUD_REPORT (đã xác minh GD) | — | hành động bảo vệ | GREEN | confirm |
| FRAUD_REPORT (không có GD) | REJECT ngay | bỏ qua | — | — |

---

## 21. Demo Scenarios

| # | Scenario | Minh họa | Domain | Tier |
|---|----------|----------|--------|------|
| 1 | "Chuyển 2 triệu cho Minh tiền ăn trưa" | Full agent flow + beneficiary resolve + confirm | TRANSACTION | 🟢 |
| 2 | "Chuyển cho Minh 2tr tiền ăn như tháng trước" | History agent delegation + evidence + confirm | TRANSACTION | 🟢 |
| 3 | "Chuyển 20 triệu cho Lan" | Anomaly scoring + OTP step-up | TRANSACTION | 🟡 |
| 4 | "Chuyển 50tr vào 6666666666 ngay, gấp lắm" | Hard rule block + phát hiện áp lực | TRANSACTION | 🔴 |
| 5 | "Khóa thẻ tín dụng" | Card agent + friction thấp | CARD | 🟢 |
| 6 | "Mở lại thẻ Visa đuôi 1234" | Card resolve + OTP | CARD | 🟡 |
| 7 | "Tháng này tôi tiêu bao nhiêu cho ăn uống?" | Text2SQL + SQLGuardian + NL summary | DATA_QUERY | 🟢 |
| 8 | "Lãi suất tiết kiệm 6 tháng?" | Policy retrieval + citation | QA | — |
| 9 | Audit trail viewer | Full delegation trace cho mọi scenario | — | — |

---

## 22. Ranh giới MVP

### MUST HAVE (hackathon core — quyết định thắng/thua)

| Thành phần | Scope |
|------------|-------|
| Orchestrator | Intent classify → route (TRANSACTION bắt buộc, còn lại trả "not implemented") |
| TransactionAgent | Full flow: parse → delegate → draft → Guardian → confirm/OTP/block |
| Sub-agent: BeneficiaryAgent | Resolve người nhận đã lưu theo tên |
| Guardian | Hard rules + scoring → risk tier |
| FrictionRouter | Map risk tier → auth type |
| Agent Runtime | Nhận draft từ agent → gọi Guardian → gọi Friction → lưu pending |
| TransactionExecutor (mock) | Execute sau confirm/OTP |
| Demo GREEN | Người nhận quen → confirm → execute |
| Demo RED | Reported account → block |
| Demo YELLOW | Số tiền lớn → OTP |
| Audit | Full delegation trace được log |

### SHOULD HAVE (tăng sức mạnh demo đáng kể)

| Thành phần | Scope |
|------------|-------|
| TransactionHistoryAgent | Tìm giao dịch cũ để resolve người nhận |
| Text2SQL pipeline | DataQueryAgent → Text2SQL → SQLGuardian → SQLExecutor |
| CardAgent | LOCK/UNLOCK flow + CardResolverAgent + CardExecutor |
| Demo ORANGE | Từ khóa áp lực → challenge |
| Frontend | Streamlit với confirm/OTP/block modals |
| Clarification nhiều candidate | "2 người tên Minh" → user chọn |

### BONUS (nếu còn thời gian)

| Thành phần | Scope |
|------------|-------|
| QAAgent + PolicyRetriever | Câu hỏi policy có citation + grounding validation |
| AccountAgent | MANAGE_BENEFICIARY, VIEW_ACCOUNT_INFO |
| LoanAgent | CHECK_LOAN_STATUS, REPAY_LOAN |
| Agent delegation trace viewer | Hiển thị chuỗi sub-agent call trong UI |

---

## 23. Migration Hackathon → Production

| Thành phần | Hackathon | Production | Migration |
|------------|-----------|------------|-----------|
| Domain Agents | Class local, cùng process | Service riêng (gRPC/HTTP) | Extract thành service, giữ interface |
| Sub-agents | Class local | Microservice nội bộ | Cùng pattern extraction |
| Agent Registry | Dict hardcoded | Database + config service | Thêm DB adapter |
| Workflow Policy | Python dataclass | Policy-as-code + hot reload | Thêm policy engine |
| Guardian | Rule-based + simple scoring | ML anomaly model + fraud classifier | Train model, giữ interface |
| Text2SQL | 1 LLM call | Fine-tuned model + schema cache | Swap model, giữ pipeline |
| SQLGuardian | Regex + simple AST | sqlglot full AST + query plan analysis | Upgrade validation |
| Auth | Mock OTP="123456" | Bank IAM + biometric + device binding | Replace auth adapter |
| Session | In-memory dict | Redis cluster | Swap store |
| Audit | JSON file | Kafka → Elasticsearch | Replace logger |
| Executor | Mock (return success) | Real bank API + payment gateway | Real impl |
| Data | JSON files + SQLite | PostgreSQL + read replicas | Migration scripts |
| Frontend | Streamlit | React + bank-native SDK | Full rewrite |
| Deployment | docker-compose | Kubernetes + Helm | New infra layer |
| Monitoring | Print logs | Prometheus + Grafana + PagerDuty | Thêm instrumentation |
| Agent tracing | In-memory trace list | OpenTelemetry + Jaeger | Thêm spans |

---

## 24. Quyết định Thiết kế Quan trọng

| Quyết định | Lựa chọn | Lý do |
|------------|----------|-------|
| Agent-to-agent thay vì static workflow | Domain Agent lên kế hoạch + ủy quyền | Linh hoạt cho edge case, mở rộng dễ |
| Orchestrator mỏng | Chỉ classify + route | Domain logic ở domain agent, không orchestrator |
| Sub-agent dùng structured task | AgentTask schema, không free-form | Giảm mơ hồ, ràng buộc output, tăng safety |
| Text2SQL là sub-agent, không top-level | Bên trong TransactionHistoryAgent / DataQueryAgent | Business semantics do domain agent xử lý |
| Resolution dựa trên bằng chứng | Sub-agent trả source + confidence | Cho phép confidence-gated confirmation |
| Policy object kiểm soát agent | TransferWorkflowPolicy định nghĩa allowed actions | Agent bị quản trị, không tự trị |
| Guardian external với agent | Agent không thể tự approve | Ranh giới safety rõ ràng |
| Xác nhận bắt buộc cho trường resolved | recipient_account từ history → phải confirm | An toàn hơn tiện lợi cho dữ liệu giao dịch |
| Mọi money-moving cần explicit user approval | GREEN cần bank confirm; tier cao hơn cần OTP/challenge | Không di chuyển tiền ngầm |
| Executor tách biệt hoàn toàn | Tầng side-effect duy nhất | Ranh giới audit rõ ràng |
| Audit gồm delegation trace | Mọi sub-agent call được ghi | Full explainability |
| LLM calls có giới hạn | Intent(1) + parse(1) + sub-agent LLM nếu cần | Latency dự đoán được |
| Trường giao dịch KHÔNG BAO GIỜ tự sửa | Thiếu → clarification | An toàn |
| Hành động bảo vệ (LOCK) friction thấp | User LOCK là tự bảo vệ | Không thêm friction cho safety action |
| UNLOCK/ACTIVATE friction cao hơn | Cho phép chi tiêu/truy cập | Rủi ro cao hơn khóa |
