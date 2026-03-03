"""Tests for LangSmith tracing setup validation helpers."""

from __future__ import annotations

from inv_man_intake.observability.setup_validation import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_API_KEY_ENV_KEY,
    LANGSMITH_PROJECT_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    main,
    validate_langsmith_setup,
)


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


def test_main_returns_failure_when_project_is_required_but_missing(capsys) -> None:
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


def test_main_returns_success_for_valid_env(capsys) -> None:
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
