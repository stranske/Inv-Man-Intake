"""Trace wrappers with enable/disable toggle and context propagation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, MutableMapping, Protocol
from uuid import uuid4

TRACE_CONTEXT_PREFIX = "x-trace-"
TRACE_ID_KEY = f"{TRACE_CONTEXT_PREFIX}id"
RUN_ID_KEY = f"{TRACE_CONTEXT_PREFIX}run-id"
PARENT_RUN_ID_KEY = f"{TRACE_CONTEXT_PREFIX}parent-run-id"
PARENT_SPAN_ID_KEY = f"{TRACE_CONTEXT_PREFIX}parent-span-id"
TAGS_KEY = f"{TRACE_CONTEXT_PREFIX}tags"


@dataclass(frozen=True)
class TraceContext:
    """Trace context propagated across pipeline stages."""

    trace_id: str
    run_id: str | None = None
    parent_run_id: str | None = None
    parent_span_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TraceEvent:
    """One span event captured by the trace sink."""

    kind: str
    span_id: str
    trace_id: str
    run_id: str | None
    name: str
    parent_run_id: str | None
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


class RunHandle:
    """Context-manager run that emits start/end events through sink."""

    def __init__(self, sink: TraceSink, event: TraceEvent) -> None:
        self._sink = sink
        self._event = event

    def __enter__(self) -> RunHandle:
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
            kind="span",
            span_id=_new_id(prefix="span"),
            trace_id=context.trace_id,
            run_id=context.run_id,
            name=name,
            parent_run_id=context.parent_run_id,
            parent_span_id=context.parent_span_id,
            metadata={} if metadata is None else dict(metadata),
            started_at=_utc_now_iso(),
        )
        return SpanHandle(self._sink, event)

    def start_run(
        self,
        name: str,
        context: TraceContext,
        metadata: dict[str, Any] | None = None,
    ) -> RunHandle | NoopSpan:
        if not self._enabled or self._sink is None:
            return NoopSpan()

        run_id = context.run_id or _new_id(prefix="run")
        event = TraceEvent(
            kind="run",
            span_id=run_id,
            trace_id=context.trace_id,
            run_id=run_id,
            name=name,
            parent_run_id=context.parent_run_id,
            parent_span_id=context.parent_span_id,
            metadata={} if metadata is None else dict(metadata),
            started_at=_utc_now_iso(),
        )
        return RunHandle(self._sink, event)


def new_trace_context(tags: dict[str, str] | None = None) -> TraceContext:
    """Create a new root trace context."""
    run_id = _new_id(prefix="run")
    return TraceContext(
        trace_id=_new_id(prefix="trace"),
        run_id=run_id,
        parent_run_id=None,
        tags={} if tags is None else dict(tags),
    )


def child_trace_context(
    parent: TraceContext, parent_span_id: str, tags: dict[str, str] | None = None
) -> TraceContext:
    """Derive a child context from parent trace context and parent span."""
    merged_tags = dict(parent.tags)
    if tags:
        merged_tags.update(tags)
    return TraceContext(
        trace_id=parent.trace_id,
        run_id=parent.run_id,
        parent_run_id=parent.parent_run_id,
        parent_span_id=parent_span_id,
        tags=merged_tags,
    )


def child_run_context(
    parent: TraceContext, parent_run_id: str, tags: dict[str, str] | None = None
) -> TraceContext:
    """Derive a child context from parent trace context and parent run."""
    merged_tags = dict(parent.tags)
    if tags:
        merged_tags.update(tags)
    return TraceContext(
        trace_id=parent.trace_id,
        run_id=_new_id(prefix="run"),
        parent_run_id=parent_run_id,
        parent_span_id=parent.parent_span_id,
        tags=merged_tags,
    )


def inject_trace_context(
    context: TraceContext,
    carrier: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Inject context into a string carrier for cross-service propagation."""
    target = {} if carrier is None else carrier
    target[TRACE_ID_KEY] = context.trace_id
    if context.run_id:
        target[RUN_ID_KEY] = context.run_id
    if context.parent_run_id:
        target[PARENT_RUN_ID_KEY] = context.parent_run_id
    if context.parent_span_id:
        target[PARENT_SPAN_ID_KEY] = context.parent_span_id
    if context.tags:
        target[TAGS_KEY] = json.dumps(context.tags, sort_keys=True)
    return dict(target)


def extract_trace_context(carrier: Mapping[str, str]) -> TraceContext | None:
    """Extract context from a string carrier, returning ``None`` if missing."""
    trace_id = carrier.get(TRACE_ID_KEY)
    if trace_id is None or trace_id.strip() == "":
        return None

    raw_tags = carrier.get(TAGS_KEY)
    tags: dict[str, str] = {}
    if raw_tags:
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, dict):
                tags = {str(key): str(value) for key, value in parsed.items()}
        except json.JSONDecodeError:
            tags = {}

    return TraceContext(
        trace_id=trace_id,
        run_id=carrier.get(RUN_ID_KEY),
        parent_run_id=carrier.get(PARENT_RUN_ID_KEY),
        parent_span_id=carrier.get(PARENT_SPAN_ID_KEY),
        tags=tags,
    )


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
