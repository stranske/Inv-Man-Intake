"""Tests for return-stream shape characterization and scoring gates."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from inv_man_intake.assist.egress_guard import EgressConsent, ProviderConfig
from inv_man_intake.intake.standard_elements import (
    DataDrivenStandardElementLibrary,
    StandardElement,
)
from inv_man_intake.performance.characterize import (
    characterize_series,
    gate_scoring_submission,
    require_operator_confirmation,
)
from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.metrics import compute_metrics
from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission


def test_non_standard_series_tagged_and_gated() -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
            (date(2025, 3, 31), -0.01),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    characterization = characterize_series(
        series,
        metrics,
        source_notes=("Pro forma backfilled track record; operator review required.",),
    )

    assert characterization.tag == "pro_forma"
    assert characterization.requires_operator_confirmation is True
    assert characterization.metrics == metrics
    with pytest.raises(PermissionError, match="requires operator confirmation"):
        gate_scoring_submission(_score_submission(), characterization=characterization)

    confirmed = require_operator_confirmation(characterization)
    assert confirmed.requires_operator_confirmation is False
    assert gate_scoring_submission(_score_submission(), characterization=confirmed) == (
        _score_submission()
    )


def test_clean_monthly_series_flows_to_scoring_without_confirmation() -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
            (date(2025, 3, 31), 0.03),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    characterization = characterize_series(series, metrics)

    assert characterization.tag == "standard"
    assert characterization.requires_operator_confirmation is False
    assert gate_scoring_submission(_score_submission(), characterization=characterization) == (
        _score_submission()
    )


def test_metrics_are_byte_identical_to_deterministic_output() -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.02),
            (date(2025, 2, 28), -0.01),
            (date(2025, 3, 31), 0.03),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    characterization = characterize_series(
        series,
        metrics,
        source_notes=("Composite sleeve in USD terms.",),
    )

    assert characterization.metrics.to_canonical_dict() == metrics.to_canonical_dict()


def test_short_currency_keywords_require_token_boundary() -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.02),
            (date(2025, 2, 28), 0.03),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    standard = characterize_series(series, metrics, source_notes=("Amateur sleeve upload",))
    currency = characterize_series(series, metrics, source_notes=("USD sleeve upload",))

    assert standard.tag == "standard"
    assert currency.tag == "currency_noted"


def test_ambiguous_tail_routes_through_egress_guard(tmp_path: Path) -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))
    calls: list[dict[str, Any]] = []

    def client(payload: dict[str, Any], provider_config: ProviderConfig) -> dict[str, Any]:
        calls.append({"payload": payload, "provider": provider_config.provider})
        return {
            "tag": "gross_net_ambiguous",
            "rationale": "The notes require gross/net treatment review.",
            "confidence": 0.73,
        }

    characterization = characterize_series(
        series,
        metrics,
        source_notes=("Manager says treatment needs review.",),
        consent=EgressConsent(
            granted_by="operator",
            purpose="classify ambiguous return stream",
            granted_at="2026-07-07T23:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier",
            model="review-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.ndjson",
        client=client,
        now=lambda: datetime(2026, 7, 7, 23, 0, tzinfo=UTC),
    )

    assert characterization.tag == "gross_net_ambiguous"
    assert calls
    assert calls[0]["payload"]["constraints"]["do_not_compute_or_change_returns"] is True
    assert (tmp_path / "egress.ndjson").read_text(encoding="utf-8")


def test_invalid_llm_payload_raises_domain_error(tmp_path: Path) -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    def client(payload: dict[str, Any], provider_config: ProviderConfig) -> dict[str, Any]:
        return {
            "tag": "gross_net_ambiguous",
            "rationale": "The notes require gross/net treatment review.",
            "confidence": 0.73,
            "provider_metadata": {"trace_id": "abc"},
        }

    with pytest.raises(ValueError, match="invalid LLM characterization payload"):
        characterize_series(
            series,
            metrics,
            source_notes=("Manager says treatment needs review.",),
            consent=EgressConsent(
                granted_by="operator",
                purpose="classify ambiguous return stream",
                granted_at="2026-07-07T23:00:00Z",
            ),
            provider_config=ProviderConfig(
                provider="frontier",
                model="review-model",
                zero_retention=True,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.ndjson",
            client=client,
            now=lambda: datetime(2026, 7, 7, 23, 0, tzinfo=UTC),
        )


def test_ambiguous_source_names_route_through_egress_guard(tmp_path: Path) -> None:
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))
    calls: list[dict[str, Any]] = []

    def client(payload: dict[str, Any], provider_config: ProviderConfig) -> dict[str, Any]:
        calls.append(payload)
        return {
            "tag": "composite",
            "rationale": "The source name indicates composite returns.",
            "confidence": 0.71,
        }

    characterization = characterize_series(
        series,
        metrics,
        source_names=("returns-upload.csv",),
        consent=EgressConsent(
            granted_by="operator",
            purpose="classify ambiguous return stream",
            granted_at="2026-07-07T23:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier",
            model="review-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.ndjson",
        client=client,
        now=lambda: datetime(2026, 7, 7, 23, 0, tzinfo=UTC),
    )

    assert characterization.tag == "composite"
    assert characterization.evidence == ("returns-upload.csv",)
    assert calls[0]["source_names"] == ["returns-upload.csv"]
    assert calls[0]["allowed_tags"] == [
        "pro_forma",
        "blended",
        "backfilled",
        "gross_net_ambiguous",
        "currency_noted",
        "composite",
    ]


def test_doc_type_handling_uses_standard_element_library_port() -> None:
    throwaway_doc_type = "library_added_return_stream"
    library = DataDrivenStandardElementLibrary(
        version="test",
        non_authoritative=True,
        elements_by_doc_type={
            throwaway_doc_type: (
                StandardElement(
                    key="performance.return_stream",
                    detector_name="field_present",
                    mandatory=True,
                ),
            )
        },
    )
    series = _monthly_series(
        (
            (date(2025, 1, 31), 0.01),
            (date(2025, 2, 28), 0.02),
        )
    )
    metrics = compute_metrics(PerformancePayload(monthly=series))

    characterization = characterize_series(series, metrics, standard_library=library)

    assert characterization.doc_types_available == library.doc_types()


def _monthly_series(points: tuple[tuple[date, float], ...]) -> PerformanceSeries:
    return PerformanceSeries(
        "monthly",
        tuple(PerformancePoint(as_of=as_of, value=value) for as_of, value in points),
    )


def _score_submission() -> ScoreSubmission:
    return ScoreSubmission(
        manager_id="manager-1",
        asset_class="equity_market_neutral",
        components=(
            ScoreComponent("performance_consistency", 0.8),
            ScoreComponent("risk_adjusted_returns", 0.7),
            ScoreComponent("operational_quality", 0.6),
            ScoreComponent("transparency", 0.5),
            ScoreComponent("team_experience", 0.4),
        ),
    )
