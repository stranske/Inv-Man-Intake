PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS firms (
    firm_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    aliases_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS funds (
    fund_id TEXT PRIMARY KEY,
    firm_id TEXT NOT NULL,
    fund_name TEXT NOT NULL,
    strategy TEXT,
    asset_class TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_funds_firm
        FOREIGN KEY (firm_id)
        REFERENCES firms (firm_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    received_at TEXT NOT NULL,
    version_date TEXT NOT NULL,
    source_channel TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_document_version UNIQUE (fund_id, file_hash, version_date),
    CONSTRAINT fk_documents_fund
        FOREIGN KEY (fund_id)
        REFERENCES funds (fund_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_funds_firm_id ON funds (firm_id);
CREATE INDEX IF NOT EXISTS idx_documents_fund_id ON documents (fund_id);
CREATE INDEX IF NOT EXISTS idx_documents_received_at ON documents (received_at);
