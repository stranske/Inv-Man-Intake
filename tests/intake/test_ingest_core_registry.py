"""Coverage for persisting accepted intake bundles into the core registry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.storage.document_store import InMemoryDocumentStore

_FIXTURE_ROOT = Path("tests/fixtures/intake")


def _registry() -> tuple[CoreRepository, InMemoryDocumentStore]:
    connection = sqlite3.connect(":memory:")
    repository = CoreRepository(connection)
    repository.ensure_core_schema()
    return repository, InMemoryDocumentStore()


def test_mixed_bundle_persists_firm_fund_documents_and_versions() -> None:
    service = IngestionService()
    repository, store = _registry()

    result = register_intake_bundle_file(
        _FIXTURE_ROOT / "pdf_primary_mixed_bundle.json",
        service,
        core_repository=repository,
        document_store=store,
    )

    assert result.accepted is True
    assert result.package_id == "pkg_pdf_mixed_001"
    assert len(result.persisted_documents) == 4

    firm = repository.get_firm("firm_summit_arc_advisors")
    fund = repository.get_fund("fund_summit_arc_special_situations")
    assert firm is not None
    assert firm.legal_name == "Summit Arc Advisors"
    assert fund is not None
    assert fund.firm_id == firm.firm_id
    assert fund.fund_name == "Summit Arc Special Situations"

    record = service.get_record("pkg_pdf_mixed_001")
    for document_id, version in zip(record.document_ids, result.persisted_documents, strict=True):
        document = repository.get_document(document_id)
        assert document is not None
        assert document.fund_id == "fund_summit_arc_special_situations"
        assert document.file_hash == version.file_hash
        assert document.received_at == "2026-03-04T08:20:00+00:00"
        assert document.version_date == "2026-03-04"
        assert document.source_channel == "internal_forward"
        assert store.exists(f"{document.fund_id}/{document.document_id}", version.version_id)


def test_duplicate_package_id_does_not_write_additional_versions() -> None:
    service = IngestionService()
    repository, store = _registry()

    first = register_intake_bundle_file(
        _FIXTURE_ROOT / "pdf_primary_bundle.json",
        service,
        core_repository=repository,
        document_store=store,
    )
    second = register_intake_bundle_file(
        _FIXTURE_ROOT / "pdf_primary_bundle.json",
        service,
        core_repository=repository,
        document_store=store,
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.errors[0].code == "duplicate_package_id"
    document_id = service.get_record("pkg_pdf_primary_001").document_ids[0]
    document = repository.get_document(document_id)
    assert document is not None
    assert len(store.list_versions(f"{document.fund_id}/{document_id}")) == 1


def test_re_registering_identical_bytes_returns_prior_version_record() -> None:
    service = IngestionService()
    repository, store = _registry()

    first = register_intake_bundle_file(
        _FIXTURE_ROOT / "pdf_primary_bundle.json",
        service,
        core_repository=repository,
        document_store=store,
    )
    repeated = store.put(
        document_key="fund_north_ridge_opportunities_i/pkg_pdf_primary_001:doc:0",
        file_name="north_ridge_q1_update.pdf",
        content=b"pkg_pdf_primary_001\nnorth_ridge_q1_update.pdf\nemail:msg-1001\n",
        received_at="2026-03-01T09:00:00Z",
    )

    assert first.persisted_documents[0] == repeated
    assert (
        len(store.list_versions("fund_north_ridge_opportunities_i/pkg_pdf_primary_001:doc:0")) == 1
    )


def test_core_document_versions_sort_deterministically_for_intake_rows(tmp_path: Path) -> None:
    service = IngestionService()
    repository, store = _registry()

    early = tmp_path / "early.json"
    late = tmp_path / "late.json"
    _write_bundle(early, package_id="pkg_order_early", received_at="2026-03-01T09:00:00Z")
    _write_bundle(late, package_id="pkg_order_late", received_at="2026-03-02T09:00:00Z")

    for path in (late, early):
        register_intake_bundle_file(
            path,
            service,
            core_repository=repository,
            document_store=store,
        )

    versions = repository.list_document_versions(
        "fund_order_fund",
        "order_deck.pdf",
    )

    assert [version.document_id for version in versions] == [
        "pkg_order_early:doc:0",
        "pkg_order_late:doc:0",
    ]


def _write_bundle(path: Path, *, package_id: str, received_at: str) -> None:
    path.write_text(
        json.dumps(
            {
                "package_id": package_id,
                "metadata": {
                    "firm_name": "Order Firm",
                    "fund_name": "Order Fund",
                    "received_at": received_at,
                    "source_channel": "email",
                },
                "files": [
                    {
                        "file_name": "order_deck.pdf",
                        "role": "investment_deck",
                        "source_ref": f"email:{package_id}",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
