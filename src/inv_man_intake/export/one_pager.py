"""No-egress content model for the browser-printable manager strategy summary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inv_man_intake.packet import ManagerProfile


@dataclass(frozen=True)
class OnePagerField:
    """A labeled, human-readable value in the one-page summary."""

    label: str
    value: str


@dataclass(frozen=True)
class OnePagerGraphic:
    """A bounded graphic reference with enough provenance for the SPA."""

    label: str
    provenance_ref: str
    media_type: str | None = None


@dataclass(frozen=True)
class OnePagerModel:
    """Structured content consumed by HTML, print, or later document renderers."""

    title: str
    identity: tuple[OnePagerField, ...]
    coverage: tuple[OnePagerField, ...]
    final_score: float
    explainability: tuple[OnePagerField, ...]
    provenance_citations: tuple[str, ...]
    return_stats: tuple[OnePagerField, ...]
    graphics: tuple[OnePagerGraphic, ...]

    def as_dict(self) -> dict[str, object]:
        """Return JSON-ready primitives for the static SPA without rendering HTML."""

        return asdict(self)


@dataclass(frozen=True)
class OnePagerExporter:
    """Build a browser-agnostic summary model from the packet's canonical profile."""

    max_graphics: int = 4
    max_citations: int = 5
    max_identity_fields: int = 4
    max_explainability_fields: int = 5
    max_return_stats: int = 4
    max_value_characters: int = 80

    def build(self, profile: ManagerProfile) -> OnePagerModel:
        """Build the complete one-page content model without I/O or network access."""

        if (
            min(
                self.max_graphics,
                self.max_citations,
                self.max_identity_fields,
                self.max_explainability_fields,
                self.max_return_stats,
                self.max_value_characters,
            )
            < 0
        ):
            raise ValueError("one-pager limits must be non-negative")
        _validate_scores(profile.scores)
        identity = _identity_fields(
            profile.identity, self.max_identity_fields, self.max_value_characters
        )
        manager = next((field.value for field in identity if field.label == "Manager"), "Manager")
        return OnePagerModel(
            title=f"{manager} strategy summary",
            identity=identity,
            coverage=_coverage_fields(profile, self.max_value_characters),
            final_score=_final_score(profile.scores),
            explainability=_bounded_fields(
                (
                    OnePagerField(label=_display_label(key), value=f"{value:.4f}")
                    for key, value in sorted(profile.scores.items())
                ),
                self.max_explainability_fields,
                self.max_value_characters,
            ),
            provenance_citations=tuple(
                _bounded_text(ref, self.max_value_characters)
                for ref in profile.lineage_refs[: self.max_citations]
            ),
            return_stats=_bounded_fields(
                (
                    OnePagerField(label=_display_label(key), value=value)
                    for key, value in sorted(profile.returns_metrics.items())
                ),
                self.max_return_stats,
                self.max_value_characters,
            ),
            graphics=_graphics(profile, max_graphics=self.max_graphics),
        )


def build_one_pager(profile: ManagerProfile, *, max_graphics: int = 4) -> OnePagerModel:
    """Build the default one-page strategy summary model for a manager profile."""

    return OnePagerExporter(max_graphics=max_graphics).build(profile)


def _identity_fields(
    identity: Mapping[str, str], max_fields: int, max_value_characters: int
) -> tuple[OnePagerField, ...]:
    fields = _bounded_fields(
        (
            OnePagerField(label=_display_label(key), value=value)
            for key, value in sorted(
                identity.items(), key=lambda item: (item[0] != "identity.manager", item[0])
            )
        ),
        max_fields,
        max_value_characters,
    )
    if fields:
        return fields
    return (OnePagerField(label="Manager", value="Unknown manager"),)


def _coverage_fields(
    profile: ManagerProfile, max_value_characters: int
) -> tuple[OnePagerField, ...]:
    document_types = ", ".join(sorted({document.document_type for document in profile.documents}))
    coverage_items = sum(len(document.standard_element_coverage) for document in profile.documents)
    detected_items = sum(
        coverage.detected
        for document in profile.documents
        for coverage in document.standard_element_coverage
    )
    return (
        OnePagerField(label="Documents", value=str(len(profile.documents))),
        OnePagerField(
            label="Document types",
            value=_bounded_text(document_types or "Not classified", max_value_characters),
        ),
        OnePagerField(label="Standard elements", value=f"{detected_items}/{coverage_items}"),
    )


def _final_score(scores: Mapping[str, float]) -> float:
    if "final_score" in scores:
        return scores["final_score"]
    return scores.get("extraction_confidence", 0.0)


def _validate_scores(scores: Mapping[str, float]) -> None:
    invalid = [
        key
        for key, value in scores.items()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
    ]
    if invalid:
        raise ValueError(f"one-pager scores must be finite numbers: {invalid}")


def _bounded_fields(
    fields: Iterable[OnePagerField], max_fields: int, max_value_characters: int
) -> tuple[OnePagerField, ...]:
    return tuple(
        OnePagerField(field.label, _bounded_text(field.value, max_value_characters))
        for field in tuple(fields)[:max_fields]
    )


def _bounded_text(value: str, max_characters: int) -> str:
    value = str(value)
    return (
        value
        if len(value) <= max_characters
        else f"{value[: max(0, max_characters - 1)].rstrip()}…"
    )


def _graphics(profile: ManagerProfile, *, max_graphics: int) -> tuple[OnePagerGraphic, ...]:
    artifacts = tuple(
        OnePagerGraphic(
            label=artifact.name,
            provenance_ref=(
                artifact.provenance_refs[0] if artifact.provenance_refs else artifact.name
            ),
            media_type=artifact.media_type,
        )
        for artifact in profile.graphics_artifacts[:max_graphics]
    )
    if artifacts:
        return artifacts
    return tuple(
        OnePagerGraphic(label=ref, provenance_ref=ref)
        for ref in profile.graphics_refs[:max_graphics]
    )


def _display_label(key: str) -> str:
    if key == "identity.manager":
        return "Manager"
    return key.replace("_", " ").replace(".", " / ").title()
