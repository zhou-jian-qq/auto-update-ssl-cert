CREATE TABLE IF NOT EXISTS banks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 443,
    threshold_days INTEGER NOT NULL DEFAULT 30,
    website_url TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    current_cert_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(current_cert_id) REFERENCES certificates(id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('candidate', 'confirmed', 'archived')),
    subject TEXT NOT NULL,
    issuer TEXT NOT NULL,
    serial_number TEXT NOT NULL,
    not_before TEXT NOT NULL,
    not_after TEXT NOT NULL,
    sans TEXT NOT NULL DEFAULT '',
    sha256_fingerprint TEXT NOT NULL,
    pem_path TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bank_id, sha256_fingerprint),
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS check_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    certificate_id INTEGER,
    checked_at TEXT NOT NULL,
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE,
    FOREIGN KEY(certificate_id) REFERENCES certificates(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificate_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    FOREIGN KEY(certificate_id) REFERENCES certificates(id) ON DELETE CASCADE
);
