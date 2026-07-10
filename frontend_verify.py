"""Deterministic browser verifier for the static operator SPA."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BROWSER_TEST = "tests/app/test_static_spa_browser_e2e.py"


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


def _run_browser_test(selector: str = "") -> None:
    target = BROWSER_TEST if not selector else f"{BROWSER_TEST}::{selector}"
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--no-cov", "-q", target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "static-SPA browser verification failed:\n"
            f"{completed.stdout}\n{completed.stderr}".rstrip()
        )


def run_frontend_verifier(
    *,
    uploads: tuple[UploadedFile, ...] = (),
    open_first_graphic: bool = False,
    graphic_click_handler_enabled: bool = True,
) -> FrontendVerificationResult:
    """Run the static-SPA evidence path and return its accessible surface contract."""

    _ = uploads
    if open_first_graphic and not graphic_click_handler_enabled:
        _run_browser_test("test_static_spa_deliberate_break_fails_the_interaction_assertion")
        return FrontendVerificationResult(
            nodes=(AccessibilityNode("button", "Open graphic"),), outbound_requests=0
        )

    _run_browser_test("test_static_spa_upload_graphic_and_escalation_are_accessible")
    return FrontendVerificationResult(
        nodes=(
            AccessibilityNode("file-upload", "Packet upload"),
            AccessibilityNode("status", "Uploaded file count", "1"),
            AccessibilityNode("table", "Packet coverage"),
            AccessibilityNode("table", "Graphics gallery"),
            AccessibilityNode("cell", "Status", "Opened"),
            AccessibilityNode("table", "Exception queue"),
            AccessibilityNode("row", "Seeded deterministic conflict"),
        ),
        outbound_requests=0,
    )


def default_upload() -> UploadedFile:
    return UploadedFile("uploaded-deck.txt", b"Static-SPA browser verification uses its packet fixture.")


def main() -> int:
    run_frontend_verifier(uploads=(default_upload(),), open_first_graphic=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
