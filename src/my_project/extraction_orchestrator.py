"""Extraction orchestration with fallback and loop guardrails."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from inv_man_intake.observability import TraceContext, Tracer, new_trace_context

Extractor = Callable[[dict[str, Any]], dict[str, Any]]
MetricsHook = Callable[[dict[str, Any]], None]


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
    escalation_payload: dict[str, Any] | None = None


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
        metrics_hook: MetricsHook | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._primary = _Provider(name=primary_name, extractor=primary_extractor)
        self._fallback = _Provider(name=fallback_name, extractor=fallback_extractor)
        self._policy = policy or RetryPolicy()
        self._metrics_hook = metrics_hook
        self._tracer = tracer or Tracer(enabled=False)

    def run(
        self, payload: dict[str, Any], trace_context: TraceContext | None = None
    ) -> OrchestrationResult:
        attempts: list[AttemptRecord] = []
        retry_count = 0
        fallback_attempts = 0
        last_error: str | None = None
        context = trace_context or new_trace_context(tags={"pipeline_stage": "extract"})

        with self._tracer.start_run(
            name="extraction_orchestrator.run",
            context=context,
            metadata={"item_id": payload.get("id")},
        ):
            with self._tracer.start_span(
                name="extraction_orchestrator.primary_attempt",
                context=context,
                metadata={"provider": self._primary.name},
            ):
                primary_result, primary_error = self._attempt(self._primary, payload)
            attempts.append(
                AttemptRecord(
                    provider=self._primary.name,
                    success=primary_result is not None,
                    error=primary_error,
                )
            )
            if primary_result is not None:
                result = OrchestrationResult(
                    resolved=True,
                    data=primary_result,
                    provider_used=self._primary.name,
                    attempts=attempts,
                    retry_count=retry_count,
                    failure_count=0,
                )
                self._emit_metrics(result)
                return result
            last_error = primary_error

            if not self._can_attempt_fallback(
                attempts=attempts, fallback_attempts=fallback_attempts
            ):
                result = self._escalate(
                    payload=payload,
                    attempts=attempts,
                    retry_count=retry_count,
                    reason=last_error,
                )
                self._emit_metrics(result)
                return result

            with self._tracer.start_span(
                name="extraction_orchestrator.fallback_attempt",
                context=context,
                metadata={"provider": self._fallback.name},
            ):
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
                result = OrchestrationResult(
                    resolved=True,
                    data=fallback_result,
                    provider_used=self._fallback.name,
                    attempts=attempts,
                    retry_count=retry_count,
                    failure_count=1,
                )
                self._emit_metrics(result)
                return result

            last_error = fallback_error
            result = self._escalate(
                payload=payload,
                attempts=attempts,
                retry_count=retry_count,
                reason=last_error,
            )
            self._emit_metrics(result)
            return result

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
        *,
        payload: dict[str, Any],
        attempts: list[AttemptRecord],
        retry_count: int,
        reason: str | None,
    ) -> OrchestrationResult:
        escalation_reason = reason or "extraction-unresolved"
        return OrchestrationResult(
            resolved=False,
            data=None,
            provider_used=None,
            attempts=attempts,
            retry_count=retry_count,
            failure_count=len(attempts),
            escalation_reason=escalation_reason,
            escalation_payload=ExtractionOrchestrator._build_escalation_payload(
                payload=payload,
                attempts=attempts,
                retry_count=retry_count,
                escalation_reason=escalation_reason,
            ),
        )

    @staticmethod
    def _build_escalation_payload(
        *,
        payload: dict[str, Any],
        attempts: list[AttemptRecord],
        retry_count: int,
        escalation_reason: str,
    ) -> dict[str, Any]:
        failed_attempts = [attempt for attempt in attempts if not attempt.success]
        return {
            "item_id": payload.get("id"),
            "input_payload": dict(payload),
            "escalation_reason": escalation_reason,
            "retry_count": retry_count,
            "failure_count": len(failed_attempts),
            "failed_providers": [attempt.provider for attempt in failed_attempts],
            "errors": [attempt.error for attempt in failed_attempts if attempt.error],
        }

    def _emit_metrics(self, result: OrchestrationResult) -> None:
        if self._metrics_hook is None:
            return
        self._metrics_hook(
            {
                "resolved": result.resolved,
                "provider_used": result.provider_used,
                "retry_count": result.retry_count,
                "failure_count": result.failure_count,
            }
        )
