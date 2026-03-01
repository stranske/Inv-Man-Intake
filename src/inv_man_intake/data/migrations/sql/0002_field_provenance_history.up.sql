PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS extracted_fields (
    field_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_page INTEGER NOT NULL,
    source_snippet TEXT,
    extracted_at TEXT NOT NULL,
    CONSTRAINT fk_extracted_fields_document
        FOREIGN KEY (document_id)
        REFERENCES documents (document_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id
    ON extracted_fields (document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_field_key
    ON extracted_fields (field_key);

CREATE TABLE IF NOT EXISTS field_corrections (
    correction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id TEXT NOT NULL,
    corrected_value TEXT NOT NULL,
    reason TEXT,
    corrected_by TEXT,
    corrected_at TEXT NOT NULL,
    CONSTRAINT fk_field_corrections_field
        FOREIGN KEY (field_id)
        REFERENCES extracted_fields (field_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_field_corrections_field_id
    ON field_corrections (field_id);
CREATE INDEX IF NOT EXISTS idx_field_corrections_corrected_at
    ON field_corrections (corrected_at);
