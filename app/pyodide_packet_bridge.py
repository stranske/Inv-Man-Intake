"""Browser-local packet bridge for the static operator SPA.

The production Python package is still the source of truth. This bridge keeps
the browser bundle deterministic and outbound-free while the full Pyodide
package packaging path is hardened by follow-up Gate 1/Gate 2 work.
"""

from __future__ import annotations

from typing import Any


def run_packet(files: list[dict[str, str]]) -> dict[str, Any]:
    """Return the packet view consumed by the static SPA."""

    uploaded = files or [
        {
            "document_id": "upload_1",
            "filename": "pdf_primary_mixed_bundle.json",
            "text": "Summit Arc Capital seeded packet.",
        }
    ]
    coverage = [
        {
            "document": file.get("document_id", f"upload_{index + 1}"),
            "type": _document_type(file.get("filename", "")),
            "coverage": "manager, fees, returns, graphics",
        }
        for index, file in enumerate(uploaded)
    ]
    return {
        "manager_profile": {
            "Manager": "Summit Arc Capital",
            "Final score": "0.7809",
            "Explainability": "risk_adjusted_returns, operational_quality, transparency",
            "Provenance": "fixture:pdf_primary_mixed_bundle.json",
        },
        "coverage": coverage,
        "graphics": [
            {"graphic": "drawdown-chart", "status": "Ready"},
            {"graphic": "strategy-exposure", "status": "Ready"},
        ],
        "returns": [
            {"period": "1Y", "return": "8.4%", "source": "manager deck"},
            {"period": "3Y", "return": "11.2%", "source": "track record"},
        ],
        "queue": [
            {
                "item": "performance_conflict",
                "reason": "mixed-source return variance",
                "owner": "analyst",
            }
        ],
        "assistant_answer": (
            "Apply manually: review performance_conflict before promotion; citations "
            "packet:upload_1 and graphic:drawdown-chart."
        ),
        "outbound_calls": 0,
    }


def _document_type(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pptx"):
        return "pitch_deck"
    if name.endswith(".xlsx"):
        return "track_record"
    if name.endswith(".json"):
        return "fixture_packet"
    return "uploaded_document"
