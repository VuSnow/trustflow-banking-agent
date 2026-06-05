"""Transaction tools — tool set for TransactionAgent.

Tools:
1. text2sql_query: Send natural language question to text2sql-agent for DB lookups
   (beneficiaries, transaction history, bank codes, candidates, etc.)
2. verify_recipient: Verify account via internal (SHB) or external (inter-bank) lookup
3. check_fraud_risk: Screen account against fraud reports
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

import httpx
import psycopg2

from backend.config import DATABASE_URL, CURRENT_BANK_CODE, TEXT2SQL_AGENT_URL

logger = logging.getLogger(__name__)


# ============================================================
# TOOL FUNCTIONS
# ============================================================


async def text2sql_query(params: dict, context: dict) -> dict:
    """Send a natural language question to text2sql-agent and return results.

    This is the primary information resolution tool. TransactionAgent should
    formulate questions in natural language — text2sql-agent handles schema
    retrieval, SQL generation, validation, and execution.

    Use cases:
    - Find beneficiaries by name/alias
    - Find recent transactions (temporal references like "tháng trước", "lần trước")
    - Find bank_code from bank name
    - Find candidates matching partial info
    - Verify transaction history for a recipient
    """
    question = params.get("question", "")
    if not question:
        return {"status": "failed", "message": "question is required."}

    user_id = context.get("user_id", "")

    # Inject user context into the question if not already present
    if user_id and user_id not in question:
        question = f"{question} (user cif_no: {user_id})"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{TEXT2SQL_AGENT_URL}/query/execute",
                json={"question": question, "execute": True},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[TEXT2SQL TOOL] HTTP error: {e}")
        return {
            "status": "failed",
            "message": f"text2sql-agent returned HTTP {e.response.status_code}. Service may be unavailable.",
        }
    except httpx.RequestError as e:
        logger.error(f"[TEXT2SQL TOOL] Connection error: {e}")
        return {
            "status": "failed",
            "message": "Cannot reach text2sql-agent. Service is unavailable.",
        }

    # Map response
    status = data.get("status")
    if status == "success":
        rows = data.get("results") or []
        return {
            "status": "success",
            "rows": rows,
            "row_count": data.get("row_count", len(rows)),
            "sql": data.get("sql", ""),
        }
    elif status == "needs_clarification":
        return {
            "status": "needs_clarification",
            "message": "\n".join(data.get("questions", ["Cần thêm thông tin."])),
            "questions": data.get("questions", []),
        }
    elif status == "blocked":
        return {
            "status": "failed",
            "message": data.get("reason", "Query blocked by policy."),
        }
    else:
        return {
            "status": "failed",
            "message": data.get("error", "Unknown error from text2sql-agent."),
        }


async def verify_recipient(params: dict, context: dict) -> dict:
    """Verify recipient account via internal (SHB) or external (inter-bank) lookup.

    REQUIRES account_no and bank_code. Routes:
    - bank_code == CURRENT_BANK (SHB): query internal accounts + customers
    - bank_code != CURRENT_BANK: query external_bank_accounts (simulates Napas API)

    Returns resolved_name, transfer_type, and account status.
    """
    account_no = params.get("account_no", "")
    bank_code = params.get("bank_code", "")

    if not account_no:
        return {"status": "failed", "message": "account_no is required."}
    if not bank_code:
        return {
            "status": "failed",
            "message": "bank_code is required. Ask the user which bank this account belongs to.",
        }

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                if bank_code.upper() == CURRENT_BANK_CODE:
                    # Internal lookup: accounts + customers
                    cur.execute(
                        "SELECT c.full_name, a.status "
                        "FROM accounts a "
                        "JOIN customers c ON a.cif_no = c.cif_no "
                        "WHERE a.account_no = %s "
                        "LIMIT 1",
                        (account_no,),
                    )
                    row = cur.fetchone()
                    if row:
                        if row[1] != "ACTIVE":
                            return {
                                "status": "inactive",
                                "message": f"Tài khoản {account_no} tại {CURRENT_BANK_CODE} hiện không hoạt động (status: {row[1]}).",
                                "account_no": account_no,
                                "bank_code": CURRENT_BANK_CODE,
                            }
                        return {
                            "status": "success",
                            "resolved_name": row[0],
                            "bank_code": CURRENT_BANK_CODE,
                            "bank_name": "SHB",
                            "account_status": row[1],
                            "account_no": account_no,
                            "transfer_type": "intrabank",
                        }
                    else:
                        return {
                            "status": "not_found",
                            "message": f"Không tìm thấy tài khoản {account_no} tại {CURRENT_BANK_CODE}.",
                            "account_no": account_no,
                            "bank_code": bank_code,
                        }
                else:
                    # External lookup: external_bank_accounts (simulates Napas)
                    cur.execute(
                        "SELECT account_holder_name, bank_name, status "
                        "FROM external_bank_accounts "
                        "WHERE account_no = %s AND bank_code = %s "
                        "LIMIT 1",
                        (account_no, bank_code.upper()),
                    )
                    row = cur.fetchone()
                    if row:
                        if row[2] != "ACTIVE":
                            return {
                                "status": "inactive",
                                "message": f"Tài khoản {account_no} tại {bank_code} hiện không hoạt động.",
                                "account_no": account_no,
                                "bank_code": bank_code,
                            }
                        return {
                            "status": "success",
                            "resolved_name": row[0],
                            "bank_code": bank_code.upper(),
                            "bank_name": row[1],
                            "account_status": row[2],
                            "account_no": account_no,
                            "transfer_type": "interbank",
                        }
                    else:
                        return {
                            "status": "not_found",
                            "message": f"Không tìm thấy tài khoản {account_no} tại ngân hàng {bank_code}.",
                            "account_no": account_no,
                            "bank_code": bank_code,
                        }
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[TX TOOL] verify_recipient error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


async def check_fraud_risk(params: dict, context: dict) -> dict:
    """Check if a recipient account has been reported for fraud.

    Queries reported_accounts table for risk assessment.
    Returns risk_level: LOW | MEDIUM | HIGH | CRITICAL, or not_reported.
    """
    account_no = params.get("account_no", "")
    bank_code = params.get("bank_code", "")

    if not account_no:
        return {"status": "failed", "message": "account_no is required."}

    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT risk_level, valid_report_count, total_reported_amount,
                           unique_reporter_count, status
                    FROM reported_accounts
                    WHERE account_no = %s
                """
                query_params: list[Any] = [account_no]
                if bank_code:
                    query += " AND bank_code = %s"
                    query_params.append(bank_code.upper())
                query += " LIMIT 1"

                cur.execute(query, query_params)
                row = cur.fetchone()

                if row:
                    return {
                        "status": "found",
                        "is_reported": True,
                        "risk_level": row[0],
                        "report_count": row[1],
                        "total_reported_amount": row[2],
                        "unique_reporter_count": row[3],
                        "account_status": row[4],
                        "account_no": account_no,
                        "bank_code": bank_code,
                    }
                else:
                    return {
                        "status": "clean",
                        "is_reported": False,
                        "risk_level": "LOW",
                        "account_no": account_no,
                        "bank_code": bank_code,
                    }
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"[TX TOOL] check_fraud_risk error: {e}")
        return {"status": "failed", "message": f"Database error: {e}"}


# ============================================================
# TOOL DEFINITIONS (for OpenAI function calling)
# ============================================================

TRANSACTION_TOOLS = [
    {
        "name": "text2sql_query",
        "description": (
            "Send a natural language question to the banking database to look up information. "
            "Use this tool to: find beneficiaries by name/alias, find recent transactions, "
            "resolve temporal references ('tháng trước', 'lần trước', 'người lần trước'), "
            "find bank_code from bank name, find candidates matching partial info, "
            "check transaction history for a specific recipient. "
            "The question should be in Vietnamese and describe what you need. "
            "Do NOT write SQL — just ask the question naturally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "Natural language question about the banking database. "
                        "Examples: 'Tìm beneficiary tên Minh gồm account_no, bank_code, bank_name', "
                        "'Tìm giao dịch chuyển tiền gần nhất', "
                        "'Tìm bank_code tương ứng với Vietcombank', "
                        "'Tìm giao dịch tháng trước tới người tên Minh'"
                    ),
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "verify_recipient",
        "description": (
            "Verify a recipient account and get the official account holder name. "
            "Routes internally (SHB) or externally (inter-bank/Napas) based on bank_code. "
            "REQUIRES both account_no AND bank_code. "
            "If bank_code is unknown, use text2sql_query to find it first, or ask the user. "
            "This is the MANDATORY verification step before creating a draft."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_no": {
                    "type": "string",
                    "description": "The recipient's account number.",
                },
                "bank_code": {
                    "type": "string",
                    "description": "Bank code (e.g. VCB, TCB, SHB, BIDV). Required for routing verification.",
                },
            },
            "required": ["account_no", "bank_code"],
        },
    },
    {
        "name": "check_fraud_risk",
        "description": (
            "Screen a recipient account against fraud/scam reports. "
            "Returns risk_level (LOW/MEDIUM/HIGH/CRITICAL) and report details. "
            "Call AFTER verify_recipient succeeds. Required before creating a draft."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_no": {
                    "type": "string",
                    "description": "The recipient's account number to check.",
                },
                "bank_code": {
                    "type": "string",
                    "description": "Bank code of the recipient account.",
                },
            },
            "required": ["account_no"],
        },
    },
]

# Function dispatch map
TOOL_FUNCTIONS: dict[str, Callable[[dict, dict], Awaitable[dict]]] = {
    "text2sql_query": text2sql_query,
    "verify_recipient": verify_recipient,
    "check_fraud_risk": check_fraud_risk,
}
