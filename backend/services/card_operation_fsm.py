"""FSM-based intercept for card operation states (confirmation & OTP).

Separate from transaction_fsm.py — card operations have their own state
to avoid conflicts when user does card + transaction in parallel.
"""
from __future__ import annotations

import logging
from datetime import datetime

from backend.models import CardActionDraft, ChatRequest, ChatResponse
from backend.services.audit_log import write_audit_log
from backend.services.confirmation_classifier import classify_confirmation
from backend.services.guardrails import validate_otp

logger = logging.getLogger(__name__)


async def handle_card_operation_state_intercept(
    request: ChatRequest,
    *,
    get_card_operation_state,
    set_card_operation_state,
    clear_card_operation_state,
) -> ChatResponse | None:
    """FSM-based intercept for card operation states.

    Handles:
    - WAITING_CONFIRMATION: LLM-based classifier → CONFIRM/CANCEL
    - WAITING_OTP: deterministic OTP validation
    """
    state = get_card_operation_state(request.session_id)
    if not state:
        return None

    fsm_state = state.get("fsm_state")
    message = request.message.strip()
    user_id = request.user_id

    if fsm_state == "WAITING_CONFIRMATION":
        return await _handle_card_confirmation(
            state, message, user_id, request.session_id,
            set_card_operation_state=set_card_operation_state,
            clear_card_operation_state=clear_card_operation_state,
        )

    if fsm_state == "WAITING_OTP":
        return _handle_card_otp(
            state, message, user_id, request.session_id,
            set_card_operation_state=set_card_operation_state,
            clear_card_operation_state=clear_card_operation_state,
        )

    return None


async def _handle_card_confirmation(
    state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_card_operation_state,
    clear_card_operation_state,
) -> ChatResponse:
    """Handle user reply in WAITING_CONFIRMATION for card operations."""
    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "CARD_OPERATION")
    masked = draft_data.get("masked_card_no", "****")
    draft_summary = f"{operation} cho thẻ {masked}"

    result = await classify_confirmation(message, draft_summary=draft_summary)
    classification = result["classification"]

    write_audit_log(
        cif_no=user_id,
        event_type="CARD_CONFIRMATION_CLASSIFIED",
        actor="classifier",
        session_id=session_id,
        event_payload={
            "user_message": message,
            "classification": classification,
            "operation": operation,
        },
    )

    if classification == "CONFIRM":
        requires_otp = state.get("requires_otp", False)

        if requires_otp:
            # Transition to WAITING_OTP
            state["fsm_state"] = "WAITING_OTP"
            state["otp_created_at"] = datetime.now().isoformat(timespec="seconds")
            set_card_operation_state(session_id, state)

            write_audit_log(
                cif_no=user_id,
                event_type="CARD_OPERATION_CONFIRMED",
                actor="user",
                session_id=session_id,
                event_payload={"fsm_transition": "WAITING_CONFIRMATION → WAITING_OTP", "operation": operation},
            )

            return ChatResponse(
                status="needs_otp",
                message="Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận.",
                data={**draft_data, "requires_otp": True},
            )

        # No OTP needed — execute immediately
        return _execute_card_operation(
            state, user_id, session_id,
            clear_card_operation_state=clear_card_operation_state,
        )

    if classification == "CANCEL":
        clear_card_operation_state(session_id)
        write_audit_log(
            cif_no=user_id,
            event_type="CARD_OPERATION_CANCELLED",
            actor="user",
            session_id=session_id,
            event_payload={"stage": "WAITING_CONFIRMATION", "operation": operation},
        )
        return ChatResponse(
            status="info_response",
            message="Đã hủy thao tác thẻ.",
            data={"operation": "CARD_OPERATION_CANCELLED"},
        )

    # MODIFY or UNCLEAR
    return ChatResponse(
        status="clarification_needed",
        message="Bạn muốn xác nhận thao tác hay hủy?",
        data={**draft_data, "requires_confirmation": True},
    )


def _handle_card_otp(
    state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_card_operation_state,
    clear_card_operation_state,
) -> ChatResponse:
    """Handle user reply in WAITING_OTP for card operations."""
    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")

    # Check OTP expiry
    otp_created = state.get("otp_created_at")
    otp_expires = state.get("otp_expires_seconds", 300)
    if otp_created:
        created_dt = datetime.fromisoformat(otp_created)
        elapsed = (datetime.now() - created_dt).total_seconds()
        if elapsed > otp_expires:
            clear_card_operation_state(session_id)
            write_audit_log(
                cif_no=user_id,
                event_type="CARD_OTP_EXPIRED",
                actor="system",
                session_id=session_id,
                event_payload={"operation": operation, "elapsed_seconds": elapsed},
            )
            return ChatResponse(
                status="info_response",
                message="Mã OTP đã hết hạn. Vui lòng thực hiện lại thao tác.",
                data={"operation": "CARD_OPERATION_EXPIRED"},
            )

    # Check cancel
    lower_msg = message.lower()
    if lower_msg in ("hủy", "cancel", "thôi", "dừng", "không"):
        clear_card_operation_state(session_id)
        write_audit_log(
            cif_no=user_id,
            event_type="CARD_OPERATION_CANCELLED",
            actor="user",
            session_id=session_id,
            event_payload={"stage": "WAITING_OTP", "operation": operation},
        )
        return ChatResponse(
            status="info_response",
            message="Đã hủy thao tác thẻ.",
            data={"operation": "CARD_OPERATION_CANCELLED"},
        )

    # Validate OTP format
    if not (message.isdigit() and len(message) == 6):
        return ChatResponse(
            status="needs_otp",
            message="Vui lòng nhập mã OTP 6 chữ số, hoặc gõ 'hủy' để hủy.",
            data={**draft_data, "requires_otp": True},
        )

    # Validate OTP
    if validate_otp(message):
        return _execute_card_operation(
            state, user_id, session_id,
            clear_card_operation_state=clear_card_operation_state,
        )

    # OTP invalid
    state["otp_attempts"] = state.get("otp_attempts", 0) + 1
    remaining = state.get("max_otp_attempts", 3) - state["otp_attempts"]

    write_audit_log(
        cif_no=user_id,
        event_type="CARD_OTP_INVALID",
        actor="system",
        session_id=session_id,
        event_payload={"attempt": state["otp_attempts"], "remaining": remaining},
    )

    if remaining <= 0:
        clear_card_operation_state(session_id)
        write_audit_log(
            cif_no=user_id,
            event_type="CARD_OPERATION_BLOCKED",
            actor="system",
            session_id=session_id,
            event_payload={"reason": "max_otp_attempts_exceeded", "operation": operation},
        )
        return ChatResponse(
            status="info_response",
            message="Bạn đã nhập sai OTP quá số lần cho phép. Thao tác đã bị hủy.",
            data={"operation": "CARD_OPERATION_BLOCKED", "reason": "max_otp_attempts"},
        )

    set_card_operation_state(session_id, state)
    return ChatResponse(
        status="needs_otp",
        message=f"Mã OTP không đúng. Vui lòng nhập lại. (Còn {remaining} lần thử)",
        data={**draft_data, "requires_otp": True, "otp_attempts_remaining": remaining},
    )


def _execute_card_operation(
    state: dict,
    user_id: str,
    session_id: str,
    *,
    clear_card_operation_state,
) -> ChatResponse:
    """Execute the card operation after confirmation (and OTP if required)."""
    import asyncio
    from backend.agents.tools.card_tools import CARD_TOOL_FUNCTIONS

    draft_data = state.get("draft", {})
    operation = draft_data.get("operation", "")
    card_id = draft_data.get("card_id", "")
    context = {"user_id": user_id, "session_id": session_id}

    # Map operation to tool call
    tool_fn = None
    tool_params: dict = {"card_id": card_id}

    if operation == "LOCK_CARD":
        tool_fn = CARD_TOOL_FUNCTIONS["lock_card"]
        tool_params["reason"] = draft_data.get("reason", "USER_REQUEST")
    elif operation == "UNLOCK_CARD":
        tool_fn = CARD_TOOL_FUNCTIONS["unlock_card"]
    elif operation == "REPORT_LOST":
        tool_fn = CARD_TOOL_FUNCTIONS["report_lost_card"]
        tool_params["reason"] = draft_data.get("reason", "LOST")
    elif operation in (
        "ENABLE_ONLINE_PAYMENT", "DISABLE_ONLINE_PAYMENT",
        "ENABLE_INTERNATIONAL_PAYMENT", "DISABLE_INTERNATIONAL_PAYMENT",
    ):
        tool_fn = CARD_TOOL_FUNCTIONS["set_card_control"]
        tool_params["control_name"] = draft_data.get("control_name", "")
        tool_params["enabled"] = draft_data.get("new_value", True)
    elif operation == "CHANGE_LIMIT":
        tool_fn = CARD_TOOL_FUNCTIONS["change_card_limit"]
        tool_params["limit_type"] = draft_data.get("limit_type", "")
        tool_params["new_limit"] = draft_data.get("new_limit", 0)

    if not tool_fn:
        clear_card_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message="Không thể thực hiện thao tác này.",
            data={"operation": operation, "error": "unknown_operation"},
        )

    # Execute tool (sync wrapper for async)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, tool_fn(tool_params, context)).result()
        else:
            result = asyncio.run(tool_fn(tool_params, context))
    except Exception as e:
        logger.error(f"[CARD FSM] Execute error: {e}", exc_info=True)
        clear_card_operation_state(session_id)
        return ChatResponse(
            status="info_response",
            message=f"Lỗi khi thực hiện thao tác: {e}",
            data={"operation": operation, "error": str(e)},
        )

    clear_card_operation_state(session_id)

    write_audit_log(
        cif_no=user_id,
        event_type="CARD_OPERATION_EXECUTED",
        actor="system",
        session_id=session_id,
        event_payload={
            "operation": operation,
            "card_id": card_id,
            "result_status": result.get("status"),
            "draft": draft_data,
        },
    )

    if result.get("status") == "success":
        return ChatResponse(
            status="info_response",
            message=f"✅ {result.get('message', 'Thao tác thành công.')}",
            data={**draft_data, "executed": True, "result": result},
        )

    return ChatResponse(
        status="info_response",
        message=result.get("message", "Không thể thực hiện thao tác."),
        data={**draft_data, "executed": False, "result": result},
    )
