"""Tests for field-level extraction evaluation."""

from __future__ import annotations

from inv_man_intake.extraction.evaluation.field_accuracy import (
    EvaluationSample,
    FieldExpectation,
    evaluate_field_accuracy,
)
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


def test_field_accuracy_harness_scores_real_sample_bytes() -> None:
    sample = EvaluationSample(
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

    report = evaluate_field_accuracy(
        provider_factory=PrimaryRegexExtractionProvider,
        samples=(sample,),
    )

    assert report.provider_name == "primary-regex"
    assert report.evaluated_fields == 4
    assert report.matched_fields == 4
    assert report.accuracy == 1.0
    assert report.missing_fields == ()
    assert report.mismatched_fields == ()
