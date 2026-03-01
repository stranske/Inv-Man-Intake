"""Trace wrappers with enable/disable toggle and context propagation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class TraceContext:
    """Trace context propagated across pipeline stages."""

    trace_id: str
    parent_span_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TraceEvent:
    """One span event captured by the trace sink."""

    span_id: str
    trace_id: str
    name: str
    parent_span_id: str | None
    metadata: dict[str, Any]
    started_at: str
    ended_at: str | None = None


class TraceSink(Protocol):
    """Sink interface for trace event emission."""

    def on_span_start(self, event: TraceEvent) -> None:
        """Capture trace span start event."""

    def on_span_end(self, event: TraceEvent) -> None:
        """Capture trace span end event."""


class InMemoryTraceSink:
    """In-memory sink useful for tests and local debugging."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def on_span_start(self, event: TraceEvent) -> None:
        self.events.append(event)

    def on_span_end(self, event: TraceEvent) -> None:
        self.events.append(event)


class NoopSpan:
    """No-op span for disabled tracing mode."""

    def __enter__(self) -> NoopSpan:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class SpanHandle:
    """Context-manager span that emits start/end events through sink."""

    def __init__(self, sink: TraceSink, event: TraceEvent) -> None:
        self._sink = sink
        self._event = event

    def __enter__(self) -> SpanHandle:
        self._sink.on_span_start(self._event)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._event.ended_at = _utc_now_iso()
        self._sink.on_span_end(self._event)


class Tracer:
    """Minimal trace wrapper with explicit enable toggle."""

    def __init__(self, enabled: bool, sink: TraceSink | None = None) -> None:
        self._enabled = enabled
        self._sink = sink

    def start_span(
        self,
        name: str,
        context: TraceContext,
        metadata: dict[str, Any] | None = None,
    ) -> SpanHandle | NoopSpan:
        if not self._enabled or self._sink is None:
            return NoopSpan()

        event = TraceEvent(
            span_id=_new_id(prefix="span"),
            trace_id=context.trace_id,
            name=name,
            parent_span_id=context.parent_span_id,
            metadata={} if metadata is None else dict(metadata),
            started_at=_utc_now_iso(),
        )
        return SpanHandle(self._sink, event)


def new_trace_context(tags: dict[str, str] | None = None) -> TraceContext:
    """Create a new root trace context."""
    return TraceContext(trace_id=_new_id(prefix="trace"), tags={} if tags is None else dict(tags))


def child_trace_context(
    parent: TraceContext, parent_span_id: str, tags: dict[str, str] | None = None
) -> TraceContext:
    """Derive a child context from parent trace context and parent span."""
    merged_tags = dict(parent.tags)
    if tags:
        merged_tags.update(tags)
    return TraceContext(trace_id=parent.trace_id, parent_span_id=parent_span_id, tags=merged_tags)


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
