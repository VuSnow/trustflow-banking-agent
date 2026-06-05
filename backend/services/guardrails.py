"""Hard guardrails — deterministic safety checks that LLM cannot override.

These are code-level rules enforced AFTER the agent produces a draft.
No matter what the LLM decides, these constraints are always applied.

ALL transactions require OTP (standard banking practice in Vietnam).
Risk levels determine the warning message shown BEFORE OTP:
- LOW: Standard OTP (no warning)
- MEDIUM: Warning about suspicious reports + OTP
- HIGH: Strong fraud warning + OTP
- BLOCK: Transaction rejected outright, cannot proceed
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result of guardrail evaluation."""
    allowed: bool
    requires_otp: bool = False
    blocked: bool = False
    warning_message: str | None = None
    reason: str | None = None
    risk_level: str | None = None  # LOW, MEDIUM, HIGH, BLOCK


def check_transaction_guardrails(
    *,
    amount: int | None,
    fraud_screening: dict | None = None,
    otp_verified: bool = False,
) -> GuardrailResult:
    """Evaluate hard guardrails for a transaction draft.

    ALL transactions require OTP. This function determines:
    1. Whether to BLOCK (no OTP possible)
    2. What warning to show before OTP prompt
    3. Whether OTP has already been verified

    Args:
        amount: Transfer amount in VND.
        fraud_screening: Fraud screening result from check_fraud_risk tool.
        otp_verified: Whether user has provided valid OTP.

    Returns:
        GuardrailResult indicating if the action is allowed to proceed.
    """

    # Rule 1: BLOCK — fraud CRITICAL, no way to proceed
    if fraud_screening and fraud_screening.get("is_reported"):
        risk_level = fraud_screening.get("risk_level", "LOW")

        if risk_level == "CRITICAL":
            logger.warning("[GUARDRAIL] BLOCK — fraud risk CRITICAL")
            return GuardrailResult(
                allowed=False,
                blocked=True,
                reason=(
                    "⚠️ Tài khoản này đã bị cơ quan chức năng xác nhận là tài khoản lừa đảo. "
                    "Giao dịch không thể thực hiện."
                ),
                risk_level="BLOCK",
            )

    # Rule 2: All non-blocked transactions require OTP
    if otp_verified:
        return GuardrailResult(allowed=True, risk_level="LOW")

    # Determine warning message based on risk
    warning = None
    risk = "LOW"

    if fraud_screening and fraud_screening.get("is_reported"):
        risk_level = fraud_screening.get("risk_level", "LOW")

        if risk_level == "HIGH":
            risk = "HIGH"
            report_count = fraud_screening.get("report_count", 0)
            warning = (
                f"⚠️ CẢNH BÁO: Tài khoản nhận có {report_count} báo cáo nghi ngờ lừa đảo "
                f"với mức rủi ro CAO. Vui lòng cân nhắc kỹ trước khi tiếp tục."
            )
        elif risk_level == "MEDIUM":
            risk = "MEDIUM"
            report_count = fraud_screening.get("report_count", 0)
            warning = (
                f"⚠️ Lưu ý: Tài khoản nhận có {report_count} báo cáo đáng ngờ. "
                "Hãy kiểm tra kỹ thông tin người nhận."
            )

    # OTP required for all transactions
    logger.info("[GUARDRAIL] %s risk — requiring OTP", risk)
    reason = "Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận giao dịch."
    if warning:
        reason = warning + "\n\n" + reason

    return GuardrailResult(
        allowed=False,
        requires_otp=True,
        warning_message=warning,
        reason=reason,
        risk_level=risk,
    )


def validate_otp(otp: str) -> bool:
    """Validate OTP (simulated — accepts any 6-digit string)."""
    return otp is not None and len(otp) == 6 and otp.isdigit()
