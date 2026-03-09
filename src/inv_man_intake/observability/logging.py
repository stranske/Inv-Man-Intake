"""Structured logging helpers with correlation-id propagation."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

CORRELATION_ID_KEY = "x-correlation-id"


@dataclass(frozen=True)
class LogContext:
    """Structured log context that travels across pipeline stages."""

    correlation_id: str
    stage: str
    status: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        normalized_status = self.status.strip().lower()
        if normalized_status != "success" and (
            self.error_code is None or self.error_code.strip() == ""
        ):
            raise ValueError("error_code is required when status is not 'success'")


def new_correlation_id() -> str:
    """Generate a stable-format correlation id."""

    return f"corr_{uuid4().hex}"


def inject_correlation_id(
    correlation_id: str, carrier: MutableMapping[str, str] | None = None
) -> dict[str, str]:
    """Inject correlation id into a string carrier."""

    target: MutableMapping[str, str] = {} if carrier is None else carrier
    target[CORRELATION_ID_KEY] = correlation_id
    return dict(target)


def extract_correlation_id(carrier: Mapping[str, str]) -> str | None:
    """Extract correlation id from a string carrier."""

    value = carrier.get(CORRELATION_ID_KEY)
    if value is None or value.strip() == "":
        return None
    return value


def ensure_correlation_id(carrier: Mapping[str, str] | None = None) -> str:
    """Reuse carrier correlation id when present, otherwise generate a new one."""

    if carrier is None:
        return new_correlation_id()
    extracted = extract_correlation_id(carrier)
    if extracted is not None:
        return extracted
    return new_correlation_id()


def build_log_record(
    *,
    context: LogContext,
    message: str,
    level: str = "INFO",
    fields: Mapping[str, str | int | float] | None = None,
) -> dict[str, str | int | float | None]:
    """Build canonical structured log fields for pipeline observability."""

    record: dict[str, str | int | float | None] = {}
    if fields is not None:
        record.update(fields)

    record.update(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "message": message,
            "correlation_id": context.correlation_id,
            "stage": context.stage,
            "status": context.status,
            "error_code": context.error_code,
        }
    )
    return record
