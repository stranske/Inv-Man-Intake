"""Shared LLM slot and model-registry resolution helpers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_MODEL_REGISTRY_CONFIG = "LANGCHAIN_MODEL_REGISTRY_CONFIG"
ENV_SLOT_CONFIG = "LANGCHAIN_SLOT_CONFIG"

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GITHUB = "github-models"

DEFAULT_SLOT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_slots.json"
DEFAULT_MODEL_REGISTRY_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "model_registry.json"
)


@dataclass(frozen=True)
class ModelRegistryEntry:
    provider: str
    model: str
    blocked: bool
    quality: dict[str, float]


def normalize_provider(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"github", "github_models", "github-models"}:
        return PROVIDER_GITHUB
    if normalized in {"anthropic", "claude"}:
        return PROVIDER_ANTHROPIC
    if normalized == PROVIDER_OPENAI:
        return PROVIDER_OPENAI
    return None


def load_model_registry() -> list[ModelRegistryEntry]:
    config_path = os.environ.get(ENV_MODEL_REGISTRY_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_MODEL_REGISTRY_CONFIG_PATH
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read model registry %s; continuing without registry", path)
        return []
    if not isinstance(payload, dict):
        logger.warning("Invalid model registry format in %s; expected object", path)
        return []

    entries: list[ModelRegistryEntry] = []
    for raw_entry in payload.get("models", []):
        provider = normalize_provider(str(raw_entry.get("provider", "")))
        model = str(raw_entry.get("model_id", "")).strip()
        if not provider or not model:
            continue
        quality_payload = raw_entry.get("quality", {})
        quality = {
            str(tier).upper(): float(score)
            for tier, score in quality_payload.items()
            if isinstance(score, int | float)
        }
        entries.append(
            ModelRegistryEntry(
                provider=provider,
                model=model,
                blocked=bool(raw_entry.get("blocked", False)),
                quality=quality,
            )
        )
    return entries


def registry_entry_for(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> ModelRegistryEntry | None:
    entries = registry if registry is not None else load_model_registry()
    normalized_provider = normalize_provider(provider)
    normalized_model = model.strip()
    for entry in entries:
        if entry.provider == normalized_provider and entry.model == normalized_model:
            return entry
    return None


def is_model_blocked(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> bool:
    entry = registry_entry_for(provider, model, registry=registry)
    return bool(entry and entry.blocked)


def select_model_for_tier(
    *,
    provider: str,
    tier: str,
    registry: list[ModelRegistryEntry] | None = None,
) -> str | None:
    entries = registry if registry is not None else load_model_registry()
    normalized_provider = normalize_provider(provider)
    normalized_tier = tier.strip().upper()
    candidates = [
        entry
        for entry in entries
        if entry.provider == normalized_provider
        and not entry.blocked
        and normalized_tier in entry.quality
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda entry: entry.quality[normalized_tier])
    return selected.model


def configured_model_for_provider(
    provider: str,
    *,
    fallback: str,
    tier: str = "T3",
    registry: list[ModelRegistryEntry] | None = None,
) -> str:
    normalized_provider = normalize_provider(provider)
    entries = registry if registry is not None else load_model_registry()

    config_path = os.environ.get(ENV_SLOT_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_SLOT_CONFIG_PATH
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            logger.warning("Invalid slot config format in %s; expected object", path)
            payload = {}
        for slot in payload.get("slots", []):
            slot_provider = normalize_provider(str(slot.get("provider", "")))
            if slot_provider != normalized_provider:
                continue
            model = str(slot.get("model", "")).strip()
            slot_tier = str(slot.get("quality_tier") or slot.get("tier") or tier).strip()
            if not model and slot_tier:
                model = select_model_for_tier(
                    provider=slot_provider or "",
                    tier=slot_tier,
                    registry=entries,
                ) or ""
            if model and not is_model_blocked(slot_provider or "", model, registry=entries):
                return model

    selected = select_model_for_tier(provider=provider, tier=tier, registry=entries)
    if selected:
        return selected
    if not is_model_blocked(provider, fallback, registry=entries):
        return fallback
    return ""
