"""Tests for field-level extraction evaluation."""

from __future__ import annotations

from inv_man_intake.extraction.evaluation.field_accuracy import (
    EvaluationSample,
    FieldExpectation,
    evaluate_field_accuracy,
)
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


def test_field_accuracy_harness_scores_real_sample_bytes() -> None:
    matched_sample = EvaluationSample(
        source_doc_id="real-sample.txt",
        content=(
            b"Strategy: Summit Arc Credit\n"
            b"Management fee: 1.25%\n"
            b"Performance fee: 10%\n"
            b"Benchmark: S&P 500\n"
        ),
        expected_fields=(
            FieldExpectation(key="strategy.name", value="Summit Arc Credit"),
            FieldExpectation(key="terms.management_fee", value="1.25%"),
            FieldExpectation(key="terms.performance_fee", value="10%"),
            FieldExpectation(key="benchmark.name", value="S&P 500"),
        ),
    )
    missing_sample = EvaluationSample(
        source_doc_id="missing-sample.txt",
        content=b"Strategy: Summit Arc Credit\n",
        expected_fields=(
            FieldExpectation(key="strategy.name", value="Summit Arc Credit"),
            FieldExpectation(key="terms.management_fee", value="1.25%"),
        ),
    )
    mismatched_sample = EvaluationSample(
        source_doc_id="mismatched-sample.txt",
        content=b"Management fee: 1.50%\n",
        expected_fields=(FieldExpectation(key="terms.management_fee", value="1.25%"),),
    )

    report = evaluate_field_accuracy(
        provider_factory=PrimaryRegexExtractionProvider,
        samples=(matched_sample, missing_sample, mismatched_sample),
    )

    assert report.provider_name == "primary-regex"
    assert report.evaluated_fields == 7
    assert report.matched_fields == 5
    assert report.accuracy == 5 / 7
    assert report.missing_fields == ("missing-sample.txt:terms.management_fee",)
    assert report.mismatched_fields == ("mismatched-sample.txt:terms.management_fee",)
