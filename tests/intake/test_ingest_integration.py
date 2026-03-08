"""Integration coverage for intake fixture bundle registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.intake.integration import IntakeRegistrationResult, register_intake_bundle_file
from inv_man_intake.intake.service import IngestionService

_FIXTURE_ROOT = Path("tests/fixtures/intake")


def _register(name: str, service: IngestionService) -> IntakeRegistrationResult:
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


def test_pptx_primary_bundle_registers_successfully() -> None:
    service = IngestionService()

    result = _register("pptx_primary_bundle.json", service)

    assert result.accepted is True
    assert result.package_id == "pkg_pptx_primary_001"
    assert result.status == "received"
    assert result.errors == ()
    record = service.get_record("pkg_pptx_primary_001")
    assert record.file_count == 1


def test_pdf_mixed_bundle_registers_successfully() -> None:
    service = IngestionService()

    result = _register("pdf_primary_mixed_bundle.json", service)

    assert result.accepted is True
    assert result.package_id == "pkg_pdf_mixed_001"
    assert result.status == "received"
    assert result.errors == ()
    record = service.get_record("pkg_pdf_mixed_001")
    assert record.file_count == 4


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
    assert result.warnings == ()
    assert [(error.code, error.path, error.message) for error in result.errors] == [
        ("missing_required_metadata", "metadata.fund_name", "fund_name is required"),
        ("missing_required_metadata", "metadata.received_at", "received_at is required"),
        (
            "invalid_received_at",
            "metadata.received_at",
            "received_at must be an ISO-8601 string",
        ),
    ]
    with pytest.raises(KeyError, match="unknown package_id=pkg_missing_metadata_001"):
        service.get_record("pkg_missing_metadata_001")


def test_unsupported_type_bundle_rejected_with_expected_errors() -> None:
    service = IngestionService()

    result = _register("malformed_unsupported_type.json", service)

    assert result.accepted is False
    assert result.package_id == "pkg_unsupported_type_001"
    assert result.warnings == ()
    assert [(error.code, error.path, error.message) for error in result.errors] == [
        (
            "unsupported_file_type",
            "files[0].file_name",
            (
                "bridgepoint_archive.zip has unsupported extension; allowed: docx, eml, "
                "md, pdf, pptx, txt, xlsx"
            ),
        ),
        (
            "missing_primary_document",
            "files",
            "at least one primary document (.pdf or .pptx) is required",
        ),
    ]
    with pytest.raises(KeyError, match="unknown package_id=pkg_unsupported_type_001"):
        service.get_record("pkg_unsupported_type_001")


def test_corrupted_bundle_rejected_with_invalid_json_error() -> None:
    service = IngestionService()

    result = _register("malformed_corrupted_file.json", service)

    assert result.accepted is False
    assert result.package_id is None
    assert len(result.errors) == 1
    assert result.errors[0].code == "invalid_json_bundle"
    assert result.errors[0].path == str(_FIXTURE_ROOT / "malformed_corrupted_file.json")
    assert result.errors[0].message == "malformed JSON at line 16, column 1"
    assert result.warnings == ()


def test_missing_bundle_file_rejected_with_bundle_read_error() -> None:
    service = IngestionService()

    result = _register("missing_bundle.json", service)

    assert result.accepted is False
    assert result.package_id is None
    assert result.status is None
    assert result.warnings == ()
    assert len(result.errors) == 1
    assert result.errors[0].code == "bundle_read_error"
    assert result.errors[0].path == str(_FIXTURE_ROOT / "missing_bundle.json")
    assert result.errors[0].message == "bundle file not found"


def test_non_object_bundle_file_rejected_with_invalid_structure(tmp_path: Path) -> None:
    service = IngestionService()
    bundle_path = tmp_path / "array_bundle.json"
    bundle_path.write_text('[{"package_id": "pkg_1"}]', encoding="utf-8")

    result = register_intake_bundle_file(bundle_path, service)

    assert result.accepted is False
    assert result.package_id is None
    assert result.status is None
    assert result.warnings == ()
    assert len(result.errors) == 1
    assert result.errors[0].code == "invalid_bundle_structure"
    assert result.errors[0].path == str(bundle_path)
    assert result.errors[0].message == "bundle root must be an object"


def test_duplicate_package_id_rejected_deterministically() -> None:
    service = IngestionService()

    first = _register("pdf_primary_bundle.json", service)
    second = _register("pdf_primary_bundle.json", service)

    assert first.accepted is True
    assert second.accepted is False
    assert second.errors[0].code == "duplicate_package_id"
