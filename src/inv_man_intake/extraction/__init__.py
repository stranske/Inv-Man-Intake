"""Extraction contracts and provider implementations."""

from inv_man_intake.extraction.confidence import (
    DocumentThresholdProfile,
    ThresholdConfig,
    ThresholdDecision,
    attach_threshold_summary,
    evaluate_thresholds,
    load_threshold_config,
    select_threshold_profile,
)
from inv_man_intake.extraction.cross_check import (
    CrossCheckReport,
    FieldCrossCheck,
    FieldObservation,
    create_cross_check_queue_item,
    cross_check_extraction_results,
    cross_check_observations,
)
from inv_man_intake.extraction.doc_type import DocumentType, classify_doc_type
from inv_man_intake.extraction.orchestrator import (
    ExtractionFailedError,
    ExtractionOrchestrator,
    OrchestrationResult,
    RetryPolicy,
)
from inv_man_intake.extraction.service import (
    DefaultExtractionService,
    ExtractionService,
    ProviderTransportBackend,
    PyodideLightTransportBackend,
    StubServiceTransportBackend,
    TransportBackend,
    build_docling_service,
    build_future_localhost_service,
    build_future_remote_service,
    build_pyodide_light_service,
    ensure_extraction_service,
    extraction_service_extractor,
)

__all__ = [
    "DefaultExtractionService",
    "ExtractionFailedError",
    "ExtractionOrchestrator",
    "ExtractionService",
    "CrossCheckReport",
    "FieldCrossCheck",
    "FieldObservation",
    "OrchestrationResult",
    "ProviderTransportBackend",
    "PyodideLightTransportBackend",
    "RetryPolicy",
    "StubServiceTransportBackend",
    "TransportBackend",
    "DocumentThresholdProfile",
    "DocumentType",
    "ThresholdConfig",
    "ThresholdDecision",
    "attach_threshold_summary",
    "build_docling_service",
    "build_future_localhost_service",
    "build_future_remote_service",
    "build_pyodide_light_service",
    "classify_doc_type",
    "create_cross_check_queue_item",
    "cross_check_extraction_results",
    "cross_check_observations",
    "ensure_extraction_service",
    "evaluate_thresholds",
    "extraction_service_extractor",
    "load_threshold_config",
    "select_threshold_profile",
]
