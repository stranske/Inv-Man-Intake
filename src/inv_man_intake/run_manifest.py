"""Per-run artifact manifest (#474).

A run writes named artifacts (``run.json`` and friends) into an operator-supplied
output directory, but until now those artifacts were discoverable only through
advisory literal strings in the source. This module materializes a
``manifest.json`` that lists every artifact with a stable ID, a ``kind``, and a
SHA-256 hash + byte count computed from the bytes actually written to disk, so a
consumer can discover and verify a run's outputs (``artifact_discipline``).

The manifest is byte-stable across identical runs: entries are sorted by name and
serialized with ``json.dumps(..., sort_keys=True)`` (via :func:`run._write_json`),
so it can be compared against a golden reference. Like the other run artifacts it
is local to the operator-supplied output directory and is never pushed to the
fleet telemetry NDJSON sink.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from inv_man_intake.intake.versioning import compute_sha256
from inv_man_intake.observability.langsmith_fleet import _is_safe_artifact_ref

MANIFEST_NAME = "manifest.json"

# Stable, human-readable kinds for the known named run artifacts; anything else
# falls back to its file suffix so the manifest still classifies new artifacts.
_KIND_BY_NAME = {
    "run.json": "run-record",
    "metadata.json": "metadata",
    "threshold-summary.json": "threshold-summary",
    "explainability.json": "explainability",
}


def _artifact_kind(name: str) -> str:
    """Classify an artifact by its file name, defaulting to its suffix."""
    if name in _KIND_BY_NAME:
        return _KIND_BY_NAME[name]
    return Path(name).suffix.lstrip(".") or "file"


def build_manifest(
    run_id: str,
    trace_id: str | None,
    artifacts: Iterable[Path],
) -> dict[str, Any]:
    """Build a deterministic manifest dict for ``artifacts``.

    Each entry is ``{artifact_id, name, kind, path, sha256, bytes}`` where
    ``sha256`` is :func:`compute_sha256` of the file's on-disk bytes and ``bytes``
    is that file's size. Entries are sorted by name so the serialized manifest is
    byte-stable. The owning ``run_id`` and ``trace_id`` are recorded at the top
    level.

    Each artifact is referenced inside the run directory as ``artifact:<name>``;
    that reference is validated with :func:`_is_safe_artifact_ref` (and any ``..``
    traversal segment is rejected) before the file is read, mirroring the safety
    rules the fleet emitter enforces. Absolute on-disk locations are expected
    (artifacts live in an operator-supplied directory); only the in-run-dir
    reference must be a safe relative name.

    Raises:
        ValueError: An artifact would produce an unsafe ``artifact:`` reference
            (e.g. an absolute or ``..`` traversal segment in its name).
        OSError: An artifact cannot be read.
    """
    entries: list[dict[str, Any]] = []
    for artifact in sorted(artifacts, key=lambda path: path.name):
        name = artifact.name
        ref = f"artifact:{name}"
        if ".." in artifact.parts or not _is_safe_artifact_ref(ref):
            raise ValueError(
                f"artifact {str(artifact)!r} would produce an unsafe artifact reference: {ref!r}"
            )
        content = artifact.read_bytes()
        entries.append(
            {
                "artifact_id": artifact.stem,
                "name": name,
                "kind": _artifact_kind(name),
                "path": name,
                "sha256": compute_sha256(content),
                "bytes": len(content),
            }
        )
    return {
        "run_id": run_id,
        "trace_id": trace_id,
        "artifacts": entries,
    }
