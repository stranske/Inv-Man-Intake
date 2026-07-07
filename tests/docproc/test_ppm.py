from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import inv_man_intake.docproc.ppm
from inv_man_intake.assist.egress_guard import EgressConsent, ProviderConfig
from inv_man_intake.docproc.ppm import evaluate_ppm
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import load_standard_element_library


def test_coverage_checklist_and_deviation_flagging(tmp_path: Path) -> None:
    outbound_calls: list[dict[str, Any]] = []

    def fake_client(payload: dict[str, Any], provider_config: ProviderConfig) -> Mapping[str, Any]:
        outbound_calls.append(payload)
        deviation = payload["deviations"][0]
        assert deviation["source_text"] == "[REDACTED]"
        return {
            "notes": [
                {
                    "element_key": "ppm.deviation.liquidity_gate",
                    "summary": "Quarterly gate differs from the standard subscription terms.",
                    "why_it_matters": "Operator should review liquidity constraints before approval.",
                    "citation": deviation["citation"],
                }
            ]
        }

    evaluation = evaluate_ppm(
        _ppm_result(
            (
                _field("ppm.strategy", "Long/short credit", "section-map", 0.91),
                _field(
                    "ppm.deviation.liquidity_gate",
                    "NON-STANDARD quarterly gate",
                    "clause-map",
                    0.88,
                ),
            )
        ),
        _ppm_library(),
        consent=EgressConsent(
            granted_by="operator",
            purpose="describe PPM deviation notes",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=fake_client,
    )

    assert [(item.key, item.status) for item in evaluation.checklist] == [
        ("ppm.strategy", "present"),
        ("ppm.fees", "missing"),
        ("ppm.side_letter_hooks", "not observed"),
    ]
    assert evaluation.checklist[1].citation == "ppm:ppm.fees:missing"
    assert evaluation.deviation_notes == (
        inv_man_intake.docproc.ppm.DeviationNote(
            element_key="ppm.deviation.liquidity_gate",
            summary="Quarterly gate differs from the standard subscription terms.",
            why_it_matters="Operator should review liquidity constraints before approval.",
            citation="ppm:ppm.deviation.liquidity_gate:p3:clause-map",
        ),
    )
    assert outbound_calls
    assert json.loads((tmp_path / "egress.jsonl").read_text(encoding="utf-8"))


def test_deterministic_coverage_does_not_call_llm(tmp_path: Path) -> None:
    def forbidden_client(
        payload: dict[str, Any], provider_config: ProviderConfig
    ) -> Mapping[str, Any]:
        raise AssertionError("coverage-only PPM evaluation must not call the LLM")

    evaluation = evaluate_ppm(
        _ppm_result((_field("ppm.strategy", "Long/short credit", "section-map", 0.91),)),
        _ppm_library(),
        consent=EgressConsent(
            granted_by="operator",
            purpose="not used",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=forbidden_client,
    )

    assert evaluation.deviation_notes == ()
    assert not (tmp_path / "egress.jsonl").exists()


def test_ppm_decoupling_includes_library_added_element_without_code_change() -> None:
    throwaway_key = "ppm.throwaway_fixture_only"
    evaluation = evaluate_ppm(
        _ppm_result((_field(throwaway_key, "present", "section-map", 0.9),)),
        load_standard_element_library(
            {
                "version": "ppm-test",
                "non_authoritative": True,
                "doc_types": {
                    "ppm": [
                        {
                            "key": throwaway_key,
                            "detector_name": "field_present",
                            "mandatory": True,
                        }
                    ]
                },
            }
        ),
    )

    assert [(item.key, item.status) for item in evaluation.checklist] == [
        (throwaway_key, "present")
    ]
    ppm_source = Path(inv_man_intake.docproc.ppm.__file__).read_text(encoding="utf-8")
    assert throwaway_key not in ppm_source


def test_deviation_notes_reject_uncited_response(tmp_path: Path) -> None:
    def uncited_client(
        payload: dict[str, Any], provider_config: ProviderConfig
    ) -> Mapping[str, Any]:
        return {
            "notes": [
                {
                    "element_key": "ppm.deviation.liquidity_gate",
                    "summary": "Looks unusual.",
                    "why_it_matters": "Needs review.",
                    "citation": "made-up-citation",
                }
            ]
        }

    with pytest.raises(ValueError, match="uncited"):
        evaluate_ppm(
            _ppm_result(
                (
                    _field(
                        "ppm.deviation.liquidity_gate",
                        "NON-STANDARD quarterly gate",
                        "clause-map",
                        0.88,
                    ),
                )
            ),
            _ppm_library(),
            consent=EgressConsent(
                granted_by="operator",
                purpose="describe PPM deviation notes",
                granted_at="2026-07-07T09:00:00Z",
            ),
            provider_config=ProviderConfig(
                provider="frontier-zero-retention",
                model="secure-model",
                zero_retention=True,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=uncited_client,
        )


def _ppm_library():
    return load_standard_element_library(
        {
            "version": "ppm-test",
            "non_authoritative": True,
            "doc_types": {
                "ppm": [
                    {
                        "key": "ppm.strategy",
                        "detector_name": "field_present",
                        "mandatory": True,
                    },
                    {
                        "key": "ppm.fees",
                        "detector_name": "field_present",
                        "mandatory": True,
                    },
                    {
                        "key": "ppm.side_letter_hooks",
                        "detector_name": "field_present",
                        "mandatory": False,
                    },
                ]
            },
        }
    )


def _ppm_result(fields: tuple[ExtractedField, ...]) -> ExtractedDocumentResult:
    return ExtractedDocumentResult(
        source_doc_id="ppm",
        provider_name="ppm-test-provider",
        fields=fields,
    )


def _field(
    key: str,
    value: str,
    method: str,
    confidence: float,
) -> ExtractedField:
    return ExtractedField(
        key=key,
        value=value,
        confidence=confidence,
        source_doc_id="ppm",
        source_page=3,
        method=method,
    )
