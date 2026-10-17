"""Z43: world brushwork that stands on nothing, and is not saying it meant to.

A map is built out of arithmetic, and arithmetic is how a slab ends up in mid
air.  Columns written to start at z 288 because 288 is the first floor's
height, on a deck that runs 272 to 288, each begin exactly 16 units above the
thing they are supposed to rest on, with a slot of daylight under every one.
Nothing else in this package can see it: they overlap nothing, they are
inside a zone, they block no route, they are lit, and every other check
passes.  Only looking at the map finds it, which is the failure mode this row
closes.

What counts as carried
----------------------
Three ways, and a solid needs one of them:

* **It rests.**  Another solid, a room's floor or the terrain is within
  :data:`HANG_SLACK` below part of its footprint.  This is the one the columns
  failed and the one most geometry passes on.
* **It hangs.**  Something is within :data:`HANG_SLACK` above part of its
  footprint -- a fixture under a ceiling, a sign under a deck.
* **It is fixed to something.**  One of its vertical faces is flush within
  :data:`HANG_SLACK` against a vertical face of another solid, over at least
  :data:`FIXING_SHARE` of that face.  A poster on a wall, a handrail against a
  pier, and a balcony deck cantilevered off three walls of a hall are all
  this, and all three are ordinary map building rather than defects.

What this does not ask
----------------------
**Whether a thing attached to a wall is attached high up.**  A shelf bolted to
a wall 400 units off the floor passes here, because it is fixed to the wall and
this check cannot tell a shelf from a mistake.  That is a design question, not
a check.

**Rooms and yards.**  The subjects are the massing solids a recipe places --
blocks, slabs, steps, panes, posters -- because that is what is positioned by
arithmetic.  A room is positioned as a whole box with its own floor in it, and
every other solid in the map is allowed to be a *support* here, rooms
included.

Saying so on purpose
--------------------
A map that wants something in mid-air marks it
:data:`~zmforge.blueprint.elements.FLOATS_ON_PURPOSE` on the massing, which is
the same shape as ``reachable=False``: the declaration lives on the geometry,
is made once, and every check that would object reads it.
"""

from __future__ import annotations

from typing import Sequence

from ..blueprint.elements import FLOATS_ON_PURPOSE, Massing, Room, Terrain
from ..blueprint.model import _solid_bounds
from ..spatial import Point, Span
from .report import Report, error

__all__ = ["check_nothing_hangs", "HANG_SLACK", "FIXING_SHARE"]


#: How far off contact still counts as contact, in units.  Everything this
#: generator writes is on a grid, so this only has to absorb floating-point
#: noise and the odd one-unit inset -- 2 is generous and still an eighth of
#: the gap that hid under those columns.
HANG_SLACK = 2.0

#: How much of a solid's own face has to be flush against another solid's
#: before it counts as fixed to it.  Half: a poster is fully against its wall,
#: a balcony deck is fully against the wall it runs along, and a block that
#: happens to graze a pier by a corner is not held up by it.
FIXING_SHARE = 0.5


def _plan_overlap(a: Span, b: Span) -> float:
    """How far two footprints overlap, negative when they are apart.

    Zero -- a shared edge -- counts as bearing.  ``zm_jumpprobe`` builds every
    capped bay as a lid spanning between two dividers whose tops are exactly
    the lid's underside and whose footprints touch it edge to edge with no
    overlap at all, which is a lintel and is how anybody would build it.  What
    this row is looking for is a *gap*, and a gap is what the shared edge is
    not.
    """
    return min(
        min(a.maxs.x, b.maxs.x) - max(a.mins.x, b.mins.x),
        min(a.maxs.y, b.maxs.y) - max(a.mins.y, b.mins.y),
    )


def _rests_on(box: Span, support: Span) -> bool:
    if support.maxs.z < box.mins.z - HANG_SLACK:
        return False
    if support.mins.z > box.mins.z + HANG_SLACK:
        return False
    return _plan_overlap(box, support) >= -HANG_SLACK


def _hangs_from(box: Span, support: Span) -> bool:
    if support.mins.z > box.maxs.z + HANG_SLACK:
        return False
    if support.maxs.z < box.maxs.z - HANG_SLACK:
        return False
    return _plan_overlap(box, support) >= -HANG_SLACK


def _fixed_to(box: Span, support: Span) -> bool:
    """A vertical face of ``box`` flush against a vertical face of ``support``."""
    for axis, other, up in (("x", "y", "z"), ("y", "x", "z")):
        near = abs(getattr(support.maxs, axis) - getattr(box.mins, axis)) <= HANG_SLACK
        far = abs(getattr(support.mins, axis) - getattr(box.maxs, axis)) <= HANG_SLACK
        if not (near or far):
            continue
        across = min(getattr(support.maxs, other), getattr(box.maxs, other)) - max(
            getattr(support.mins, other), getattr(box.mins, other)
        )
        tall = min(support.maxs.z, box.maxs.z) - max(support.mins.z, box.mins.z)
        if across <= 0.0 or tall <= 0.0:
            continue
        face = (getattr(box.maxs, other) - getattr(box.mins, other)) * (
            box.maxs.z - box.mins.z
        )
        if face <= 0.0:
            continue
        if (across * tall) / face >= FIXING_SHARE:
            return True
    return False


#: Plan bucket used to avoid comparing every solid with every other one.  The
#: same 512 the reachability flood uses, for the same reason: without it this
#: row is a nested loop over every world solid in the map, which on
#: a test map is 14 seconds a call.
_BUCKET = 512.0


def _keyed(box: Span):
    """Which plan buckets a box touches, grown by the slack."""
    import math

    for gx in range(
        math.floor((box.mins.x - HANG_SLACK) / _BUCKET),
        math.floor((box.maxs.x + HANG_SLACK) / _BUCKET) + 1,
    ):
        for gy in range(
            math.floor((box.mins.y - HANG_SLACK) / _BUCKET),
            math.floor((box.maxs.y + HANG_SLACK) / _BUCKET) + 1,
        ):
            yield gx, gy


def _floors(blueprint) -> list[tuple[int, Span]]:
    """A room's own floor, as the flat box a thing can stand on.

    Paired with ``-1`` where a solid's identity would go, so the one index can
    hold both and the caller's "not my own solid" test works on either.
    """
    out: list[tuple[int, Span]] = []
    for room in blueprint.elements(Room):
        interior = room.interior
        out.append((
            -1,
            Span.between(
                Point(interior.mins.x, interior.mins.y, room.floor_z - 1.0),
                Point(interior.maxs.x, interior.maxs.y, room.floor_z),
            ),
        ))
    return out


def _on_terrain(terrains, box: Span) -> bool:
    for terrain in terrains:
        edge = terrain.record.footprint
        for x, y in (
            (box.mins.x, box.mins.y),
            (box.maxs.x, box.maxs.y),
            (box.centre.x, box.centre.y),
        ):
            sample = terrain.record.sample(
                min(x, edge.maxs.x - 1e-6), min(y, edge.maxs.y - 1e-6)
            )
            if sample.found and box.mins.z - HANG_SLACK <= sample.z:
                return True
    return False


def check_nothing_hangs(blueprint) -> Report:
    """Z43: is every massing solid resting on, hanging from or fixed to something?"""
    report = Report()
    terrains = list(blueprint.elements(Terrain))
    grid: dict[tuple[int, int], list[tuple[int, Span]]] = {}
    for solid in blueprint.world_solids():
        entry = (id(solid), _solid_bounds(solid))
        for key in _keyed(entry[1]):
            grid.setdefault(key, []).append(entry)
    for entry in _floors(blueprint):
        for key in _keyed(entry[1]):
            grid.setdefault(key, []).append(entry)

    for massing in blueprint.elements(Massing):
        if massing.note in (FLOATS_ON_PURPOSE, "camping cap (Z46)"):
            continue  # the map said so, once, on the geometry (or Z46 capped a top)
        mine = {id(solid) for solid in massing.solids}
        for solid in massing.solids:
            box = _solid_bounds(solid)
            nearby: dict[int, Span] = {}
            for key in _keyed(box):
                for marker, other in grid.get(key, ()):
                    if marker not in mine:
                        nearby[marker if marker >= 0 else id(other)] = other
            if any(
                _rests_on(box, other)
                or _hangs_from(box, other)
                or _fixed_to(box, other)
                for other in nearby.values()
            ):
                continue
            if _on_terrain(terrains, box):
                continue
            spot = box.centre
            report.add(
                error(
                    "Z43",
                    f"{massing.id} stands on nothing: there is no floor, "
                    "solid or terrain within "
                    f"{HANG_SLACK:g} units under it, nothing that close over "
                    "it, and no wall it is flush against, so it hangs in the "
                    f"air with its underside at z={box.mins.z:g}. Either it is "
                    "in the wrong place -- which is what a block positioned by "
                    "arithmetic rather than by the thing it joins looks like "
                    "-- or the map means it, and says so with "
                    f"note={FLOATS_ON_PURPOSE!r}",
                    massing.id,
                    f"({spot.x:g}, {spot.y:g}, {box.mins.z:g})",
                )
            )
    return report
