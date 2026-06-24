from __future__ import annotations

from collections.abc import Callable

from app.streamlit_app import FIXTURE_OPTIONS, render_app


class _PresentationRecorder:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.selectboxes: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        self.success_messages: list[str] = []
        self.write_calls: list[tuple[object, ...]] = []
        self.session_state: dict[str, object] = {}

    def set_page_config(self, **kwargs: object) -> None:
        return None

    def title(self, body: str) -> None:
        return None

    def caption(self, body: str) -> None:
        self.captions.append(body)

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
        return None

    def subheader(self, body: str) -> None:
        return None

    def table(self, data: object) -> None:
        return None

    def button(self, label: str, *, key: str) -> bool:
        return False

    def write(self, *args: object, **kwargs: object) -> None:
        self.write_calls.append(args)

    def success(self, body: str) -> None:
        self.success_messages.append(body)


def test_fixture_selector_uses_friendly_labels_and_selected_description() -> None:
    recorder = _PresentationRecorder()

    render_app(recorder)

    assert recorder.selectboxes == [
        (
            "Synthetic intake bundle",
            FIXTURE_OPTIONS,
            (
                "Mixed-source PDF intake sample",
                "Mixed presentation intake sample",
            ),
        )
    ]
    _, backing_options, display_options = recorder.selectboxes[0]
    assert set(backing_options) == {
        "pdf_primary_mixed_bundle.json",
        "pptx_primary_mixed_bundle.json",
    }
    assert all(not option.endswith(".json") for option in display_options)
    assert any(
        "PDF-led sample package with mixed evidence" in caption
        and "Backing fixture: `pdf_primary_mixed_bundle.json`." in caption
        for caption in recorder.captions
    )


def test_trace_sink_observability_details_are_not_rendered_in_main_content() -> None:
    recorder = _PresentationRecorder()

    render_app(recorder)

    rendered_main_content = " ".join(
        [
            *recorder.success_messages,
            *(" ".join(map(str, call)) for call in recorder.write_calls),
        ]
    )
    assert "Trace sink:" not in rendered_main_content
    assert "LangSmith and LangChain tracing env vars are off" not in rendered_main_content
