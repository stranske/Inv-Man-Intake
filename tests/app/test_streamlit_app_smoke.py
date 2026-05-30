from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.streamlit_app import render_app

from inv_man_intake.observability import InMemoryTraceSink


class _StreamlitRecorder:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, str]] = []
        self.tables: list[object] = []

    def set_page_config(self, **kwargs: object) -> None:
        return None

    def title(self, body: str) -> None:
        return None

    def caption(self, body: str) -> None:
        return None

    def selectbox(self, label: str, options: tuple[str, ...]) -> str:
        return "pdf_primary_mixed_bundle.json"

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))

    def subheader(self, body: str) -> None:
        return None

    def table(self, data: object) -> None:
        self.tables.append(data)

    def write(self, *args: object, **kwargs: object) -> None:
        return None

    def success(self, body: str) -> None:
        return None


@dataclass(frozen=True)
class _FakeScore:
    final_score: float


@dataclass(frozen=True)
class _FakeQueueAssignment:
    owner_role: str
    item_id: str


@dataclass(frozen=True)
class _FakeArtifacts:
    sink: object
    formatted_explainability: dict[str, object]
    score: _FakeScore
    queue_assignment: _FakeQueueAssignment


def test_app_renders_score_for_fixture_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    recorder = _StreamlitRecorder()
    result = render_app(recorder)

    assert result.final_score == pytest.approx(0.7809)
    assert result.components
    assert result.owner_role == "analyst"
    assert result.sink_type == InMemoryTraceSink.__name__
    assert recorder.metrics == [("Final score", "0.7809")]
    assert recorder.tables == [result.components]


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
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2_pt_live"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_pt_live"
    assert os.environ["LANGSMITH_TRACING_ENABLED"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_live_verification_evidence_is_recorded() -> None:
    evidence = Path("app/live-verification.md")
    screenshot = Path("app/live-verification-screenshot.svg")

    assert evidence.exists()
    assert screenshot.exists()

    content = evidence.read_text(encoding="utf-8")
    assert "app/index.html" in content
    assert "python -m http.server 8000" in content
    assert "http://127.0.0.1:8000/app/index.html" in content
    assert "pdf_primary_mixed_bundle.json" in content
    assert "0.7809" in content
    assert "live-verification-screenshot.svg" in content
