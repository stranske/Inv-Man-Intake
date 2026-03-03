PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS firms (
    firm_id TEXT PRIMARY KEY CHECK (length(trim(firm_id)) > 0),
    legal_name TEXT NOT NULL CHECK (length(trim(legal_name)) > 0),
    aliases_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS funds (
    fund_id TEXT PRIMARY KEY CHECK (length(trim(fund_id)) > 0),
    firm_id TEXT NOT NULL CHECK (length(trim(firm_id)) > 0),
    fund_name TEXT NOT NULL CHECK (length(trim(fund_name)) > 0),
    strategy TEXT,
    asset_class TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_funds_firm
        FOREIGN KEY (firm_id)
        REFERENCES firms (firm_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY CHECK (length(trim(document_id)) > 0),
    fund_id TEXT NOT NULL CHECK (length(trim(fund_id)) > 0),
    file_name TEXT NOT NULL CHECK (length(trim(file_name)) > 0),
    file_hash TEXT NOT NULL CHECK (length(trim(file_hash)) > 0),
    received_at TEXT NOT NULL,
    version_date TEXT NOT NULL,
    source_channel TEXT NOT NULL CHECK (length(trim(source_channel)) > 0),
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
