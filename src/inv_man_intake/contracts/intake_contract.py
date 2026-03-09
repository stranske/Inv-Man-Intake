"""Canonical intake payload contract and validation rules for v1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

PRIMARY_EXTENSIONS: frozenset[str] = frozenset({"pdf", "pptx"})
SECONDARY_EXTENSIONS: frozenset[str] = frozenset({"xlsx", "docx", "eml", "txt", "md"})
ALLOWED_EXTENSIONS: frozenset[str] = PRIMARY_EXTENSIONS | SECONDARY_EXTENSIONS
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "firm_name",
    "fund_name",
    "received_at",
    "source_channel",
)
ALLOWED_SOURCE_CHANNELS: frozenset[str] = frozenset(
    {
        "email",
        "portal_upload",
        "data_room",
        "internal_forward",
        "other",
    }
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?$"
)


@dataclass(frozen=True)
class IntakeValidationIssue:
    """A deterministic validation issue record for intake payloads."""

    code: str
    path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class IntakeValidationResult:
    """Validation outcome for an intake payload."""

    is_valid: bool
    errors: tuple[IntakeValidationIssue, ...]
    warnings: tuple[IntakeValidationIssue, ...]


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validate_received_at(raw_value: Any) -> tuple[bool, str]:
    """Validate received_at using strict ISO 8601 date/datetime parsing."""
    if not isinstance(raw_value, str):
        return False, "received_at must be an ISO-8601 string"

    candidate = raw_value.strip()
    if not candidate:
        return False, "received_at must not be empty"

    if ISO_DATE_RE.fullmatch(candidate):
        try:
            date.fromisoformat(candidate)
        except ValueError:
            return False, "received_at must be a valid ISO-8601 date or datetime"
        return True, ""

    if not ISO_DATETIME_RE.fullmatch(candidate):
        return False, "received_at must be a valid ISO-8601 date or datetime"

    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return False, "received_at must be a valid ISO-8601 date or datetime"

    return True, ""


def _file_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_intake_payload(payload: dict[str, Any]) -> IntakeValidationResult:
    """Validate payload against the v1 intake contract.

    Rules:
    - metadata must include REQUIRED_METADATA_FIELDS
    - metadata.source_channel must be in ALLOWED_SOURCE_CHANNELS
    - files must be a non-empty list
    - each file requires file_name and role
    - file extension must be in ALLOWED_EXTENSIONS
    - payload must include at least one primary document (.pdf/.pptx)
    """

    errors: list[IntakeValidationIssue] = []
    warnings: list[IntakeValidationIssue] = []

    if not isinstance(payload, dict):
        errors.append(
            IntakeValidationIssue(
                code="invalid_payload_type",
                path="$",
                message="payload must be an object",
            )
        )
        return IntakeValidationResult(
            is_valid=False, errors=tuple(errors), warnings=tuple(warnings)
        )

    metadata = payload.get("metadata")
    files = payload.get("files")

    if not isinstance(metadata, dict):
        errors.append(
            IntakeValidationIssue(
                code="missing_metadata",
                path="metadata",
                message="metadata must be provided as an object",
            )
        )
    else:
        for field_name in REQUIRED_METADATA_FIELDS:
            value = metadata.get(field_name)
            if not _as_str(value):
                errors.append(
                    IntakeValidationIssue(
                        code="missing_required_metadata",
                        path=f"metadata.{field_name}",
                        message=f"{field_name} is required",
                    )
                )

        source_channel = _as_str(metadata.get("source_channel"))
        if source_channel and source_channel not in ALLOWED_SOURCE_CHANNELS:
            errors.append(
                IntakeValidationIssue(
                    code="invalid_source_channel",
                    path="metadata.source_channel",
                    message=(
                        "source_channel must be one of "
                        + ", ".join(sorted(ALLOWED_SOURCE_CHANNELS))
                    ),
                )
            )

        received_ok, received_error = _validate_received_at(metadata.get("received_at"))
        if not received_ok:
            errors.append(
                IntakeValidationIssue(
                    code="invalid_received_at",
                    path="metadata.received_at",
                    message=received_error,
                )
            )

    if not isinstance(files, list) or len(files) == 0:
        errors.append(
            IntakeValidationIssue(
                code="missing_files",
                path="files",
                message="files must be a non-empty array",
            )
        )
        return IntakeValidationResult(
            is_valid=False, errors=tuple(errors), warnings=tuple(warnings)
        )

    primary_count = 0
    for index, raw_file in enumerate(files):
        path_prefix = f"files[{index}]"
        if not isinstance(raw_file, dict):
            errors.append(
                IntakeValidationIssue(
                    code="invalid_file_entry",
                    path=path_prefix,
                    message="each file entry must be an object",
                )
            )
            continue

        file_name = _as_str(raw_file.get("file_name"))
        role = _as_str(raw_file.get("role"))

        if not file_name:
            errors.append(
                IntakeValidationIssue(
                    code="missing_file_name",
                    path=f"{path_prefix}.file_name",
                    message="file_name is required",
                )
            )
            continue

        if not role:
            errors.append(
                IntakeValidationIssue(
                    code="missing_file_role",
                    path=f"{path_prefix}.role",
                    message="role is required",
                )
            )

        extension = _file_extension(file_name)
        if extension not in ALLOWED_EXTENSIONS:
            errors.append(
                IntakeValidationIssue(
                    code="unsupported_file_type",
                    path=f"{path_prefix}.file_name",
                    message=(
                        f"{file_name} has unsupported extension; allowed: "
                        + ", ".join(sorted(ALLOWED_EXTENSIONS))
                    ),
                )
            )
            continue

        if extension in PRIMARY_EXTENSIONS:
            primary_count += 1

        source_ref = _as_str(raw_file.get("source_ref"))
        if not source_ref:
            warnings.append(
                IntakeValidationIssue(
                    code="missing_source_ref",
                    path=f"{path_prefix}.source_ref",
                    message="source_ref recommended for ingestion traceability",
                    severity="warning",
                )
            )

    if primary_count == 0:
        errors.append(
            IntakeValidationIssue(
                code="missing_primary_document",
                path="files",
                message="at least one primary document (.pdf or .pptx) is required",
            )
        )

    return IntakeValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
