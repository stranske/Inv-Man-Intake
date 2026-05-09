"""LangSmith tracing setup validation helpers and CLI."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from .langsmith_sink import ClientFactory, LangSmithClient, LangSmithTraceSink
from .tracing import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_API_KEY_ENV_KEY,
    LANGSMITH_PROJECT_ENV_KEY,
    LANGSMITH_TRACE_ENABLED_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    Tracer,
    new_trace_context,
    tracing_enabled_from_env,
)

__all__ = [
    "LANGCHAIN_TRACE_ENABLED_ENV_KEY",
    "LANGSMITH_API_KEY_ENV_KEY",
    "LANGSMITH_PROJECT_ENV_KEY",
    "TRACE_ENABLED_ENV_KEY",
    "SetupValidationResult",
    "validate_langsmith_setup",
    "main",
]


@dataclass(frozen=True)
class SetupValidationResult:
    """Validation result for LangSmith tracing setup."""

    is_valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_langsmith_setup(
    env: Mapping[str, str] | None = None,
    require_project: bool = False,
    probe_emit: bool = False,
    client_factory: ClientFactory | None = None,
) -> SetupValidationResult:
    """Validate required environment for LangSmith tracing setup."""
    source = env if env is not None else os.environ
    errors: list[str] = []
    warnings: list[str] = []

    api_key = source.get(LANGSMITH_API_KEY_ENV_KEY, "").strip()
    if api_key == "":
        errors.append(f"{LANGSMITH_API_KEY_ENV_KEY} is required and must be non-empty.")
    elif "..." in api_key:
        errors.append(
            f"{LANGSMITH_API_KEY_ENV_KEY} looks like a placeholder value; set a real API key."
        )

    if TRACE_ENABLED_ENV_KEY not in source and LANGSMITH_TRACE_ENABLED_ENV_KEY not in source:
        errors.append(
            f"Set {TRACE_ENABLED_ENV_KEY}=true (preferred) or "
            f"{LANGSMITH_TRACE_ENABLED_ENV_KEY}=true."
        )

    if not tracing_enabled_from_env(env=source, default_enabled=False):
        errors.append(
            "Tracing toggles resolve to disabled; set "
            f"{TRACE_ENABLED_ENV_KEY}=true (preferred) or "
            f"{LANGSMITH_TRACE_ENABLED_ENV_KEY}=true."
        )

    langchain_toggle = source.get(LANGCHAIN_TRACE_ENABLED_ENV_KEY)
    if langchain_toggle is None:
        errors.append(f"Set {LANGCHAIN_TRACE_ENABLED_ENV_KEY}=true.")
    elif _parse_bool(langchain_toggle) is not True:
        errors.append(f"{LANGCHAIN_TRACE_ENABLED_ENV_KEY} must be set to a true value.")

    project_name = source.get(LANGSMITH_PROJECT_ENV_KEY, "").strip()
    if project_name == "":
        message = (
            f"{LANGSMITH_PROJECT_ENV_KEY} is recommended to avoid writing traces "
            "to the default project."
        )
        if require_project:
            errors.append(message.replace(" is recommended", " is required"))
        else:
            warnings.append(message)

    if probe_emit and len(errors) == 0:
        try:
            probe_client = _ProbeClient((client_factory or _default_probe_client_factory)())
            sink = LangSmithTraceSink(
                client=probe_client,
                project_name=project_name or None,
            )
            tracer = Tracer(enabled=True, sink=sink)
            context = new_trace_context(tags={"validation": "langsmith_probe"})
            with tracer.start_span(
                name="langsmith_setup_probe",
                context=context,
                metadata={"probe": True},
            ):
                pass
            if probe_client.observed_run_count == 0:
                errors.append("LangSmith probe emitted no run; verify client wiring.")
        except Exception as exc:  # pragma: no cover - exact client failures vary.
            errors.append(f"LangSmith probe failed to emit a trace span: {exc}")

    return SetupValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory | None = None,
) -> int:
    """CLI entrypoint for setup validation."""
    parser = argparse.ArgumentParser(
        prog="python -m inv_man_intake.observability.setup_validation",
        description="Validate LangSmith tracing environment setup.",
    )
    parser.add_argument(
        "--require-project",
        action="store_true",
        help=f"Require {LANGSMITH_PROJECT_ENV_KEY} to be set.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Emit one probe span through the configured LangSmith client.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = validate_langsmith_setup(
        env=env,
        require_project=args.require_project,
        probe_emit=args.probe,
        client_factory=client_factory,
    )

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if result.is_valid:
        print("LangSmith setup validation passed.")
        return 0

    print("LangSmith setup validation failed.")
    return 1


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


class _ProbeClient:
    def __init__(self, client: LangSmithClient) -> None:
        self._client = client
        self.create_run_count = 0

    def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"],
        **kwargs: Any,
    ) -> Any:
        self.create_run_count += 1
        return self._client.create_run(name=name, inputs=inputs, run_type=run_type, **kwargs)

    def update_run(self, run_id: UUID, **kwargs: Any) -> Any:
        return self._client.update_run(run_id, **kwargs)

    @property
    def observed_run_count(self) -> int:
        create_calls = getattr(self._client, "create_calls", None)
        if isinstance(create_calls, list):
            return len(create_calls)
        return self.create_run_count


def _default_probe_client_factory() -> LangSmithClient:
    from langsmith import Client

    return Client()


if __name__ == "__main__":
    raise SystemExit(main())
