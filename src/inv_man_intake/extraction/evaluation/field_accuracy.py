"""Field-level extraction accuracy harness for real-document samples."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inv_man_intake.extraction.providers.base import ExtractionProvider


@dataclass(frozen=True)
class FieldExpectation:
    """Expected field value for one evaluated document."""

    key: str
    value: str


@dataclass(frozen=True)
class EvaluationSample:
    """Document bytes and expected field values for one extraction run."""

    source_doc_id: str
    content: bytes
    expected_fields: tuple[FieldExpectation, ...]


@dataclass(frozen=True)
class FieldAccuracyReport:
    """Aggregate field-level accuracy metrics."""

    provider_name: str
    evaluated_fields: int
    matched_fields: int
    missing_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]

    @property
    def accuracy(self) -> float:
        if self.evaluated_fields == 0:
            return 0.0
        return self.matched_fields / self.evaluated_fields


class _ProviderFactory(Protocol):
    def __call__(self) -> ExtractionProvider: ...


def evaluate_field_accuracy(
    *,
    provider_factory: _ProviderFactory,
    samples: tuple[EvaluationSample, ...],
) -> FieldAccuracyReport:
    """Run a provider over samples and compute exact normalized field accuracy."""

    provider = provider_factory()
    matched = 0
    evaluated = 0
    missing: list[str] = []
    mismatched: list[str] = []

    for sample in samples:
        try:
            result = provider.extract(source_doc_id=sample.source_doc_id, content=sample.content)
        except Exception:  # noqa: BLE001 - record the sample failure and continue.
            for expected in sample.expected_fields:
                evaluated += 1
                missing.append(f"{sample.source_doc_id}:{expected.key}")
            continue

        actual: dict[str, str] = {}
        duplicate_keys: set[str] = set()
        for field in result.fields:
            key = _normalize(field.key)
            if key in actual:
                duplicate_keys.add(key)
            actual[key] = _normalize(field.value)

        for expected in sample.expected_fields:
            evaluated += 1
            key = _normalize(expected.key)
            expected_value = _normalize(expected.value)
            actual_value = actual.get(key)
            field_ref = f"{sample.source_doc_id}:{expected.key}"
            if actual_value is None:
                missing.append(field_ref)
            elif key in duplicate_keys:
                mismatched.append(field_ref)
            elif actual_value == expected_value:
                matched += 1
            else:
                mismatched.append(field_ref)

    return FieldAccuracyReport(
        provider_name=provider.name,
        evaluated_fields=evaluated,
        matched_fields=matched,
        missing_fields=tuple(missing),
        mismatched_fields=tuple(mismatched),
    )


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())
