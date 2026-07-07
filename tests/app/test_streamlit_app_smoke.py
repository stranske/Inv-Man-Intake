from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.streamlit_app import QUEUE_ACTION_STATE_KEY, build_operator_packet_view, render_app

from inv_man_intake.observability import InMemoryTraceSink
from inv_man_intake.packet import PacketFile


class _StreamlitRecorder:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, str]] = []
        self.tables: list[object] = []
        self.buttons: list[tuple[str, str]] = []
        self.selectboxes: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        self.success_messages: list[str] = []
        self.write_calls: list[tuple[object, ...]] = []
        self.clicked_keys: set[str] = set()
        self.session_state: dict[str, object] = {}

    def set_page_config(self, **kwargs: object) -> None:
        return None

    def title(self, body: str) -> None:
        return None

    def caption(self, body: str) -> None:
        return None

    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        format_func: Callable[[str], str] | None = None,
    ) -> str:
        display_options = tuple(
            format_func(option) if format_func else option for option in options
        )
        self.selectboxes.append((label, options, display_options))
        return "pdf_primary_mixed_bundle.json"

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))

    def subheader(self, body: str) -> None:
        return None

    def table(self, data: object) -> None:
        self.tables.append(data)

    def button(self, label: str, *, key: str) -> bool:
        self.buttons.append((label, key))
        return key in self.clicked_keys

    def write(self, *args: object, **kwargs: object) -> None:
        self.write_calls.append(args)
        return None

    def success(self, body: str) -> None:
        self.success_messages.append(body)
        return None


@dataclass(frozen=True)
class _FakeScore:
    final_score: float
    red_flag_reason: str | None = None


@dataclass(frozen=True)
class _FakeQueueAssignment:
    owner_role: str
    item_id: str


@dataclass(frozen=True)
class _FakeThresholdDecision:
    escalate: bool
    escalation_reason: str | None


@dataclass(frozen=True)
class _FakeArtifacts:
    sink: object
    trace_context: object
    formatted_explainability: dict[str, object]
    score: _FakeScore
    queue_assignment: _FakeQueueAssignment
    threshold_decision: object = _FakeThresholdDecision(escalate=False, escalation_reason=None)


@dataclass(frozen=True)
class _FakeTraceContext:
    tags: dict[str, str]


def test_app_renders_score_for_fixture_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    recorder = _StreamlitRecorder()
    result = render_app(recorder)

    assert result.final_score == pytest.approx(0.7809)
    assert result.components
    assert result.owner_role == "analyst"
    assert result.sink_type == InMemoryTraceSink.__name__
    assert "langsmith_enabled" not in result.trace_tags
    assert "langsmith_project" not in result.trace_tags
    assert recorder.metrics == [("Final score", "0.7809")]
    assert recorder.tables[0] == result.components


def test_demo_presentation_hides_developer_observability_details() -> None:
    recorder = _StreamlitRecorder()

    render_app(recorder)

    assert recorder.selectboxes
    label, backing_options, display_options = recorder.selectboxes[0]
    assert label == "Synthetic intake bundle"
    assert "pdf_primary_mixed_bundle.json" in backing_options
    assert "Mixed-source PDF intake sample" in display_options
    assert all(not option.endswith(".json") for option in display_options)

    rendered_main_content = " ".join(
        [*recorder.success_messages, *(" ".join(map(str, call)) for call in recorder.write_calls)]
    )
    assert "Trace sink:" not in rendered_main_content
    assert "LangSmith and LangChain tracing env vars are off" not in rendered_main_content


def test_app_temporarily_disables_langsmith_and_langchain_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_live")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_pt_live")
    monkeypatch.setenv("LANGSMITH_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    def _fake_pipeline(**_: object) -> _FakeArtifacts:
        assert "LANGSMITH_API_KEY" not in os.environ
        assert "LANGCHAIN_API_KEY" not in os.environ
        assert "LANGSMITH_TRACING_ENABLED" not in os.environ
        assert "LANGCHAIN_TRACING_V2" not in os.environ
        return _FakeArtifacts(
            sink=InMemoryTraceSink(),
            trace_context=_FakeTraceContext(tags={"stage": "intake"}),
            formatted_explainability={"components": [{"component": "risk_adjusted_returns"}]},
            score=_FakeScore(final_score=0.1234),
            queue_assignment=_FakeQueueAssignment(owner_role="analyst", item_id="queue-item"),
        )

    monkeypatch.setattr("app.streamlit_app.run_v1_smoke_pipeline", _fake_pipeline)

    recorder = _StreamlitRecorder()
    result = render_app(recorder)

    assert result.final_score == pytest.approx(0.1234)
    assert result.owner_role == "analyst"
    assert result.item_id == "queue-item"
    assert result.sink_type == InMemoryTraceSink.__name__
    assert result.trace_tags == {"stage": "intake"}
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2_pt_live"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_pt_live"
    assert os.environ["LANGSMITH_TRACING_ENABLED"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_analyst_queue_renders_readable_item_and_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = "pkg_pdf_mixed_001:validation:performance_conflict:corr_4d03914dd557"

    def _fake_pipeline(**_: object) -> _FakeArtifacts:
        return _FakeArtifacts(
            sink=InMemoryTraceSink(),
            trace_context=_FakeTraceContext(tags={"stage": "intake"}),
            formatted_explainability={"components": [{"component": "risk_adjusted_returns"}]},
            score=_FakeScore(final_score=0.4321),
            queue_assignment=_FakeQueueAssignment(owner_role="analyst", item_id=item_id),
            threshold_decision=_FakeThresholdDecision(
                escalate=True, escalation_reason="confidence_below_threshold:terms.management_fee"
            ),
        )

    monkeypatch.setattr("app.streamlit_app.run_v1_smoke_pipeline", _fake_pipeline)

    recorder = _StreamlitRecorder()
    recorder.clicked_keys.add(f"{item_id}:escalate")
    result = render_app(recorder)

    queue_rows = recorder.tables[1]
    assert isinstance(queue_rows, list)
    assert queue_rows == [
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
            "State": "Escalated to ops",
        }
    ]
    assert item_id not in str(queue_rows)
    assert recorder.buttons == [
        ("Accept", f"{item_id}:accept"),
        ("Escalate", f"{item_id}:escalate"),
        ("Needs-info", f"{item_id}:needs-info"),
    ]
    assert recorder.session_state[QUEUE_ACTION_STATE_KEY] == {result.item_id: "Escalated to ops"}


def test_app_uses_browser_safe_score_when_pyodide_lacks_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _sqlite_missing_pipeline(**_: object) -> object:
        raise ModuleNotFoundError("No module named 'sqlite3'", name="sqlite3")

    monkeypatch.setattr("app.streamlit_app.run_v1_smoke_pipeline", _sqlite_missing_pipeline)

    recorder = _StreamlitRecorder()
    result = render_app(recorder)

    assert result.final_score == pytest.approx(0.7809)
    assert result.sink_type == InMemoryTraceSink.__name__
    assert result.trace_tags == {"stage": "browser-demo", "sqlite_fallback": "true"}
    assert recorder.metrics == [("Final score", "0.7809")]


def test_app_browser_safe_score_uses_registry_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    def _sqlite_missing_pipeline(**_: object) -> object:
        raise ModuleNotFoundError("No module named 'sqlite3'", name="sqlite3")

    monkeypatch.setattr("app.streamlit_app.run_v1_smoke_pipeline", _sqlite_missing_pipeline)
    monkeypatch.setattr(
        "app.streamlit_app.weights_for_registry",
        lambda: {
            "credit_long_short": {
                "performance_consistency": 1.00,
                "risk_adjusted_returns": 0.00,
                "operational_quality": 0.00,
                "transparency": 0.00,
                "team_experience": 0.00,
            }
        },
    )

    result = render_app(_StreamlitRecorder())

    assert result.final_score == pytest.approx(0.80)
    assert result.components[0] == {
        "component": "performance_consistency",
        "contribution": pytest.approx(0.80),
    }


def test_operator_packet_panels_render_after_existing_queue() -> None:
    recorder = _StreamlitRecorder()

    render_app(recorder)

    assert recorder.tables[2]
    coverage_rows = recorder.tables[2]
    assert isinstance(coverage_rows, list)
    assert {row["Document"] for row in coverage_rows} == {"track_record", "deck", "ppm"}
    assert recorder.tables[3], "manager profile table should render packet fields"
    assert recorder.tables[4], "graphics gallery table should expose a clickable target"
    assert recorder.tables[5], "return-stream table should render extracted return metrics"
    assert recorder.tables[6], "exception queue should consume validation_queue_api"
    assert recorder.tables[7] == [{"Deterministic outbound calls": 0}]


def test_operator_packet_view_accepts_library_added_doc_type_without_app_code_change() -> None:
    view = build_operator_packet_view(
        (
            PacketFile(
                document_id="custom",
                filename="custom.txt",
                content=b"custom_added_type Summit Arc AUM $100.0M",
            ),
        ),
        priority=("custom_added_type",),
    )

    assert view.coverage_rows == [
        {
            "Document": "custom",
            "Type": "custom_added_type",
            "Coverage": "2/4",
            "Missing": "None",
        }
    ]
    assert view.outbound_calls == 0


def test_live_verification_evidence_is_recorded() -> None:
    evidence = Path("app/live-verification.md")
    screenshot = Path("app/live-verification-screenshot.svg")
    browser_script = Path("scripts/verify_stlite_browser.py")

    assert evidence.exists()
    assert screenshot.exists()
    assert browser_script.exists()

    content = evidence.read_text(encoding="utf-8")
    assert "app/index.html" in content
    assert "python -m http.server 8000" in content
    assert "http://127.0.0.1:8000/app/index.html" in content
    assert (
        "uv run --extra dev python scripts/verify_stlite_browser.py --browser-channel chrome"
        in content
    )
    assert "app/live-verification-artifacts/browser-demo-score.png" in content
    assert "app/live-verification-artifacts/browser-demo-score.json" in content
    assert "pdf_primary_mixed_bundle.json" in content
    assert "0.7809" in content
    assert "live-verification-screenshot.svg" in content
    assert "static visual reference only" in content


def test_stlite_mount_bundles_package_and_fixture_files() -> None:
    content = Path("app/index.html").read_text(encoding="utf-8")
    stlite_lock = set(Path("requirements-stlite.lock").read_text(encoding="utf-8").splitlines())

    assert '"src/inv_man_intake/v1_smoke.py"' in content
    assert '"src/inv_man_intake/data/migrations/sql/0001_core_firm_fund_document.up.sql"' in content
    assert '"tests/fixtures/intake/pdf_primary_mixed_bundle.json"' in content
    assert "Object.fromEntries" in content
    assert '"langsmith>=0.4.59"' not in content
    assert stlite_lock == {
        "@stlite/mountable==0.75.0",
        "pyodide==0.26.2",
        "streamlit==1.40.1",
    }
    assert '<script src="./vendor/stlite@0.75.0/stlite.js"></script>' in content
    assert (
        'pyodideUrl: new URL("./vendor/pyodide@0.26.2/pyodide.js", ' "window.location.href).href"
    ) in content
