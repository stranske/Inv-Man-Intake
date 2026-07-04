"""Read-only extraction calibration metrics from human corrections."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from inv_man_intake.data.provenance import CorrectionRecord, ExtractedFieldRecord
from inv_man_intake.extraction.confidence import ThresholdConfig

DEFAULT_CONFIDENCE_BUCKETS: tuple[float, ...] = (0.0, 0.6, 0.75, 0.85, 1.0)
type CorrectnessSignal = bool | None


@dataclass(frozen=True)
class FieldCalibrationObservation:
    """Correctness signal for one extracted field."""

    field_id: str
    field_key: str
    confidence: float
    observed_correct: CorrectnessSignal
    original_value: str
    latest_value: str | None


def build_calibration_report(
    *,
    extracted_fields: Iterable[ExtractedFieldRecord],
    corrections: Iterable[CorrectionRecord],
    threshold_config: ThresholdConfig,
    expected_field_keys: Iterable[str] = (),
    confidence_buckets: tuple[float, ...] = DEFAULT_CONFIDENCE_BUCKETS,
) -> dict[str, object]:
    """Compute precision, recall, confidence calibration, and threshold suggestions.

    The report is intentionally read-only: callers provide the extracted fields and correction
    history, and this function returns deterministic JSON-compatible data without touching
    threshold config files.
    """

    fields = tuple(extracted_fields)
    if not fields:
        raise ValueError("at least one extracted field is required")

    _validate_buckets(confidence_buckets)
    observations = _observations(fields, corrections)
    known_observations = tuple(
        observation for observation in observations if observation.observed_correct is not None
    )
    observed_by_key = {observation.field_key for observation in observations}
    expected_keys = set(expected_field_keys) or observed_by_key
    missing_expected = sorted(expected_keys.difference(observed_by_key))

    true_positive_count = sum(
        observation.observed_correct is True for observation in known_observations
    )
    false_positive_count = sum(
        observation.observed_correct is False for observation in known_observations
    )
    false_negative_count = false_positive_count + len(missing_expected)

    precision = _ratio(true_positive_count, true_positive_count + false_positive_count)
    recall = _ratio(true_positive_count, true_positive_count + false_negative_count)

    auto_accept = [
        observation
        for observation in known_observations
        if observation.confidence >= threshold_config.field_auto_accept_min
    ]
    auto_accept_precision = _ratio(
        sum(observation.observed_correct is True for observation in auto_accept),
        len(auto_accept),
    )

    return {
        "summary": {
            "field_count": len(observations),
            "known_field_count": len(known_observations),
            "unknown_field_count": len(observations) - len(known_observations),
            "expected_field_count": len(expected_keys),
            "true_positive_count": true_positive_count,
            "false_positive_count": false_positive_count,
            "false_negative_count": false_negative_count,
            "precision": precision,
            "recall": recall,
            "auto_accept_precision": auto_accept_precision,
            "missing_expected_fields": missing_expected,
        },
        "field_metrics": _field_metrics(known_observations),
        "confidence_buckets": _confidence_bucket_metrics(known_observations, confidence_buckets),
        "threshold_suggestions": _threshold_suggestions(
            precision=precision,
            recall=recall,
            auto_accept_precision=auto_accept_precision,
            threshold_config=threshold_config,
        ),
    }


def _observations(
    fields: tuple[ExtractedFieldRecord, ...],
    corrections: Iterable[CorrectionRecord],
) -> tuple[FieldCalibrationObservation, ...]:
    latest_correction = _latest_corrections(corrections)
    observations: list[FieldCalibrationObservation] = []
    for field in sorted(fields, key=lambda record: (record.field_key, record.field_id)):
        if not 0.0 <= field.confidence <= 1.0:
            raise ValueError(f"field {field.field_id} confidence must be within [0, 1]")
        correction = latest_correction.get(field.field_id)
        latest_value = None if correction is None else correction.corrected_value
        observations.append(
            FieldCalibrationObservation(
                field_id=field.field_id,
                field_key=field.field_key,
                confidence=field.confidence,
                observed_correct=None if latest_value is None else latest_value == field.value,
                original_value=field.value,
                latest_value=latest_value,
            )
        )
    return tuple(observations)


def _latest_corrections(
    corrections: Iterable[CorrectionRecord],
) -> dict[str, CorrectionRecord]:
    latest: dict[str, CorrectionRecord] = {}
    for correction in corrections:
        current = latest.get(correction.field_id)
        if current is None or (correction.corrected_at, correction.correction_id) > (
            current.corrected_at,
            current.correction_id,
        ):
            latest[correction.field_id] = correction
    return latest


def _field_metrics(
    observations: tuple[FieldCalibrationObservation, ...],
) -> dict[str, dict[str, object]]:
    by_key: dict[str, list[FieldCalibrationObservation]] = defaultdict(list)
    for observation in observations:
        by_key[observation.field_key].append(observation)

    return {
        field_key: {
            "count": len(items),
            "precision": _ratio(sum(item.observed_correct is True for item in items), len(items)),
            "correct_count": sum(item.observed_correct is True for item in items),
            "corrected_count": sum(item.observed_correct is False for item in items),
            "mean_confidence": _rounded(sum(item.confidence for item in items) / len(items)),
        }
        for field_key, items in sorted(by_key.items())
    }


def _confidence_bucket_metrics(
    observations: tuple[FieldCalibrationObservation, ...],
    buckets: tuple[float, ...],
) -> list[dict[str, object]]:
    bucketed: list[dict[str, object]] = []
    for start, end in pairwise(buckets):
        items = [
            observation
            for observation in observations
            if _in_bucket(observation.confidence, start, end)
        ]
        if not items:
            continue
        observed_accuracy = _ratio(sum(item.observed_correct is True for item in items), len(items))
        mean_confidence = _rounded(sum(item.confidence for item in items) / len(items))
        bucketed.append(
            {
                "bucket": f"{start:.2f}-{end:.2f}",
                "count": len(items),
                "mean_confidence": mean_confidence,
                "observed_accuracy": observed_accuracy,
                "calibration_gap": _rounded(mean_confidence - observed_accuracy),
            }
        )
    return bucketed


def _threshold_suggestions(
    *,
    precision: float,
    recall: float,
    auto_accept_precision: float,
    threshold_config: ThresholdConfig,
) -> dict[str, dict[str, object]]:
    return {
        "field_auto_accept_min": {
            "current": threshold_config.field_auto_accept_min,
            "direction": _direction(auto_accept_precision, high_water=0.95, low_water=0.85),
            "basis": "auto_accept_precision",
            "observed": auto_accept_precision,
        },
        "key_field_confidence_min": {
            "current": threshold_config.key_field_confidence_min,
            "direction": _direction(precision, high_water=0.92, low_water=0.8),
            "basis": "overall_precision",
            "observed": precision,
        },
        "document_key_field_coverage_min": {
            "current": threshold_config.document_key_field_coverage_min,
            "direction": _direction(recall, high_water=0.9, low_water=0.75),
            "basis": "overall_recall",
            "observed": recall,
        },
        "mandatory_field_min": {
            "current": threshold_config.mandatory_field_min,
            "direction": _direction(precision, high_water=0.95, low_water=0.85),
            "basis": "overall_precision",
            "observed": precision,
        },
    }


def _direction(observed: float, *, high_water: float, low_water: float) -> str:
    if observed < low_water:
        return "raise"
    if observed >= high_water:
        return "consider_lowering"
    return "hold"


def _validate_buckets(buckets: tuple[float, ...]) -> None:
    if len(buckets) < 2:
        raise ValueError("at least two confidence bucket boundaries are required")
    if buckets[0] != 0.0 or buckets[-1] != 1.0:
        raise ValueError("confidence buckets must start at 0.0 and end at 1.0")
    if any(left >= right for left, right in pairwise(buckets)):
        raise ValueError("confidence buckets must be strictly increasing")


def _in_bucket(value: float, start: float, end: float) -> bool:
    if end == 1.0:
        return start <= value <= end
    return start <= value < end


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return _rounded(numerator / denominator)


def _rounded(value: float) -> float:
    return round(value, 4)
