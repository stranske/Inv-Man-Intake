"""Extraction-orchestrator tests that require document bytes."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.orchestrator import ExtractionOrchestrator
from inv_man_intake.extraction.providers.pdf_primary import PdfPrimaryExtractionProvider
from inv_man_intake.v1_smoke import run_v1_smoke_pipeline

_FIXTURE_ROOT = Path("tests/fixtures/extraction")


def test_document_bytes_flow_through_orchestrator_provider_boundary() -> None:
    provider = PdfPrimaryExtractionProvider()
    orchestrator = ExtractionOrchestrator(
        primary_name=provider.name,
        primary_extractor=lambda payload: {
            "result": provider.extract(
                source_doc_id=str(payload["document_id"]),
                content=bytes(payload["content"]),
            )
        },
        fallback_name="unused-fallback",
        fallback_extractor=lambda payload: {"document_id": payload["document_id"]},
    )

    result = orchestrator.run(
        {
            "id": "doc_pdf_1:extract",
            "document_id": "doc_pdf_1",
            "content": (_FIXTURE_ROOT / "summit_arc_investment_update.pdf").read_bytes(),
        }
    )

    assert result.resolved is True
    assert result.provider_used == "pdf-primary"
    assert result.data is not None
    extracted = result.data["result"]
    assert any(field.source_page > 0 for field in extracted.fields)


def test_v1_smoke_routes_secondary_bytes_to_deterministic_escalation() -> None:
    artifacts = run_v1_smoke_pipeline(
        fixture_root=Path("tests/fixtures/intake"),
        package_id="pkg_pdf_mixed_001",
        expected_document_ids=(
            "pkg_pdf_mixed_001:doc:0",
            "pkg_pdf_mixed_001:doc:1",
            "pkg_pdf_mixed_001:doc:2",
            "pkg_pdf_mixed_001:doc:3",
        ),
    )

    secondary = artifacts.secondary_extraction_result
    assert secondary.resolved is False
    assert secondary.escalation_route == "ops_review"
    assert secondary.escalation_reason.startswith("secondary-unsupported-escalation:")
