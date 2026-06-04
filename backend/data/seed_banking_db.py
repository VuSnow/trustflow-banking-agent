"""Seed banking.db with realistic test data."""
import sqlite3
import json
import os
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "banking.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    account_number TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    account_type TEXT DEFAULT 'checking',
    balance INTEGER DEFAULT 0,
    currency TEXT DEFAULT 'VND',
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS beneficiaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL,
    nicknames TEXT,
    account_number TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    created_at TEXT,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    source_account TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_account TEXT NOT NULL,
    recipient_bank TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'VND',
    category TEXT,
    transaction_type TEXT,
    note TEXT,
    status TEXT DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reported_accounts (
    account_number TEXT PRIMARY KEY,
    bank_name TEXT,
    reason TEXT,
    reported_at TEXT,
    severity TEXT DEFAULT 'high'
);
"""


def seed():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    now = datetime.now()

    # --- Users ---
    users = [
        ("u1", "Nguyễn Thanh Tùng", "0901234567", "tung.nguyen@email.com"),
        ("u2", "Trần Minh Châu", "0912345678", "chau.tran@email.com"),
    ]
    
    first_names = ["An", "Bình", "Cường", "Dung", "Em", "Giang", "Hoa", "Khoa", "Linh", "Minh", "Nam", "Oanh", "Phúc", "Quang", "Sơn", "Tuấn", "Uyên", "Vy", "Xuân", "Yến", "Hiếu", "Thảo", "Đức", "Lan", "Hải", "Trang", "Long", "Mai", "Hùng", "Nhi"]
    last_names = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Võ", "Đặng", "Bùi", "Đỗ", "Ngô"]
    middle_names = ["Văn", "Thị", "Đức", "Minh", "Quốc", "Thanh", "Ngọc", "Hoàng", "Anh", "Hữu"]
    
    for i in range(3, 103):
        name = f"{random.choice(last_names)} {random.choice(middle_names)} {random.choice(first_names)}"
        phone = f"09{random.randint(10000000, 99999999)}"
        email = f"user{i}@email.com"
        users.append((f"u{i}", name, phone, email))

    conn.executemany(
        "INSERT INTO users (user_id, name, phone, email, created_at) VALUES (?,?,?,?,?)",
        [(u[0], u[1], u[2], u[3], (now - timedelta(days=random.randint(10, 365))).isoformat())
         for u in users],
    )

    # --- Accounts ---
    banks = ["Vietcombank", "Techcombank", "MB Bank", "BIDV", "VPBank", "ACB", "VietinBank"]
    accounts = [
        ("acc1", "u1", "1900000001", "Vietcombank", "checking", 50_000_000),
        ("acc2", "u1", "1900000002", "Vietcombank", "savings", 200_000_000),
        ("acc3", "u2", "2800000001", "Techcombank", "checking", 30_000_000),
        ("acc4", "u2", "2800000002", "MB Bank", "checking", 15_000_000),
    ]
    
    acc_idx = 5
    for u in users[2:]:
        num_accounts = random.randint(1, 3)
        for _ in range(num_accounts):
            acc_id = f"acc{acc_idx}"
            uid = u[0]
            acc_num = f"{random.randint(1000000000, 9999999999)}"
            bank = random.choice(banks)
            acc_type = random.choice(["checking", "savings"])
            balance = random.randint(1_000_000, 500_000_000)
            accounts.append((acc_id, uid, acc_num, bank, acc_type, balance))
            acc_idx += 1

    conn.executemany(
        "INSERT INTO accounts (account_id, user_id, account_number, bank_name, account_type, balance) VALUES (?,?,?,?,?,?)",
        accounts,
    )

    # --- Beneficiaries ---
    beneficiaries = [
        # user u1
        ("u1", "Nguyễn Văn Minh", json.dumps(["Minh", "anh Minh", "Minh béo"]), "0123456789", "Vietcombank",
         (now - timedelta(days=90)).isoformat(), (now - timedelta(days=5)).isoformat()),
        ("u1", "Trần Thị Lan", json.dumps(["Lan", "chị Lan", "Lan kế toán"]), "9876543210", "Techcombank",
         (now - timedelta(days=180)).isoformat(), (now - timedelta(days=15)).isoformat()),
        ("u1", "Phạm Đức Anh", json.dumps(["Đức Anh", "Anh", "thằng Anh"]), "1112223334", "MB Bank",
         (now - timedelta(days=60)).isoformat(), (now - timedelta(days=30)).isoformat()),
        ("u1", "Trần Minh Đức", json.dumps(["Minh Đức", "Đức"]), "5554443332", "Techcombank",
         (now - timedelta(days=45)).isoformat(), (now - timedelta(days=10)).isoformat()),
        # user u2
        ("u2", "Lê Hoàng Nam", json.dumps(["Nam", "Nam béo"]), "5556667778", "BIDV",
         (now - timedelta(days=120)).isoformat(), (now - timedelta(days=7)).isoformat()),
        ("u2", "Nguyễn Thanh Tùng", json.dumps(["Tùng", "anh Tùng"]), "1900000001", "Vietcombank",
         (now - timedelta(days=200)).isoformat(), (now - timedelta(days=3)).isoformat()),
        ("u2", "Võ Thị Mai", json.dumps(["Mai", "chị Mai"]), "7778889990", "VPBank",
         (now - timedelta(days=150)).isoformat(), (now - timedelta(days=20)).isoformat()),
    ]
    
    for u in users[2:]:
        num_ben = random.randint(1, 5)
        for _ in range(num_ben):
            b_name = f"{random.choice(last_names)} {random.choice(middle_names)} {random.choice(first_names)}"
            nicks = [b_name.split()[-1], f"anh {b_name.split()[-1]}", f"chị {b_name.split()[-1]}"]
            beneficiaries.append((
                u[0], b_name, json.dumps(nicks), f"{random.randint(1000000000, 9999999999)}", random.choice(banks),
                (now - timedelta(days=random.randint(30, 300))).isoformat(),
                (now - timedelta(days=random.randint(1, 29))).isoformat()
            ))

    conn.executemany(
        "INSERT INTO beneficiaries (user_id, name, nicknames, account_number, bank_name, created_at, last_used_at) VALUES (?,?,?,?,?,?,?)",
        beneficiaries,
    )

    # --- Transactions ---
    categories = ["food", "bills", "transfer",
                  "salary", "shopping", "entertainment"]
    tx_rows = []

    # u1 transactions — emphasis on Minh (frequent recipient)
    u1_recipients = [
        ("Nguyễn Văn Minh", "0123456789", "Vietcombank"),
        ("Trần Thị Lan", "9876543210", "Techcombank"),
        ("Phạm Đức Anh", "1112223334", "MB Bank"),
        ("Trần Minh Đức", "5554443332", "Techcombank"),
        ("Công ty điện lực", "0001112223", "Vietcombank"),
    ]

    for i in range(150):
        days_ago = random.randint(1, 90)
        recip = random.choices(u1_recipients, weights=[35, 20, 15, 15, 15], k=1)[0]
        amount = random.choice(
            [500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 200_000, 10_000_000])
        cat = random.choice(categories)
        tx_rows.append((
            "u1", "1900000001", recip[0], recip[1], recip[2],
            amount, "VND", cat, "transfer", f"Giao dịch #{i+1}",
            "completed", (now - timedelta(days=days_ago,
                          hours=random.randint(0, 23))).isoformat()
        ))

    # u2 transactions
    u2_recipients = [
        ("Lê Hoàng Nam", "5556667778", "BIDV"),
        ("Nguyễn Thanh Tùng", "1900000001", "Vietcombank"),
        ("Võ Thị Mai", "7778889990", "VPBank"),
    ]

    for i in range(100):
        days_ago = random.randint(1, 90)
        recip = random.choices(u2_recipients, weights=[40, 35, 25], k=1)[0]
        amount = random.choice(
            [500_000, 1_000_000, 2_000_000, 5_000_000, 15_000_000])
        cat = random.choice(categories)
        tx_rows.append((
            "u2", "2800000001", recip[0], recip[1], recip[2],
            amount, "VND", cat, "transfer", f"Giao dịch #{i+1}",
            "completed", (now - timedelta(days=days_ago,
                          hours=random.randint(0, 23))).isoformat()
        ))
        
    # Other users transactions
    for u in users[2:]:
        num_tx = random.randint(5, 20)
        uid = u[0]
        u_accounts = [a for a in accounts if a[1] == uid]
        if not u_accounts:
            continue
        
        for i in range(num_tx):
            days_ago = random.randint(1, 90)
            acc = random.choice(u_accounts)[2]
            recip_name = f"{random.choice(last_names)} {random.choice(middle_names)} {random.choice(first_names)}"
            recip_acc = f"{random.randint(1000000000, 9999999999)}"
            recip_bank = random.choice(banks)
            amount = random.randint(100, 20000) * 1000
            cat = random.choice(categories)
            tx_rows.append((
                uid, acc, recip_name, recip_acc, recip_bank,
                amount, "VND", cat, "transfer", f"Giao dịch #{i+1}",
                "completed", (now - timedelta(days=days_ago, hours=random.randint(0, 23))).isoformat()
            ))

    conn.executemany(
        "INSERT INTO transactions (user_id, source_account, recipient_name, recipient_account, recipient_bank, amount, currency, category, transaction_type, note, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        tx_rows,
    )

    # --- Reported / Scam accounts ---
    reported = [
        ("6666666666", "Unknown Bank", "scam",
         (now - timedelta(days=30)).isoformat(), "high"),
        ("9999888877", "Techcombank", "fraud",
         (now - timedelta(days=60)).isoformat(), "high"),
        ("1231231230", "BIDV", "suspicious",
         (now - timedelta(days=15)).isoformat(), "medium"),
    ]
    for _ in range(20):
        reported.append((
            f"{random.randint(1000000000, 9999999999)}",
            random.choice(banks),
            random.choice(["scam", "fraud", "suspicious"]),
            (now - timedelta(days=random.randint(1, 90))).isoformat(),
            random.choice(["high", "medium", "low"])
        ))

    conn.executemany(
        "INSERT INTO reported_accounts (account_number, bank_name, reason, reported_at, severity) VALUES (?,?,?,?,?)",
        reported,
    )

    conn.commit()
    conn.close()
    print(f"✓ Seeded {DB_PATH}")
    print(f"  - {len(users)} users")
    print(f"  - {len(accounts)} accounts")
    print(f"  - {len(beneficiaries)} beneficiaries")
    print(f"  - {len(tx_rows)} transactions")
    print(f"  - {len(reported)} reported accounts")


if __name__ == "__main__":
    seed()
