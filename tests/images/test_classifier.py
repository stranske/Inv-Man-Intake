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
                b"sector exposure table drawdown sharpe attribution monthly index returns "
                b"12.4% 8.1% -2.0%"
            )
        )
    )

    assert result.label == "informative"
    assert result.confidence >= 0.75
    assert "informative_terms" in result.reason_codes
    assert "chart_indicators" in result.reason_codes
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
    assert "logo_banner_pattern" in result.reason_codes


def test_classifier_uses_low_density_fallback_for_decorative_payloads() -> None:
    result = classify_visual_artifact(
        _artifact(content=b"\x89PNG\r\n\x1a\n", source_ref="banner-1")
    )

    assert result.label == "boilerplate"
    assert "text_density_low" in result.reason_codes
    assert result.artifact_id == "va_test"


def test_classifier_sets_high_text_density_feature_for_long_textual_payloads() -> None:
    long_text = (
        b"Portfolio return benchmark exposure risk alpha volatility attribution monthly "
        b"sector positioning table drawdown sharpe correlation index performance gross "
        b"net leverage allocation factors scenario stress testing outlook commentary "
        b"portfolio return benchmark exposure risk alpha volatility attribution monthly "
    )
    result = classify_visual_artifact(_artifact(content=long_text, source_ref="content-panel"))

    assert result.label == "informative"
    assert "text_density_high" in result.reason_codes
    assert "text_density_low" not in result.reason_codes


def test_classifier_prefers_informative_on_mixed_signals_with_chart_evidence() -> None:
    result = classify_visual_artifact(
        _artifact(
            content=(
                b"Confidential for institutional use only. Performance attribution table "
                b"Q4 2025 return 11.2% benchmark 8.4% risk and exposure summary."
            ),
            source_ref="slide-content",
        )
    )

    assert result.label == "informative"
    assert result.reason_codes[:2] == ("informative_terms", "boilerplate_terms")
    assert "chart_indicators" in result.reason_codes
    assert result.rationale.startswith("Informative visual signals:")


def test_classifier_boilerplate_reasoning_for_short_disclaimer_banner() -> None:
    result = classify_visual_artifact(
        _artifact(
            content=b"Confidential. Terms of use. Trademark.",
            source_ref="masthead-banner",
        )
    )

    assert result.label == "boilerplate"
    assert result.reason_codes == ("boilerplate_terms", "text_density_low", "logo_banner_pattern")
    assert result.rationale.startswith("Boilerplate visual signals:")
