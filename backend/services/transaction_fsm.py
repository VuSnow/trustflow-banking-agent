"""FSM-based intercept for transaction states (confirmation & OTP).

Extracted from main.py to keep the entrypoint slim.
"""
from __future__ import annotations

import logging
from datetime import datetime

from backend.models import ActionDraft, ChatRequest, ChatResponse
from backend.services.audit_log import write_audit_log
from backend.services.confirmation_classifier import classify_confirmation
from backend.services.guardrails import validate_otp

logger = logging.getLogger(__name__)


async def handle_transaction_state_intercept(
    request: ChatRequest,
    *,
    get_transaction_state,
    set_transaction_state,
    clear_transaction_state,
    clear_pipeline_state,
) -> ChatResponse | None:
    """FSM-based intercept for transaction states.

    Handles:
    - WAITING_CONFIRMATION: LLM-based classifier → CONFIRM/CANCEL/MODIFY/UNCLEAR
    - WAITING_OTP: deterministic OTP validation (no LLM, no classifier)

    Frozen draft immutability: when in WAITING_CONFIRMATION or WAITING_OTP,
    the draft cannot be modified. MODIFY intent requires cancellation first.
    """
    tx_state = get_transaction_state(request.session_id)
    if not tx_state:
        return None

    fsm_state = tx_state.get("fsm_state")
    message = request.message.strip()
    user_id = request.user_id

    # ─── WAITING_CONFIRMATION: use LLM classifier ────────────────────────
    if fsm_state == "WAITING_CONFIRMATION":
        return await _handle_waiting_confirmation(
            tx_state, message, user_id, request.session_id,
            set_transaction_state=set_transaction_state,
            clear_transaction_state=clear_transaction_state,
            clear_pipeline_state=clear_pipeline_state,
        )

    # ─── WAITING_OTP: deterministic validation, no LLM ───────────────────
    if fsm_state == "WAITING_OTP":
        return _handle_waiting_otp(
            tx_state, message, user_id, request.session_id,
            set_transaction_state=set_transaction_state,
            clear_transaction_state=clear_transaction_state,
            clear_pipeline_state=clear_pipeline_state,
        )

    # Unknown/completed state — don't intercept
    return None


# ─── WAITING_CONFIRMATION handler ────────────────────────────────────────────


async def _handle_waiting_confirmation(
    tx_state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_transaction_state,
    clear_transaction_state,
    clear_pipeline_state,
) -> ChatResponse:
    """Handle user reply while in WAITING_CONFIRMATION state."""
    draft_data = tx_state.get("draft", {})
    draft_summary = (
        f"{draft_data.get('amount', '?'):,} {draft_data.get('currency', 'VND')} "
        f"→ {draft_data.get('recipient_name', '?')} "
        f"({draft_data.get('recipient_account', '?')}) "
        f"@ {draft_data.get('bank_name') or draft_data.get('recipient_bank', '?')}"
    )

    result = await classify_confirmation(message, draft_summary=draft_summary)
    classification = result["classification"]

    write_audit_log(
        cif_no=user_id,
        event_type="CONFIRMATION_CLASSIFIED",
        actor="classifier",
        session_id=session_id,
        event_payload={
            "user_message": message,
            "classification": classification,
            "reason": result.get("reason", ""),
        },
    )

    if classification == "CONFIRM":
        return _confirm_transaction(
            tx_state, user_id, session_id,
            set_transaction_state=set_transaction_state,
        )

    if classification == "CANCEL":
        return _cancel_transaction(
            user_id, session_id, stage="WAITING_CONFIRMATION",
            clear_transaction_state=clear_transaction_state,
            clear_pipeline_state=clear_pipeline_state,
        )

    if classification == "MODIFY":
        return ChatResponse(
            status="info_response",
            message=(
                "Giao dịch đang chờ xác nhận không thể sửa đổi. "
                "Bạn có thể hủy giao dịch hiện tại và tạo giao dịch mới với thông tin đúng.\n\n"
                "Bạn muốn hủy giao dịch này không?"
            ),
            data={**tx_state["draft"], "requires_confirmation": True, "modify_requested": True},
        )

    # UNCLEAR
    return ChatResponse(
        status="clarification_needed",
        message="Tôi chưa hiểu rõ ý bạn. Bạn muốn xác nhận chuyển tiền hay hủy giao dịch?",
        data={**tx_state["draft"], "requires_confirmation": True},
    )


def _confirm_transaction(tx_state, user_id, session_id, *, set_transaction_state):
    """Transition WAITING_CONFIRMATION → WAITING_OTP."""
    tx_state["fsm_state"] = "WAITING_OTP"
    tx_state["otp_created_at"] = datetime.now().isoformat(timespec="seconds")
    set_transaction_state(session_id, tx_state)

    write_audit_log(
        cif_no=user_id,
        event_type="TRANSACTION_CONFIRMED",
        actor="user",
        session_id=session_id,
        event_payload={"fsm_transition": "WAITING_CONFIRMATION → WAITING_OTP"},
    )

    logger.info(f"[CONFIRM] User confirmed, moving to WAITING_OTP session={session_id}")

    warning = tx_state.get("warning_message")
    otp_message = "Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận giao dịch."
    if warning:
        otp_message = warning + "\n\n" + otp_message

    return ChatResponse(
        status="needs_otp",
        message=otp_message,
        data={**tx_state["draft"], "requires_otp": True, "risk_level": tx_state.get("risk_level")},
    )


def _cancel_transaction(user_id, session_id, *, stage, clear_transaction_state, clear_pipeline_state):
    """Cancel the transaction and clear state."""
    clear_transaction_state(session_id)
    clear_pipeline_state(session_id)

    write_audit_log(
        cif_no=user_id,
        event_type="TRANSACTION_CANCELLED",
        actor="user",
        session_id=session_id,
        event_payload={"stage": stage},
    )

    return ChatResponse(
        status="info_response",
        message="Đã hủy giao dịch. Nếu bạn cần hỗ trợ thêm, hãy cho tôi biết.",
        data={"operation": "TRANSACTION_CANCELLED"},
    )


# ─── WAITING_OTP handler ─────────────────────────────────────────────────────


def _handle_waiting_otp(
    tx_state: dict,
    message: str,
    user_id: str,
    session_id: str,
    *,
    set_transaction_state,
    clear_transaction_state,
    clear_pipeline_state,
) -> ChatResponse | None:
    """Handle user reply while in WAITING_OTP state."""

    # Check OTP expiry
    otp_created = tx_state.get("otp_created_at")
    otp_expires = tx_state.get("otp_expires_seconds", 300)
    if otp_created:
        created_dt = datetime.fromisoformat(otp_created)
        elapsed = (datetime.now() - created_dt).total_seconds()
        if elapsed > otp_expires:
            tx_state["fsm_state"] = "BLOCKED"
            clear_transaction_state(session_id)
            clear_pipeline_state(session_id)

            write_audit_log(
                cif_no=user_id,
                event_type="OTP_EXPIRED",
                actor="system",
                session_id=session_id,
                event_payload={"elapsed_seconds": elapsed, "limit_seconds": otp_expires},
            )

            return ChatResponse(
                status="info_response",
                message="Mã OTP đã hết hạn. Giao dịch đã bị hủy. Vui lòng thực hiện lại.",
                data={"operation": "TRANSACTION_EXPIRED", "reason": "otp_timeout"},
            )

    # Check for cancel intent
    lower_msg = message.lower()
    if lower_msg in ("hủy", "cancel", "thôi", "dừng", "không"):
        return _cancel_transaction(
            user_id, session_id, stage="WAITING_OTP",
            clear_transaction_state=clear_transaction_state,
            clear_pipeline_state=clear_pipeline_state,
        )

    # Check if message looks like OTP (6 digits)
    if not (message.isdigit() and len(message) == 6):
        return ChatResponse(
            status="needs_otp",
            message="Vui lòng nhập mã OTP 6 chữ số, hoặc gõ 'hủy' để hủy giao dịch.",
            data={**tx_state["draft"], "requires_otp": True},
        )

    # Validate OTP deterministically — NEVER send to LLM
    saved_draft_data = tx_state["draft"]

    if validate_otp(message):
        return _otp_success(
            tx_state, saved_draft_data, user_id, session_id,
            clear_transaction_state=clear_transaction_state,
            clear_pipeline_state=clear_pipeline_state,
        )

    return _otp_failure(
        tx_state, saved_draft_data, user_id, session_id,
        set_transaction_state=set_transaction_state,
        clear_transaction_state=clear_transaction_state,
        clear_pipeline_state=clear_pipeline_state,
    )


def _otp_success(tx_state, saved_draft_data, user_id, session_id, *, clear_transaction_state, clear_pipeline_state):
    """Handle valid OTP."""
    tx_state["fsm_state"] = "OTP_VERIFIED"
    clear_transaction_state(session_id)
    clear_pipeline_state(session_id)
    draft = ActionDraft(**saved_draft_data)

    write_audit_log(
        cif_no=user_id,
        event_type="OTP_VERIFIED",
        actor="system",
        session_id=session_id,
        event_payload={
            "draft": saved_draft_data,
            "fsm_transition": "WAITING_OTP → OTP_VERIFIED",
        },
    )

    logger.info(f"[OTP] Valid for session={session_id}")
    return ChatResponse(
        status="draft_ready",
        message=(
            f"✅ OTP xác thực thành công. Giao dịch chuyển "
            f"{draft.amount:,} {draft.currency} đến {draft.recipient_name} "
            f"({draft.recipient_account}) đã sẵn sàng thực hiện."
            if draft.amount
            else "✅ OTP xác thực thành công. Giao dịch đã sẵn sàng thực hiện."
        ),
        data={**draft.model_dump(), "otp_verified": True},
    )


def _otp_failure(tx_state, saved_draft_data, user_id, session_id, *, set_transaction_state, clear_transaction_state, clear_pipeline_state):
    """Handle invalid OTP with attempt tracking."""
    tx_state["otp_attempts"] = tx_state.get("otp_attempts", 0) + 1
    remaining = tx_state.get("max_otp_attempts", 3) - tx_state["otp_attempts"]

    write_audit_log(
        cif_no=user_id,
        event_type="OTP_INVALID",
        actor="system",
        session_id=session_id,
        event_payload={
            "attempt": tx_state["otp_attempts"],
            "remaining": remaining,
        },
    )

    if remaining <= 0:
        tx_state["fsm_state"] = "BLOCKED"
        clear_transaction_state(session_id)
        clear_pipeline_state(session_id)

        write_audit_log(
            cif_no=user_id,
            event_type="TRANSACTION_BLOCKED",
            actor="system",
            session_id=session_id,
            event_payload={"reason": "max_otp_attempts_exceeded"},
        )

        logger.warning(f"[OTP] Max attempts reached for session={session_id}")
        return ChatResponse(
            status="info_response",
            message="Bạn đã nhập sai OTP quá số lần cho phép. Giao dịch đã bị hủy vì lý do bảo mật.",
            data={"operation": "TRANSACTION_BLOCKED", "reason": "max_otp_attempts"},
        )

    set_transaction_state(session_id, tx_state)
    logger.info(f"[OTP] Invalid, {remaining} attempts left")
    return ChatResponse(
        status="needs_otp",
        message=f"Mã OTP không đúng. Vui lòng nhập lại. (Còn {remaining} lần thử)",
        data={**saved_draft_data, "requires_otp": True, "otp_attempts_remaining": remaining},
    )
