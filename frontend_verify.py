"""Deterministic frontend verifier for the operator packet surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.streamlit_app import (
    OPERATOR_GRAPHIC_STATE_KEY,
    render_operator_packet,
)


@dataclass(frozen=True)
class AccessibilityNode:
    role: str
    name: str
    value: str = ""


@dataclass(frozen=True)
class FrontendVerificationResult:
    nodes: tuple[AccessibilityNode, ...]
    outbound_requests: int

    def names(self) -> tuple[str, ...]:
        return tuple(node.name for node in self.nodes)

    def has_node(self, *, role: str, name: str, value: str | None = None) -> bool:
        return any(
            node.role == role and node.name == name and (value is None or node.value == value)
            for node in self.nodes
        )


class UploadedFile:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


class StreamlitRecorder:
    def __init__(
        self,
        *,
        uploads: tuple[UploadedFile, ...] = (),
        clicked_buttons: set[str] | None = None,
        graphic_click_handler_enabled: bool = True,
    ) -> None:
        self._nodes: list[AccessibilityNode] = []
        self._uploads = uploads
        self._clicked_buttons = clicked_buttons or set()
        self._graphic_click_handler_enabled = graphic_click_handler_enabled
        self._session_state: dict[str, object] = {}

    @property
    def session_state(self) -> dict[str, object]:
        return self._session_state

    @property
    def nodes(self) -> tuple[AccessibilityNode, ...]:
        return tuple(self._nodes)

    def set_page_config(self, **kwargs: Any) -> None:
        self._nodes.append(AccessibilityNode("document", "page-config", repr(sorted(kwargs))))

    def title(self, body: str) -> None:
        self._nodes.append(AccessibilityNode("heading", body))

    def caption(self, body: str) -> None:
        self._nodes.append(AccessibilityNode("note", body))

    def selectbox(
        self,
        label: str,
        options: tuple[str, ...],
        *,
        format_func: Any = None,
    ) -> str:
        selected = options[0]
        label_value = format_func(selected) if format_func else selected
        self._nodes.append(AccessibilityNode("combobox", label, str(label_value)))
        return selected

    def metric(self, label: str, value: str) -> None:
        self._nodes.append(AccessibilityNode("status", label, value))

    def subheader(self, body: str) -> None:
        self._nodes.append(AccessibilityNode("heading", body))

    def table(self, data: object) -> None:
        rows = list(data) if isinstance(data, list) else [data]
        for row in rows:
            if isinstance(row, dict):
                for key, value in row.items():
                    self._nodes.append(AccessibilityNode("cell", str(key), str(value)))
            else:
                self._nodes.append(AccessibilityNode("cell", "table-row", str(row)))

    def button(self, label: str, *, key: str) -> bool:
        self._nodes.append(AccessibilityNode("button", label, key))
        if key.startswith("open-graphic:") and not self._graphic_click_handler_enabled:
            return False
        if key.startswith("open-graphic:") and "__all_open_graphics__" in self._clicked_buttons:
            return True
        return key in self._clicked_buttons

    def write(self, *args: object, **kwargs: object) -> None:
        _ = kwargs
        self._nodes.append(AccessibilityNode("text", "write", " ".join(map(str, args))))

    def success(self, body: str) -> None:
        self._nodes.append(AccessibilityNode("status", "success", body))

    def file_uploader(self, label: str, **kwargs: Any) -> tuple[UploadedFile, ...]:
        self._nodes.append(AccessibilityNode("file-upload", label, repr(sorted(kwargs))))
        if self._uploads:
            self._nodes.append(
                AccessibilityNode("status", "Uploaded file count", str(len(self._uploads)))
            )
        return self._uploads


def run_frontend_verifier(
    *,
    uploads: tuple[UploadedFile, ...] = (),
    open_first_graphic: bool = False,
    graphic_click_handler_enabled: bool = True,
) -> FrontendVerificationResult:
    clicked_buttons = {"__all_open_graphics__"} if open_first_graphic else set()
    recorder = StreamlitRecorder(
        uploads=uploads,
        clicked_buttons=clicked_buttons,
        graphic_click_handler_enabled=graphic_click_handler_enabled,
    )
    view = render_operator_packet(recorder, use_real_streamlit=True)
    if open_first_graphic and graphic_click_handler_enabled:
        state = recorder.session_state.get(OPERATOR_GRAPHIC_STATE_KEY)
        assert isinstance(state, dict)
    return FrontendVerificationResult(
        nodes=recorder.nodes,
        outbound_requests=view.outbound_calls,
    )


def default_upload() -> UploadedFile:
    return UploadedFile(
        "uploaded-deck.txt",
        (
            b"Uploaded Summit Arc investor deck. Manager: Summit Arc Capital. "
            b"AUM $101.0M. Management fee 1.25%. Graphic: drawdown chart."
        ),
    )


def main() -> int:
    result = run_frontend_verifier(uploads=(default_upload(),), open_first_graphic=True)
    if result.outbound_requests != 0:
        raise SystemExit("frontend verifier attempted outbound requests")
    required = {
        "Packet upload",
        "Uploaded file count",
        "Packet coverage",
        "Graphics gallery",
        "Return stream",
        "Exception queue",
    }
    missing = required.difference(result.names())
    if missing:
        raise SystemExit(f"frontend verifier missing nodes: {', '.join(sorted(missing))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
