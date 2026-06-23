"""Regenerate the committed Pyodide wheel set used by the offline stlite demo.

The Pyodide wheels under app/vendor/pyodide@0.26.2 are committed so the browser
demo boots offline with zero network access. This script reads the committed
pyodide-lock.json, computes the dependency closure for the currently vendored
wheel set plus micropip and packaging, and downloads any missing lock files from
jsDelivr. Existing files are left untouched, making the script idempotent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import urlretrieve

PYODIDE_VERSION = "0.26.2"
PYODIDE_CDN_BASE = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full"


def canonical_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_closure(pyodide_vendor: Path) -> list[dict[str, object]]:
    lock_path = pyodide_vendor / "pyodide-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages", {})
    packages_by_name = {
        canonical_package_name(package.get("name", key)): package
        for key, package in packages.items()
    }
    local_wheels = {path.name for path in pyodide_vendor.glob("*.whl")}
    seed = {
        canonical_package_name(package.get("name", key))
        for key, package in packages.items()
        if package.get("file_name") in local_wheels
    }
    seed.update({canonical_package_name("micropip"), canonical_package_name("packaging")})

    closure: set[str] = set()
    stack = sorted(seed)
    while stack:
        package_name = stack.pop()
        if package_name in closure:
            continue
        closure.add(package_name)
        package = packages_by_name.get(package_name)
        if package is None:
            raise RuntimeError(f"Package {package_name} is missing from {lock_path}")
        for dependency in package.get("depends", []):
            canonical_dependency = canonical_package_name(dependency)
            if canonical_dependency not in closure:
                stack.append(canonical_dependency)

    return [packages_by_name[package_name] for package_name in sorted(closure)]


def fetch_missing_runtime(repo_root: Path) -> list[Path]:
    pyodide_vendor = repo_root / "app" / "vendor" / f"pyodide@{PYODIDE_VERSION}"
    pyodide_vendor.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for package in dependency_closure(pyodide_vendor):
        file_name = package.get("file_name")
        if not isinstance(file_name, str) or not file_name:
            continue
        destination = pyodide_vendor / file_name
        if destination.exists():
            print(f"skip existing {destination.relative_to(repo_root)}")
            continue
        source_url = f"{PYODIDE_CDN_BASE}/{file_name}"
        print(f"download {source_url} -> {destination.relative_to(repo_root)}")
        urlretrieve(source_url, destination)
        downloaded.append(destination)

    return downloaded


def main() -> int:
    repo_root = Path.cwd().resolve()
    downloaded = fetch_missing_runtime(repo_root)
    print(f"downloaded {len(downloaded)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
