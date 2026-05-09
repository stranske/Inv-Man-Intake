"""Tests for LangSmith tracing setup validation helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from inv_man_intake.observability.setup_validation import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_API_KEY_ENV_KEY,
    LANGSMITH_PROJECT_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    main,
    validate_langsmith_setup,
)


class FakeLangSmithClient:
    def __init__(self, record_create: bool = True) -> None:
        self.record_create = record_create
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[tuple[UUID, dict[str, Any]]] = []

    def create_run(self, **kwargs: Any) -> None:
        if self.record_create:
            self.create_calls.append(kwargs)

    def update_run(self, run_id: UUID, **kwargs: Any) -> None:
        self.update_calls.append((run_id, kwargs))


def test_validate_langsmith_setup_accepts_valid_required_env() -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    result = validate_langsmith_setup(env=env)

    assert result.is_valid is True
    assert result.errors == ()
    assert result.warnings == ()


def test_validate_langsmith_setup_probe_emits_mocked_span() -> None:
    client = FakeLangSmithClient()
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    result = validate_langsmith_setup(
        env=env,
        probe_emit=True,
        client_factory=lambda: client,
    )

    assert result.is_valid is True
    assert len(client.create_calls) == 1
    assert client.create_calls[0]["name"] == "langsmith_setup_probe"


def test_validate_langsmith_setup_probe_fails_when_client_records_no_run() -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    result = validate_langsmith_setup(
        env=env,
        probe_emit=True,
        client_factory=lambda: FakeLangSmithClient(record_create=False),
    )

    assert result.is_valid is False
    assert any("probe emitted no run" in message for message in result.errors)


def test_validate_langsmith_setup_requires_api_key() -> None:
    env = {
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    result = validate_langsmith_setup(env=env)

    assert result.is_valid is False
    assert any("LANGSMITH_API_KEY" in message for message in result.errors)


def test_validate_langsmith_setup_supports_langsmith_toggle_fallback() -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        "LANGSMITH_TRACING_ENABLED": "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    result = validate_langsmith_setup(env=env)

    assert result.is_valid is True
    assert result.errors == ()


def test_validate_langsmith_setup_errors_when_langchain_toggle_disabled() -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "false",
    }

    result = validate_langsmith_setup(env=env)

    assert result.is_valid is False
    assert any(LANGCHAIN_TRACE_ENABLED_ENV_KEY in message for message in result.errors)


def test_main_returns_failure_when_project_is_required_but_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    exit_code = main(argv=["--require-project"], env=env)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR:" in captured.out
    assert "LangSmith setup validation failed." in captured.out


def test_main_returns_success_for_valid_env(capsys: pytest.CaptureFixture[str]) -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    exit_code = main(argv=[], env=env)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "LangSmith setup validation passed." in captured.out


def test_main_probe_uses_mocked_client(capsys: pytest.CaptureFixture[str]) -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    exit_code = main(
        argv=["--probe"],
        env=env,
        client_factory=lambda: FakeLangSmithClient(),
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "LangSmith setup validation passed." in captured.out


def test_main_probe_returns_failure_when_no_run_recorded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {
        LANGSMITH_API_KEY_ENV_KEY: "lsv2_pt_123456",
        LANGSMITH_PROJECT_ENV_KEY: "inv-man-intake-dev",
        TRACE_ENABLED_ENV_KEY: "true",
        LANGCHAIN_TRACE_ENABLED_ENV_KEY: "true",
    }

    exit_code = main(
        argv=["--probe"],
        env=env,
        client_factory=lambda: FakeLangSmithClient(record_create=False),
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "ERROR:" in captured.out
    assert "probe emitted no run" in captured.out
