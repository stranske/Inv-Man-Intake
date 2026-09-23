"""Build deterministic ``evidence-object/v1`` records for extracted fields."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

_EVIDENCE_ID_PREFIX = "evidence:sha256:"
_EVIDENCE_FILE_PREFIX = "evidence-"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def build_evidence_objects(fields: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project extracted fields into stable, schema-ready evidence objects.

    The identifier hashes the canonical evidence payload, so repeated runs over
    identical field provenance produce byte-identical file names and contents.
    """

    objects: list[dict[str, Any]] = []
    for field in fields:
        fact_ref = _required_string(field, "key")
        location = field.get("location")
        location_map = location if isinstance(location, Mapping) else {}
        source_id = field.get("source_doc_id") or location_map.get("source_doc_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f"field {fact_ref!r} has no non-empty source document id")

        payload: dict[str, Any] = {
            "schema_version": "evidence-object/v1",
            "fact_ref": fact_ref,
            "source_id": source_id,
            "method": _evidence_method(field.get("method")),
            "excerpt": _excerpt(field.get("snippet")),
            "confidence": _confidence(field.get("confidence")),
        }
        locator = _locator(field=field, location=location_map)
        if locator:
            payload["locator"] = locator

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        evidence = {"evidence_id": f"{_EVIDENCE_ID_PREFIX}{digest}", **payload}
        objects.append(evidence)

    return sorted(objects, key=lambda item: str(item["evidence_id"]))


def evidence_object_filename(evidence: Mapping[str, Any]) -> str:
    """Return the safe deterministic file name for an evidence object."""

    evidence_id = evidence.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith(_EVIDENCE_ID_PREFIX):
        raise ValueError("evidence object has no supported content-derived evidence_id")
    digest = evidence_id.removeprefix(_EVIDENCE_ID_PREFIX)
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("evidence object evidence_id must end in a lowercase SHA-256 digest")
    return f"{_EVIDENCE_FILE_PREFIX}{digest}.json"


def _required_string(field: Mapping[str, Any], key: str) -> str:
    value = field.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"extracted field has no non-empty {key}")
    return value


def _evidence_method(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if "ocr" in normalized:
        return "ocr"
    if "llm" in normalized:
        return "llm"
    if "manual" in normalized:
        return "manual"
    if "table" in normalized:
        return "table"
    if "fallback" in normalized:
        return "fallback"
    if "computed" in normalized or "threshold" in normalized:
        return "computed"
    if "text" in normalized:
        return "text"
    if "rule" in normalized:
        return "rule"
    return "parser"


def _excerpt(value: Any) -> str | None:
    if value is None:
        return None
    excerpt = str(value)
    return excerpt[:2000]


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    confidence = float(value)
    if not 0 <= confidence <= 1:
        raise ValueError(f"evidence confidence must be in [0, 1]; got {confidence!r}")
    return confidence


def _locator(*, field: Mapping[str, Any], location: Mapping[str, Any]) -> dict[str, Any]:
    locator: dict[str, Any] = {}
    page = field.get("source_page")
    if page is None:
        page = location.get("source_page")
    if page is not None:
        locator["page"] = int(page)

    table_index = location.get("table_index")
    if table_index is not None:
        locator["table_index"] = int(table_index)

    bbox = location.get("bbox")
    if isinstance(bbox, (list, tuple)):
        locator["bbox"] = [float(value) for value in bbox]
    return locator
