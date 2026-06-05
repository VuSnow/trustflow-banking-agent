"""CardOperationAgent — agentic tool-calling agent for CARD_OPERATION intent.

Uses a ReAct-style loop: LLM reasons about what to do, calls tools,
observes results, and repeats until it has enough info to build a draft
or return info directly.

Architecture:
- get_user_cards, get_card_detail: card resolution
- lock_card, unlock_card, report_lost_card: status changes
- set_card_control: toggle controls
- change_card_limit: limit changes
- get_card_transactions: read card transactions

This agent handles card resolution and builds drafts.
Confirmation + OTP is handled by card_operation_fsm.py.
"""
import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import (
    CardActionDraft,
    CardOperationState,
    DomainAgentOutput,
)
from backend.agents.tools.card_tools import CARD_TOOLS, CARD_TOOL_FUNCTIONS
from backend.prompts.card_operation import CARD_OPERATION_SYSTEM_PROMPT
from backend.services.card_guardrails import check_card_operation_guardrails
from backend.services.chat_session_store import ChatSessionStore
from backend.services.audit_log import write_audit_log

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 8


class CardOperationAgent:
    """Agentic card operation agent with tool-calling loop."""

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
        """Run the card operation agent loop."""
        trace = []

        messages = [{"role": "system", "content": CARD_OPERATION_SYSTEM_PROMPT}]

        if history:
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("message", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        openai_tools = self._build_openai_tools()
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

            # Case 1: Tool calls
            if choice.message.tool_calls:
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)
                    trace.append(f"tool:{fn_name}")
                    logger.info(f"[CARD AGENT] Tool call: {fn_name}({fn_args})")

                    tool_fn = CARD_TOOL_FUNCTIONS.get(fn_name)
                    if tool_fn:
                        result = await tool_fn(fn_args, context)
                    else:
                        result = {"error": f"Unknown tool: {fn_name}"}

                    logger.info(f"[CARD AGENT] Tool result: {result}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })

                continue

            # Case 2: Final response
            raw_content = choice.message.content
            trace.append("final_response")
            logger.info(f"[CARD AGENT] Final: {raw_content}")

            return self._process_final_response(raw_content, trace, context)

        # Max iterations
        logger.warning("[CARD AGENT] Max iterations reached")
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message="Xin lỗi, tôi không thể xử lý yêu cầu này. Vui lòng thử lại.",
            delegation_trace=trace,
        )

    def _process_final_response(
        self, raw: str, trace: list[str], context: dict
    ) -> DomainAgentOutput:
        """Parse the agent's final JSON response."""
        try:
            data = json.loads(self._strip_markdown_fences(raw))
        except (json.JSONDecodeError, TypeError):
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=raw or "Vui lòng cung cấp thêm thông tin.",
                delegation_trace=trace,
            )

        status = data.get("status", "")
        session_id = context.get("session_id", "")
        user_id = context.get("user_id", "")

        # ─── Cancelled ────────────────────────────────────────────────────
        if status == "cancelled":
            trace.append("user_cancelled")
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", "Đã hủy thao tác."),
                response_data={"operation": "CARD_OPERATION_CANCELLED"},
                delegation_trace=trace,
            )

        # ─── Info response (read-only operations) ─────────────────────────
        if status == "info_response":
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", ""),
                response_data=data.get("data"),
                delegation_trace=trace,
            )

        # ─── Error ────────────────────────────────────────────────────────
        if status == "error":
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", "Không thể thực hiện thao tác."),
                response_data=data,
                delegation_trace=trace,
            )

        # ─── Needs clarification ─────────────────────────────────────────
        if status == "needs_clarification":
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=data.get("message", "Vui lòng cung cấp thêm thông tin."),
                response_data={
                    "candidates": data.get("candidates"),
                    "reason": data.get("reason"),
                },
                delegation_trace=trace,
            )

        # ─── Draft created (mutating operation) ──────────────────────────
        if status == "draft_created":
            operation = data.get("operation", "")
            card_id = data.get("card_id", "")
            masked_card_no = data.get("masked_card_no", "")
            requires_otp = data.get("requires_otp", False)

            # Check guardrails
            card_status = data.get("card_status")
            guardrail = check_card_operation_guardrails(
                operation=operation,
                card_status=card_status,
                otp_verified=False,
            )

            if guardrail.blocked:
                trace.append("guardrail_blocked")
                write_audit_log(
                    cif_no=user_id,
                    event_type="CARD_OPERATION_BLOCKED",
                    actor="guardrail",
                    session_id=session_id,
                    event_payload={"reason": guardrail.reason, "operation": operation},
                )
                return DomainAgentOutput(
                    status="info_response",
                    info_response=guardrail.reason,
                    response_data={"operation": operation, "blocked": True},
                    delegation_trace=trace,
                )

            # Build draft
            draft = CardActionDraft(
                operation=operation,
                card_id=card_id,
                masked_card_no=masked_card_no,
                card_type=data.get("card_type"),
                card_network=data.get("card_network"),
                reason=data.get("reason"),
                limit_type=data.get("limit_type"),
                new_limit=data.get("new_limit"),
                old_limit=data.get("old_limit"),
                control_name=data.get("control_name"),
                new_value=data.get("new_value"),
                old_value=data.get("old_value"),
            )
            trace.append("build_card_draft")

            # Determine if OTP is required from guardrail
            otp_needed = guardrail.requires_otp or requires_otp

            # Persist card operation state
            card_state = CardOperationState(
                session_id=session_id,
                user_id=user_id,
                fsm_state="WAITING_CONFIRMATION",
                draft=draft.model_dump(),
                requires_otp=otp_needed,
            )
            self._session_store.set_card_operation_state(session_id, card_state.model_dump())

            write_audit_log(
                cif_no=user_id,
                event_type="CARD_OPERATION_DRAFT_CREATED",
                actor="agent",
                session_id=session_id,
                event_payload={
                    "draft": draft.model_dump(),
                    "requires_otp": otp_needed,
                    "operation": operation,
                },
            )

            # Build confirmation message
            confirm_msg = self._build_confirmation_message(draft, otp_needed)

            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=confirm_msg,
                response_data={
                    **draft.model_dump(),
                    "requires_confirmation": True,
                    "requires_otp": otp_needed,
                    "fsm_state": "WAITING_CONFIRMATION",
                },
                delegation_trace=trace,
            )

        # Unknown status
        msg = data.get("message") or "Vui lòng cung cấp thêm thông tin."
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message=msg,
            delegation_trace=trace,
        )

    def _build_confirmation_message(self, draft: CardActionDraft, requires_otp: bool) -> str:
        """Build human-readable confirmation for card operations."""
        op = draft.operation
        card_info = f"thẻ {draft.card_network or ''} {draft.card_type or ''} {draft.masked_card_no}".strip()

        if op == "LOCK_CARD":
            msg = f"Xác nhận **khóa tạm thời** {card_info}?\n\nBạn có thể mở khóa lại sau."
        elif op == "UNLOCK_CARD":
            msg = f"Xác nhận **mở khóa** {card_info}?"
        elif op == "REPORT_LOST":
            msg = (
                f"⚠️ Xác nhận **báo mất** {card_info}?\n\n"
                "**Lưu ý: Thao tác này không thể hoàn tác.** Thẻ sẽ bị khóa vĩnh viễn."
            )
        elif op in ("ENABLE_ONLINE_PAYMENT", "DISABLE_ONLINE_PAYMENT"):
            action = "bật" if "ENABLE" in op else "tắt"
            msg = f"Xác nhận **{action} thanh toán online** cho {card_info}?"
        elif op in ("ENABLE_INTERNATIONAL_PAYMENT", "DISABLE_INTERNATIONAL_PAYMENT"):
            action = "bật" if "ENABLE" in op else "tắt"
            msg = f"Xác nhận **{action} thanh toán quốc tế** cho {card_info}?"
        elif op == "CHANGE_LIMIT":
            limit_labels = {
                "daily_atm_limit": "hạn mức ATM hàng ngày",
                "daily_pos_limit": "hạn mức POS hàng ngày",
                "daily_online_limit": "hạn mức online hàng ngày",
                "per_transaction_limit": "hạn mức mỗi giao dịch",
            }
            label = limit_labels.get(draft.limit_type or "", draft.limit_type or "hạn mức")
            old = f"{draft.old_limit:,}" if draft.old_limit else "?"
            new = f"{draft.new_limit:,}" if draft.new_limit else "?"
            msg = f"Xác nhận thay đổi **{label}** cho {card_info}?\n\n• Hiện tại: {old} VND\n• Mới: {new} VND"
        else:
            msg = f"Xác nhận thao tác {op} cho {card_info}?"

        if requires_otp:
            msg += "\n\n_(Sau xác nhận sẽ cần nhập OTP)_"

        msg += "\n\nBạn xác nhận không?"
        return msg

    def _build_openai_tools(self) -> list[dict]:
        """Convert CARD_TOOLS to OpenAI tools format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in CARD_TOOLS
        ]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Strip ```json ... ``` fences from LLM output."""
        if not text:
            return text
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (fences)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text
