"""The play lamp: every buyable and door gets a lamp within reach, on every map.

WHY
---
``D5`` ("no lamp within 192 units of a door or buyable") fires on most
maps without this: a perk machine outdoors at night, buyables under a moon
and nothing else, a machine in a gap between grid lamps.
:meth:`Blueprint.light_rooms` only fills *room*
interiors on a grid, so anything outdoors, in a sunlit room or between two
grid points misses out, and a buyable in a dark gap is a buyable a player
walks past.

THE RULE
--------
After the fill grid, :func:`light_play` walks every perk machine, mystery box,
Wunderfizz, power switch, wall buy and door.  One with no lamp within
:data:`PLAY_LIGHT` in plan (the same test ``D5`` makes: within the lamp's own
radius, and the lamp no more than 64 below or 512 above the thing) gets a
lamp of its own:

* in front of it (a door: on whichever side is not buried), :data:`LIFT`
  units over its floor and never closer than
  :data:`~zmforge.lighting.CEILING_CLEARANCE` under the ceiling of the room
  it is in;
* in the map's lamp style -- the colour and radius of the nearest lamp
  already placed, and the brightness (``stops``) of the brightest lamp within
  512 units, so it is never dimmer than the filler around it;
* shadowless, because a map has a fixed number of omni shadow slices and a
  lamp placed to raise the light level has no business spending one.

Idempotent: a thing lit once is lit, so a second call adds nothing.
"""

from __future__ import annotations

import math

from ..lighting import CEILING_CLEARANCE, is_glow
from ..spatial import Axis, Point

__all__ = ["PLAY_LIGHT", "LIFT", "FRONT", "play_things", "light_play", "DARK_REACH", "DARK_STRETCH",
           "PATH_STEP", "dark_stretches", "light_paths"]

#: ``D5``'s own reach: a lamp within this many units in plan lights the thing.
PLAY_LIGHT = 192.0
#: How far over the thing's floor the lamp hangs, ceiling permitting.
LIFT = 96.0
#: How far in front of the thing's face the lamp hangs.
FRONT = 48.0
#: Nothing gets a radius smaller than this from the style it copies.
MIN_RADIUS = 256.0


def play_things(bp) -> list[tuple[str, Point, tuple[Point, ...]]]:
    """``(id, floor point, candidate lamp offsets)`` per door and buyable."""
    from .elements import Door, Machine, MysteryBox, PowerSwitch, WallWeapon, Wunderfizz
    from ..spatial import Facing

    out = []
    for door in bp.elements(Door):
        box = door.box
        c = box.centre
        floor = Point(c.x, c.y, box.mins.z)
        thin = Axis.X if box.extent(Axis.X) < box.extent(Axis.Y) else Axis.Y
        offsets = tuple(
            Point(sign * FRONT, 0.0, 0.0) if thin is Axis.X else Point(0.0, sign * FRONT, 0.0)
            for sign in (1.0, -1.0)
        )
        out.append((door.id, floor, offsets))
    for kind in (Machine, MysteryBox, PowerSwitch, Wunderfizz, WallWeapon):
        for element in bp.elements(kind):
            step = Facing.of(element.facing).step
            ahead = Point(step.x * FRONT, step.y * FRONT, 0.0)
            floor = Point.of(element.position)
            if kind is WallWeapon:
                floor = Point(floor.x, floor.y, floor.z + 8.0)
            out.append((element.id, floor, (ahead, Point(0.0, 0.0, 0.0))))
    return out


def _lit(lamps, point: Point) -> bool:
    for lamp in lamps:
        p = lamp.position
        d = math.hypot(p.x - point.x, p.y - point.y)
        if d <= PLAY_LIGHT and d <= lamp.radius and point.z - 64.0 <= p.z <= point.z + 512.0:
            return True
    return False


def _room_over(bp, point: Point):
    from .elements import Room, Yard

    for kind in (Room, Yard):
        for room in bp.elements(kind):
            interior = room.interior
            if (interior.holds_flat(point.x, point.y)
                    and interior.mins.z - 8.0 <= point.z <= interior.maxs.z):
                return room
    return None


def _buried_test(bp):
    from ..solids.halfspace import plane_through

    planes = [
        [plane_through(*face.points) for face in solid.faces]
        for solid in bp.world_solids()
    ]

    def buried(point: Point) -> bool:
        for faces in planes:
            if min(face.depth_at(point) for face in faces) > 1e-6:
                return True
        return False

    return buried


def light_play(bp) -> list:
    """Give every unlit door and buyable a shadowless lamp; return the new lamps."""
    from .elements import Lamp, Room

    lamps = list(bp.elements(Lamp))
    things = [t for t in play_things(bp) if not _lit(lamps, t[1])]
    if not things:
        return []
    buried = _buried_test(bp)
    added = []
    for thing_id, floor, offsets in things:
        if _lit(lamps, floor):
            continue  # an earlier play lamp already reaches it
        for offset in offsets:
            spot = Point(floor.x + offset.x, floor.y + offset.y, floor.z + 8.0)
            room = _room_over(bp, spot)
            z = floor.z + LIFT
            if isinstance(room, Room):
                ceiling = room.shell.ceiling_underside_z - CEILING_CLEARANCE
                if ceiling <= floor.z + 16.0:
                    continue
                z = min(z, ceiling)
            point = Point(spot.x, spot.y, z)
            if buried(point):
                continue
            nearest = min(
                # a glow is no style to copy (lighting.is_glow; D8)
                [l for l in lamps if not is_glow(l.radius)] or lamps,
                key=lambda l: (l.position.x - point.x) ** 2 + (l.position.y - point.y) ** 2
                + (l.position.z - point.z) ** 2,
                default=None,
            )
            colour = nearest.colour if nearest is not None else (1.0, 1.0, 1.0)
            radius = max(MIN_RADIUS, nearest.radius if nearest is not None else 512.0)
            nearby = [
                l for l in lamps
                if math.hypot(l.position.x - point.x, l.position.y - point.y) <= 512.0
            ]
            stops = None
            if nearby:
                brightest = max(nearby, key=bp.stops_of)
                stops = brightest.stops
            zone = bp._zone_name_over(room) if isinstance(room, Room) else None
            lamp = bp.place_light(
                point, colour=colour, radius=radius, stops=stops, zone_name=zone,
                shadows=False, id=f"{thing_id}_play_lamp",
            )
            lamps.append(lamp)
            added.append(lamp)
            break
    return added


# ---------------------------------------------------------------------------
# Walk paths: no long dark stretch (D7)
# ---------------------------------------------------------------------------
# Lamps on a grid leave dark spots between them.  The corn
# maze's moon lamps stand on every other cell each way, so the diagonal cells
# between them were 362 units from any lamp, and the dark runs along the
# paths reached 448 units.  A map that declares its walk paths
# (``bp.walk_paths``: polylines of floor points, the maze's cell-to-cell
# passages) gets a lamp in the middle of every dark stretch longer than
# :data:`DARK_STRETCH`, through the recipe's own *fixture* (a lantern, a fire
# barrel), so the path reads as pools of light with dark between them, not
# as flat brightness.

#: A path point with no lamp this near in plan is dark (D5's ``DARK_GAP``).
DARK_REACH = 256.0
#: The longest dark stretch of walk path a map may keep (D7 warns above it).
DARK_STRETCH = 320.0
#: How finely a walk path is sampled.
PATH_STEP = 32.0


def _lamp_grid(lamps):
    grid: dict = {}
    for lamp in lamps:
        p = lamp.position
        grid.setdefault((int(p.x // DARK_REACH), int(p.y // DARK_REACH)), []).append(lamp)
    return grid


def _dark(grid, x: float, y: float, z: float) -> bool:
    cx, cy = int(x // DARK_REACH), int(y // DARK_REACH)
    for gx in (cx - 1, cx, cx + 1):
        for gy in (cy - 1, cy, cy + 1):
            for lamp in grid.get((gx, gy), ()):
                p = lamp.position
                d = math.hypot(p.x - x, p.y - y)
                if d <= DARK_REACH and d <= lamp.radius and z - 64.0 <= p.z <= z + 512.0:
                    return False
    return True


def _samples(paths):
    """Sample nodes ``(x, y, z)`` rounded to the unit, and their neighbours
    along the paths (shared end points join two paths)."""
    adj: dict = {}
    for path in paths:
        prev = None
        for a, b in zip(path, path[1:]):
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // PATH_STEP))
            for k in range(n + 1):
                t = k / n
                node = (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t),
                        round(a[2] + (b[2] - a[2]) * t))
                adj.setdefault(node, set())
                if prev is not None and prev != node:
                    adj[prev].add(node)
                    adj[node].add(prev)
                prev = node
    return adj


def dark_stretches(bp, paths=None) -> list[tuple[float, list[tuple[int, int, int]]]]:
    """Every dark stretch of the declared walk paths, longest first:
    ``(length, the samples along its longest run)``."""
    from .elements import Lamp

    paths = getattr(bp, "walk_paths", None) if paths is None else paths
    if not paths:
        return []
    adj = _samples(paths)
    grid = _lamp_grid(bp.elements(Lamp))
    dark = {n for n in adj if _dark(grid, *n)}

    def sweep(start, comp):
        dist, back, stack = {start: 0.0}, {start: None}, [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v in comp and v not in dist:
                    dist[v] = dist[u] + math.hypot(v[0] - u[0], v[1] - u[1])
                    back[v] = u
                    stack.append(v)
        far = max(dist, key=lambda n: (dist[n], n))
        return far, dist[far], back

    out, seen = [], set()
    for s in sorted(dark):
        if s in seen:
            continue
        comp, stack = set(), [s]
        while stack:
            u = stack.pop()
            if u not in comp:
                comp.add(u)
                stack += [v for v in adj[u] if v in dark and v not in comp]
        seen |= comp
        t, _, _ = sweep(s, comp)
        u, length, back = sweep(t, comp)
        run = [u]
        while back[run[-1]] is not None:
            run.append(back[run[-1]])
        out.append((length, run))
    out.sort(key=lambda r: -r[0])
    return out


def light_paths(bp, fixture=None, *, stretch: float = DARK_STRETCH, colour=None, radius: float = 300.0,
                limit: int = 400, id_prefix: str = "path") -> list:
    """Put a lamp in the middle of every dark stretch of ``bp.walk_paths``
    longer than *stretch*, worst first, until none is.  *fixture*
    ``(point, (dx, dy)) -> Point | None`` dresses the spot (a lantern on the
    ground, a fire barrel) and says where its light hangs, or refuses it;
    without one the lamp hangs :data:`LIFT` over the path.  The lamps are
    shadowless, *radius* in reach, in *colour* (default: the nearest lamp's).
    Returns the new lamps."""
    from .elements import Lamp

    added: list = []
    refused: set = set()
    for _ in range(limit):
        runs = [r for r in dark_stretches(bp) if r[0] > stretch]
        target = None
        for length, run in runs:
            # the middle of the run first, then out from it
            order = sorted(range(len(run)), key=lambda i: abs(i - len(run) / 2))
            for i in order:
                node = run[i]
                if node in refused:
                    continue
                a, b = run[max(0, i - 1)], run[min(len(run) - 1, i + 1)]
                dx, dy = b[0] - a[0], b[1] - a[1]
                norm = math.hypot(dx, dy) or 1.0
                point = Point(*node)
                spot = (fixture(point, (dx / norm, dy / norm)) if fixture is not None
                        else Point(point.x, point.y, point.z + LIFT))
                if spot is None:
                    refused.add(node)
                    continue
                target = spot
                refused.add(node)  # never the same spot twice
                break
            if target is not None:
                break
        if target is None:
            break
        lamps = list(bp.elements(Lamp))
        nearest = min(lamps, key=lambda l: (l.position.x - target.x) ** 2 + (l.position.y - target.y) ** 2,
                      default=None)
        hue = colour if colour is not None else (nearest.colour if nearest is not None else (1.0, 1.0, 1.0))
        lamp = bp.place_light(target, colour=hue, radius=radius, shadows=False,
                              id=f"{id_prefix}_lamp_{len(added)}")
        added.append(lamp)
    return added
