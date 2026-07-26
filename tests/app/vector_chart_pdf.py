"""Shared PDF fixture for offline vector-figure browser coverage."""

from __future__ import annotations


def build_vector_chart_pdf() -> bytes:
    """Build a compact PDF with two overlapping filled bars for browser rendering.

    The bars use distinct RGB fills and intersect so ``pathBounds`` merges them into
    one region. A solid single-color crop would make ``colors > 1`` fail even when
    rendering succeeded (post-merge CI failure on #861); multi-color content is the
    intentional gate against blank/uniform canvases.
    """

    # Blue bar + overlapping red bar (distinct fills; merged region is multi-color).
    stream = (
        b"q "
        b"0.1 0.4 0.8 rg 120 180 200 190 re f "
        b"0.9 0.2 0.1 rg 220 220 180 150 re f "
        b"Q\n"
    )
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(value)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    document.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    document.extend(
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return bytes(document)
