from __future__ import annotations

import ast
import types
from pathlib import Path

from scripts.langchain import _llm_client

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module_source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_langchain_client_uses_llm_registry_as_single_resolution_source() -> None:
    source = _module_source("tools/langchain_client.py")
    tree = ast.parse(source)

    local_classes = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    local_function_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }

    assert "ModelRegistryEntry" not in local_classes
    assert "SlotDefinition" not in local_classes
    assert "json.loads" not in source
    assert "from tools.llm_registry import" in source

    # Compatibility wrappers are allowed, but the resolver implementation must
    # live in tools.llm_registry so scripts and providers share one source.
    assert {"build_chat_client", "build_chat_clients"} <= local_function_names
    assert "resolve_slots(" in source
    assert "load_slot_config(" in source


def test_script_llm_client_adapter_delegates_to_langchain_client(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    sentinel_client = object()

    def fake_build_chat_client(**kwargs: object) -> object:
        calls.append(kwargs)
        return types.SimpleNamespace(
            client=sentinel_client,
            provider="openai",
            model="gpt-configured",
            provider_label="openai/gpt-configured",
        )

    monkeypatch.setattr(_llm_client, "build_client", lambda **kwargs: fake_build_chat_client(**kwargs))

    client, label = _llm_client.get_llm_client(
        provider="openai",
        model="gpt-configured",
        return_field="provider_label",
    )

    assert client is sentinel_client
    assert label == "openai/gpt-configured"
    assert calls == [
        {
            "model": "gpt-configured",
            "provider": "openai",
            "force_openai": False,
        }
    ]


def test_scripts_do_not_bypass_shared_llm_client_adapter() -> None:
    for path in (REPO_ROOT / "scripts").rglob("*.py"):
        if path.as_posix().endswith("scripts/langchain/_llm_client.py"):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path.as_posix())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "tools.langchain_client"
                and any(alias.name in {"build_chat_client", "*"} for alias in node.names)
            ):
                raise AssertionError(path.relative_to(REPO_ROOT).as_posix())
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "tools"
                and any(alias.name == "langchain_client" for alias in node.names)
            ):
                raise AssertionError(path.relative_to(REPO_ROOT).as_posix())
            if isinstance(node, ast.Import) and any(
                alias.name == "tools.langchain_client" for alias in node.names
            ):
                raise AssertionError(path.relative_to(REPO_ROOT).as_posix())
