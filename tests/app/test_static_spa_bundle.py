from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_static_spa_replaces_stlite_mount() -> None:
    index = (ROOT / "app" / "index.html").read_text(encoding="utf-8")

    assert 'data-app-runtime="static-spa-pyodide"' in index
    assert "./vendor/pyodide@0.26.2/pyodide.js" in index
    assert "static_operator_app.js" in index
    assert "stlite.mount" not in index
    assert "vendor/stlite" not in index
    assert "streamlit_app.py" not in index


def test_static_spa_exposes_operator_surfaces() -> None:
    index = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static_operator_app.js").read_text(encoding="utf-8")

    for required_text in (
        "Packet upload",
        "Packet coverage",
        "Manager profile",
        "Graphics gallery",
        "Return stream",
        "Exception queue",
        "Assistant panel",
    ):
        assert required_text in index

    assert "loadPyodide" in script
    assert "pyodide_packet_bridge.py" in script
    assert "Deterministic outbound calls" in script


def test_pyodide_bridge_keeps_parity_seed_data() -> None:
    bridge = (ROOT / "app" / "pyodide_packet_bridge.py").read_text(encoding="utf-8")

    assert "def run_packet" in bridge
    assert "Final score" in bridge
    assert "0.7809" in bridge
    assert "performance_conflict" in bridge
    assert "outbound_calls" in bridge
