from __future__ import annotations

import json
import sys
import types

import pytest

from tools import langchain_client, llm_provider


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


def test_slot_config_ignores_non_object_payload(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "gpt-safe",
                    "provider": "openai",
                    "quality": {"T3": 0.80},
                }
            ]
        },
    )
    slots_path = tmp_path / "llm_slots.json"
    slots_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, str(slots_path))

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("slot1", langchain_client.PROVIDER_OPENAI, "gpt-5.4"),
        ("slot2", langchain_client.PROVIDER_ANTHROPIC, "claude-sonnet-4-6"),
        ("slot3", langchain_client.PROVIDER_GITHUB, langchain_client.DEFAULT_MODEL),
    ]


def test_slot_config_ignores_non_list_slots_payload(tmp_path, monkeypatch) -> None:
    slots_path = _write_json(tmp_path / "llm_slots.json", {"slots": {"bad": "shape"}})
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("slot1", langchain_client.PROVIDER_OPENAI, "gpt-5.4"),
        ("slot2", langchain_client.PROVIDER_ANTHROPIC, "claude-sonnet-4-6"),
        ("slot3", langchain_client.PROVIDER_GITHUB, langchain_client.DEFAULT_MODEL),
    ]


def test_slot_config_skips_non_object_slot_entries(tmp_path, monkeypatch) -> None:
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {
            "slots": [
                "bad-entry",
                {"name": "safe", "provider": "openai", "model": "gpt-safe"},
            ]
        },
    )
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("safe", langchain_client.PROVIDER_OPENAI, "gpt-safe")
    ]


def test_model_registry_ignores_non_object_payload(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "model_registry.json"
    registry_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {"slots": [{"name": "primary", "provider": "openai", "quality_tier": "T3"}]},
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)

    slots = langchain_client._resolve_slots()

    assert [(slot.name, slot.provider, slot.model) for slot in slots] == [
        ("slot1", langchain_client.PROVIDER_OPENAI, "gpt-5.4"),
        ("slot2", langchain_client.PROVIDER_ANTHROPIC, "claude-sonnet-4-6"),
        ("slot3", langchain_client.PROVIDER_GITHUB, langchain_client.DEFAULT_MODEL),
    ]


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


def test_llm_provider_uses_configured_slot_model(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "gpt-configured",
                    "provider": "openai",
                    "quality": {"T3": 0.91},
                }
            ]
        },
    )
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {"slots": [{"name": "primary", "provider": "openai", "model": "gpt-configured"}]},
    )
    fake_openai_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai_module)
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-token")

    client = llm_provider.OpenAIProvider()._get_client()

    assert client is not None
    assert FakeChatOpenAI.calls[-1]["model"] == "gpt-configured"


def test_llm_provider_skips_blocked_slot_model(tmp_path, monkeypatch) -> None:
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
                    "model_id": "gpt-safe",
                    "provider": "openai",
                    "quality": {"T3": 0.80},
                },
            ]
        },
    )
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {"slots": [{"name": "primary", "provider": "openai", "model": "gpt-blocked"}]},
    )
    fake_openai_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai_module)
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-token")

    client = llm_provider.OpenAIProvider()._get_client()

    assert client is not None
    assert FakeChatOpenAI.calls[-1]["model"] == "gpt-safe"


def test_anthropic_completion_reports_configured_model(tmp_path, monkeypatch) -> None:
    registry_path = _write_json(
        tmp_path / "model_registry.json",
        {
            "models": [
                {
                    "model_id": "claude-configured",
                    "provider": "anthropic",
                    "quality": {"T3": 0.91},
                }
            ]
        },
    )
    slots_path = _write_json(
        tmp_path / "llm_slots.json",
        {
            "slots": [
                {
                    "name": "primary",
                    "provider": "anthropic",
                    "model": "claude-configured",
                }
            ]
        },
    )

    class FakeAnthropicClient:
        def invoke(self, prompt, **kwargs):
            return types.SimpleNamespace(content="ok")

    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, registry_path)
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, slots_path)
    monkeypatch.setattr(
        llm_provider.AnthropicProvider,
        "_get_client",
        lambda self: FakeAnthropicClient(),
    )
    monkeypatch.setattr(
        llm_provider.GitHubModelsProvider,
        "_build_analysis_prompt",
        lambda self, session_output, tasks, context: "prompt",
    )
    monkeypatch.setattr(
        llm_provider.GitHubModelsProvider,
        "_parse_response",
        lambda self, content, tasks, quality_context=None: llm_provider.CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.9,
            reasoning="ok",
            provider_used="github-models",
            model_name="stale-hardcoded",
        ),
    )

    result = llm_provider.AnthropicProvider().analyze_completion("output", ["task"])

    assert result.model_name == "claude-configured"
