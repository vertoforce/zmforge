"""Lightning bolts toward the power switch: the one text-free wayfinding P17 allows.

Painted lightning-bolt symbols pointing toward power are a zombies
convention, and P17's one exception.  :func:`paint_power_bolts` paints one
beside each door on the
**cheapest route from the spawn to the power switch's zone** (the door graph,
:func:`zmforge.verify.design.cheapest_route`), on the wall of the side the
player approaches from, next to the frame, its arrow pointing at the doorway.

Where it does not paint, so the last stretch stays for players to find:

* the door into the power switch's own zone;
* any door whose bolt would stand within :data:`POWER_CLEAR` units of the
  switch;
* any door off that route: doors beyond the power room, and routes that lead
  back to power from deeper in the map, get nothing.

It runs by itself in every ``Project.commit``.  A recipe opts out with
``bp.power_bolts = False``.  What it painted is on ``bp.power_bolt_doors``
(door ids, in route order).
"""

from __future__ import annotations

import math

from ..spatial import Facing, Point

__all__ = ["BOLT", "BOLT_CELL", "POWER_CLEAR", "paint_power_bolts", "power_route_doors"]

#: The stencil: a bolt over an arrow pointing to the reader's right (the
#: helper mirrors it when the doorway is on the left).
BOLT = (
    "....###..",
    "...###...",
    "..###....",
    ".######..",
    "...###...",
    "..###....",
    ".###.....",
    ".##......",
    ".#.......",
    ".........",
    "......#..",
    "#########",
    "......#..",
)
#: Units per stencil cell: 27 x 39 units.
BOLT_CELL = 3.0
#: No bolt within this of the switch (about 300).
POWER_CLEAR = 300.0
#: Gap between the door frame and the stencil, and the stencil's centre height.
FRAME_GAP = 20.0
HEIGHT = 64.0


def power_route_doors(bp) -> list[tuple[str, str, str]]:
    """``(door id, from zone, to zone)`` on the cheapest route from the spawn
    to the power switch's zone, spawn first (free edges left out).  Only doors
    that can be bought before the power is on count: a power-gated door
    (``Door.power_gated``) is never on the way to power (``Z80``)."""
    from ..verify.design import cheapest_route

    zone = _power_zone(bp)
    if zone is None:
        return []
    return [(door, a, b) for door, a, b in cheapest_route(bp, zone, before_power=True)
            if door]


def _power_zone(bp) -> str | None:
    from ..blueprint.elements import PowerSwitch
    from ..script.zonegate import zone_at
    from ..verify.design import _zone_boxes

    switch = next(iter(bp.elements(PowerSwitch)), None)
    if switch is None:
        return None
    p = switch.position
    return zone_at((p.x, p.y, p.z), _zone_boxes(bp))


def _approach(rooms, door, axis_x: bool):
    """``(room, wall face coordinate, travel sign)`` of the approach room: the
    room of the from-zone whose wall the doorway is cut in."""
    c = door.box.centre
    best = None
    for room in rooms:
        i = room.interior
        if axis_x:
            if not i.mins.y - 1.0 <= c.y <= i.maxs.y + 1.0:
                continue
            options = ((abs(c.x - i.maxs.x), i.maxs.x, 1.0), (abs(i.mins.x - c.x), i.mins.x, -1.0))
        else:
            if not i.mins.x - 1.0 <= c.x <= i.maxs.x + 1.0:
                continue
            options = ((abs(c.y - i.maxs.y), i.maxs.y, 1.0), (abs(i.mins.y - c.y), i.mins.y, -1.0))
        for gap, face, sign in options:
            if gap <= 64.0 and (best is None or gap < best[0]):
                best = (gap, room, face, sign)
    return None if best is None else best[1:]


def paint_power_bolts(bp) -> list[str]:
    """Paint the route to power (module docstring); returns the door ids.

    Idempotent: a blueprint already painted returns what it painted."""
    done = getattr(bp, "power_bolt_doors", None)
    if done is not None:
        return list(done)
    painted: list[str] = []
    bp.power_bolt_doors = painted
    if getattr(bp, "power_bolts", True) is False:
        return painted
    from ..blueprint.elements import Door, PowerSwitch
    from ..lettering import brush_symbol
    from ..spatial import Axis
    from ..verify.design import _rooms_by_zone

    switch = next(iter(bp.elements(PowerSwitch)), None)
    route = power_route_doors(bp)
    if switch is None or not route:
        return painted
    sw = switch.position
    doors = {d.id: d for d in bp.elements(Door)}
    by_zone = _rooms_by_zone(bp)
    power_zone = _power_zone(bp)
    for door_id, from_zone, to_zone in route:
        door = doors.get(door_id)
        if door is None or to_zone == power_zone:
            continue  # the door into the power room: players find the rest
        axis_x = door.through_axis is Axis.X
        found = _approach(by_zone.get(from_zone, ()), door, axis_x)
        if found is None:
            continue
        room, face, sign = found
        b, c = door.box, door.box.centre
        i = room.interior
        if axis_x:
            half, lo, hi, mid = (b.maxs.y - b.mins.y) / 2.0, i.mins.y, i.maxs.y, c.y
        else:
            half, lo, hi, mid = (b.maxs.x - b.mins.x) / 2.0, i.mins.x, i.maxs.x, c.x
        reach = half + FRAME_GAP + len(BOLT[0]) * BOLT_CELL / 2.0
        spot = None
        for side in (1.0, -1.0):
            u = mid + side * reach
            if lo + 24.0 <= u <= hi - 24.0:
                spot = (u, side)
                break
        if spot is None:
            continue
        u, side = spot
        x, y = (face, u) if axis_x else (u, face)
        if math.hypot(x - sw.x, y - sw.y) < POWER_CLEAR:
            continue
        # The stencil faces back into the approach room.
        facing = (Facing.WEST if sign > 0 else Facing.EAST) if axis_x else (
            Facing.SOUTH if sign > 0 else Facing.NORTH)
        # Reader's right is (-fy, fx); the doorway lies at -side along the wall.
        step = facing.step
        right = (-step.y, step.x)
        towards = (0.0, -side) if axis_x else (-side, 0.0)
        mirror = right[0] * towards[0] + right[1] * towards[1] < 0
        brush_symbol(bp, BOLT, at=Point(x, y, room.floor_z + HEIGHT), facing=facing,
                     cell=BOLT_CELL, mirror=mirror, ident=f"power_bolt_{door_id}",
                     note="power bolt")
        painted.append(door_id)
    return painted
