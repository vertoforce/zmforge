"""Raster output: a PNG encoder, a drawing surface and a bitmap font.

This layer knows nothing about maps. It exists because the mod tools take a
usermap's loading screen as a plain ``.png`` on disk (Section 6.1), so the
generator has to be able to write one without an imaging dependency on the
machine that runs the mod tools.
"""

from __future__ import annotations

from .glyphs import GLYPH_HEIGHT, GLYPH_WIDTH, glyph_for
from .png import (
    ImageError,
    PngHeader,
    SIGNATURE,
    decode_png,
    encode_png,
    read_png_header,
)
from .raster import Colour, Raster, blend

__all__ = [
    "Colour",
    "Raster",
    "blend",
    "ImageError",
    "PngHeader",
    "SIGNATURE",
    "encode_png",
    "decode_png",
    "read_png_header",
    "GLYPH_WIDTH",
    "GLYPH_HEIGHT",
    "glyph_for",
]
