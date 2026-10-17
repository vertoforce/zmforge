"""Z60: the per-prop rules in ``props/notes.json``, asked of every map.

A prop's ``rules`` block (its own, merged over every category whose
``pattern`` matches it) says what that prop needs to read right wherever it
goes: which way its front is, what it faces, what stands under or near it,
where it mounts.  Each rule type is judged here
the same way on every map, so a lesson learned on one map (a sink with no
legs, a pipe ending in mid-air, a chair with its back to its desk) is asked
of the next one without anyone remembering it.

Everything is a **warning**, one line per rule and model per map with the
count and the first place it happens.  A rule is only judged where the
blueprint can answer it without guessing:

* orientation rules (``faces``, ``faced_by``, ``clearance_front``) need a
  measured ``front`` (measured once; the result is in ``src/zmforge/props/notes.json``); a model whose front is
  ``unknown`` is skipped, and so is a partner whose front is unknown;
* a prop outside every room (terrain, a yard) is not asked the room rules
  (``mount``, ``faces: room``, ``max_per_room``, ``not_in``);
* a pipe run is judged as a run: the connected set of pieces, not each
  piece, has to touch a floor, ceiling, wall, brush or other prop.
"""

from __future__ import annotations

import fnmatch
import math
from collections import defaultdict
from dataclasses import dataclass

from .report import Report, warning

__all__ = [
    "BACK_TURNED",
    "FACING_CONE",
    "TOUCH",
    "STEP",
    "check_prop_rules",
]

#: A chair's front more than this many degrees off the bearing to its desk
#: has its back (or near enough) to the desk.  Sideways is allowed: a chair
#: pushed back and turned is a lived-in room, not a mistake.
BACK_TURNED = 120.0
#: A chair "faces" a monitor when its front is within this of the bearing.
FACING_CONE = 75.0
#: Two things closer than this touch (units): float noise plus a skirting.
TOUCH = 4.0
#: The Z53 step: anything this low is stepped over, not walked into.
STEP = 18.0
#: How much of a clearance box a prop may take before it counts as blocked
#: (a paper ball or a cable does not block a machine).
CLEAR_SHARE = 0.25
#: Plan cell size of the brush index, in units.
_CELL = 256.0


@dataclass
class _Item:
    prop: object
    ident: str
    scatter: str
    placed: object
    rules: dict
    box: tuple[float, float, float, float, float, float]

    @property
    def cx(self) -> float:
        return self.placed.x

    @property
    def cy(self) -> float:
        return self.placed.y


_MATCHED: dict[tuple[str, tuple[str, ...]], bool] = {}


def _matches(model: str, what) -> bool:
    key = (model, tuple(what))
    hit = _MATCHED.get(key)
    if hit is None:
        hit = _MATCHED[key] = any(fnmatch.fnmatchcase(model, pattern) for pattern in what)
    return hit


def _gap(a, b) -> float:
    """Distance between two plan boxes ``(x0, y0, x1, y1)``; 0 when they overlap."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _gap3(a, b) -> float:
    dx = max(b[0] - a[3], a[0] - b[3], 0.0)
    dy = max(b[1] - a[4], a[1] - b[4], 0.0)
    dz = max(b[2] - a[5], a[2] - b[5], 0.0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _plan(box):
    return (box[0], box[1], box[3], box[4])


def _front(item: _Item) -> tuple[float, float] | None:
    from ..props.notes import front_of

    local = front_of(item.prop.model)
    if local is None:
        return None
    a = math.radians(local + item.prop.yaw)
    return math.cos(a), math.sin(a)


def _half_depth(item: _Item, fx: float, fy: float) -> float:
    """How far the footprint reaches from its centre along a world direction."""
    x0, y0, _z0, x1, y1, _z1 = item.box
    return abs(fx) * (x1 - x0) / 2.0 + abs(fy) * (y1 - y0) / 2.0


def _angle(fx: float, fy: float, dx: float, dy: float) -> float:
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return 0.0
    c = max(-1.0, min(1.0, (fx * dx + fy * dy) / n))
    return math.degrees(math.acos(c))


def _nearest_point(box, x: float, y: float) -> tuple[float, float]:
    return min(max(x, box[0]), box[3]), min(max(y, box[1]), box[4])


class _World:
    """Rooms, brushes and props, indexed once for every rule."""

    def __init__(self, blueprint) -> None:
        from ..blueprint.elements import Massing, PropScatter, Room
        from .looks import _placed

        self.rooms = list(blueprint.elements(Room))
        self.brushes = []
        for element in blueprint.elements(Massing):
            b = element.bounds
            self.brushes.append((element.id, (b.mins.x, b.mins.y, b.mins.z, b.maxs.x, b.maxs.y, b.maxs.z)))
        #: Brushes by plan cell, for the point tests (a map has thousands).
        self._cells: dict[tuple[int, int], list] = defaultdict(list)
        for entry in self.brushes:
            b = entry[1]
            for i in range(int(b[0] // _CELL), int(b[3] // _CELL) + 1):
                for j in range(int(b[1] // _CELL), int(b[4] // _CELL) + 1):
                    self._cells[(i, j)].append(entry)
        self.items: list[_Item] = []
        from ..props.notes import rules_for

        cache: dict[str, dict] = {}
        for scatter in blueprint.elements(PropScatter):
            for prop in scatter.props:
                placed = _placed(prop)
                if placed is None:
                    continue
                if prop.model not in cache:
                    cache[prop.model] = rules_for(prop.model)
                x0, y0, x1, y1 = placed.footprint.bounds
                self.items.append(_Item(prop, prop.id or scatter.id, scatter.id, placed,
                                        cache[prop.model], (x0, y0, placed.z_low, x1, y1, placed.z_high)))

    def room_at(self, x: float, y: float, z: float):
        from .looks import _room_at

        return _room_at(self.rooms, x, y, z)

    def in_brush(self, x: float, y: float, z0: float, z1: float) -> bool:
        for _id, b in self._cells.get((int(x // _CELL), int(y // _CELL)), ()):
            if b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] < z1 and z0 < b[5]:
                return True
        return False

    def open_at(self, room, x: float, y: float, z: float) -> bool:
        """Is (x, y) open floor-to-head space of *room* at height *z*?"""
        box = room.interior
        if not (box.mins.x <= x <= box.maxs.x and box.mins.y <= y <= box.maxs.y):
            return False
        return not self.in_brush(x, y, z - 1.0, z + 1.0)


# -- the rules ---------------------------------------------------------------
def _faces(world: _World, item: _Item, rule) -> str | None:
    front = _front(item)
    if front is None:
        return None
    fx, fy = front
    if rule == "room":
        reach = _half_depth(item, fx, fy) + 6.0
        # A sign turned into its wall has its centre past the wall's face, so
        # the room is found from either side of it.
        room = (world.room_at(item.cx, item.cy, item.placed.z_low)
                or world.room_at(item.cx - fx * reach, item.cy - fy * reach, item.placed.z_low)
                or world.room_at(item.cx + fx * reach, item.cy + fy * reach, item.placed.z_low))
        if room is None:
            return None
        z = (item.placed.z_low + item.placed.z_high) / 2.0
        ahead = world.open_at(room, item.cx + fx * reach, item.cy + fy * reach, z)
        behind = world.open_at(room, item.cx - fx * reach, item.cy - fy * reach, z)
        if not ahead and behind:
            return "faces the wall behind it, its back to the room"
        return None
    what, within = rule["what"], float(rule.get("within", 24.0))
    best = None
    for other in world.items:
        if other is item or not _matches(other.prop.model, what):
            continue
        if other.box[5] < item.placed.z_low or other.box[2] > item.placed.z_high:
            continue
        gap = _gap(_plan(item.box), _plan(other.box))
        if gap <= within and (best is None or gap < best[0]):
            best = (gap, other)
    if best is None:
        return None
    px, py = _nearest_point(best[1].box, item.cx, item.cy)
    off = _angle(fx, fy, px - item.cx, py - item.cy)
    if off > BACK_TURNED:
        return f"turns its back on {best[1].prop.model} ({best[1].ident}), {off:.0f} degrees off it"
    return None


def _faced_by(world: _World, item: _Item, rule) -> str | None:
    what, within = rule["what"], float(rule.get("within", 72.0))
    near = [o for o in world.items if o is not item and _matches(o.prop.model, what)
            and _gap(_plan(item.box), _plan(o.box)) <= within
            and abs(o.placed.z_low - item.placed.z_low) < 96.0]
    if not near:
        return f"no seat within {within:g} units: nobody could use it"
    known = [(o, _front(o)) for o in near]
    known = [(o, f) for o, f in known if f is not None]
    if not known:
        return None
    for o, (fx, fy) in known:
        if _angle(fx, fy, item.cx - o.cx, item.cy - o.cy) <= FACING_CONE:
            return None
    return f"no seat faces it ({len(known)} within {within:g} units, all turned away)"


def front_box(cx: float, cy: float, fx: float, fy: float, reach: float, side: float,
              depth: float, z0: float, z1: float) -> tuple[float, ...]:
    """The upright box *depth* deep in front of a thing at (*cx*, *cy*).

    (*fx*, *fy*) is the unit front; *reach* is how far the thing itself runs
    forward of its centre and *side* its half width across the front.
    Returns ``(x0, y0, z0, x1, y1, z1)``.  Shared by ``Z60``'s
    ``clearance_front`` and ``D6`` (:mod:`zmforge.verify.design`).
    """
    mx, my = cx + fx * (reach + depth / 2.0), cy + fy * (reach + depth / 2.0)
    hx = abs(fx) * depth / 2.0 + abs(fy) * side
    hy = abs(fy) * depth / 2.0 + abs(fx) * side
    return (mx - hx, my - hy, z0, mx + hx, my + hy, z1)


def props_in(world: _World, zone, *, skip=None, solid_only: bool = True,
             share: float = CLEAR_SHARE, prop_share: float | None = None,
             min_top: float | None = None) -> list[_Item]:
    """The props standing in *zone* (``front_box``'s tuple).

    A prop counts when it overlaps the zone's height band and covers more
    than *share* of the zone's plan, or (with *prop_share*) when more than
    that share of its own plan is inside the zone.  *min_top* keeps only
    props whose top is over it; *solid_only* only solid ones.
    """
    area = (zone[3] - zone[0]) * (zone[4] - zone[1])
    out = []
    for other in world.items:
        if other is skip or (solid_only and not other.prop.solid):
            continue
        b = other.box
        if b[5] <= zone[2] or b[2] >= zone[5]:
            continue
        if min_top is not None and b[5] <= min_top:
            continue
        ox = min(b[3], zone[3]) - max(b[0], zone[0])
        oy = min(b[4], zone[4]) - max(b[1], zone[1])
        if ox <= 0 or oy <= 0:
            continue
        own = max((b[3] - b[0]) * (b[4] - b[1]), 1e-6)
        if ox * oy > share * area or (prop_share is not None and ox * oy > prop_share * own):
            out.append(other)
    return out


def _clearance_front(world: _World, item: _Item, depth) -> str | None:
    front = _front(item)
    if front is None:
        return None
    fx, fy = front
    reach = _half_depth(item, fx, fy)
    side = _half_depth(item, -fy, fx)
    zone = front_box(item.cx, item.cy, fx, fy, reach, side, depth,
                     item.placed.z_low + STEP, item.placed.z_low + 64.0)
    area = (zone[3] - zone[0]) * (zone[4] - zone[1])
    hits = props_in(world, zone, skip=item)
    if hits:
        other = hits[0]
        return f"{other.prop.model} ({other.ident}) stands in the {depth:g} units in front of it"
    for bid, b in world.brushes:
        if b[5] <= zone[2] or b[2] >= zone[5]:
            continue
        ox = min(b[3], zone[3]) - max(b[0], zone[0])
        oy = min(b[4], zone[4]) - max(b[1], zone[1])
        if ox > 0 and oy > 0 and ox * oy > CLEAR_SHARE * area:
            return f"brush {bid} stands in the {depth:g} units in front of it"
    return None


def _on_a_wall(world: _World, item: _Item, room) -> bool:
    x0, y0, z0, x1, y1, z1 = item.box
    box = room.interior
    if (x0 - box.mins.x <= TOUCH or box.maxs.x - x1 <= TOUCH
            or y0 - box.mins.y <= TOUCH or box.maxs.y - y1 <= TOUCH):
        return True
    for _bid, b in world.brushes:
        if b[5] < z0 or b[2] > z1:
            continue
        if _gap((x0, y0, x1, y1), _plan(b)) <= TOUCH and (b[5] - b[2]) >= 0.5 * (z1 - z0):
            return True
    for other in world.items:
        if other is item or not other.prop.solid:
            continue
        b = other.box
        if b[5] >= z1 and b[2] <= z0 and _gap((x0, y0, x1, y1), _plan(b)) <= TOUCH:
            return True
    return False


def _mount(world: _World, item: _Item, rule) -> str | None:
    room = world.room_at(item.cx, item.cy, item.placed.z_low)
    if room is None:
        return None
    on = rule.get("on")
    if on == "wall" and not _on_a_wall(world, item, room):
        return "hangs free of any wall (a wall piece belongs on a wall)"
    band = rule.get("height")
    if band:
        mid = (item.placed.z_low + item.placed.z_high) / 2.0 - room.floor_z
        if not float(band[0]) <= mid <= float(band[1]):
            return f"its middle is {mid:.0f} above the floor, outside {band[0]}-{band[1]}"
    return None


def _needs_near(world: _World, item: _Item, rules) -> str | None:
    for rule in rules:
        what, within, where = rule.get("what", ["*"]), float(rule.get("within", 6.0)), rule.get("where", "around")
        plan = _plan(item.box)
        found = False
        if where == "below":
            low = item.placed.z_low
            pool = [b for _bid, b in world.brushes] if "brush" in what or "*" in what else []
            pool += [o.box for o in world.items if o is not item and _matches(o.prop.model, what)]
            for b in pool:
                if abs(b[5] - low) <= within and _gap(plan, _plan(b)) <= 0.0 and b[5] - b[2] > 1.0:
                    found = True
                    break
        else:
            pool = [b for _bid, b in world.brushes] if "brush" in what else []
            pool += [o.box for o in world.items if o is not item and _matches(o.prop.model, what)]
            found = any(_gap3(item.box, b) <= within for b in pool)
        if not found:
            return f"nothing {where} it within {within:g} units: needs {rule.get('why', ', '.join(what))}"
    return None


def _floating_runs(world: _World, members: list[_Item], gap: float) -> list[list[_Item]]:
    """The connected runs among *members* that touch nothing else."""
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(members):
        for j in range(i + 1, len(members)):
            if _gap3(a.box, members[j].box) <= gap:
                parent[find(i)] = find(j)
    runs: dict[int, list[_Item]] = defaultdict(list)
    for i, m in enumerate(members):
        runs[find(i)].append(m)
    ids = {id(m) for m in members}
    out = []
    for run in runs.values():
        if not any(_anchored(world, m, gap, ids) for m in run):
            out.append(run)
    return out


def _anchored(world: _World, item: _Item, gap: float, run_ids) -> bool:
    b = item.box
    room = world.room_at(item.cx, item.cy, b[2])
    if room is None:
        return True  # outdoors: nothing to measure against, so not asked
    box = room.interior
    if (b[2] - room.floor_z <= gap or box.maxs.z - b[5] <= gap
            or b[0] - box.mins.x <= gap or box.maxs.x - b[3] <= gap
            or b[1] - box.mins.y <= gap or box.maxs.y - b[4] <= gap):
        return True
    if any(_gap3(b, bb) <= gap for _bid, bb in world.brushes):
        return True
    return any(id(o) not in run_ids and _gap3(b, o.box) <= gap for o in world.items if o is not item)


# -- the check ---------------------------------------------------------------
def check_prop_rules(blueprint) -> Report:
    """Z60, a warning per rule and model a map breaks, with the count."""
    from ..props.notes import massing_rules

    report = Report()
    world = _World(blueprint)
    broken: dict[tuple[str, str], list[str]] = defaultdict(list)
    first: dict[tuple[str, str], str] = {}

    def hit(rule: str, model: str, where: str, why: str, element: str) -> None:
        broken[(rule, model)].append(f"{where}: {why}")
        first.setdefault((rule, model), element)

    judges = (("faces", _faces), ("faced_by", _faced_by), ("clearance_front", _clearance_front),
              ("mount", _mount), ("needs_near", _needs_near))
    per_room: dict[tuple[str, str], list[_Item]] = defaultdict(list)
    runs: dict[float, list[_Item]] = defaultdict(list)
    for item in world.items:
        rules = item.rules
        if not rules:
            continue
        at = f"{item.ident} at {item.prop.origin.x:g} {item.prop.origin.y:g} {item.prop.origin.z:g}"
        for key, judge in judges:
            if key in rules:
                why = judge(world, item, rules[key])
                if why:
                    hit(key, item.prop.model, at, why, item.scatter)
        if "connects" in rules:
            runs[float(rules["connects"].get("gap", TOUCH))].append(item)
        if "max_per_room" in rules or "not_in" in rules:
            room = world.room_at(item.cx, item.cy, item.placed.z_low)
            if room is None:
                continue
            if "max_per_room" in rules:
                per_room[(room.id, item.prop.model)].append(item)
            for word in rules.get("not_in", ()):
                if word in room.id:
                    hit("not_in", item.prop.model, at, f"in {room.id}, a {word} room", item.scatter)
                    break
    for (room_id, model), items in per_room.items():
        cap = int(items[0].rules["max_per_room"])
        if len(items) > cap:
            hit("max_per_room", model, f"{room_id}", f"{len(items)} in one room, at most {cap}",
                items[0].scatter)
    for gap, members in runs.items():
        for run in _floating_runs(world, members, gap):
            m = run[0]
            hit("connects", m.prop.model,
                f"{m.ident} at {m.prop.origin.x:g} {m.prop.origin.y:g} {m.prop.origin.z:g}",
                f"a run of {len(run)} piece(s) touches no floor, ceiling, wall, brush or fixture",
                m.scatter)
    for key, patterns, rules in massing_rules():
        assembly = rules.get("assembly")
        if not assembly:
            continue
        token, gap = assembly["group_by"], float(assembly.get("gap", TOUCH))
        groups: dict[str, list] = defaultdict(list)
        for bid, box in world.brushes:
            if any(fnmatch.fnmatchcase(bid, p) for p in patterns) and token in bid:
                groups[bid.split(token, 1)[0]].append((bid, box))
        for prefix, parts in sorted(groups.items()):
            parent = list(range(len(parts)))

            def find(i: int) -> int:
                while parent[i] != i:
                    i = parent[i]
                return i

            for i in range(len(parts)):
                for j in range(i + 1, len(parts)):
                    if _gap3(parts[i][1], parts[j][1]) <= gap:
                        parent[find(i)] = find(j)
            roots = {find(i) for i in range(len(parts))}
            if len(roots) > 1:
                strays = sorted(parts[i][0] for i in range(len(parts))
                                if find(i) != max(roots, key=lambda r: sum(find(k) == r for k in range(len(parts)))))
                hit("assembly", f"{key} {prefix}", prefix,
                    f"{len(roots)} separate pieces, {', '.join(strays[:4])} off the rest", parts[0][0])
    for (rule, model), where in sorted(broken.items()):
        report.add(
            warning(
                "Z60",
                f"{rule}: {model} x{len(where)} (first {where[0]})"
                + (f"; also {', '.join(w.split(':')[0] for w in where[1:4])}" if len(where) > 1 else ""),
                first[(rule, model)],
            )
        )
    return report
