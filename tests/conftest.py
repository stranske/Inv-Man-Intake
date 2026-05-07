"""Pytest runtime configuration shared across the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config: object) -> int:  # pragma: no cover - xdist hook
    """Stabilize CI runs when workflows invoke pytest with ``-n auto``.

    The reusable CI workflow enables xdist automatically. Returning ``1`` keeps
    behavior deterministic while still allowing the workflow to pass ``-n auto``.
    """

    return 1


_V1_SMOKE_FIXTURE_ROOT = Path("tests/fixtures/intake")
_V1_SMOKE_PACKAGE_ID = "pkg_pdf_mixed_001"
_V1_SMOKE_EXPECTED_DOCUMENT_IDS: tuple[str, ...] = (
    "pkg_pdf_mixed_001:doc:0",
    "pkg_pdf_mixed_001:doc:1",
    "pkg_pdf_mixed_001:doc:2",
    "pkg_pdf_mixed_001:doc:3",
)


@pytest.fixture(scope="session")
def v1_smoke_artifacts():
    """Run the v1 intake-to-scoring smoke pipeline once and share its output.

    Both ``tests/test_v1_acceptance_smoke.py`` and the queue contract tests in
    ``tests/queue/test_v1_smoke_state_transition.py`` need the same set of
    pipeline artifacts. Running the pipeline twice in the same session was
    pure cost; this fixture makes them share one execution.
    """

    from inv_man_intake.v1_smoke import run_v1_smoke_pipeline

    return run_v1_smoke_pipeline(
        fixture_root=_V1_SMOKE_FIXTURE_ROOT,
        package_id=_V1_SMOKE_PACKAGE_ID,
        expected_document_ids=_V1_SMOKE_EXPECTED_DOCUMENT_IDS,
    )
