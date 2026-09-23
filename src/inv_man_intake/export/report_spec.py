"""Emit one-pager exports with an output-substrate report specification."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inv_man_intake.packet import ManagerProfile

SCHEMA_VERSION = "output-substrate/v1"
RENDERER_PROFILE = "investment_review"
_REQUIRED_FIELDS = (
    "schema_version",
    "renderer_profile",
    "workspace_bundle_ref",
    "manifest_ref",
    "manifest_csv_exports",
)
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def build_report_spec(*, workspace_bundle_ref: str, manifest_ref: str) -> dict[str, object]:
    """Build the supported output-substrate subset for a one-pager export."""

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "renderer_profile": RENDERER_PROFILE,
        "workspace_bundle_ref": {"path": workspace_bundle_ref},
        "manifest_ref": manifest_ref,
        "manifest_csv_exports": [],
    }
    validate_report_spec(payload)
    return payload


def validate_report_spec(payload: Mapping[str, object]) -> None:
    """Validate the producer subset supported until the fleet schema is synced locally."""

    for field in _REQUIRED_FIELDS:
        if field not in payload:
            raise ValueError(f"report spec missing required field: {field}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if payload["renderer_profile"] != RENDERER_PROFILE:
        raise ValueError(f"renderer_profile must be {RENDERER_PROFILE}")

    workspace_ref = payload["workspace_bundle_ref"]
    if not isinstance(workspace_ref, Mapping):
        raise ValueError("workspace_bundle_ref must be an object")
    workspace_path = workspace_ref.get("path")
    if not isinstance(workspace_path, str) or not _is_safe_relative_posix_path(workspace_path):
        raise ValueError("workspace_bundle_ref.path must be a run-relative POSIX file path")

    manifest_ref = payload["manifest_ref"]
    if not isinstance(manifest_ref, str) or not manifest_ref.strip():
        raise ValueError("manifest_ref must be a non-empty string")

    csv_exports = payload["manifest_csv_exports"]
    if not isinstance(csv_exports, list):
        raise ValueError("manifest_csv_exports must be an array")
    if csv_exports:
        raise ValueError("manifest_csv_exports are not supported by the one-pager producer")


def export_one_pager(
    profile: ManagerProfile,
    output_dir: Path,
    *,
    workspace_bundle_ref: str,
    manifest_ref: str,
    max_graphics: int = 4,
) -> tuple[Path, Path]:
    """Compatibility wrapper for the canonical one-pager export entrypoint."""

    from inv_man_intake.export.one_pager import export_one_pager as canonical_export

    return canonical_export(
        profile,
        output_dir,
        workspace_bundle_ref=workspace_bundle_ref,
        manifest_ref=manifest_ref,
        max_graphics=max_graphics,
    )


def _is_safe_relative_posix_path(value: str) -> bool:
    if not value or not value.strip() or value != value.strip():
        return False
    if value.startswith(("/", "//")) or value.endswith("/"):
        return False
    if "\\" in value or _WINDOWS_DRIVE.match(value):
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and parts != (".",) and ".." not in parts


__all__ = [
    "build_report_spec",
    "export_one_pager",
    "validate_report_spec",
]
