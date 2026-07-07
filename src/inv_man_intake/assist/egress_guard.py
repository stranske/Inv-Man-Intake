"""Redaction and audit boundary for approved LLM-lane egress."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]
type LlmClient = Callable[[dict[str, JsonValue], "ProviderConfig"], Mapping[str, Any]]

_SENSITIVE_KEYS = {
    "document_text",
    "full_text",
    "raw_document",
    "raw_text",
    "source_text",
}
_PROPRIETARY_PATTERNS = (
    re.compile(r"\bPROPRIETARY[:\-_ ][A-Za-z0-9_.:/-]+", re.IGNORECASE),
    re.compile(r"\bCONFIDENTIAL[:\-_ ][A-Za-z0-9_.:/-]+", re.IGNORECASE),
)
_REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class EgressConsent:
    """Per-call human authorization for LLM-lane egress."""

    granted_by: str
    purpose: str
    granted_at: str


@dataclass(frozen=True)
class ProviderConfig:
    """Provider policy required before any payload may leave the local process."""

    provider: str
    model: str
    zero_retention: bool
    baa_eligible: bool


@dataclass(frozen=True)
class EgressLogRecord:
    """Append-only audit entry for one guarded outbound request."""

    timestamp: str
    provider: str
    model: str
    consent_granted_by: str
    purpose: str
    redaction_applied: bool
    outbound_payload: dict[str, JsonValue]


@dataclass(frozen=True)
class EgressResponse:
    """Guarded LLM-lane response plus the audit record that was written."""

    provider_response: dict[str, Any]
    outbound_payload: dict[str, JsonValue]
    log_record: EgressLogRecord


def send_to_llm(
    payload: Mapping[str, Any],
    *,
    consent: EgressConsent | None,
    provider_config: ProviderConfig,
    log_path: Path,
    client: LlmClient,
    now: Callable[[], datetime] | None = None,
) -> EgressResponse:
    """Redact, require consent/provider policy, call an injected client, and log.

    The guard accepts only an injected ``client`` callable so production wiring has
    to cross this boundary explicitly. Tests can assert the exact outbound payload
    without any network dependency.
    """

    if consent is None:
        raise PermissionError("LLM egress requires per-call operator consent")
    if not consent.granted_by.strip() or not consent.purpose.strip():
        raise ValueError("LLM egress consent must include actor and purpose")
    if not provider_config.zero_retention or not provider_config.baa_eligible:
        raise ValueError("LLM egress provider must be zero-retention and BAA eligible")

    outbound_payload = redact_payload(payload)
    response = dict(client(outbound_payload, provider_config))
    timestamp = (now or _utc_now)().astimezone(UTC).isoformat()
    log_record = EgressLogRecord(
        timestamp=timestamp,
        provider=provider_config.provider,
        model=provider_config.model,
        consent_granted_by=consent.granted_by,
        purpose=consent.purpose,
        redaction_applied=outbound_payload != _json_payload(payload),
        outbound_payload=outbound_payload,
    )
    _append_log_record(log_path, log_record)
    return EgressResponse(
        provider_response=response,
        outbound_payload=outbound_payload,
        log_record=log_record,
    )


def redact_payload(payload: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Return the minimal redacted JSON payload permitted for LLM egress."""

    return {
        str(key): _redact_value(key=str(key), value=value)
        for key, value in payload.items()
        if not str(key).startswith("_")
    }


def _redact_value(*, key: str, value: Any) -> JsonValue:
    normalized_key = key.lower()
    if normalized_key in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_value(key=str(child_key), value=child_value)
            for child_key, child_value in value.items()
            if not str(child_key).startswith("_")
        }
    if isinstance(value, str):
        redacted = value
        for pattern in _PROPRIETARY_PATTERNS:
            redacted = pattern.sub(_REDACTED, redacted)
        return redacted
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [_redact_value(key=key, value=item) for item in value]
    if isinstance(value, bool | int | float) or value is None:
        return cast(JsonValue, value)
    return str(value)


def _json_payload(payload: Mapping[str, Any]) -> dict[str, JsonValue]:
    return {
        str(key): _json_value(value)
        for key, value in payload.items()
        if not str(key).startswith("_")
    }


def _json_value(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [_json_value(item) for item in value]
    if isinstance(value, str | bool | int | float) or value is None:
        return cast(JsonValue, value)
    return str(value)


def _append_log_record(log_path: Path, record: EgressLogRecord) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
