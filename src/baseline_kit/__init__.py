"""Small baseline test helpers vendored for this repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

_EPSILON = 1e-9


def load_catalog(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Catalog root must be a mapping")
    return payload


def evaluate_direction(direction: str, variant: float, control: float) -> bool:
    key = str(direction).strip().lower()
    if key == "increase":
        return variant > control + _EPSILON
    if key == "decrease":
        return variant < control - _EPSILON
    if key in {"equal", "same"}:
        return abs(variant - control) <= _EPSILON
    raise ValueError(f"Unknown direction: {direction}")


def check_metrics(num_regression: Any, metrics: dict[str, Any]) -> None:
    num_regression.check(metrics)


@dataclass(frozen=True)
class InvariantResult:
    name: str
    ok: bool
    severity: str
    detail: str


def assert_invariants(results: list[InvariantResult], context: str = "") -> None:
    failures = [result for result in results if not result.ok]
    if not failures:
        return
    prefix = f"[{context}] " if context else ""
    message = "\n".join(
        f"{prefix}{result.severity}:{result.name}: {result.detail}" for result in failures
    )
    raise AssertionError("Invariant failures:\n" + message)


@dataclass(frozen=True)
class CoverageManifest:
    all_keys: set[str]
    touched_keys: set[str]
    priority_params: list[str]
    title: str = "Baseline coverage manifest"

    @property
    def unknown_catalog_keys(self) -> set[str]:
        return self.touched_keys - self.all_keys

    @property
    def uncovered_keys(self) -> set[str]:
        return self.all_keys - self.touched_keys

    @property
    def priority_gaps(self) -> list[str]:
        return [key for key in self.priority_params if key not in self.touched_keys]

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        lines.append(f"- total metric keys: {len(self.all_keys)}")
        lines.append(f"- touched by directionals: {len(self.touched_keys)}")
        lines.append(f"- uncovered: {len(self.uncovered_keys)}")
        lines.append("")
        lines.append("## Priority gaps")
        if self.priority_gaps:
            lines.extend(f"- {key}" for key in self.priority_gaps)
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Unknown directional keys")
        if self.unknown_catalog_keys:
            lines.extend(f"- {key}" for key in sorted(self.unknown_catalog_keys))
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Uncovered keys")
        if self.uncovered_keys:
            lines.extend(f"- {key}" for key in sorted(self.uncovered_keys))
        else:
            lines.append("- none")
        lines.append("")
        return "\n".join(lines)
