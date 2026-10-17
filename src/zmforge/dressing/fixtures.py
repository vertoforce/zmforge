"""Hung and leaning fixtures built from detail brushes: signs, rails, struts.

Units are map units (inches); every function adds brushes to the blueprint
it is given, with ids ``<ident>_*``, and is deterministic (no randomness).
"""

from __future__ import annotations

from typing import Sequence

from ..blueprint.elements import FLOATS_ON_PURPOSE, Massing
from ..lettering import PLATE, brush_text, text_size
from ..materials import FaceMaterials, Material
from ..solids.forms import Solid, SolidFace
from ..solids.halfspace import orient_inward
from ..spatial import Bounds, Facing, Point

__all__ = ["RAIL", "hanging_sign", "hang_bar", "sheared_bar"]

#: Black metal for curtain tracks, hanger rods and lighting bars.
RAIL = Material("t7_metal_black_trim_01", 16.0)


def hanging_sign(bp, ident: str, x: float, y: float, *, floor: float, ceiling: float,
                 lines: Sequence[tuple[str, float]], faces: Sequence[Facing],
                 bottom: float = 100.0) -> list[str]:
    """A lettered board hung from the ceiling on two rods, centred on
    (*x*, *y*) with its bottom *bottom* above *floor*, lettered with *lines*
    (``(text, cell)``, top line first) on each face in *faces* (NORTH/SOUTH,
    or EAST/WEST: the board is thin across them).  Returns the lettering ids.

    Use it for any words the player must read in a room: words laid flat on
    the floor read as grey planks in every render."""
    across_x = faces[0] in (Facing.EAST, Facing.WEST)
    half = max(text_size(t, c)[0] for t, c in lines) / 2.0 + 8.0
    height = sum(text_size(t, c)[1] for t, c in lines) + 5.0 * (len(lines) - 1) + 20.0
    z0 = floor + bottom
    z1 = min(z0 + height, ceiling - 6.0)
    board = FaceMaterials(default=PLATE, per_side={})
    if across_x:
        box = ((x - 1.0, y - half, z0), (x + 1.0, y + half, z1))
        rods = ((x, y - half + 12.0), (x, y + half - 12.0))
    else:
        box = ((x - half, y - 1.0, z0), (x + half, y + 1.0, z1))
        rods = ((x - half + 12.0, y), (x + half - 12.0, y))
    bp.add_block(Bounds.between(*box), board, contents=("detail",), reachable=False,
                 id=f"{ident}_board", note=FLOATS_ON_PURPOSE)
    for k, (rx, ry) in enumerate(rods):
        bp.add_block(Bounds.between((rx - 0.5, ry - 0.5, z1), (rx + 0.5, ry + 0.5, ceiling)),
                     board, contents=("detail",), reachable=False,
                     id=f"{ident}_rod_{k}", note="hanging sign rod")
    step = {Facing.NORTH: (0.0, 1.0), Facing.SOUTH: (0.0, -1.0),
            Facing.EAST: (1.0, 0.0), Facing.WEST: (-1.0, 0.0)}
    ids: list[str] = []
    for facing in faces:
        dx, dy = step[facing]
        z = z1 - 10.0
        for n, (txt, cell) in enumerate(lines):
            h = text_size(txt, cell)[1]
            ids += brush_text(bp, txt, at=Point(x + dx, y + dy, z - h / 2.0), facing=facing,
                              cell=cell, ident=f"{ident}_{facing.name.lower()}{n}", on_prop=True)
            z -= h + 5.0
    return ids


def hang_bar(bp, ident: str, a: tuple[float, float], b: tuple[float, float], z: float, *,
             ceiling: float, half: float = 0.75, rods: bool = True, rod_inset: float = 6.0,
             material: Material = RAIL, depth: float | None = None) -> None:
    """A thin metal bar from *a* to *b* (x, y; the run must be along x or
    along y) with its top at *z*, hung from *ceiling* on a rod near each end:
    a curtain track, or a lighting bar.  ``rods=False`` for a bar that meets
    another bar's rod (the corner of a U track); *half* is half its width and
    *depth* its height (default: square).  A curtain, drape or lamp row is
    only whole with the rail it hangs from."""
    (x0, y0), (x1, y1) = a, b
    along_x = abs(x1 - x0) >= abs(y1 - y0)
    tall = 2.0 * half if depth is None else depth
    lo_x, hi_x = min(x0, x1), max(x0, x1)
    lo_y, hi_y = min(y0, y1), max(y0, y1)
    if along_x:
        box = ((lo_x, y0 - half, z - tall), (hi_x, y0 + half, z))
        ends = ((lo_x + rod_inset, y0), (hi_x - rod_inset, y0))
    else:
        box = ((x0 - half, lo_y, z - tall), (x0 + half, hi_y, z))
        ends = ((x0, lo_y + rod_inset), (x0, hi_y - rod_inset))
    bp.add_block(Bounds.between(*box), material, contents=("detail",), reachable=False,
                 id=f"{ident}_bar", note=FLOATS_ON_PURPOSE)
    if not rods or z >= ceiling - 0.5:
        return
    for k, (x, y) in enumerate(ends):
        bp.add_block(Bounds.between((x - 0.4, y - 0.4, z), (x + 0.4, y + 0.4, ceiling)),
                     material, contents=("detail",), reachable=False,
                     id=f"{ident}_rod_{k}", note="hanger rod")


def sheared_bar(bp, ident: str, low: tuple[float, float, float],
                high: tuple[float, float, float], half: float, material: Material, *,
                note: str = FLOATS_ON_PURPOSE, half_y: float | None = None) -> None:
    """One convex detail brush: a straight bar, *half* either side of its
    centre line in x and y, from the flat end at *low* to the flat end at
    *high* (``high`` above ``low``).  A leaning strut (a lever arm, a tripod
    leg, a cable) is one piece this way: built from stacked boxes it read as
    a staircase in the renders.  *half_y*, when given,
    is the half-width in y (a slab: a roof plane, a leaning board)."""
    (x0, y0, z0), (x1, y1, z1) = low, high
    sx, sy = (x1 - x0) / (z1 - z0), (y1 - y0) / (z1 - z0)
    h = half
    k = half if half_y is None else half_y

    def at(end: int, dx: float, dy: float) -> Point:
        return Point((x1 if end else x0) + dx, (y1 if end else y0) + dy, z1 if end else z0)

    faces = (
        ((at(0, -h, -k), at(0, -h, k), at(1, -h, -k)), Point(1.0, 0.0, -sx)),
        ((at(0, h, -k), at(0, h, k), at(1, h, -k)), Point(-1.0, 0.0, sx)),
        ((at(0, -h, -k), at(0, h, -k), at(1, -h, -k)), Point(0.0, 1.0, -sy)),
        ((at(0, -h, k), at(0, h, k), at(1, -h, k)), Point(0.0, -1.0, sy)),
        ((at(0, -h, -k), at(0, h, -k), at(0, -h, k)), Point(0.0, 0.0, 1.0)),
        ((at(1, -h, -k), at(1, h, -k), at(1, -h, k)), Point(0.0, 0.0, -1.0)),
    )
    solid = Solid(tuple(SolidFace(orient_inward(*pts, inward), material, inward)
                        for pts, inward in faces), ("detail",), note)
    bp._install(Massing(id=bp._claim("block", ident), solids=[solid], note=note,
                        reachable=False))
