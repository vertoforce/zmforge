"""Brush lettering: words in the world as thin boxes, not decals.

A wall-art texture is not proven to link in every build, so a map that wants a sign to say
something builds the letters out of brushes: a white plate standing a unit off
the surface and the 5x7 glyphs of :mod:`zmforge.images.glyphs` on it in dark
trim, each glyph cut into a few rectangles.  This is the idea of
the DMV's old window signs and ``dmv_rooms.eye._cells_to_rects`` lifted into one
helper any recipe can call, for a plate on any of the four walls or lying on
the floor.

Two calls:

:func:`text_boxes`
    the geometry only, ``[(kind, Bounds), ...]`` with kind ``"plate"`` or
    ``"ink"``; pure, so tests and planners can measure a sign before it exists.
:func:`brush_text`
    the same boxes added to a blueprint as detail brushes that nothing stands
    on (``reachable=False``), returning their ids.

The glyph set is what :data:`zmforge.images.glyphs.GLYPHS` draws: A-Z, 0-9,
``+,-./:?_'`` and space.  Anything else draws as ``?``, which
:func:`unsupported` reports before a sign is built with it.
"""
from __future__ import annotations

from typing import Sequence

from .blueprint.elements import FLOATS_ON_PURPOSE
from .images.glyphs import GLYPH_HEIGHT, GLYPH_WIDTH, GLYPHS, glyph_for
from .materials import CAULK, FaceMaterials, Material
from .spatial import Bounds, Facing, Point, Side

__all__ = [
    "PLATE",
    "INK",
    "cells_to_rects",
    "text_size",
    "text_boxes",
    "brush_text",
    "brush_symbol",
    "symbol_boxes",
    "unsupported",
]

#: The plate and the letters.  The same two trims the DMV's window signs use,
#: both link (zm_dmv uses them).
PLATE = Material("t7_plastic_molding_trim_white", 64.0)
INK = Material("t7_metal_black_trim_01", 16.0)

#: Clear margin round the ink, how far the plate stands off its surface, and
#: how far the ink stands off the plate.
MARGIN = 3.0
PLATE_DEPTH = 1.0
INK_DEPTH = 0.75


def cells_to_rects(glyph: Sequence[str]) -> list[tuple[int, int, int, int]]:
    """Cover a glyph's ink with few rectangles ``(col, row, width, height)``:
    at each uncovered ink cell, the larger of a run across then down, or a run
    down then across (the eye chart's cover, ``dmv_rooms.eye``)."""
    ink = {(c, r) for r, line in enumerate(glyph) for c, ch in enumerate(line) if ch == "#"}
    used: set[tuple[int, int]] = set()
    rects: list[tuple[int, int, int, int]] = []

    def free(cc: int, rr: int) -> bool:
        return (cc, rr) in ink and (cc, rr) not in used

    for r in range(len(glyph)):
        for c in range(len(glyph[0])):
            if not free(c, r):
                continue
            w = 1
            while free(c + w, r):
                w += 1
            h = 1
            while all(free(c + i, r + h) for i in range(w)):
                h += 1
            h2 = 1
            while free(c, r + h2):
                h2 += 1
            w2 = 1
            while all(free(c + w2, r + j) for j in range(h2)):
                w2 += 1
            best = (c, r, w, h) if w * h >= w2 * h2 else (c, r, w2, h2)
            bc, br, bw, bh = best
            used |= {(bc + i, br + j) for i in range(bw) for j in range(bh)}
            rects.append(best)
    return rects


def unsupported(text: str) -> set[str]:
    """The characters of *text* the font has no glyph for (they draw as ``?``)."""
    return {ch for ch in text.upper() if ch != " " and ch not in GLYPHS}


def text_size(text: str, cell: float) -> tuple[float, float]:
    """Width and height of the ink of *text* at *cell* units per font cell
    (one blank column between letters)."""
    n = len(text)
    return (n * GLYPH_WIDTH + max(n - 1, 0)) * cell, GLYPH_HEIGHT * cell


def _axes(facing: Facing, flat: bool) -> tuple[tuple[float, float, float], ...]:
    """``(normal, right, up)`` unit vectors of the reading plane.

    On a wall, *facing* is where the plate's face looks (into the room); the
    reader looks the other way, so their right is ``(-ny, nx)``.  On the
    floor the normal is +z and *facing* is where the tops of the letters
    point: a reader standing on the far side looking that way reads it."""
    fx, fy = facing.step.x, facing.step.y
    if flat:
        return (0.0, 0.0, 1.0), (fy, -fx, 0.0), (fx, fy, 0.0)
    return (fx, fy, 0.0), (-fy, fx, 0.0), (0.0, 0.0, 1.0)


def _box(origin: tuple[float, float, float], axes, u0: float, u1: float,
         v0: float, v1: float, n0: float, n1: float) -> Bounds:
    """The axis-aligned box spanning right ``u0..u1``, up ``v0..v1`` and
    normal ``n0..n1`` from *origin*."""
    normal, right, up = axes
    xs, ys, zs = [], [], []
    for u in (u0, u1):
        for v in (v0, v1):
            for n in (n0, n1):
                xs.append(origin[0] + right[0] * u + up[0] * v + normal[0] * n)
                ys.append(origin[1] + right[1] * u + up[1] * v + normal[1] * n)
                zs.append(origin[2] + right[2] * u + up[2] * v + normal[2] * n)
    return Bounds.between((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def text_boxes(text: str, *, at: Point, facing: Facing, cell: float = 2.0,
               flat: bool = False, plate: bool = True) -> list[tuple[str, Bounds]]:
    """Every box of *text* as ``(kind, bounds)``.

    *at* is the middle of the lettering on the surface it stands on (a wall's
    inner face, or the floor's top); the plate grows out of that surface by
    :data:`PLATE_DEPTH` and the ink out of the plate by :data:`INK_DEPTH`.
    With ``plate=False`` the ink stands straight on the surface."""
    text = text.upper()
    axes = _axes(Facing.of(facing), flat)
    origin = (at.x, at.y, at.z)
    width, height = text_size(text, cell)
    out: list[tuple[str, Bounds]] = []
    n_ink = PLATE_DEPTH if plate else 0.0
    if plate:
        out.append(("plate", _box(origin, axes, -width / 2 - MARGIN, width / 2 + MARGIN,
                                  -height / 2 - MARGIN, height / 2 + MARGIN,
                                  0.0, PLATE_DEPTH)))
    left, top = -width / 2.0, height / 2.0
    for index, char in enumerate(text):
        if char == " ":
            continue
        x0 = left + index * (GLYPH_WIDTH + 1) * cell
        for c, r, w, h in cells_to_rects(glyph_for(char)):
            out.append(("ink", _box(origin, axes, x0 + c * cell, x0 + (c + w) * cell,
                                    top - (r + h) * cell, top - r * cell,
                                    n_ink, n_ink + INK_DEPTH)))
    return out


def _faces(kind: str, facing: Facing, flat: bool, plate: Material, ink: Material,
           on_prop: bool = False) -> FaceMaterials:
    """Paint the face the reader sees (and, for a plate, its edges).  A plate
    on a prop gets its back painted too: a prop is no seal (its measured box
    leaves a unit or two of gap, a sign hung between two props has air
    behind it), and a caulk back seen from behind is a hole (Z84)."""
    front = Side.TOP if flat else Facing.of(facing).side
    if kind == "ink":
        return FaceMaterials(default=CAULK, per_side={front: ink})
    per = {side: plate for side in Side if on_prop or side is not front.opposite}
    return FaceMaterials(default=CAULK, per_side=per)


def brush_text(bp, text: str, *, at: Point, facing: Facing, cell: float = 2.0,
               flat: bool = False, plate: bool = True, plate_material: Material = PLATE,
               ink: Material = INK, ident: str, on_prop: bool = False) -> list[str]:
    """Build *text* as detail brushes on *bp*; returns the element ids.

    ``ident`` prefixes every id (``<ident>_plate``, ``<ident>_<n>``) and must
    be unique map-wide.  Refuses a character the font cannot draw rather than
    shipping a ``?``.  ``on_prop`` marks a plate that stands on a prop
    rather than on a wall or the floor (see Z43)."""
    missing = unsupported(text)
    if missing:
        raise ValueError(f"{ident}: no glyph for {sorted(missing)} in {text!r}")
    ids: list[str] = []
    for n, (kind, box) in enumerate(text_boxes(text, at=at, facing=facing, cell=cell,
                                               flat=flat, plate=plate)):
        element = bp.add_block(
            box, _faces(kind, facing, flat, plate_material, ink, on_prop),
            contents=("detail",), reachable=False,
            id=f"{ident}_plate" if kind == "plate" else f"{ident}_{n}",
            # A plate resting on a prop (a desk top, a cabinet face) has no
            # world brush under it; Z43 is told it floats on purpose.
            note=FLOATS_ON_PURPOSE if on_prop else f"lettering: {text}",
        )
        ids.append(element.id)
    return ids


def symbol_boxes(bitmap: Sequence[str], *, at: Point, facing: Facing, cell: float = 3.0,
                 mirror: bool = False) -> list[Bounds]:
    """A ``#``/``.`` *bitmap* (top row first) as boxes standing on a wall.

    *at* is the middle of the symbol on the wall's face; *facing* is where
    the face looks; *mirror* flips it left to right as the reader sees it.
    The paint stands :data:`INK_DEPTH` off the wall, like unplated ink."""
    rows = [row[::-1] for row in bitmap] if mirror else list(bitmap)
    axes = _axes(Facing.of(facing), False)
    width, height = len(rows[0]) * cell, len(rows) * cell
    left, top = -width / 2.0, height / 2.0
    return [_box((at.x, at.y, at.z), axes, left + c * cell, left + (c + w) * cell,
                 top - (r + h) * cell, top - r * cell, 0.0, INK_DEPTH)
            for c, r, w, h in cells_to_rects(rows)]


def brush_symbol(bp, bitmap: Sequence[str], *, at: Point, facing: Facing, cell: float = 3.0,
                 mirror: bool = False, paint: Material = PLATE, ident: str,
                 note: str = "symbol") -> list[str]:
    """Paint *bitmap* (:func:`symbol_boxes`) on a wall as detail brushes that
    nothing stands on; returns the element ids (``<ident>_<n>``)."""
    ids = []
    for n, box in enumerate(symbol_boxes(bitmap, at=at, facing=facing, cell=cell,
                                         mirror=mirror)):
        element = bp.add_block(box, _faces("ink", facing, False, paint, paint),
                               contents=("detail",), reachable=False, id=f"{ident}_{n}",
                               note=f"lettering: {note}")
        ids.append(element.id)
    return ids
