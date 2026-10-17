"""Z85: every barricade window is a window, with a dressed, dim closet behind.

A zombie window must show solid wall to waist height.  The opening is cut from the floor for the prefab's traversal
channel, and nothing was drawn under the boards, so each window read as a
doorway onto a blank, blown-out box.  See :mod:`zmforge.blueprint.windows`.

Errors:

- a window with no drawn sill wall to :data:`SILL_WALL_HEIGHT` under it, or one
  whose room-side face is a placeholder material;
- a closet (its ``Yard``) whose wall or floor is a placeholder or white material;
- a lamp inside a closet brighter than :data:`CLOSET_LAMP_MAX_LUMA` against the
  map's exposure, or two closet lamps stacked on one spot (the glare).

Warning: a closet with no prop in it (a bare box behind the boards).
"""

from __future__ import annotations

from dataclasses import replace

from .report import Report, error, warning

__all__ = ["CODE", "check_windows"]

CODE = "Z85"

#: Two closet lamps closer than this are one spot, lit twice.
STACKED = 32.0


def _luma(colour) -> float:
    r, g, b = colour
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def check_windows(bp) -> Report:
    from ..blueprint.elements import Lamp, PropScatter, Window, Yard
    from ..blueprint.windows import (
        BRIGHT_MATERIALS,
        CLOSET_LAMP_MAX_LUMA,
        PLACEHOLDER_MATERIALS,
        SILL_WALL_HEIGHT,
        sill_wall_box,
        sill_wall_solid,
    )
    from ..spatial import Side

    report = Report()
    windows = list(bp.elements(Window))
    if not windows:
        return report
    for window in windows:
        room = bp.find(window.room_id)
        if room is None or not 0 <= window.aperture_index < len(room.apertures):
            report.add(error(CODE, f"barricade window {window.id} names no hole "
                                   f"({window.room_id!r} aperture {window.aperture_index})"))
            continue
        hole = room.opening(window.aperture_index).box
        if hole.mins.z >= room.floor_z + SILL_WALL_HEIGHT - 1e-6:
            continue  # real wall under a raised opening
        box, solid = sill_wall_box(bp, window), sill_wall_solid(bp, window)
        if box is None or solid is None or box.maxs.z < room.floor_z + SILL_WALL_HEIGHT - 1e-6:
            report.add(error(CODE, f"barricade window {window.id} has no wall under it: "
                                   f"the hole starts {hole.mins.z - room.floor_z:g} above the "
                                   f"floor and nothing is drawn up to the {SILL_WALL_HEIGHT:g}-unit "
                                   "sill, so it reads as a doorway (blueprint/windows.py)"))
            continue
        names = {face.material.name for face in solid.faces}
        if names <= PLACEHOLDER_MATERIALS or any(
                n in PLACEHOLDER_MATERIALS - {"caulk"} for n in names):
            report.add(error(CODE, f"barricade window {window.id}'s sill wall is drawn in "
                                   f"{sorted(names)}, a placeholder"))

    yards = {y.id: y for y in bp.elements(Yard)}
    lamps = list(bp.elements(Lamp))
    props = [p for s in bp.elements(PropScatter) for p in s.props]
    for yard_id in sorted({w.yard_id for w in windows if w.yard_id}):
        yard = yards.get(yard_id)
        if yard is None:
            continue
        inside = yard.interior
        for label, material in (("wall", yard.materials.wall),
                                ("floor", yard.materials.for_side(Side.BOTTOM))):
            if material.name in PLACEHOLDER_MATERIALS | BRIGHT_MATERIALS:
                report.add(error(CODE, f"closet {yard.id} behind a barricade window has a "
                                       f"placeholder or white {label} ({material.name}): a "
                                       "blank box glaring through the boards"))
        mine = [lamp for lamp in lamps
                if inside.holds_flat(lamp.position.x, lamp.position.y)
                and inside.mins.z - 1 <= lamp.position.z <= inside.maxs.z + 1]
        for lamp in mine:
            # Against a default white room lamp of this map, so a map-wide
            # brightness offset (a night map's) moves both alike.
            room_lamp = bp.stops_of(replace(lamp, stops=None))
            weight = 2.0 ** (bp.stops_of(lamp) - room_lamp) * _luma(lamp.colour)
            if weight > CLOSET_LAMP_MAX_LUMA + 1e-9:
                report.add(error(CODE, f"lamp {lamp.id} in closet {yard.id} is {weight:.2f} of a "
                                       f"room lamp, over {CLOSET_LAMP_MAX_LUMA:g}: the closet glares "
                                       "white through the boards (use CLOSET_LAMP_COLOUR)"))
        for i, a in enumerate(mine):
            for b in mine[i + 1:]:
                if abs(a.position.x - b.position.x) < STACKED and abs(a.position.y - b.position.y) < STACKED:
                    report.add(error(CODE, f"lamps {a.id} and {b.id} are stacked on one spot in "
                                           f"closet {yard.id}"))
        if not any(inside.holds_flat(p.origin.x, p.origin.y)
                   and inside.mins.z - 8 <= p.origin.z <= inside.maxs.z for p in props):
            report.add(warning(CODE, f"closet {yard.id} behind a barricade window is bare: "
                                     "no prop in it"))
    return report
