"""Coverage for the filesystem content resolver that persists real document bytes."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.integration import (
    filesystem_content_resolver,
    register_intake_bundle,
)
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.storage.document_store import InMemoryDocumentStore

_EXTRACTION_FIXTURES = Path("tests/fixtures/extraction")


def _real_content_bundle() -> dict[str, Any]:
    """A bundle whose every ``file_name`` resolves to a committed real fixture file."""

    return {
        "package_id": "pkg_real_content_001",
        "metadata": {
            "firm_name": "Summit Arc Advisors",
            "fund_name": "Summit Arc Special Situations",
            "received_at": "2026-03-04T08:20:00Z",
            "source_channel": "internal_forward",
        },
        "files": [
            {
                "file_name": "summit_arc_investment_update.pdf",
                "role": "investment_deck",
                "source_ref": "email:fwd-7421",
            },
            {
                "file_name": "summit_arc_track_record.xlsx",
                "role": "performance_track_record",
                "source_ref": "email:fwd-7421",
            },
        ],
    }


def _registry() -> tuple[CoreRepository, InMemoryDocumentStore]:
    connection = sqlite3.connect(":memory:")
    repository = CoreRepository(connection)
    repository.ensure_core_schema()
    return repository, InMemoryDocumentStore()


def test_persisted_hash_matches_real_file_bytes() -> None:
    service = IngestionService()
    repository, store = _registry()

    result = register_intake_bundle(
        _real_content_bundle(),
        service,
        core_repository=repository,
        document_store=store,
        content_resolver=filesystem_content_resolver(_EXTRACTION_FIXTURES),
    )

    assert result.accepted is True
    assert len(result.persisted_documents) == 2

    pdf_version = result.persisted_documents[0]
    pdf_bytes = (_EXTRACTION_FIXTURES / "summit_arc_investment_update.pdf").read_bytes()
    assert pdf_version.file_hash == hashlib.sha256(pdf_bytes).hexdigest()
    assert pdf_version.byte_size == 670

    xlsx_version = result.persisted_documents[1]
    xlsx_bytes = (_EXTRACTION_FIXTURES / "summit_arc_track_record.xlsx").read_bytes()
    assert xlsx_version.file_hash == hashlib.sha256(xlsx_bytes).hexdigest()
    assert xlsx_version.byte_size == 457


def test_real_resolver_differs_from_fabricated_default() -> None:
    """The real-content hash must not coincide with the fabricated placeholder hash."""

    service = IngestionService()
    repository, store = _registry()

    real = register_intake_bundle(
        _real_content_bundle(),
        service,
        core_repository=repository,
        document_store=store,
        content_resolver=filesystem_content_resolver(_EXTRACTION_FIXTURES),
    )

    fabricated_bytes = b"pkg_real_content_001\nsummit_arc_investment_update.pdf\nemail:fwd-7421\n"
    fabricated_hash = hashlib.sha256(fabricated_bytes).hexdigest()
    assert real.persisted_documents[0].file_hash != fabricated_hash


def test_missing_real_file_raises_instead_of_fabricating(tmp_path: Path) -> None:
    """A resolver pointed at a directory without the file surfaces the gap, no fallback."""

    resolver = filesystem_content_resolver(tmp_path)
    with pytest.raises(FileNotFoundError, match="summit_arc_investment_update.pdf"):
        resolver({"file_name": "summit_arc_investment_update.pdf"}, "pkg_real_content_001")


def test_real_resolver_rejects_parent_directory_escape(tmp_path: Path) -> None:
    resolver = filesystem_content_resolver(tmp_path / "bundle")

    with pytest.raises(ValueError, match="escapes the content base directory"):
        resolver({"file_name": "../outside.pdf"}, "pkg_real_content_001")


def test_real_resolver_rejects_absolute_path_escape(tmp_path: Path) -> None:
    resolver = filesystem_content_resolver(tmp_path / "bundle")

    with pytest.raises(ValueError, match="escapes the content base directory"):
        resolver({"file_name": str(tmp_path / "outside.pdf")}, "pkg_real_content_001")
