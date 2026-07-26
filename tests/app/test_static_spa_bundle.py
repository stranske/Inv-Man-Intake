from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "inv_man_intake"


def _bundled_modules() -> tuple[str, ...]:
    script = (ROOT / "app" / "static_operator_app.js").read_text(encoding="utf-8")
    block = re.search(r"const PRODUCTION_PACKET_MODULES = \[(.*?)\];", script, re.DOTALL)
    assert block is not None, "PRODUCTION_PACKET_MODULES array not found"
    return tuple(re.findall(r'"([^"]+)"', block.group(1)))


def _eager_package_imports(source: str) -> set[str]:
    """Return inv_man_intake modules imported when ``source`` is executed.

    Function-scoped and ``TYPE_CHECKING`` imports are excluded: they do not run
    when the browser bundle imports the module.
    """

    tree = ast.parse(source)
    skipped: set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or (
            isinstance(node, ast.If) and "TYPE_CHECKING" in ast.dump(node.test)
        ):
            skipped.update(ast.walk(node))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if node in skipped:
            continue
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("inv_man_intake"):
            modules.add(node.module or "")
        elif isinstance(node, ast.Import):
            modules.update(
                alias.name for alias in node.names if alias.name.startswith("inv_man_intake")
            )
    return modules


def _relative_path(module: str) -> str:
    parts = module.split(".")[1:]
    candidate = PACKAGE_ROOT.joinpath(*parts).with_suffix(".py")
    assert candidate.is_file(), f"{module} does not resolve to a bundleable module file"
    return "/".join(parts) + ".py"


def _required_bundle_closure() -> set[str]:
    pending = [
        _relative_path(module)
        for module in _eager_package_imports(
            (ROOT / "app" / "pyodide_packet_bridge.py").read_text(encoding="utf-8")
        )
    ]
    required: set[str] = set()
    while pending:
        current = pending.pop()
        if current in required:
            continue
        required.add(current)
        source = (PACKAGE_ROOT / current).read_text(encoding="utf-8")
        pending.extend(_relative_path(module) for module in _eager_package_imports(source))
    return required


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


def test_static_spa_bundles_cross_check_dependency_closure() -> None:
    """The production packet bundle includes lazy cross-check imports."""

    script = (ROOT / "app" / "static_operator_app.js").read_text(encoding="utf-8")

    assert '"extraction/cross_check.py"' in script
    assert '"performance/contracts.py"' in script
    assert '"performance/conflict_resolver.py"' in script


def test_static_spa_bundles_every_eagerly_imported_bridge_dependency() -> None:
    """A module the bridge imports at run time must be fetched into the Pyodide FS.

    The bundle materializes individual module files without package ``__init__``
    files, so a missing entry raises ``ModuleNotFoundError`` and silently drops
    the operator into the fallback packet view.
    """

    missing = sorted(_required_bundle_closure() - set(_bundled_modules()))

    assert not missing, f"PRODUCTION_PACKET_MODULES is missing {missing}"


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
    assert profile["one_pager"] is not None
    assert profile["outbound_calls"] == 0


def test_fallback_never_returns_a_fabricated_one_pager() -> None:
    bridge_path = ROOT / "app" / "pyodide_packet_bridge.py"
    spec = importlib.util.spec_from_file_location("pyodide_packet_bridge_fallback", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._fallback_packet_view([{"filename": "arbitrary.txt"}])["one_pager"] is None
