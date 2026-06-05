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


def check_bill_payment_guardrails(
    *,
    amount: int | None,
    biller_code: str | None,
    customer_bill_code: str | None,
    bill_status: str | None = None,
    user_id: str | None = None,
    otp_verified: bool = False,
) -> GuardrailResult:
    """Evaluate guardrails for a bill payment draft.

    Bill payment guardrails:
    1. Amount must be present and > 0
    2. Biller must be active (already checked by resolve_biller_account tool)
    3. Bill must be UNPAID if bill_id is provided
    4. No fraud check needed (billers are trusted entities)
    5. OTP always required

    Args:
        amount: Payment amount in VND.
        biller_code: Biller identifier.
        customer_bill_code: Customer's bill code at the biller.
        bill_status: Status of the bill if bill_id provided.
        user_id: User's CIF number.
        otp_verified: Whether OTP has been provided.

    Returns:
        GuardrailResult.
    """
    # Rule 1: Amount required
    if not amount or amount <= 0:
        logger.warning("[GUARDRAIL] BLOCK — bill payment amount missing or invalid")
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason="Số tiền thanh toán không hợp lệ.",
            risk_level="BLOCK",
        )

    # Rule 2: Biller info required
    if not biller_code or not customer_bill_code:
        logger.warning("[GUARDRAIL] BLOCK — biller info incomplete")
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason="Thông tin nhà cung cấp dịch vụ không đầy đủ.",
            risk_level="BLOCK",
        )

    # Rule 3: Bill must be unpaid if status provided
    if bill_status and bill_status != "UNPAID":
        logger.warning("[GUARDRAIL] BLOCK — bill already paid/cancelled: %s", bill_status)
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason=f"Hóa đơn này đã được thanh toán hoặc đã hủy (trạng thái: {bill_status}).",
            risk_level="BLOCK",
        )

    # Rule 4: OTP verified → allowed
    if otp_verified:
        return GuardrailResult(allowed=True, risk_level="LOW")

    # Rule 5: Require OTP (always LOW risk for bill payment)
    logger.info("[GUARDRAIL] BILL_PAYMENT LOW risk — requiring OTP")
    return GuardrailResult(
        allowed=False,
        requires_otp=True,
        reason="Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận thanh toán.",
        risk_level="LOW",
    )


def check_topup_guardrails(
    *,
    amount: int | None,
    topup_target: str | None,
    topup_type: str | None = "phone",
    otp_verified: bool = False,
) -> GuardrailResult:
    """Evaluate guardrails for a top-up draft.

    Top-up guardrails:
    1. Amount must be present and within allowed range
    2. Target (phone/wallet) must be provided
    3. No fraud check needed (carrier/wallet is trusted)
    4. OTP always required

    Args:
        amount: Top-up amount in VND.
        topup_target: Phone number or wallet ID.
        topup_type: "phone" or "wallet".
        otp_verified: Whether OTP has been provided.

    Returns:
        GuardrailResult.
    """
    # Rule 1: Amount required and in range
    if not amount or amount <= 0:
        logger.warning("[GUARDRAIL] BLOCK — topup amount missing or invalid")
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason="Số tiền nạp không hợp lệ.",
            risk_level="BLOCK",
        )

    # Phone topup: 10k - 500k; wallet: 10k - 10M
    max_amount = 500_000 if topup_type == "phone" else 10_000_000
    if amount > max_amount:
        logger.warning("[GUARDRAIL] BLOCK — topup amount exceeds limit: %s > %s", amount, max_amount)
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason=f"Số tiền nạp vượt quá giới hạn cho phép ({max_amount:,} VND).",
            risk_level="BLOCK",
        )

    if amount < 10_000:
        logger.warning("[GUARDRAIL] BLOCK — topup amount below minimum")
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason="Số tiền nạp tối thiểu là 10,000 VND.",
            risk_level="BLOCK",
        )

    # Rule 2: Target required
    if not topup_target:
        logger.warning("[GUARDRAIL] BLOCK — topup target missing")
        return GuardrailResult(
            allowed=False,
            blocked=True,
            reason="Vui lòng cung cấp số điện thoại hoặc ví cần nạp.",
            risk_level="BLOCK",
        )

    # Rule 3: OTP verified → allowed
    if otp_verified:
        return GuardrailResult(allowed=True, risk_level="LOW")

    # Rule 4: Require OTP (always LOW risk for topup)
    logger.info("[GUARDRAIL] TOP_UP LOW risk — requiring OTP")
    return GuardrailResult(
        allowed=False,
        requires_otp=True,
        reason="Vui lòng nhập mã OTP đã gửi đến số điện thoại của bạn để xác nhận nạp tiền.",
        risk_level="LOW",
    )
