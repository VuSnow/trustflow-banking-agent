from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from backend.agents.registry import AgentRegistry
from backend.agents.sub_agents.fraud_report import FraudVerificationAgent
from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import (
    AgentTask,
    DomainAgentOutput,
    FraudReportDetails,
    FraudReportDraft,
    FraudReportExtraction,
)
from backend.prompts.fraud_report import (
    FRAUD_REPORT_SYSTEM_PROMPT,
    FRAUD_REPORT_USER_TEMPLATE,
)
from backend.services.fraud_report import (
    FraudConfidenceScorer,
    FraudReportSessionStore,
    FraudReportStore,
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "reported_account_no",
    "reported_bank_code",
    "contact_channel",
    "aftermath",
    "reason_text",
    "has_evidence",
)

CONTEXT_ORDER = (
    "contact_channel",
    "aftermath",
    "reason_text",
    "has_evidence",
)

FIRST_INTAKE_FIELDS = [
    "reported_account_no",
    "reported_bank_code",
    "transaction_ref",
    "contact_channel",
    "aftermath",
    "reason_text",
    "has_evidence",
]


class FraudReportAgent:
    """Draft-only domain agent for FRAUD_REPORT intent."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.store = FraudReportStore()
        self.registry = AgentRegistry()
        self.registry.register("fraud_verification", FraudVerificationAgent())
        self.session_store = FraudReportSessionStore()
        self.scorer = FraudConfidenceScorer()

    async def run(self, message: str, user_id: str, session_id: str) -> DomainAgentOutput:
        trace: list[str] = []
        current_state = self.session_store.get(user_id, session_id)
        current_fields = current_state.fields if current_state else {}

        logger.info(
            "[FRAUD] start user=%s session=%s has_session=%s",
            user_id,
            session_id,
            bool(current_state),
        )

        extraction = await self._extract_entities(message, current_fields)
        trace.append("extract_fraud_report")

        if extraction.operation == "CHECK_FRAUD_STATUS":
            return DomainAgentOutput(
                status="info_response",
                info_response=(
                    "Hiện tại hệ thống chỉ hỗ trợ tạo bản nháp báo cáo lừa đảo, "
                    "chưa có tra cứu trạng thái báo cáo đã gửi."
                ),
                response_data={
                    "operation": "CHECK_FRAUD_STATUS",
                    "supported": False,
                    "reason": "fraud report persistence is not implemented in this phase",
                },
                delegation_trace=trace,
            )

        merged_fields = self._merge_fields(current_fields, extraction, message)
        state = self.session_store.merge(user_id, session_id, merged_fields)
        trace.append("merge_session_state")

        if state.selected_transaction_ref and not state.fields.get("transaction_ref"):
            state.fields["transaction_ref"] = state.selected_transaction_ref

        selection_result = await self._maybe_select_candidate_transaction(
            message=message,
            user_id=user_id,
            session_id=session_id,
            state=state,
            trace=trace,
        )
        if selection_result is not None:
            return selection_result

        # Duplicate detection: check if user already reported this account
        reported_account_no = state.fields.get("reported_account_no")
        if reported_account_no:
            existing_reports = self.store.find_user_existing_reports(user_id, reported_account_no)
            if existing_reports:
                tx_ref = state.fields.get("transaction_ref")
                exact_dup = any(
                    r.get("transaction_ref") == tx_ref
                    for r in existing_reports
                    if tx_ref
                )
                if exact_dup:
                    self.session_store.clear(user_id, session_id)
                    trace.append("duplicate_report_rejected")
                    return DomainAgentOutput(
                        status="info_response",
                        info_response=(
                            "Bạn đã báo cáo tài khoản này với cùng giao dịch trước đó. "
                            "Nếu có thông tin mới, vui lòng liên hệ hotline ngân hàng."
                        ),
                        response_data={
                            "operation": "REPORT_FRAUD",
                            "rejected": True,
                            "reason": "duplicate_report",
                            "existing_reports": [
                                {"report_id": str(r.get("report_id")), "status": r.get("status")}
                                for r in existing_reports
                            ],
                            "trace": trace,
                        },
                        delegation_trace=trace,
                    )

        missing_fields = self._missing_required_fields(state.fields)

        if missing_fields:
            next_question = self._next_question(state, missing_fields)
            self.session_store.set_stage(user_id, session_id, next_question["stage"])
            self.session_store.set_last_prompt(user_id, session_id, next_question["question"])
            if current_state is None:
                clarification_message = self._build_initial_intake_message()
            else:
                clarification_message = next_question["message"]
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=clarification_message,
                response_data={
                    "operation": "REPORT_FRAUD",
                    "collected_fields": state.fields,
                    "missing_fields": missing_fields,
                    "stage": next_question["stage"],
                    "next_question": next_question,
                    "candidate_transactions": state.candidate_transactions,
                    "required_information": self._required_information_payload(),
                    "trace": trace,
                },
                delegation_trace=trace,
            )

        verification_agent = self.registry.get("fraud_verification")
        verification_result = await verification_agent.execute_task(
            AgentTask(
                task_type="verify_fraud_report",
                constraints={
                    "user_id": user_id,
                    "reported_account_no": state.fields["reported_account_no"],
                    "reported_bank_code": state.fields.get("reported_bank_code"),
                    "transaction_ref": state.fields.get("transaction_ref"),
                },
            )
        )
        trace.append("verify_fraud_report")

        verification = verification_result.result
        if verification.get("is_self_report"):
            self.session_store.clear(user_id, session_id)
            return DomainAgentOutput(
                status="info_response",
                info_response="Không thể tạo báo cáo lừa đảo cho tài khoản thuộc chính bạn.",
                response_data={
                    "operation": "REPORT_FRAUD",
                    "rejected": True,
                    "reason": "self_reported_account",
                    "verification_evidence": verification,
                    "trace": trace,
                },
                delegation_trace=trace,
            )

        scoring = self.scorer.calculate(
            has_evidence=bool(state.fields["has_evidence"]),
            transaction_found=bool(verification.get("transaction_found")),
            existing_reports_count=int(verification.get("existing_reports_count") or 0),
            reason_text=state.fields["reason_text"],
        )
        trace.append("score_report")

        draft = self._build_draft(
            user_id=user_id,
            fields=state.fields,
            verification=verification,
            scoring=scoring,
        )
        trace.append("build_fraud_report_draft")

        # Persist report to database
        try:
            report_id = self.store.persist_report(
                reporter_cif_no=user_id,
                transaction_ref=state.fields.get("transaction_ref"),
                reported_account_no=state.fields["reported_account_no"],
                reported_bank_code=state.fields["reported_bank_code"],
                reported_customer_cif=None,
                fraud_type=state.fields.get("fraud_type") or "OTHER",
                contact_channel=state.fields["contact_channel"],
                aftermath=state.fields["aftermath"],
                reason_text=state.fields["reason_text"],
                has_evidence=bool(state.fields["has_evidence"]),
                confidence_score=scoring["confidence_score"],
                status=scoring["status"],
            )
            trace.append("persist_fraud_report")

            # Update reported_accounts aggregate
            tx_amount = verification.get("transaction_amount")
            self.store.update_reported_account_aggregate(
                account_no=state.fields["reported_account_no"],
                bank_code=state.fields["reported_bank_code"],
                confidence_score=scoring["confidence_score"],
                reporter_cif_no=user_id,
                amount=int(tx_amount) if tx_amount else None,
            )
            trace.append("update_reported_accounts_aggregate")
        except Exception as exc:
            logger.error("[FRAUD] persist failed: %s", exc, exc_info=True)
            report_id = None

        self.session_store.clear(user_id, session_id)

        logger.info(
            "[FRAUD] complete user=%s status=%s confidence=%s tx_found=%s existing_reports=%s",
            user_id,
            scoring["status"],
            scoring["confidence_score"],
            verification.get("transaction_found"),
            verification.get("existing_reports_count"),
        )

        return DomainAgentOutput(
            status="info_response",
            info_response=self._build_final_message(scoring, verification),
            response_data={
                "fraud_report_draft": draft.model_dump(),
                "verification_evidence": verification,
                "confidence_score": scoring["confidence_score"],
                "confidence_status": scoring["status"],
                "scoring_reasons": scoring["scoring_reasons"],
                "missing_fields": [],
                "candidate_transactions": state.candidate_transactions,
                "trace": trace,
            },
            delegation_trace=trace,
        )

    async def _extract_entities(
        self,
        message: str,
        current_fields: dict,
    ) -> FraudReportExtraction:
        try:
            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": FRAUD_REPORT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": FRAUD_REPORT_USER_TEMPLATE.format(
                            message=message,
                            current_state=json.dumps(
                                current_fields,
                                ensure_ascii=False,
                                indent=2,
                            ),
                        ),
                    },
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            logger.info("[FRAUD EXTRACT RAW] %s", raw)
            data = json.loads(raw)
            return FraudReportExtraction(**data)
        except Exception as exc:
            logger.error("[FRAUD] extraction failed: %s", exc, exc_info=True)
            return FraudReportExtraction(**self._infer_fields_from_text(message))

    def _merge_fields(
        self,
        current_fields: dict,
        extraction: FraudReportExtraction,
        message: str,
    ) -> dict:
        merged = dict(current_fields)
        inferred = self._infer_fields_from_text(message)
        extracted = extraction.model_dump(exclude={"missing_fields", "confidence"})

        for source in (extracted, inferred):
            for key, value in source.items():
                if key == "operation":
                    continue
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if key == "reason_text" and merged.get(key):
                    if len(str(value)) <= len(str(merged[key])):
                        continue
                    merged[key] = f"{merged[key]} {value}".strip()
                    continue
                merged[key] = value

        if not merged.get("fraud_type"):
            merged["fraud_type"] = "OTHER"

        return merged

    def _build_draft(
        self,
        *,
        user_id: str,
        fields: dict,
        verification: dict,
        scoring: dict,
    ) -> FraudReportDraft:
        transaction_ref = fields.get("transaction_ref") or verification.get("transaction_ref")
        details = FraudReportDetails(
            reporter_cif_no=user_id,
            transaction_ref=transaction_ref,
            reported_account_no=fields["reported_account_no"],
            reported_bank_code=fields["reported_bank_code"],
            reported_customer_cif=None,
            fraud_type=fields.get("fraud_type") or "OTHER",
            contact_channel=fields["contact_channel"],
            aftermath=fields["aftermath"],
            reason_text=fields["reason_text"],
            has_evidence=bool(fields["has_evidence"]),
            confidence_score=scoring["confidence_score"],
            status=scoring["status"],
        )
        return FraudReportDraft(
            cif_no=user_id,
            report_draft=details,
            verification_evidence=verification,
        )

    async def _maybe_select_candidate_transaction(
        self,
        *,
        message: str,
        user_id: str,
        session_id: str,
        state,
        trace: list[str],
    ) -> DomainAgentOutput | None:
        account_no = state.fields.get("reported_account_no")
        bank_code = state.fields.get("reported_bank_code")
        if not account_no or not bank_code:
            self.session_store.set_stage(user_id, session_id, "collect_account" if not account_no else "collect_bank")
            return None

        # Reuse previous candidates if the user is replying to the selection question.
        if state.candidate_transactions and not state.selected_transaction_ref:
            selected = self._parse_candidate_selection(message, state.candidate_transactions)
            if selected:
                self.session_store.set_selected_transaction(user_id, session_id, selected["transaction_ref"])
                self.session_store.set_stage(user_id, session_id, "collect_context")
                state = self.session_store.get_or_create(user_id, session_id)
                trace.append("select_candidate_transaction")
            elif state.stage == "confirm_transaction":
                prompt = self._build_selection_prompt(state.candidate_transactions)
                return DomainAgentOutput(
                    status="clarification_needed",
                    clarification_message=prompt,
                    response_data={
                        "operation": "REPORT_FRAUD",
                        "candidate_transactions": state.candidate_transactions,
                        "verification_evidence": {
                            "transaction_found": True,
                            "matching_transactions": state.candidate_transactions,
                        },
                        "stage": "confirm_transaction",
                        "trace": trace,
                    },
                    delegation_trace=trace,
                )

        if state.selected_transaction_ref:
            self.session_store.set_stage(user_id, session_id, "collect_context")
            return None

        verification = self.registry.get("fraud_verification")
        verification_result = await verification.execute_task(
            AgentTask(
                task_type="verify_fraud_report",
                constraints={
                    "user_id": user_id,
                    "reported_account_no": account_no,
                    "reported_bank_code": bank_code,
                    "transaction_ref": state.fields.get("transaction_ref"),
                },
            )
        )
        trace.append("verify_candidates")
        candidates = verification_result.result.get("matching_transactions", [])
        self.session_store.set_transaction_candidates(user_id, session_id, candidates)

        if not candidates:
            self.session_store.set_stage(user_id, session_id, "collect_context")
            trace.append("no_candidate_transactions")

        if len(candidates) == 1:
            selected = candidates[0]
            self.session_store.set_selected_transaction(user_id, session_id, selected["transaction_ref"])
            self.session_store.set_stage(user_id, session_id, "collect_context")
            trace.append("auto_select_transaction")
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=self._build_context_prompt(selected, auto_selected=True),
                response_data={
                    "operation": "REPORT_FRAUD",
                    "candidate_transactions": candidates,
                    "selected_transaction_ref": selected["transaction_ref"],
                    "verification_evidence": verification_result.result,
                    "trace": trace,
                },
                delegation_trace=trace,
            )

        self.session_store.set_stage(user_id, session_id, "confirm_transaction")
        prompt = self._build_selection_prompt(candidates)
        self.session_store.set_last_prompt(user_id, session_id, prompt)
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message=prompt,
            response_data={
                "operation": "REPORT_FRAUD",
                "candidate_transactions": candidates,
                "verification_evidence": verification_result.result,
                "stage": "confirm_transaction",
                "trace": trace,
            },
            delegation_trace=trace,
        )

    def _missing_required_fields(self, fields: dict) -> list[str]:
        missing = []
        for field_name in REQUIRED_FIELDS:
            if field_name not in fields:
                missing.append(field_name)
                continue
            value = fields[field_name]
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field_name)
        return missing

    def _next_question(self, state, missing_fields: list[str]) -> dict:
        question_map = {
            "reported_account_no": {
                "stage": "collect_account",
                "question": "Số tài khoản của người bạn muốn báo cáo là gì?",
                "message": "Tôi cần số tài khoản của người bị báo cáo trước tiên.",
            },
            "reported_bank_code": {
                "stage": "collect_bank",
                "question": "Tài khoản đó thuộc ngân hàng nào?",
                "message": "Tôi cần biết ngân hàng của tài khoản đó.",
            },
            "contact_channel": {
                "stage": "collect_context",
                "question": "Bạn bị liên hệ qua kênh nào, ví dụ Zalo, Facebook, Telegram, điện thoại?",
                "message": self._build_context_prompt(None),
            },
            "aftermath": {
                "stage": "collect_context",
                "question": "Sau khi chuyển tiền hoặc phát hiện nghi ngờ, chuyện gì đã xảy ra?",
                "message": self._build_context_prompt(None),
            },
            "reason_text": {
                "stage": "collect_context",
                "question": "Bạn mô tả ngắn gọn sự việc để tôi chốt nội dung báo cáo.",
                "message": self._build_context_prompt(None),
            },
            "has_evidence": {
                "stage": "collect_context",
                "question": "Bạn có bằng chứng như ảnh chụp màn hình, tin nhắn, số điện thoại hoặc liên kết không?",
                "message": self._build_context_prompt(None),
            },
        }

        for field_name in (
            "reported_account_no",
            "reported_bank_code",
            "contact_channel",
            "aftermath",
            "reason_text",
            "has_evidence",
        ):
            if field_name in missing_fields:
                item = question_map[field_name]
                return {
                    "field": field_name,
                    "stage": item["stage"],
                    "question": item["question"],
                    "message": item["message"],
                }

        return {
            "field": None,
            "stage": "collect_context",
            "question": "",
            "message": self._build_context_prompt(None),
        }

    def _build_context_prompt(self, selected_transaction: dict | None, auto_selected: bool = False) -> str:
        tx_text = ""
        if selected_transaction:
            tx_text = (
                f" Tôi đã đối chiếu thấy giao dịch {selected_transaction.get('transaction_ref')} "
                f"gửi đến {selected_transaction.get('recipient_name')} - {selected_transaction.get('recipient_account')} "
                f"({selected_transaction.get('recipient_bank')}) vào {selected_transaction.get('created_at')}."
            )
        prefix = "Tôi đã thấy một giao dịch khớp." if auto_selected else "Tôi đã xác định được giao dịch liên quan."
        return (
            f"{prefix}{tx_text} Bây giờ tôi cần thêm 3 thông tin để hoàn tất báo cáo: "
            f"bạn bị liên hệ qua kênh nào, sau khi chuyển tiền chuyện gì xảy ra, "
            f"và bạn có bằng chứng gì không? Nếu có thể, mô tả ngắn gọn lại sự việc. "
            f"Nếu giao dịch vừa xảy ra, hãy liên hệ ngân hàng ngay và đừng chuyển thêm tiền."
        )

    def _build_selection_prompt(self, candidates: list[dict]) -> str:
        lines = [
            "Tôi tìm thấy nhiều giao dịch có thể liên quan. Bạn hãy chọn số tương ứng:",
            "",
            "| # | Mã giao dịch | Người nhận | Số tài khoản | Ngân hàng | Số tiền | Thời gian |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for index, tx in enumerate(candidates, start=1):
            lines.append(
                "| {index} | {transaction_ref} | {recipient_name} | {recipient_account} | {recipient_bank} | {amount} {currency} | {created_at} |".format(
                    index=index,
                    transaction_ref=tx.get("transaction_ref", ""),
                    recipient_name=tx.get("recipient_name", ""),
                    recipient_account=tx.get("recipient_account", ""),
                    recipient_bank=tx.get("recipient_bank", ""),
                    amount=tx.get("amount", ""),
                    currency=tx.get("currency", ""),
                    created_at=tx.get("created_at", ""),
                )
            )
        lines.extend(
            [
                "",
                "Bạn trả lời bằng số 1, 2, 3... hoặc gửi mã giao dịch nếu bạn nhớ rõ.",
                "Nếu giao dịch vừa xảy ra, hãy liên hệ ngân hàng ngay và giữ lại bằng chứng.",
            ]
        )
        return "\n".join(lines)

    def _parse_candidate_selection(self, message: str, candidates: list[dict]) -> dict | None:
        text = message.strip().lower()
        if not candidates:
            return None

        direct_ref = re.search(r"\bTX-\d+\b", message, re.IGNORECASE)
        if direct_ref:
            ref = direct_ref.group(0).upper()
            for candidate in candidates:
                if candidate.get("transaction_ref", "").upper() == ref:
                    return candidate

        number_match = re.search(r"\b(\d{1,2})\b", text)
        if number_match:
            index = int(number_match.group(1)) - 1
            if 0 <= index < len(candidates):
                return candidates[index]

        return None

    def _build_final_message(self, scoring: dict, verification: dict) -> str:
        if verification.get("transaction_found"):
            evidence_text = "Tôi đã tìm thấy giao dịch phù hợp trong lịch sử của bạn."
        else:
            evidence_text = (
                "Tôi chưa tìm thấy giao dịch phù hợp, nên báo cáo sẽ được đánh dấu "
                "cần xem xét thủ công."
            )
        return (
            f"Tôi đã lập bản nháp báo cáo lừa đảo với trạng thái {scoring['status']} "
            f"và điểm tin cậy {scoring['confidence_score']}/100. {evidence_text}"
        )

    def _build_initial_intake_message(self) -> str:
        items = self._required_information_payload()
        lines = [
            "Tôi có thể giúp bạn ghi nhận báo cáo lừa đảo.",
            "Để làm báo cáo đầy đủ, vui lòng gửi cho tôi các thông tin sau trong cùng một tin nhắn nếu có thể:",
            "",
            "| Trường | Mô tả |",
            "| --- | --- |",
        ]
        for item in items:
            lines.append(f"| {item['label']} | {item['description']} |")
        lines.extend(
            [
                "",
                "Nếu bạn chưa có mã giao dịch, hãy gửi thời gian và số tiền gần đúng.",
                "Nếu vừa chuyển tiền, hãy liên hệ ngân hàng ngay và không chuyển thêm tiền.",
            ]
        )
        return "\n".join(lines)

    def _required_information_payload(self) -> list[dict]:
        return [
            {
                "field": "reported_account_no",
                "label": "Số tài khoản bị báo cáo",
                "description": "số tài khoản của người/tài khoản bạn nghi là lừa đảo",
            },
            {
                "field": "reported_bank_code",
                "label": "Ngân hàng của tài khoản đó",
                "description": "tên ngân hàng hoặc mã ngân hàng nếu bạn biết",
            },
            {
                "field": "transaction_ref",
                "label": "Mã giao dịch nếu có",
                "description": "mã giao dịch, hoặc thời gian và số tiền gần đúng nếu không có mã",
            },
            {
                "field": "contact_channel",
                "label": "Kênh liên hệ",
                "description": "ví dụ Zalo, Facebook, Telegram, điện thoại, SMS, email hoặc website",
            },
            {
                "field": "aftermath",
                "label": "Diễn biến sau đó",
                "description": "ví dụ bị chặn liên lạc, chưa nhận hàng, bị yêu cầu thêm tiền, hoặc mất tiền",
            },
            {
                "field": "reason_text",
                "label": "Mô tả ngắn sự việc",
                "description": "một đến hai câu nêu vì sao bạn cho rằng đây là lừa đảo",
            },
            {
                "field": "has_evidence",
                "label": "Bằng chứng",
                "description": "ảnh chụp màn hình, tin nhắn, link, số điện thoại, biên lai, hoặc xác nhận là không có",
            },
        ]

    def _infer_fields_from_text(self, message: str) -> dict:
        text = message.lower()
        inferred: dict = {}

        if any(token in text for token in ("trạng thái báo cáo", "status", "tiến độ báo cáo")):
            inferred["operation"] = "CHECK_FRAUD_STATUS"
        else:
            inferred["operation"] = "REPORT_FRAUD"

        account_match = re.search(r"\b\d{6,20}\b", message)
        if account_match:
            inferred["reported_account_no"] = account_match.group(0)

        bank_match = re.search(
            r"\b(VCB|VIETCOMBANK|VPB|VPBANK|TCB|TECHCOMBANK|ACB|MBB|MB|BIDV|VTB|VIETINBANK|TPB|TPBANK)\b",
            message,
            re.IGNORECASE,
        )
        if bank_match:
            inferred["reported_bank_code"] = bank_match.group(1).upper()

        ref_match = re.search(r"\b(?:TX|TXN|GD|REF)[-_\s]*\d+\b", message, re.IGNORECASE)
        if ref_match:
            inferred["transaction_ref"] = ref_match.group(0).replace(" ", "-").upper()

        channel_map = {
            "zalo": "ZALO",
            "facebook": "FACEBOOK",
            "fb": "FACEBOOK",
            "telegram": "TELEGRAM",
            "website": "WEBSITE",
            "web": "WEBSITE",
            "điện thoại": "PHONE",
            "dien thoai": "PHONE",
            "sms": "SMS",
            "email": "EMAIL",
        }
        for token, value in channel_map.items():
            if token in text:
                inferred["contact_channel"] = value
                break

        if any(token in text for token in ("block", "chặn", "chan")):
            inferred["aftermath"] = "BLOCKED_CONTACT"
        elif any(token in text for token in ("không nhận được hàng", "khong nhan duoc hang")):
            inferred["aftermath"] = "NO_GOODS"
        elif any(token in text for token in ("chuyển thêm", "chuyen them", "thêm tiền", "them tien")):
            inferred["aftermath"] = "REQUESTED_MORE_MONEY"
        elif any(token in text for token in ("mất tiền", "mat tien", "bị trừ tiền", "bi tru tien")):
            inferred["aftermath"] = "MONEY_LOST"

        if any(token in text for token in ("screenshot", "ảnh", "anh chup", "tin nhắn", "tin nhan", "bằng chứng", "bang chung")):
            inferred["has_evidence"] = True
        elif any(token in text for token in ("không có bằng chứng", "khong co bang chung", "không có ảnh", "khong co anh")):
            inferred["has_evidence"] = False

        if any(token in text for token in ("mua hàng", "mua hang", "không nhận được hàng", "khong nhan duoc hang")):
            inferred["fraud_type"] = "SHOPPING_SCAM"
        elif any(token in text for token in ("đầu tư", "dau tu", "lãi", "lai suat")):
            inferred["fraud_type"] = "INVESTMENT_SCAM"
        elif any(token in text for token in ("vay", "khoản vay", "phi truoc", "phí trước")):
            inferred["fraud_type"] = "LOAN_SCAM"
        elif any(token in text for token in ("giả danh", "gia danh", "mạo danh", "mao danh")):
            inferred["fraud_type"] = "IMPERSONATION_SCAM"
        elif any(token in text for token in ("lừa", "lua", "scam", "fraud")):
            inferred["fraud_type"] = "SCAM_TRANSFER"

        if len(message.strip()) >= 12 and inferred.get("operation") == "REPORT_FRAUD":
            inferred["reason_text"] = message.strip()

        return inferred
