"""FSM-based intercept for account operation states (confirmation & OTP).

Separate from transaction_fsm and card_operation_fsm.
"""
from __future__ import annotations

import logging
from datetime import datetime

from backend.models import ChatRequest, ChatResponse
from backend.services.audit_log import write_audit_log
from backend.services.confirmation_classifier import classify_confirmation
from backend.services.guardrails import validate_otp

logger = logging.getLogger(__name__)


async def handle_account_operation_state_intercept(
    request: ChatRequest,
    *,
    get_account_operation_state,
    set_account_operation_state,
    clear_account_operation_state,
) -> ChatResponse | None:
    """FSM-based intercept for account operation states."""
    state = get_account_operation_state(request.session_id)
    if not state:
        return None

    fsm_state = state.get("fsm_state")
    message = request.message.strip()
    user_id = request.user_id

    if fsm_state == "WAITING_CONFIRMATION":
        return await _handle_confirmation(
            state, message, user_id, request.session_id,
            set_account_operation_state=set_account_operation_state,
            clear_account_operation_state=clear_account_operation_state,
        )

    if fsm_state == "WAITING_OTP":
        return _handle_otp(
            state, message, user_id, request.session_id,
            set_account_operation_state=set_account_operation_state,
            clear_account_operation_state=clear_account_operation_state,
        )

    return None


async def _handle_confirmation(
    state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_account_operation_state,
    clear_account_operation_state,
) -> ChatResponse:
    """Handle user reply in WAITING_CONFIRMATION."""
    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")
    draft_summary = f"{operation} — {draft_data.get('product_name') or draft_data.get('account_no', '')}"

    result = await classify_confirmation(message, draft_summary=draft_summary)
    classification = result["classification"]

    write_audit_log(
        cif_no=user_id,
        event_type="ACCOUNT_CONFIRMATION_CLASSIFIED",
        actor="classifier",
        session_id=session_id,
        event_payload={"classification": classification, "operation": operation},
    )

    if classification == "CONFIRM":
        requires_otp = state.get("requires_otp", False)

        if requires_otp:
            state["fsm_state"] = "WAITING_OTP"
            state["otp_created_at"] = datetime.now().isoformat(timespec="seconds")
            set_account_operation_state(session_id, state)

            write_audit_log(
                cif_no=user_id,
                event_type="ACCOUNT_OPERATION_CONFIRMED",
                actor="user",
                session_id=session_id,
                event_payload={"fsm_transition": "WAITING_CONFIRMATION → WAITING_OTP", "operation": operation},
            )
            return ChatResponse(
                status="needs_otp",
                message="Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận.",
                data={**draft_data, "requires_otp": True},
            )

        # No OTP — execute immediately
        return await _execute_operation(
            state, user_id, session_id,
            clear_account_operation_state=clear_account_operation_state,
        )

    if classification == "CANCEL":
        clear_account_operation_state(session_id)
        write_audit_log(
            cif_no=user_id,
            event_type="ACCOUNT_OPERATION_CANCELLED",
            actor="user",
            session_id=session_id,
            event_payload={"stage": "WAITING_CONFIRMATION", "operation": operation},
        )
        return ChatResponse(
            status="info_response",
            message="Đã hủy thao tác.",
            data={"operation": "ACCOUNT_OPERATION_CANCELLED"},
        )

    # UNCLEAR / MODIFY
    return ChatResponse(
        status="clarification_needed",
        message="Bạn muốn xác nhận hay hủy thao tác?",
        data={**draft_data, "requires_confirmation": True},
    )


def _handle_otp(
    state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_account_operation_state,
    clear_account_operation_state,
) -> ChatResponse:
    """Handle user reply in WAITING_OTP."""
    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")

    # Check expiry
    otp_created = state.get("otp_created_at")
    otp_expires = state.get("otp_expires_seconds", 300)
    if otp_created:
        elapsed = (datetime.now() - datetime.fromisoformat(otp_created)).total_seconds()
        if elapsed > otp_expires:
            clear_account_operation_state(session_id)
            write_audit_log(
                cif_no=user_id,
                event_type="ACCOUNT_OTP_EXPIRED",
                actor="system",
                session_id=session_id,
                event_payload={"operation": operation},
            )
            return ChatResponse(
                status="info_response",
                message="Mã OTP đã hết hạn. Vui lòng thực hiện lại.",
                data={"operation": "ACCOUNT_OPERATION_EXPIRED"},
            )

    # Cancel
    if message.lower() in ("hủy", "cancel", "thôi", "dừng", "không"):
        clear_account_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message="Đã hủy thao tác.",
            data={"operation": "ACCOUNT_OPERATION_CANCELLED"},
        )

    # Validate format
    if not (message.isdigit() and len(message) == 6):
        return ChatResponse(
            status="needs_otp",
            message="Vui lòng nhập mã OTP 6 chữ số, hoặc gõ 'hủy' để hủy.",
            data={**draft_data, "requires_otp": True},
        )

    # Validate OTP
    if validate_otp(message):
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            _execute_operation(state, user_id, session_id, clear_account_operation_state=clear_account_operation_state)
        ) if False else _execute_operation_sync(state, user_id, session_id, clear_account_operation_state=clear_account_operation_state)

    # Invalid
    state["otp_attempts"] = state.get("otp_attempts", 0) + 1
    remaining = state.get("max_otp_attempts", 3) - state["otp_attempts"]

    if remaining <= 0:
        clear_account_operation_state(session_id)
        write_audit_log(
            cif_no=user_id,
            event_type="ACCOUNT_OPERATION_BLOCKED",
            actor="system",
            session_id=session_id,
            event_payload={"reason": "max_otp_attempts", "operation": operation},
        )
        return ChatResponse(
            status="info_response",
            message="Bạn đã nhập sai OTP quá số lần cho phép. Thao tác đã bị hủy.",
            data={"operation": "ACCOUNT_OPERATION_BLOCKED"},
        )

    set_account_operation_state(session_id, state)
    return ChatResponse(
        status="needs_otp",
        message=f"Mã OTP không đúng. Vui lòng nhập lại. (Còn {remaining} lần thử)",
        data={**draft_data, "requires_otp": True, "otp_attempts_remaining": remaining},
    )


def _execute_operation_sync(
    state: dict,
    user_id: str,
    session_id: str,
    *,
    clear_account_operation_state,
) -> ChatResponse:
    """Execute account operation synchronously after OTP validation."""
    import asyncio
    from backend.agents.tools.account_tools import ACCOUNT_TOOL_FUNCTIONS

    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")
    context = {"user_id": user_id, "session_id": session_id}

    tool_fn = None
    tool_params: dict = {}

    if operation == "OPEN_ACCOUNT":
        tool_fn = ACCOUNT_TOOL_FUNCTIONS["open_account"]
        tool_params = {
            "product_code": draft_data.get("product_code"),
            "nickname": draft_data.get("nickname"),
            "purpose": draft_data.get("purpose"),
        }
    elif operation == "CLOSE_ACCOUNT":
        tool_fn = ACCOUNT_TOOL_FUNCTIONS["close_account"]
        tool_params = {
            "account_no": draft_data.get("account_no"),
            "account_id": draft_data.get("account_id"),
        }

    if not tool_fn:
        clear_account_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message="Không thể thực hiện thao tác.",
            data={"operation": operation, "error": "unknown_operation"},
        )

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(tool_fn(tool_params, context))
        loop.close()
    except Exception as e:
        logger.error(f"[ACCOUNT FSM] Execute error: {e}", exc_info=True)
        clear_account_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message=f"Lỗi khi thực hiện: {e}",
            data={"operation": operation, "error": str(e)},
        )

    clear_account_operation_state(session_id)

    write_audit_log(
        cif_no=user_id,
        event_type="ACCOUNT_OPERATION_EXECUTED",
        actor="system",
        session_id=session_id,
        event_payload={"operation": operation, "result_status": result.get("status"), "draft": draft_data},
    )

    if result.get("status") == "success":
        return ChatResponse(
            status="info_response",
            message=f"✅ {result.get('message', 'Thao tác thành công.')}",
            data={**draft_data, "executed": True, "result": result},
        )

    # Failed (eligibility issue caught at execute time)
    reasons = result.get("reasons", [])
    msg = result.get("message", "Không thể thực hiện thao tác.")
    if reasons:
        msg = msg + "\n" + "\n".join(f"• {r}" for r in reasons)
    return ChatResponse(
        status="info_response",
        message=msg,
        data={**draft_data, "executed": False, "result": result},
    )


async def _execute_operation(
    state: dict,
    user_id: str,
    session_id: str,
    *,
    clear_account_operation_state,
) -> ChatResponse:
    """Execute account operation after confirmation (async version)."""
    from backend.agents.tools.account_tools import ACCOUNT_TOOL_FUNCTIONS

    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")
    context = {"user_id": user_id, "session_id": session_id}

    tool_fn = None
    tool_params: dict = {}

    if operation == "OPEN_ACCOUNT":
        tool_fn = ACCOUNT_TOOL_FUNCTIONS["open_account"]
        tool_params = {
            "product_code": draft_data.get("product_code"),
            "nickname": draft_data.get("nickname"),
            "purpose": draft_data.get("purpose"),
        }
    elif operation == "CLOSE_ACCOUNT":
        tool_fn = ACCOUNT_TOOL_FUNCTIONS["close_account"]
        tool_params = {
            "account_no": draft_data.get("account_no"),
            "account_id": draft_data.get("account_id"),
        }

    if not tool_fn:
        clear_account_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message="Không thể thực hiện thao tác.",
            data={"operation": operation, "error": "unknown_operation"},
        )

    try:
        result = await tool_fn(tool_params, context)
    except Exception as e:
        logger.error(f"[ACCOUNT FSM] Execute error: {e}", exc_info=True)
        clear_account_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message=f"Lỗi khi thực hiện: {e}",
            data={"operation": operation, "error": str(e)},
        )

    clear_account_operation_state(session_id)

    write_audit_log(
        cif_no=user_id,
        event_type="ACCOUNT_OPERATION_EXECUTED",
        actor="system",
        session_id=session_id,
        event_payload={"operation": operation, "result_status": result.get("status"), "draft": draft_data},
    )

    if result.get("status") == "success":
        return ChatResponse(
            status="info_response",
            message=f"✅ {result.get('message', 'Thao tác thành công.')}",
            data={**draft_data, "executed": True, "result": result},
        )

    reasons = result.get("reasons", [])
    msg = result.get("message", "Không thể thực hiện thao tác.")
    if reasons:
        msg = msg + "\n" + "\n".join(f"• {r}" for r in reasons)
    return ChatResponse(
        status="info_response",
        message=msg,
        data={**draft_data, "executed": False, "result": result},
    )
