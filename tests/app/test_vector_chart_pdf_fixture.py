"""Non-browser gate for the multi-color vector chart PDF fixture."""

from __future__ import annotations

from tests.app.vector_chart_pdf import build_vector_chart_pdf


def test_vector_chart_pdf_fixture_encodes_two_distinct_fills() -> None:
    """Fixture must stay multi-color so the browser colors>1 gate remains meaningful."""

    pdf = build_vector_chart_pdf()
    assert b"0.1 0.4 0.8 rg" in pdf
    assert b"0.9 0.2 0.1 rg" in pdf
    # Deliberate break: reverting to a single solid fill makes this fail.
    assert pdf.count(b" re f ") >= 2
