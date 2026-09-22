"""End-to-end v1 smoke coverage for the PPTX-primary intake bundle."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from inv_man_intake import v1_smoke
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult
from inv_man_intake.observability import InMemoryTraceSink, Tracer, new_trace_context
from inv_man_intake.v1_smoke import run_v1_smoke_pipeline


def test_pptx_primary_bundle_reaches_scoring_without_escalation() -> None:
    artifacts = run_v1_smoke_pipeline(
        fixture_root=Path("tests/fixtures/intake"),
        intake_bundle_file="pptx_primary_mixed_bundle.json",
        package_id="pkg_pptx_mixed_001",
        expected_document_ids=(
            "pkg_pptx_mixed_001:doc:0",
            "pkg_pptx_mixed_001:doc:1",
            "pkg_pptx_mixed_001:doc:2",
        ),
    )

    assert artifacts.extraction_with_thresholds.provider_name == "pptx-primary"
    assert artifacts.score.final_score is not None
    assert artifacts.threshold_decision.escalate is False


@pytest.mark.parametrize(
    ("file_name", "expected_factory"),
    [("fixture.PDF", "legacy-pdf"), ("fixture.pptx", "pyodide-light")],
)
def test_extraction_smoke_selects_factory_for_file_type(
    monkeypatch: pytest.MonkeyPatch, file_name: str, expected_factory: str
) -> None:
    called: list[str] = []

    def legacy_factory() -> SimpleNamespace:
        called.append("legacy-pdf")
        return SimpleNamespace(backend_name="legacy-pdf")

    def pyodide_factory(name: str) -> SimpleNamespace:
        assert name == file_name
        called.append("pyodide-light")
        return SimpleNamespace(backend_name="pyodide-light")

    result = ExtractedDocumentResult(source_doc_id="doc-1", provider_name="test")

    class FakeOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            self.provider_name = kwargs["primary_name"]

        def run(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                resolved=True,
                provider_used=self.provider_name,
                data={"result": result},
            )

    monkeypatch.setattr(v1_smoke, "build_legacy_pdf_fixture_service", legacy_factory)
    monkeypatch.setattr(v1_smoke, "build_pyodide_light_service", pyodide_factory)
    monkeypatch.setattr(v1_smoke, "extraction_service_extractor", lambda _service: lambda _: None)
    monkeypatch.setattr(v1_smoke, "ExtractionOrchestrator", FakeOrchestrator)

    extracted = v1_smoke._run_extraction_smoke(
        tracer=Tracer(enabled=False, sink=InMemoryTraceSink()),
        trace_context=new_trace_context(),
        source_doc_id="doc-1",
        primary_file_name=file_name,
        content=b"fixture",
        correlation_id="corr-1",
    )

    assert called == [expected_factory]
    assert extracted is result
