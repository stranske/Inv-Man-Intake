from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operator_and_assistant_design_docs_lock_issue_718_boundaries() -> None:
    operator_doc = (ROOT / "docs/design/operator-application.md").read_text(encoding="utf-8")
    assistant_doc = (ROOT / "docs/design/intake-improvement-assistant.md").read_text(
        encoding="utf-8"
    )
    combined = f"{operator_doc}\n{assistant_doc}"

    for required in (
        "#718",
        "#721",
        "#722",
        "#723",
        "#724",
        "#725",
        "#726",
        "#727",
        "#711",
        "#714",
        "#716",
        "#717",
        "validation_queue_api.py",
        "run.py",
        "local-first",
        "no raw document payload egress",
        "requires_human_apply",
        "never edits `config/*`",
    ):
        assert required in combined

    assert "headless backend" in operator_doc
    assert "No Auto-Apply" in assistant_doc
