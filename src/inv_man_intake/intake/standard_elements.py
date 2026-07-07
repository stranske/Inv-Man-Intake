"""Data-driven standard-element-library port for intake packet routing."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

Standardness = Literal["unknown"]
Detector = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class StandardElement:
    """One externally-authored element contract entry."""

    key: str
    detector_name: str
    mandatory: bool = False


@dataclass(frozen=True)
class ElementCoverage:
    """Coverage result for a single element without standardness judgment."""

    key: str
    detected: bool
    mandatory: bool
    standardness: Standardness


class StandardElementLibrary(Protocol):
    """Minimal port the intake app consumes from a standard-element library."""

    non_authoritative: bool

    def doc_types(self) -> tuple[str, ...]:
        """Return document type identifiers supplied by library data."""

    def elements_for(self, doc_type: str) -> tuple[StandardElement, ...]:
        """Return element specs for a document type."""

    def evaluate_coverage(
        self, doc_type: str, extracted: Mapping[str, Any]
    ) -> tuple[ElementCoverage, ...]:
        """Evaluate element detector coverage for extracted data."""


class DataDrivenStandardElementLibrary:
    """Runtime-loaded standard-element library backed only by data."""

    def __init__(
        self,
        *,
        version: str,
        non_authoritative: bool,
        elements_by_doc_type: Mapping[str, tuple[StandardElement, ...]],
        detectors: Mapping[str, Detector] | None = None,
    ) -> None:
        if not version:
            raise ValueError("standard element library version must be non-empty")
        if not elements_by_doc_type:
            raise ValueError("standard element library must define at least one document type")
        self.version = version
        self.non_authoritative = non_authoritative
        self._elements_by_doc_type = dict(elements_by_doc_type)
        self._detectors = dict(detectors if detectors is not None else default_detector_registry())
        self._validate_detector_references()

    def doc_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._elements_by_doc_type))

    def elements_for(self, doc_type: str) -> tuple[StandardElement, ...]:
        try:
            return self._elements_by_doc_type[doc_type]
        except KeyError as exc:
            raise KeyError(f"unknown standard-element doc_type: {doc_type}") from exc

    def evaluate_coverage(
        self, doc_type: str, extracted: Mapping[str, Any]
    ) -> tuple[ElementCoverage, ...]:
        coverage: list[ElementCoverage] = []
        for element in self.elements_for(doc_type):
            detector = self._detectors[element.detector_name]
            detector_payload = {**extracted, "field_key": element.key}
            coverage.append(
                ElementCoverage(
                    key=element.key,
                    detected=detector(detector_payload),
                    mandatory=element.mandatory,
                    standardness=classify_element_standardness(
                        element=element, extracted=extracted
                    ),
                )
            )
        return tuple(coverage)

    def _validate_detector_references(self) -> None:
        missing = sorted(
            {
                element.detector_name
                for elements in self._elements_by_doc_type.values()
                for element in elements
                if element.detector_name not in self._detectors
            }
        )
        if missing:
            raise ValueError(f"unknown detector reference(s): {', '.join(missing)}")


def register_detector(
    registry: Mapping[str, Detector],
    name: str,
    detector: Detector,
) -> dict[str, Detector]:
    """Return a detector registry with one additional named detector."""

    if not name:
        raise ValueError("detector name must be non-empty")
    updated = dict(registry)
    updated[name] = detector
    return updated


def default_detector_registry() -> dict[str, Detector]:
    """Detectors used by the deliberately dumb stub library."""

    return {
        "field_present": _field_present_detector,
        "numeric_field_present": _numeric_field_present_detector,
    }


def load_standard_element_library(
    source: str | Path | Mapping[str, Any],
    *,
    detectors: Mapping[str, Detector] | None = None,
) -> DataDrivenStandardElementLibrary:
    """Load and validate a standard-element library from JSON-like data."""

    payload = _read_payload(source)
    if not isinstance(payload, Mapping):
        raise ValueError("standard element library root must be an object")
    doc_type_payload = payload.get("doc_types")
    if not isinstance(doc_type_payload, Mapping):
        raise ValueError("standard element library must contain object field 'doc_types'")

    elements_by_doc_type: dict[str, tuple[StandardElement, ...]] = {}
    for doc_type, raw_elements in doc_type_payload.items():
        if not isinstance(doc_type, str) or not doc_type:
            raise ValueError("document type identifiers must be non-empty strings")
        if not isinstance(raw_elements, list) or not raw_elements:
            raise ValueError(f"doc_type {doc_type!r} must define a non-empty element list")
        elements = tuple(
            _parse_standard_element(doc_type=doc_type, raw_element=raw_element)
            for raw_element in raw_elements
        )
        duplicate_keys = sorted(
            key for key in {element.key for element in elements} if _count_key(elements, key) > 1
        )
        if duplicate_keys:
            raise ValueError(
                f"doc_type {doc_type!r} contains duplicate element key(s): "
                + ", ".join(duplicate_keys)
            )
        elements_by_doc_type[doc_type] = elements

    return DataDrivenStandardElementLibrary(
        version=_required_string(payload, "version"),
        non_authoritative=_required_bool(payload, "non_authoritative"),
        elements_by_doc_type=elements_by_doc_type,
        detectors=detectors,
    )


def classify_element_standardness(
    *,
    element: StandardElement,
    extracted: Mapping[str, Any],
) -> Standardness:
    """Placeholder for future human-authored standardness logic."""

    _ = element, extracted
    return "unknown"


def _read_payload(source: str | Path | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    path = Path(source)
    return cast(Mapping[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _parse_standard_element(
    *,
    doc_type: str,
    raw_element: object,
) -> StandardElement:
    if not isinstance(raw_element, Mapping):
        raise ValueError(f"element entry for {doc_type!r} must be an object")
    return StandardElement(
        key=_required_string(raw_element, "key"),
        detector_name=_required_string(raw_element, "detector_name"),
        mandatory=_required_bool(raw_element, "mandatory"),
    )


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"standard element library field {key!r} must be a non-empty string")
    return value


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"standard element library field {key!r} must be a boolean")
    return value


def _count_key(elements: tuple[StandardElement, ...], key: str) -> int:
    return sum(1 for element in elements if element.key == key)


def _field_present_detector(extracted: Mapping[str, Any]) -> bool:
    field_key = extracted.get("field_key")
    if not isinstance(field_key, str):
        return False
    fields = extracted.get("fields", ())
    return field_key in fields


def _numeric_field_present_detector(extracted: Mapping[str, Any]) -> bool:
    if not _field_present_detector(extracted):
        return False
    field_key = extracted.get("field_key")
    values = extracted.get("values")
    value = (
        values.get(field_key)
        if isinstance(field_key, str) and isinstance(values, Mapping)
        else extracted.get("value")
    )
    return isinstance(value, int | float) and not isinstance(value, bool)
