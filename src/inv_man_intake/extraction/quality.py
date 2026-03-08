"""Extraction QA corpus evaluation and baseline metrics generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


@dataclass(frozen=True)
class CorpusFixture:
    """One extraction QA fixture with expected canonical field values."""

    document_id: str
    scenario: str
    content: str
    expected_fields: dict[str, str]


def load_corpus(path: Path) -> tuple[CorpusFixture, ...]:
    """Load extraction QA fixtures from a JSON corpus file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures: list[CorpusFixture] = []
    for item in payload["fixtures"]:
        fixtures.append(
            CorpusFixture(
                document_id=item["document_id"],
                scenario=item["scenario"],
                content=item["content"],
                expected_fields=dict(item["expected_fields"]),
            )
        )
    return tuple(fixtures)


def generate_quality_report(
    corpus_path: Path,
) -> dict[str, object]:
    """Evaluate baseline extraction quality against fixture expectations."""

    provider = PrimaryRegexExtractionProvider()
    fixtures = load_corpus(corpus_path)

    fixture_reports: list[dict[str, object]] = []
    total_expected = 0
    total_correct = 0
    total_extracted_expected_keys = 0
    total_extracted_correct = 0
    parser_failures = 0
    fallback_uses = 0

    for fixture in fixtures:
        try:
            result = provider.extract(
                source_doc_id=fixture.document_id,
                content=fixture.content.encode("utf-8"),
            )
        except Exception:  # noqa: BLE001
            parser_failures += 1
            fixture_reports.append(
                {
                    "document_id": fixture.document_id,
                    "scenario": fixture.scenario,
                    "error": "provider-exception",
                    "expected_count": len(fixture.expected_fields),
                    "matched_count": 0,
                    "missing_keys": sorted(fixture.expected_fields.keys()),
                    "incorrect_values": [],
                }
            )
            continue

        if result.provider_name != provider.name:
            fallback_uses += 1

        extracted_by_key = {field.key: field.value for field in result.fields}

        missing_keys: list[str] = []
        incorrect_values: list[dict[str, str]] = []
        matched_count = 0

        for key, expected_value in fixture.expected_fields.items():
            total_expected += 1
            actual_value = extracted_by_key.get(key)
            if actual_value is None:
                missing_keys.append(key)
                continue

            total_extracted_expected_keys += 1
            if actual_value == expected_value:
                matched_count += 1
                total_correct += 1
                total_extracted_correct += 1
            else:
                incorrect_values.append(
                    {
                        "key": key,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )

        fixture_reports.append(
            {
                "document_id": fixture.document_id,
                "scenario": fixture.scenario,
                "provider": result.provider_name,
                "expected_count": len(fixture.expected_fields),
                "matched_count": matched_count,
                "missing_keys": missing_keys,
                "incorrect_values": incorrect_values,
            }
        )

    completeness = (total_correct / total_expected) if total_expected else 0.0
    accuracy = (
        total_extracted_correct / total_extracted_expected_keys
        if total_extracted_expected_keys
        else 0.0
    )

    return {
        "fixture_count": len(fixtures),
        "summary": {
            "accuracy": round(accuracy, 4),
            "completeness": round(completeness, 4),
            "parser_failure_count": parser_failures,
            "fallback_usage_count": fallback_uses,
            "total_expected_fields": total_expected,
            "total_correct_fields": total_correct,
        },
        "fixtures": fixture_reports,
    }
