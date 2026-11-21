"""Project intake IDs into run-contract/v1 and read historical aliases."""

from __future__ import annotations

import re
import unicodedata
from hashlib import sha256
from typing import Any

_CANONICAL_KEY = re.compile(r"[a-z0-9][a-z0-9_.:-]*")


def entity_identity_refs(firm_id: str, fund_id: str) -> tuple[str, str]:
    """Return the backplane refs for the resolved intake firm and fund IDs."""
    return (
        _entity_ref("manager", "firm", firm_id),
        _entity_ref("fund", "fund", fund_id),
    )


def _entity_ref(namespace: str, local_type: str, local_id: str) -> str:
    value = unicodedata.normalize("NFKC", local_id).casefold().strip()
    prefix = f"{namespace}:"
    if value.startswith(prefix) and _CANONICAL_KEY.fullmatch(value[len(prefix) :]):
        return value

    # Intake's generated local IDs already contain a normalized name slug.
    slug = re.sub(r"[^a-z0-9]+", "_", value.removeprefix(f"{local_type}_")).strip("_")
    if not slug:
        # Explicit intake IDs can contain only characters outside the wire alphabet.
        slug = f"id_{sha256(local_id.encode('utf-8')).hexdigest()}"
    return f"{namespace}:{slug}"


def normalize_legacy_identity_refs(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical view of the original inv-man-ingest alias pair."""
    if (
        envelope.get("schema_version") != "run-contract/v1"
        or envelope.get("repo") != "stranske/Inv-Man-Intake"
        or envelope.get("tool") != "inv-man-ingest"
    ):
        return envelope
    inputs = envelope.get("inputs")
    if not isinstance(inputs, dict):
        return envelope
    firm_id, fund_id = inputs.get("firm_id"), inputs.get("fund_id")
    if not isinstance(firm_id, str) or not isinstance(fund_id, str) or not firm_id or not fund_id:
        return envelope
    # The pair disambiguates a legacy fund prefix from a canonical fund name
    # whose slug itself starts with "fund_".
    if envelope.get("identity_refs") != [f"firm:{firm_id}", f"fund:{fund_id}"]:
        return envelope
    return {**envelope, "identity_refs": list(entity_identity_refs(firm_id, fund_id))}
