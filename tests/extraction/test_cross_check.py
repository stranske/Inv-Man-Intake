"""Tests for cross-source extraction field cross-checking."""

from __future__ import annotations

import pytest

from inv_man_intake.extraction.cross_check import (
    FieldObservation,
    create_cross_check_queue_item,
    cross_check_extraction_results,
    cross_check_observations,
)
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField


def test_disagreeing_sources_escalate() -> None:
    report = cross_check_observations(
        (
            FieldObservation(
                key="operations.aum",
                value="$100.0M",
                source="pitchbook",
                confidence=0.91,
            ),
            FieldObservation(
                key="operations.aum",
                value="$89.0M",
                source="tear-sheet",
                confidence=0.89,
            ),
            FieldObservation(
                key="terms.management_fee",
                value="1.50%",
                source="pitchbook",
                confidence=0.88,
            ),
            FieldObservation(
                key="terms.management_fee",
                value="1.52 %",
                source="tear-sheet",
                confidence=0.86,
            ),
            FieldObservation(
                key="performance.net_return_1y",
                value="12.0%",
                source="pitchbook",
                confidence=0.87,
            ),
            FieldObservation(
                key="performance.net_return_1y",
                value="12.4%",
                source="tear-sheet",
                confidence=0.85,
            ),
        )
    )

    decisions = {field.key: field for field in report.fields}

    assert report.escalate is True
    assert decisions["operations.aum"].escalate is True
    assert decisions["operations.aum"].reason is not None
    assert decisions["operations.aum"].reason.startswith("cross_check_disagreement:operations.aum")
    assert decisions["operations.aum"].accepted_source == "pitchbook"
    assert decisions["terms.management_fee"].escalate is False
    assert decisions["performance.net_return_1y"].escalate is False


def test_cross_check_accepts_within_tolerance_and_supports_provider_results() -> None:
    primary = _result(
        provider_name="primary",
        fields=(
            _field("operations.aum", "$100,000,000", "primary-regex", confidence=0.87),
            _field("terms.management_fee", "1.25%", "primary-regex", confidence=0.92),
        ),
    )
    secondary = _result(
        provider_name="docling",
        fields=(
            _field("operations.aum", "$101.0M", "docling", confidence=0.82),
            _field("terms.management_fee", "1.24%", "docling", confidence=0.81),
        ),
    )

    report = cross_check_extraction_results((primary, secondary))

    assert report.escalate is False
    assert report.escalation_reasons == ()
    assert {field.key for field in report.fields} == {"operations.aum", "terms.management_fee"}


def test_unparseable_numeric_key_fails_closed() -> None:
    report = cross_check_observations(
        (
            FieldObservation(
                key="operations.aum",
                value="about a lot",
                source="memo",
                confidence=0.99,
            ),
            FieldObservation(
                key="operations.aum",
                value="$100M",
                source="tear-sheet",
                confidence=0.81,
            ),
        )
    )

    decision = report.fields[0]
    assert report.escalate is True
    assert decision.accepted_value == "$100M"
    assert decision.accepted_source == "tear-sheet"
    assert report.escalation_reasons == ("cross_check_unparseable:operations.aum:memo",)


def test_cross_check_queue_item_uses_existing_validation_queue_contract() -> None:
    report = cross_check_observations(
        (
            FieldObservation(key="operations.aum", value="$100.0M", source="memo"),
            FieldObservation(key="operations.aum", value="$89.0M", source="tear-sheet"),
        )
    )

    item = create_cross_check_queue_item(package_id="pkg-715", report=report)

    assert item is not None
    assert item.item_id == "pkg-715:validation:extraction_cross_check"
    assert item.package_id == "pkg-715"
    assert item.state == "pending_triage"
    assert item.escalation_reason.startswith("cross_check_disagreement:operations.aum")


def test_cross_check_queue_item_is_not_created_without_escalation() -> None:
    report = cross_check_observations(
        (
            FieldObservation(key="operations.aum", value="$100.0M", source="memo"),
            FieldObservation(key="operations.aum", value="$101.0M", source="tear-sheet"),
        )
    )

    assert create_cross_check_queue_item(package_id="pkg-715", report=report) is None


def test_invalid_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="tolerance_percent"):
        cross_check_observations((), tolerance_percent=float("inf"))


def _result(
    *,
    provider_name: str,
    fields: tuple[ExtractedField, ...],
) -> ExtractedDocumentResult:
    return ExtractedDocumentResult(
        source_doc_id="manager-doc",
        provider_name=provider_name,
        fields=fields,
    )


def _field(
    key: str,
    value: str,
    method: str,
    *,
    confidence: float,
) -> ExtractedField:
    return ExtractedField(
        key=key,
        value=value,
        confidence=confidence,
        source_doc_id="manager-doc",
        source_page=1,
        method=method,
    )
