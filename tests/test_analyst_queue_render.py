from __future__ import annotations

from app.streamlit_app import (
    QUEUE_ACTION_STATE_KEY,
    DemoResult,
    render_analyst_queue,
)


class StreamlitRecorder:
    def __init__(self) -> None:
        self.tables: list[object] = []
        self.buttons: list[tuple[str, str]] = []
        self.clicked_keys: set[str] = set()
        self.session_state: dict[str, object] = {}

    def button(self, label: str, *, key: str) -> bool:
        self.buttons.append((label, key))
        return key in self.clicked_keys

    def table(self, data: object) -> None:
        self.tables.append(data)


def _demo_result(
    item_id: str,
    decision_reason: str = "confidence_below_threshold:terms.management_fee",
) -> DemoResult:
    return DemoResult(
        fixture_name="pdf_primary_mixed_bundle.json",
        package_id="pkg_pdf_mixed_001",
        final_score=0.4321,
        components=[],
        owner_role="analyst",
        item_id=item_id,
        sink_type="InMemoryTraceSink",
        trace_tags={},
        decision_reason=decision_reason,
    )


def test_analyst_queue_render_decodes_item_id_and_records_session_action() -> None:
    item_id = "pkg_pdf_mixed_001:validation:performance_conflict:corr_4d03914dd557"
    recorder = StreamlitRecorder()
    recorder.clicked_keys.add(f"{item_id}:needs-info")

    card = render_analyst_queue(recorder, _demo_result(item_id))

    assert card.owner == "Analyst"
    assert card.package == "pkg_pdf_mixed_001"
    assert card.headline == "Performance Conflict requires validation review"
    assert card.state == "Needs information"
    assert recorder.buttons == [
        ("Accept", f"{item_id}:accept"),
        ("Escalate", f"{item_id}:escalate"),
        ("Needs-info", f"{item_id}:needs-info"),
    ]
    assert recorder.session_state[QUEUE_ACTION_STATE_KEY] == {item_id: "Needs information"}

    assert recorder.tables == [
        [
            {
                "Owner": "Analyst",
                "Package": "pkg_pdf_mixed_001",
                "Issue": "Performance Conflict requires validation review",
                "Reason": "Pipeline decision: confidence_below_threshold:terms.management_fee",
                "Affected evidence": "Package pkg_pdf_mixed_001; evidence marker corr_4d03914dd557",
                "Suggested resolution": (
                    "Open the package evidence, confirm the conflict, then accept the score, "
                    "escalate to ops, or request missing information."
                ),
                "State": "Needs information",
            }
        ]
    ]
    assert item_id not in str(recorder.tables)


def test_analyst_queue_card_reason_reflects_pipeline_decision() -> None:
    """The card reason must be derived from the real pipeline decision (#698), not a fixed template
    built from the item_id tokens."""
    item_id = "pkg_pdf_mixed_001:validation:performance_conflict:corr_4d03914dd557"
    recorder = StreamlitRecorder()

    card = render_analyst_queue(
        recorder, _demo_result(item_id, decision_reason="missing_mandatory_field:operations.aum")
    )

    assert card.reason == "Pipeline decision: missing_mandatory_field:operations.aum"
    # Not the old token-derived boilerplate.
    assert "evidence needs confirmation" not in card.reason
