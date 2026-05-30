"""Audited intake/extraction entry points used by operators and automation."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Literal


@dataclass(frozen=True)
class PipelineEntrypoint:
    """One production or manual entry point that executes intake and extraction."""

    name: str
    module: str
    function: str
    mode: str
    intake_surface: str
    extraction_surface: str
    invocation: str
    verification: Literal["verified", "missing_module", "missing_callable"]


def audit_intake_extraction_entrypoints() -> tuple[PipelineEntrypoint, ...]:
    """Return the current audited entry points for intake + extraction execution."""

    return tuple(
        _build_entrypoint(
            name=name,
            module=module,
            function=function,
            mode=mode,
            intake_surface=intake_surface,
            extraction_surface=extraction_surface,
            invocation=invocation,
        )
        for name, module, function, mode, intake_surface, extraction_surface, invocation in (
            (
                "v1_smoke_pipeline",
                "inv_man_intake.v1_smoke",
                "run_v1_smoke_pipeline",
                "manual",
                "register_intake_bundle_file",
                "ExtractionOrchestrator.run",
                "python -c 'from inv_man_intake.v1_smoke import run_v1_smoke_pipeline'",
            ),
            (
                "throughput_readiness_batch",
                "inv_man_intake.readiness.throughput",
                "run_readiness_check",
                "production",
                "run_v1_smoke_pipeline -> register_intake_bundle_file",
                "run_v1_smoke_pipeline -> ExtractionOrchestrator.run",
                "python -m inv_man_intake.readiness.throughput",
            ),
            (
                "ingest_cli",
                "inv_man_intake.cli.ingest",
                "main",
                "production",
                "run_pipeline -> register_intake_bundle_file",
                "run_pipeline -> ExtractionOrchestrator.run",
                "python -m inv_man_intake.cli.ingest <bundle> --out <output_dir>",
            ),
        )
    )


def _build_entrypoint(
    *,
    name: str,
    module: str,
    function: str,
    mode: str,
    intake_surface: str,
    extraction_surface: str,
    invocation: str,
) -> PipelineEntrypoint:
    verification = _resolve_verification(module=module, function=function)
    return PipelineEntrypoint(
        name=name,
        module=module,
        function=function,
        mode=mode,
        intake_surface=intake_surface,
        extraction_surface=extraction_surface,
        invocation=invocation,
        verification=verification,
    )


def _resolve_verification(
    *, module: str, function: str
) -> Literal["verified", "missing_module", "missing_callable"]:
    try:
        imported = import_module(module)
    except ModuleNotFoundError:
        return "missing_module"
    return "verified" if callable(getattr(imported, function, None)) else "missing_callable"
