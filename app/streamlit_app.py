"""Streamlit/stlite demo for the local intake-to-score smoke path."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
DESIGN_SYSTEM_ROOT = Path(__file__).resolve().parents[1] / "design-system"
if str(DESIGN_SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(DESIGN_SYSTEM_ROOT))

from inv_man_intake.extraction.providers.base import (  # noqa: E402
    ExtractedDocumentResult,
    ExtractedField,
)
from inv_man_intake.intake.standard_elements import load_standard_element_library  # noqa: E402
from inv_man_intake.observability import InMemoryTraceSink  # noqa: E402
from inv_man_intake.packet import PacketFile, ingest_packet  # noqa: E402
from inv_man_intake.readiness.fixture_batches import DEFAULT_BATCH_PACKAGES  # noqa: E402
from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission  # noqa: E402
from inv_man_intake.scoring.engine import compute_score  # noqa: E402
from inv_man_intake.scoring.weights import weights_for_registry  # noqa: E402
from inv_man_intake.validation_queue_api import (  # noqa: E402
    ValidationQueueQuery,
    list_validation_queue,
)
from inv_man_intake.workflow_validation import ValidationQueueRow  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "intake"
FIXTURE_OPTIONS = tuple(
    cast(str, package["intake_bundle_file"]) for package in DEFAULT_BATCH_PACKAGES
)
FIXTURE_DISPLAY_METADATA = {
    "pdf_primary_mixed_bundle.json": {
        "label": "Mixed-source PDF intake sample",
        "description": "PDF-led sample package with mixed evidence for the analyst queue demo.",
    },
    "pptx_primary_mixed_bundle.json": {
        "label": "Mixed presentation intake sample",
        "description": "Presentation-led sample package for checking intake and scoring output.",
    },
}
PACKAGE_CONFIG_BY_FIXTURE = {
    cast(str, package["intake_bundle_file"]): {
        "package_id": cast(str, package["package_id"]),
        "expected_document_ids": cast(tuple[str, ...], package["expected_document_ids"]),
    }
    for package in DEFAULT_BATCH_PACKAGES
}
run_v1_smoke_pipeline: Any | None = None


def fixture_display_label(fixture_name: str) -> str:
    """Return the analyst-facing label for a committed fixture bundle."""

    metadata = FIXTURE_DISPLAY_METADATA.get(fixture_name)
    if metadata:
        return metadata["label"]
    return fixture_name.removesuffix(".json").replace("_", " ").title()


def fixture_display_description(fixture_name: str) -> str:
    """Return a one-line description for the selected fixture bundle."""

    metadata = FIXTURE_DISPLAY_METADATA.get(fixture_name)
    if metadata:
        return metadata["description"]
    return "Sample intake bundle for the deterministic browser demo."


class StreamlitLike(Protocol):
    """Small subset used by the renderer so tests can pass a recorder."""

    def set_page_config(self, **kwargs: Any) -> None: ...
    def title(self, body: str) -> None: ...
    def caption(self, body: str) -> None: ...
    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        format_func: Callable[[str], str] | None = None,
    ) -> str: ...
    def metric(self, label: str, value: str) -> None: ...
    def subheader(self, body: str) -> None: ...
    def table(self, data: object) -> None: ...
    def button(self, label: str, *, key: str) -> bool: ...
    @property
    def session_state(self) -> dict[str, object]: ...
    def write(self, *args: object, **kwargs: object) -> None: ...
    def success(self, body: str) -> None: ...


@dataclass(frozen=True)
class DemoResult:
    fixture_name: str
    package_id: str
    final_score: float
    components: list[dict[str, object]]
    owner_role: str
    item_id: str
    sink_type: str
    trace_tags: dict[str, str]
    decision_reason: str


@dataclass(frozen=True)
class AnalystQueueCard:
    """Human-readable queue row for the demo analyst workflow."""

    owner: str
    package: str
    headline: str
    reason: str
    affected_evidence: str
    suggested_resolution: str
    state: str


@dataclass(frozen=True)
class OperatorPacketView:
    """Operator-facing projection of a packet ingestion run."""

    packet_id: str
    coverage_rows: list[dict[str, object]]
    profile_rows: list[dict[str, object]]
    graphics_rows: list[dict[str, object]]
    return_rows: list[dict[str, object]]
    exception_rows: list[dict[str, object]]
    outbound_calls: int


QUEUE_ACTION_STATE_KEY = "analyst_queue_action_state"
OPERATOR_GRAPHIC_STATE_KEY = "operator_graphic_open_state"
DEFAULT_DOC_TYPE_PRIORITY = ("track_record", "deck", "ppm")
SAMPLE_PACKET_FILES = (
    PacketFile(
        document_id="track_record",
        filename="track-record.txt",
        content=(
            b"Track record for Summit Arc. Manager: Summit Arc Capital. "
            b"1 year return 12.5%. AUM $100.0M."
        ),
    ),
    PacketFile(
        document_id="deck",
        filename="deck.txt",
        content=(
            b"Investor deck for Summit Arc. Management fee 1.25%. "
            b"AUM $92.0M. Graphic: drawdown chart."
        ),
    ),
    PacketFile(
        document_id="ppm",
        filename="ppm.txt",
        content=b"Private placement memorandum. Management fee 1.25%.",
    ),
)


def _suppress_langsmith_env() -> dict[str, str]:
    suppressed: dict[str, str] = {}
    for key in (
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_TRACING_ENABLED",
        "LANGCHAIN_TRACING_V2",
    ):
        value = os.environ.pop(key, None)
        if value is not None:
            suppressed[key] = value
    return suppressed


def _restore_env(values: dict[str, str]) -> None:
    for key, value in values.items():
        os.environ[key] = value


def run_demo_fixture(fixture_name: str) -> DemoResult:
    """Run the real deterministic smoke pipeline for one committed fixture bundle."""

    package = PACKAGE_CONFIG_BY_FIXTURE[fixture_name]
    suppressed_env = _suppress_langsmith_env()
    try:
        pipeline = _load_v1_smoke_pipeline()
        artifacts = pipeline(
            fixture_root=FIXTURE_ROOT,
            intake_bundle_file=fixture_name,
            package_id=package["package_id"],
            expected_document_ids=package["expected_document_ids"],
        )
    except ModuleNotFoundError as exc:
        if exc.name != "sqlite3":
            raise
        return _browser_safe_demo_fixture(fixture_name)
    finally:
        _restore_env(suppressed_env)

    assert isinstance(artifacts.sink, InMemoryTraceSink)
    trace_tags = cast(dict[str, str], artifacts.trace_context.tags)
    assert "langsmith_enabled" not in trace_tags
    assert "langsmith_project" not in trace_tags
    components = cast(list[dict[str, object]], artifacts.formatted_explainability["components"])
    decision = artifacts.threshold_decision
    escalation_reason = (
        getattr(decision, "escalation_reason", None)
        if getattr(decision, "escalate", False)
        else None
    )
    decision_reason = (
        escalation_reason
        or artifacts.score.red_flag_reason
        or "auto-pass: no escalation or red flags"
    )
    return DemoResult(
        fixture_name=fixture_name,
        package_id=package["package_id"],
        final_score=float(artifacts.score.final_score),
        components=components,
        owner_role=str(artifacts.queue_assignment.owner_role),
        item_id=str(artifacts.queue_assignment.item_id),
        sink_type=type(artifacts.sink).__name__,
        trace_tags=trace_tags,
        decision_reason=str(decision_reason),
    )


def _load_v1_smoke_pipeline() -> Any:
    global run_v1_smoke_pipeline
    if run_v1_smoke_pipeline is None:
        from inv_man_intake.v1_smoke import run_v1_smoke_pipeline as pipeline

        run_v1_smoke_pipeline = pipeline
    return run_v1_smoke_pipeline


def _browser_safe_demo_fixture(fixture_name: str) -> DemoResult:
    """Render deterministic score evidence when Pyodide lacks sqlite3."""

    package = PACKAGE_CONFIG_BY_FIXTURE[fixture_name]
    components = (
        ScoreComponent("performance_consistency", 0.80),
        ScoreComponent("risk_adjusted_returns", 0.78),
        ScoreComponent("operational_quality", 0.69),
        ScoreComponent("transparency", 0.74),
        ScoreComponent("team_experience", 0.978997),
    )
    score = compute_score(
        ScoreSubmission(
            manager_id="fund_summit_arc_special_situations",
            asset_class="credit",
            components=components,
        ),
        weights_by_asset_class=weights_for_registry(),
    )
    return DemoResult(
        fixture_name=fixture_name,
        package_id=cast(str, package["package_id"]),
        final_score=float(score.final_score),
        components=[
            {"component": name, "contribution": contribution}
            for name, contribution in score.contributions.items()
        ],
        owner_role="analyst",
        item_id=f"{package['package_id']}:validation:browser-demo",
        sink_type=InMemoryTraceSink.__name__,
        trace_tags={"stage": "browser-demo", "sqlite_fallback": "true"},
        decision_reason=score.red_flag_reason or "auto-pass: no red flags (synthetic browser demo)",
    )


def build_analyst_queue_card(
    result: DemoResult,
    action_state: dict[str, str] | None = None,
) -> AnalystQueueCard:
    """Decode the internal queue item id into a readable analyst work item."""

    tokens = result.item_id.split(":")
    package_id = tokens[0] if tokens and tokens[0] else result.package_id
    validation_rule = _label_from_token(tokens[1]) if len(tokens) > 1 else "Validation"
    conflict_type = _label_from_token(tokens[2]) if len(tokens) > 2 else "Review needed"
    correlation = tokens[3] if len(tokens) > 3 else "demo item"

    return AnalystQueueCard(
        owner=result.owner_role.title(),
        package=package_id,
        headline=f"{conflict_type} requires {validation_rule.lower()} review",
        # Surface the REAL pipeline decision (threshold escalation / red-flag reason), not a
        # template derived from the item_id tokens (#698).
        reason=f"Pipeline decision: {result.decision_reason}",
        affected_evidence=f"Package {package_id}; evidence marker {correlation}",
        suggested_resolution=(
            "Open the package evidence, confirm the conflict, then accept the score, "
            "escalate to ops, or request missing information."
        ),
        state=(action_state or {}).get(result.item_id, "Waiting for analyst action"),
    )


def _label_from_token(token: str) -> str:
    return token.replace("_", " ").replace("-", " ").title()


def _queue_action_state(st: StreamlitLike) -> dict[str, str]:
    state = st.session_state.setdefault(QUEUE_ACTION_STATE_KEY, {})
    if not isinstance(state, dict):
        state = {}
        st.session_state[QUEUE_ACTION_STATE_KEY] = state
    return cast(dict[str, str], state)


def _record_queue_action(action_state: dict[str, str], item_id: str, action: str) -> None:
    action_state[item_id] = action


def render_analyst_queue(st: StreamlitLike, result: DemoResult) -> AnalystQueueCard:
    """Render a readable queue card and in-memory action controls."""

    action_state = _queue_action_state(st)
    if st.button("Accept", key=f"{result.item_id}:accept"):
        _record_queue_action(action_state, result.item_id, "Accepted")
    if st.button("Escalate", key=f"{result.item_id}:escalate"):
        _record_queue_action(action_state, result.item_id, "Escalated to ops")
    if st.button("Needs-info", key=f"{result.item_id}:needs-info"):
        _record_queue_action(action_state, result.item_id, "Needs information")
    card = build_analyst_queue_card(result, action_state)
    st.table(
        [
            {
                "Owner": card.owner,
                "Package": card.package,
                "Issue": card.headline,
                "Reason": card.reason,
                "Affected evidence": card.affected_evidence,
                "Suggested resolution": card.suggested_resolution,
                "State": card.state,
            }
        ]
    )
    return card


class _OperatorPacketProvider:
    """Browser-safe native-text provider for the operator app MVP."""

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        text = content.decode("utf-8", errors="ignore")
        fields = tuple(_operator_fields(source_doc_id, text))
        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name="operator-browser-native-text",
            fields=fields,
        )


def _operator_fields(source_doc_id: str, text: str) -> list[ExtractedField]:
    lowered = text.casefold()
    fields: list[ExtractedField] = []
    if "summit arc" in lowered:
        fields.append(
            _operator_field(source_doc_id, "identity.manager", "Summit Arc Capital", 0.91)
        )
    if "aum" in lowered:
        value = "$100.0M" if "100" in lowered else "$92.0M"
        fields.append(_operator_field(source_doc_id, "operations.aum", value, 0.86))
    if "return" in lowered:
        fields.append(_operator_field(source_doc_id, "performance.net_return_1y", "12.5%", 0.88))
    if "fee" in lowered:
        fields.append(_operator_field(source_doc_id, "terms.management_fee", "1.25%", 0.84))
    return fields


def _operator_field(source_doc_id: str, key: str, value: str, confidence: float) -> ExtractedField:
    return ExtractedField(
        key=key,
        value=value,
        confidence=confidence,
        source_doc_id=source_doc_id,
        source_page=1,
        method="browser-native-text",
    )


def _operator_library(priority: Sequence[str]):
    return load_standard_element_library(
        {
            "version": "operator-browser-mvp",
            "non_authoritative": True,
            "doc_types": {
                doc_type: [
                    {
                        "key": "identity.manager",
                        "detector_name": "field_present",
                        "mandatory": doc_type == priority[0],
                    },
                    {
                        "key": "operations.aum",
                        "detector_name": "numeric_field_present",
                        "mandatory": doc_type in set(priority[:2]),
                    },
                    {
                        "key": "performance.net_return_1y",
                        "detector_name": "field_present",
                        "mandatory": doc_type == "track_record",
                    },
                    {
                        "key": "terms.management_fee",
                        "detector_name": "field_present",
                        "mandatory": doc_type in {"deck", "ppm"},
                    },
                ]
                for doc_type in priority
            },
        }
    )


def build_operator_packet_view(
    files: Sequence[PacketFile] = SAMPLE_PACKET_FILES,
    *,
    priority: Sequence[str] = DEFAULT_DOC_TYPE_PRIORITY,
    action_state: Mapping[str, str] | None = None,
) -> OperatorPacketView:
    """Run packet ingestion and return the operator app tables."""

    profile = ingest_packet(
        files,
        provider=_OperatorPacketProvider(),
        standard_library=_operator_library(tuple(priority)),
        packet_id="operator-browser-packet",
    )
    coverage_rows = [
        {
            "Document": document.document_id,
            "Type": document.document_type,
            "Coverage": f"{_detected_count(document.standard_element_coverage)}/"
            f"{len(document.standard_element_coverage)}",
            "Missing": ", ".join(
                coverage.key
                for coverage in document.standard_element_coverage
                if coverage.mandatory and not coverage.detected
            )
            or "None",
        }
        for document in profile.documents
    ]
    profile_rows = [
        {"Field": key, "Value": value}
        for group in (profile.identity, profile.terms, profile.returns_metrics)
        for key, value in group.items()
    ]
    graphic_refs = profile.graphics_refs or tuple(
        f"{document.document_id}:visual:coverage"
        for document in profile.documents
        if document.document_type == "deck"
    )
    graphics_rows = [
        {
            "Graphic": graphic_ref,
            "Status": (action_state or {}).get(graphic_ref, "Ready"),
        }
        for graphic_ref in graphic_refs
    ]
    return_rows = [
        {"Metric": key, "Value": value} for key, value in profile.returns_metrics.items()
    ] or [{"Metric": "performance.net_return_1y", "Value": "Not supplied"}]
    queue_rows = _operator_queue_rows(profile.packet_id, profile.escalations)
    exception_rows = [
        {
            "Item": row.item_id,
            "State": row.state,
            "Owner": row.owner_role or "unassigned",
            "Reason": row.escalation_reason,
            "Next action": row.next_action,
        }
        for row in list_validation_queue(
            queue_rows,
            query=ValidationQueueQuery(states=("pending_triage",), owner_roles=("analyst",)),
        ).items
    ]
    return OperatorPacketView(
        packet_id=profile.packet_id,
        coverage_rows=coverage_rows,
        profile_rows=profile_rows,
        graphics_rows=graphics_rows,
        return_rows=return_rows,
        exception_rows=exception_rows,
        outbound_calls=0,
    )


def _detected_count(coverage_rows: Sequence[object]) -> int:
    return sum(1 for coverage in coverage_rows if getattr(coverage, "detected", False))


def _operator_queue_rows(
    packet_id: str, escalations: Sequence[str]
) -> tuple[ValidationQueueRow, ...]:
    reasons = tuple(escalations) or ("operator_packet_review:coverage_complete",)
    return tuple(
        ValidationQueueRow(
            item_id=f"{packet_id}:validation:{index}",
            package_id=packet_id,
            state="pending_triage",
            owner_id="operator",
            owner_role="analyst",
            escalation_reason=reason,
            next_action="Review packet evidence",
            updated_at=f"2026-07-07T19:2{index}:00Z",
        )
        for index, reason in enumerate(reasons, start=1)
    )


def _uploaded_packet_files(st: StreamlitLike) -> tuple[PacketFile, ...] | None:
    uploader = getattr(st, "file_uploader", None)
    if not callable(uploader):
        return None
    uploads = uploader(
        "Packet upload",
        accept_multiple_files=True,
        type=("txt", "md", "csv", "json"),
    )
    if not uploads:
        return None
    return tuple(
        PacketFile(
            document_id=f"upload_{index}",
            filename=getattr(upload, "name", f"upload-{index}.txt"),
            content=upload.getvalue(),
        )
        for index, upload in enumerate(uploads, start=1)
    )


def render_operator_packet(
    st: StreamlitLike,
    *,
    use_real_streamlit: bool,
) -> OperatorPacketView:
    """Render the packet-level operator app MVP."""

    priority = DEFAULT_DOC_TYPE_PRIORITY
    files = SAMPLE_PACKET_FILES
    graphic_state = st.session_state.setdefault(OPERATOR_GRAPHIC_STATE_KEY, {})
    if not isinstance(graphic_state, dict):
        graphic_state = {}
        st.session_state[OPERATOR_GRAPHIC_STATE_KEY] = graphic_state
    if use_real_streamlit:
        priority_selection = st.selectbox(
            "Doc-type priority",
            (
                "track_record -> deck -> ppm",
                "deck -> track_record -> ppm",
                "ppm -> deck -> track_record",
            ),
        )
        priority = tuple(part.strip() for part in priority_selection.split("->"))
        uploaded = _uploaded_packet_files(st)
        if uploaded is not None:
            files = uploaded

    view = build_operator_packet_view(
        files,
        priority=priority,
        action_state=cast(dict[str, str], graphic_state),
    )
    st.subheader("Packet coverage")
    st.table(view.coverage_rows)
    st.subheader("Manager profile")
    st.table(view.profile_rows)
    st.subheader("Graphics gallery")
    if use_real_streamlit:
        for row in view.graphics_rows:
            graphic_ref = str(row["Graphic"])
            if st.button("Open graphic", key=f"open-graphic:{graphic_ref}"):
                cast(dict[str, str], graphic_state)[graphic_ref] = "Opened"
        view = build_operator_packet_view(
            files,
            priority=priority,
            action_state=cast(dict[str, str], graphic_state),
        )
    st.table(view.graphics_rows)
    st.subheader("Return stream")
    st.table(view.return_rows)
    st.subheader("Exception queue")
    st.table(view.exception_rows)
    st.table([{"Deterministic outbound calls": view.outbound_calls}])
    return view


def render_app(st: StreamlitLike | None = None) -> DemoResult:
    """Render the browser demo and return the underlying deterministic result."""

    use_real_streamlit = st is None
    if st is None:
        import streamlit as streamlit_module

        st = cast(StreamlitLike, streamlit_module)

    st.set_page_config(page_title="Inv-Man-Intake Demo", layout="wide")
    if use_real_streamlit:
        from ds_streamlit import inject_theme

        inject_theme()
    st.title("Inv-Man-Intake")
    st.caption("Synthetic fixture demo. Computation runs locally with LangSmith disabled.")
    fixture_name = st.selectbox(
        "Synthetic intake bundle",
        FIXTURE_OPTIONS,
        format_func=fixture_display_label,
    )
    st.caption(f"{fixture_display_description(fixture_name)} Backing fixture: `{fixture_name}`.")
    result = run_demo_fixture(fixture_name)

    st.metric("Final score", f"{result.final_score:.4f}")
    st.subheader("Explainability")
    st.table(result.components)
    st.subheader("Analyst queue")
    render_analyst_queue(st, result)
    render_operator_packet(st, use_real_streamlit=use_real_streamlit)
    return result


if __name__ == "__main__":
    render_app()
