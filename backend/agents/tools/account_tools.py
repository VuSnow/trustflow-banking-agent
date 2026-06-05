"""Account operation tools — tool set for AccountOperationAgent.

Tools:
1. get_user_accounts: List all accounts belonging to user
2. get_account_detail: Get full account detail
3. list_account_products: List available account products
4. check_account_opening_eligibility: Validate if user can open a product
5. open_account: Create a new account
6. close_account: Close an account (set CLOSED)
7. update_account_nickname: Update account nickname
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras

from backend.config import DATABASE_URL

logger = logging.getLogger(__name__)


async def get_user_accounts(params: dict, context: dict) -> dict:
    """List all accounts belonging to user."""
    user_id = context.get("user_id", "")
    if not user_id:
        return {"status": "failed", "message": "user_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT account_id, account_no, account_type, currency,
                           balance, available_balance, status, is_primary,
                           nickname, opened_at
                    FROM accounts
                    WHERE cif_no = %s
                    ORDER BY is_primary DESC, opened_at ASC
                    """,
                    (user_id,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    r["account_id"] = str(r["account_id"])
            return {"status": "success", "accounts": rows, "count": len(rows)}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] get_user_accounts error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def get_account_detail(params: dict, context: dict) -> dict:
    """Get full account detail. Validates ownership."""
    user_id = context.get("user_id", "")
    account_no = params.get("account_no")
    account_id = params.get("account_id")

    if not user_id:
        return {"status": "failed", "message": "user_id is required."}
    if not account_no and not account_id:
        return {"status": "failed", "message": "account_no or account_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if account_id:
                    cur.execute(
                        """
                        SELECT account_id, account_no, account_type, currency,
                               balance, available_balance, status, is_primary,
                               nickname, opened_at, closed_at
                        FROM accounts
                        WHERE account_id = %s::uuid AND cif_no = %s
                        """,
                        (account_id, user_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT account_id, account_no, account_type, currency,
                               balance, available_balance, status, is_primary,
                               nickname, opened_at, closed_at
                        FROM accounts
                        WHERE account_no = %s AND cif_no = %s
                        """,
                        (account_no, user_id),
                    )
                row = cur.fetchone()

            if not row:
                return {"status": "not_found", "message": "Không tìm thấy tài khoản hoặc tài khoản không thuộc về bạn."}

            result = dict(row)
            result["account_id"] = str(result["account_id"])
            return {"status": "success", "account": result}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] get_account_detail error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def list_account_products(params: dict, context: dict) -> dict:
    """List available account products that can be opened."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT product_code, product_name, account_type, currency,
                           monthly_fee, opening_fee, max_accounts_per_customer,
                           description
                    FROM account_products
                    WHERE is_active = true
                    ORDER BY product_code
                    """
                )
                rows = [dict(r) for r in cur.fetchall()]
            return {"status": "success", "products": rows, "count": len(rows)}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] list_account_products error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def check_account_opening_eligibility(params: dict, context: dict) -> dict:
    """Check if user is eligible to open a specific account product.

    Checks:
    1. Customer is ACTIVE
    2. KYC is VERIFIED or ENHANCED
    3. Product is active
    4. User has not exceeded max_accounts_per_customer for this product
    """
    user_id = context.get("user_id", "")
    product_code = params.get("product_code")

    if not product_code:
        return {"status": "failed", "message": "product_code is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get customer info
                cur.execute(
                    "SELECT status, kyc_level FROM customers WHERE cif_no = %s",
                    (user_id,),
                )
                customer = cur.fetchone()
                if not customer:
                    return {"status": "failed", "eligible": False, "reasons": ["Không tìm thấy thông tin khách hàng."]}

                reasons = []

                if customer["status"] != "ACTIVE":
                    reasons.append(f"Tài khoản khách hàng không hoạt động (status: {customer['status']}).")

                if customer["kyc_level"] not in ("VERIFIED", "ENHANCED"):
                    reasons.append(f"Chưa hoàn tất xác minh danh tính (KYC: {customer['kyc_level']}). Cần mức VERIFIED trở lên.")

                # Get product info
                cur.execute(
                    "SELECT * FROM account_products WHERE product_code = %s AND is_active = true",
                    (product_code,),
                )
                product = cur.fetchone()
                if not product:
                    reasons.append(f"Sản phẩm {product_code} không tồn tại hoặc đã ngừng cung cấp.")
                    return {"status": "failed", "eligible": False, "reasons": reasons}

                # Count existing accounts of same type
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM accounts
                    WHERE cif_no = %s AND account_type = %s AND currency = %s AND status = 'ACTIVE'
                    """,
                    (user_id, product["account_type"], product["currency"]),
                )
                count_row = cur.fetchone()
                current_count = count_row["cnt"] if count_row else 0

                if current_count >= product["max_accounts_per_customer"]:
                    reasons.append(
                        f"Bạn đã có {current_count}/{product['max_accounts_per_customer']} "
                        f"tài khoản {product['product_name']}. Không thể mở thêm."
                    )

            if reasons:
                return {"status": "failed", "eligible": False, "reasons": reasons}

            return {
                "status": "success",
                "eligible": True,
                "product": dict(product),
                "current_account_count": current_count,
                "reasons": [],
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] check_eligibility error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def open_account(params: dict, context: dict) -> dict:
    """Create a new account for the user.

    Requires product_code. Optionally accepts nickname and purpose.
    """
    user_id = context.get("user_id", "")
    product_code = params.get("product_code")
    nickname = params.get("nickname")
    purpose = params.get("purpose")

    if not product_code:
        return {"status": "failed", "message": "product_code is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get product
                cur.execute(
                    "SELECT * FROM account_products WHERE product_code = %s AND is_active = true",
                    (product_code,),
                )
                product = cur.fetchone()
                if not product:
                    return {"status": "failed", "message": f"Sản phẩm {product_code} không khả dụng."}

                # Generate account number (mock: random 11 digits)
                import random
                account_no = str(random.randint(10000000000, 99999999999))

                # Create account
                new_account_id = str(uuid.uuid4())
                now = datetime.now().isoformat(timespec="seconds")

                cur.execute(
                    """
                    INSERT INTO accounts (account_id, account_no, cif_no, account_type, currency,
                                          balance, available_balance, status, is_primary, nickname, opened_at)
                    VALUES (%s::uuid, %s, %s, %s, %s, 0, 0, 'ACTIVE', false, %s, %s)
                    """,
                    (new_account_id, account_no, user_id,
                     product["account_type"], product["currency"],
                     nickname, now),
                )
            conn.commit()

            return {
                "status": "success",
                "message": f"Đã mở {product['product_name']} thành công.",
                "account": {
                    "account_id": new_account_id,
                    "account_no": account_no,
                    "account_type": product["account_type"],
                    "currency": product["currency"],
                    "status": "ACTIVE",
                    "nickname": nickname,
                    "monthly_fee": product["monthly_fee"],
                },
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] open_account error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def close_account(params: dict, context: dict) -> dict:
    """Close an account. Validates eligibility before closing.

    Checks:
    - Account belongs to user
    - Account is ACTIVE
    - Balance is 0
    - Not primary account
    - No pending transactions
    """
    user_id = context.get("user_id", "")
    account_no = params.get("account_no")
    account_id = params.get("account_id")

    if not account_no and not account_id:
        return {"status": "failed", "message": "account_no or account_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get account
                if account_id:
                    cur.execute(
                        "SELECT * FROM accounts WHERE account_id = %s::uuid AND cif_no = %s",
                        (account_id, user_id),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM accounts WHERE account_no = %s AND cif_no = %s",
                        (account_no, user_id),
                    )
                account = cur.fetchone()

                if not account:
                    return {"status": "failed", "message": "Tài khoản không tồn tại hoặc không thuộc về bạn."}

                reasons = []

                if account["status"] != "ACTIVE":
                    reasons.append(f"Tài khoản đang ở trạng thái {account['status']}, không thể đóng.")

                if account["balance"] and account["balance"] > 0:
                    reasons.append(
                        f"Tài khoản còn số dư {account['balance']:,} {account['currency']}. "
                        "Vui lòng chuyển hết số dư sang tài khoản khác trước khi đóng."
                    )

                if account["is_primary"]:
                    reasons.append(
                        "Đây là tài khoản chính. Vui lòng đổi tài khoản chính trước khi đóng."
                    )

                # Check pending transactions
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM transactions
                    WHERE (source_account_no = %s OR destination_account_no = %s)
                      AND status = 'PENDING'
                    """,
                    (account["account_no"], account["account_no"]),
                )
                pending = cur.fetchone()
                if pending and pending["cnt"] > 0:
                    reasons.append(f"Có {pending['cnt']} giao dịch đang chờ xử lý.")

                if reasons:
                    return {"status": "failed", "eligible": False, "reasons": reasons}

                # Close the account
                now = datetime.now().isoformat(timespec="seconds")
                cur.execute(
                    "UPDATE accounts SET status = 'CLOSED', closed_at = %s WHERE account_id = %s",
                    (now, account["account_id"]),
                )
            conn.commit()

            return {
                "status": "success",
                "message": f"Đã đóng tài khoản {account['account_no']} thành công.",
                "account_no": account["account_no"],
                "closed_at": now,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] close_account error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def update_account_nickname(params: dict, context: dict) -> dict:
    """Update account nickname. Low-risk operation."""
    user_id = context.get("user_id", "")
    account_no = params.get("account_no")
    account_id = params.get("account_id")
    new_nickname = params.get("nickname")

    if not account_no and not account_id:
        return {"status": "failed", "message": "account_no or account_id is required."}
    if not new_nickname:
        return {"status": "failed", "message": "nickname is required."}
    if len(new_nickname) > 100:
        return {"status": "failed", "message": "Nickname tối đa 100 ký tự."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if account_id:
                    cur.execute(
                        "SELECT account_id, account_no, nickname, status FROM accounts WHERE account_id = %s::uuid AND cif_no = %s",
                        (account_id, user_id),
                    )
                else:
                    cur.execute(
                        "SELECT account_id, account_no, nickname, status FROM accounts WHERE account_no = %s AND cif_no = %s",
                        (account_no, user_id),
                    )
                account = cur.fetchone()

                if not account:
                    return {"status": "failed", "message": "Tài khoản không tồn tại hoặc không thuộc về bạn."}

                if account["status"] != "ACTIVE":
                    return {"status": "failed", "message": f"Không thể đổi tên tài khoản ở trạng thái {account['status']}."}

                old_nickname = account["nickname"]
                cur.execute(
                    "UPDATE accounts SET nickname = %s WHERE account_id = %s",
                    (new_nickname, account["account_id"]),
                )
            conn.commit()

            return {
                "status": "success",
                "message": f"Đã đổi tên tài khoản {account['account_no']} thành \"{new_nickname}\".",
                "account_no": account["account_no"],
                "old_nickname": old_nickname,
                "new_nickname": new_nickname,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[ACCOUNT TOOL] update_nickname error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


# ============================================================
# TOOL DEFINITIONS (for OpenAI function calling)
# ============================================================

ACCOUNT_TOOLS = [
    {
        "name": "get_user_accounts",
        "description": (
            "List all accounts belonging to the current user. "
            "Returns account numbers, types, currencies, balances, status, and primary flag."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_account_detail",
        "description": (
            "Get full detail of a specific account. Validates ownership. "
            "Use when you need to check balance, status, or other details before an operation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_no": {"type": "string", "description": "Account number."},
                "account_id": {"type": "string", "description": "Account UUID (if known)."},
            },
        },
    },
    {
        "name": "list_account_products",
        "description": (
            "List available account products that can be opened. "
            "Returns product codes, names, types, currencies, fees, and limits. "
            "Use when user wants to open an account but hasn't specified which type."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "check_account_opening_eligibility",
        "description": (
            "Check if user is eligible to open a specific account product. "
            "Validates: customer active, KYC verified, product active, max account count. "
            "Call BEFORE creating an open account draft."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_code": {"type": "string", "description": "Product code: CURRENT_VND, CURRENT_USD, or SAVINGS_VND."},
            },
            "required": ["product_code"],
        },
    },
    {
        "name": "open_account",
        "description": (
            "Create a new account for the user. Requires product_code. "
            "Only call AFTER eligibility check passes AND user confirms."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_code": {"type": "string", "description": "Product code to open."},
                "nickname": {"type": "string", "description": "Optional friendly name for the account."},
                "purpose": {"type": "string", "description": "Purpose: daily_spending, salary, savings, international."},
            },
            "required": ["product_code"],
        },
    },
    {
        "name": "close_account",
        "description": (
            "Close an account. Validates: belongs to user, ACTIVE, balance=0, not primary, no pending transactions. "
            "Only call AFTER user confirms."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_no": {"type": "string", "description": "Account number to close."},
                "account_id": {"type": "string", "description": "Account UUID (if known)."},
            },
        },
    },
    {
        "name": "update_account_nickname",
        "description": (
            "Update account nickname/friendly name. Low-risk operation. "
            "Account must be ACTIVE and belong to user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_no": {"type": "string", "description": "Account number."},
                "account_id": {"type": "string", "description": "Account UUID (if known)."},
                "nickname": {"type": "string", "description": "New nickname (max 100 chars)."},
            },
            "required": ["nickname"],
        },
    },
]

ACCOUNT_TOOL_FUNCTIONS: dict[str, Any] = {
    "get_user_accounts": get_user_accounts,
    "get_account_detail": get_account_detail,
    "list_account_products": list_account_products,
    "check_account_opening_eligibility": check_account_opening_eligibility,
    "open_account": open_account,
    "close_account": close_account,
    "update_account_nickname": update_account_nickname,
}
