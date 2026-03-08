"""Confidence threshold loading and enforcement helpers for extraction decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField


@dataclass(frozen=True)
class ThresholdConfig:
    """Confidence policy values used for extraction gating decisions."""

    field_auto_accept_min: float
    key_field_confidence_min: float
    document_key_field_coverage_min: float
    mandatory_field_min: float
    mandatory_fields: tuple[str, ...]


@dataclass(frozen=True)
class ThresholdDecision:
    """Outcome of applying threshold policy to an extraction result."""

    auto_accept_fields: tuple[str, ...]
    key_field_coverage_ratio: float
    auto_pass_document: bool
    escalate: bool
    escalation_reason: str | None


def load_threshold_config(path: str | Path) -> ThresholdConfig:
    """Load threshold policy values from a simple YAML config file."""

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    mandatory_fields: list[str] = []
    in_mandatory_list = False

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line == "mandatory_fields:":
            in_mandatory_list = True
            continue
        if in_mandatory_list and line.startswith("-"):
            mandatory_fields.append(line.removeprefix("-").strip().strip('"'))
            continue
        if ":" in line:
            in_mandatory_list = False
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"')

    required = {
        "field_auto_accept_min",
        "key_field_confidence_min",
        "document_key_field_coverage_min",
        "mandatory_field_min",
    }
    missing = sorted(required.difference(values))
    if missing:
        raise ValueError(f"missing threshold config keys: {', '.join(missing)}")

    return ThresholdConfig(
        field_auto_accept_min=float(values["field_auto_accept_min"]),
        key_field_confidence_min=float(values["key_field_confidence_min"]),
        document_key_field_coverage_min=float(values["document_key_field_coverage_min"]),
        mandatory_field_min=float(values["mandatory_field_min"]),
        mandatory_fields=tuple(mandatory_fields),
    )


def evaluate_thresholds(
    *,
    result: ExtractedDocumentResult,
    key_fields: tuple[str, ...],
    config: ThresholdConfig,
) -> ThresholdDecision:
    """Apply threshold policy to field/document extraction confidence."""

    field_by_key = {field.key: field for field in result.fields}

    auto_accept_fields = tuple(
        field.key for field in result.fields if field.confidence >= config.field_auto_accept_min
    )

    eligible_key_fields = [
        key
        for key in key_fields
        if key in field_by_key and field_by_key[key].confidence >= config.key_field_confidence_min
    ]
    key_field_coverage_ratio = (
        len(eligible_key_fields) / len(key_fields) if key_fields else 1.0
    )
    auto_pass_document = key_field_coverage_ratio >= config.document_key_field_coverage_min

    for mandatory_field in config.mandatory_fields:
        candidate = field_by_key.get(mandatory_field)
        if candidate is None:
            return ThresholdDecision(
                auto_accept_fields=auto_accept_fields,
                key_field_coverage_ratio=key_field_coverage_ratio,
                auto_pass_document=False,
                escalate=True,
                escalation_reason=f"missing_mandatory_field:{mandatory_field}",
            )
        if candidate.confidence < config.mandatory_field_min:
            return ThresholdDecision(
                auto_accept_fields=auto_accept_fields,
                key_field_coverage_ratio=key_field_coverage_ratio,
                auto_pass_document=False,
                escalate=True,
                escalation_reason=f"confidence_below_threshold:{mandatory_field}",
            )

    escalate = not auto_pass_document
    reason = None if auto_pass_document else "low_key_field_coverage"

    return ThresholdDecision(
        auto_accept_fields=auto_accept_fields,
        key_field_coverage_ratio=key_field_coverage_ratio,
        auto_pass_document=auto_pass_document,
        escalate=escalate,
        escalation_reason=reason,
    )


def attach_threshold_summary(
    *,
    result: ExtractedDocumentResult,
    decision: ThresholdDecision,
) -> ExtractedDocumentResult:
    """Attach deterministic threshold summary fields onto extraction output."""

    summary_fields = (
        ExtractedField(
            key="confidence.document.key_field_coverage_ratio",
            value=f"{decision.key_field_coverage_ratio:.4f}",
            confidence=1.0,
            source_doc_id=result.source_doc_id,
            source_page=0,
        ),
        ExtractedField(
            key="confidence.document.auto_pass",
            value="true" if decision.auto_pass_document else "false",
            confidence=1.0,
            source_doc_id=result.source_doc_id,
            source_page=0,
        ),
        ExtractedField(
            key="confidence.document.escalation_reason",
            value=decision.escalation_reason or "none",
            confidence=1.0,
            source_doc_id=result.source_doc_id,
            source_page=0,
        ),
    )

    return ExtractedDocumentResult(
        source_doc_id=result.source_doc_id,
        provider_name=result.provider_name,
        fields=tuple(result.fields) + summary_fields,
    )
