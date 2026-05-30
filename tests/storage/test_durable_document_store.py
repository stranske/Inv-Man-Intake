"""Durable document-store coverage for on-disk intake persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.integration import register_intake_bundle_to_path
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.storage.document_store import FilesystemDocumentStore

_FIXTURE_ROOT = Path("tests/fixtures/intake")


def test_persisted_bundle_reloads_across_processes(tmp_path: Path) -> None:
    db_path = tmp_path / "core.sqlite"
    store_root = tmp_path / "document-store"
    service = IngestionService()

    result = register_intake_bundle_to_path(
        _FIXTURE_ROOT / "pdf_primary_mixed_bundle.json",
        db_path=db_path,
        store_root=store_root,
        service=service,
    )

    assert result.accepted is True
    record = service.get_record("pkg_pdf_mixed_001")
    original_versions = {version.document_key: version for version in result.persisted_documents}
    assert original_versions

    reloaded_store = FilesystemDocumentStore(store_root)
    connection = sqlite3.connect(db_path)
    reloaded_repository = CoreRepository(connection)
    try:
        for document_id in record.document_ids:
            document = reloaded_repository.get_document(document_id)
            assert document is not None
            document_key = f"{record.fund_id}/{document_id}"
            versions = reloaded_store.list_versions(document_key)
            assert versions
            assert versions[0].file_hash == original_versions[document_key].file_hash
            assert versions[0].file_hash == document.file_hash
            assert reloaded_store.get(document_key, versions[0].version_id)
    finally:
        connection.close()


def test_idempotent_reingest_returns_prior_version(tmp_path: Path) -> None:
    store = FilesystemDocumentStore(tmp_path / "document-store")

    first = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-01T09:00:00Z",
    )
    second = store.put(
        document_key="fund_1/deck",
        file_name="manager_deck.pdf",
        content=b"same-content",
        received_at="2026-03-02T09:00:00Z",
    )

    assert second.version_id == first.version_id
    assert second.file_hash == first.file_hash
    assert store.list_versions("fund_1/deck") == (first,)
    reloaded = FilesystemDocumentStore(tmp_path / "document-store")
    assert reloaded.list_versions("fund_1/deck") == (first,)


def test_read_only_operations_do_not_create_blob_directories(tmp_path: Path) -> None:
    store = FilesystemDocumentStore(tmp_path / "document-store")

    assert store.exists("fund_1/missing", "2026-03-01T09:00:00+00:00:abcd") is False
    blob_root = tmp_path / "document-store" / "blobs"
    assert list(blob_root.iterdir()) == []
