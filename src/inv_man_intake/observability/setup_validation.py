"""LangSmith tracing setup validation helpers and CLI."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .tracing import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_TRACE_ENABLED_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    tracing_enabled_from_env,
)

LANGSMITH_API_KEY_ENV_KEY = "LANGSMITH_API_KEY"
LANGSMITH_PROJECT_ENV_KEY = "LANGSMITH_PROJECT"


@dataclass(frozen=True)
class SetupValidationResult:
    """Validation result for LangSmith tracing setup."""

    is_valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_langsmith_setup(
    env: Mapping[str, str] | None = None,
    require_project: bool = False,
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

    return SetupValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
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
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = validate_langsmith_setup(env=env, require_project=args.require_project)

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


if __name__ == "__main__":
    raise SystemExit(main())
