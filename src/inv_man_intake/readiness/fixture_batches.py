"""Shared fixture batch metadata for demo and readiness entrypoints."""

from __future__ import annotations

from typing import TypedDict


class FixtureBatchPackage(TypedDict):
    intake_bundle_file: str
    package_id: str
    expected_document_ids: tuple[str, ...]


DEFAULT_BATCH_PACKAGES: tuple[FixtureBatchPackage, ...] = (
    {
        "intake_bundle_file": "pdf_primary_mixed_bundle.json",
        "package_id": "pkg_pdf_mixed_001",
        "expected_document_ids": (
            "pkg_pdf_mixed_001:doc:0",
            "pkg_pdf_mixed_001:doc:1",
            "pkg_pdf_mixed_001:doc:2",
            "pkg_pdf_mixed_001:doc:3",
        ),
    },
    {
        "intake_bundle_file": "pptx_primary_mixed_bundle.json",
        "package_id": "pkg_pptx_mixed_001",
        "expected_document_ids": (
            "pkg_pptx_mixed_001:doc:0",
            "pkg_pptx_mixed_001:doc:1",
            "pkg_pptx_mixed_001:doc:2",
        ),
    },
)
