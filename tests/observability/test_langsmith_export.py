"""Tests for LangSmith trace export wiring."""

from __future__ import annotations

import warnings
from typing import Any
from uuid import UUID

from inv_man_intake.observability.langsmith_sink import LangSmithTraceSink
from inv_man_intake.observability.tracing import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_API_KEY_ENV_KEY,
    LANGSMITH_PROJECT_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    InMemoryTraceSink,
    Tracer,
    new_trace_context,
)


class FakeLangSmithClient:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[tuple[UUID, dict[str, Any]]] = []

    def create_run(self, **kwargs: Any) -> None:
        self.create_calls.append(kwargs)

    def update_run(self, run_id: UUID, **kwargs: Any) -> None:
        self.update_calls.append((run_id, kwargs))


def test_langsmith_sink_emits_create_and_update_payloads() -> None:
    client = FakeLangSmithClient()
    sink = LangSmithTraceSink(client=client, project_name="inv-man-intake-dev")
    tracer = Tracer(enabled=True, sink=sink)
    context = new_trace_context(tags={"stage": "intake"})

    with tracer.start_span(
        name="extract_positions",
        context=context,
        metadata={"provider": "primary"},
    ):
        pass

    assert len(client.create_calls) == 1
    create_payload = client.create_calls[0]
    assert create_payload["name"] == "extract_positions"
    assert create_payload["project_name"] == "inv-man-intake-dev"
    assert create_payload["run_type"] == "tool"
    assert create_payload["inputs"]["trace_id"] == context.trace_id
    assert create_payload["extra"]["metadata"] == {"provider": "primary"}
    assert len(client.update_calls) == 1
    update_run_id, update_payload = client.update_calls[0]
    assert update_run_id == create_payload["id"]
    assert update_payload["end_time"] is not None


def test_tracer_from_env_uses_langsmith_sink_when_enabled_with_api_key(
    monkeypatch,
) -> None:
    created_clients: list[FakeLangSmithClient] = []

    def _client_factory() -> FakeLangSmithClient:
        client = FakeLangSmithClient()
        created_clients.append(client)
        return client

    monkeypatch.setattr(
        "inv_man_intake.observability.langsmith_sink._default_client_factory",
        _client_factory,
    )
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_x",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
        TRACE_ENABLED_ENV_KEY: "true",
    }

    tracer = Tracer.from_env(env=env)
    context = new_trace_context()
    with tracer.start_span(name="probe", context=context):
        pass

    assert len(created_clients) == 1
    assert len(created_clients[0].create_calls) == 1


def test_tracer_from_env_does_not_construct_client_when_disabled(monkeypatch) -> None:
    def _client_factory() -> FakeLangSmithClient:
        raise AssertionError("LangSmith client should not be constructed")

    monkeypatch.setattr(
        "inv_man_intake.observability.langsmith_sink._default_client_factory",
        _client_factory,
    )
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_x",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
        TRACE_ENABLED_ENV_KEY: "false",
    }

    tracer = Tracer.from_env(env=env)
    with tracer.start_span(name="disabled", context=new_trace_context()):
        pass


def test_tracer_from_env_falls_back_to_memory_sink_without_api_key() -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
        TRACE_ENABLED_ENV_KEY: "true",
    }

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        tracer = Tracer.from_env(env=env)

    assert isinstance(tracer._sink, InMemoryTraceSink)
    assert any("LANGSMITH_API_KEY is empty" in str(item.message) for item in captured)
