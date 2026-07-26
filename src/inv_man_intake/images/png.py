"""Stdlib-only PNG encoding for PDF ``/FlateDecode`` image XObjects.

Pillow and every other native imaging dependency are deliberately excluded so
the core import graph stays Pyodide-clean; ``zlib`` and ``struct`` are enough
because PDF's ``/Predictor >= 10`` filtering is byte-for-byte PNG filtering.
"""

from __future__ import annotations

import struct
import zlib

from inv_man_intake.images.models import ImageGeometry

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_COLOR_TYPE_GRAY = 0
_COLOR_TYPE_RGB = 2
_COLOR_TYPE_INDEXED = 3

_VALID_BIT_DEPTHS = {
    _COLOR_TYPE_GRAY: frozenset({1, 2, 4, 8, 16}),
    _COLOR_TYPE_RGB: frozenset({8, 16}),
    _COLOR_TYPE_INDEXED: frozenset({1, 2, 4, 8}),
}


class PngEncodeError(ValueError):
    """Raised when the XObject geometry cannot describe a valid PNG."""


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def _color_type_for(geometry: ImageGeometry) -> int:
    color_space = (geometry.color_space or "").casefold()
    if color_space == "indexed":
        return _COLOR_TYPE_INDEXED
    if geometry.color_components == 1:
        return _COLOR_TYPE_GRAY
    if geometry.color_components == 3:
        return _COLOR_TYPE_RGB
    raise PngEncodeError(f"unsupported colour geometry: {geometry.color_space!r}")


def _row_stride(*, width: int, components: int, bit_depth: int) -> int:
    return (width * components * bit_depth + 7) // 8


def encode_png(
    *,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    scanlines: bytes,
    palette: bytes | None = None,
) -> bytes:
    """Assemble a PNG from already-filtered scanlines (one filter byte per row)."""

    if width <= 0 or height <= 0:
        raise PngEncodeError("image dimensions must be positive")
    if bit_depth not in _VALID_BIT_DEPTHS.get(color_type, frozenset()):
        raise PngEncodeError(f"bit depth {bit_depth} is invalid for colour type {color_type}")
    if color_type == _COLOR_TYPE_INDEXED and not palette:
        raise PngEncodeError("indexed images require a palette")

    header = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    chunks = [_PNG_MAGIC, _chunk(b"IHDR", header)]
    if palette:
        chunks.append(_chunk(b"PLTE", palette))
    chunks.append(_chunk(b"IDAT", zlib.compress(scanlines, 9)))
    chunks.append(_chunk(b"IEND", b""))
    return b"".join(chunks)


def rebuild_flate_raster_to_png(stream: bytes, geometry: ImageGeometry) -> bytes:
    """Rebuild a PDF ``/FlateDecode`` sample stream into a viewable PNG.

    A ``/Predictor >= 10`` stream already carries PNG per-scanline filter bytes,
    so its inflated bytes map straight onto the IDAT payload. Unpredicted
    streams are raw samples and need a zero filter byte prepended per row.
    """

    if not geometry.is_complete:
        raise PngEncodeError("incomplete XObject geometry")

    width = geometry.width
    height = geometry.height
    bit_depth = geometry.bits_per_component
    components = geometry.color_components
    if width is None or height is None or bit_depth is None or components is None:
        raise PngEncodeError("incomplete XObject geometry")

    color_type = _color_type_for(geometry)
    try:
        samples = zlib.decompress(stream)
    except zlib.error as exc:
        raise PngEncodeError(f"stream is not valid zlib data: {exc}") from exc

    stride = _row_stride(width=width, components=components, bit_depth=bit_depth)
    predictor = geometry.predictor or 1

    if predictor >= 10:
        expected = (stride + 1) * height
        if len(samples) != expected:
            raise PngEncodeError(f"predicted stream is {len(samples)} bytes, expected {expected}")
        scanlines = samples
    else:
        expected = stride * height
        if len(samples) != expected:
            raise PngEncodeError(f"sample stream is {len(samples)} bytes, expected {expected}")
        scanlines = b"".join(
            b"\x00" + samples[row * stride : (row + 1) * stride] for row in range(height)
        )

    return encode_png(
        width=width,
        height=height,
        bit_depth=bit_depth,
        color_type=color_type,
        scanlines=scanlines,
        palette=geometry.palette,
    )


__all__ = ["PngEncodeError", "encode_png", "rebuild_flate_raster_to_png"]
