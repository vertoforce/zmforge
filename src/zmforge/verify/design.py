"""D1-D6: play-structure checks from the level design literature.

``docs/map-design-method.md`` section 8 states the practices the wider
level-design craft adds to our method.
These are the ones a blueprint can measure.  Every one is a **warning**: a map
without a training ring still plays, and ``Project.commit`` refuses a map only
on errors.

``D1`` training loop
    Every zone with zombie spawns has a closed walkable ring round a central
    block, with lanes at least :data:`LANE` wide and at least
    :data:`RING_MIN` round (measured along the lane's centre line), so a
    player can train zombies there.  Measured on a :data:`RES` floor grid of
    the zone's rooms and the doorways between them: a cell is a lane centre
    when the walkable floor reaches :data:`LANE` / 2 from it in every
    direction, and a ring is a closed band of lane centres round something
    that is not (a block, a building, a wall between two doors).
``D2`` (none)
    Research item 2, two ways out of a room with a perk, box, wall buy or
    quest station, was rejected as a rule: rooms with perks
    and buys do not need two exits.  The code is left unused.
``D3`` points to core
    A fact, not a check: the cheapest door spend from spawn to Juggernog,
    Quick Revive, power and the first box (:func:`points_to_core`, printed in
    the review facts).  No threshold until stock maps are measured.
``D4`` lock before key
    A lock (a quest's hand-in desk, its buyable exit) stands in a zone that
    opens no later, by cheapest door spend, than the zone of its first key
    or part.
``D5`` light the play first
    Every door, buyable and quest station has a lamp within
    :data:`PLAY_LIGHT` units, at least as bright as the filler lamps near it;
    every training ring (``D1``) is lit at its centre; and no point on the
    straight way from a room's doorways to its doors and buyables is more
    than :data:`DARK_GAP` units from a lamp.
``D6`` clean fronts
    No floor-standing prop whose top is over :data:`TALL` units stands in the
    :data:`FRONT_DEPTH` units in front of anything the player uses.  The
    front box is ``Z60``'s ``clearance_front`` (:func:`prop_rules.front_box`),
    asked of interactables rather than props.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

from .report import Report, error, warning

__all__ = [
    "DARK_GAP",
    "FRONT_DEPTH",
    "LANE",
    "PLAY_LIGHT",
    "RES",
    "RING_MIN",
    "TALL",
    "check_design",
    "check_training_loops",
    "check_lock_before_key",
    "check_play_lighting",
    "check_clean_fronts",
    "cheapest_route",
    "points_to_core",
    "quest_locks",
    "training_rings",
    "zone_spend",
]

#: Narrowest lane a training ring may have (research item 1).
LANE = 128.0
#: Shortest ring, measured along its lane centres (research item 1: ~1000).
RING_MIN = 1000.0
#: Floor grid pitch for ``D1``.
RES = 16.0
#: A zone grid over this many cells is measured on coarser cells.
MAX_CELLS = 600_000
#: A door, buyable or quest station needs a lamp this close (research item 5).
PLAY_LIGHT = 192.0
#: Filler lamps this close to a play thing are what it must match.
FILLER_REACH = 512.0
#: No point on a route to a door or buyable is further than this from a lamp
#: (the stock study's lit-floor radius, ``STOCK["lit_within_256"]``).
DARK_GAP = 256.0
#: Spacing of the samples along a route.
ROUTE_STEP = 64.0
#: A training ring's centre needs a lamp this close.
RING_LIGHT = 256.0
#: How deep the clean space in front of an interactable runs (research item 10).
FRONT_DEPTH = 96.0
#: A prop whose top is more than this over the floor is tall dressing.
TALL = 24.0
#: A prop no taller than this over the floor is stepped over (the Z53 step).
STEP = 18.0


# ---------------------------------------------------------------------------
# Zones and door spend
# ---------------------------------------------------------------------------
def _zone_boxes(bp):
    from ..blueprint.elements import Zone

    return [(z.name, z.bounds.mins.x, z.bounds.maxs.x, z.bounds.mins.y, z.bounds.maxs.y,
             z.bounds.mins.z, z.bounds.maxs.z) for z in bp.elements(Zone) if z.bounds is not None]


def zone_spend(bp) -> tuple[dict[str, int], dict[str, list[str]]]:
    """``(zone -> cheapest points to open it from the start, zone -> door ids)``.

    Over the zone manager's own edges (``bp.script.edges``): an ``always_on``
    edge is free, a door's flag costs that door's price, and a zone only a
    script flag opens is not in the result.
    """
    cost, steps = _cheapest(bp)
    return cost, {z: [door for door, _, _ in path if door] for z, path in steps.items()}


def cheapest_route(bp, zone: str, *, before_power: bool = False
                   ) -> list[tuple[str | None, str, str]]:
    """The cheapest way from the start into *zone*: ``(door id or None for a
    free edge, from zone, to zone)`` per step, spawn first; ``[]`` for a
    starting zone or one no door opens.  ``before_power`` leaves out the
    doors that stay shut until the power is on (``Door.power_gated``)."""
    return list(_cheapest(bp, before_power=before_power)[1].get(zone, ()))


def _cheapest(bp, *, before_power: bool = False):
    from ..blueprint.elements import Door, Zone

    price: dict[str, tuple[int, str]] = {}
    for door in bp.elements(Door):
        if before_power and door.power_gated:
            continue
        if door.flag and (door.flag not in price or door.price < price[door.flag][0]):
            price[door.flag] = (int(door.price), door.id)
    plan = bp.script
    always_on = plan.always_on_flag
    edges: dict[str, list[tuple[str, int, str | None]]] = defaultdict(list)
    for e in plan.edges:
        if e.flag == always_on:
            cost, label = 0, None
        elif e.flag in price:
            cost, label = price[e.flag]
        else:
            continue
        edges[e.zone_a].append((e.zone_b, cost, label))
        edges[e.zone_b].append((e.zone_a, cost, label))
    starts = [z.name for z in bp.elements(Zone) if z.starting]
    cost = {s: 0 for s in starts}
    via: dict[str, list] = {s: [] for s in starts}
    heap = [(0, s) for s in starts]
    while heap:
        c, zone = heapq.heappop(heap)
        if c > cost.get(zone, math.inf):
            continue
        for other, price_, label in edges.get(zone, ()):
            if c + price_ < cost.get(other, math.inf):
                cost[other] = c + price_
                via[other] = via[zone] + [(label, zone, other)]
                heapq.heappush(heap, (c + price_, other))
    return cost, via


def points_to_core(bp) -> dict:
    """``D3``: the cheapest door spend from spawn to the core of the map.

    Juggernog, Quick Revive, the power switch and the first mystery box
    location (the ``starting`` box, else the first placed).  A fact for the
    review: no threshold until stock maps are measured.
    """
    from ..blueprint.elements import Machine, MysteryBox, PowerSwitch
    from ..script.zonegate import zone_at

    spend, via = zone_spend(bp)
    boxes = _zone_boxes(bp)
    machines = list(bp.elements(Machine))
    boxes_ = list(bp.elements(MysteryBox))
    first_box = next((b for b in boxes_ if b.starting), boxes_[0] if boxes_ else None)
    targets = {
        "juggernog": next((m for m in machines if m.perk.slug == "juggernog"), None),
        "quick_revive": next((m for m in machines if m.perk.slug == "quick_revive"), None),
        "power": next(iter(bp.elements(PowerSwitch)), None),
        "first_box": first_box,
    }
    out: dict = {}
    for name, element in targets.items():
        if element is None:
            out[name] = None
            continue
        p = element.position
        zone = zone_at((p.x, p.y, p.z), boxes)
        out[name] = {"id": element.id, "zone": zone,
                     "door_spend": spend.get(zone) if zone else None,
                     "via": via.get(zone) if zone else None}
    out["note"] = ("fact only (D3): points of doors on the cheapest way from the start; "
                   "no threshold until stock maps are measured; null spend = opened by "
                   "script only or outside every zone")
    return out


# ---------------------------------------------------------------------------
# D1: training loops
# ---------------------------------------------------------------------------
def _rooms_by_zone(bp) -> dict[str, list]:
    from ..blueprint.elements import Room, Zone
    from ..placement.audit import _zone_named

    zones = list(bp.elements(Zone))
    out: dict[str, list] = defaultdict(list)
    for room in bp.elements(Room):
        if room.reachable:
            out[_zone_named(room, zones)].append(room)
    return out


def _edt(walk: list[list[bool]], nx: int, ny: int, res: float) -> list[list[float]]:
    """Distance from every walkable cell to the nearest blocked one (3-4 chamfer)."""
    big = 1e9
    d = [[big if walk[i][j] else 0.0 for j in range(ny)] for i in range(nx)]
    a, b = res, res * 1.4142
    for i in range(nx):
        row, prev = d[i], d[i - 1] if i else None
        for j in range(ny):
            v = row[j]
            if v:
                if j:
                    v = min(v, row[j - 1] + a)
                if prev is not None:
                    v = min(v, prev[j] + a)
                    if j:
                        v = min(v, prev[j - 1] + b)
                    if j + 1 < ny:
                        v = min(v, prev[j + 1] + b)
                row[j] = v
    for i in range(nx - 1, -1, -1):
        row, nxt = d[i], d[i + 1] if i + 1 < nx else None
        for j in range(ny - 1, -1, -1):
            v = row[j]
            if v:
                if j + 1 < ny:
                    v = min(v, row[j + 1] + a)
                if nxt is not None:
                    v = min(v, nxt[j] + a)
                    if j + 1 < ny:
                        v = min(v, nxt[j + 1] + b)
                    if j:
                        v = min(v, nxt[j - 1] + b)
                row[j] = v
    return d


def _zone_rings(rooms, blockers) -> list[dict]:
    """Every closed ring of wide lanes in one zone's rooms, longest first."""
    from .routes import _in_band

    x0 = min(r.interior.mins.x for r in rooms) - 2 * RES
    y0 = min(r.interior.mins.y for r in rooms) - 2 * RES
    x1 = max(r.interior.maxs.x for r in rooms) + 2 * RES
    y1 = max(r.interior.maxs.y for r in rooms) + 2 * RES
    res = RES
    while ((x1 - x0) / res) * ((y1 - y0) / res) > MAX_CELLS:
        res *= 2.0
    nx, ny = int((x1 - x0) // res) + 1, int((y1 - y0) // res) + 1

    def cells(bx0, by0, bx1, by1):
        i0, i1 = max(0, int((bx0 - x0) // res)), min(nx - 1, int((bx1 - x0) // res))
        j0, j1 = max(0, int((by0 - y0) // res)), min(ny - 1, int((by1 - y0) // res))
        for i in range(i0, i1 + 1):
            cx = x0 + (i + 0.5) * res
            if not bx0 <= cx <= bx1:
                continue
            for j in range(j0, j1 + 1):
                cy = y0 + (j + 0.5) * res
                if by0 <= cy <= by1:
                    yield i, j, cx, cy

    walk = [[False] * ny for _ in range(nx)]
    floor = [[None] * ny for _ in range(nx)]
    for room in rooms:
        b = room.interior
        for i, j, _, _ in cells(b.mins.x, b.mins.y, b.maxs.x, b.maxs.y):
            walk[i][j] = True
            floor[i][j] = room.floor_z
        for aperture, hole in zip(room.apertures, room.aperture_boxes):
            if aperture.sill > STEP:
                continue
            for i, j, _, _ in cells(hole.mins.x, hole.mins.y, hole.maxs.x, hole.maxs.y):
                walk[i][j] = True
                floor[i][j] = room.floor_z
    for blk in blockers:
        r = blk.reach()
        if blk.cx + r < x0 or blk.cx - r > x1 or blk.cy + r < y0 or blk.cy - r > y1:
            continue
        for i, j, cx, cy in cells(blk.cx - r, blk.cy - r, blk.cx + r, blk.cy + r):
            f = floor[i][j]
            if f is None or not walk[i][j] or not _in_band(blk, f):
                continue
            if blk.distance(cx, cy) <= res / 2.0:
                walk[i][j] = False
    dist = _edt(walk, nx, ny, res)
    need = LANE / 2.0 - res / 2.0
    lane = [[dist[i][j] >= need for j in range(ny)] for i in range(nx)]
    # Components of "not a lane centre" (4-connected); one that does not reach
    # the grid's edge is enclosed by lane centres: a ring's middle.
    label = [[0] * ny for _ in range(nx)]
    rings = []
    n = 0
    for si in range(nx):
        for sj in range(ny):
            if lane[si][sj] or label[si][sj]:
                continue
            n += 1
            label[si][sj] = n
            stack, members, edge, block = [(si, sj)], [], False, False
            while stack:
                i, j = stack.pop()
                members.append((i, j))
                if i in (0, nx - 1) or j in (0, ny - 1):
                    edge = True
                if not walk[i][j]:
                    block = True
                for u, v in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if 0 <= u < nx and 0 <= v < ny and not lane[u][v] and not label[u][v]:
                        label[u][v] = n
                        stack.append((u, v))
            if edge or not block:
                continue
            border = set()
            for i, j in members:
                for u in (i - 1, i, i + 1):
                    for v in (j - 1, j, j + 1):
                        if 0 <= u < nx and 0 <= v < ny and lane[u][v]:
                            border.add((u, v))
            cx = x0 + (sum(i for i, _ in members) / len(members) + 0.5) * res
            cy = y0 + (sum(j for _, j in members) / len(members) + 0.5) * res
            fl = [floor[i][j] for i, j in border if floor[i][j] is not None]
            rings.append({"length": len(border) * res, "centre": (cx, cy),
                          "floor": min(fl) if fl else None})
    rings.sort(key=lambda r: -r["length"])
    return rings


def training_rings(bp) -> dict[str, list[dict]]:
    """``zone -> rings`` for every zone with zombie spawns (``D1``)."""
    from ..blueprint.elements import Spawn
    from .routes import plans_from_blueprint

    spawning = {s.zone_name for s in bp.elements(Spawn) if not s.is_dog}
    by_zone = _rooms_by_zone(bp)
    wanted = {z: by_zone[z] for z in sorted(spawning) if by_zone.get(z)}
    if not wanted:
        return {}
    _, found = plans_from_blueprint(bp)
    # Z55 leaves detail and caulk-only brushes out (they do not split the
    # BSP); a player still walks into them, so a ring goes round them.
    blockers = [b for b in found if not b.label.startswith("brush ")] + _massing_blockers(bp)
    return {zone: _zone_rings(rooms, blockers) for zone, rooms in wanted.items()}


def _massing_blockers(bp) -> list:
    from ..blueprint.elements import STAIR_CLIP, Massing
    from ..blueprint.model import _solid_bounds
    from .routes import Blocker

    out = []
    for m in bp.elements(Massing):
        if m.note == STAIR_CLIP:
            continue
        for solid in m.solids:
            b = _solid_bounds(solid)
            out.append(Blocker.box(b.mins.x, b.mins.y, b.maxs.x, b.maxs.y, b.mins.z, b.maxs.z,
                                   f"brush {m.id}"))
    return out


def check_training_loops(bp, rings: dict | None = None) -> Report:
    """``D1``: every zone with spawns has a ring to train round."""
    report = Report()
    rings = training_rings(bp) if rings is None else rings
    for zone, found in rings.items():
        good = [r for r in found if r["length"] >= RING_MIN]
        if good:
            continue
        best = (f"; the longest closed ring is {found[0]['length']:.0f} units round"
                if found else "; there is no closed ring at all")
        report.add(warning(
            "D1", f"zone {zone}: zombies spawn here and there is no closed ring of lanes "
            f"{LANE:g}+ units wide, {RING_MIN:g}+ units round, round a central block to "
            f"train them round{best} (map-design-method section 8: train, then transit)",
            zone))
    return report


# ---------------------------------------------------------------------------
# D4: lock before key
# ---------------------------------------------------------------------------
def quest_locks(quest) -> list[dict]:
    """Every lock in *quest* and the keys or parts it takes (for ``D4``).

    A hand-in step's desk takes its items; the buyable exit takes the whole
    quest, so its keys are every step's points.
    """
    from ..script.quest import CollectDeliver, step_points

    out = []
    for step in quest.steps:
        if isinstance(step, CollectDeliver) and step.deliver:
            out.append({"label": f"quest {quest.key} step {step.key} desk",
                        "lock": [float(c) for c in step.deliver_at],
                        "keys": [[float(c) for c in it.point] for it in step.items]})
    if quest.exit is not None:
        keys = [[float(c) for c in p] for s in quest.steps for p in step_points(s)]
        if keys:
            out.append({"label": f"quest {quest.key} exit",
                        "lock": [float(c) for c in quest.exit.origin], "keys": keys})
    return out


def check_lock_before_key(bp) -> Report:
    """``D4``: each lock's zone opens no later than its first key's zone."""
    from ..script.zonegate import zone_at

    report = Report()
    locks = getattr(bp, "quest_locks", None) or []
    if not locks:
        return report
    spend, _ = zone_spend(bp)
    boxes = _zone_boxes(bp)
    for lock in locks:
        lz = zone_at(lock["lock"], boxes)
        keyed = [(spend.get(z, math.inf), z) for p in lock["keys"]
                 if (z := zone_at(p, boxes)) is not None]
        if lz is None or not keyed:
            continue
        first_cost, first_zone = min(keyed)
        lock_cost = spend.get(lz, math.inf)
        if first_cost == math.inf or lock_cost <= first_cost:
            continue
        where = "(" + ", ".join(f"{c:g}" for c in lock["lock"]) + ")"
        opens = ("opens only by script" if lock_cost == math.inf
                 else f"opens at {lock_cost:g} points of doors")
        report.add(warning(
            "D4", f"{lock['label']}: the lock is in zone {lz}, which {opens}, but its first "
            f"key or part is in zone {first_zone}, open at {first_cost:g}: players find the "
            "key before they have seen the lock (show the lock before the key)",
            position=where))
    return report


# ---------------------------------------------------------------------------
# D5: light the play first
# ---------------------------------------------------------------------------
def _play_things(bp) -> list[tuple[str, float, float, float]]:
    from ..blueprint.elements import (Door, Machine, MysteryBox, PowerSwitch, WallWeapon,
                                      Wunderfizz)

    out = []
    for d in bp.elements(Door):
        c = d.box.centre
        out.append((f"door {d.id}", c.x, c.y, d.box.mins.z))
    for kind, name in ((Machine, None), (MysteryBox, "box"), (PowerSwitch, "power switch"),
                       (Wunderfizz, "wunderfizz"), (WallWeapon, None)):
        for e in bp.elements(kind):
            label = (f"{e.perk.slug} machine" if kind is Machine
                     else f"{e.slug} wall buy" if kind is WallWeapon else f"{name} {e.id}")
            out.append((label, e.position.x, e.position.y, e.position.z))
    for label, point, _r in getattr(bp, "quest_use_points", ()) or ():
        out.append((label, point.x, point.y, point.z))
    return out


def _lamps_near(lamps, x, y, z, reach):
    for lamp, lx, ly, lz, stops, radius in lamps:
        d = math.hypot(lx - x, ly - y)
        if d <= reach and d <= radius and z - 64.0 <= lz <= z + 512.0:
            yield lamp, d, stops


def check_play_lighting(bp, rings: dict | None = None) -> Report:
    """``D5``: doors, buyables and quest stations lit first and brightest;
    training rings lit at the centre; no dark gap on the way to them."""
    from ..blueprint.elements import Lamp, Room
    from .looks import _room_at

    report = Report()
    lamps = [(l, l.position.x, l.position.y, l.position.z, bp.stops_of(l), l.radius)
             for l in bp.elements(Lamp)]
    things = _play_things(bp)
    if not lamps or not things:
        return report
    play = set()
    for _, x, y, z in things:
        for lamp, _d, _s in _lamps_near(lamps, x, y, z, PLAY_LIGHT):
            play.add(id(lamp))
    filler = [entry for entry in lamps if id(entry[0]) not in play]
    rooms = [r for r in bp.elements(Room) if r.reachable]
    unlit: dict[str, list[str]] = defaultdict(list)
    dim: dict[str, list[str]] = defaultdict(list)
    for label, x, y, z in things:
        room = _room_at(rooms, x, y, z + 8.0)
        key = room.id if room else "outside"
        near = list(_lamps_near(lamps, x, y, z, PLAY_LIGHT))
        if not near:
            unlit[key].append(label)
            continue
        best = max(s for _, _, s in near)
        rivals = [s for _, _, s in _lamps_near(filler, x, y, z, FILLER_REACH)]
        if rivals and max(rivals) > best + 1e-6:
            dim[key].append(f"{label} ({best:.1f} stops against {max(rivals):.1f})")
    # Perks and the power switch: an error, because Blueprint.light_rooms now gives every unlit door and
    # buyable a play lamp (zmforge.blueprint.autolamp); one left dark is a
    # map that skipped it.
    for key, labels in unlit.items():
        vital = [l for l in labels if l.endswith(" machine") or l.startswith("power switch")]
        if vital:
            report.add(error("D5", f"room {key}: no lamp within {PLAY_LIGHT:g} units of "
                                   + ", ".join(vital) + "; a perk or the power switch in the "
                                   "dark is walked past", key))
    for key, labels in unlit.items():
        report.add(warning("D5", f"room {key}: no lamp within {PLAY_LIGHT:g} units of "
                                 f"{len(labels)} door(s)/buyable(s)/quest station(s): "
                                 + ", ".join(labels[:4]) + (" ..." if len(labels) > 4 else ""),
                           key))
    for key, labels in dim.items():
        report.add(warning("D5", f"room {key}: {len(labels)} door(s)/buyable(s)/quest "
                                 "station(s) lit dimmer than the filler lamps near them: "
                                 + "; ".join(labels[:3]) + (" ..." if len(labels) > 3 else ""),
                           key))
    # Training rings: lit at the centre.
    rings = training_rings(bp) if rings is None else rings
    for zone, found in rings.items():
        for ring in found:
            if ring["length"] < RING_MIN:
                continue
            cx, cy = ring["centre"]
            fz = ring["floor"] if ring["floor"] is not None else 0.0
            if not any(True for _ in _lamps_near(lamps, cx, cy, fz, RING_LIGHT)):
                report.add(warning("D5", f"zone {zone}: the training ring round "
                                         f"({cx:.0f}, {cy:.0f}) has no lamp within "
                                         f"{RING_LIGHT:g} units of its centre", zone,
                                   position=f"({cx:.0f}, {cy:.0f})"))
    # Dark gaps on the way from each doorway to the room's doors and buyables.
    by_room: dict[str, list] = defaultdict(list)
    for label, x, y, z in things:
        room = _room_at(rooms, x, y, z + 8.0)
        if room is not None:
            by_room[room.id].append((label, x, y))
    for room in rooms:
        targets = by_room.get(room.id)
        if not targets:
            continue
        doorways = [((h.mins.x + h.maxs.x) / 2.0, (h.mins.y + h.maxs.y) / 2.0)
                    for a, h in zip(room.apertures, room.aperture_boxes) if a.sill <= STEP]
        dark = []
        for label, tx, ty in targets:
            for dx, dy in doorways:
                n = max(1, int(math.hypot(tx - dx, ty - dy) // ROUTE_STEP))
                gap = None
                for k in range(n + 1):
                    sx, sy = dx + (tx - dx) * k / n, dy + (ty - dy) * k / n
                    if not any(True for _ in _lamps_near(lamps, sx, sy, room.floor_z, DARK_GAP)):
                        gap = (sx, sy)
                        break
                if gap:
                    dark.append(f"{label} (dark at {gap[0]:.0f} {gap[1]:.0f})")
                    break
        if dark:
            report.add(warning("D5", f"room {room.id}: a dark gap (over {DARK_GAP:g} units from "
                                     f"any lamp) on the way from a doorway to {len(dark)} "
                                     "door(s)/buyable(s): " + "; ".join(dark[:3])
                                     + (" ..." if len(dark) > 3 else ""), room.id))
    return report


# ---------------------------------------------------------------------------
# D7: no long dark stretch of walk path
# ---------------------------------------------------------------------------
def check_path_lighting(bp) -> Report:
    """``D7``: along the map's declared walk paths (``bp.walk_paths``, a
    maze's passages), no stretch longer than
    :data:`zmforge.blueprint.autolamp.DARK_STRETCH` is over
    :data:`~zmforge.blueprint.autolamp.DARK_REACH` from every lamp (a
    warning; a dark stretch of path reads as unlit).  A map that declares no paths has nothing to answer."""
    from ..blueprint.autolamp import DARK_REACH, DARK_STRETCH, dark_stretches

    report = Report()
    runs = [r for r in dark_stretches(bp) if r[0] > DARK_STRETCH]
    if runs:
        where = "; ".join(f"{length:.0f} units from {run[0][0]} {run[0][1]}" for length, run in runs[:3])
        report.add(warning("D7", f"{len(runs)} stretch(es) of walk path over {DARK_STRETCH:g} units "
                                 f"long with no lamp within {DARK_REACH:g}: {where}"
                                 + (" ..." if len(runs) > 3 else "")))
    return report


# ---------------------------------------------------------------------------
# D6: clean fronts
# ---------------------------------------------------------------------------
def _fronts(bp):
    """``(label, x, y, z, fx, fy, reach, side)`` per face a player uses."""
    from ..blueprint.elements import (Door, Machine, MysteryBox, PowerSwitch, WallWeapon,
                                      Wunderfizz)
    from ..spatial import Axis

    out = []
    for kind, reach, side in ((Machine, 24.0, 32.0), (MysteryBox, 24.0, 48.0),
                              (PowerSwitch, 8.0, 24.0), (Wunderfizz, 24.0, 32.0),
                              (WallWeapon, 16.0, 32.0)):
        for e in bp.elements(kind):
            step = e.facing.step
            label = (f"{e.perk.slug} machine" if kind is Machine
                     else f"{e.slug} wall buy" if kind is WallWeapon
                     else f"{kind.__name__} {e.id}")
            out.append((label, e.position.x, e.position.y, e.position.z, step.x, step.y,
                        reach, side))
    for d in bp.elements(Door):
        c, b = d.box.centre, d.box
        if d.through_axis is Axis.X:
            half, depth, dirs = (b.maxs.y - b.mins.y) / 2.0, (b.maxs.x - b.mins.x) / 2.0, ((1, 0), (-1, 0))
        else:
            half, depth, dirs = (b.maxs.x - b.mins.x) / 2.0, (b.maxs.y - b.mins.y) / 2.0, ((0, 1), (0, -1))
        for fx, fy in dirs:
            out.append((f"door {d.id}", c.x, c.y, b.mins.z, float(fx), float(fy), depth, half))
    return out


def check_clean_fronts(bp) -> Report:
    """``D6``: no tall dressing in the space in front of anything the player uses."""
    from ..blueprint.elements import Room
    from .looks import _room_at
    from .prop_rules import _World, front_box, props_in

    report = Report()
    fronts = _fronts(bp)
    quest = list(getattr(bp, "quest_use_points", ()) or ())
    if not fronts and not quest:
        return report
    world = _World(bp)
    rooms = [r for r in bp.elements(Room) if r.reachable]
    hits: dict[str, list[str]] = {}
    where: dict[str, str] = {}

    def ask(label, zone, x, y):
        # Floor-standing props only: a monitor on the station's desk or a
        # board on the wall behind it is the station, not dressing in front.
        floor = zone[2] - TALL
        found = [it for it in props_in(world, zone, solid_only=False, prop_share=0.5,
                                       min_top=zone[2])
                 if it.box[2] <= floor + STEP
                 and not (it.box[0] <= x <= it.box[3] and it.box[1] <= y <= it.box[4])]
        if found:
            hits.setdefault(label, [])
            hits[label] += [f"{it.prop.model} ({it.ident})" for it in found
                            if f"{it.prop.model} ({it.ident})" not in hits[label]]
            where.setdefault(label, f"({x:.0f}, {y:.0f})")

    for label, x, y, z, fx, fy, reach, side in fronts:
        room = _room_at(rooms, x, y, z + 8.0)
        floor = room.floor_z if room is not None else z
        zone = front_box(x, y, fx, fy, reach, side, FRONT_DEPTH, floor + TALL, floor + 96.0)
        ask(label, zone, x, y)
    for label, p, _radius in quest:
        room = _room_at(rooms, p.x, p.y, p.z + 8.0)
        floor = room.floor_z if room is not None else p.z
        h = FRONT_DEPTH / 2.0
        ask(label, (p.x - h, p.y - h, floor + TALL, p.x + h, p.y + h, floor + 96.0), p.x, p.y)
    for label, found in hits.items():
        report.add(warning(
            "D6", f"{label}: {len(found)} prop(s) taller than {TALL:g} units stand in the "
            f"{FRONT_DEPTH:g} units in front of it, e.g. " + ", ".join(found[:3])
            + " (keep the front of anything the player uses clean)", position=where[label]))
    return report


# ---------------------------------------------------------------------------
def check_design(bp) -> Report:
    """``D1``, ``D4``, ``D5`` and ``D6`` over a blueprint (``D3`` is a
    review fact, :func:`points_to_core`)."""
    report = Report()
    rings = training_rings(bp)
    report.extend(check_training_loops(bp, rings))
    report.extend(check_lock_before_key(bp))
    report.extend(check_play_lighting(bp, rings))
    report.extend(check_path_lighting(bp))
    from .lightlevel import check_light_level

    report.extend(check_light_level(bp))
    report.extend(check_clean_fronts(bp))
    return report
