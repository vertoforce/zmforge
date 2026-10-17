"""Z46: can a *zombie* get onto everything a player can stand and fight on?

WHY THIS IS A SEPARATE QUESTION FROM EVERY CHECK BESIDE IT
-----------------------------------------------------------
``Z25`` floods the map as a player: it jumps 39 units, leaps 80 of air and
survives a 256-unit drop.  ``N1`` refuses a tread taller than the navmesh
generator's ``maxStepHeight``.  ``H1`` reads the mesh the compiler wrote and
asks whether it is joined up.  A staircase of bare brush treads passes all
three and the walkers still do not climb it, which is the defect this check
exists for: only playing the map shows it, not building it.

Measured on a map with a 17-tread flight of brush stairs, as played:

* ``cod2map64 -platform pc -navmesh`` **does** lay walkable surface up the
  flight -- one simplified face climbing from z 34.8 to z 279.9 -- and that
  face is joined to the ground at its foot and to the landing at its head, so
  a breadth-first search over the compiled mesh walks from bottom to top in
  three faces.  ``H1`` therefore has nothing to say, and neither does anything
  else: the whole run reports ``0 error(s)``.
* Treyarch's own flights are not built the way ours were.  In
  ``_prefabs/zm/zm_giant/geo/zm_giant_zone_c_stairs_2.map`` the 23 treads are
  ``misc_prefab`` tread *models*, which carry no collision, and the only solid
  thing over the flight is one ``metal_clip_nosight`` wedge whose sloped face
  spans the flight's whole 220 of run and 176 of rise.  Its sister flight
  ``zm_giant_zone_c_stairs_1.map`` is the same in ``metal_clip``.  So what a
  walker's capsule slides along on a shipped map is a *plane*; the steps are
  scenery.

The mesh says "walk here"; the collision the walker is actually pushed around
by is a stack of vertical risers.  This check is the model-level statement of
the difference, in two halves:

``a flight with no clip ramp``
    every walkable flight of two treads or more carries the wedge
    :meth:`~zmforge.blueprint.model.Blueprint.add_steps` now lays over it
    (note :data:`~zmforge.blueprint.elements.STAIR_CLIP`).  A recipe that
    passes ``clip_ramp=False`` is saying "nothing climbs this", and then the
    flight has to be declared ``reachable=False`` as well or this check says
    so.

``floor a player reaches and the zombie rules do not``
    the same flood ``Z25`` runs, run a second time with the walkers' own
    movement: **no jump, no leap across a gap**, and a rise of at most
    :data:`~zmforge.verify.documented.MAX_STEP_HEIGHT`, the navmesh
    generator's own ``maxStepHeight``.  The difference between the two floods
    is, exactly, the floor a player can stand on and fight from where nothing
    can follow -- a safe spot, which on a zombies map is the whole game.

What is deliberately out of reach is *declared*, not skipped
------------------------------------------------------------
A map is allowed places nothing can follow the player to: a barn's tie beams,
a lamp hung on a chain, a decorative ledge.  The flag that
says so is the one the model already carries, ``reachable=False``
(:func:`~zmforge.verify.reachability._declared_unreachable`), and a surface
carrying it produces no standing room at all, so it cannot be a finding here.
That is exactly the way a deliberate exception goes quiet without anybody
noticing it went quiet, so every one of them is **printed**, as a ``Z46``
warning naming the surface and its height.  A reader of the report sees the
list of places the map has decided zombies never reach, and can disagree with
it.
"""

from __future__ import annotations

from collections import deque
from typing import Sequence

from ..blueprint.elements import STAIR_CLIP, Massing, Room
from ..blueprint.model import _solid_bounds
from ..spatial import Axis, Span
from .documented import MAX_STEP_HEIGHT
from .model import PLAYER_HULL_WIDTH
from .reachability import (
    Flood,
    Standing,
    TOUCH,
    _buckets,
    _seed_cells,
    flood_from_spawn,
    standing_cells,
)
from .report import Report, error, warning

__all__ = ["check_zombie_climb", "zombie_flood", "zombie_how"]


def zombie_how(here: Standing, there: Standing) -> str | None:
    """How a walker gets from ``here`` to ``there``, or ``None`` if it cannot.

    :func:`~zmforge.verify.reachability._how` with the player's two abilities
    taken away.  A zombie has no jump -- nothing in the shipped AI raises one
    onto a ledge it cannot step onto -- so the only climb is a step, and the
    tallest step is the one the navmesh generator itself will lay surface
    over.  Falling is left alone: a walker goes off a ledge the same way a
    player does, and a drop is not what a staircase defect looks like.
    """
    over_x = min(here.floor.maxs.x, there.floor.maxs.x) - max(
        here.floor.mins.x, there.floor.mins.x
    )
    over_y = min(here.floor.maxs.y, there.floor.maxs.y) - max(
        here.floor.mins.y, there.floor.mins.y
    )
    if over_x < -TOUCH or over_y < -TOUCH:
        return None
    if over_x <= TOUCH and over_y <= TOUCH:
        return None  # a corner is not a way through
    rise = there.z - here.z
    if rise > MAX_STEP_HEIGHT:
        return None
    if rise >= 0.0:
        return "walked up"
    return "walked down"


def zombie_flood(blueprint) -> Flood:
    """Which standing rectangles a walker can get to, from the spawn floor.

    Seeded from the initial-spawn slots, the same places :func:`Z25
    <zmforge.verify.reachability.check_reachability>` seeds from: the players
    start on the ground floor and so do the walkers, so "can a zombie get from
    where the round starts to here" is the question a safe spot answers no to.
    """
    cells = standing_cells(blueprint)
    grid: dict[tuple[int, int], list[int]] = {}
    for index, cell in enumerate(cells):
        for key in _buckets(cell):
            grid.setdefault(key, []).append(index)

    seeds = _seed_cells(blueprint, cells)
    reached = set(seeds)
    queue = deque(seeds)
    while queue:
        index = queue.popleft()
        here = cells[index]
        nearby: set[int] = set()
        for key in _buckets(here):
            nearby.update(grid.get(key, ()))
        for other in nearby:
            if other in reached:
                continue
            if zombie_how(here, cells[other]) is None:
                continue
            reached.add(other)
            queue.append(other)
    return Flood(tuple(cells), frozenset(reached), tuple(seeds))


def _clip_ramps(blueprint) -> list[Span]:
    return [
        _solid_bounds(solid)
        for element in blueprint.elements(Massing)
        if element.note == STAIR_CLIP
        for solid in element.solids
    ]


def _covers(ramp: Span, flight: Span) -> bool:
    """Is ``ramp`` the clip over ``flight``?

    Plan overlap on both axes and a shared height band is enough: the ramp is
    built from the flight's own arithmetic, one tread short of its run, so it
    can never be a ramp that belongs to a different flight without also
    standing inside this one.
    """
    return (
        min(ramp.maxs.x, flight.maxs.x) - max(ramp.mins.x, flight.mins.x) > TOUCH
        and min(ramp.maxs.y, flight.maxs.y) - max(ramp.mins.y, flight.mins.y) > TOUCH
        and min(ramp.maxs.z, flight.maxs.z) - max(ramp.mins.z, flight.mins.z) > TOUCH
    )


def _check_flights_are_clipped(blueprint, report: Report) -> None:
    ramps = _clip_ramps(blueprint)
    for element in blueprint.elements(Massing):
        if element.note != "steps" or not element.walkable:
            continue
        if not element.reachable:
            continue
        boxes = [_solid_bounds(solid) for solid in element.solids]
        if len(boxes) < 2:
            continue  # one step is a kerb, and a kerb is stepped over
        span = Span.between(
            type(boxes[0].mins)(
                min(b.mins.x for b in boxes),
                min(b.mins.y for b in boxes),
                min(b.mins.z for b in boxes),
            ),
            type(boxes[0].maxs)(
                max(b.maxs.x for b in boxes),
                max(b.maxs.y for b in boxes),
                max(b.maxs.z for b in boxes),
            ),
        )
        if any(_covers(ramp, span) for ramp in ramps):
            continue
        report.add(
            error(
                "Z46",
                f"this flight of {len(boxes)} treads has no clip ramp over it, "
                "so the only thing a walker's capsule meets on the way up is a "
                "riser per tread; every staircase in Treyarch's own source "
                "(_prefabs/zm/zm_giant/geo/zm_giant_zone_c_stairs_1 and _2) is "
                "tread models under one sloped clip brush, and the navmesh "
                "will not say this is wrong -- it lays a smooth face up the "
                "flight either way",
                element.id,
            )
        )


def _declared_out_of_reach(blueprint, report: Report) -> None:
    """Print the surfaces the map has declared nothing can get onto.

    A warning per surface, so a deliberate exception is a line in the report
    rather than an absence of one.
    """
    for room in blueprint.elements(Room):
        if room.reachable:
            continue
        report.add(
            warning(
                "Z46",
                f"declared out of reach: the floor of room {room.id} at z "
                f"{room.floor_z:g}; no walker is expected to path onto it and "
                "no finding below counts it",
                room.id,
            )
        )
    for element in blueprint.elements(Massing):
        if element.reachable or not element.walkable:
            continue
        tops = [_solid_bounds(solid).maxs.z for solid in element.solids]
        if not tops:
            continue
        report.add(
            warning(
                "Z46",
                f"declared out of reach: {element.note or 'massing'} "
                f"{element.id}, {len(tops)} surface(s) topping out at z "
                f"{max(tops):g}; no walker is expected to climb it",
                element.id,
            )
        )


#: :attr:`Massing.note` of the massings that are *routes* rather than
#: furniture.  The distinction, and the words for it, are ``H1``'s: "a room
#: floor, a terrain cell and a flight of steps are routes and are errors; the
#: top of any other walkable massing is a warning, because a table nothing can
#: climb is what a table is and a platform nothing can climb is the defect,
#: and the model does not say which of its slabs is which."  A deck, a landing
#: and a flight are how a storey is got to and are errors here; a counter, a
#: bunk and a crate are cover, and a zombie that cannot climb one is a zombies
#: map working.
ROUTE_NOTES = frozenset({"steps", "slab", STAIR_CLIP})


def _route_ids(blueprint) -> set[str]:
    ids = {room.id for room in blueprint.elements(Room)}
    ids |= {
        element.id
        for element in blueprint.elements(Massing)
        if element.note in ROUTE_NOTES
    }
    return ids


def _check_no_safe_spots(blueprint, report: Report) -> None:
    routes = _route_ids(blueprint)
    player = flood_from_spawn(blueprint)
    walkers = zombie_flood(blueprint)
    worst: dict[tuple[str, str], tuple[float, Span, float]] = {}
    for index, cell in enumerate(player.cells):
        if index not in player.reached or index in walkers.reached:
            continue
        if cell.sill:
            continue  # a window ledge is a way through, not a place to fight
        if (
            cell.floor.extent(Axis.X) < PLAYER_HULL_WIDTH
            or cell.floor.extent(Axis.Y) < PLAYER_HULL_WIDTH
        ):
            continue
        area = cell.floor.extent(Axis.X) * cell.floor.extent(Axis.Y)
        total, biggest, _z = worst.get(
            (cell.label, cell.element_id), (0.0, cell.floor, cell.z)
        )
        if area > biggest.extent(Axis.X) * biggest.extent(Axis.Y):
            biggest = cell.floor
        worst[(cell.label, cell.element_id)] = (total + area, biggest, cell.z)
    rooms = [room for room in blueprint.elements(Room) if room.reachable]
    for (label, element_id), (area, biggest, z) in sorted(
        worst.items(), key=lambda item: -item[1][0]
    ):
        spot = biggest.centre
        speak = error if element_id in routes else warning
        if speak is warning and _low_cover_in_play(
            blueprint, rooms, element_id, spot.x, spot.y, z
        ):
            # A top under LOW_SAFE_TOP over the floor
            # of a playable room is a step a player makes in one jump and no
            # zombie follows -- a free safe spot, not cover.  An error unless
            # the element says reachable=False.
            speak = error
        report.add(
            speak(
                "Z46",
                f"{label} has {area:.0f} square units of standing room at z "
                f"{z:g} that a player reaches and the walkers' own movement "
                f"does not, the largest piece around ({spot.x:g}, {spot.y:g}); "
                "a zombie has no jump and steps at most "
                f"{MAX_STEP_HEIGHT:g} units, so this is a place to stand and "
                "fight that nothing can follow the player onto. Build the "
                "route (a clipped flight, a ramp, a landing within one step) "
                "or declare the surface reachable=False and mean it"
                + ("" if element_id in routes else "; a warning and not an "
                   "error because this is cover rather than a route, and a "
                   "crate nothing can climb is what a crate is"),
                element_id,
            )
        )


def check_zombie_climb(blueprint) -> Report:
    """Z46 over a blueprint: the flights, the safe spots and the exceptions."""
    report = Report()
    _check_flights_are_clipped(blueprint, report)
    _declared_out_of_reach(blueprint, report)
    _check_no_safe_spots(blueprint, report)
    # Every collision surface, not only the declared floors: prop and brush
    # tops, stair rails and pockets, with the stock melee reach counted
    # (zm_cemetery; zmforge.verify.camping).
    from .camping import check_camping_spots

    report.extend(check_camping_spots(blueprint))
    return report


#: A zombie-proof standing top lower than this over the floor of a playable
#: room is an error, not a warning: a player gets
#: onto it in one jump and fights from it untouched.
LOW_SAFE_TOP = 64.0


def _low_cover_in_play(blueprint, rooms, element_id, x, y, z) -> bool:
    try:
        element = blueprint.find(element_id) if element_id else None
    except Exception:
        element = None
    if element is not None and getattr(element, "reachable", True) is False:
        return False  # declared: the map means it
    if element is not None and getattr(element, "walkable", False):
        # walkable=True is the map declaring the top a surface people stand
        # on, built at that height on purpose; only a top nobody declared is
        # the error.
        return False
    for room in rooms:
        interior = room.interior
        if not interior.holds_flat(x, y):
            continue
        if room.floor_z - 1.0 <= z <= interior.maxs.z:
            return z - room.floor_z < LOW_SAFE_TOP
    return False
