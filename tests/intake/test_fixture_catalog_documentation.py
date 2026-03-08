"""Guardrails for intake fixture catalog documentation completeness."""

from __future__ import annotations

from pathlib import Path

DOC_PATH = Path("docs/runbooks/intake_fixture_catalog.md")
FIXTURE_DIR = Path("tests/fixtures/intake")

EXPECTED_ROWS: dict[str, tuple[str, ...]] = {
    "pdf_primary_bundle.json": (
        "parseable_pdf_primary_only",
        "accepted=true",
        "package_id=pkg_pdf_primary_001",
        "file_count=1",
    ),
    "pptx_primary_bundle.json": (
        "parseable_pptx_primary_only",
        "accepted=true",
        "package_id=pkg_pptx_primary_001",
        "file_count=1",
    ),
    "pdf_primary_mixed_bundle.json": (
        "parseable_pdf_primary_mixed_secondary",
        "accepted=true",
        "package_id=pkg_pdf_mixed_001",
        "file_count=4",
    ),
    "pptx_primary_mixed_bundle.json": (
        "parseable_pptx_primary_mixed_secondary",
        "accepted=true",
        "package_id=pkg_pptx_mixed_001",
        "file_count=3",
    ),
    "malformed_missing_metadata.json": (
        "malformed_missing_required_metadata",
        "accepted=false",
        "missing_required_metadata",
        "invalid_received_at",
    ),
    "malformed_unsupported_type.json": (
        "malformed_unsupported_file_type_and_missing_primary",
        "accepted=false",
        "unsupported_file_type",
        "missing_primary_document",
    ),
    "malformed_corrupted_file.json": (
        "malformed_invalid_json_bundle",
        "accepted=false",
        "package_id=None",
        "invalid_json_bundle",
    ),
}


def _doc_lines() -> list[str]:
    return DOC_PATH.read_text(encoding="utf-8").splitlines()


def _fixture_rows(lines: list[str]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in lines:
        if "| `tests/fixtures/intake/" not in line:
            continue
        for fixture_name in EXPECTED_ROWS:
            if fixture_name in line:
                rows[fixture_name] = line
    return rows


def test_fixture_catalog_references_every_intake_fixture_file() -> None:
    lines = _doc_lines()
    text = "\n".join(lines)
    fixture_names = sorted(path.name for path in FIXTURE_DIR.glob("*.json"))

    assert fixture_names
    for fixture_name in fixture_names:
        assert fixture_name in text


def test_fixture_catalog_rows_capture_expected_outcomes() -> None:
    rows = _fixture_rows(_doc_lines())

    assert set(rows) == set(EXPECTED_ROWS)
    for fixture_name, expected_tokens in EXPECTED_ROWS.items():
        row = rows[fixture_name]
        for token in expected_tokens:
            assert token in row
