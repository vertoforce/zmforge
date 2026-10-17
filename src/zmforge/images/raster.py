"""A mutable RGB raster with the handful of drawing operations a plan needs.

Everything is clipped, so a caller may draw off the edge without checking,
and every coordinate is in pixels with ``y`` growing downwards -- the
world-to-pixel flip belongs to :mod:`zmforge.emit.planview`, not here.

The representation is one ``bytearray`` of interleaved RGB, which is both
what :func:`~zmforge.images.png.encode_png` wants and fast to fill: a
horizontal run is one slice assignment.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .glyphs import GLYPH_HEIGHT, GLYPH_WIDTH, glyph_for
from .png import encode_png

__all__ = ["Colour", "Raster"]

#: An RGB triple, 0-255 per channel.
Colour = tuple[int, int, int]


def _clamp_channel(value: int) -> int:
    return 0 if value < 0 else (255 if value > 255 else int(value))


def _as_bytes(colour: Sequence[int]) -> bytes:
    if len(colour) != 3:
        raise ValueError(f"a colour is three channels, got {tuple(colour)!r}")
    return bytes(_clamp_channel(channel) for channel in colour)


def blend(under: Colour, over: Colour, weight: float) -> Colour:
    """*over* mixed onto *under* by ``weight`` in ``0..1``."""
    weight = 0.0 if weight < 0.0 else (1.0 if weight > 1.0 else weight)
    return tuple(  # type: ignore[return-value]
        int(round(a + (b - a) * weight)) for a, b in zip(under, over)
    )


class Raster:
    """A ``width * height`` RGB image, drawn on in place."""

    __slots__ = ("width", "height", "pixels")

    def __init__(self, width: int, height: int, background: Colour = (0, 0, 0)) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"a raster needs positive dimensions, got {width}x{height}")
        self.width = int(width)
        self.height = int(height)
        self.pixels = bytearray(_as_bytes(background) * (self.width * self.height))

    # -- reading ---------------------------------------------------------
    def pixel(self, x: int, y: int) -> Colour:
        """The colour at ``(x, y)``; raises outside the image."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"({x}, {y}) is outside {self.width}x{self.height}")
        at = (y * self.width + x) * 3
        return (self.pixels[at], self.pixels[at + 1], self.pixels[at + 2])

    # -- writing ---------------------------------------------------------
    def fill(self, colour: Colour) -> None:
        self.pixels[:] = _as_bytes(colour) * (self.width * self.height)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, colour: Colour) -> None:
        """Fill the half-open rectangle ``[x0, x1) x [y0, y1)``, clipped."""
        left, right = sorted((int(x0), int(x1)))
        top, bottom = sorted((int(y0), int(y1)))
        left, top = max(left, 0), max(top, 0)
        right, bottom = min(right, self.width), min(bottom, self.height)
        if left >= right or top >= bottom:
            return
        run = _as_bytes(colour) * (right - left)
        for y in range(top, bottom):
            start = (y * self.width + left) * 3
            self.pixels[start : start + len(run)] = run

    def outline_rect(
        self, x0: int, y0: int, x1: int, y1: int, colour: Colour, weight: int = 1
    ) -> None:
        """A rectangular frame drawn *inside* the given rectangle."""
        left, right = sorted((int(x0), int(x1)))
        top, bottom = sorted((int(y0), int(y1)))
        weight = max(1, int(weight))
        self.fill_rect(left, top, right, top + weight, colour)
        self.fill_rect(left, bottom - weight, right, bottom, colour)
        self.fill_rect(left, top, left + weight, bottom, colour)
        self.fill_rect(right - weight, top, right, bottom, colour)

    def dot(self, x: int, y: int, radius: int, colour: Colour) -> None:
        """A filled square of side ``2 * radius + 1`` centred on ``(x, y)``."""
        self.fill_rect(x - radius, y - radius, x + radius + 1, y + radius + 1, colour)

    def diamond(self, x: int, y: int, radius: int, colour: Colour) -> None:
        """A filled diamond, for markers that must read differently to dots."""
        radius = max(1, int(radius))
        for offset in range(-radius, radius + 1):
            span = radius - abs(offset)
            self.fill_rect(x - span, y + offset, x + span + 1, y + offset + 1, colour)

    def line(self, x0: int, y0: int, x1: int, y1: int, colour: Colour, weight: int = 1) -> None:
        """A Bresenham line; ``weight`` thickens it into squares."""
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        step_x = 1 if x1 >= x0 else -1
        step_y = 1 if y1 >= y0 else -1
        error = dx - dy
        radius = max(0, int(weight) - 1)
        while True:
            self.dot(x0, y0, radius, colour)
            if x0 == x1 and y0 == y1:
                return
            doubled = error * 2
            if doubled > -dy:
                error -= dy
                x0 += step_x
            if doubled < dx:
                error += dx
                y0 += step_y

    # -- text ------------------------------------------------------------
    def text(
        self,
        x: int,
        y: int,
        message: str,
        colour: Colour,
        *,
        scale: int = 1,
        spacing: int = 1,
    ) -> int:
        """Draw *message* with its top-left at ``(x, y)``; returns its width.

        ``scale`` multiplies the 5x7 cell, ``spacing`` is the gap between
        cells in unscaled columns.
        """
        scale = max(1, int(scale))
        step = (GLYPH_WIDTH + max(0, int(spacing))) * scale
        pen = int(x)
        for character in message:
            cell = glyph_for(character)
            for row, bits in enumerate(cell):
                top = int(y) + row * scale
                run_start: int | None = None
                for column in range(GLYPH_WIDTH + 1):
                    ink = column < GLYPH_WIDTH and bits[column] == "#"
                    if ink and run_start is None:
                        run_start = column
                    elif not ink and run_start is not None:
                        self.fill_rect(
                            pen + run_start * scale,
                            top,
                            pen + column * scale,
                            top + scale,
                            colour,
                        )
                        run_start = None
            pen += step
        return max(0, pen - int(x) - (max(0, int(spacing)) * scale))

    @staticmethod
    def text_width(message: str, *, scale: int = 1, spacing: int = 1) -> int:
        """How wide :meth:`text` would draw *message*."""
        if not message:
            return 0
        scale = max(1, int(scale))
        spacing = max(0, int(spacing))
        return len(message) * (GLYPH_WIDTH + spacing) * scale - spacing * scale

    @staticmethod
    def text_height(*, scale: int = 1) -> int:
        return GLYPH_HEIGHT * max(1, int(scale))

    # -- output ----------------------------------------------------------
    def to_png(self, *, level: int = 6) -> bytes:
        return encode_png(self.width, self.height, bytes(self.pixels), level=level)

    def rows(self) -> Iterable[bytes]:  # pragma: no cover - debugging aid
        stride = self.width * 3
        for start in range(0, stride * self.height, stride):
            yield bytes(self.pixels[start : start + stride])
