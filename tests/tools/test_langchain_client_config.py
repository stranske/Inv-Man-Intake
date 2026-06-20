from __future__ import annotations

import json
import sys
import types

import pytest

from tools import langchain_client


class FakeChatOpenAI:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)


class FakeChatAnthropic:
    calls: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.calls.append(kwargs)


@pytest.fixture(autouse=True)
def reset_fake_chat_calls():
    FakeChatOpenAI.calls.clear()
    FakeChatAnthropic.calls.clear()
    yield
    FakeChatOpenAI.calls.clear()
    FakeChatAnthropic.calls.clear()


def _write_json(path, payload: dict[str, object]) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_slot_config_skips_model_registry_blocked_models(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "gpt-blocked",
                    "provider": "openai",
                    "blocked": True,
                    "quality": {"T3": 0.99},
                },
                {
                    "model_id": "claude-ok",
                    "provider": "anthropic",
                    "quality": {"T3": 0.80},
                },
            ]
        },
    )
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {
            "slots": [
                {"name": "unsafe", "provider": "openai", "model": "gpt-blocked"},
                {"name": "safe", "provider": "anthropic", "model": "claude-ok"},
            ]
        },
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("safe", langchain_client.PROVIDER_ANTHROPIC, "claude-ok")
    ]


def test_slot_config_resolves_quality_tier_from_model_registry(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "gpt-low",
                    "provider": "openai",
                    "quality": {"T3": 0.50},
                },
                {
                    "model_id": "gpt-blocked-high",
                    "provider": "openai",
                    "blocked": True,
                    "quality": {"T3": 0.99},
                },
                {
                    "model_id": "gpt-safe-high",
                    "provider": "openai",
                    "quality": {"T3": 0.85},
                },
            ]
        },
    )
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {"slots": [{"name": "review", "provider": "openai", "quality_tier": "T3"}]},
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("review", langchain_client.PROVIDER_OPENAI, "gpt-safe-high")
    ]


def test_build_chat_client_refuses_explicit_blocked_model(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "gpt-blocked",
                    "provider": "openai",
                    "blocked": True,
                    "quality": {"T1": 0.10},
                }
            ]
        },
    )
    fake_openai_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    fake_anthropic_module = types.SimpleNamespace(ChatAnthropic=FakeChatAnthropic)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai_module)
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_anthropic_module)
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-token")

    client = langchain_client.build_chat_client(provider="openai", model="gpt-blocked")

    assert client is None
    assert FakeChatOpenAI.calls == []
