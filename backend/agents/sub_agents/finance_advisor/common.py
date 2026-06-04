from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re
from typing import Iterable


INCOME_KEYWORDS = (
    "salary",
    "luong",
    "lương",
    "bonus",
    "income",
    "refund",
    "cashback",
    "deposit",
    "transfer in",
    "inbound",
)

BILL_KEYWORDS = (
    "electricity",
    "dien",
    "điện",
    "water",
    "nuoc",
    "nước",
    "internet",
    "phone",
    "mobile",
    "bill",
    "hoa don",
    "hóa đơn",
)

FOOD_KEYWORDS = (
    "food",
    "an uong",
    "ăn uống",
    "coffee",
    "cafe",
    "restaurant",
    "grabfood",
    "baemin",
    "gojek",
    "delivery",
)

TRANSPORT_KEYWORDS = (
    "grab",
    "be",
    "taxi",
    "metro",
    "bus",
    "xe",
    "ship",
)

SHOPPING_KEYWORDS = (
    "shopee",
    "lazada",
    "tiki",
    "mall",
    "shopping",
    "retail",
)

ENTERTAINMENT_KEYWORDS = (
    "netflix",
    "spotify",
    "youtube",
    "disney",
    "game",
    "entertainment",
    "movie",
)

SUBSCRIPTION_KEYWORDS = (
    "netflix",
    "spotify",
    "youtube premium",
    "google one",
    "icloud",
    "apple",
    "microsoft",
    "adobe",
    "subscription",
    "membership",
)

DEFAULT_BUDGET_RATIOS = {
    "food": 0.25,
    "bills": 0.30,
    "transport": 0.10,
    "shopping": 0.15,
    "entertainment": 0.10,
    "subscriptions": 0.05,
    "savings": 0.20,
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def format_currency(value: float | int) -> str:
    return f"{int(round(value)):,} VND"


def to_int(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def transaction_text(transaction: dict) -> str:
    parts = [
        transaction.get("recipient_name"),
        transaction.get("recipient_bank"),
        transaction.get("transaction_type"),
        transaction.get("category"),
        transaction.get("note"),
    ]
    return normalize_text(" ".join([p for p in parts if p]))


def counterparty_key(transaction: dict) -> str:
    text = normalize_text(
        transaction.get("recipient_name")
        or transaction.get("note")
        or transaction.get("transaction_type")
        or transaction.get("category")
    )
    text = re.sub(r"\d+", "", text)
    text = re.sub(r"[^a-z0-9\u00c0-\u1ef9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip() or "unknown"


def infer_category(transaction: dict) -> str:
    text = transaction_text(transaction)
    raw_category = normalize_text(transaction.get("category"))
    transaction_type = normalize_text(transaction.get("transaction_type"))

    if any(keyword in text for keyword in INCOME_KEYWORDS) or transaction_type in {"salary", "income"}:
        return "income"
    if any(keyword in text for keyword in SUBSCRIPTION_KEYWORDS):
        return "subscriptions"
    if any(keyword in text for keyword in BILL_KEYWORDS) or raw_category in {"bills", "utilities"}:
        return "bills"
    if any(keyword in text for keyword in FOOD_KEYWORDS) or raw_category == "food":
        return "food"
    if any(keyword in text for keyword in TRANSPORT_KEYWORDS) or raw_category == "transport":
        return "transport"
    if any(keyword in text for keyword in SHOPPING_KEYWORDS) or raw_category == "shopping":
        return "shopping"
    if any(keyword in text for keyword in ENTERTAINMENT_KEYWORDS) or raw_category == "entertainment":
        return "entertainment"
    if "transfer" in transaction_type or raw_category == "transfer":
        return "transfers"
    if raw_category:
        return raw_category
    return "other"


def is_income_transaction(transaction: dict) -> bool:
    return infer_category(transaction) == "income"


def group_by(items: Iterable[dict], key_fn):
    grouped = defaultdict(list)
    for item in items:
        grouped[key_fn(item)].append(item)
    return grouped


def parse_created_at(transaction: dict) -> datetime | None:
    value = transaction.get("created_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
