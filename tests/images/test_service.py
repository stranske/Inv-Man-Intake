"""Tests for visual artifact classification service orchestration."""

from __future__ import annotations

from inv_man_intake.images.models import ArtifactSource, VisualArtifact
from inv_man_intake.images.service import (
    classify_visual_artifacts,
    extract_and_classify_visual_artifacts,
)


def _artifact(*, artifact_id: str, content: bytes, source_ref: str) -> VisualArtifact:
    return VisualArtifact(
        artifact_id=artifact_id,
        source=ArtifactSource(source_doc_id="doc-1", page_number=1, source_ref=source_ref),
        mime_type="image/png",
        sha256="abc123",
        byte_size=len(content),
        storage_path=f"artifacts/doc-1/{artifact_id}.png",
        content=content,
    )


def _pdf_fixture_bytes() -> bytes:
    return (
        b"1 0 obj\n<< /Type /Page /Resources << /XObject << /Im0 5 0 R >> >> >>\nendobj\n"
        b"5 0 obj\n<< /Subtype /Image /Filter /DCTDecode /Length 79 >>\n"
        b"stream\nPerformance chart Q1 2026 portfolio return benchmark 12.4% exposure risk\n"
        b"endstream\nendobj\n"
    )


def test_classify_visual_artifacts_returns_label_rationale_for_each_artifact() -> None:
    artifacts = (
        _artifact(
            artifact_id="va_info",
            content=b"Performance chart Q4 2025 return 11.2% benchmark 8.4% exposure risk table.",
            source_ref="slide-content",
        ),
        _artifact(
            artifact_id="va_boiler",
            content=b"Confidential. Terms of use. Trademark.",
            source_ref="masthead-banner",
        ),
    )

    results = classify_visual_artifacts(artifacts)

    assert len(results) == 2
    assert results[0].artifact.artifact_id == "va_info"
    assert results[0].classification.label == "informative"
    assert "chart_indicators" in results[0].classification.reason_codes
    assert results[0].classification.rationale
    assert results[1].artifact.artifact_id == "va_boiler"
    assert results[1].classification.label == "boilerplate"
    assert "boilerplate_terms" in results[1].classification.reason_codes
    assert results[1].classification.rationale


def test_extract_and_classify_visual_artifacts_is_deterministic() -> None:
    first = extract_and_classify_visual_artifacts(
        source_doc_id="doc_pdf_service",
        file_name="manager_deck.pdf",
        content=_pdf_fixture_bytes(),
    )
    second = extract_and_classify_visual_artifacts(
        source_doc_id="doc_pdf_service",
        file_name="manager_deck.pdf",
        content=_pdf_fixture_bytes(),
    )

    assert len(first) == 1
    assert first[0].classification.label == "informative"
    assert first[0].classification.rationale
    assert first[0].classification.reason_codes
    assert [item.artifact.artifact_id for item in first] == [
        item.artifact.artifact_id for item in second
    ]
    assert [item.classification.label for item in first] == [
        item.classification.label for item in second
    ]
    assert [item.classification.reason_codes for item in first] == [
        item.classification.reason_codes for item in second
    ]
    assert [item.classification.rationale for item in first] == [
        item.classification.rationale for item in second
    ]


def test_classify_visual_artifacts_is_deterministic_for_positive_and_negative_examples() -> None:
    artifacts = (
        _artifact(
            artifact_id="va_info",
            content=b"Portfolio benchmark performance chart Q2 2026 return 9.1% exposure risk table.",
            source_ref="slide-main",
        ),
        _artifact(
            artifact_id="va_boiler",
            content=b"Confidential. For professional investors. Terms of use. All rights reserved.",
            source_ref="footer-banner",
        ),
    )

    first = classify_visual_artifacts(artifacts)
    second = classify_visual_artifacts(artifacts)

    assert [item.classification.label for item in first] == ["informative", "boilerplate"]
    assert [item.classification.label for item in first] == [
        item.classification.label for item in second
    ]
    assert [item.classification.reason_codes for item in first] == [
        item.classification.reason_codes for item in second
    ]
    assert [item.classification.confidence for item in first] == [
        item.classification.confidence for item in second
    ]
    assert [item.classification.rationale for item in first] == [
        item.classification.rationale for item in second
    ]
