"""AccountOperationAgent — agentic tool-calling agent for ACCOUNT_OPERATION intent.

Handles: OPEN_ACCOUNT, CLOSE_ACCOUNT, UPDATE_NICKNAME.
Uses ReAct-style loop with tools for account resolution and operations.
"""
import json
import logging

from openai import AsyncOpenAI

from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models import (
    AccountActionDraft,
    AccountOperationState,
    DomainAgentOutput,
)
from backend.agents.tools.account_tools import ACCOUNT_TOOLS, ACCOUNT_TOOL_FUNCTIONS
from backend.prompts.account_operation import ACCOUNT_OPERATION_SYSTEM_PROMPT
from backend.services.account_guardrails import check_account_operation_guardrails
from backend.services.chat_session_store import ChatSessionStore
from backend.services.audit_log import write_audit_log

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 8


class AccountOperationAgent:
    """Agentic account operation agent with tool-calling loop."""

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
        """Run the account operation agent loop."""
        trace = []

        messages = [{"role": "system", "content": ACCOUNT_OPERATION_SYSTEM_PROMPT}]

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

            if choice.message.tool_calls:
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)
                    trace.append(f"tool:{fn_name}")
                    logger.info(f"[ACCOUNT AGENT] Tool call: {fn_name}({fn_args})")

                    tool_fn = ACCOUNT_TOOL_FUNCTIONS.get(fn_name)
                    if tool_fn:
                        result = await tool_fn(fn_args, context)
                    else:
                        result = {"error": f"Unknown tool: {fn_name}"}

                    logger.info(f"[ACCOUNT AGENT] Tool result: {result}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })

                continue

            # Final response
            raw_content = choice.message.content
            trace.append("final_response")
            logger.info(f"[ACCOUNT AGENT] Final: {raw_content}")

            return self._process_final_response(raw_content, trace, context)

        logger.warning("[ACCOUNT AGENT] Max iterations reached")
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

        if status == "cancelled":
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", "Đã hủy thao tác."),
                response_data={"operation": "ACCOUNT_OPERATION_CANCELLED"},
                delegation_trace=trace,
            )

        if status == "info_response":
            return DomainAgentOutput(
                status="info_response",
                info_response=data.get("message", ""),
                response_data=data.get("data"),
                delegation_trace=trace,
            )

        if status == "needs_clarification":
            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=data.get("message", "Vui lòng cung cấp thêm thông tin."),
                response_data={"candidates": data.get("candidates")},
                delegation_trace=trace,
            )

        if status == "draft_created":
            operation = data.get("operation", "")

            # Check guardrails
            guardrail = check_account_operation_guardrails(operation=operation)

            if not guardrail.requires_confirmation:
                # UPDATE_NICKNAME — should already have been executed by tool
                return DomainAgentOutput(
                    status="info_response",
                    info_response=data.get("message", "Thao tác hoàn tất."),
                    response_data=data.get("data"),
                    delegation_trace=trace,
                )

            # Build draft
            draft = AccountActionDraft(
                operation=operation,
                account_id=data.get("account_id"),
                account_no=data.get("account_no"),
                product_code=data.get("product_code"),
                product_name=data.get("product_name"),
                account_type=data.get("account_type"),
                currency=data.get("currency"),
                purpose=data.get("purpose"),
                nickname=data.get("nickname"),
                monthly_fee=data.get("monthly_fee"),
                opening_fee=data.get("opening_fee"),
                reason=data.get("reason"),
            )
            trace.append("build_account_draft")

            # Persist state
            acct_state = AccountOperationState(
                session_id=session_id,
                user_id=user_id,
                fsm_state="WAITING_CONFIRMATION",
                draft=draft.model_dump(),
                requires_otp=guardrail.requires_otp,
            )
            self._session_store.set_account_operation_state(session_id, acct_state.model_dump())

            write_audit_log(
                cif_no=user_id,
                event_type="ACCOUNT_OPERATION_DRAFT_CREATED",
                actor="agent",
                session_id=session_id,
                event_payload={
                    "draft": draft.model_dump(),
                    "requires_otp": guardrail.requires_otp,
                    "operation": operation,
                },
            )

            # Build confirmation
            confirm_msg = self._build_confirmation_message(draft, guardrail.requires_otp)

            return DomainAgentOutput(
                status="clarification_needed",
                clarification_message=confirm_msg,
                response_data={
                    **draft.model_dump(),
                    "requires_confirmation": True,
                    "requires_otp": guardrail.requires_otp,
                    "fsm_state": "WAITING_CONFIRMATION",
                },
                delegation_trace=trace,
            )

        # Unknown
        msg = data.get("message") or "Vui lòng cung cấp thêm thông tin."
        return DomainAgentOutput(
            status="clarification_needed",
            clarification_message=msg,
            delegation_trace=trace,
        )

    def _build_confirmation_message(self, draft: AccountActionDraft, requires_otp: bool) -> str:
        """Build confirmation message for account operations."""
        op = draft.operation

        if op == "OPEN_ACCOUNT":
            parts = ["Vui lòng xác nhận mở tài khoản mới:\n"]
            parts.append(f"• Loại: **{draft.product_name or draft.account_type}**")
            parts.append(f"• Tiền tệ: **{draft.currency}**")
            if draft.monthly_fee is not None:
                fee_text = f"{draft.monthly_fee:,} VND/tháng" if draft.monthly_fee > 0 else "Miễn phí"
                parts.append(f"• Phí duy trì: {fee_text}")
            if draft.nickname:
                parts.append(f"• Tên gợi nhớ: {draft.nickname}")
            if draft.purpose:
                parts.append(f"• Mục đích: {draft.purpose}")
            parts.append("\nBạn xác nhận mở tài khoản không?")
            return "\n".join(parts)

        if op == "CLOSE_ACCOUNT":
            parts = ["⚠️ Xác nhận **đóng tài khoản**:\n"]
            parts.append(f"• Số tài khoản: **{draft.account_no}**")
            parts.append("\n**Lưu ý: Thao tác này không thể hoàn tác.**")
            if requires_otp:
                parts.append("\n_(Sau xác nhận sẽ cần nhập OTP)_")
            parts.append("\nBạn xác nhận đóng tài khoản không?")
            return "\n".join(parts)

        return f"Xác nhận thao tác {op}?\n\nBạn xác nhận không?"

    def _build_openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in ACCOUNT_TOOLS
        ]

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        if not text:
            return text
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text
