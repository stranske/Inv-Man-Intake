"""Heuristic informative-vs-boilerplate classifier for visual artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from inv_man_intake.images.models import VisualArtifact

VisualClassificationLabel = Literal["informative", "boilerplate"]

_INFORMATIVE_TERMS = {
    "alpha",
    "attribution",
    "benchmark",
    "bps",
    "chart",
    "correlation",
    "drawdown",
    "exposure",
    "gross",
    "index",
    "monthly",
    "performance",
    "portfolio",
    "return",
    "returns",
    "risk",
    "sector",
    "sharpe",
    "table",
    "volatility",
    "ytd",
}
_BOILERPLATE_TERMS = {
    "all rights reserved",
    "confidential",
    "copyright",
    "disclaimer",
    "for institutional use",
    "for professional investors",
    "logo",
    "not an offer",
    "terms of use",
    "trademark",
}
_CHART_PATTERN = re.compile(r"\b(?:q[1-4]|20\d{2}|fy\d{2}|[0-9]+(?:\.[0-9]+)?%)\b", re.I)
_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_%.-]*")


@dataclass(frozen=True)
class VisualArtifactClassification:
    """Classification result consumed by downstream filtering and review queues."""

    artifact_id: str
    label: VisualClassificationLabel
    confidence: float
    reason_codes: tuple[str, ...]
    rationale: str


def classify_visual_artifact(artifact: VisualArtifact) -> VisualArtifactClassification:
    """Classify a visual artifact using deterministic lightweight content heuristics."""

    text = _decode_preview_text(artifact.content)
    lowered = text.lower()
    tokens = tuple(token.lower() for token in _TOKEN_PATTERN.findall(text))
    token_count = len(tokens)

    informative_hits = tuple(term for term in sorted(_INFORMATIVE_TERMS) if term in lowered)
    boilerplate_hits = tuple(term for term in sorted(_BOILERPLATE_TERMS) if term in lowered)

    informative_score = 0
    boilerplate_score = 0
    reasons: list[str] = []

    if informative_hits:
        informative_score += min(4, len(informative_hits)) * 2
        reasons.append("informative_terms")
    if boilerplate_hits:
        boilerplate_score += min(4, len(boilerplate_hits)) * 2
        reasons.append("boilerplate_terms")

    if _CHART_PATTERN.search(text):
        informative_score += 3
        reasons.append("chart_numeric_markers")
    if token_count >= 18:
        informative_score += 2
        reasons.append("text_density")
    elif artifact.byte_size <= 512 or token_count <= 5:
        boilerplate_score += 2
        reasons.append("low_information_density")

    if artifact.source.source_ref is not None:
        source_ref = artifact.source.source_ref.lower()
        if any(marker in source_ref for marker in ("logo", "banner", "footer", "masthead")):
            boilerplate_score += 3
            reasons.append("boilerplate_source_ref")

    if informative_score >= boilerplate_score:
        label: VisualClassificationLabel = "informative"
        margin = informative_score - boilerplate_score
        confidence = _confidence(0.62, margin, informative_score + boilerplate_score)
        rationale = _rationale("informative", informative_hits, boilerplate_hits, reasons)
    else:
        label = "boilerplate"
        margin = boilerplate_score - informative_score
        confidence = _confidence(0.58, margin, informative_score + boilerplate_score)
        rationale = _rationale("boilerplate", informative_hits, boilerplate_hits, reasons)

    reason_codes = tuple(dict.fromkeys(reasons)) or ("fallback_content_heuristic",)
    return VisualArtifactClassification(
        artifact_id=artifact.artifact_id,
        label=label,
        confidence=confidence,
        reason_codes=reason_codes,
        rationale=rationale,
    )


def _decode_preview_text(content: bytes) -> str:
    return content[:8192].decode("utf-8", errors="ignore")


def _confidence(base: float, margin: int, total_score: int) -> float:
    score = base + min(0.25, margin * 0.04) + min(0.12, total_score * 0.01)
    return round(min(0.95, score), 2)


def _rationale(
    label: VisualClassificationLabel,
    informative_hits: tuple[str, ...],
    boilerplate_hits: tuple[str, ...],
    reasons: list[str],
) -> str:
    if label == "informative" and informative_hits:
        return f"Informative visual signals: {', '.join(informative_hits[:4])}."
    if label == "boilerplate" and boilerplate_hits:
        return f"Boilerplate visual signals: {', '.join(boilerplate_hits[:4])}."
    if "chart_numeric_markers" in reasons:
        return "Numeric chart or period markers indicate review-relevant content."
    if "low_information_density" in reasons:
        return "Low text density and small payload suggest decorative or repeated boilerplate."
    return f"Defaulted to {label} based on balanced content heuristics."
