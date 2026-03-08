"""Integration helpers for registering intake bundles from fixture-style payloads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from inv_man_intake.contracts.intake_contract import IntakeValidationIssue, validate_intake_payload
from inv_man_intake.intake.models import IngestStatus, IntakeFile
from inv_man_intake.intake.service import IngestionService


@dataclass(frozen=True)
class IntakeRegistrationResult:
    """Outcome for one intake bundle registration attempt."""

    accepted: bool
    package_id: str | None
    status: IngestStatus | None
    errors: tuple[IntakeValidationIssue, ...]
    warnings: tuple[IntakeValidationIssue, ...]


def register_intake_bundle(
    bundle: dict[str, Any],
    service: IngestionService,
) -> IntakeRegistrationResult:
    """Validate and register one intake bundle with deterministic errors."""

    if not isinstance(bundle, dict):
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_bundle_structure",
                    path="$",
                    message="bundle root must be an object",
                ),
            ),
            warnings=(),
        )

    validation = validate_intake_payload(bundle)
    package_id = _as_non_empty_str(bundle.get("package_id"))
    if not package_id:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="missing_package_id",
                    path="package_id",
                    message="package_id is required",
                ),
                *validation.errors,
            ),
            warnings=validation.warnings,
        )

    if not validation.is_valid:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=package_id,
            status=None,
            errors=validation.errors,
            warnings=validation.warnings,
        )

    metadata = bundle["metadata"]
    files = [
        IntakeFile(
            file_name=_as_non_empty_str(entry.get("file_name")),
            role=_as_non_empty_str(entry.get("role")),
            source_ref=_as_non_empty_str(entry.get("source_ref")) or None,
        )
        for entry in bundle["files"]
        if isinstance(entry, dict)
    ]

    try:
        record = service.receive_package(
            package_id=package_id,
            firm_id=_stable_identifier(
                preferred=metadata.get("firm_id"),
                fallback=metadata.get("firm_name"),
                prefix="firm",
            ),
            fund_id=_stable_identifier(
                preferred=metadata.get("fund_id"),
                fallback=metadata.get("fund_name"),
                prefix="fund",
            ),
            files=files,
            at=_as_non_empty_str(metadata.get("received_at")),
        )
    except ValueError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=package_id,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="duplicate_package_id",
                    path="package_id",
                    message=str(exc),
                ),
            ),
            warnings=validation.warnings,
        )

    return IntakeRegistrationResult(
        accepted=True,
        package_id=record.package_id,
        status=record.status,
        errors=(),
        warnings=validation.warnings,
    )


def register_intake_bundle_file(
    path: Path | str,
    service: IngestionService,
) -> IntakeRegistrationResult:
    """Load, validate, and register an intake bundle from disk."""

    bundle_path = Path(path)
    try:
        raw_text = bundle_path.read_text(encoding="utf-8")
    except OSError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="bundle_read_error",
                    path=str(bundle_path),
                    message=str(exc),
                ),
            ),
            warnings=(),
        )

    try:
        parsed = json.loads(raw_text)
    except JSONDecodeError as exc:
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_json_bundle",
                    path=str(bundle_path),
                    message=(
                        f"malformed JSON at line {exc.lineno}, "
                        f"column {exc.colno}"
                    ),
                ),
            ),
            warnings=(),
        )

    if not isinstance(parsed, dict):
        return IntakeRegistrationResult(
            accepted=False,
            package_id=None,
            status=None,
            errors=(
                IntakeValidationIssue(
                    code="invalid_bundle_structure",
                    path=str(bundle_path),
                    message="bundle root must be an object",
                ),
            ),
            warnings=(),
        )

    return register_intake_bundle(parsed, service)


def _as_non_empty_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _stable_identifier(preferred: Any, fallback: Any, prefix: str) -> str:
    preferred_value = _as_non_empty_str(preferred)
    if preferred_value:
        return preferred_value

    fallback_value = _as_non_empty_str(fallback).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", fallback_value).strip("_")
    return f"{prefix}_{slug or 'unknown'}"
