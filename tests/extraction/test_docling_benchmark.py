"""Tests for the Docling field-accuracy benchmark harness."""

from __future__ import annotations

from pathlib import Path

from eval.benchmarks.docling_field_accuracy import (
    BenchmarkSample,
    format_report,
    load_samples,
    run_benchmark,
    select_rotating_sample,
)

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    ExtractionProvider,
    SourceLocation,
)


class _ExpectedValueProvider:
    """Provider test double that emits benchmark expectations for each source id."""

    def __init__(self, samples: tuple[BenchmarkSample, ...]) -> None:
        self._fields_by_source = {sample.sample_id: sample.expected_fields for sample in samples}

    @property
    def name(self) -> str:
        return "expected-value-provider"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        assert content
        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            fields=tuple(
                ExtractedField(
                    key=field.key,
                    value=field.value,
                    confidence=1.0,
                    source_doc_id=source_doc_id,
                    source_page=1,
                    method=self.name,
                    location=SourceLocation(source_doc_id=source_doc_id, source_page=1),
                )
                for field in self._fields_by_source[source_doc_id]
            ),
        )


def test_docling_benchmark_loads_four_rotating_samples() -> None:
    samples = load_samples(repo_root=Path(__file__).resolve().parents[2])

    assert [sample.sample_id for sample in samples] == [
        "summit-arc-investment-update-pdf",
        "harborline-strategy-review-pptx",
        "alpha-capital-manager-package-txt",
        "qa-dense-table-manager-report-txt",
    ]
    assert all(sample.source_path.exists() for sample in samples)

    rotated = [select_rotating_sample(samples, sample_index=index).sample_id for index in range(6)]

    assert rotated == [
        "summit-arc-investment-update-pdf",
        "harborline-strategy-review-pptx",
        "alpha-capital-manager-package-txt",
        "qa-dense-table-manager-report-txt",
        "summit-arc-investment-update-pdf",
        "harborline-strategy-review-pptx",
    ]


def test_docling_benchmark_reports_field_accuracy_metric() -> None:
    samples = load_samples(repo_root=Path(__file__).resolve().parents[2])
    provider: ExtractionProvider = _ExpectedValueProvider(samples)

    report = run_benchmark(provider=provider, samples=samples)

    assert report.provider_name == "expected-value-provider"
    assert report.evaluated_fields == 19
    assert report.matched_fields == 19
    assert format_report(report) == "field_accuracy: 1.00"
