"""Confidence threshold loading and enforcement helpers for extraction decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path

from inv_man_intake.extraction.doc_type import DocumentType
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField


@dataclass(frozen=True)
class ThresholdConfig:
    """Confidence policy values used for extraction gating decisions."""

    field_auto_accept_min: float
    key_field_confidence_min: float
    document_key_field_coverage_min: float
    mandatory_field_min: float
    mandatory_fields: tuple[str, ...]
    document_profiles: Mapping[str, DocumentThresholdProfile] = dataclass_field(
        default_factory=dict
    )


@dataclass(frozen=True)
class DocumentThresholdProfile:
    """Document-type-specific expected-field and confidence policy overrides."""

    key_fields: tuple[str, ...]
    config: ThresholdConfig


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
    profile_name: str | None = None
    profile_list_name: str | None = None
    in_document_profiles = False
    profile_values: dict[str, dict[str, str]] = {}
    profile_key_fields: dict[str, list[str]] = {}
    profile_mandatory_fields: dict[str, list[str]] = {}
    profile_lists_seen: dict[str, set[str]] = {}

    for raw_line in lines:
        line_without_comment = raw_line.split("#", 1)[0].rstrip()
        line = line_without_comment.strip()
        if not line:
            continue
        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        if line == "document_profiles:":
            in_document_profiles = True
            profile_name = None
            profile_list_name = None
            in_mandatory_list = False
            continue
        if in_document_profiles:
            if indent == 0:
                in_document_profiles = False
                profile_name = None
                profile_list_name = None
            elif indent == 2 and line.endswith(":"):
                profile_name = line.removesuffix(":").strip()
                if not profile_name:
                    raise ValueError("document profile name must be non-empty")
                profile_values.setdefault(profile_name, {})
                profile_key_fields.setdefault(profile_name, [])
                profile_mandatory_fields.setdefault(profile_name, [])
                profile_lists_seen.setdefault(profile_name, set())
                profile_list_name = None
                continue
            elif indent == 4 and profile_name is not None:
                if line in {"key_fields:", "mandatory_fields:"}:
                    profile_list_name = line.removesuffix(":")
                    profile_lists_seen[profile_name].add(profile_list_name)
                    continue
                if ":" in line:
                    profile_list_name = None
                    key, value = line.split(":", 1)
                    normalized_key = key.strip()
                    if normalized_key not in {
                        "field_auto_accept_min",
                        "key_field_confidence_min",
                        "document_key_field_coverage_min",
                        "mandatory_field_min",
                    }:
                        raise ValueError(
                            f"unknown threshold config key in profile {profile_name}: {normalized_key}"
                        )
                    profile_values[profile_name][normalized_key] = value.strip().strip('"')
                    continue
                raise ValueError(f"unexpected line in document profile {profile_name}: {line!r}")
            elif indent == 6 and line.startswith("-") and profile_name is not None:
                value = line.removeprefix("-").strip().strip('"')
                if profile_list_name == "key_fields":
                    profile_key_fields[profile_name].append(value)
                    continue
                if profile_list_name == "mandatory_fields":
                    profile_mandatory_fields[profile_name].append(value)
                    continue
                raise ValueError(f"unexpected list item in document profile {profile_name}")
            elif indent != 0:
                raise ValueError(f"unexpected indentation in document_profiles: {raw_line!r}")
        if line == "mandatory_fields:":
            in_mandatory_list = True
            continue
        if line.startswith("mandatory_fields:"):
            raise ValueError(
                "unsupported mandatory_fields format: use block list form with one '- <field>' per line"
            )
        if in_mandatory_list and line.startswith("-"):
            mandatory_fields.append(line.removeprefix("-").strip().strip('"'))
            continue
        if ":" in line:
            in_mandatory_list = False
            key, value = line.split(":", 1)
            normalized_key = key.strip()
            if normalized_key not in {
                "field_auto_accept_min",
                "key_field_confidence_min",
                "document_key_field_coverage_min",
                "mandatory_field_min",
            }:
                raise ValueError(f"unknown threshold config key: {normalized_key}")
            values[normalized_key] = value.strip().strip('"')

    required = {
        "field_auto_accept_min",
        "key_field_confidence_min",
        "document_key_field_coverage_min",
        "mandatory_field_min",
    }
    missing = sorted(required.difference(values))
    if missing:
        raise ValueError(f"missing threshold config keys: {', '.join(missing)}")

    base_config = ThresholdConfig(
        field_auto_accept_min=_threshold_value("field_auto_accept_min", values),
        key_field_confidence_min=_threshold_value("key_field_confidence_min", values),
        document_key_field_coverage_min=_threshold_value("document_key_field_coverage_min", values),
        mandatory_field_min=_threshold_value("mandatory_field_min", values),
        mandatory_fields=tuple(mandatory_fields),
    )
    profiles = {
        name: _document_profile(
            name=name,
            values=profile_values[name],
            key_fields=tuple(profile_key_fields[name]),
            mandatory_fields=tuple(profile_mandatory_fields[name]),
            has_mandatory_fields="mandatory_fields" in profile_lists_seen.get(name, set()),
            base_config=base_config,
        )
        for name in profile_values
    }
    return replace(base_config, document_profiles=profiles)


def _document_profile(
    *,
    name: str,
    values: dict[str, str],
    key_fields: tuple[str, ...],
    mandatory_fields: tuple[str, ...],
    has_mandatory_fields: bool,
    base_config: ThresholdConfig,
) -> DocumentThresholdProfile:
    if not key_fields:
        raise ValueError(f"document profile {name} missing key_fields")

    merged_values = {
        "field_auto_accept_min": str(base_config.field_auto_accept_min),
        "key_field_confidence_min": str(base_config.key_field_confidence_min),
        "document_key_field_coverage_min": str(base_config.document_key_field_coverage_min),
        "mandatory_field_min": str(base_config.mandatory_field_min),
        **values,
    }
    return DocumentThresholdProfile(
        key_fields=key_fields,
        config=ThresholdConfig(
            field_auto_accept_min=_threshold_value("field_auto_accept_min", merged_values),
            key_field_confidence_min=_threshold_value("key_field_confidence_min", merged_values),
            document_key_field_coverage_min=_threshold_value(
                "document_key_field_coverage_min", merged_values
            ),
            mandatory_field_min=_threshold_value("mandatory_field_min", merged_values),
            mandatory_fields=(
                mandatory_fields if has_mandatory_fields else base_config.mandatory_fields
            ),
        ),
    )


def _threshold_value(name: str, values: dict[str, str]) -> float:
    """Parse a threshold float and fail closed if it is not finite and within [0, 1].

    A policy gate must reject malformed config deterministically rather than silently change
    routing (a negative coverage floor auto-passes every document; NaN flips comparisons). See #695.
    """

    value = float(values[name])
    if not math.isfinite(value) or not (0.0 <= value <= 1.0):
        raise ValueError(f"threshold {name} must be a finite value in [0, 1]; got {values[name]!r}")
    return value


def evaluate_thresholds(
    *,
    result: ExtractedDocumentResult,
    key_fields: tuple[str, ...],
    config: ThresholdConfig,
) -> ThresholdDecision:
    """Apply threshold policy to field/document extraction confidence."""

    # Duplicate keys are collapsed deterministically (highest confidence wins) instead of the
    # previous silent last-wins, which let provider/field order invert the decision. Duplicates
    # are surfaced as an escalation reason rather than hidden. See #696.
    field_by_key: dict[str, ExtractedField] = {}
    duplicate_keys: list[str] = []
    for field in result.fields:
        existing = field_by_key.get(field.key)
        if existing is None:
            field_by_key[field.key] = field
            continue
        if field.key not in duplicate_keys:
            duplicate_keys.append(field.key)
        if field.confidence > existing.confidence:
            field_by_key[field.key] = field

    auto_accept_fields = tuple(
        field.key for field in result.fields if field.confidence >= config.field_auto_accept_min
    )

    eligible_key_fields = [
        key
        for key in key_fields
        if key in field_by_key and field_by_key[key].confidence >= config.key_field_confidence_min
    ]
    key_field_coverage_ratio = len(eligible_key_fields) / len(key_fields) if key_fields else 1.0
    auto_pass_document = key_field_coverage_ratio >= config.document_key_field_coverage_min

    mandatory_failures: list[str] = []
    for mandatory_field in config.mandatory_fields:
        candidate = field_by_key.get(mandatory_field)
        if candidate is None:
            mandatory_failures.append(f"missing_mandatory_field:{mandatory_field}")
            continue
        if candidate.confidence < config.mandatory_field_min:
            mandatory_failures.append(f"confidence_below_threshold:{mandatory_field}")

    duplicate_reasons = [f"duplicate_field_key:{key}" for key in sorted(duplicate_keys)]

    if mandatory_failures or duplicate_reasons:
        return ThresholdDecision(
            auto_accept_fields=auto_accept_fields,
            key_field_coverage_ratio=key_field_coverage_ratio,
            auto_pass_document=False,
            escalate=True,
            escalation_reason=";".join(mandatory_failures + duplicate_reasons),
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


def select_threshold_profile(
    *,
    document_type: DocumentType | str,
    key_fields: tuple[str, ...],
    config: ThresholdConfig,
) -> tuple[tuple[str, ...], ThresholdConfig]:
    """Return expected fields and thresholds for a document type, preserving unknown fallback."""

    profile_key = document_type.value if isinstance(document_type, DocumentType) else document_type
    profile = config.document_profiles.get(profile_key)
    if profile is None:
        return key_fields, config
    return profile.key_fields, profile.config


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
            method="threshold-summary",
        ),
        ExtractedField(
            key="confidence.document.auto_pass",
            value="true" if decision.auto_pass_document else "false",
            confidence=1.0,
            source_doc_id=result.source_doc_id,
            source_page=0,
            method="threshold-summary",
        ),
        ExtractedField(
            key="confidence.document.escalation_reason",
            value=decision.escalation_reason or "none",
            confidence=1.0,
            source_doc_id=result.source_doc_id,
            source_page=0,
            method="threshold-summary",
        ),
    )

    return ExtractedDocumentResult(
        source_doc_id=result.source_doc_id,
        provider_name=result.provider_name,
        fields=tuple(result.fields) + summary_fields,
    )
