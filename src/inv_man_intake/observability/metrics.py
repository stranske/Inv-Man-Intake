"""Operational metric counters for intake pipeline observability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

FAILURE_COUNT = "pipeline_failure_total"
FALLBACK_COUNT = "pipeline_fallback_total"
ESCALATION_COUNT = "pipeline_escalation_total"
LATENCY_MS = "pipeline_latency_ms"


@dataclass(frozen=True)
class MetricPoint:
    """One metric point value and the tags that scoped it."""

    name: str
    value: float
    tags: Mapping[str, str]


class InMemoryMetrics:
    """Simple in-memory counter/timer sink for deterministic tests."""

    def __init__(self) -> None:
        self._points: list[MetricPoint] = []

    def increment(self, name: str, *, by: float = 1.0, tags: Mapping[str, str] | None = None) -> None:
        self._points.append(
            MetricPoint(name=name, value=by, tags=dict(tags or {}))
        )

    def observe_ms(self, name: str, milliseconds: float, *, tags: Mapping[str, str] | None = None) -> None:
        self._points.append(
            MetricPoint(name=name, value=milliseconds, tags=dict(tags or {}))
        )

    def record_failure(self, *, stage: str, error_code: str) -> None:
        self.increment(
            FAILURE_COUNT,
            tags={"stage": stage, "error_code": error_code},
        )

    def record_fallback(self, *, stage: str, reason: str) -> None:
        self.increment(
            FALLBACK_COUNT,
            tags={"stage": stage, "reason": reason},
        )

    def record_escalation(self, *, stage: str, reason: str) -> None:
        self.increment(
            ESCALATION_COUNT,
            tags={"stage": stage, "reason": reason},
        )

    def record_latency(self, *, stage: str, milliseconds: float, status: str) -> None:
        self.observe_ms(
            LATENCY_MS,
            milliseconds,
            tags={"stage": stage, "status": status},
        )

    def points(self) -> tuple[MetricPoint, ...]:
        return tuple(self._points)

    def count(self, name: str, *, tags: Mapping[str, str] | None = None) -> float:
        expected_tags = dict(tags or {})
        return sum(
            point.value
            for point in self._points
            if point.name == name and dict(point.tags) == expected_tags
        )
