-- external_bank_accounts: simulates inter-bank account directory (like Napas)
-- Contains accounts from banks OTHER than CURRENT_BANK (default: SHB)

CREATE TABLE IF NOT EXISTS external_bank_accounts (
    id SERIAL PRIMARY KEY,
    account_no VARCHAR(20) NOT NULL,
    account_holder_name VARCHAR(100) NOT NULL,
    bank_code VARCHAR(10) NOT NULL,
    bank_name VARCHAR(50) NOT NULL,
    id_number VARCHAR(20),
    phone VARCHAR(15),
    status VARCHAR(10) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_bank_acc_unique
    ON external_bank_accounts(account_no, bank_code);

INSERT INTO external_bank_accounts (account_no, account_holder_name, bank_code, bank_name, id_number, phone) VALUES
('9999888877', 'Nguyen Van Anh', 'VCB', 'Vietcombank', '079123456789', '0901234567'),
('1234567890', 'Tran Thi Bich', 'TCB', 'Techcombank', '079987654321', '0912345678'),
('0011223344', 'Le Quang Minh', 'ACB', 'ACB', '079111222333', '0923456789'),
('5566778899', 'Pham Duc Huy', 'BIDV', 'BIDV', '079444555666', '0934567890'),
('6677889900', 'Hoang Thi Nhi', 'ACB', 'ACB', '079777888999', '0945678901'),
('1122334455', 'Vo Van Tai', 'CTG', 'VietinBank', '079222333444', '0956789012'),
('2233445566', 'Dang Minh Tuan', 'MBB', 'MB Bank', '079333444555', '0967890123'),
('3344556677', 'Bui Thi Lan', 'VPB', 'VPBank', '079555666777', '0978901234'),
('4455667788', 'Ngo Thanh Son', 'TPB', 'TPBank', '079666777888', '0989012345'),
('5566001122', 'Truong Van Duc', 'STB', 'Sacombank', '079888999000', '0990123456'),
('7788990011', 'Ly Thi Hong', 'HDB', 'HDBank', '079000111222', '0911234567'),
('8899001122', 'Phan Quoc Bao', 'OCB', 'OCB', '079123789456', '0922345678'),
('9900112233', 'Mai Van Khanh', 'EIB', 'Eximbank', '079456123789', '0933456789'),
('1010202030', 'Cao Thi Dung', 'AGR', 'Agribank', '079789456123', '0944567890'),
('2020303040', 'Dinh Hoang Nam', 'VIB', 'VIB', '079321654987', '0955678901')
ON CONFLICT (account_no, bank_code) DO NOTHING;
