"""Tests for trace wrapper enable/disable behavior and context propagation."""

from __future__ import annotations

from inv_man_intake.observability.tracing import (
    InMemoryTraceSink,
    Tracer,
    child_run_context,
    child_trace_context,
    new_trace_context,
)


def test_tracer_disabled_mode_emits_no_events() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=False, sink=sink)
    context = new_trace_context(tags={"stage": "intake"})

    with tracer.start_span(name="parse", context=context, metadata={"doc": "deck.pdf"}):
        pass

    assert sink.events == []


def test_tracer_enabled_mode_emits_start_and_end_events() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    context = new_trace_context(tags={"stage": "ingestion"})

    with tracer.start_span(name="store", context=context, metadata={"bundle": "pkg_1"}):
        pass

    assert len(sink.events) == 2
    start_event, end_event = sink.events
    assert start_event.trace_id == context.trace_id
    assert start_event.name == "store"
    assert start_event.ended_at is not None
    assert end_event.ended_at is not None


def test_child_trace_context_preserves_trace_id_and_merges_tags() -> None:
    root = new_trace_context(tags={"asset_class": "quant", "stage": "intake"})
    child = child_trace_context(root, parent_span_id="span_parent_1", tags={"stage": "extract"})

    assert child.trace_id == root.trace_id
    assert child.parent_span_id == "span_parent_1"
    assert child.tags["asset_class"] == "quant"
    assert child.tags["stage"] == "extract"


def test_tracer_start_run_emits_run_event() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    context = new_trace_context(tags={"stage": "workflow"})

    with tracer.start_run(name="intake", context=context, metadata={"repo": "Inv-Man-Intake"}):
        pass

    assert len(sink.events) == 2
    run_start, run_end = sink.events
    assert run_start.kind == "run"
    assert run_start.trace_id == context.trace_id
    assert run_start.run_id is not None
    assert run_start.ended_at is not None
    assert run_end.kind == "run"
    assert run_end.run_id == run_start.run_id
    assert run_end.ended_at is not None


def test_child_run_context_preserves_trace_and_sets_parent_run() -> None:
    root = new_trace_context(tags={"stage": "intake"})
    child = child_run_context(root, parent_run_id="run_parent_1", tags={"stage": "extract"})

    assert child.trace_id == root.trace_id
    assert child.run_id is not None
    assert child.parent_run_id == "run_parent_1"
    assert child.tags["stage"] == "extract"
