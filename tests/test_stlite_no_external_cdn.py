from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "index.html"
APP_PYPI = REPO_ROOT / "app" / "pypi"
STLITE_VENDOR = REPO_ROOT / "app" / "vendor" / "stlite@0.75.0"
PYODIDE_VENDOR = REPO_ROOT / "app" / "vendor" / "pyodide@0.26.2"


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
        '<script src="./vendor/stlite@0.75.0/stlite.js"></script>' in index_html
    ), "index.html must load the vendored stlite runtime"
    assert re.search(
        r"""pyodideUrl:\s*(?:new URL\()?["']\./vendor/pyodide@0\.26\.2/pyodide\.js["']""",
        index_html,
    ), "pyodideUrl must point at the local ./vendor pyodide runtime"


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


def test_vendored_stlite_runtime_and_wheels_exist() -> None:
    stlite_js = STLITE_VENDOR / "stlite.js"
    assert stlite_js.is_file(), f"Missing vendored stlite runtime: {stlite_js}"
    assert stlite_js.stat().st_size > 0, f"Vendored stlite runtime is empty: {stlite_js}"

    for pattern in ["streamlit-*.whl", "stlite_lib-*.whl"]:
        matches = list((STLITE_VENDOR / "pypi").glob(pattern))
        assert matches, f"Missing vendored stlite wheel matching {pattern}"
        assert all(
            path.stat().st_size > 0 for path in matches
        ), f"Vendored stlite wheel matching {pattern} must be non-empty"


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


def test_stlite_manifest_entries_exist() -> None:
    manifest_path = STLITE_VENDOR / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    missing = [
        rel_path
        for rel_path in manifest["files"].values()
        if not (STLITE_VENDOR / rel_path.removeprefix("./")).exists()
    ]

    assert not missing, f"Missing vendored stlite assets: {missing}"


def test_vendored_worker_has_local_pyodide_fallback() -> None:
    worker_path = STLITE_VENDOR / "static" / "js" / "3209.4faed50e.chunk.js"
    worker_source = worker_path.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/pyodide" not in worker_source
    assert "../../../pyodide@0.26.2/pyodide.js" in worker_source
