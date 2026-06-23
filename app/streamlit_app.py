"""Streamlit/stlite demo for the local intake-to-score smoke path."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from inv_man_intake.observability import InMemoryTraceSink  # noqa: E402
from inv_man_intake.readiness.fixture_batches import DEFAULT_BATCH_PACKAGES  # noqa: E402
from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission  # noqa: E402
from inv_man_intake.scoring.engine import compute_score  # noqa: E402
from inv_man_intake.scoring.weights import weights_by_asset_class_for  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "intake"
FIXTURE_OPTIONS = tuple(
    cast(str, package["intake_bundle_file"]) for package in DEFAULT_BATCH_PACKAGES
)
FIXTURE_DISPLAY_LABELS = {
    "pdf_primary_mixed_bundle.json": "Mixed-source PDF intake sample",
    "pptx_primary_mixed_bundle.json": "Mixed presentation intake sample",
}
PACKAGE_CONFIG_BY_FIXTURE = {
    cast(str, package["intake_bundle_file"]): {
        "package_id": cast(str, package["package_id"]),
        "expected_document_ids": cast(tuple[str, ...], package["expected_document_ids"]),
    }
    for package in DEFAULT_BATCH_PACKAGES
}
run_v1_smoke_pipeline: Any | None = None


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


QUEUE_ACTION_STATE_KEY = "analyst_queue_action_state"


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
    return DemoResult(
        fixture_name=fixture_name,
        package_id=package["package_id"],
        final_score=float(artifacts.score.final_score),
        components=components,
        owner_role=str(artifacts.queue_assignment.owner_role),
        item_id=str(artifacts.queue_assignment.item_id),
        sink_type=type(artifacts.sink).__name__,
        trace_tags=trace_tags,
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
        weights_by_asset_class=weights_by_asset_class_for("credit"),
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
        reason=(
            "The scoring pipeline routed this package for analyst review because "
            f"{conflict_type.lower()} evidence needs confirmation."
        ),
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


def render_app(st: StreamlitLike | None = None) -> DemoResult:
    """Render the browser demo and return the underlying deterministic result."""

    if st is None:
        import streamlit as streamlit_module

        st = cast(StreamlitLike, streamlit_module)

    st.set_page_config(page_title="Inv-Man-Intake Demo", layout="wide")
    st.title("Inv-Man-Intake")
    st.caption("Synthetic fixture demo. Computation runs locally with LangSmith disabled.")
    fixture_name = st.selectbox(
        "Synthetic intake bundle",
        FIXTURE_OPTIONS,
        format_func=lambda fixture: FIXTURE_DISPLAY_LABELS.get(
            fixture, fixture.removesuffix(".json").replace("_", " ").title()
        ),
    )
    result = run_demo_fixture(fixture_name)

    st.metric("Final score", f"{result.final_score:.4f}")
    st.subheader("Explainability")
    st.table(result.components)
    st.subheader("Analyst queue")
    render_analyst_queue(st, result)
    return result


if __name__ == "__main__":
    render_app()
