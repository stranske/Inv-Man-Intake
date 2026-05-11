"""Tests for baseline visual artifact classification heuristics."""

from __future__ import annotations

from inv_man_intake.images.classifier import classify_visual_artifact
from inv_man_intake.images.models import ArtifactSource, VisualArtifact


def _artifact(*, content: bytes, source_ref: str = "pdf-object-1") -> VisualArtifact:
    return VisualArtifact(
        artifact_id="va_test",
        source=ArtifactSource(source_doc_id="doc-1", page_number=1, source_ref=source_ref),
        mime_type="image/png",
        sha256="abc123",
        byte_size=len(content),
        storage_path="artifacts/doc-1/image.png",
        content=content,
    )


def test_classifier_labels_chart_like_performance_content_as_informative() -> None:
    result = classify_visual_artifact(
        _artifact(
            content=(
                b"Performance chart Q1 2026 portfolio return alpha volatility benchmark "
                b"sector exposure table drawdown sharpe 12.4% 8.1% -2.0%"
            )
        )
    )

    assert result.label == "informative"
    assert result.confidence >= 0.75
    assert "informative_terms" in result.reason_codes
    assert "chart_numeric_markers" in result.reason_codes
    assert result.rationale


def test_classifier_labels_logo_and_disclaimer_payload_as_boilerplate() -> None:
    result = classify_visual_artifact(
        _artifact(
            content=b"Confidential logo. Copyright 2026. All rights reserved. Not an offer.",
            source_ref="footer-logo",
        )
    )

    assert result.label == "boilerplate"
    assert result.confidence >= 0.7
    assert "boilerplate_terms" in result.reason_codes
    assert "boilerplate_source_ref" in result.reason_codes


def test_classifier_uses_low_density_fallback_for_decorative_payloads() -> None:
    result = classify_visual_artifact(
        _artifact(content=b"\x89PNG\r\n\x1a\n", source_ref="banner-1")
    )

    assert result.label == "boilerplate"
    assert "low_information_density" in result.reason_codes
    assert result.artifact_id == "va_test"
