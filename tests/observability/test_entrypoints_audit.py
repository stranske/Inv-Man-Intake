"""Tests for audited intake/extraction entry points."""

from __future__ import annotations

from importlib import import_module

from inv_man_intake.observability.entrypoints import audit_intake_extraction_entrypoints


def test_audit_lists_manual_and_production_entrypoints() -> None:
    entrypoints = audit_intake_extraction_entrypoints()

    assert [entrypoint.name for entrypoint in entrypoints] == [
        "v1_smoke_pipeline",
        "throughput_readiness_batch",
    ]
    assert {entrypoint.mode for entrypoint in entrypoints} == {"manual", "production"}


def test_audited_entrypoints_resolve_to_callables() -> None:
    for entrypoint in audit_intake_extraction_entrypoints():
        module = import_module(entrypoint.module)
        target = getattr(module, entrypoint.function)
        assert callable(target)
        assert entrypoint.verification == "verified"


def test_audit_requires_intake_and_extraction_surfaces() -> None:
    for entrypoint in audit_intake_extraction_entrypoints():
        assert entrypoint.intake_surface
        assert "intake" in entrypoint.intake_surface
        assert entrypoint.extraction_surface
        assert "extract" in entrypoint.extraction_surface.casefold()
        assert entrypoint.invocation.startswith("python ")
