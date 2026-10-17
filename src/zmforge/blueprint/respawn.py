"""Where a bled-out player comes back: one respawn group per zone.

The stock respawn pick needs a *group* behind every ``player_respawn_point``.
``_zm.gsc:3361 check_for_valid_spawn_near_team`` picks the respawn struct
nearest a living team mate among those whose zone is enabled
(``script_noteworthy`` is the zone name, ``_zm_zonemgr.gsc:504-510`` unlocks
it), then ``:3453 get_valid_spawn_location`` reads
``struct::get_array( spawn_points[closest_group].target, "targetname" )`` and
hands out the first point nobody stands on.  A struct with no ``target`` gives
an empty array, the pick returns ``undefined``, and ``spectator_respawn``
falls back to the player's own initial spawn struct (``:3282``, ``:3315``):
the player comes back where the game started, not beside the team.

Shipped ``zm_giant.map`` carries nine respawn structs, one per zone, each
``script_int 2000`` / ``radius 2000`` with a ``target`` naming four
``script_struct`` points a few dozen units apart, ``script_int`` 1 to 4
(the start zone's struct targets ``initial_spawn_points`` itself).  This
module lays out the same thing for any blueprint: per zone, a group of
:func:`group_size` points on walkable floor inside the zone, clear of world
solids, doors, props, interactives and barricades, and the respawn struct on
the group's anchor, so the struct's origin is inside the zone it names (the
pick skips a struct outside an enabled zone, ``_zm.gsc:3397``).

Zones a script seals (:attr:`PlayerStart.sealed_zones`, set by
:func:`zmforge.script.splitstart.install_split_start`) get no group: a
respawn there is what Z78 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from ..spatial import Point, Span

if TYPE_CHECKING:  # pragma: no cover
    from .model import Blueprint

__all__ = [
    "GRID",
    "SPACING",
    "PLAYER_HALF",
    "PLAYER_HEIGHT",
    "RespawnGroup",
    "group_size",
    "respawn_groups",
    "target_name",
]

#: Candidate spacing inside a zone.
GRID = 32.0
#: Least distance between two points of one group.  Stock ``zm_giant`` groups
#: are 50 to 65 units apart; a player hull is 30 wide, so 48 keeps two
#: respawning players from overlapping and away from the telefrag test.
SPACING = 48.0
#: The fallback spacing in a crowded zone: a 30-unit hull and six of air.
TIGHT_SPACING = 36.0
#: Half a player's hull, plus a unit of air.
PLAYER_HALF = 16.0
#: A standing player's height.
PLAYER_HEIGHT = 72.0
#: Anything this far above the floor or more is in the player's body; lower
#: than this is a seam in the ground, not an obstacle.
FOOT = 4.0
#: No point nearer than this to an interactive origin or a barricade.
CLEAR_OF_USE = 72.0
CLEAR_OF_BARRICADE = 96.0
#: A walk-through prop taller than this is avoided while there is room.
SOFT_PROP_HEIGHT = 24.0
#: Terrain a point stands on may vary this much under the body.
MAX_SPREAD = 4.0
#: Most points a group gets (a higher-player mod's eight).
MAX_POINTS = 8
STOCK_POINTS = 4


@dataclass(frozen=True)
class RespawnGroup:
    """One zone's respawn struct (at :attr:`anchor`) and its target points."""

    zone: str
    anchor: Point
    points: tuple[Point, ...]

    @property
    def target(self) -> str:
        return target_name(self.zone)


def target_name(zone: str) -> str:
    """The ``targetname`` a zone's respawn points share."""
    return f"{zone}_respawn_points"


def group_size(slots: int) -> int:
    """Points per group: one per player slot, four to eight."""
    return max(STOCK_POINTS, min(MAX_POINTS, int(slots)))


def _obstacles(bp: "Blueprint") -> tuple[list[Span], list[Span]]:
    """``(hard, soft)``: what a player collides with, and walk-through props
    tall enough that a player appearing inside one would look wrong (tried
    to avoid, given up in a crowded zone's last pass)."""
    from ..emit.mapfile import _room_solids, _terrain_columns, _terrain_plinth, _yard_solids
    from ..script.gobblegum import _prop_box
    from .elements import Door, Massing, PropScatter, Room, Terrain, Yard
    from .model import _solid_bounds

    # Every brush a player collides with.  Not Blueprint.world_solids: that
    # is the BSP-overlap scan's list and drops detail brushes, all-caulk
    # solids and scripted brush groups, all of which a player stands in
    # (a test map: a respawn point 10 units into a detail wall,
    # caught by Z86's brush test).
    solids = [s for room in bp.elements(Room) for s in _room_solids(room)]
    solids += [s for yard in bp.elements(Yard) for s in _yard_solids(yard)]
    solids += [s for massing in bp.elements(Massing) for s in massing.solids]
    for terrain in bp.elements(Terrain):
        solids += _terrain_columns(terrain) + _terrain_plinth(terrain)
    boxes = [_solid_bounds(s) for s in solids
             if not any("noncolliding" in c.lower() for c in s.contents)]
    for door in bp.elements(Door):
        if door.box is not None:
            boxes.append(door.box)
    soft: list[Span] = []
    for scatter in bp.elements(PropScatter):
        for prop in scatter.props:
            span = _prop_box(prop)
            if span is not None:
                x0, y0, z0, x1, y1, z1 = span
                box = Span(Point(x0, y0, z0), Point(x1, y1, z1))
                if prop.solid:
                    boxes.append(box)
                elif z1 - z0 > SOFT_PROP_HEIGHT:
                    soft.append(box)
    # The item itself, not its apron: a player may stand where a buyer
    # stands, and in a 128-unit room the aprons are the whole floor.
    for keep in bp.interactive_keeps():
        boxes.append(keep.body)
    return boxes, soft


def _keep_away(bp: "Blueprint") -> list[tuple[Point, float]]:
    from .elements import (Machine, MysteryBox, PowerSwitch, Spawn, WallWeapon,
                           Window, Wunderfizz)

    out: list[tuple[Point, float]] = []
    for kind in (Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz):
        for element in bp.elements(kind):
            position = getattr(element, "position", None)
            if position is not None:
                out.append((position, CLEAR_OF_USE))
    for window in bp.elements(Window):
        if window.barricade_origin is not None:
            out.append((window.barricade_origin, CLEAR_OF_BARRICADE))
    for spawn in bp.elements(Spawn):
        if spawn.position is not None:
            out.append((spawn.position, SPACING))
    return out


def body_at(spot: Point) -> Span:
    """The box a player standing at ``spot`` fills, feet excluded."""
    return Span(
        Point(spot.x - PLAYER_HALF, spot.y - PLAYER_HALF, spot.z + FOOT),
        Point(spot.x + PLAYER_HALF, spot.y + PLAYER_HALF, spot.z + PLAYER_HEIGHT),
    )


def _hits(body: Span, boxes: Sequence[Span]) -> bool:
    return any(
        b.mins.x < body.maxs.x and b.maxs.x > body.mins.x
        and b.mins.y < body.maxs.y and b.maxs.y > body.mins.y
        and b.mins.z < body.maxs.z and b.maxs.z > body.mins.z
        for b in boxes
    )


class _Ground:
    """:meth:`Blueprint.ground_under` with its surfaces gathered once.

    The same three sources and the same pick (terrain over the room floor it
    lies on, the highest surface no more than a step above ``below``); the
    model's own method re-reads every element per call, which on ``zm_dmv``
    was 4 ms a point and 17 s a map.  ``tests/test_respawn.py`` holds the two
    to the same answer.  Unlike the model's, a room or yard floor carries its
    element's ``reachable`` flag.
    """

    def __init__(self, bp: "Blueprint") -> None:
        from .elements import Massing, Room, Terrain, Yard
        from .model import _solid_bounds

        self.terrain = list(bp.elements(Terrain))
        self.platforms = [
            (_solid_bounds(solid), massing.reachable)
            for massing in bp.elements(Massing) if massing.walkable
            for solid in massing.solids
        ]
        self.floors = [
            (el.interior, el.floor_z, getattr(el, "reachable", True))
            for kind in (Room, Yard) for el in bp.elements(kind)
        ]

    def under(self, x: float, y: float, below: float) -> tuple[float, float, bool] | None:
        """``(z, spread, reachable)`` of the surface under ``(x, y)``, or None."""
        from .model import STEP_TOLERANCE

        hits: list[tuple[float, float, bool]] = []
        for terrain in self.terrain:
            sample = terrain.record.sample(x, y)
            if sample.found:
                hits.append((sample.z, sample.spread, True))
        terrain_found = bool(hits)
        for box, reachable in self.platforms:
            if box.holds_flat(x, y):
                hits.append((box.maxs.z, 0.0, reachable))
        if not terrain_found:
            for interior, z, reachable in self.floors:
                if interior.holds_flat(x, y):
                    hits.append((z, 0.0, reachable))
        if not hits:
            return None
        allowed = [h for h in hits if h[0] <= below + STEP_TOLERANCE] or hits
        return max(allowed, key=lambda h: h[0])


def _candidates(bp: "Blueprint", bounds: Span, boxes: Sequence[Span],
                away: Sequence[tuple[Point, float]], sealed: Sequence[Span],
                floor: "_Ground | None" = None, grid: float = GRID) -> list[Point]:
    lo, hi = bounds.mins, bounds.maxs
    floor = floor or _Ground(bp)
    reach = bounds.grown(PLAYER_HALF + PLAYER_HEIGHT)
    near = [b for b in boxes if b.overlaps(reach)]
    out: list[Point] = []
    nx = int((hi.x - lo.x - 2 * GRID) // grid) + 1
    ny = int((hi.y - lo.y - 2 * GRID) // grid) + 1
    for i in range(max(nx, 0)):
        x = lo.x + GRID + i * grid
        for j in range(max(ny, 0)):
            y = lo.y + GRID + j * grid
            ground = floor.under(x, y, hi.z - PLAYER_HEIGHT)
            if ground is None:
                continue
            z, spread, reachable = ground
            if not reachable or spread > MAX_SPREAD:
                continue
            spot = Point(x, y, z)
            if not (lo.z <= z + 1.0 and z + PLAYER_HEIGHT <= hi.z + 1.0):
                continue
            if any(s.holds(Point(x, y, z + 1.0)) for s in sealed):
                continue
            if any(abs(p.z - spot.z) < 96.0
                   and (p.x - x) ** 2 + (p.y - y) ** 2 < r * r for p, r in away):
                continue
            if _hits(body_at(spot), near):
                continue
            out.append(spot)
    return out


def _pick(candidates: list[Point], centre: Point, count: int,
          spacing: float = SPACING) -> tuple[Point, ...]:
    """The most open candidate near the zone's middle, and its nearest
    neighbours at least :data:`SPACING` apart."""
    if not candidates:
        return ()

    cells: dict[tuple[int, int], list[Point]] = {}
    for q in candidates:
        cells.setdefault((round(q.x / GRID), round(q.y / GRID)), []).append(q)
    reach = 3  # grid steps: 96 units

    def openness(p: Point) -> int:
        i, j = round(p.x / GRID), round(p.y / GRID)
        return sum(1 for di in range(-reach, reach + 1) for dj in range(-reach, reach + 1)
                   for q in cells.get((i + di, j + dj), ()) if abs(q.z - p.z) < 8.0)

    anchor = min(candidates, key=lambda p: (-openness(p), (p.x - centre.x) ** 2
                                            + (p.y - centre.y) ** 2, p.x, p.y))
    chosen = [anchor]
    for p in sorted(candidates, key=lambda q: (q.distance_to(anchor), q.x, q.y)):
        if len(chosen) >= count:
            break
        if abs(p.z - anchor.z) > 18.0:
            continue
        if all(p.distance_to(c) >= spacing for c in chosen):
            chosen.append(p)
    return tuple(chosen)


def respawn_groups(bp: "Blueprint") -> list[RespawnGroup]:
    """One group per unsealed zone that has room for at least one point.

    Deterministic: the same blueprint gives the same points.  A zone with no
    clear floor gets no group (``Z86`` warns about it).
    """
    from .elements import PlayerStart, Zone

    starts = bp.elements(PlayerStart)
    if not starts:
        return []
    start = starts[0]
    sealed_names = set(getattr(start, "sealed_zones", ()) or ())
    zones = [z for z in bp.elements(Zone) if z.bounds is not None]
    sealed = [z.bounds for z in zones if z.name in sealed_names]
    hard, soft = _obstacles(bp)
    away = _keep_away(bp)
    count = group_size(start.slots)
    floor = _Ground(bp)
    volumes: dict[str, list[Span]] = {}
    for zone in zones:
        if zone.name not in sealed_names:
            volumes.setdefault(zone.name, []).append(zone.bounds)
    groups: list[RespawnGroup] = []
    for name, bounds in volumes.items():
        points: tuple[Point, ...] = ()
        # A crowded room gets a finer grid and the hull's own spacing before
        # it is allowed fewer points than players.
        # Last, a quarter grid, hull-width spacing and half the keep-away
        # (zm_dmv's eye exam and break room, 260 units square and full).
        for grid, spacing, keep in ((GRID, SPACING, 1.0), (GRID / 2.0, TIGHT_SPACING, 1.0),
                                    (GRID / 4.0, 2.0 * PLAYER_HALF, 0.5)):
            clear = [(p, r * keep) for p, r in away]
            boxes = hard + soft if keep == 1.0 else hard
            candidates = [p for b in bounds
                          for p in _candidates(bp, b, boxes, clear, sealed, floor, grid)]
            points = _pick(candidates, bounds[0].centre, count, spacing)
            if len(points) >= count:
                break
        if points:
            groups.append(RespawnGroup(name, points[0], points))
    return groups

