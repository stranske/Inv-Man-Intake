from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_static_spa_replaces_stlite_mount() -> None:
    index = (ROOT / "app" / "index.html").read_text(encoding="utf-8")

    assert 'data-app-runtime="static-spa-pyodide"' in index
    assert '<script src="./vendor/pyodide@0.26.2/pyodide.js"></script>' in index
    assert '<script type="module" src="./static_operator_app.js"></script>' in index
    assert (ROOT / "app" / "static_operator_app.js").is_file()
    assert (ROOT / "app" / "vendor" / "pyodide@0.26.2" / "pyodide.js").is_file()
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
    assert "state.pyodide.toPy(payload)" in script
    assert "pyodideInit: null" in script
    assert "await state.pyodideInit" in script
    assert "state.pyodideInit = null" in script
    assert "bridgeResponse.ok" in script
    assert "Deterministic outbound calls" in script


def test_pyodide_bridge_runs_packet_pipeline_for_seed_data() -> None:
    bridge_path = ROOT / "app" / "pyodide_packet_bridge.py"
    bridge = bridge_path.read_text(encoding="utf-8")

    assert "def run_packet" in bridge
    assert "_ingest_packet(" in bridge
    assert "_fallback_packet_view" in bridge
    assert "outbound_calls" in bridge

    spec = importlib.util.spec_from_file_location("pyodide_packet_bridge", bridge_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    profile = module.run_packet(
        [
            {
                "document_id": "upload_1",
                "filename": "deck.txt",
                "text": "Summit Arc Capital deck with AUM 100, return history, and fee terms.",
            }
        ]
    )

    assert profile["manager_profile"]["Manager"] == "Summit Arc Capital"
    assert profile["manager_profile"]["Provenance"].startswith("upload_1:")
    assert profile["coverage"][0]["document"] == "upload_1"
    assert profile["outbound_calls"] == 0
