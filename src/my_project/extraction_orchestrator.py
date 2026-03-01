"""Extraction orchestration with fallback and loop guardrails."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Extractor = Callable[[dict[str, Any]], dict[str, Any]]


class ExtractionFailedError(RuntimeError):
    """Raised when an extractor cannot resolve a payload."""


@dataclass(frozen=True)
class RetryPolicy:
    """Retry limits for orchestration."""

    max_total_attempts: int = 2
    max_fallback_attempts: int = 1


@dataclass(frozen=True)
class AttemptRecord:
    """A single extractor attempt."""

    provider: str
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class OrchestrationResult:
    """Result envelope for extraction orchestration."""

    resolved: bool
    data: dict[str, Any] | None
    provider_used: str | None
    attempts: list[AttemptRecord]
    retry_count: int
    failure_count: int
    escalation_reason: str | None = None


@dataclass(frozen=True)
class _Provider:
    name: str
    extractor: Extractor


class ExtractionOrchestrator:
    """Run primary extraction with one fallback retry under guardrails."""

    def __init__(
        self,
        *,
        primary_name: str,
        primary_extractor: Extractor,
        fallback_name: str,
        fallback_extractor: Extractor,
        policy: RetryPolicy | None = None,
    ) -> None:
        self._primary = _Provider(name=primary_name, extractor=primary_extractor)
        self._fallback = _Provider(name=fallback_name, extractor=fallback_extractor)
        self._policy = policy or RetryPolicy()

    def run(self, payload: dict[str, Any]) -> OrchestrationResult:
        attempts: list[AttemptRecord] = []
        retry_count = 0
        fallback_attempts = 0
        last_error: str | None = None

        primary_result, primary_error = self._attempt(self._primary, payload)
        attempts.append(
            AttemptRecord(
                provider=self._primary.name, success=primary_result is not None, error=primary_error
            )
        )
        if primary_result is not None:
            return OrchestrationResult(
                resolved=True,
                data=primary_result,
                provider_used=self._primary.name,
                attempts=attempts,
                retry_count=retry_count,
                failure_count=0,
            )
        last_error = primary_error

        if not self._can_attempt_fallback(attempts=attempts, fallback_attempts=fallback_attempts):
            return self._escalate(attempts=attempts, retry_count=retry_count, reason=last_error)

        fallback_result, fallback_error = self._attempt(self._fallback, payload)
        fallback_attempts += 1
        retry_count += 1
        attempts.append(
            AttemptRecord(
                provider=self._fallback.name,
                success=fallback_result is not None,
                error=fallback_error,
            )
        )
        if fallback_result is not None:
            return OrchestrationResult(
                resolved=True,
                data=fallback_result,
                provider_used=self._fallback.name,
                attempts=attempts,
                retry_count=retry_count,
                failure_count=1,
            )

        last_error = fallback_error
        return self._escalate(attempts=attempts, retry_count=retry_count, reason=last_error)

    def _can_attempt_fallback(
        self, *, attempts: list[AttemptRecord], fallback_attempts: int
    ) -> bool:
        if fallback_attempts >= self._policy.max_fallback_attempts:
            return False
        if len(attempts) >= self._policy.max_total_attempts:
            return False

        # Guardrail: prevent retrying the same provider in a fallback slot.
        previous_provider = attempts[-1].provider if attempts else None
        return previous_provider != self._fallback.name

    @staticmethod
    def _attempt(
        provider: _Provider, payload: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            return provider.extractor(payload), None
        except Exception as exc:  # noqa: BLE001
            return None, f"{provider.name}: {exc}"

    @staticmethod
    def _escalate(
        *, attempts: list[AttemptRecord], retry_count: int, reason: str | None
    ) -> OrchestrationResult:
        return OrchestrationResult(
            resolved=False,
            data=None,
            provider_used=None,
            attempts=attempts,
            retry_count=retry_count,
            failure_count=len(attempts),
            escalation_reason=reason or "extraction-unresolved",
        )
