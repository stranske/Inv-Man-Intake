from __future__ import annotations

from frontend_verify import default_upload, run_frontend_verifier


def test_frontend_verifier_upload_and_mvp_interactions_are_accessible() -> None:
    result = run_frontend_verifier(uploads=(default_upload(),), open_first_graphic=True)

    assert result.outbound_requests == 0
    assert result.has_node(role="file-upload", name="Packet upload")
    assert result.has_node(role="status", name="Uploaded file count", value="1")
    assert result.has_node(role="heading", name="Packet coverage")
    assert result.has_node(role="heading", name="Graphics gallery")
    assert result.has_node(role="button", name="Open graphic")
    assert result.has_node(role="cell", name="Status", value="Opened")
    assert result.has_node(role="heading", name="Return stream")
    assert result.has_node(role="heading", name="Exception queue")


def test_frontend_verifier_exposes_concrete_ui_state_per_interaction() -> None:
    result = run_frontend_verifier(uploads=(default_upload(),), open_first_graphic=False)

    assert result.has_node(role="cell", name="Document", value="upload_1")
    assert result.has_node(role="cell", name="Type")
    assert result.has_node(role="cell", name="Deterministic outbound calls", value="0")
    assert "Manager profile" in result.names()
