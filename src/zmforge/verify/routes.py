"""Z55: the furniture in a room does not cut the room into pieces.

Z53 keeps each doorway and the 48 units either side of it clear, Z54 keeps
props out of the walls, and Z48 floods from the spawn with the dressing in the
way.  None of them asks the question a player asks on walking in: can I get
from this door to every other door, every perk, every wall buy, every barricade
and every quest trigger *in this room*, past the desks and shelves the recipe
put here?  A row of cabinets across the middle of a room passes all three (the
doorways are clear, nothing is in a wall, and the spawn still reaches the far
half through another room), and still leaves half the room's content behind a
wall of furniture from the door the player uses.

How it is asked, per room:

* the floor is rasterised at :data:`CELL` units;
* each cell's clearance is its distance to the nearest thing a player walks
  into -- a solid prop's turned footprint, a world brush, or a wall of the room
  itself (doorways are the gaps in it) -- counting only things that stand in
  the player's body band, from :data:`STEP` over the floor to the top of the
  hull (so a rug is stepped over and a soffit walked under);
* a cell is walkable when its clearance is at least :data:`WALKABLE` (the
  player's radius, less half a cell for the raster), which is the same as
  growing every footprint by the player's radius;
* every doorway, perk, wall buy, box, power switch, barricade and quest use
  point is given the walkable cells near its use spot, and all of them must
  lie in one connected piece of walkable floor.  One that does not is an
  error.
* the narrowest point on the widest route from the room's first doorway to
  each of them is measured too (a max-min flood); under :data:`NARROW` units
  of corridor is a warning.

The same code runs over a :class:`~zmforge.blueprint.model.Blueprint`
(:func:`check_room_routes`, in every ``generate``) and over the stored model
document a written map carries (:func:`check_room_routes_document`, in
``zmforge check``), so a staged map can be re-asked without regenerating it.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ..props.origins import drawn_box
from .report import Report, error, warning

__all__ = [
    "CELL",
    "NARROW",
    "RADIUS",
    "STEP",
    "Blocker",
    "RoomPlan",
    "check_plans",
    "check_room_routes",
    "check_room_routes_document",
    "plans_from_blueprint",
    "plans_from_document",
]

#: Grid pitch of the floor raster.
CELL = 8.0
#: Half the player's 30-unit hull (``verify.model.PLAYER_HULL_WIDTH``).
RADIUS = 15.0
#: A cell is walkable when its centre is this far from every obstacle: the
#: radius less half a cell, because the best centre in a gap can sit up to
#: half a cell off the gap's middle.  So a gap of 30 (a hull) always passes,
#: one under 22 always fails, and one in between depends on the raster --
#: an error from this check is always a real gap under a hull.
WALKABLE = RADIUS - CELL / 2.0
#: A corridor narrower than this is a warning: a hull plus five a side.
NARROW = 40.0
#: A blocker whose top is no higher than this over the floor is stepped over.
STEP = 18.0
#: A blocker whose top is no higher than this over the floor is jumped onto
#: (``verify.reachability.JUMP_UP``), so it cannot be the reason for an error.
JUMP = 39.0
#: Top of the player's body band over the floor (``PLAYER_HULL_HEIGHT``).
HULL_HEIGHT = 72.0
#: How far from a use spot the player may stand and still use it.
USE_REACH = 32.0
#: Clearance is only ever compared with numbers up to NARROW / 2; cap there.
_CAP = 64.0
#: The use spots of an item facing into the room: its origin, then 24 and 48
#: in front (``verify.reachability.USE_OFFSETS``).
USE_OFFSETS = (0.0, 24.0, 48.0)


@dataclass(frozen=True, slots=True)
class Blocker:
    """An upright box, turned by ``cos``/``sin`` about its centre."""

    cx: float
    cy: float
    hx: float
    hy: float
    cos: float
    sin: float
    z0: float
    z1: float
    label: str

    def distance(self, x: float, y: float) -> float:
        dx, dy = x - self.cx, y - self.cy
        lx = dx * self.cos + dy * self.sin
        ly = -dx * self.sin + dy * self.cos
        ox = max(abs(lx) - self.hx, 0.0)
        oy = max(abs(ly) - self.hy, 0.0)
        return math.hypot(ox, oy)

    def reach(self) -> float:
        """Radius of a circle round the centre that holds the whole footprint."""
        return math.hypot(self.hx, self.hy)

    @classmethod
    def box(cls, x0, y0, x1, y1, z0, z1, label: str) -> "Blocker":
        return cls((x0 + x1) / 2.0, (y0 + y1) / 2.0, (x1 - x0) / 2.0,
                   (y1 - y0) / 2.0, 1.0, 0.0, z0, z1, label)


@dataclass
class RoomPlan:
    """One room as this check needs it: plan, floor, doors and targets."""

    id: str
    interior: tuple[float, float, float, float]
    floor: float
    walls: list[Blocker] = field(default_factory=list)
    #: ``(name, [(x, y), ...], reach, z)``: the points a player uses the
    #: thing from, how far from one of them he may stand, and its height.
    targets: list[tuple[str, list[tuple[float, float]], float, float]] = field(
        default_factory=list)


# --------------------------------------------------------------------------
# Obstacles
# --------------------------------------------------------------------------
def _prop_blocker(model, origin, yaw, scale, local, label) -> Blocker:
    (x0, y0, z0), (x1, y1, z1) = local
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    mx, my = (x0 + x1) / 2.0 * scale, (y0 + y1) / 2.0 * scale
    ox, oy, oz = origin
    return Blocker(ox + mx * c - my * s, oy + mx * s + my * c,
                   (x1 - x0) * scale / 2.0, (y1 - y0) * scale / 2.0, c, s,
                   oz + z0 * scale, oz + z1 * scale, label)


def _in_band(blocker: Blocker, floor: float) -> bool:
    """Does it stand on this floor and rise into the player's body?

    A blocker whose underside is more than a step over the floor is standing
    on something else -- a hill of terrain, a platform -- and the route over
    that is Z25's and Z48's three-dimensional question, not this one.
    """
    return (blocker.z1 > floor + STEP and blocker.z0 < floor + HULL_HEIGHT
            and blocker.z0 <= floor + STEP)


def _walls_of(interior, floor, doorways) -> list[Blocker]:
    """The four walls of a room as thin boxes, with a gap per doorway.

    ``doorways`` is ``(side, low, high)`` along the wall's own axis.
    """
    x0, y0, x1, y1 = interior
    t = 16.0
    out = []
    sides = {
        "north": ("x", x0, x1, lambda a, b: (a, y1, b, y1 + t)),
        "south": ("x", x0, x1, lambda a, b: (a, y0 - t, b, y0)),
        "east": ("y", y0, y1, lambda a, b: (x1, a, x1 + t, b)),
        "west": ("y", y0, y1, lambda a, b: (x0 - t, a, x0, b)),
    }
    for side, (_, low, high, make) in sides.items():
        gaps = sorted((a, b) for s, a, b in doorways if s == side)
        cursor = low - t
        for a, b in gaps + [(high + t, high + t)]:
            if a > cursor:
                bx0, by0, bx1, by1 = make(cursor, a)
                out.append(Blocker.box(bx0, by0, bx1, by1, floor, floor + 1e4,
                                       f"{side} wall"))
            cursor = max(cursor, b)
    return out


# --------------------------------------------------------------------------
# The raster
# --------------------------------------------------------------------------
class _Grid:
    def __init__(self, plan: RoomPlan, blockers: list[Blocker]) -> None:
        x0, y0, x1, y1 = plan.interior
        self.x0, self.y0 = x0, y0
        self.nx = max(1, int((x1 - x0) // CELL))
        self.ny = max(1, int((y1 - y0) // CELL))
        mine = [b for b in blockers if _in_band(b, plan.floor)] + plan.walls
        # Bucket the blockers by the cells they could matter to.
        buckets: dict[tuple[int, int], list[Blocker]] = {}
        pitch = 64.0
        for b in mine:
            r = b.reach() + _CAP
            for i in range(int((b.cx - r - x0) // pitch), int((b.cx + r - x0) // pitch) + 1):
                for j in range(int((b.cy - r - y0) // pitch), int((b.cy + r - y0) // pitch) + 1):
                    buckets.setdefault((i, j), []).append(b)
        self.clear: list[float] = []
        self.nearest: list[str] = []
        for j in range(self.ny):
            for i in range(self.nx):
                x, y = self.centre(i, j)
                best, who = _CAP, ""
                for b in buckets.get((int((x - x0) // pitch), int((y - y0) // pitch)), ()):
                    d = b.distance(x, y)
                    if d < best:
                        best, who = d, b.label
                self.clear.append(best)
                self.nearest.append(who)

    def centre(self, i: int, j: int) -> tuple[float, float]:
        return self.x0 + (i + 0.5) * CELL, self.y0 + (j + 0.5) * CELL

    def near(self, x: float, y: float, reach: float) -> list[int]:
        """Walkable cells within ``reach`` of a point."""
        out = []
        r = int(reach // CELL) + 1
        ci, cj = int((x - self.x0) // CELL), int((y - self.y0) // CELL)
        for j in range(max(0, cj - r), min(self.ny, cj + r + 1)):
            for i in range(max(0, ci - r), min(self.nx, ci + r + 1)):
                k = j * self.nx + i
                cx, cy = self.centre(i, j)
                if self.clear[k] >= WALKABLE and math.hypot(cx - x, cy - y) <= reach:
                    out.append(k)
        return out

    def neighbours(self, k: int):
        i, j = k % self.nx, k // self.nx
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            a, b = i + di, j + dj
            if 0 <= a < self.nx and 0 <= b < self.ny:
                if di and dj:
                    # No squeezing diagonally between two blocked cells.
                    if (self.clear[j * self.nx + a] < WALKABLE
                            and self.clear[b * self.nx + i] < WALKABLE):
                        continue
                yield b * self.nx + a

    def widest(self, seeds: list[int]) -> dict[int, float]:
        """Best bottleneck clearance to every walkable cell from ``seeds``."""
        best: dict[int, float] = {}
        heap = [(-self.clear[k], k) for k in seeds]
        heapq.heapify(heap)
        while heap:
            neg, k = heapq.heappop(heap)
            if k in best:
                continue
            best[k] = -neg
            for n in self.neighbours(k):
                if n in best or self.clear[n] < WALKABLE:
                    continue
                heapq.heappush(heap, (-min(-neg, self.clear[n]), n))
        return best

    def fence(self, piece: set[int]) -> str:
        """The blocker most of the cells shutting ``piece`` in are nearest to."""
        from collections import Counter

        seen: Counter = Counter()
        for k in piece:
            for n in self.neighbours(k):
                if self.clear[n] < WALKABLE and self.nearest[n]:
                    seen[self.nearest[n]] += 1
        props = [(c, label) for label, c in seen.items() if not label.endswith(" wall")]
        if props:
            return max(props)[1]
        return seen.most_common(1)[0][0] if seen else ""

    def pinch(self, best: dict[int, float], cells: list[int]) -> str:
        """What stands at the narrowest point of the route to ``cells``."""
        target = max(cells, key=lambda k: best.get(k, -1.0))
        bottleneck = best[target]
        # The pinch cell is one on the route whose own clearance is the
        # bottleneck; name the blocker nearest to it.
        for k, value in best.items():
            if (abs(self.clear[k] - bottleneck) < 1e-9
                    and abs(value - bottleneck) < 1e-9 and self.nearest[k]):
                return self.nearest[k]
        return ""


def _on_raised_ground(floor, spots, z, blockers) -> bool:
    """Is this target up on ground this flat-floor check does not model?

    More than a step over the floor and *not* resting on a blocker that
    stands on the floor (a form on a desk is reached from round the desk)
    means terrain or a platform -- the cemetery's grave on its hill, at z 74
    over a room floor of 16 -- and the route up there is Z25's and Z48's
    three-dimensional question, not this one.
    """
    if z - floor <= STEP:
        return False
    x, y = spots[0]
    return not any(
        b.distance(x, y) <= 1.0 and b.z0 <= floor + STEP and b.z1 <= z + STEP
        for b in blockers
    )


def _cut_off(grid: "_Grid", plan: RoomPlan, local: list[Blocker]):
    """``(cells, pieces, owner, main, home, [(name, culprit), ...])``."""
    cells = [(name, sorted({k for (x, y) in spots for k in grid.near(x, y, reach)}))
             for name, spots, reach, z in plan.targets
             if not _on_raised_ground(plan.floor, spots, z, local)]
    pieces: list[set[int]] = []
    owner: dict[int, int] = {}
    for _, ks in cells:
        for k in ks:
            if k in owner:
                continue
            piece = set(grid.widest([k]))
            for m in piece:
                owner[m] = len(pieces)
            pieces.append(piece)
    if not pieces:
        return cells, pieces, owner, None, [], [(name, "") for name, _ in cells]
    score = [sum(1 for _, ks in cells if any(owner.get(k) == p for k in ks))
             for p in range(len(pieces))]
    main = max(range(len(pieces)), key=score.__getitem__)
    home = [name for name, ks in cells if any(owner.get(k) == main for k in ks)]
    out = []
    for name, ks in cells:
        if any(owner.get(k) == main for k in ks):
            continue
        # What is in the way: the prop or brush most of the fence round the
        # target's own piece of floor is made of (walls last).
        out.append((name, grid.fence(set().union(
            *(pieces[owner[k]] for k in ks if k in owner)))))
    return cells, pieces, owner, main, home, out


def check_plans(plans: list[RoomPlan], blockers: list[Blocker], *, code: str = "Z55") -> Report:
    """Errors for targets cut off even jumping; warnings for jump-only and narrow."""
    report = Report()
    for plan in plans:
        if len(plan.targets) < 2:
            continue
        x0, y0, x1, y1 = plan.interior
        local = [b for b in blockers
                 if x0 - b.reach() - _CAP <= b.cx <= x1 + b.reach() + _CAP
                 and y0 - b.reach() - _CAP <= b.cy <= y1 + b.reach() + _CAP]
        # Two floods.  "Hard" counts only what a player cannot jump onto
        # (top more than JUMP over the floor, ``verify.reachability.JUMP_UP``);
        # a target it cannot reach is an error.  "Walking" counts everything
        # over a step; a target only it cannot reach is a warning.
        hard = [b for b in local if b.z1 > plan.floor + JUMP]
        cells, pieces, owner, main, home, cut = _cut_off(_Grid(plan, hard), plan, hard)
        if main is None:
            if cells:
                report.add(error(code, f"room {plan.id}: none of its {len(cells)} doors "
                               "and interactives has a walkable cell beside it", plan.id))
            continue
        for name, culprit in cut:
            report.add(error(
                code,
                f"room {plan.id}: {name} cannot be reached from {home[0]}"
                + (f" or the {len(home) - 1} other door(s)/interactives joined to it"
                   if len(home) > 1 else "")
                + ", even jumping; solid props and brushes leave no gap a 30-unit "
                "player fits; "
                + (f"shut in by {culprit}" if culprit else "no walkable floor beside it"),
                plan.id,
            ))
        hard_cut = {name for name, _ in cut}
        grid = _Grid(plan, local)
        cells, pieces, owner, main, home, cut = _cut_off(grid, plan, local)
        if main is None:
            continue
        for name, culprit in cut:
            if name in hard_cut:
                continue
            report.add(warning(
                code,
                f"room {plan.id}: {name} is reached from {home[0]} only by jumping "
                f"over furniture; walking, it is shut in by {culprit or 'the room'}",
                plan.id,
            ))
        # Narrowest point on the widest walking route from the first home target.
        first = next(ks for name, ks in cells if name == home[0])
        best = grid.widest([k for k in first if owner.get(k) == main])
        for name, ks in cells:
            if name == home[0] or not any(k in best for k in ks):
                continue
            # The true gap is between 2c and 2c + CELL for a bottleneck
            # clearance c; warn only when even the wide end is under NARROW.
            width = 2.0 * max(best[k] for k in ks if k in best) + CELL / 2.0
            if width + CELL / 2.0 < NARROW:
                report.add(warning(
                    code,
                    f"room {plan.id}: the widest route from {home[0]} to {name} "
                    f"narrows to about {width:.0f} units (under {NARROW:g}) at "
                    f"{grid.pinch(best, [k for k in ks if k in best]) or 'a wall'}",
                    plan.id,
                ))
    return report


# --------------------------------------------------------------------------
# From a Blueprint
# --------------------------------------------------------------------------
def _spots(position, dx, dy) -> list[tuple[float, float]]:
    return [(position.x + dx * o, position.y + dy * o) for o in USE_OFFSETS]


def _inside(interior, x, y, slack=0.0) -> bool:
    x0, y0, x1, y1 = interior
    return x0 - slack <= x <= x1 + slack and y0 - slack <= y <= y1 + slack


def _doorway_spots(interior, side: str, low: float, high: float):
    """Use spots of a doorway: along its middle, one hull inside the room."""
    x0, y0, x1, y1 = interior
    mid = (low + high) / 2.0
    inset = RADIUS + CELL
    return [{
        "north": (mid, y1 - inset), "south": (mid, y0 + inset),
        "east": (x1 - inset, mid), "west": (x0 + inset, mid),
    }[side]]


def _assign(plans: list[RoomPlan], name: str, spots, z: float,
            reach: float = USE_REACH) -> None:
    for plan in plans:
        if -8.0 <= z - plan.floor <= HULL_HEIGHT and any(
            _inside(plan.interior, x, y, 1.0) for x, y in spots
        ):
            inside = [(x, y) for x, y in spots if _inside(plan.interior, x, y)]
            plan.targets.append((name, inside or spots, reach, z))
            return


def plans_from_blueprint(blueprint) -> tuple[list[RoomPlan], list[Blocker]]:
    from ..blueprint.elements import (
        STAIR_CLIP, Machine, Massing, MysteryBox, PowerSwitch, PropScatter,
        Room, WallWeapon, Window, Wunderfizz,
    )
    from ..blueprint.model import _solid_bounds
    from .approach import _model_boxes

    plans: list[RoomPlan] = []
    for room in blueprint.elements(Room):
        if not room.reachable:
            continue
        box = room.interior
        interior = (box.mins.x, box.mins.y, box.maxs.x, box.maxs.y)
        doorways = []
        for aperture, hole in zip(room.apertures, room.aperture_boxes):
            if aperture.sill > STEP:
                continue
            side = aperture.side.name.lower()
            if side in ("north", "south"):
                doorways.append((side, hole.mins.x, hole.maxs.x))
            else:
                doorways.append((side, hole.mins.y, hole.maxs.y))
        plan = RoomPlan(room.id, interior, room.floor_z,
                        walls=_walls_of(interior, room.floor_z, doorways))
        for n, (side, low, high) in enumerate(doorways):
            plan.targets.append((f"the {side} doorway #{n + 1}",
                                 _doorway_spots(interior, side, low, high), USE_REACH, plan.floor))
        plans.append(plan)

    for kind, label in ((Machine, None), (MysteryBox, "the mystery box"),
                        (PowerSwitch, "the power switch"), (Wunderfizz, "the wunderfizz"),
                        (WallWeapon, None)):
        for item in blueprint.elements(kind):
            step = item.facing.step
            name = label or (f"the {item.perk.slug} machine" if kind is Machine
                             else f"the {item.slug} wall buy")
            _assign(plans, name, _spots(item.position, step.x, step.y), item.position.z)
    for window in blueprint.elements(Window):
        o = window.barricade_origin
        if o is None:
            continue
        out = window.side.outward
        # The barricade faces out; the player repairs it from inside.
        _assign(plans, f"the barricade {window.id}",
                [(o.x - out.x * d, o.y - out.y * d) for d in (24.0, 48.0)], o.z)
    for label, point, radius in getattr(blueprint, "quest_use_points", ()):
        _assign(plans, f"the {label} trigger", [(point.x, point.y)], point.z,
                max(radius, RADIUS) if radius else USE_REACH)

    table = _model_boxes()
    blockers: list[Blocker] = []
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if not prop.solid:
                continue
            local = drawn_box(prop.model, prop.collision_box) or table.get(prop.model)
            if local is None:
                continue
            o = prop.origin
            blockers.append(_prop_blocker(prop.model, (o.x, o.y, o.z), prop.yaw,
                                          prop.scale, local,
                                          f"{prop.model} ({prop.id or scatter.id}) at "
                                          f"{o.x:g} {o.y:g}"))
    clips = {id(s) for m in blueprint.elements(Massing) if m.note == STAIR_CLIP
             for s in m.solids}
    massing = {id(s): m.id for m in blueprint.elements(Massing) for s in m.solids}
    for solid in blueprint.world_solids():
        if id(solid) in clips or id(solid) not in massing:
            continue  # room shells are the walls above; stair clips are floor
        b = _solid_bounds(solid)
        blockers.append(Blocker.box(b.mins.x, b.mins.y, b.maxs.x, b.maxs.y,
                                    b.mins.z, b.maxs.z,
                                    f"brush {massing[id(solid)]}"))
    return plans, blockers


def check_room_routes(blueprint) -> Report:
    """Z55 over a blueprint: every room's doors and interactives joined."""
    plans, blockers = plans_from_blueprint(blueprint)
    return check_plans(plans, blockers)


# --------------------------------------------------------------------------
# From the stored model document (``<map>.blueprint.json``)
# --------------------------------------------------------------------------
_ITEM_NAMES = {"perk": "perk machine", "wall_buy": "wall buy", "power_switch": "power switch",
               "mystery_box": "mystery box", "pack_a_punch": "pack-a-punch", "wunderfizz": "wunderfizz"}


def plans_from_document(document: dict) -> tuple[list[RoomPlan], list[Blocker]]:
    from .approach import _model_boxes

    editor = document.get("editor", {})
    engine = document.get("engine", {})
    plans: list[RoomPlan] = []
    for room in editor.get("rooms", ()):
        if not room.get("reachable", True):
            continue
        t = float(room["wall"])
        interior = (room["x0"] + t, room["y0"] + t, room["x1"] - t, room["y1"] - t)
        floor = float(room["z"]) + t
        doorways = []
        for opening in room.get("openings", ()):
            if float(opening["sill"]) > STEP:
                continue
            side = opening["side"]
            if side in ("north", "south"):
                mid = (room["x0"] + room["x1"]) / 2.0 + float(opening["center"])
            else:
                mid = (room["y0"] + room["y1"]) / 2.0 + float(opening["center"])
            half = float(opening["width"]) / 2.0
            doorways.append((side, mid - half, mid + half))
        plan = RoomPlan(room["id"], interior, floor,
                        walls=_walls_of(interior, floor, doorways))
        for n, (side, low, high) in enumerate(doorways):
            plan.targets.append((f"the {side} doorway #{n + 1}",
                                 _doorway_spots(interior, side, low, high), USE_REACH, plan.floor))
        for opening in room.get("openings", ()):
            barricade = opening.get("barricade")
            if not barricade:
                continue
            side = opening["side"]
            axis_mid = ((room["x0"] + room["x1"]) if side in ("north", "south")
                        else (room["y0"] + room["y1"])) / 2.0 + float(opening["center"])
            (sx, sy), = _doorway_spots(interior, side, axis_mid, axis_mid)
            plan.targets.append((f"the barricade {barricade['id']}", [(sx, sy)], USE_REACH, floor))
        plans.append(plan)
    for item in editor.get("items", ()):
        kind = item.get("type")
        if kind not in _ITEM_NAMES:
            continue
        a = math.radians(float(item.get("yaw", 0.0)))
        pos = type("P", (), {"x": float(item["x"]), "y": float(item["y"])})
        _assign(plans, f"the {_ITEM_NAMES[kind]} {item.get('id', '')}".rstrip(),
                _spots(pos, math.cos(a), math.sin(a)), float(item["z"]))
    for point in engine.get("use_points", ()):
        radius = float(point.get("radius") or 0.0)
        _assign(plans, f"the {point['label']} trigger", [(point["x"], point["y"])],
                float(point["z"]), max(radius, RADIUS) if radius else USE_REACH)

    table = _model_boxes()
    blockers: list[Blocker] = []
    for prop in engine.get("props", ()):
        if not prop.get("solid"):
            continue
        local = drawn_box(prop["model"], prop.get("collision_box")) or table.get(prop["model"])
        if not local:
            continue
        o = prop["origin"]
        o = (o["x"], o["y"], o["z"]) if isinstance(o, dict) else tuple(o)
        blockers.append(_prop_blocker(prop["model"], o, float(prop.get("yaw", 0.0)),
                                      float(prop.get("scale", 1.0)), local,
                                      f"{prop['model']} ({prop.get('id') or prop.get('scatter')}) "
                                      f"at {o[0]:g} {o[1]:g}"))
    for block in editor.get("blocks", ()):
        blockers.append(Blocker.box(block["x0"], block["y0"], block["x1"], block["y1"],
                                    block["z0"], block["z1"], f"brush {block['id']}"))
    return plans, blockers


def check_room_routes_document(document: dict) -> Report:
    """Z55 over a stored model document, for ``zmforge check``."""
    plans, blockers = plans_from_document(document)
    return check_plans(plans, blockers)


def main(argv=None) -> int:
    """``python -m zmforge.verify.routes --tools-root ROOT NAME``: Z55 alone,
    over the stored model document of a written map (a build script can run
    it before every build, including one that reuses a staging tree)."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="zmforge.verify.routes")
    parser.add_argument("name")
    parser.add_argument("--tools-root", required=True)
    args = parser.parse_args(argv)
    from ..toolchain.layout import resolve_layout

    path = Path(str(resolve_layout(args.tools_root).map_source(args.name))).with_name(
        f"{args.name}.blueprint.json")
    if not path.exists():
        print(f"Z55: no stored model at {path}; nothing to check")
        return 0
    report = check_room_routes_document(json.loads(path.read_text(encoding="utf-8")))
    for finding in report:
        print(finding)
    print(f"Z55: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 0 if not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
