"""Cross-check key numeric extraction fields across provider/source outputs."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.workflow_validation import ValidationQueueItem, create_queue_item

DEFAULT_KEY_NUMERIC_FIELDS = (
    "operations.aum",
    "terms.management_fee",
    "performance.net_return_1y",
)
DEFAULT_FIELD_TOLERANCE_PERCENT = 5.0
_FLOAT_TOLERANCE = 1e-12
_NUMERIC_VALUE_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_MAGNITUDE_MULTIPLIERS = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
}


@dataclass(frozen=True)
class FieldObservation:
    """One observed value for a key field from a provider/source."""

    key: str
    value: str
    source: str
    confidence: float = 0.0


@dataclass(frozen=True)
class FieldCrossCheck:
    """Field-level cross-check decision and escalation reason."""

    key: str
    observations: tuple[FieldObservation, ...]
    accepted_value: str | None
    accepted_source: str | None
    escalate: bool
    reason: str | None


@dataclass(frozen=True)
class CrossCheckReport:
    """Cross-check summary for the configured key numeric fields."""

    fields: tuple[FieldCrossCheck, ...]

    @property
    def escalate(self) -> bool:
        """Whether any checked field requires analyst escalation."""

        return any(field.escalate for field in self.fields)

    @property
    def escalation_reasons(self) -> tuple[str, ...]:
        """Stable field-level reasons suitable for queue/escalation payloads."""

        return tuple(field.reason for field in self.fields if field.reason)


def cross_check_extraction_results(
    results: Sequence[ExtractedDocumentResult],
    *,
    key_fields: Iterable[str] = DEFAULT_KEY_NUMERIC_FIELDS,
    tolerance_percent: float = DEFAULT_FIELD_TOLERANCE_PERCENT,
) -> CrossCheckReport:
    """Cross-check key numeric fields whenever multiple provider/source values exist."""

    observations: list[FieldObservation] = []
    for result in results:
        observations.extend(_observations_from_result(result))
    return cross_check_observations(
        observations,
        key_fields=key_fields,
        tolerance_percent=tolerance_percent,
    )


def create_cross_check_queue_item(
    *,
    package_id: str,
    report: CrossCheckReport,
    item_id: str | None = None,
) -> ValidationQueueItem | None:
    """Build a validation queue item when cross-checks require escalation."""

    if not report.escalate:
        return None
    resolved_item_id = item_id or f"{package_id}:validation:extraction_cross_check"
    return create_queue_item(
        item_id=resolved_item_id,
        package_id=package_id,
        escalation_reason=";".join(report.escalation_reasons),
    )


def cross_check_observations(
    observations: Iterable[FieldObservation],
    *,
    key_fields: Iterable[str] = DEFAULT_KEY_NUMERIC_FIELDS,
    tolerance_percent: float = DEFAULT_FIELD_TOLERANCE_PERCENT,
) -> CrossCheckReport:
    """Reconcile key field observations and escalate disagreements beyond tolerance."""

    if tolerance_percent < 0.0 or tolerance_percent > 100.0:
        raise ValueError("tolerance_percent must be between 0 and 100 inclusive")

    fields_by_key: dict[str, list[FieldObservation]] = {key: [] for key in key_fields}
    for observation in observations:
        if observation.key in fields_by_key:
            fields_by_key[observation.key].append(observation)

    decisions = tuple(
        _cross_check_field(
            key=key,
            observations=tuple(field_observations),
            tolerance_percent=tolerance_percent,
        )
        for key, field_observations in fields_by_key.items()
        if len(field_observations) > 1
    )
    return CrossCheckReport(fields=decisions)


def _observations_from_result(result: ExtractedDocumentResult) -> list[FieldObservation]:
    observations: list[FieldObservation] = []
    for field in result.fields:
        observations.append(
            FieldObservation(
                key=field.key,
                value=field.value,
                source=_field_source(result=result, field=field),
                confidence=field.confidence,
            )
        )
    return observations


def _field_source(*, result: ExtractedDocumentResult, field: ExtractedField) -> str:
    method = field.method.strip() or result.provider_name
    return f"{result.provider_name}:{method}:{field.source_doc_id}:p{field.source_page}"


def _cross_check_field(
    *,
    key: str,
    observations: tuple[FieldObservation, ...],
    tolerance_percent: float,
) -> FieldCrossCheck:
    parsed: list[tuple[FieldObservation, float]] = []
    parse_failures: list[str] = []
    for observation in observations:
        value = _parse_numeric_value(observation.value)
        if value is None:
            parse_failures.append(observation.source)
            continue
        parsed.append((observation, value))

    accepted = _select_accepted_observation(observations)
    if parse_failures:
        accepted = _select_accepted_observation(tuple(observation for observation, _ in parsed))
        return FieldCrossCheck(
            key=key,
            observations=observations,
            accepted_value=accepted.value if accepted is not None else None,
            accepted_source=accepted.source if accepted is not None else None,
            escalate=True,
            reason=f"cross_check_unparseable:{key}:{','.join(sorted(parse_failures))}",
        )

    disagreement = _first_disagreement(parsed, tolerance_percent=tolerance_percent)
    assert accepted is not None
    if disagreement is None:
        return FieldCrossCheck(
            key=key,
            observations=observations,
            accepted_value=accepted.value,
            accepted_source=accepted.source,
            escalate=False,
            reason=None,
        )

    left, right, percent_difference = disagreement
    return FieldCrossCheck(
        key=key,
        observations=observations,
        accepted_value=accepted.value,
        accepted_source=accepted.source,
        escalate=True,
        reason=(
            f"cross_check_disagreement:{key}:"
            f"{left.source}!={right.source}:"
            f"{percent_difference:.4f}%>{tolerance_percent:.4f}%"
        ),
    )


def _select_accepted_observation(
    observations: tuple[FieldObservation, ...],
) -> FieldObservation | None:
    if not observations:
        return None
    return max(
        observations,
        key=lambda observation: (observation.confidence, observation.source, observation.value),
    )


def _first_disagreement(
    parsed: list[tuple[FieldObservation, float]],
    *,
    tolerance_percent: float,
) -> tuple[FieldObservation, FieldObservation, float] | None:
    for left_index, (left_observation, left_value) in enumerate(parsed):
        for right_observation, right_value in parsed[left_index + 1 :]:
            percent_difference = _relative_difference_percent(left_value, right_value)
            if percent_difference > tolerance_percent:
                return left_observation, right_observation, percent_difference
    return None


def _relative_difference_percent(value_a: float, value_b: float) -> float:
    denominator = max(abs(value_a), abs(value_b), _FLOAT_TOLERANCE)
    return (abs(value_a - value_b) / denominator) * 100.0


def _parse_numeric_value(raw_value: str) -> float | None:
    normalized = raw_value.strip().casefold()
    match = _NUMERIC_VALUE_RE.search(normalized)
    if match is None:
        return None

    value = float(match.group(0).replace(",", ""))
    if not math.isfinite(value):
        return None

    suffix = normalized[match.end() :].strip()
    if suffix.startswith("%"):
        return value

    for token, multiplier in _MAGNITUDE_MULTIPLIERS.items():
        if suffix.startswith(token):
            return value * multiplier
    return value
