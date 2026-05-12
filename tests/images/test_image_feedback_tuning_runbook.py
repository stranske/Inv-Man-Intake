"""Guardrails for image feedback tuning runbook completeness."""

from __future__ import annotations

from pathlib import Path

DOC_PATH = Path("docs/runbooks/image_feedback_tuning.md")


REQUIRED_TOKENS = (
    "python scripts/image_feedback_report.py",
    "--reviewed-from",
    "--reviewed-to",
    "informative_rate",
    "quality_rank_distribution",
    "disagreement_rate",
    "Interpretation guidance for tuning decisions",
    "minimum sample-size guard",
    "Recommended tuning loop",
)


def test_image_feedback_tuning_runbook_covers_generation_and_consumption() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    for token in REQUIRED_TOKENS:
        assert token in text
