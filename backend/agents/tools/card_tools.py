"""Card operation tools — tool set for CardOperationAgent.

Tools:
1. get_user_cards: List all cards belonging to user
2. get_card_detail: Get full card detail including controls and limits
3. lock_card: Lock a card (TEMP_LOCKED)
4. unlock_card: Unlock a TEMP_LOCKED card
5. report_lost_card: Mark card as LOST (permanent, cannot unlock)
6. set_card_control: Toggle a card control (online_payment, international, etc.)
7. change_card_limit: Change a card limit
8. get_card_transactions: Get recent card transactions
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


# ============================================================
# TOOL FUNCTIONS
# ============================================================


async def get_user_cards(params: dict, context: dict) -> dict:
    """List all cards belonging to user. Returns masked info only."""
    user_id = context.get("user_id", "")
    if not user_id:
        return {"status": "failed", "message": "user_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT card_id, masked_card_no, card_type, card_network,
                           account_no, status, credit_limit, available_limit, issued_at
                    FROM cards
                    WHERE cif_no = %s
                    ORDER BY issued_at DESC
                    """,
                    (user_id,),
                )
                rows = [dict(r) for r in cur.fetchall()]
            return {
                "status": "success",
                "cards": rows,
                "count": len(rows),
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] get_user_cards error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def get_card_detail(params: dict, context: dict) -> dict:
    """Get full card detail including controls and limits.

    Accepts card_id or last4 + optional filters (card_type, card_network).
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    last4 = params.get("last4")
    card_type = params.get("card_type")
    card_network = params.get("card_network")

    if not user_id:
        return {"status": "failed", "message": "user_id is required."}
    if not card_id and not last4:
        return {"status": "failed", "message": "card_id or last4 is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Build query
                conditions = ["c.cif_no = %s"]
                query_params: list[Any] = [user_id]

                if card_id:
                    conditions.append("c.card_id = %s::uuid")
                    query_params.append(card_id)
                elif last4:
                    conditions.append("c.masked_card_no LIKE %s")
                    query_params.append(f"%{last4}")

                if card_type:
                    conditions.append("c.card_type = %s")
                    query_params.append(card_type.upper())

                if card_network:
                    conditions.append("c.card_network = %s")
                    query_params.append(card_network.upper())

                where_clause = " AND ".join(conditions)

                cur.execute(
                    f"""
                    SELECT c.card_id, c.masked_card_no, c.card_type, c.card_network,
                           c.account_no, c.status, c.credit_limit, c.available_limit, c.issued_at,
                           cc.online_payment_enabled, cc.international_payment_enabled,
                           cc.atm_withdrawal_enabled, cc.pos_payment_enabled, cc.contactless_enabled,
                           cl.daily_atm_limit, cl.daily_pos_limit, cl.daily_online_limit,
                           cl.per_transaction_limit, cl.max_daily_atm_limit,
                           cl.max_daily_pos_limit, cl.max_daily_online_limit,
                           cl.max_per_transaction_limit
                    FROM cards c
                    LEFT JOIN card_controls cc ON c.card_id = cc.card_id
                    LEFT JOIN card_limits cl ON c.card_id = cl.card_id
                    WHERE {where_clause}
                    """,
                    query_params,
                )
                rows = [dict(r) for r in cur.fetchall()]

            if not rows:
                return {"status": "not_found", "message": "Không tìm thấy thẻ phù hợp."}

            if len(rows) == 1:
                card = rows[0]
                # Convert UUID to string
                card["card_id"] = str(card["card_id"])
                return {"status": "success", "card": card}

            # Multiple matches
            cards = []
            for r in rows:
                r["card_id"] = str(r["card_id"])
                cards.append(r)
            return {
                "status": "multiple",
                "message": f"Tìm thấy {len(cards)} thẻ phù hợp.",
                "cards": cards,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] get_card_detail error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def lock_card(params: dict, context: dict) -> dict:
    """Lock a card (set status = TEMP_LOCKED).

    Only works if card is currently ACTIVE and belongs to user.
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    reason = params.get("reason", "USER_REQUEST")

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                # Verify ownership and status
                cur.execute(
                    "SELECT status FROM cards WHERE card_id = %s::uuid AND cif_no = %s",
                    (card_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}

                current_status = row[0]
                if current_status != "ACTIVE":
                    return {
                        "status": "failed",
                        "message": f"Không thể khóa thẻ ở trạng thái {current_status}. Thẻ phải đang ACTIVE.",
                    }

                # Lock the card
                cur.execute(
                    "UPDATE cards SET status = 'TEMP_LOCKED' WHERE card_id = %s::uuid",
                    (card_id,),
                )

                # Record operation
                cur.execute(
                    """
                    INSERT INTO card_operation_requests
                        (request_id, user_id, card_id, operation, status, old_value, new_value, reason, session_id, created_at, completed_at)
                    VALUES (%s, %s, %s::uuid, 'LOCK_CARD', 'COMPLETED', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), user_id, card_id,
                        '{"status": "ACTIVE"}', '{"status": "TEMP_LOCKED"}',
                        reason, context.get("session_id"),
                        datetime.now().isoformat(), datetime.now().isoformat(),
                    ),
                )
            conn.commit()
            return {"status": "success", "message": "Đã khóa thẻ thành công.", "new_status": "TEMP_LOCKED"}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] lock_card error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def unlock_card(params: dict, context: dict) -> dict:
    """Unlock a TEMP_LOCKED card (set status = ACTIVE).

    Only works if card is TEMP_LOCKED. LOST/STOLEN/BLOCKED_BY_BANK cannot be unlocked.
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM cards WHERE card_id = %s::uuid AND cif_no = %s",
                    (card_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}

                current_status = row[0]
                if current_status == "ACTIVE":
                    return {"status": "failed", "message": "Thẻ đang hoạt động, không cần mở khóa."}
                if current_status in ("LOST", "STOLEN", "BLOCKED_BY_BANK"):
                    return {
                        "status": "failed",
                        "message": f"Không thể mở khóa thẻ ở trạng thái {current_status}. Vui lòng liên hệ ngân hàng.",
                    }
                if current_status in ("EXPIRED", "CLOSED"):
                    return {
                        "status": "failed",
                        "message": f"Thẻ đã {current_status}, không thể mở khóa.",
                    }

                # Unlock
                cur.execute(
                    "UPDATE cards SET status = 'ACTIVE' WHERE card_id = %s::uuid",
                    (card_id,),
                )
                cur.execute(
                    """
                    INSERT INTO card_operation_requests
                        (request_id, user_id, card_id, operation, status, old_value, new_value, reason, session_id, created_at, completed_at)
                    VALUES (%s, %s, %s::uuid, 'UNLOCK_CARD', 'COMPLETED', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), user_id, card_id,
                        f'{{"status": "{current_status}"}}', '{"status": "ACTIVE"}',
                        "USER_REQUEST", context.get("session_id"),
                        datetime.now().isoformat(), datetime.now().isoformat(),
                    ),
                )
            conn.commit()
            return {"status": "success", "message": "Đã mở khóa thẻ thành công.", "new_status": "ACTIVE"}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] unlock_card error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def report_lost_card(params: dict, context: dict) -> dict:
    """Report card as LOST. This is permanent — card cannot be unlocked after.

    Works if card is ACTIVE or TEMP_LOCKED.
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    reason = params.get("reason", "USER_REPORT_LOST")

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM cards WHERE card_id = %s::uuid AND cif_no = %s",
                    (card_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}

                current_status = row[0]
                if current_status in ("LOST", "STOLEN"):
                    return {"status": "failed", "message": "Thẻ đã được báo mất trước đó."}
                if current_status in ("EXPIRED", "CLOSED"):
                    return {"status": "failed", "message": f"Thẻ đã {current_status}, không cần báo mất."}

                cur.execute(
                    "UPDATE cards SET status = 'LOST' WHERE card_id = %s::uuid",
                    (card_id,),
                )
                cur.execute(
                    """
                    INSERT INTO card_operation_requests
                        (request_id, user_id, card_id, operation, status, old_value, new_value, reason, session_id, created_at, completed_at)
                    VALUES (%s, %s, %s::uuid, 'REPORT_LOST', 'COMPLETED', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), user_id, card_id,
                        f'{{"status": "{current_status}"}}', '{"status": "LOST"}',
                        reason, context.get("session_id"),
                        datetime.now().isoformat(), datetime.now().isoformat(),
                    ),
                )
            conn.commit()
            return {
                "status": "success",
                "message": "Đã báo mất thẻ thành công. Thẻ đã bị khóa vĩnh viễn. Vui lòng yêu cầu phát hành thẻ mới nếu cần.",
                "new_status": "LOST",
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] report_lost_card error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def set_card_control(params: dict, context: dict) -> dict:
    """Toggle a card control setting.

    control_name must be one of:
    - online_payment_enabled
    - international_payment_enabled
    - atm_withdrawal_enabled
    - pos_payment_enabled
    - contactless_enabled

    Card must be ACTIVE.
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    control_name = params.get("control_name")
    enabled = params.get("enabled")

    valid_controls = (
        "online_payment_enabled", "international_payment_enabled",
        "atm_withdrawal_enabled", "pos_payment_enabled", "contactless_enabled",
    )

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}
    if control_name not in valid_controls:
        return {"status": "failed", "message": f"control_name must be one of: {valid_controls}"}
    if enabled is None:
        return {"status": "failed", "message": "enabled (true/false) is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                # Verify ownership + status
                cur.execute(
                    "SELECT status FROM cards WHERE card_id = %s::uuid AND cif_no = %s",
                    (card_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}
                if row[0] != "ACTIVE":
                    return {"status": "failed", "message": f"Thẻ đang ở trạng thái {row[0]}. Cần ACTIVE để thay đổi cài đặt."}

                # Get current value
                cur.execute(
                    f"SELECT {control_name} FROM card_controls WHERE card_id = %s::uuid",
                    (card_id,),
                )
                ctrl_row = cur.fetchone()
                old_value = ctrl_row[0] if ctrl_row else None

                # Update
                cur.execute(
                    f"UPDATE card_controls SET {control_name} = %s, updated_at = %s WHERE card_id = %s::uuid",
                    (enabled, datetime.now().isoformat(), card_id),
                )

                # Record operation
                op_name = f"{'ENABLE' if enabled else 'DISABLE'}_{control_name.replace('_enabled', '').upper()}"
                cur.execute(
                    """
                    INSERT INTO card_operation_requests
                        (request_id, user_id, card_id, operation, status, old_value, new_value, reason, session_id, created_at, completed_at)
                    VALUES (%s, %s, %s::uuid, %s, 'COMPLETED', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), user_id, card_id, op_name,
                        f'{{"{control_name}": {str(old_value).lower()}}}',
                        f'{{"{control_name}": {str(enabled).lower()}}}',
                        "USER_REQUEST", context.get("session_id"),
                        datetime.now().isoformat(), datetime.now().isoformat(),
                    ),
                )
            conn.commit()

            status_text = "bật" if enabled else "tắt"
            control_labels = {
                "online_payment_enabled": "thanh toán online",
                "international_payment_enabled": "thanh toán quốc tế",
                "atm_withdrawal_enabled": "rút tiền ATM",
                "pos_payment_enabled": "thanh toán POS",
                "contactless_enabled": "thanh toán không tiếp xúc",
            }
            label = control_labels.get(control_name, control_name)
            return {
                "status": "success",
                "message": f"Đã {status_text} {label} cho thẻ.",
                "control_name": control_name,
                "new_value": enabled,
                "old_value": old_value,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] set_card_control error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def change_card_limit(params: dict, context: dict) -> dict:
    """Change a card limit.

    limit_type must be one of:
    - daily_atm_limit
    - daily_pos_limit
    - daily_online_limit
    - per_transaction_limit

    New limit must not exceed max_* limit. Card must be ACTIVE.
    """
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    limit_type = params.get("limit_type")
    new_limit = params.get("new_limit")

    valid_limits = ("daily_atm_limit", "daily_pos_limit", "daily_online_limit", "per_transaction_limit")

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}
    if limit_type not in valid_limits:
        return {"status": "failed", "message": f"limit_type must be one of: {valid_limits}"}
    if not new_limit or new_limit <= 0:
        return {"status": "failed", "message": "new_limit must be a positive number."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Verify ownership + status
                cur.execute(
                    "SELECT status FROM cards WHERE card_id = %s::uuid AND cif_no = %s",
                    (card_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}
                if row["status"] != "ACTIVE":
                    return {"status": "failed", "message": f"Thẻ đang ở trạng thái {row['status']}. Cần ACTIVE để thay đổi hạn mức."}

                # Get current limits
                cur.execute(
                    "SELECT * FROM card_limits WHERE card_id = %s::uuid",
                    (card_id,),
                )
                limits = cur.fetchone()
                if not limits:
                    return {"status": "failed", "message": "Không tìm thấy thông tin hạn mức thẻ."}

                old_limit = limits[limit_type]
                max_key = f"max_{limit_type}"
                max_limit = limits.get(max_key, 200000000)

                if new_limit > max_limit:
                    return {
                        "status": "failed",
                        "message": f"Hạn mức mới ({new_limit:,} VND) vượt quá giới hạn tối đa ({max_limit:,} VND).",
                        "max_allowed": max_limit,
                    }

                # Update
                cur.execute(
                    f"UPDATE card_limits SET {limit_type} = %s, updated_at = %s WHERE card_id = %s::uuid",
                    (new_limit, datetime.now().isoformat(), card_id),
                )

                cur.execute(
                    """
                    INSERT INTO card_operation_requests
                        (request_id, user_id, card_id, operation, status, old_value, new_value, reason, session_id, created_at, completed_at)
                    VALUES (%s, %s, %s::uuid, 'CHANGE_LIMIT', 'COMPLETED', %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()), user_id, card_id,
                        f'{{"{limit_type}": {old_limit}}}',
                        f'{{"{limit_type}": {new_limit}}}',
                        "USER_REQUEST", context.get("session_id"),
                        datetime.now().isoformat(), datetime.now().isoformat(),
                    ),
                )
            conn.commit()

            limit_labels = {
                "daily_atm_limit": "hạn mức ATM hàng ngày",
                "daily_pos_limit": "hạn mức POS hàng ngày",
                "daily_online_limit": "hạn mức online hàng ngày",
                "per_transaction_limit": "hạn mức mỗi giao dịch",
            }
            label = limit_labels.get(limit_type, limit_type)
            return {
                "status": "success",
                "message": f"Đã thay đổi {label} từ {old_limit:,} VND thành {new_limit:,} VND.",
                "limit_type": limit_type,
                "old_limit": old_limit,
                "new_limit": new_limit,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] change_card_limit error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def get_card_transactions(params: dict, context: dict) -> dict:
    """Get recent transactions for a specific card."""
    user_id = context.get("user_id", "")
    card_id = params.get("card_id")
    limit = params.get("limit", 10)

    if not card_id:
        return {"status": "failed", "message": "card_id is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Verify ownership
                cur.execute(
                    "SELECT cif_no FROM cards WHERE card_id = %s::uuid",
                    (card_id,),
                )
                row = cur.fetchone()
                if not row or row["cif_no"] != user_id:
                    return {"status": "failed", "message": "Thẻ không thuộc về bạn hoặc không tồn tại."}

                # Get transactions
                cur.execute(
                    """
                    SELECT transaction_id, amount, currency, direction,
                           counterparty_name, description, status, transaction_time
                    FROM transactions
                    WHERE card_id = %s::uuid
                    ORDER BY transaction_time DESC
                    LIMIT %s
                    """,
                    (card_id, limit),
                )
                rows = [dict(r) for r in cur.fetchall()]

            if not rows:
                return {"status": "success", "transactions": [], "count": 0, "message": "Không có giao dịch thẻ gần đây."}

            # Convert UUIDs/datetimes to string
            for r in rows:
                for k, v in r.items():
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
                    elif isinstance(v, uuid.UUID):
                        r[k] = str(v)

            return {"status": "success", "transactions": rows, "count": len(rows)}
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CARD TOOL] get_card_transactions error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


# ============================================================
# TOOL DEFINITIONS (for OpenAI function calling)
# ============================================================

CARD_TOOLS = [
    {
        "name": "get_user_cards",
        "description": (
            "List all cards belonging to the current user. "
            "Returns masked card numbers, type, network, status, and linked account. "
            "Use this when user asks to see their cards or when you need to identify which card to operate on."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_card_detail",
        "description": (
            "Get full detail of a specific card including controls (online payment, international, etc.) "
            "and limits (ATM, POS, online). Can find by card_id or last 4 digits of card number. "
            "Optionally filter by card_type (DEBIT/CREDIT) and card_network (VISA/MASTERCARD/NAPAS)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card (if known)."},
                "last4": {"type": "string", "description": "Last 4 digits of card number."},
                "card_type": {"type": "string", "description": "DEBIT or CREDIT."},
                "card_network": {"type": "string", "description": "VISA, MASTERCARD, or NAPAS."},
            },
        },
    },
    {
        "name": "lock_card",
        "description": (
            "Temporarily lock a card. Card must be ACTIVE. Sets status to TEMP_LOCKED. "
            "User can unlock later. Use this for 'khóa thẻ', 'tạm khóa', 'freeze card'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card to lock."},
                "reason": {"type": "string", "description": "Reason for locking: USER_REQUEST, SECURITY, SUSPICIOUS_ACTIVITY."},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "unlock_card",
        "description": (
            "Unlock a temporarily locked card. Only works if status is TEMP_LOCKED. "
            "LOST/STOLEN/BLOCKED_BY_BANK cards cannot be unlocked through this tool. "
            "Use this for 'mở khóa thẻ', 'unlock card'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card to unlock."},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "report_lost_card",
        "description": (
            "Report a card as lost or stolen. This is PERMANENT — card cannot be unlocked after. "
            "Works if card is ACTIVE or TEMP_LOCKED. Use for 'báo mất thẻ', 'mất thẻ', 'thẻ bị đánh cắp'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the lost card."},
                "reason": {"type": "string", "description": "LOST or STOLEN."},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "set_card_control",
        "description": (
            "Toggle a card control setting (enable/disable). Card must be ACTIVE. "
            "Controls: online_payment_enabled, international_payment_enabled, "
            "atm_withdrawal_enabled, pos_payment_enabled, contactless_enabled."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card."},
                "control_name": {
                    "type": "string",
                    "description": "Control to toggle.",
                    "enum": [
                        "online_payment_enabled",
                        "international_payment_enabled",
                        "atm_withdrawal_enabled",
                        "pos_payment_enabled",
                        "contactless_enabled",
                    ],
                },
                "enabled": {"type": "boolean", "description": "true to enable, false to disable."},
            },
            "required": ["card_id", "control_name", "enabled"],
        },
    },
    {
        "name": "change_card_limit",
        "description": (
            "Change a card's transaction limit. Card must be ACTIVE. "
            "New limit must not exceed the maximum allowed. "
            "Limit types: daily_atm_limit, daily_pos_limit, daily_online_limit, per_transaction_limit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card."},
                "limit_type": {
                    "type": "string",
                    "description": "Which limit to change.",
                    "enum": ["daily_atm_limit", "daily_pos_limit", "daily_online_limit", "per_transaction_limit"],
                },
                "new_limit": {"type": "integer", "description": "New limit amount in VND."},
            },
            "required": ["card_id", "limit_type", "new_limit"],
        },
    },
    {
        "name": "get_card_transactions",
        "description": (
            "Get recent transactions for a specific card. "
            "Returns last N transactions ordered by time. Use for 'xem giao dịch thẻ gần đây'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "UUID of the card."},
                "limit": {"type": "integer", "description": "Max transactions to return (default 10)."},
            },
            "required": ["card_id"],
        },
    },
]

CARD_TOOL_FUNCTIONS: dict[str, Any] = {
    "get_user_cards": get_user_cards,
    "get_card_detail": get_card_detail,
    "lock_card": lock_card,
    "unlock_card": unlock_card,
    "report_lost_card": report_lost_card,
    "set_card_control": set_card_control,
    "change_card_limit": change_card_limit,
    "get_card_transactions": get_card_transactions,
}
