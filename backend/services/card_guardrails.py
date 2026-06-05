"""Guardrails for card operations.

Determines:
1. Whether the operation is allowed (based on card status)
2. Whether OTP is required
3. Risk level
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CardGuardrailResult:
    """Result of card operation guardrail evaluation."""
    allowed: bool
    requires_otp: bool = False
    blocked: bool = False
    reason: str | None = None
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH


# Operations that do NOT require OTP (safety/disable actions)
NO_OTP_OPERATIONS = {
    "LOCK_CARD",
    "REPORT_LOST",
    "DISABLE_ONLINE_PAYMENT",
    "DISABLE_INTERNATIONAL_PAYMENT",
    "DISABLE_ATM_WITHDRAWAL",
    "DISABLE_POS_PAYMENT",
    "DISABLE_CONTACTLESS",
}

# Operations that require OTP (enable/sensitive actions)
OTP_REQUIRED_OPERATIONS = {
    "UNLOCK_CARD",
    "ENABLE_ONLINE_PAYMENT",
    "ENABLE_INTERNATIONAL_PAYMENT",
    "ENABLE_ATM_WITHDRAWAL",
    "ENABLE_POS_PAYMENT",
    "ENABLE_CONTACTLESS",
    "CHANGE_LIMIT",
}


def check_card_operation_guardrails(
    *,
    operation: str,
    card_status: str | None = None,
    otp_verified: bool = False,
) -> CardGuardrailResult:
    """Evaluate guardrails for a card operation.

    Args:
        operation: The card operation (LOCK_CARD, UNLOCK_CARD, etc.)
        card_status: Current card status.
        otp_verified: Whether OTP was already verified.

    Returns:
        CardGuardrailResult
    """
    # Read-only operations always allowed
    if operation in ("VIEW_CARD_INFO", "VIEW_CARD_TRANSACTIONS"):
        return CardGuardrailResult(allowed=True, risk_level="LOW")

    # Status-based blocks
    if operation == "LOCK_CARD":
        if card_status != "ACTIVE":
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason=f"Không thể khóa thẻ ở trạng thái {card_status}.",
            )

    if operation == "UNLOCK_CARD":
        if card_status in ("LOST", "STOLEN", "BLOCKED_BY_BANK"):
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason=f"Không thể mở khóa thẻ ở trạng thái {card_status}. Vui lòng liên hệ ngân hàng.",
            )
        if card_status in ("EXPIRED", "CLOSED"):
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason=f"Thẻ đã {card_status}, không thể mở khóa.",
            )
        if card_status == "ACTIVE":
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason="Thẻ đang hoạt động, không cần mở khóa.",
            )

    if operation == "REPORT_LOST":
        if card_status in ("LOST", "STOLEN"):
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason="Thẻ đã được báo mất trước đó.",
            )
        if card_status in ("EXPIRED", "CLOSED"):
            return CardGuardrailResult(
                allowed=False, blocked=True,
                reason=f"Thẻ đã {card_status}, không cần báo mất.",
            )

    # Controls and limit changes require ACTIVE card
    if operation in OTP_REQUIRED_OPERATIONS or operation in NO_OTP_OPERATIONS:
        if operation not in ("LOCK_CARD", "REPORT_LOST", "UNLOCK_CARD"):
            if card_status != "ACTIVE":
                return CardGuardrailResult(
                    allowed=False, blocked=True,
                    reason=f"Thẻ phải đang ACTIVE để thay đổi cài đặt (hiện tại: {card_status}).",
                )

    # Check OTP requirement
    if operation in OTP_REQUIRED_OPERATIONS:
        if otp_verified:
            return CardGuardrailResult(allowed=True, risk_level="LOW")
        logger.info("[CARD GUARDRAIL] %s requires OTP", operation)
        return CardGuardrailResult(
            allowed=False,
            requires_otp=True,
            reason="Vui lòng nhập mã OTP để xác nhận thao tác.",
            risk_level="MEDIUM",
        )

    # No OTP needed — allow with confirmation only
    if operation in NO_OTP_OPERATIONS:
        return CardGuardrailResult(allowed=True, risk_level="LOW")

    # Unknown operation — require OTP to be safe
    logger.warning("[CARD GUARDRAIL] Unknown operation: %s", operation)
    return CardGuardrailResult(
        allowed=False, requires_otp=True,
        reason="Vui lòng nhập mã OTP để xác nhận.",
        risk_level="MEDIUM",
    )
