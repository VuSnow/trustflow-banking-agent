"""TransactionAgent — agentic tool-calling agent for TRANSACTION intent.

Uses a ReAct-style loop: LLM reasons about what to do, calls tools,
observes results, and repeats until it has enough info to build a draft
or needs to ask the user for clarification.

Architecture:
- text2sql_query: primary resolution tool (beneficiaries, history, bank codes)
- verify_recipient: mandatory account verification before draft
- check_fraud_risk: mandatory fraud screening before draft
- Backend (main.py) owns: FSM state, frozen draft, confirmation, OTP, execution

This agent NEVER executes transactions or handles OTP.
"""
import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import (
    ActionDraft,
    DomainAgentOutput,
    TransactionState,
)
from backend.agents.tools.transaction_tools import TRANSACTION_TOOLS, TOOL_FUNCTIONS
from backend.prompts.transaction import TRANSACTION_AGENT_SYSTEM_PROMPT
from backend.services.guardrails import check_transaction_guardrails, check_bill_payment_guardrails, check_topup_guardrails
from backend.services.chat_session_store import ChatSessionStore
from backend.services.audit_log import write_audit_log

logger = logging.getLogger(__name__)

# Safety: max iterations to prevent infinite loops
MAX_AGENT_ITERATIONS = 8


class TransactionAgent:
    """Agentic transaction agent with tool-calling loop + hard guardrails."""

    def __init__(self, client: AsyncOpenAI | None = None):
        self.client = client or AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._session_store = ChatSessionStore()

    async def run(
        self,
        message: str,
        user_id: str,
        session_id: str,
        history: list[dict] | None = None,
        pipeline_context: dict | None = None,
    ) -> DomainAgentOutput:
        """Run the agent loop.

        Args:
            message: Current user message.
            user_id: User identifier (cif_no).
            session_id: Chat session identifier.
            history: Recent chat history [{"role": "user"|"assistant", "message": "..."}].
        """
        trace = []

        # Build messages for the agent
        messages = [{"role": "system", "content": TRANSACTION_AGENT_SYSTEM_PROMPT}]

        # Inject history for multi-turn context
        if history:
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("message", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        # Current user message
        messages.append({"role": "user", "content": message})

        # Convert tools to OpenAI function format
        openai_tools = self._build_openai_tools()

        # Agent loop
        context = {"user_id": user_id, "session_id": session_id}
        for iteration in range(MAX_AGENT_ITERATIONS):
            trace.append(f"iteration_{iteration}")

            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=0.0,
            )

            choice = response.choices[0]

            # Case 1: LLM wants to call tools
            if choice.message.tool_calls:
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)
                    trace.append(f"tool:{fn_name}")
                    logger.info(f"[TX AGENT] Tool call: {fn_name}({fn_args})")

                    # Execute tool
                    tool_fn = TOOL_FUNCTIONS.get(fn_name)
                    if tool_fn:
                        result = await tool_fn(fn_args, context)
                    else:
                        result = {"error": f"Unknown tool: {fn_name}"}

                    logger.info(f"[TX AGENT] Tool result: {result}")

                    # Append tool result back to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })

                continue  # Next iteration — let LLM process tool results

            # Case 2: LLM produced a final response (no tool calls)
            raw_content = choice.message.content
            trace.append("final_response")
            logger.info(f"[TX AGENT] Final: {raw_content}")

            return self._process_final_response(raw_content, trace, context)

        # Max iterations reached
        logger.warning("[TX AGENT] Max iterations reached")
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message="Xin lỗi, tôi không thể xử lý yêu cầu này lúc này. Vui lòng thử lại.",
            delegation_trace=trace,
        )

    def _process_final_response(
        self, raw: str, trace: list[str], context: dict
    ) -> DomainAgentOutput:
        """Parse the agent's final JSON response and apply guardrails."""
        try:
            data = json.loads(self._strip_markdown_fences(raw))
        except (json.JSONDecodeError, TypeError):
            # LLM returned free text — treat as clarification
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=raw or "Vui lòng cung cấp thêm thông tin.",
                delegation_trace=trace,
            )

        status = data.get("status", "")
        session_id = context.get("session_id", "")
        user_id = context.get("user_id", "")

        # ─── Cancelled ───────────────────────────────────────────────────
        if status == "cancelled":
            trace.append("user_cancelled")
            self._session_store.clear_transaction_state(session_id)
            write_audit_log(
                cif_no=user_id,
                event_type="TRANSACTION_CANCELLED",
                actor="agent",
                session_id=session_id,
                event_payload={"reason": "user_requested_cancel"},
            )
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", "Đã hủy giao dịch."),
                response_data={"operation": "TRANSACTION_CANCELLED"},
                delegation_trace=trace,
            )

        # ─── Needs clarification ─────────────────────────────────────────
        if status == "needs_clarification":
            msg = data.get("message", "Vui lòng cung cấp thêm thông tin.")
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=msg,
                response_data={
                    "reason": data.get("reason"),
                    "candidates": data.get("candidates"),
                    "missing_fields": data.get("missing_fields"),
                },
                delegation_trace=trace,
            )

        # ─── Needs confirmation (name mismatch etc.) ─────────────────────
        if status == "needs_confirmation":
            msg = data.get("message", "Vui lòng xác nhận.")
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=msg,
                response_data={
                    "reason": data.get("reason"),
                    "candidate": data.get("candidate"),
                    "warnings": data.get("warnings", []),
                    "requires_user_confirmation": True,
                },
                delegation_trace=trace,
            )

        # ─── Draft created — apply guardrails ────────────────────────────
        if status == "draft_created":
            action = data.get("action", "TRANSFER_MONEY")
            draft = self._build_draft(data)
            trace.append("build_draft")

            # Route guardrails by operation
            if action == "BILL_PAYMENT":
                guardrail = check_bill_payment_guardrails(
                    amount=draft.amount,
                    biller_code=draft.biller_code,
                    customer_bill_code=draft.customer_bill_code,
                    bill_status=data.get("bill_status"),
                    user_id=user_id,
                    otp_verified=False,
                )
                fraud_data = None
            elif action == "TOP_UP":
                guardrail = check_topup_guardrails(
                    amount=draft.amount,
                    topup_target=draft.topup_target,
                    topup_type=draft.topup_type,
                    otp_verified=False,
                )
                fraud_data = None
            else:
                fraud_data = data.get("fraud_screening") or context.get("fraud_screening")
                guardrail = check_transaction_guardrails(
                    amount=draft.amount,
                    fraud_screening=fraud_data,
                    otp_verified=False,
                )

            # BLOCK: reject outright
            if guardrail.blocked:
                trace.append("guardrail_blocked")
                write_audit_log(
                    cif_no=user_id,
                    event_type="TRANSACTION_BLOCKED",
                    actor="guardrail",
                    session_id=session_id,
                    event_payload={
                        "reason": guardrail.reason,
                        "risk_level": guardrail.risk_level,
                        "draft": draft.model_dump(),
                    },
                )
                return DomainAgentOutput(
                    status="info_response",
                    info_response=guardrail.reason,
                    response_data={
                        **draft.model_dump(),
                        "blocked": True,
                        "risk_level": guardrail.risk_level,
                    },
                    delegation_trace=trace,
                )

            # ALL transactions require confirmation → OTP
            trace.append("guardrail_confirmation_required")

            # Persist frozen transaction state
            tx_state = TransactionState(
                session_id=session_id,
                user_id=user_id,
                fsm_state="WAITING_CONFIRMATION",
                draft=draft.model_dump(),
                fraud_screening=fraud_data,
                risk_level=guardrail.risk_level,
                warning_message=guardrail.warning_message,
            )
            self._session_store.set_transaction_state(session_id, tx_state.model_dump())

            # Audit: draft created
            write_audit_log(
                cif_no=user_id,
                event_type="TRANSACTION_DRAFT_CREATED",
                actor="agent",
                session_id=session_id,
                event_payload={
                    "draft": draft.model_dump(),
                    "risk_level": guardrail.risk_level,
                    "resolution_source": draft.resolution_source,
                    "warnings": draft.warnings,
                },
            )

            logger.info(f"[TX AGENT] Draft frozen: WAITING_CONFIRMATION session={session_id}")

            # Build confirmation message
            confirm_msg = self._build_confirmation_message(draft, guardrail.warning_message)

            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=confirm_msg,
                response_data={
                    **draft.model_dump(),
                    "fraud_screening": fraud_data,
                    "warning_message": guardrail.warning_message,
                    "requires_confirmation": True,
                    "risk_level": guardrail.risk_level,
                    "fsm_state": "WAITING_CONFIRMATION",
                },
                delegation_trace=trace,
            )

        # ─── Unknown status — treat as clarification ─────────────────────
        msg = data.get("message") or data.get("clarification_message") or "Vui lòng cung cấp thêm thông tin."
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message=msg,
            delegation_trace=trace,
        )

    def _build_draft(self, data: dict) -> ActionDraft:
        """Build ActionDraft from agent output data."""
        action = data.get("action", "TRANSFER_MONEY")

        if action == "BILL_PAYMENT":
            return ActionDraft(
                action_type="TRANSACTION",
                operation="BILL_PAYMENT",
                amount=data.get("amount"),
                currency=data.get("currency", "VND"),
                biller_code=data.get("biller_code"),
                biller_name=data.get("biller_name"),
                customer_bill_code=data.get("customer_bill_code"),
                bill_id=data.get("bill_id"),
                bill_period=data.get("bill_period"),
                note=data.get("note"),
                resolution_source=data.get("resolution_source", "resolve_biller_account"),
                confidence=data.get("confidence"),
                warnings=data.get("warnings") or [],
            )

        if action == "TOP_UP":
            return ActionDraft(
                action_type="TRANSACTION",
                operation="TOP_UP",
                amount=data.get("amount"),
                currency=data.get("currency", "VND"),
                topup_target=data.get("topup_target"),
                topup_provider=data.get("topup_provider"),
                topup_type=data.get("topup_type", "phone"),
                note=data.get("note"),
                resolution_source=data.get("resolution_source", "user_provided"),
                confidence=data.get("confidence"),
                warnings=data.get("warnings") or [],
            )

        return ActionDraft(
            action_type="TRANSACTION",
            operation="TRANSFER_MONEY",
            amount=data.get("amount"),
            currency=data.get("currency", "VND"),
            recipient_name=data.get("recipient_name"),
            recipient_account=data.get("account_no"),
            recipient_bank=data.get("bank_code"),
            bank_name=data.get("bank_name"),
            transfer_type=data.get("transfer_type"),
            note=data.get("note"),
            resolution_source=data.get("resolution_source"),
            confidence=data.get("confidence"),
            warnings=data.get("warnings") or [],
        )

    def _build_confirmation_message(self, draft: ActionDraft, warning: str | None) -> str:
        """Build a human-readable confirmation message from the frozen draft."""
        if draft.operation == "BILL_PAYMENT":
            return self._build_bill_confirmation(draft, warning)
        if draft.operation == "TOP_UP":
            return self._build_topup_confirmation(draft, warning)
        return self._build_transfer_confirmation(draft, warning)

    def _build_transfer_confirmation(self, draft: ActionDraft, warning: str | None) -> str:
        """Confirmation message for TRANSFER_MONEY."""
        parts = ["Vui lòng xác nhận thông tin giao dịch:\n"]
        parts.append(f"• Người nhận: **{draft.recipient_name}**")
        parts.append(f"• Số tài khoản: **{draft.recipient_account}**")

        bank_display = draft.bank_name or draft.recipient_bank or ""
        if draft.recipient_bank and draft.bank_name:
            bank_display = f"{draft.bank_name} ({draft.recipient_bank})"
        parts.append(f"• Ngân hàng: **{bank_display}**")

        if draft.amount:
            parts.append(f"• Số tiền: **{draft.amount:,} {draft.currency}**")

        transfer_label = "Nội bộ SHB" if draft.transfer_type == "intrabank" else "Liên ngân hàng"
        parts.append(f"• Loại: {transfer_label}")

        if draft.note:
            parts.append(f"• Nội dung: {draft.note}")

        if draft.warnings:
            for w in draft.warnings:
                parts.append(f"⚠️ {w}")

        if warning:
            parts.append(f"\n{warning}")

        parts.append("\nBạn xác nhận chuyển tiền không?")
        return "\n".join(parts)

    def _build_bill_confirmation(self, draft: ActionDraft, warning: str | None) -> str:
        """Confirmation message for BILL_PAYMENT."""
        parts = ["Vui lòng xác nhận thanh toán hóa đơn:\n"]
        parts.append(f"• Nhà cung cấp: **{draft.biller_name}**")
        parts.append(f"• Mã khách hàng: **{draft.customer_bill_code}**")

        if draft.bill_period:
            parts.append(f"• Kỳ: **{draft.bill_period}**")

        if draft.amount:
            parts.append(f"• Số tiền: **{draft.amount:,} {draft.currency}**")

        if draft.note:
            parts.append(f"• Nội dung: {draft.note}")

        if draft.warnings:
            for w in draft.warnings:
                parts.append(f"⚠️ {w}")

        if warning:
            parts.append(f"\n{warning}")

        parts.append("\nBạn xác nhận thanh toán không?")
        return "\n".join(parts)

    def _build_topup_confirmation(self, draft: ActionDraft, warning: str | None) -> str:
        """Confirmation message for TOP_UP."""
        parts = ["Vui lòng xác nhận nạp tiền:\n"]
        parts.append(f"• Số điện thoại/ví: **{draft.topup_target}**")

        if draft.topup_provider:
            parts.append(f"• Nhà mạng/ví: **{draft.topup_provider}**")

        if draft.amount:
            parts.append(f"• Số tiền: **{draft.amount:,} {draft.currency}**")

        topup_label = "Nạp điện thoại" if draft.topup_type == "phone" else "Nạp ví"
        parts.append(f"• Loại: {topup_label}")

        if draft.warnings:
            for w in draft.warnings:
                parts.append(f"⚠️ {w}")

        if warning:
            parts.append(f"\n{warning}")

        parts.append("\nBạn xác nhận nạp tiền không?")
        return "\n".join(parts)

    def _build_openai_tools(self) -> list[dict]:
        """Convert TRANSACTION_TOOLS to OpenAI tools format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in TRANSACTION_TOOLS
        ]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Strip markdown code fences (```json ... ```) from LLM output."""
        import re
        stripped = text.strip()
        match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
        if match:
            return match.group(1).strip()
        return stripped
