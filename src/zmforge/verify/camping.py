"""Z46, second half: no camping spot anywhere -- on a prop, on a brush, in a pocket.

WHAT THIS ASKS
--------------
Every place a player can stand, a zombie can hit him.  The rest of ``Z46``
(:mod:`~zmforge.verify.climb`) floods the *declared* standing room -- room
floors, walkable massing tops, thresholds, terrain -- and so it never sees the
defect players actually find: the top of a crate, a sarcophagus lid, the rail
over a flight of stairs, a pocket between pews.  On ``zm_cemetery`` that meant
tops of objects and the stairs down, where zombies could not reach.

This module compares two floods over **every collision surface the map
writes**, and then asks the melee question:

1. **Player surfaces.**  The declared standing room (:func:`~zmforge.verify.
   model._standing_patches`), plus the top of every colliding brush (world
   *and* ``detail``: a detail brush does not split the BSP but it stops a
   player exactly like a structural one) and of every solid prop's collision
   box (:attr:`~zmforge.blueprint.elements.Prop.collision_box` or the
   measured model box, the same boxes the collmaps are cut from).  Each is
   cut where anything stands in the body of a player on it, with every
   obstacle grown by the hull radius, so a rectangle here is where a
   player's **origin** can be.
2. **The player flood**, from the spawn: walk, step, jump up at most
   :data:`PLAYER_CLIMB`, drop anything short of a fatal fall.
3. **The zombie flood**, from the same seeds over the same rectangles: rise
   at most :data:`ZOMBIE_STEP`, no jump, drop as Z46 already lets it.  The
   zombies' only other traversals on a generated map are the barricade
   windows, which bring them *in*; there are no jump-up nodes to add.
4. **Melee.**  A rectangle the player reaches and the walkers do not is only
   a camping spot if a zombie cannot hit him there.  The stock decision is
   ``zombieShouldMeleeCondition``: ``DistanceSquared( self.origin,
   enemy.origin ) > ZM_MELEE_DIST_SQ`` refuses, with ``ZM_MELEE_DIST 64``
   (``scripts/shared/ai/zombie.gsh:3``, used at ``zombie.gsc:828``) -- a
   **3-D** distance between the two feet.  So a point is safe when every
   rectangle a zombie's origin can reach is more than 64 away, height
   included, and a spot is a finding when a :data:`FOOTHOLD` disc of such
   points exists: somewhere the player stands still and nothing touches him.

The numbers, and where each comes from
--------------------------------------
* player jump 39 (:data:`~zmforge.verify.reachability.JUMP_UP`: Treyarch
  ``Scale_Standards.pdf`` "Standing Jump ... 39 units height"); **no mantle
  is added**: mantling is the ``surfaceClimbType`` of a material, and no
  brush this generator writes carries ``mantle_on`` (zero mantle faces in
  all 22 stock ``map_source/zm`` maps either); see
  ``docs/playable-map-requirements.md``.
* player and zombie radius 15 (``player_shared.gsc`` ``PLAYER_RADIUS 15``;
  ``aitype.awi`` ``physRadius 15``), height 72.
* zombie step 18 (``bin/default_navmesh_settings.json`` ``maxStepHeight``).
* zombie melee 64, 3-D (above).

What it cannot see (the limits, also in ``docs/map-principles.md``)
-------------------------------------------------------------------
* A running leap across a gap is not a player link here (``Z25`` owns
  leaps): a top reached only by a leap is not found.
* Walls do not stop the melee test: a zombie within 64 through a wall counts
  as a hit.  A spot pressed against a wall with zombies on its far side reads
  as covered.
* Sloped brushes (wedges, the clip ramp over a flight) are never a surface;
  the ramp is walked, its box is not stood on.
* A prop with no measured box and no collision box is invisible to it
  (``Z48`` already prints each such model).
* Tops narrower than :data:`MIN_TOP` (8) either way, such as a 2-wide stair
  rail, are not standing room here.
* Pockets 30 to 31 units wide: the navmesh wants 31, the player fits in 30;
  the one unit is not modelled.

How a spot is fixed
-------------------
Clever spots stay; zombies are given a way up to them instead.  :func:`reach_camping_tops` gives a top a stock zombie
traversal from the floor beside it, and the walker flood here follows it
both ways; :func:`clip_camping_tops` caps with invisible ``clip`` only the
tops no traversal fits.  Invisible zombie-only ramps were looked at and not
used: the stock maps use ``clip_ai`` only as AI blockers (barricade
receivers, fences in ``zm_giant``), and whether ``cod2map64 -navmesh`` lays
walkable mesh on a ``clip_ai`` top has not been measured.

Deliberate exceptions are the ones Z46 already reads: a room or massing
declared ``reachable=False`` has no surface here.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Sequence

from ..blueprint.elements import FLOATS_ON_PURPOSE, STAIR_CLIP, Massing, PropScatter
from ..blueprint.model import _solid_bounds
from ..spatial import Point, Span
from .documented import MAX_STEP_HEIGHT
from .model import PLAYER_HULL_HEIGHT, PLAYER_HULL_WIDTH
from .reachability import (
    FATAL_DROP,
    JUMP_UP,
    STEP_UP,
    TOUCH,
    Standing,
    _raised_sills,
    _seed_cells,
)
from .report import Report, error, warning

__all__ = ["check_camping_spots", "camping_spots", "clip_camping_tops", "NAV_ISLAND", "PLAYER_CLIMB", "ZOMBIE_STEP",
           "ZM_MELEE_DIST", "FOOTHOLD", "HULL_RADIUS"]

#: How high a player gets his feet onto: the stock jump, no mantle (above).
PLAYER_CLIMB = JUMP_UP
#: How high a walker steps: the navmesh generator's ``maxStepHeight``.
ZOMBIE_STEP = MAX_STEP_HEIGHT
#: ``ZM_MELEE_DIST`` (``scripts/shared/ai/zombie.gsh:3``): the 3-D distance,
#: feet to feet, inside which a zombie decides to swing.
ZM_MELEE_DIST = 64.0
#: Player and zombie capsule radius (``PLAYER_RADIUS 15``, ``physRadius 15``).
HULL_RADIUS = PLAYER_HULL_WIDTH / 2.0
#: The radius of the patch of safe ground that makes a spot: a disc 16 across,
#: somewhere a player stands still without balancing on a line.
FOOTHOLD = 8.0
#: Sample spacing over a candidate rectangle.
_STEP = 8.0
_BUCKET = 128.0


def _is_box(solid) -> bool:
    """Six axis-aligned faces: a box whose top is flat."""
    if len(solid.faces) != 6:
        return False
    for face in solid.faces:
        pts = face.points
        if len(pts) < 3:
            return False
        a, b, c = pts[0], pts[1], pts[2]
        ux, uy, uz = b.x - a.x, b.y - a.y, b.z - a.z
        vx, vy, vz = c.x - a.x, c.y - a.y, c.z - a.z
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        if sum(1 for k in n if abs(k) > 1e-6) != 1:
            return False
    return True


def _colliders(blueprint):
    """``(label, element id, box, is a surface)`` for every colliding solid.

    Rooms and yards give their shells (obstacles, never surfaces: a floor is
    already the room's own patch and a wall runs to the roof); every massing
    without a targetname gives its brushes, ``detail`` included; a clip ramp
    over a flight is the stairs and is left out altogether, as ``Z25`` does.
    """
    from ..blueprint.elements import Room, Terrain, Yard
    from ..emit.mapfile import _room_solids, _terrain_columns, _terrain_plinth, _yard_solids

    out: list[tuple[str, str, Span, bool]] = []
    for room in blueprint.elements(Room):
        for solid in _room_solids(room):
            out.append((room.id, room.id, _solid_bounds(solid), False))
    for yard in blueprint.elements(Yard):
        for solid in _yard_solids(yard):
            out.append((yard.id, yard.id, _solid_bounds(solid), False))
    for terrain in blueprint.elements(Terrain):
        for solid in list(_terrain_columns(terrain)) + list(_terrain_plinth(terrain)):
            out.append((terrain.id, terrain.id, _solid_bounds(solid), False))
    for massing in blueprint.elements(Massing):
        if massing.targetname or massing.note == STAIR_CLIP:
            continue
        surface = massing.reachable and not massing.walkable
        for solid in massing.solids:
            if "nonsolid" in solid.contents:
                continue
            box = _solid_bounds(solid)
            out.append((massing.note or "massing", massing.id, box,
                        surface and _is_box(solid)))
    return out


def _prop_boxes(blueprint) -> list[tuple[str, str, Span]]:
    """Every solid, collmap-baking prop's collision box in world space."""
    from .approach import _model_boxes
    from ..props.origins import drawn_box

    table = _model_boxes()
    out = []
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if not prop.solid or prop.dynamic:
                continue
            local = drawn_box(prop.model, prop.collision_box) or table.get(prop.model)
            if local is None:
                continue
            (x0, y0, z0), (x1, y1, z1) = local
            s = prop.scale
            a = math.radians(prop.yaw)
            c, n = math.cos(a), math.sin(a)
            cx, cy = (x0 + x1) / 2.0 * s, (y0 + y1) / 2.0 * s
            wx = prop.origin.x + cx * c - cy * n
            wy = prop.origin.y + cx * n + cy * c
            hx = ((x1 - x0) * abs(c) + (y1 - y0) * abs(n)) * s / 2.0
            hy = ((x1 - x0) * abs(n) + (y1 - y0) * abs(c)) * s / 2.0
            lo, hi = prop.origin.z + z0 * s, prop.origin.z + z1 * s
            if hi - lo <= 0.0:
                continue
            out.append((prop.model, prop.id,
                        Span.between(Point(wx - hx, wy - hy, lo), Point(wx + hx, wy + hy, hi))))
    return out


class _Index:
    """Plan buckets over boxes, so a patch only meets the boxes near it."""

    def __init__(self, boxes: Sequence[Span]) -> None:
        self.boxes = list(boxes)
        self.grid: dict[tuple[int, int], list[int]] = {}
        for i, b in enumerate(self.boxes):
            for key in self._keys(b.mins.x, b.mins.y, b.maxs.x, b.maxs.y):
                self.grid.setdefault(key, []).append(i)

    @staticmethod
    def _keys(x0, y0, x1, y1):
        for gx in range(math.floor(x0 / _BUCKET), math.floor(x1 / _BUCKET) + 1):
            for gy in range(math.floor(y0 / _BUCKET), math.floor(y1 / _BUCKET) + 1):
                yield gx, gy

    def near(self, x0, y0, x1, y1) -> list[Span]:
        seen: set[int] = set()
        for key in self._keys(x0, y0, x1, y1):
            seen.update(self.grid.get(key, ()))
        return [self.boxes[i] for i in seen]


def _cut(patch: Span, z: float, index: _Index) -> list[Span]:
    """``patch`` minus where a player's origin cannot be at height ``z``."""
    from .reachability import _free_rects

    near = [
        b for b in index.near(patch.mins.x, patch.mins.y, patch.maxs.x, patch.maxs.y)
        if b.maxs.z > z + STEP_UP and b.mins.z < z + PLAYER_HULL_HEIGHT
    ]
    return _free_rects(patch, z, near)


#: A brush or prop top narrower than this is not counted as standing room:
#: a 2-wide stair rail, a 6-wide limb of a brush figure, a lettering stroke.
#: The engine's box player can balance on one, but nobody camps there, and
#: counting them turned wall lettering and cut-out figures into ladders into
#: slivers of floor (a test map).  A stated limit of the check.
MIN_TOP = 8.0


def _grown(box: Span) -> Span:
    return Span.between(
        Point(box.mins.x - HULL_RADIUS, box.mins.y - HULL_RADIUS, box.mins.z),
        Point(box.maxs.x + HULL_RADIUS, box.maxs.y + HULL_RADIUS, box.maxs.z),
    )


def _cells(blueprint) -> list[Standing]:
    from .model import _standing_patches

    colliders = _colliders(blueprint)
    props = _prop_boxes(blueprint)
    grown = [
        Span.between(
            Point(b.mins.x - HULL_RADIUS, b.mins.y - HULL_RADIUS, b.mins.z),
            Point(b.maxs.x + HULL_RADIUS, b.maxs.y + HULL_RADIUS, b.maxs.z),
        )
        for b in [c[2] for c in colliders] + [p[2] for p in props]
    ]
    index = _Index(grown)
    sources: list[tuple[str, str, Span, float, bool]] = []
    for label, element_id, patch, z in _standing_patches(blueprint):
        sources.append((label, element_id, patch, z, False))
    for label, element_id, patch, z in _raised_sills(blueprint):
        sources.append((label, element_id, patch, z, True))
    # A top is grown by the hull radius: a player's box rests on anything
    # under any part of it, so his origin can stand 15 past the edge -- which
    # is how a 2-wide stair rail is standing room.
    for label, element_id, box, surface in colliders:
        if surface and min(box.maxs.x - box.mins.x, box.maxs.y - box.mins.y) >= MIN_TOP:
            sources.append((f"the top of {label} {element_id}", element_id,
                            _grown(box), box.maxs.z, False))
    for model, prop_id, box in props:
        if min(box.maxs.x - box.mins.x, box.maxs.y - box.mins.y) < MIN_TOP:
            continue
        sources.append((f"the top of prop {model} ({prop_id})", prop_id,
                        _grown(box), box.maxs.z, False))
    cells: list[Standing] = []
    for label, element_id, patch, z, sill in sources:
        for rect in _cut(patch, z, index):
            cells.append(Standing(label, element_id, rect, z, sill))
    return cells


def _gap(a: Standing, b: Standing) -> tuple[float, float]:
    ax0, ay0, ax1, ay1 = a.plan
    bx0, by0, bx1, by1 = b.plan
    return (max(ax0, bx0) - min(ax1, bx1), max(ay0, by0) - min(ay1, by1))


def _touch(a: Standing, b: Standing) -> bool:
    """Two origin rectangles a body crosses between: a shared edge, or the
    hull radius of air that separates a floor from the top of the thing it is
    cut around (the floor stops a radius short of the box, the top does not)."""
    gx, gy = _gap(a, b)
    if gx > HULL_RADIUS + TOUCH or gy > HULL_RADIUS + TOUCH:
        return False
    if gx > -TOUCH and gy > -TOUCH:
        return False  # corner to corner is not a way through
    return True


def _flood(cells: Sequence[Standing], seeds: Sequence[int], up: float,
           links: dict[int, list[int]] | None = None) -> set[int]:
    links = links or {}
    grid: dict[tuple[int, int], list[int]] = {}
    for i, c in enumerate(cells):
        for key in _Index._keys(c.plan[0], c.plan[1], c.plan[2], c.plan[3]):
            grid.setdefault(key, []).append(i)
    reached = set(seeds)
    queue = deque(seeds)
    while queue:
        index = queue.popleft()
        for j in links.get(index, ()):
            if j not in reached:
                reached.add(j)
                queue.append(j)
        here = cells[index]
        x0, y0, x1, y1 = here.plan
        near: set[int] = set()
        for key in _Index._keys(x0 - HULL_RADIUS - 1, y0 - HULL_RADIUS - 1,
                                x1 + HULL_RADIUS + 1, y1 + HULL_RADIUS + 1):
            near.update(grid.get(key, ()))
        for j in near:
            if j in reached:
                continue
            there = cells[j]
            rise = there.z - here.z
            if rise > up or -rise >= FATAL_DROP:
                continue
            if not _touch(here, there):
                continue
            reached.add(j)
            queue.append(j)
    return reached


def _reach_sq(px: float, py: float, cell: Standing) -> float:
    x0, y0, x1, y1 = cell.plan
    dx = x0 - px if px < x0 else (px - x1 if px > x1 else 0.0)
    dy = y0 - py if py < y0 else (py - y1 if py > y1 else 0.0)
    return dx * dx + dy * dy


def _samples(cell: Standing):
    x0, y0, x1, y1 = cell.plan
    nx = max(1, int((x1 - x0) // _STEP))
    ny = max(1, int((y1 - y0) // _STEP))
    for i in range(nx + 1):
        for j in range(ny + 1):
            yield x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny


#: The narrowest top the navmesh generator lays mesh on
#: (``default_navmesh_settings.json`` ``minCharacterWidth``).  A top this wide
#: both ways can carry an island of its own, and the stock
#: ``player_shared.gsc`` ``last_valid_position`` loop sends the walkers to
#: ``self.origin`` whenever ``IsPointOnNavMesh`` says the player is on mesh:
#: to an island they have no path to.  The rule: such a top is an error
#: however close the walkers get, because a walker standing within 64 units
#: of it can still have no path onto it **(hypothesis, unverified in play)**.
NAV_ISLAND = 31.0


def _components(cells: Sequence[Standing], members: Sequence[int]) -> list[list[int]]:
    """``members`` joined into pieces of one surface: same height, touching."""
    left = set(members)
    out: list[list[int]] = []
    while left:
        seed = left.pop()
        piece, queue = [seed], [seed]
        while queue:
            a = cells[queue.pop()]
            for j in list(left):
                b = cells[j]
                if abs(a.z - b.z) > TOUCH:
                    continue
                gx, gy = _gap(a, b)
                if gx > TOUCH or gy > TOUCH or (gx > -TOUCH and gy > -TOUCH):
                    continue
                left.discard(j)
                piece.append(j)
                queue.append(j)
        out.append(piece)
    return out


def camping_spots(blueprint) -> list[tuple[Standing, Point, bool, tuple]]:
    """Every piece of surface a player reaches and no walker reaches, big
    enough to stand on: ``(cell, spot, error, raw box)``.  ``error`` is True
    when no walker can hit a foothold on it, or when it is a top wide enough
    to carry a navmesh island of its own; False is a top inside the walkers'
    swing (a warning)."""
    cells = _cells(blueprint)
    seeds = _seed_cells(blueprint, cells)
    player = _flood(cells, seeds, PLAYER_CLIMB)
    walkers = _flood(cells, seeds, ZOMBIE_STEP, _traversal_links(blueprint, cells))
    zgrid: dict[tuple[int, int], list[int]] = {}
    for i in walkers:
        c = cells[i]
        for key in _Index._keys(*c.plan):
            zgrid.setdefault(key, []).append(i)
    by_surface: dict[tuple[str, float], list[int]] = {}
    for i in sorted(player - walkers):
        if cells[i].sill:
            continue
        by_surface.setdefault((cells[i].element_id, cells[i].z), []).append(i)
    found: list[tuple[Standing, Point, bool, tuple]] = []
    for members in by_surface.values():
        for piece in _components(cells, members):
            x0 = min(cells[i].plan[0] for i in piece)
            y0 = min(cells[i].plan[1] for i in piece)
            x1 = max(cells[i].plan[2] for i in piece)
            y1 = max(cells[i].plan[3] for i in piece)
            if x1 - x0 < 2 * FOOTHOLD or y1 - y0 < 2 * FOOTHOLD:
                continue  # no foothold: a sliver between two cuts
            cell = cells[piece[0]]
            is_top = cell.label.startswith("the top of")
            # the raw top is the grown one less a hull radius each side
            raw = 2 * HULL_RADIUS if is_top else 0.0
            island = (is_top and x1 - x0 - raw >= NAV_ISLAND
                      and y1 - y0 - raw >= NAV_ISLAND)
            spot = _melee_safe(cells, zgrid, piece)
            if spot is None:
                spot = Point((x0 + x1) / 2.0, (y0 + y1) / 2.0, cell.z)
                error_ = island
            else:
                error_ = True
            found.append((cell, spot, error_, (x0, y0, x1, y1)))
    return found


def _cell_at(cells: Sequence[Standing], point: Point, below: float) -> int | None:
    """The highest cell holding ``point`` in plan, from 2 over it to
    ``below`` under it."""
    best = None
    for i, c in enumerate(cells):
        x0, y0, x1, y1 = c.plan
        if not (x0 - TOUCH <= point.x <= x1 + TOUCH and y0 - TOUCH <= point.y <= y1 + TOUCH):
            continue
        if not (point.z - below <= c.z <= point.z + 2.0):
            continue
        if best is None or c.z > cells[best].z:
            best = i
    return best


def _traversal_links(blueprint, cells: Sequence[Standing]) -> dict[int, list[int]]:
    """Each traversal's two ends, joined both ways: a walker climbs up after
    the player on ``up`` and comes back on ``down``."""
    from ..blueprint.elements import Traversal

    links: dict[int, list[int]] = {}
    for trav in blueprint.elements(Traversal):
        a = _cell_at(cells, trav.begin, ZOMBIE_STEP)
        b = _cell_at(cells, trav.end, ZOMBIE_STEP)
        if a is None or b is None:
            continue
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    return links


def _melee_safe(cells, zgrid, piece) -> Point | None:
    """A point of ``piece`` with a :data:`FOOTHOLD` disc no walker can hit."""
    for i in piece:
        cell = cells[i]
        x0, y0, x1, y1 = cell.plan
        r = ZM_MELEE_DIST + FOOTHOLD
        near: set[int] = set()
        for key in _Index._keys(x0 - r, y0 - r, x1 + r, y1 + r):
            near.update(zgrid.get(key, ()))
        threats = [cells[j] for j in near if abs(cells[j].z - cell.z) <= ZM_MELEE_DIST]
        for px, py in _samples(cell):
            safe = True
            for z in threats:
                dz = z.z - cell.z
                d = math.sqrt(_reach_sq(px, py, z)) - FOOTHOLD
                if d <= 0.0 or d * d + dz * dz <= ZM_MELEE_DIST * ZM_MELEE_DIST:
                    safe = False
                    break
            if safe:
                return Point(px, py, cell.z)
    return None


def check_camping_spots(blueprint) -> Report:
    """Z46 over every collision surface: a camping spot is an error."""
    report = Report()
    report.extend(check_traversal_nodes(blueprint))
    for cell, spot, is_error, (x0, y0, x1, y1) in camping_spots(blueprint):
        if not is_error:
            # a top a walker can swing at from the floor is a clever spot the
            # map keeps, not a finding
            continue
        speak = error
        why = ("no ground a walker reaches is within ZM_MELEE_DIST "
               f"{ZM_MELEE_DIST:g} (3-D, feet to feet) of a foothold on it"
               if is_error else
               "a walker can stand within ZM_MELEE_DIST of it, so this is a "
               "warning; if play finds it safe, clip it")
        rx, ry = x1 - x0 - 2 * HULL_RADIUS, y1 - y0 - 2 * HULL_RADIUS
        if is_error and cell.label.startswith("the top of") and (
                rx >= NAV_ISLAND and ry >= NAV_ISLAND):
            why += (f" or it is {rx:.0f} by {ry:.0f}, wide enough for a "
                    "navmesh island the walkers are sent to and cannot reach")
        report.add(
            speak(
                "Z46",
                f"camping spot: {cell.label} at z {cell.z:g}, around "
                f"({spot.x:.0f}, {spot.y:.0f}): a player gets there (walk, step, "
                f"jump of {PLAYER_CLIMB:g}) and no walker does (step "
                f"{ZOMBIE_STEP:g}, no jump), and {why}. Clip the top out of "
                "reach (camping.clip_camping_tops), lower it under a step, or "
                "open the pocket; a deliberate one is declared reachable=False",
                cell.element_id,
            )
        )
    return report


def clip_camping_tops(blueprint, *, rounds: int = 3) -> int:
    """Cap every top :func:`camping_spots` finds with an invisible ``clip``
    block, so the look stays and nobody stands there.

    The cap stands :data:`CAP_HEIGHT` over the top, more than a jump over
    anything the player could have got onto it from; it is a surface itself
    (reachable, not walkable), so the next round finds it if something higher
    still lets a player onto the cap, and caps that.  Pockets are left to the
    recipe: a pocket wants opening, not a lid.  Returns how many caps."""
    from ..materials import CLIP

    made = 0
    for _ in range(rounds):
        tops = {}
        for cell, _spot, err, _box in camping_spots(blueprint):
            if err and cell.label.startswith("the top of"):
                tops.setdefault(cell.element_id, cell.z)
        if not tops:
            break
        for element_id, z in sorted(tops.items()):
            box = _top_box(blueprint, element_id, z)
            if box is None:
                continue
            bottom = _above_lights(blueprint, box, z)
            top = z + CAP_HEIGHT
            if "_campclip" in element_id:
                # a cap a player still gets onto is one he drops onto from
                # above (a tread over a gallery): take it to the ceiling
                top = max(top, _ceiling(blueprint, box, z))
            blueprint.add_block(
                Span.between(Point(box.mins.x, box.mins.y, bottom),
                             Point(box.maxs.x, box.maxs.y, max(top, bottom + CAP_HEIGHT))),
                CLIP, id=f"{element_id}_campclip{made}",
                # it rests on a prop or brush top, which Z43 cannot see as
                # a floor; the cap is meant to sit exactly there (Z43 skips
                # this note, as it skips FLOATS_ON_PURPOSE)
                note=CAMPING_CAP)
            made += 1
    return made


#: :attr:`Massing.note` of a camping cap.  Not FLOATS_ON_PURPOSE: that note
#: is a recipe's own statement about its geometry, and a map test pins its set.
CAMPING_CAP = "camping cap (Z46)"

#: How tall a camping cap stands over the top it closes: more than
#: :data:`PLAYER_CLIMB`, so the cap's own top is never a jump from the old one.
CAP_HEIGHT = 48.0


#: Highest a cap may start over the top it closes and still close it: the
#: standing test is the band from one step (16) to a body (72) over the top.
_CAP_LIFT_MAX = 56.0


def _above_lights(blueprint, box: Span, z: float) -> float:
    """Where a cap over ``box`` starts: at the top, or just over a lamp or
    effect standing on it, so the cap never swallows a light (Z11: the
    cemetery's lamp-post caps did)."""
    from ..blueprint.elements import AmbientFx, Lamp

    bottom = z
    points = [l.position for l in blueprint.elements(Lamp)]
    points += [f.position for f in blueprint.elements(AmbientFx)]
    for p in points:
        if p is None:
            continue
        if (box.mins.x - 1 <= p.x <= box.maxs.x + 1 and box.mins.y - 1 <= p.y <= box.maxs.y + 1
                and z - 1 <= p.z <= z + _CAP_LIFT_MAX - 8):
            bottom = max(bottom, p.z + 8.0)
    return min(bottom, z + _CAP_LIFT_MAX)


def _ceiling(blueprint, box: Span, z: float) -> float:
    """The underside of the roof over ``box``, or 256 over ``z`` outdoors."""
    from ..blueprint.elements import Room

    x, y = box.centre.x, box.centre.y
    for room in blueprint.elements(Room):
        inside = room.interior
        if room.roofed and inside.holds_flat(x, y) and inside.mins.z - 1 <= z <= inside.maxs.z:
            return inside.maxs.z
    return z + 256.0


def _top_box(blueprint, element_id: str, z: float) -> Span | None:
    for model, prop_id, box in _prop_boxes(blueprint):
        if prop_id == element_id and abs(box.maxs.z - z) <= TOUCH:
            return box
    for massing in blueprint.elements(Massing):
        if massing.id != element_id:
            continue
        for solid in massing.solids:
            box = _solid_bounds(solid)
            if abs(box.maxs.z - z) <= TOUCH:
                return box
    return None


#: The zombie traversals a top can be given, by rise: the animscripts of the
#: stock zombie ``traverse@zombie`` table (``share/raw/animtables/
#: zm_genesis_zombie.ai_ast``: ``jump_up_36`` .. ``jump_up_96`` and
#: ``jump_down_36`` .. ``jump_down_96``, mapped onto the
#: ``ai_zombie_base_*jump_up_N`` / ``*jump_down_N`` xanims that
#: ``zone_source/all/assetlist/zm_levelcommon.csv`` packs for every usermap),
#: and the node spacing of Treyarch's ``t7_zm_jump_128.map`` (begin 47 out
#: from the ledge face, end 32 onto the top).  **Unverified in game:** that
#: the usermap spawner's own table (compiled into ``zm_levelcommon``, not
#: shipped as text) names the 36-96 rows the way genesis's does, and how far
#: a rise may differ from ``N`` before the animation looks wrong; the band
#: here is 18 under to 12 over.
TRAVERSAL_RISES = (36, 48, 72, 96)
BEGIN_BACK = 47.0
END_IN = 32.0


def _animscript_for(rise: float) -> int | None:
    fits = [n for n in TRAVERSAL_RISES if n - 18.0 <= rise <= n + 12.0]
    return min(fits, key=lambda n: abs(n - rise)) if fits else None


def reach_camping_tops(blueprint, *, rounds: int = 3) -> tuple[int, int]:
    """Give every camping top a stock zombie traversal from the floor beside
    it, so a walker follows the player up instead of the top being banned.

    Only a top at least :data:`NAV_ISLAND` wide both ways can take one (the
    navmesh lays nothing narrower, and a traversal must land on mesh), and
    only where a walker-reachable floor lies :data:`BEGIN_BACK` out from one
    side at a rise :func:`_animscript_for` covers.  Returns ``(made,
    left)``: the traversals placed and the error tops still without one,
    which :func:`clip_camping_tops` then caps."""
    from ..blueprint.elements import Traversal

    made = 0
    left = 0
    tried: set[tuple[str, float]] = set()
    turned = {prop.id for scatter in blueprint.elements(PropScatter) for prop in scatter.props
              if prop.id and min(prop.yaw % 90.0, 90.0 - prop.yaw % 90.0) > 0.5}
    for _ in range(rounds):
        cells = _cells(blueprint)
        seeds = _seed_cells(blueprint, cells)
        walkers = _flood(cells, seeds, ZOMBIE_STEP, _traversal_links(blueprint, cells))
        solids = [c[2] for c in _colliders(blueprint)] + [p[2] for p in _prop_boxes(blueprint)]
        tops: dict[str, float] = {}
        for cell, _spot, err, _box in camping_spots(blueprint):
            if err and cell.label.startswith("the top of"):
                tops.setdefault(cell.element_id, cell.z)
        left = 0
        placed = 0
        for element_id, z in sorted(tops.items()):
            if (element_id, z) in tried:
                left += 1  # it has one and is still out of reach: cap it
                continue
            tried.add((element_id, z))
            box = _top_box(blueprint, element_id, z)
            if element_id in turned:
                # A prop turned off the axes: its box here is the axis-aligned
                # box round the turned one, whose corners are not on the top,
                # so a node placed from it can land off the mesh (zm_cemetery's
                # dead car at 14 degrees: "Could not drop node at (150.0,9.0,
                # 128.5) to the navmesh").  Capped instead.
                left += 1
                continue
            if box is None or (box.maxs.x - box.mins.x < NAV_ISLAND
                               or box.maxs.y - box.mins.y < NAV_ISLAND):
                left += 1
                continue
            region = _nav_region(blueprint, box, z, solids)
            if not region:
                left += 1
                continue
            cx, cy = box.centre.x, box.centre.y
            hx, hy = (box.maxs.x - box.mins.x) / 2.0, (box.maxs.y - box.mins.y) / 2.0
            done = False
            for dx, dy, half in ((0, -1, hy), (0, 1, hy), (-1, 0, hx), (1, 0, hx)):
                face_x, face_y = cx + dx * hx, cy + dy * hy
                begin_xy = (face_x + dx * BEGIN_BACK, face_y + dy * BEGIN_BACK)
                inward = min(END_IN, half)
                spot = _nearest_in(region, face_x - dx * inward, face_y - dy * inward)
                if spot is None:
                    break
                end = Point(spot[0], spot[1], z)
                probe = Point(begin_xy[0], begin_xy[1], z - ZOMBIE_STEP)
                hit = _cell_at(cells, probe, TRAVERSAL_RISES[-1] + 12.0)
                if hit is None or hit not in walkers:
                    continue
                n = _animscript_for(z - cells[hit].z)
                if n is None:
                    continue
                blueprint._install(Traversal(
                    id=blueprint._claim("traversal", None),
                    begin=Point(begin_xy[0], begin_xy[1], cells[hit].z),
                    end=end, up=f"jump_up_{n}", down=f"jump_down_{n}",
                    note="zombie way onto a camping top (Z46)"))
                placed += 1
                done = True
                break
            if not done:
                left += 1
        made += placed
        if not placed:
            break
    return made, left


#: How far the navmesh generator erodes a surface from its edges and from
#: anything standing on it: half its ``minCharacterWidth`` (31).  Measured on
#: a zm_corn_maze compile: 5 of 100 traversal nodes
#: printed "Could not drop node ... to the navmesh"; four were end nodes on
#: hay bale tops at the very spot a solid hurricane lamp stood, while ends on
#: 32-wide barrel tops dropped.  So an end node is placed only inside the top
#: shrunk by this much, minus every solid on the top grown by this much.
NAV_ERODE = 15.5


def _nav_region(blueprint, top: Span, z: float, solids=None) -> list[Span]:
    """Where on ``top`` (a raw box whose top face is at ``z``) the navmesh can
    lie: the face shrunk by :data:`NAV_ERODE`, minus the footprint, grown by
    the same, of any solid in a walker's body over it."""
    from .reachability import _free_rects

    x0, y0 = top.mins.x + NAV_ERODE, top.mins.y + NAV_ERODE
    x1, y1 = top.maxs.x - NAV_ERODE, top.maxs.y - NAV_ERODE
    if x1 - x0 <= TOUCH or y1 - y0 <= TOUCH:
        return []
    if solids is None:
        solids = [c[2] for c in _colliders(blueprint)] + [p[2] for p in _prop_boxes(blueprint)]
    patch = Span.flat_ok(Point(x0, y0, z), Point(x1, y1, z))
    blocking = []
    for b in solids:
        if b.maxs.z <= z + 1.0 or b.mins.z >= z + PLAYER_HULL_HEIGHT:
            continue
        if b.maxs.x + NAV_ERODE <= x0 or b.mins.x - NAV_ERODE >= x1:
            continue
        if b.maxs.y + NAV_ERODE <= y0 or b.mins.y - NAV_ERODE >= y1:
            continue
        # lifted into the band _free_rects tests, so a lamp standing on the
        # top counts however short it is
        blocking.append(Span.between(
            Point(b.mins.x - NAV_ERODE, b.mins.y - NAV_ERODE, z + STEP_UP + 1.0),
            Point(b.maxs.x + NAV_ERODE, b.maxs.y + NAV_ERODE, z + PLAYER_HULL_HEIGHT - 1.0)))
    return [r for r in _free_rects(patch, z, blocking)
            if r.maxs.x - r.mins.x > TOUCH and r.maxs.y - r.mins.y > TOUCH]


def _nearest_in(rects: Sequence[Span], x: float, y: float) -> tuple[float, float] | None:
    best = None
    for r in rects:
        px = min(max(x, r.mins.x), r.maxs.x)
        py = min(max(y, r.mins.y), r.maxs.y)
        d = (px - x) ** 2 + (py - y) ** 2
        if best is None or d < best[0]:
            best = (d, px, py)
    return None if best is None else (best[1], best[2])


def _top_under(solids, point: Point) -> Span | None:
    for b in solids:
        if (abs(b.maxs.z - point.z) <= 1.0 and b.mins.x - TOUCH <= point.x <= b.maxs.x + TOUCH
                and b.mins.y - TOUCH <= point.y <= b.maxs.y + TOUCH):
            return b
    return None


def check_traversal_nodes(blueprint) -> Report:
    """Z46: every traversal end node stands where the navmesh will be, so
    ``cod2map64`` does not print "Could not drop node ... to the navmesh" and
    fail the compile (zm_corn_maze)."""
    from ..blueprint.elements import Traversal

    report = Report()
    travs = blueprint.elements(Traversal)
    if not travs:
        return report
    solids = [c[2] for c in _colliders(blueprint)] + [p[2] for p in _prop_boxes(blueprint)]
    for trav in travs:
        top = _top_under(solids, trav.end)
        if top is None:
            continue  # ends on a floor, not a top: the floor's own mesh
        region = _nav_region(blueprint, top, trav.end.z, solids)
        inside = any(r.mins.x - TOUCH <= trav.end.x <= r.maxs.x + TOUCH
                     and r.mins.y - TOUCH <= trav.end.y <= r.maxs.y + TOUCH for r in region)
        if not inside:
            report.add(error(
                "Z46",
                f"traversal {trav.id}: its end node at ({trav.end.x:.1f}, "
                f"{trav.end.y:.1f}, {trav.end.z:g}) is not on navmesh: the top is "
                f"narrower than {2 * NAV_ERODE:g} there or something solid stands "
                "on it, and cod2map64 fails the compile with 'Could not drop "
                "node ... to the navmesh'",
                trav.id))
    return report
