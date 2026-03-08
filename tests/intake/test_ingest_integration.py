"""Integration coverage for intake fixture bundle registration."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.service import IngestionService

_FIXTURE_ROOT = Path("tests/fixtures/intake")


def _register(name: str, service: IngestionService):
    return register_intake_bundle_file(_FIXTURE_ROOT / name, service)


def test_pdf_primary_bundle_registers_successfully() -> None:
    service = IngestionService()

    result = _register("pdf_primary_bundle.json", service)

    assert result.accepted is True
    assert result.package_id == "pkg_pdf_primary_001"
    assert result.status == "received"
    assert result.errors == ()
    record = service.get_record("pkg_pdf_primary_001")
    assert record.file_count == 1


def test_pptx_mixed_bundle_registers_successfully() -> None:
    service = IngestionService()

    result = _register("pptx_primary_mixed_bundle.json", service)

    assert result.accepted is True
    assert result.package_id == "pkg_pptx_mixed_001"
    assert result.status == "received"
    assert result.errors == ()
    record = service.get_record("pkg_pptx_mixed_001")
    assert record.file_count == 3


def test_missing_metadata_bundle_rejected_with_deterministic_errors() -> None:
    service = IngestionService()

    result = _register("malformed_missing_metadata.json", service)

    assert result.accepted is False
    assert result.package_id == "pkg_missing_metadata_001"
    assert result.status is None
    error_codes = {error.code for error in result.errors}
    assert "missing_required_metadata" in error_codes
    assert "invalid_received_at" in error_codes


def test_unsupported_type_bundle_rejected_with_expected_errors() -> None:
    service = IngestionService()

    result = _register("malformed_unsupported_type.json", service)

    assert result.accepted is False
    assert result.package_id == "pkg_unsupported_type_001"
    error_codes = {error.code for error in result.errors}
    assert "unsupported_file_type" in error_codes
    assert "missing_primary_document" in error_codes


def test_corrupted_bundle_rejected_with_invalid_json_error() -> None:
    service = IngestionService()

    result = _register("malformed_corrupted_file.json", service)

    assert result.accepted is False
    assert result.package_id is None
    assert len(result.errors) == 1
    assert result.errors[0].code == "invalid_json_bundle"


def test_duplicate_package_id_rejected_deterministically() -> None:
    service = IngestionService()

    first = _register("pdf_primary_bundle.json", service)
    second = _register("pdf_primary_bundle.json", service)

    assert first.accepted is True
    assert second.accepted is False
    assert second.errors[0].code == "duplicate_package_id"
