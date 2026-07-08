from __future__ import annotations

from frontend_verify import run_frontend_verifier


def test_graphics_gallery_deliberate_break_detects_unbound_click_handler() -> None:
    result = run_frontend_verifier(
        open_first_graphic=True,
        graphic_click_handler_enabled=False,
    )

    assert result.has_node(role="button", name="Open graphic")
    assert not result.has_node(role="cell", name="Status", value="Opened")
