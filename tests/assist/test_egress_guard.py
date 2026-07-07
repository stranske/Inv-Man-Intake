"""Tests for the assistant egress guard."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import inv_man_intake.run as deterministic_run
from inv_man_intake.assist.egress_guard import EgressConsent, ProviderConfig, send_to_llm


def test_guard_redacts_requires_consent_and_logs(tmp_path: Path) -> None:
    outbound_calls: list[dict[str, Any]] = []

    def fake_client(payload: dict[str, Any], provider_config: ProviderConfig) -> Mapping[str, Any]:
        outbound_calls.append({"payload": payload, "provider": provider_config.provider})
        return {"recommendations": ["review threshold drift"]}

    log_path = tmp_path / "egress.jsonl"
    provider_config = ProviderConfig(
        provider="frontier-zero-retention",
        model="secure-model",
        zero_retention=True,
        baa_eligible=True,
    )
    payload = {
        "task": "recommend intake improvements",
        "document_text": "PROPRIETARY:AlphaFund raw document text",
        "signals": [
            {
                "field": "aum",
                "snippet": "AUM changed for PROPRIETARY:AlphaFund",
                "derived_score": 0.42,
            }
        ],
    }

    with pytest.raises(PermissionError):
        send_to_llm(
            payload,
            consent=None,
            provider_config=provider_config,
            log_path=log_path,
            client=fake_client,
        )

    result = send_to_llm(
        payload,
        consent=EgressConsent(
            granted_by="operator",
            purpose="rank intake-improvement recommendations",
            granted_at="2026-07-07T09:00:00+00:00",
        ),
        provider_config=provider_config,
        log_path=log_path,
        client=fake_client,
        now=lambda: datetime(2026, 7, 7, 9, 0, tzinfo=UTC),
    )

    assert outbound_calls
    outbound_payload = outbound_calls[-1]["payload"]
    assert outbound_payload["document_text"] == "[REDACTED]"
    assert "PROPRIETARY:AlphaFund" not in json.dumps(outbound_payload)
    assert result.provider_response == {"recommendations": ["review threshold drift"]}

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["consent_granted_by"] == "operator"
    assert records[0]["redaction_applied"] is True
    assert "PROPRIETARY:AlphaFund" not in json.dumps(records[0])


def test_guard_rejects_non_zero_retention_provider(tmp_path: Path) -> None:
    def fake_client(payload: dict[str, Any], provider_config: ProviderConfig) -> Mapping[str, Any]:
        raise AssertionError("provider must not be called when policy is invalid")

    with pytest.raises(ValueError, match="zero-retention"):
        send_to_llm(
            {"task": "summarize", "document_text": "PROPRIETARY:AlphaFund"},
            consent=EgressConsent(
                granted_by="operator",
                purpose="test",
                granted_at="2026-07-07T09:00:00+00:00",
            ),
            provider_config=ProviderConfig(
                provider="unsafe-provider",
                model="model",
                zero_retention=False,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=fake_client,
        )


def test_deterministic_packet_path_does_not_import_egress_guard() -> None:
    source = inspect.getsource(deterministic_run)

    assert "egress_guard" not in source
    assert "send_to_llm" not in source
