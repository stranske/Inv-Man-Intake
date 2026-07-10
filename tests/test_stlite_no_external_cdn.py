from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "index.html"
DESIGN_SYSTEM = REPO_ROOT / "design-system"
PYODIDE_VENDOR = REPO_ROOT / "app" / "vendor" / "pyodide@0.26.2"


def _has_design_system_stylesheets(index_html: str) -> bool:
    return all(
        link in index_html
        for link in (
            '<link rel="stylesheet" href="../design-system/tokens.css" />',
            '<link rel="stylesheet" href="../design-system/components.css" />',
        )
    )


def test_index_has_no_external_runtime_ref() -> None:
    index_html = INDEX_HTML.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net" not in index_html, "index.html must not reference jsDelivr"
    assert not re.search(
        r"""<(?:script|link)\b[^>]+(?:src|href)=["']https?://""", index_html
    ), "index.html must not load external http(s) scripts or stylesheets"
    assert not re.search(
        r"""\bimport(?:\s*\(|\s+[^;]*?\s+from\s+)["']https?://""", index_html
    ), "index.html must not import external http(s) modules"
    assert (
        '<script src="./vendor/pyodide@0.26.2/pyodide.js"></script>' in index_html
    ), "index.html must load the vendored Pyodide runtime"
    assert (
        '<script type="module" src="./static_operator_app.js"></script>' in index_html
    ), "index.html must load the static SPA module locally"
    assert "vendor/stlite" not in index_html
    assert "stlite.mount" not in index_html


def test_design_system_stylesheets_present() -> None:
    index_html = INDEX_HTML.read_text(encoding="utf-8")

    assert _has_design_system_stylesheets(index_html)
    assert 'class="ds theme-air density-compact"' in index_html
    assert "../design-system/tokens.css" in index_html
    assert "../design-system/components.css" in index_html
    assert (DESIGN_SYSTEM / "tokens.css").is_file()
    assert (DESIGN_SYSTEM / "components.css").is_file()


def test_design_system_stylesheet_gate_fails_when_link_removed() -> None:
    index_html = INDEX_HTML.read_text(encoding="utf-8")

    assert (
        _has_design_system_stylesheets(
            index_html.replace(
                '<link rel="stylesheet" href="../design-system/tokens.css" />',
                "",
            )
        )
        is False
    )
    assert (
        _has_design_system_stylesheets(
            index_html.replace(
                '<link rel="stylesheet" href="../design-system/components.css" />',
                "",
            )
        )
        is False
    )


def test_vendored_pyodide_runtime_files_exist_and_are_non_empty() -> None:
    for relative_path in [
        "pyodide.js",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
    ]:
        path = PYODIDE_VENDOR / relative_path
        assert path.is_file(), f"Missing vendored Pyodide runtime file: {path}"
        assert path.stat().st_size > 0, f"Vendored Pyodide runtime file is empty: {path}"


def test_required_pyodide_wheels_are_vendored() -> None:
    for pattern in [
        "micropip-*.whl",
        "packaging-*.whl",
        "numpy-*.whl",
        "pandas-*.whl",
        "pillow-*.whl",
        "protobuf-*.whl",
    ]:
        matches = list(PYODIDE_VENDOR.glob(pattern))
        assert matches, f"Missing vendored Pyodide wheel matching {pattern}"
        assert all(
            path.stat().st_size > 0 for path in matches
        ), f"Vendored Pyodide wheel matching {pattern} must be non-empty"


def test_static_spa_runtime_files_exist() -> None:
    app_js = REPO_ROOT / "app" / "static_operator_app.js"
    bridge = REPO_ROOT / "app" / "pyodide_packet_bridge.py"

    assert app_js.is_file()
    assert bridge.is_file()
    assert app_js.stat().st_size > 0
    assert bridge.stat().st_size > 0
    assert (PYODIDE_VENDOR / "pyodide.js").is_file()
    assert (PYODIDE_VENDOR / "pyodide.asm.wasm").is_file()
    assert (PYODIDE_VENDOR / "python_stdlib.zip").is_file()


def test_static_spa_module_uses_local_pyodide_runtime() -> None:
    app_js = (REPO_ROOT / "app" / "static_operator_app.js").read_text(encoding="utf-8")

    assert 'const PYODIDE_RUNTIME = "./vendor/pyodide@0.26.2/";' in app_js
    assert "loadPyodide({ indexURL: PYODIDE_RUNTIME })" in app_js
    assert "https://" not in app_js
    assert "http://" not in app_js


def test_pyodide_bridge_has_no_network_or_streamlit_dependency() -> None:
    bridge = (REPO_ROOT / "app" / "pyodide_packet_bridge.py").read_text(encoding="utf-8")

    assert "def run_packet" in bridge
    assert "streamlit" not in bridge
    assert "requests" not in bridge
    assert "urllib" not in bridge
