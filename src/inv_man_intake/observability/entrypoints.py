"""Audited intake/extraction entry points used by operators and automation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineEntrypoint:
    """One production or manual entry point that executes intake and extraction."""

    name: str
    module: str
    function: str
    mode: str
    intake_surface: str
    extraction_surface: str


def audit_intake_extraction_entrypoints() -> tuple[PipelineEntrypoint, ...]:
    """Return the current audited entry points for intake + extraction execution."""

    return (
        PipelineEntrypoint(
            name="v1_smoke_pipeline",
            module="inv_man_intake.v1_smoke",
            function="run_v1_smoke_pipeline",
            mode="manual",
            intake_surface="register_intake_bundle_file",
            extraction_surface="ExtractionOrchestrator.run",
        ),
        PipelineEntrypoint(
            name="throughput_readiness_batch",
            module="inv_man_intake.readiness.throughput",
            function="run_readiness_check",
            mode="production",
            intake_surface="run_v1_smoke_pipeline -> register_intake_bundle_file",
            extraction_surface="run_v1_smoke_pipeline -> ExtractionOrchestrator.run",
        ),
    )
