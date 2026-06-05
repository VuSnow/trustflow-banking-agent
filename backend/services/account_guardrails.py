"""Guardrails for account operations.

Determines:
1. Whether the operation requires confirmation
2. Whether OTP is required
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AccountGuardrailResult:
    """Result of account operation guardrail evaluation."""
    requires_confirmation: bool = True
    requires_otp: bool = False
    blocked: bool = False
    reason: str | None = None


def check_account_operation_guardrails(*, operation: str) -> AccountGuardrailResult:
    """Evaluate guardrails for an account operation.

    - OPEN_ACCOUNT: confirmation only, no OTP
    - CLOSE_ACCOUNT: confirmation + OTP (irreversible)
    - UPDATE_NICKNAME: no confirmation, no OTP (executed directly by agent)
    """
    if operation == "OPEN_ACCOUNT":
        return AccountGuardrailResult(
            requires_confirmation=True,
            requires_otp=False,
        )

    if operation == "CLOSE_ACCOUNT":
        return AccountGuardrailResult(
            requires_confirmation=True,
            requires_otp=True,
        )

    if operation == "UPDATE_NICKNAME":
        return AccountGuardrailResult(
            requires_confirmation=False,
            requires_otp=False,
        )

    # Unknown — be safe
    logger.warning("[ACCOUNT GUARDRAIL] Unknown operation: %s", operation)
    return AccountGuardrailResult(
        requires_confirmation=True,
        requires_otp=True,
    )
