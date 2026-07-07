"""Tests for the assistant egress guard."""

from __future__ import annotations

import ast
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
        "attachment": b"PROPRIETARY:AlphaFund bytes",
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
    assert outbound_payload["attachment"] == "[REDACTED]"
    assert "PROPRIETARY:AlphaFund" not in json.dumps(outbound_payload)
    assert result.provider_response == {"recommendations": ["review threshold drift"]}

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["consent_granted_by"] == "operator"
    assert records[0]["consent_granted_at"] == "2026-07-07T09:00:00+00:00"
    assert records[0]["redaction_applied"] is True
    assert "PROPRIETARY:AlphaFund" not in json.dumps(records[0])


def test_guard_isolated_from_client_payload_mutation(tmp_path: Path) -> None:
    def mutating_client(
        payload: dict[str, Any], provider_config: ProviderConfig
    ) -> Mapping[str, Any]:
        payload["document_text"] = "PROPRIETARY:AlphaFund restored"
        payload["nested"]["raw_document"] = "PROPRIETARY:AlphaFund restored"
        return {"ok": True}

    result = send_to_llm(
        {
            "document_text": "PROPRIETARY:AlphaFund",
            "nested": {"raw_document": "CONFIDENTIAL:LPData"},
        },
        consent=EgressConsent(
            granted_by="operator",
            purpose="test mutation isolation",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=mutating_client,
        now=lambda: datetime(2026, 7, 7, 9, 1, tzinfo=UTC),
    )

    assert result.outbound_payload["document_text"] == "[REDACTED]"
    assert result.outbound_payload["nested"] == {"raw_document": "[REDACTED]"}
    assert result.log_record.outbound_payload == result.outbound_payload
    assert "PROPRIETARY:AlphaFund" not in json.dumps(
        json.loads((tmp_path / "egress.jsonl").read_text(encoding="utf-8"))
    )


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


def test_guard_rejects_non_baa_provider(tmp_path: Path) -> None:
    def fake_client(payload: dict[str, Any], provider_config: ProviderConfig) -> Mapping[str, Any]:
        raise AssertionError("provider must not be called when policy is invalid")

    with pytest.raises(ValueError, match="BAA eligible"):
        send_to_llm(
            {"task": "summarize"},
            consent=EgressConsent(
                granted_by="operator",
                purpose="test",
                granted_at="2026-07-07T09:00:00+00:00",
            ),
            provider_config=ProviderConfig(
                provider="unsafe-provider",
                model="model",
                zero_retention=True,
                baa_eligible=False,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=fake_client,
        )


def test_guard_rejects_consent_without_timezone(tmp_path: Path) -> None:
    def fake_client(payload: dict[str, Any], provider_config: ProviderConfig) -> Mapping[str, Any]:
        raise AssertionError("client must not be called when consent is invalid")

    with pytest.raises(ValueError, match="granted_at must include a timezone"):
        send_to_llm(
            {"task": "summarize"},
            consent=EgressConsent(
                granted_by="operator",
                purpose="test",
                granted_at="2026-07-07T09:00:00",
            ),
            provider_config=ProviderConfig(
                provider="frontier-zero-retention",
                model="model",
                zero_retention=True,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=fake_client,
        )


def test_deterministic_packet_path_does_not_import_egress_guard() -> None:
    tree = ast.parse(Path(deterministic_run.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert "inv_man_intake.assist" not in imported_modules
    assert "inv_man_intake.assist.egress_guard" not in imported_modules
