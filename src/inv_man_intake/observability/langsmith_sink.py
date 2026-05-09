"""LangSmith trace sink for repository trace events."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from .tracing import LANGSMITH_PROJECT_ENV_KEY, TraceEvent


class LangSmithClient(Protocol):
    """Minimal LangSmith client surface used by the trace sink."""

    def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"],
        **kwargs: Any,
    ) -> Any:
        """Create a LangSmith run."""

    def update_run(self, run_id: UUID, **kwargs: Any) -> Any:
        """Update a LangSmith run."""


ClientFactory = Callable[[], LangSmithClient]


class LangSmithTraceSink:
    """Emit trace events to LangSmith through ``langsmith.Client``."""

    def __init__(
        self,
        client: LangSmithClient | None = None,
        client_factory: ClientFactory | None = None,
        project_name: str | None = None,
    ) -> None:
        self._client = client
        self._client_factory = client_factory or _default_client_factory
        self._project_name = project_name

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LangSmithTraceSink:
        """Create a sink using the LangSmith project configured in env."""
        source = env if env is not None else os.environ
        project_name = source.get(LANGSMITH_PROJECT_ENV_KEY, "").strip() or None
        return cls(project_name=project_name)

    def on_span_start(self, event: TraceEvent) -> None:
        run_id = _event_run_uuid(event)
        payload: dict[str, Any] = {
            "id": run_id,
            "name": event.name,
            "run_type": "chain" if event.kind == "run" else "tool",
            "inputs": {
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "run_id": event.run_id,
            },
            "start_time": event.started_at,
            "extra": {
                "metadata": event.metadata,
                "trace": {
                    "kind": event.kind,
                    "trace_id": event.trace_id,
                    "span_id": event.span_id,
                    "run_id": event.run_id,
                    "parent_run_id": event.parent_run_id,
                    "parent_span_id": event.parent_span_id,
                },
            },
        }
        if self._project_name:
            payload["project_name"] = self._project_name
        parent_id = _parent_run_uuid(event)
        if parent_id is not None:
            payload["parent_run_id"] = parent_id

        self._get_client().create_run(**payload)

    def on_span_end(self, event: TraceEvent) -> None:
        payload: dict[str, Any] = {
            "end_time": event.ended_at,
            "outputs": {
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "metadata": event.metadata,
            },
        }
        self._get_client().update_run(_event_run_uuid(event), **payload)

    def _get_client(self) -> LangSmithClient:
        if self._client is None:
            self._client = self._client_factory()
        return self._client


def _default_client_factory() -> LangSmithClient:
    from langsmith import Client

    return Client()


def _event_run_uuid(event: TraceEvent) -> UUID:
    return uuid5(NAMESPACE_URL, f"{event.trace_id}:{event.span_id}")


def _parent_run_uuid(event: TraceEvent) -> UUID | None:
    parent_id = event.parent_run_id or event.parent_span_id
    if parent_id is None:
        return None
    return uuid5(NAMESPACE_URL, f"{event.trace_id}:{parent_id}")
