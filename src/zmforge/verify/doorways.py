"""Z53: no solid prop stands in a doorway or in the floor either side of it.

Measured on zm_dmv: a filing cabinet placed against the records
room's west wall ran 10 units into the 80-unit doorway behind the counter, and
a player could not walk through to Speed Cola.  Nothing else
caught it -- Z44 asks whether props overlap *each other*, Z25 floods from the
spawn and still finds a route (the door was only narrowed), and Z48 asks only
about items.  So this asks the one question directly, of every recipe: is the
hole and the floor in front of and behind it clear?

The clear zone of a doorway (an opening whose sill is the floor) runs along the
wall for the opening's width plus :data:`SIDE_MARGIN` each side, and across it
from :data:`APPROACH` inside one room to :data:`APPROACH` inside the other --
a player's width (32) plus margin.  A prop blocks when it is solid and stands
taller than a step (:data:`STEP`) *on that floor*; a sheet of paper does not,
and neither does a prop raised on something else: a prop can stand on a clip
block, and then the block, not the model, is what a player walking through
meets.
"""

from __future__ import annotations

from ..spatial import Side
from .report import Report, error

__all__ = ["APPROACH", "SIDE_MARGIN", "STEP", "doorway_zones", "check_doorways"]

#: How far into each room the clear zone reaches: a 32-unit player hull and
#: 16 of margin.
APPROACH = 48.0
#: How far past each jamb the zone runs along the wall.
SIDE_MARGIN = 8.0
#: A prop no taller than this is stepped over, not walked round.
STEP = 18.0


def doorway_zones(blueprint):
    """``(room id, (x0, y0, x1, y1), floor z)`` for every doorway."""
    from ..blueprint.elements import Room

    out = []
    for room in blueprint.elements(Room):
        floor = room.floor_z
        for aperture, box in zip(room.apertures, room.aperture_boxes):
            if aperture.sill > 0.0:
                continue
            if aperture.side in (Side.NORTH, Side.SOUTH):
                rect = (box.mins.x - SIDE_MARGIN, box.mins.y - APPROACH,
                        box.maxs.x + SIDE_MARGIN, box.maxs.y + APPROACH)
            else:
                rect = (box.mins.x - APPROACH, box.mins.y - SIDE_MARGIN,
                        box.maxs.x + APPROACH, box.maxs.y + SIDE_MARGIN)
            out.append((room.id, rect, floor))
    return out


def check_doorways(blueprint) -> Report:
    """Z53, an error per solid prop standing in a doorway's clear zone."""
    from ..blueprint.elements import PropScatter
    from ..placement.relations import Placed
    from ..props.origins import drawn_box
    from ..recipes.props import collision_box

    report = Report()
    zones = doorway_zones(blueprint)
    if not zones:
        return report
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if not prop.solid:
                continue
            measured = drawn_box(prop.model, collision_box(prop.model))
            if measured is None:
                continue
            placed = Placed.from_model(
                prop.model, measured, (prop.origin.x, prop.origin.y, prop.origin.z),
                prop.yaw, prop.scale, solid=True, ident=prop.id,
            )
            x0, y0, x1, y1 = placed.footprint.bounds
            for room_id, (zx0, zy0, zx1, zy1), floor in zones:
                if placed.z_high <= floor + STEP or placed.z_low >= floor + STEP:
                    continue
                if x0 < zx1 and zx0 < x1 and y0 < zy1 and zy0 < y1:
                    report.add(
                        error(
                            "Z53",
                            f"{prop.model} ({prop.id or scatter.id}) at "
                            f"{prop.origin.x:g} {prop.origin.y:g} stands in the "
                            f"doorway of {room_id} or the {APPROACH:g} units of "
                            "floor either side of it; a player walks into it",
                        )
                    )
                    break
    return report
