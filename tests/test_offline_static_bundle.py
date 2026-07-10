from __future__ import annotations

from pathlib import Path

from scripts.verify_static_spa_pyodide import handle_offline_route, verify_offline_runtime

ROOT = Path(__file__).resolve().parents[1]


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = _FakeRequest(url)
        self.continued = False
        self.aborted = False

    def continue_(self) -> None:
        self.continued = True

    def abort(self) -> None:
        self.aborted = True


def test_offline_static_bundle_runtime_is_fully_local() -> None:
    result = verify_offline_runtime(ROOT)

    assert result.status == "pass"
    assert result.index_path == "app/index.html"
    assert result.pyodide_vendor.startswith("app/vendor/pyodide@")
    assert result.app_runtime == "static-spa-pyodide"
    assert "micropip" in result.dependency_closure


def test_offline_static_bundle_intercepts_outbound_requests() -> None:
    external_requests: list[str] = []
    local_route = _FakeRoute("http://127.0.0.1:8000/app/index.html")
    external_route = _FakeRoute("https://cdn.example.invalid/runtime.js")

    handle_offline_route(local_route, external_requests)
    handle_offline_route(external_route, external_requests)

    assert local_route.continued is True
    assert local_route.aborted is False
    assert external_route.continued is False
    assert external_route.aborted is True
    assert external_requests == ["https://cdn.example.invalid/runtime.js"]
