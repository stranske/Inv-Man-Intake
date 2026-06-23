from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "index.html"
APP_PYPI = REPO_ROOT / "app" / "pypi"
STLITE_VENDOR = REPO_ROOT / "app" / "vendor" / "stlite@0.75.0"
PYODIDE_VENDOR = REPO_ROOT / "app" / "vendor" / "pyodide@0.26.2"


def test_index_has_no_external_runtime_ref() -> None:
    index_html = INDEX_HTML.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net" not in index_html
    assert not re.search(r"https?://", index_html)
    assert '<script src="./vendor/stlite@0.75.0/stlite.js"></script>' in index_html
    assert 'pyodideUrl: "./vendor/pyodide@0.26.2/pyodide.js"' in index_html


def test_local_stlite_pyodide_and_wheels_are_committed() -> None:
    assert (STLITE_VENDOR / "stlite.js").is_file()
    assert (STLITE_VENDOR / "static" / "js").is_dir()
    assert (PYODIDE_VENDOR / "pyodide.js").is_file()
    assert (PYODIDE_VENDOR / "pyodide.asm.wasm").is_file()
    assert (PYODIDE_VENDOR / "python_stdlib.zip").is_file()

    app_wheels = {path.name for path in APP_PYPI.glob("*.whl")}
    vendor_wheels = {path.name for path in (STLITE_VENDOR / "pypi").glob("*.whl")}

    assert "stlite_lib-0.1.0-py3-none-any.whl" in app_wheels
    assert "streamlit-1.40.1-cp312-none-any.whl" in app_wheels
    assert app_wheels == vendor_wheels
