"""A PNG encoder and a header reader, in terms of nothing but ``zlib``.

WHY hand-rolled: the only raster this package needs to produce is the
loading screen of Section 6.1 -- 8-bit truecolour, no alpha, no interlace,
which is exactly what the mod tools' own template images are (their IHDR
reads ``08 02 00 00 00``: bit depth 8, colour type 2, no interlace). An
encoder for that one shape is forty lines and no dependency, and a tools
install that cannot ``pip install`` a native imaging library can still make a
map that looks finished.

The decoder is deliberately partial: it reads back only what
:func:`encode_png` writes, because its job is to let the tests and
:mod:`zmforge.verify` inspect our own output rather than to be a general
image library.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from ..errors import ForgeError

__all__ = [
    "SIGNATURE",
    "ImageError",
    "PngHeader",
    "encode_png",
    "read_png_header",
    "decode_png",
]

#: The eight bytes every PNG starts with.
SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: What the mod tools' template images are, and so what we emit.
BIT_DEPTH = 8
COLOUR_TYPE_RGB = 2


class ImageError(ForgeError):
    """A raster could not be encoded, or a file is not a PNG we understand."""


@dataclass(frozen=True, slots=True)
class PngHeader:
    """An IHDR, as far as anything here cares about it."""

    width: int
    height: int
    bit_depth: int
    colour_type: int
    interlace: int

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + kind + payload + crc.to_bytes(4, "big")


def encode_png(width: int, height: int, pixels: bytes, *, level: int = 6) -> bytes:
    """Encode ``width * height * 3`` bytes of RGB as a PNG file.

    Every scanline is written with filter type 0 (none): the images this
    package makes are flat colour fields, where a filter buys little and
    costs a pass over six megabytes of pixels.
    """
    if width <= 0 or height <= 0:
        raise ImageError(f"a PNG needs positive dimensions, got {width}x{height}")
    stride = width * 3
    if len(pixels) != stride * height:
        raise ImageError(
            f"{width}x{height} RGB needs {stride * height} bytes, got {len(pixels)}"
        )
    raw = bytearray()
    for start in range(0, stride * height, stride):
        raw.append(0)
        raw += pixels[start : start + stride]
    header = struct.pack(
        ">IIBBBBB", width, height, BIT_DEPTH, COLOUR_TYPE_RGB, 0, 0, 0
    )
    return b"".join(
        (
            SIGNATURE,
            _chunk(b"IHDR", header),
            _chunk(b"IDAT", zlib.compress(bytes(raw), level)),
            _chunk(b"IEND", b""),
        )
    )


def read_png_header(data: bytes) -> PngHeader:
    """The IHDR of *data*, or :class:`ImageError` if it is not a PNG."""
    if not data.startswith(SIGNATURE):
        raise ImageError("not a PNG: the eight-byte signature is missing")
    if len(data) < 33:
        raise ImageError("truncated PNG: no room for an IHDR")
    length = int.from_bytes(data[8:12], "big")
    if data[12:16] != b"IHDR" or length != 13:
        raise ImageError("malformed PNG: the first chunk is not a 13-byte IHDR")
    width, height, depth, colour, _compression, _filter, interlace = struct.unpack(
        ">IIBBBBB", data[16:29]
    )
    return PngHeader(width, height, depth, colour, interlace)


def decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Read back an unfiltered 8-bit RGB PNG: ``(width, height, pixels)``.

    Only the subset :func:`encode_png` writes is supported; anything else
    raises rather than guessing.
    """
    header = read_png_header(data)
    if (header.bit_depth, header.colour_type, header.interlace) != (
        BIT_DEPTH,
        COLOUR_TYPE_RGB,
        0,
    ):
        raise ImageError(
            "decode_png reads 8-bit non-interlaced RGB only, not "
            f"depth {header.bit_depth} colour type {header.colour_type}"
        )
    compressed = bytearray()
    offset = 8
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        if kind == b"IDAT":
            compressed += payload
        elif kind == b"IEND":
            break
        offset += 12 + length
    raw = zlib.decompress(bytes(compressed))
    stride = header.width * 3
    pixels = bytearray()
    for row in range(header.height):
        start = row * (stride + 1)
        if raw[start] != 0:
            raise ImageError(f"scanline {row} uses filter {raw[start]}, only 0 is read")
        pixels += raw[start + 1 : start + 1 + stride]
    if len(pixels) != stride * header.height:
        raise ImageError("truncated image data")
    return header.width, header.height, bytes(pixels)
