"""Repo-owned evidence resolution layered on the fleet run-contract validator.

The shared ``scripts.validate_run_contract`` file is managed by Workflows. Keep
this producer-specific file-to-reference check outside that sync surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from scripts.validate_run_contract import Report
from scripts.validate_run_contract import main as validate_shared_run_contract
from scripts.validate_run_contract import validate_envelope as validate_shared_envelope


def _load_emitted_evidence(
    *, run_dir: Path, manifest: dict[str, Any] | None
) -> list[dict[str, Any]] | None:
    """Load safe manifest entries dedicated to emitted evidence objects."""
    if manifest is None:
        return None
    documents: list[dict[str, Any]] = []
    for entry in manifest.get("artifacts", []):
        name = entry.get("name")
        relative = entry.get("path")
        if not (isinstance(name, str) and name.startswith("evidence-") and name.endswith(".json")):
            continue
        if not isinstance(relative, str):
            raise ValueError(f"evidence artifact {name!r} has no string path")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"evidence artifact {name!r} has an unsafe path")
        document = json.loads((run_dir / relative_path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"evidence artifact {name!r} is not a JSON object")
        documents.append(document)
    return documents


def validate_envelope(
    *,
    envelope: dict[str, Any],
    schema_dir: Path,
    registry: dict[str, Any],
    repo: str,
    manifest: dict[str, Any] | None,
    evidence_objects: list[dict[str, Any]] | None = None,
) -> Report:
    """Apply shared validation, then Inv-Man's emitted evidence closure rule."""
    report = validate_shared_envelope(
        envelope=envelope,
        schema_dir=schema_dir,
        registry=registry,
        repo=repo,
        manifest=manifest,
    )
    if report.skipped or evidence_objects is None:
        return report

    schema = json.loads((schema_dir / "evidence-object-v1.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, evidence in enumerate(evidence_objects):
        for err in sorted(
            validator.iter_errors(evidence), key=lambda item: list(item.absolute_path)
        ):
            path = "/".join(str(part) for part in err.absolute_path)
            report.fail(f"evidence object: {err.message}", f"evidence[{index}]/{path}")
        evidence_id = evidence.get("evidence_id")
        if isinstance(evidence_id, str):
            if evidence_id in evidence_by_id:
                report.fail(f"duplicate emitted evidence_id '{evidence_id}'", "evidence_refs")
            evidence_by_id[evidence_id] = evidence

    refs = envelope.get("evidence_refs", []) or []
    for ref in refs:
        if isinstance(ref, str) and ref not in evidence_by_id:
            report.fail(
                f"evidence_ref '{ref}' has no emitted evidence-object/v1 file", "evidence_refs"
            )
    referenced = {ref for ref in refs if isinstance(ref, str)}
    for evidence_id in evidence_by_id:
        if evidence_id not in referenced:
            report.fail(
                f"emitted evidence_id '{evidence_id}' is not referenced by the run envelope",
                "evidence_refs",
            )
    return report


def main(argv: list[str] | None = None) -> int:
    """Run local evidence closure before the authoritative shared validator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_json", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--schema-dir", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    try:
        envelope = json.loads(args.run_json.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        evidence_objects = _load_emitted_evidence(run_dir=args.run_json.parent, manifest=manifest)
        report = validate_envelope(
            envelope=envelope,
            schema_dir=args.schema_dir,
            registry=registry,
            repo=args.repo,
            manifest=manifest,
            evidence_objects=evidence_objects,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: cannot load emitted evidence objects: {exc}", file=sys.stderr)
        return 2
    if not report.conformant:
        for violation in report.violations:
            print(f"[{violation.path}] {violation.message}", file=sys.stderr)
        return 1
    return validate_shared_run_contract(argv)


if __name__ == "__main__":
    raise SystemExit(main())
