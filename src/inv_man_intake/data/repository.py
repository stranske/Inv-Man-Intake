"""Repository layer for core hierarchy CRUD and lookup helpers."""

from __future__ import annotations

import sqlite3

from inv_man_intake.data.models import Document, Firm, Fund
from inv_man_intake.data.provenance import CorrectionRecord, ExtractedFieldRecord


class CoreRepository:
    """Repository for firm/fund/document persistence and lookups."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")

    def ensure_core_schema(self) -> None:
        self._connection.executescript("""
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
                FOREIGN KEY (firm_id) REFERENCES firms (firm_id) ON DELETE CASCADE
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
                FOREIGN KEY (fund_id) REFERENCES funds (fund_id) ON DELETE CASCADE
            );
            """)
        self._connection.commit()

    def create_firm(self, firm: Firm) -> None:
        self._connection.execute(
            "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
            (firm.firm_id, firm.legal_name, firm.aliases_json, firm.created_at),
        )
        self._connection.commit()

    def get_firm(self, firm_id: str) -> Firm | None:
        row = self._connection.execute(
            "SELECT firm_id, legal_name, aliases_json, created_at FROM firms WHERE firm_id = ?",
            (firm_id,),
        ).fetchone()
        if row is None:
            return None
        return Firm(
            firm_id=str(row[0]),
            legal_name=str(row[1]),
            aliases_json=None if row[2] is None else str(row[2]),
            created_at=str(row[3]),
        )

    def update_firm_aliases(self, firm_id: str, aliases_json: str | None) -> None:
        cursor = self._connection.execute(
            "UPDATE firms SET aliases_json = ? WHERE firm_id = ?",
            (aliases_json, firm_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"unknown firm_id={firm_id}")
        self._connection.commit()

    def create_fund(self, fund: Fund) -> None:
        self._connection.execute(
            (
                "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                fund.fund_id,
                fund.firm_id,
                fund.fund_name,
                fund.strategy,
                fund.asset_class,
                fund.created_at,
            ),
        )
        self._connection.commit()

    def get_fund(self, fund_id: str) -> Fund | None:
        row = self._connection.execute(
            (
                "SELECT fund_id, firm_id, fund_name, strategy, asset_class, created_at "
                "FROM funds WHERE fund_id = ?"
            ),
            (fund_id,),
        ).fetchone()
        if row is None:
            return None
        return Fund(
            fund_id=str(row[0]),
            firm_id=str(row[1]),
            fund_name=str(row[2]),
            strategy=None if row[3] is None else str(row[3]),
            asset_class=None if row[4] is None else str(row[4]),
            created_at=str(row[5]),
        )

    def update_fund(self, fund: Fund) -> None:
        cursor = self._connection.execute(
            (
                "UPDATE funds SET firm_id = ?, fund_name = ?, strategy = ?, asset_class = ? "
                "WHERE fund_id = ?"
            ),
            (
                fund.firm_id,
                fund.fund_name,
                fund.strategy,
                fund.asset_class,
                fund.fund_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"unknown fund_id={fund.fund_id}")
        self._connection.commit()

    def create_document(self, document: Document) -> None:
        self._connection.execute(
            (
                "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
                "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                document.document_id,
                document.fund_id,
                document.file_name,
                document.file_hash,
                document.received_at,
                document.version_date,
                document.source_channel,
                document.created_at,
            ),
        )
        self._connection.commit()

    def get_document(self, document_id: str) -> Document | None:
        row = self._connection.execute(
            (
                "SELECT document_id, fund_id, file_name, file_hash, received_at, version_date, "
                "source_channel, created_at FROM documents WHERE document_id = ?"
            ),
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        return Document(
            document_id=str(row[0]),
            fund_id=str(row[1]),
            file_name=str(row[2]),
            file_hash=str(row[3]),
            received_at=str(row[4]),
            version_date=str(row[5]),
            source_channel=str(row[6]),
            created_at=str(row[7]),
        )

    def update_document(self, document: Document) -> None:
        cursor = self._connection.execute(
            (
                "UPDATE documents SET fund_id = ?, file_name = ?, file_hash = ?, received_at = ?, "
                "version_date = ?, source_channel = ? WHERE document_id = ?"
            ),
            (
                document.fund_id,
                document.file_name,
                document.file_hash,
                document.received_at,
                document.version_date,
                document.source_channel,
                document.document_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"unknown document_id={document.document_id}")
        self._connection.commit()

    def list_document_versions(self, fund_id: str, file_name: str) -> tuple[Document, ...]:
        rows = self._connection.execute(
            (
                "SELECT document_id, fund_id, file_name, file_hash, received_at, version_date, "
                "source_channel, created_at FROM documents WHERE fund_id = ? AND file_name = ? "
                "ORDER BY version_date ASC, received_at ASC, document_id ASC"
            ),
            (fund_id, file_name),
        ).fetchall()
        return tuple(
            Document(
                document_id=str(row[0]),
                fund_id=str(row[1]),
                file_name=str(row[2]),
                file_hash=str(row[3]),
                received_at=str(row[4]),
                version_date=str(row[5]),
                source_channel=str(row[6]),
                created_at=str(row[7]),
            )
            for row in rows
        )

    def list_provenance_rows(self, document_id: str) -> tuple[tuple[str, str, int], ...]:
        """Return provenance rows when extracted_fields table exists, else empty tuple."""
        table_exists = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'extracted_fields'"
        ).fetchone()
        if table_exists is None:
            return ()

        rows = self._connection.execute(
            (
                "SELECT field_key, value, source_page FROM extracted_fields "
                "WHERE document_id = ? ORDER BY field_key"
            ),
            (document_id,),
        ).fetchall()

        return tuple((str(row[0]), str(row[1]), int(row[2])) for row in rows)


class FieldProvenanceRepository:
    """Persistence API for extracted fields and append-only correction history."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def insert_extracted_field(self, record: ExtractedFieldRecord) -> None:
        self._connection.execute(
            (
                "INSERT INTO extracted_fields (field_id, document_id, field_key, value, confidence, "
                "source_page, source_snippet, extracted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                record.field_id,
                record.document_id,
                record.field_key,
                record.value,
                record.confidence,
                record.source_page,
                record.source_snippet,
                record.extracted_at,
            ),
        )
        self._connection.commit()

    def append_correction(
        self,
        field_id: str,
        corrected_value: str,
        corrected_at: str,
        reason: str | None = None,
        corrected_by: str | None = None,
    ) -> CorrectionRecord:
        cursor = self._connection.execute(
            (
                "INSERT INTO field_corrections (field_id, corrected_value, reason, corrected_by, "
                "corrected_at) VALUES (?, ?, ?, ?, ?)"
            ),
            (field_id, corrected_value, reason, corrected_by, corrected_at),
        )
        self._connection.commit()

        correction_id = cursor.lastrowid
        assert correction_id is not None
        return CorrectionRecord(
            correction_id=int(correction_id),
            field_id=field_id,
            corrected_value=corrected_value,
            reason=reason,
            corrected_by=corrected_by,
            corrected_at=corrected_at,
        )

    def get_latest_value(self, field_id: str) -> str:
        correction = self._connection.execute(
            (
                "SELECT corrected_value FROM field_corrections WHERE field_id = ? "
                "ORDER BY corrected_at DESC, correction_id DESC LIMIT 1"
            ),
            (field_id,),
        ).fetchone()
        if correction is not None:
            return str(correction[0])

        original = self._connection.execute(
            "SELECT value FROM extracted_fields WHERE field_id = ?",
            (field_id,),
        ).fetchone()
        if original is None:
            raise KeyError(f"field_id={field_id} not found")
        return str(original[0])

    def get_correction_history(self, field_id: str) -> tuple[CorrectionRecord, ...]:
        rows = self._connection.execute(
            (
                "SELECT correction_id, field_id, corrected_value, reason, corrected_by, corrected_at "
                "FROM field_corrections WHERE field_id = ? ORDER BY correction_id ASC"
            ),
            (field_id,),
        ).fetchall()
        return tuple(
            CorrectionRecord(
                correction_id=int(row[0]),
                field_id=str(row[1]),
                corrected_value=str(row[2]),
                reason=None if row[3] is None else str(row[3]),
                corrected_by=None if row[4] is None else str(row[4]),
                corrected_at=str(row[5]),
            )
            for row in rows
        )
