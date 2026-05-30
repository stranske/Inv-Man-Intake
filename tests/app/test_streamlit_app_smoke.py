from __future__ import annotations

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
