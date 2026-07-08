"""Extraction orchestration with fallback and loop guardrails."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from inv_man_intake.extraction.cross_check import (
    CrossCheckReport,
    create_cross_check_queue_item,
    cross_check_extraction_results,
)
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult
from inv_man_intake.observability import TraceContext, Tracer, new_trace_context
from inv_man_intake.workflow_validation import ValidationQueueItem

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
    correlation_id: str | None = None
    escalation_route: str | None = None
    escalation_reason: str | None = None
    escalation_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class _Provider:
    name: str
    extractor: Extractor


class ExtractionOrchestrator:
    """Run primary extraction with bounded fallback retries under guardrails."""

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
        self._tracer = tracer or Tracer.from_env()

    def run(
        self, payload: dict[str, Any], trace_context: TraceContext | None = None
    ) -> OrchestrationResult:
        attempts: list[AttemptRecord] = []
        retry_count = 0
        fallback_attempts = 0
        last_error: str | None = None
        context = trace_context or new_trace_context(tags={"pipeline_stage": "extract"})
        correlation_id = self._resolve_correlation_id(payload=payload, context=context)

        with self._tracer.start_run(
            name="extraction_orchestrator.run",
            context=context,
            metadata={"item_id": payload.get("id"), "correlation_id": correlation_id},
        ):
            with self._tracer.start_span(
                name="extraction_orchestrator.primary_attempt",
                context=context,
                metadata={"provider": self._primary.name, "correlation_id": correlation_id},
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
                result = self._with_cross_check(
                    OrchestrationResult(
                        resolved=True,
                        data=primary_result,
                        provider_used=self._primary.name,
                        attempts=attempts,
                        retry_count=retry_count,
                        failure_count=0,
                        correlation_id=correlation_id,
                    ),
                    payload=payload,
                    provider_result=primary_result,
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
                    correlation_id=correlation_id,
                )
                self._emit_metrics(result)
                return result

            while self._can_attempt_fallback(
                attempts=attempts, fallback_attempts=fallback_attempts
            ):
                with self._tracer.start_span(
                    name="extraction_orchestrator.fallback_attempt",
                    context=context,
                    metadata={"provider": self._fallback.name, "correlation_id": correlation_id},
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
                    failed_attempts = [attempt for attempt in attempts if not attempt.success]
                    result = self._with_cross_check(
                        OrchestrationResult(
                            resolved=True,
                            data=fallback_result,
                            provider_used=self._fallback.name,
                            attempts=attempts,
                            retry_count=retry_count,
                            failure_count=len(failed_attempts),
                            correlation_id=correlation_id,
                        ),
                        payload=payload,
                        provider_result=fallback_result,
                    )
                    self._emit_metrics(result)
                    return result
                last_error = fallback_error

            result = self._escalate(
                payload=payload,
                attempts=attempts,
                retry_count=retry_count,
                reason=last_error,
                correlation_id=correlation_id,
            )
            self._emit_metrics(result)
            return result

    def _can_attempt_fallback(
        self, *, attempts: list[AttemptRecord], fallback_attempts: int
    ) -> bool:
        # Guardrail: if providers are identical, fallback would repeat the same path.
        if self._primary.name == self._fallback.name:
            return False
        if fallback_attempts >= self._policy.max_fallback_attempts:
            return False
        return len(attempts) < self._policy.max_total_attempts

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
        correlation_id: str | None,
    ) -> OrchestrationResult:
        escalation_reason = reason or "extraction-unresolved"
        escalation_route = ExtractionOrchestrator._resolve_escalation_route(attempts=attempts)
        return OrchestrationResult(
            resolved=False,
            data=None,
            provider_used=None,
            attempts=attempts,
            retry_count=retry_count,
            failure_count=len(attempts),
            correlation_id=correlation_id,
            escalation_route=escalation_route,
            escalation_reason=escalation_reason,
            escalation_payload=ExtractionOrchestrator._build_escalation_payload(
                payload=payload,
                attempts=attempts,
                retry_count=retry_count,
                escalation_route=escalation_route,
                escalation_reason=escalation_reason,
                correlation_id=correlation_id,
            ),
        )

    @staticmethod
    def _build_escalation_payload(
        *,
        payload: dict[str, Any],
        attempts: list[AttemptRecord],
        retry_count: int,
        escalation_route: str,
        escalation_reason: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        failed_attempts = [attempt for attempt in attempts if not attempt.success]
        return {
            "item_id": payload.get("id"),
            "input_payload": dict(payload),
            "escalation_route": escalation_route,
            "escalation_reason": escalation_reason,
            "retry_count": retry_count,
            "failure_count": len(failed_attempts),
            "correlation_id": correlation_id,
            "failed_providers": [attempt.provider for attempt in failed_attempts],
            "errors": [attempt.error for attempt in failed_attempts if attempt.error],
        }

    @staticmethod
    def _resolve_correlation_id(*, payload: dict[str, Any], context: TraceContext) -> str | None:
        from_payload = payload.get("correlation_id")
        if isinstance(from_payload, str) and from_payload.strip():
            return from_payload.strip()
        from_tags = context.tags.get("correlation_id")
        if isinstance(from_tags, str) and from_tags.strip():
            return from_tags.strip()
        return None

    @staticmethod
    def _resolve_escalation_route(*, attempts: list[AttemptRecord]) -> str:
        failed_provider_count = len(
            {attempt.provider for attempt in attempts if not attempt.success}
        )
        if failed_provider_count > 1:
            return "ops_review"
        return "pending_triage"

    @staticmethod
    def _with_cross_check(
        result: OrchestrationResult,
        *,
        payload: dict[str, Any],
        provider_result: dict[str, Any],
    ) -> OrchestrationResult:
        extraction_results = _extract_document_results(provider_result)
        if len(extraction_results) < 2:
            return result

        report = cross_check_extraction_results(
            extraction_results,
            disable_discrepancy_check=bool(payload.get("disable_cross_check_discrepancy")),
        )
        queue_item = create_cross_check_queue_item(
            package_id=_resolve_cross_check_package_id(payload=payload, result=provider_result),
            report=report,
        )
        data = dict(provider_result)
        data["cross_check_report"] = report
        data["cross_check_queue_item"] = queue_item
        if queue_item is None:
            return OrchestrationResult(
                resolved=result.resolved,
                data=data,
                provider_used=result.provider_used,
                attempts=result.attempts,
                retry_count=result.retry_count,
                failure_count=result.failure_count,
                correlation_id=result.correlation_id,
            )

        escalation_payload = _cross_check_escalation_payload(
            payload=payload,
            report=report,
            queue_item=queue_item,
            correlation_id=result.correlation_id,
        )
        return OrchestrationResult(
            resolved=result.resolved,
            data=data,
            provider_used=result.provider_used,
            attempts=result.attempts,
            retry_count=result.retry_count,
            failure_count=result.failure_count,
            correlation_id=result.correlation_id,
            escalation_route="pending_triage",
            escalation_reason=queue_item.escalation_reason,
            escalation_payload=escalation_payload,
        )

    def _emit_metrics(self, result: OrchestrationResult) -> None:
        if self._metrics_hook is None:
            return
        self._metrics_hook(
            {
                "resolved": result.resolved,
                "provider_used": result.provider_used,
                "retry_count": result.retry_count,
                "failure_count": result.failure_count,
                "correlation_id": result.correlation_id,
            }
        )


def _extract_document_results(
    provider_result: dict[str, Any],
) -> tuple[ExtractedDocumentResult, ...]:
    candidates = (
        provider_result.get("extraction_results"),
        provider_result.get("results"),
        provider_result.get("documents"),
    )
    for candidate in candidates:
        results = _coerce_document_results(candidate)
        if results:
            return results
    return _coerce_document_results(provider_result.get("result"))


def _coerce_document_results(candidate: object) -> tuple[ExtractedDocumentResult, ...]:
    if isinstance(candidate, ExtractedDocumentResult):
        return (candidate,)
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
        return tuple(item for item in candidate if isinstance(item, ExtractedDocumentResult))
    return ()


def _resolve_cross_check_package_id(*, payload: dict[str, Any], result: dict[str, Any]) -> str:
    for key in ("package_id", "id", "item_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("package_id", "id", "item_id"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown-package"


def _cross_check_escalation_payload(
    *,
    payload: dict[str, Any],
    report: CrossCheckReport,
    queue_item: ValidationQueueItem,
    correlation_id: str | None,
) -> dict[str, Any]:
    return {
        "item_id": payload.get("id"),
        "input_payload": dict(payload),
        "escalation_route": "pending_triage",
        "escalation_reason": queue_item.escalation_reason,
        "retry_count": 0,
        "failure_count": 0,
        "correlation_id": correlation_id,
        "queue_item_id": queue_item.item_id,
        "package_id": queue_item.package_id,
        "cross_check_reasons": list(report.escalation_reasons),
    }
