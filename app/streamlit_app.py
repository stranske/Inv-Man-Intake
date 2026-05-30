"""Streamlit/stlite demo for the local intake-to-score smoke path."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from inv_man_intake.observability import InMemoryTraceSink  # noqa: E402
from inv_man_intake.readiness.throughput import DEFAULT_BATCH_PACKAGES  # noqa: E402
from inv_man_intake.v1_smoke import run_v1_smoke_pipeline  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "intake"
FIXTURE_OPTIONS = tuple(
    cast(str, package["intake_bundle_file"]) for package in DEFAULT_BATCH_PACKAGES
)
PACKAGE_CONFIG_BY_FIXTURE = {
    cast(str, package["intake_bundle_file"]): {
        "package_id": cast(str, package["package_id"]),
        "expected_document_ids": cast(tuple[str, ...], package["expected_document_ids"]),
    }
    for package in DEFAULT_BATCH_PACKAGES
}


class StreamlitLike(Protocol):
    """Small subset used by the renderer so tests can pass a recorder."""

    def set_page_config(self, **kwargs: Any) -> None: ...
    def title(self, body: str) -> None: ...
    def caption(self, body: str) -> None: ...
    def selectbox(self, label: str, options: tuple[str, ...]) -> str: ...
    def metric(self, label: str, value: str) -> None: ...
    def subheader(self, body: str) -> None: ...
    def table(self, data: object) -> None: ...
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
        artifacts = run_v1_smoke_pipeline(
            fixture_root=FIXTURE_ROOT,
            intake_bundle_file=fixture_name,
            package_id=package["package_id"],
            expected_document_ids=package["expected_document_ids"],
        )
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


def render_app(st: StreamlitLike | None = None) -> DemoResult:
    """Render the browser demo and return the underlying deterministic result."""

    if st is None:
        import streamlit as streamlit_module

        st = cast(StreamlitLike, streamlit_module)

    st.set_page_config(page_title="Inv-Man-Intake Demo", layout="wide")
    st.title("Inv-Man-Intake")
    st.caption("Synthetic fixture demo. Computation runs locally with LangSmith disabled.")
    fixture_name = st.selectbox("Synthetic intake bundle", FIXTURE_OPTIONS)
    result = run_demo_fixture(fixture_name)

    st.metric("Final score", f"{result.final_score:.4f}")
    st.subheader("Explainability")
    st.table(result.components)
    st.subheader("Analyst queue")
    st.write({"owner_role": result.owner_role, "item_id": result.item_id})
    st.success(f"Trace sink: {result.sink_type}; LangSmith and LangChain tracing env vars are off.")
    return result


if __name__ == "__main__":
    render_app()
