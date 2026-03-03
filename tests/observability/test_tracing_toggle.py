"""Tests for trace wrapper enable/disable behavior and context propagation."""

from __future__ import annotations

from inv_man_intake.observability.tracing import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_TRACE_ENABLED_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    InMemoryTraceSink,
    Tracer,
    child_run_context,
    child_trace_context,
    extract_trace_context,
    inject_trace_context,
    new_trace_context,
    tracing_enabled_from_env,
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
    assert start_event.ended_at is None
    assert end_event.ended_at is not None
    assert start_event.span_id == end_event.span_id


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
    assert run_start.ended_at is None
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


def test_trace_context_inject_and_extract_round_trip() -> None:
    context = new_trace_context(tags={"stage": "intake", "asset_class": "credit"})
    context = child_trace_context(
        context,
        parent_span_id="span_parent_7",
        tags={"stage": "extract"},
    )

    carrier = inject_trace_context(context)
    extracted = extract_trace_context(carrier)

    assert extracted is not None
    assert extracted.trace_id == context.trace_id
    assert extracted.run_id == context.run_id
    assert extracted.parent_span_id == "span_parent_7"
    assert extracted.tags == context.tags


def test_extract_trace_context_returns_none_without_trace_id() -> None:
    assert extract_trace_context({"x-trace-run-id": "run_123"}) is None


def test_cross_stage_propagation_shares_trace_id() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    root = new_trace_context(tags={"stage": "intake"})

    with tracer.start_span(name="intake", context=root):
        pass

    intake_start = sink.events[0]
    carrier = inject_trace_context(root)
    extracted = extract_trace_context(carrier)
    assert extracted is not None
    stage_two = child_trace_context(
        extracted,
        parent_span_id=intake_start.span_id,
        tags={"stage": "extract"},
    )

    with tracer.start_span(name="extract", context=stage_two):
        pass

    extract_start = sink.events[2]
    assert extract_start.trace_id == intake_start.trace_id
    assert extract_start.parent_span_id == intake_start.span_id
    assert stage_two.tags["stage"] == "extract"


def test_cross_service_propagation_uses_shared_trace_context() -> None:
    service_a_sink = InMemoryTraceSink()
    service_b_sink = InMemoryTraceSink()
    service_a_tracer = Tracer(enabled=True, sink=service_a_sink)
    service_b_tracer = Tracer(enabled=True, sink=service_b_sink)

    root = new_trace_context(tags={"service": "intake-api", "stage": "ingest"})
    with service_a_tracer.start_span(name="receive_request", context=root):
        pass
    ingress_span = service_a_sink.events[0]

    outbound_headers = inject_trace_context(root, carrier={"x-request-id": "req_42"})
    inbound_context = extract_trace_context(outbound_headers)
    assert inbound_context is not None
    downstream_context = child_trace_context(
        inbound_context,
        parent_span_id=ingress_span.span_id,
        tags={"service": "extract-worker", "stage": "extract"},
    )

    with service_b_tracer.start_span(name="extract_positions", context=downstream_context):
        pass

    downstream_start = service_b_sink.events[0]
    assert downstream_start.trace_id == ingress_span.trace_id
    assert downstream_start.parent_span_id == ingress_span.span_id
    assert downstream_context.tags["service"] == "extract-worker"
    assert downstream_context.tags["stage"] == "extract"


def test_tracing_enabled_from_env_defaults_to_disabled() -> None:
    assert tracing_enabled_from_env(env={}) is False


def test_tracing_enabled_from_env_honors_primary_toggle() -> None:
    env = {TRACE_ENABLED_ENV_KEY: "true"}
    assert tracing_enabled_from_env(env=env) is True


def test_tracing_enabled_from_env_primary_toggle_can_disable() -> None:
    env = {
        TRACE_ENABLED_ENV_KEY: "false",
        LANGSMITH_TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }
    assert tracing_enabled_from_env(env=env, default_enabled=True) is False


def test_tracing_enabled_from_env_falls_back_to_langchain_toggle() -> None:
    env = {LANGCHAIN_TRACE_ENABLED_ENV_KEY: "yes"}
    assert tracing_enabled_from_env(env=env) is True


def test_tracing_enabled_from_env_falls_back_to_langsmith_toggle() -> None:
    env = {LANGSMITH_TRACE_ENABLED_ENV_KEY: "on"}
    assert tracing_enabled_from_env(env=env) is True


def test_tracing_enabled_from_env_uses_default_for_invalid_value() -> None:
    env = {TRACE_ENABLED_ENV_KEY: "not-a-bool"}
    assert tracing_enabled_from_env(env=env, default_enabled=True) is True


def test_tracer_from_env_uses_resolved_toggle() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer.from_env(sink=sink, env={TRACE_ENABLED_ENV_KEY: "1"})
    context = new_trace_context(tags={"stage": "config"})

    with tracer.start_span(name="parse", context=context):
        pass

    assert len(sink.events) == 2
