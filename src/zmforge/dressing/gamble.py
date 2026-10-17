"""The gamble machine, at the farthest point of every map (P22).

Every map carries one machine that takes 2,000 points for a
1 in 4 chance at 10,000 (the mechanic is
:mod:`zmforge.script.gamble`).  This module decides where it goes and builds
what the player sees.

**Where: the farthest walk.**  Distance is walking distance from the spawn,
not a straight line: a Dijkstra over the same standing rectangles and the
same links (:func:`zmforge.verify.reachability._how`, ``_gap_jump``) as the
``Z25`` flood, at the flood's own cost (each link tested once).  Walls
decide the walk; furniture does not (see :func:`walking_distances`).  Doors are not obstacles to that flood, so a room behind
a door counts: the farthest point is somewhere a player has to buy their way
to.  A split start (:mod:`zmforge.script.splitstart`)
is measured from the hub (``PlayerStart.position``), and its sealed zones are
never candidates and never walked through.

Candidates are wall spots in every reachable room, every 32 units along each
interior wall, 48 in from the corners, back to the wall and facing into the
room; they are tried farthest first, and the first that passes every test in
:func:`_fits` wins: flat reachable ground in that room, 128 units from any
other interactive or quest trigger, 64 from a doorway and 96 from a
barricade, clear of every interactive's keep, no prop wider than
:data:`BIG_PROP` where it stands, and ``Z9``'s own two brushwork questions (a
stand box clear of world solids with floor under it, no brushwork in the
front of the body).  Smaller dressing in its body or stand is taken out, with
whatever stood on it, the way an approach lane clears (``lanes``): in a
densely dressed map every far wall is furnished, and the farthest point wins
over a crate.

**What: one model slot.**  The custom ``zmf_prop_gamble_atm`` (an ATM-like
cabinet, origin at floor centre, front facing -Y at yaw 0 like the stock
perk machines, 44 x 36 x 91 with its plate, its own ``LUCKY 4`` topper) once
it is in the prop library; until then a brush cabinet of that footprint with
``1 IN 4`` on its face and the name (``LUCKY 4``) in brush lettering on the
wall above.  Either way a small warm light pool stands in front of it.

**When.**  :meth:`zmforge.project.Project.commit` calls
:func:`place_gamble_machine` after the power bolts and before the camping
clips and the checks, so every map gets it with no recipe line.  A recipe
says otherwise with ``bp.signature_gamble``: ``False`` for none (test maps),
or a :class:`SignatureGamble` for a fixed spot, another name, other odds or
another limit.  What was placed is ``bp.gamble_machine`` (a
:class:`GamblePlacement`); why nothing was, ``bp.gamble_failure``.  ``Z87``
(:mod:`zmforge.verify.gamble`) holds every map not opted out to exactly one.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ..spatial import Facing, Point, Span

__all__ = [
    "ATM_MODEL",
    "WIDTH",
    "DEPTH",
    "HEIGHT",
    "SignatureGamble",
    "GamblePlacement",
    "walking_distances",
    "place_gamble_machine",
]

#: The custom cabinet model (modelled separately; used once it is in
#: :data:`zmforge.props.library.PROPS`).
ATM_MODEL = "zmf_prop_gamble_atm"
#: The cabinet's footprint: across its face, front to back, and tall -- the
#: custom model's measured box (``recipes/props.py``; as linked:
#: (-22, -18, 0) .. (22, 18, 90.9), the back conduit included).
WIDTH, DEPTH, HEIGHT = 44.0, 36.0, 90.9
#: Gap between the cabinet's back and the wall.
WALL_GAP = 1.0
#: Where the player stands to use it, in front of the origin.
STAND = 48.0
#: No other interactive or quest trigger within this of the machine.
CLEAR_OF_OTHERS = 128.0
CLEAR_OF_DOORWAYS = 64.0
CLEAR_OF_WINDOWS = 96.0
#: Wall spots every this many units, this far in from each corner.
STEP = 32.0
CORNER = 48.0
#: At most this many candidates are tested, farthest first.
MAX_TRIED = 600
LIGHT_COLOUR = (1.0, 0.78, 0.45)
LIGHT_RADIUS = 256.0
SIGN_HEIGHT = 104.0
USE_LABEL = "gamble machine"
#: A prop wider than this in plan is part of what a room is built round (a
#: car, a counter run); the machine never clears one to fit.
BIG_PROP = 120.0


@dataclass(frozen=True)
class SignatureGamble:
    """A recipe's say over its gamble machine.  Every field left alone is
    the default; ``position`` (with ``facing``, the way the machine's front
    looks) pins it instead of searching for the farthest spot."""

    position: Point | None = None
    facing: Facing | str | None = None
    name: str = "LUCKY 4"
    cost: int | None = None
    prize: int | None = None
    wins: int | None = None
    out_of: int | None = None
    #: Plays per player per round; ``None`` here means the default (1).
    per_round: int | None = None
    #: ``True``: no per-round limit at all.
    unlimited: bool = False
    light_colour: tuple[float, float, float] = LIGHT_COLOUR
    #: Force a model (``None``: the custom ATM when it exists, else brushes).
    model: str | None = None


@dataclass
class GamblePlacement:
    position: Point
    facing: Facing
    room_id: str
    zone: str
    walk: float | None
    stand: Point
    model: str | None
    #: Dressing props taken out to make room (and what stood on them).
    cleared: int = 0
    ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Walking distance
# ---------------------------------------------------------------------------
@dataclass
class Walk:
    cells: tuple
    dist: dict
    index: dict

    def at(self, x: float, y: float, z: float) -> float | None:
        """Walking distance to (x, y) on the floor at z, or ``None``."""
        from ..verify.reachability import (PLAYER_REACH_DOWN, STEP_TOLERANCE, TOUCH,
                                           _BUCKET)

        key = (math.floor(x / _BUCKET), math.floor(y / _BUCKET))
        best = None
        for i in self.index.get(key, ()):
            d = self.dist.get(i)
            if d is None:
                continue
            cell = self.cells[i]
            if not cell.floor.holds_flat(x, y, tolerance=TOUCH):
                continue
            if not (-STEP_TOLERANCE <= z - cell.z <= PLAYER_REACH_DOWN):
                continue
            c = cell.floor.centre
            total = d + math.hypot(x - c.x, y - c.y)
            if best is None or total < best:
                best = total
        return best


def _sealed(bp) -> tuple[list, Point | None]:
    """The sealed zones' boxes and, for a split start, the hub point."""
    from ..blueprint.elements import PlayerStart, Zone

    starts = list(bp.elements(PlayerStart))
    names = set()
    for s in starts:
        names |= set(getattr(s, "sealed_zones", ()) or ())
    boxes = [z.bounds for z in bp.elements(Zone) if z.name in names and z.bounds is not None]
    hub = starts[0].position if names and starts else None
    return boxes, hub


def _standing_cells(bp, obstacles) -> list:
    """:func:`zmforge.verify.reachability.standing_cells`, the same cells,
    with the obstacles handed to each patch pre-filtered through a plan grid.
    The stock function scans every obstacle for every patch; on zm_cemetery
    (6,349 patches) that scan was most of a 53 s walk (cProfile)."""
    from ..verify.model import _standing_patches
    from ..verify.reachability import Standing, _free_rects, _raised_sills

    cell = 512.0
    grid: dict = {}
    for n, box in enumerate(obstacles):
        for gx in range(math.floor(box.mins.x / cell), math.floor(box.maxs.x / cell) + 1):
            for gy in range(math.floor(box.mins.y / cell), math.floor(box.maxs.y / cell) + 1):
                grid.setdefault((gx, gy), []).append(n)

    def near(patch) -> list:
        found: set = set()
        for gx in range(math.floor(patch.mins.x / cell), math.floor(patch.maxs.x / cell) + 1):
            for gy in range(math.floor(patch.mins.y / cell), math.floor(patch.maxs.y / cell) + 1):
                found.update(grid.get((gx, gy), ()))
        return [obstacles[n] for n in sorted(found)]

    cells: list = []
    sources = [(patch, False) for patch in _standing_patches(bp)]
    sources += [(patch, True) for patch in _raised_sills(bp)]
    for (label, element_id, patch, z), sill in sources:
        for rect in _free_rects(patch, z, near(patch)):
            cells.append(Standing(label, element_id, rect, z, sill))
    return cells


def walking_distances(bp, *, dressed: bool = False, jumps: bool = False) -> Walk:
    """Walking distance from the spawn (the hub, after a split start) to
    every standing rectangle ``Z25`` floods; see the module docstring.

    One pass at the flood's own cost: each cell is linked (``_how``, then
    ``_gap_jump``) at most once, and is taken out of the bucket index the
    moment it is reached, exactly as :func:`~zmforge.verify.reachability.
    flood_from_spawn` does.  Cells are expanded nearest first (a heap), so a
    cell's distance is its first discoverer's plus the centre-to-centre step:
    Dijkstra's order with the flood's cost, an upper bound within one cell's
    width of the true shortest walk.  (A full Dijkstra re-tests every link
    until a cell is settled and ran for over 50 minutes on zm_cemetery.)

    ``dressed`` counts the floor props as obstacles too, as ``Z48`` does.  It
    is off by default: on zm_corn_maze the 11,390 prop boxes cut the floor
    into 37,860 rectangles (59 s before a single link is tested) against 726
    for the building alone (0.2 s), and walls, not furniture, decide how far
    a room is.  ``jumps`` adds the flood's gap-jump links; off by default
    because testing them is most of the cost on a terrain map and the
    machine belongs on floor a player walks to, not jumps to.  The chosen
    spot's own stand is cleared of dressing
    (:func:`_clear_dressing`) and ``Z55``/``Z48`` check the way to it."""
    from ..verify.reachability import (GAP_JUMP, _buckets, _gap_jump, _how, _obstacles,
                                       _seed_cells)

    obstacles = list(_obstacles(bp))
    if dressed:
        from ..verify.approach import prop_obstacles

        obstacles += prop_obstacles(bp)[0]
    sealed, hub = _sealed(bp)
    cells = [c for c in _standing_cells(bp, obstacles)
             if not any(b.holds_flat(c.floor.centre.x, c.floor.centre.y) for b in sealed)]
    index: dict = {}
    for i, cell in enumerate(cells):
        for key in _buckets(cell):
            index.setdefault(key, set()).add(i)
    open_ = {k: set(v) for k, v in index.items()}
    seeds = _seed_cells(bp, cells, [hub] if hub is not None else None)
    dist: dict = {}

    def take(i: int, d: float) -> None:
        dist[i] = d
        for key in _buckets(cells[i]):
            bucket = open_.get(key)
            if bucket is not None:
                bucket.discard(i)

    for i in seeds:
        take(i, 0.0)
    heap = [(0.0, i) for i in seeds]
    while heap:
        d, i = heapq.heappop(heap)
        here = cells[i]
        near: set = set()
        for key in _buckets(here, reach=GAP_JUMP):
            near.update(open_.get(key, ()))
        a = here.floor.centre
        for j in near:
            if j in dist:
                continue
            there = cells[j]
            if _how(here, there) is None and (
                    not jumps or _gap_jump(here, there, obstacles) is None):
                continue
            b = there.floor.centre
            nd = d + math.hypot(a.x - b.x, a.y - b.y) + abs(here.z - there.z)
            take(j, nd)
            heapq.heappush(heap, (nd, j))
    return Walk(tuple(cells), dist, index)


# ---------------------------------------------------------------------------
# Candidates and the fit test
# ---------------------------------------------------------------------------
def _candidates(bp, sealed) -> list[tuple[Point, Facing, object]]:
    from ..blueprint.elements import Room

    inset = DEPTH / 2.0 + WALL_GAP
    out = []
    for room in bp.elements(Room):
        if not room.reachable:
            continue
        box = room.interior
        c = box.centre
        if any(b.holds_flat(c.x, c.y) for b in sealed):
            continue
        z = room.floor_z
        x0, x1 = box.mins.x + CORNER, box.maxs.x - CORNER
        y0, y1 = box.mins.y + CORNER, box.maxs.y - CORNER
        xs = [x0 + STEP * i for i in range(int((x1 - x0) // STEP) + 1)] if x1 >= x0 else []
        ys = [y0 + STEP * i for i in range(int((y1 - y0) // STEP) + 1)] if y1 >= y0 else []
        for x in xs:
            out.append((Point(x, box.maxs.y - inset, z), Facing.SOUTH, room))
            out.append((Point(x, box.mins.y + inset, z), Facing.NORTH, room))
        for y in ys:
            out.append((Point(box.maxs.x - inset, y, z), Facing.WEST, room))
            out.append((Point(box.mins.x + inset, y, z), Facing.EAST, room))
    return out


def _flat_distance(p: Point, box: Span) -> float:
    dx = max(box.mins.x - p.x, 0.0, p.x - box.maxs.x)
    dy = max(box.mins.y - p.y, 0.0, p.y - box.maxs.y)
    return math.hypot(dx, dy)


def _cabinet(at: Point, facing: Facing) -> Span:
    step = facing.step
    half_w, half_d = WIDTH / 2.0, DEPTH / 2.0
    hx = abs(step.x) * half_d + abs(step.y) * half_w
    hy = abs(step.y) * half_d + abs(step.x) * half_w
    return Span(Point(at.x - hx, at.y - hy, at.z), Point(at.x + hx, at.y + hy, at.z + HEIGHT))


def _fits(bp, at: Point, facing: Facing, room, *,
          clear_props: bool = False) -> tuple[Point | None, str]:
    """``(spot, "")`` if a machine fits at ``at``, else ``(None, why)``.

    ``clear_props`` lets dressing stand where the machine and its stand go
    (:func:`_clear_dressing` takes it out afterwards), unless one of those
    props is a big piece (:data:`BIG_PROP` across) a room is built round."""
    from ..blueprint import reach
    from ..blueprint.catalogue import perk_named
    from ..blueprint.elements import Machine, Window
    from ..script.gobblegum import (_body_hits_a_prop, _clear_of_others,
                                    _front_hits_brushwork, _room_of, _world_boxes)
    from ..verify.model import _approach_box

    ground = bp.ground_under(at.x, at.y, below=at.z + 32.0)
    if not ground.found and room is not None and not room.roofed:
        ground = bp.ground_under(at.x, at.y, below=at.z + 512.0)  # terrain
    if not ground.found or not ground.reachable:
        return None, "no reachable floor"
    if ground.spread > 1.0:
        return None, "uneven ground"
    spot = Point(at.x, at.y, ground.z)
    if room is not None and _room_of(bp, spot) is not room:
        return None, "not in its room"
    if not _clear_of_others(bp, spot):
        return None, "another interactive within 128"
    for _label, p, _r in getattr(bp, "quest_use_points", ()) or ():
        if abs(p.z - spot.z) < 96.0 and math.hypot(p.x - spot.x, p.y - spot.y) < CLEAR_OF_OTHERS:
            return None, "a quest trigger within 128"
    if room is not None:
        for hole in room.aperture_boxes:
            if _flat_distance(spot, hole) < CLEAR_OF_DOORWAYS:
                return None, "beside a doorway"
    for window in bp.elements(Window):
        o = window.barricade_origin
        if o is not None and abs(o.z - spot.z) < 128.0 and \
                math.hypot(o.x - spot.x, o.y - spot.y) < CLEAR_OF_WINDOWS:
            return None, "beside a barricade"
    probe = Machine(id="gamble_probe", perk=perk_named("gobblegum"), position=spot,
                    facing=facing)
    keep = reach.keep_of(probe)
    if keep is not None and reach.first_clash(keep, bp.interactive_keeps()) is not None:
        return None, "in an interactive's keep"
    if clear_props:
        if any(_big(box) for _prop, box in _props_in(bp, _zones_to_clear(probe, keep, spot))):
            return None, "a big prop where it would stand"
    else:
        if keep is not None and _body_hits_a_prop(bp, keep.body):
            return None, "a prop in its body"
        if _body_hits_a_prop(bp, _approach_box(probe, spot.z)):
            return None, "a prop in its stand"
    if _front_hits_brushwork(bp, probe, spot.z):
        return None, "brushwork in its stand or front (Z9)"
    body = _cabinet(Point(spot.x, spot.y, spot.z + 1.0), facing)
    if any(b.overlaps(body, slack=0.0) for b in _world_boxes(bp)):
        return None, "cabinet inside a world solid"
    return spot, ""


def _zones_to_clear(probe, keep, spot: Point) -> list:
    """The machine's own body, the stock machine body the keep rules use,
    and the stand in front, as boxes."""
    from ..verify.model import _approach_box

    boxes = [_cabinet(spot, probe.facing), _approach_box(probe, spot.z)]
    if keep is not None:
        boxes.append(keep.body)
    return boxes


def _props_in(bp, boxes) -> list:
    """``(prop, world box)`` for every prop whose box meets one of *boxes*."""
    from ..blueprint.elements import PropScatter
    from ..script.gobblegum import _prop_box

    out = []
    for scatter in bp.elements(PropScatter):
        for prop in scatter.props:
            o = prop.origin
            if not any(b.mins.x - 200.0 < o.x < b.maxs.x + 200.0
                       and b.mins.y - 200.0 < o.y < b.maxs.y + 200.0 for b in boxes):
                continue
            span = _prop_box(prop)
            if span is None:
                continue
            x0, y0, z0, x1, y1, z1 = span
            if any(x0 < b.maxs.x and x1 > b.mins.x and y0 < b.maxs.y and y1 > b.mins.y
                   and z0 < b.maxs.z and z1 > b.mins.z for b in boxes):
                out.append((prop, span))
    return out


def _big(span) -> bool:
    x0, y0, _z0, x1, y1, _z1 = span
    return max(x1 - x0, y1 - y0) > BIG_PROP


def _clear_dressing(bp, spot: Point, facing: Facing) -> int:
    """Take out the dressing in the machine's body and stand, and whatever
    stood on it (:func:`zmforge.blueprint.lanes._drop_what_stood_on`, the
    lane rule's own sweep).  Returns how many props went."""
    from ..blueprint import reach
    from ..blueprint.catalogue import perk_named
    from ..blueprint.elements import Machine, PropScatter
    from ..blueprint.lanes import _drop_what_stood_on

    probe = Machine(id="gamble_probe", perk=perk_named("gobblegum"), position=spot,
                    facing=facing)
    hits = _props_in(bp, _zones_to_clear(probe, reach.keep_of(probe), spot))
    if not hits:
        return 0
    gone = {id(p) for p, _span in hits}
    cleared = getattr(bp, "lane_cleared", None)
    if cleared is None:
        cleared = []
        bp.lane_cleared = cleared
    before = len(cleared)
    for scatter in bp.elements(PropScatter):
        kept = [p for p in scatter.props if id(p) not in gone]
        if len(kept) != len(scatter.props):
            for p in scatter.props:
                if id(p) in gone:
                    cleared.append((p.id or scatter.id, "gamble_machine"))
            scatter.props = kept
    removed = [(span, "gamble_machine") for _p, span in hits]
    history = getattr(bp, "_lane_removed", None)
    if history is not None:
        history.extend(removed)
    _drop_what_stood_on(bp, removed, cleared)
    return len(cleared) - before


# ---------------------------------------------------------------------------
# Placing it
# ---------------------------------------------------------------------------
def _custom_model_ready() -> bool:
    """The custom cabinet is in the prop kit *and* has its measured box
    (``recipes/props.py`` ``CATALOGUE_BOX``), which the collmap bake needs;
    until both, the brush fallback stands in."""
    from ..props.library import PROPS
    from ..recipes.props import MODEL_BOX

    return ATM_MODEL in MODEL_BOX and any(p.name == ATM_MODEL for p in PROPS)


def _spec(bp) -> SignatureGamble | None:
    value = getattr(bp, "signature_gamble", None)
    if value is False:
        return None
    if value is None or value is True:
        return SignatureGamble()
    if not isinstance(value, SignatureGamble):
        raise TypeError("bp.signature_gamble is False, None or a SignatureGamble")
    return value


def place_gamble_machine(bp) -> GamblePlacement | None:
    """Place the map's gamble machine (module docstring).

    Idempotent.  Returns the placement, or ``None`` when the recipe opted
    out or no spot fits (``bp.gamble_failure`` says which; ``Z87`` reports
    the second).  A pinned ``position`` that does not fit raises
    :class:`ValueError`: the recipe asked for something that cannot be.
    """
    if getattr(bp, "gamble_machine", None) is not None or \
            getattr(bp, "gamble_failure", None) is not None:
        return getattr(bp, "gamble_machine", None)
    spec = _spec(bp)
    if spec is None:
        bp.gamble_failure = "opted out"
        return None
    from ..blueprint.elements import PlayerStart, Room
    from ..placement.audit import _zone_named
    from ..blueprint.elements import Zone

    if not bp.elements(PlayerStart):
        bp.gamble_failure = "no player start"
        return None
    # The world solids as they stand now, as the boxes gobblegum's Z9 helpers
    # read.  From each solid's own face points (``_solid_bounds``, never
    # smaller than the solid) rather than ``inspect_solid``'s vertices:
    # the same answer or a more cautious one, in a tenth of the time
    # (zm_cemetery's 4,559 solids: 5.4 s under cProfile).
    from ..blueprint.model import _solid_bounds

    bp._zmf_bgb_world_boxes = [_solid_bounds(solid) for solid in bp.world_solids()]
    walk = walking_distances(bp)
    zones = list(bp.elements(Zone))
    chosen = None
    if spec.position is not None:
        if spec.facing is None:
            raise ValueError("SignatureGamble.position needs a facing")
        facing = Facing.of(spec.facing)
        from ..script.gobblegum import _room_of

        room = _room_of(bp, spec.position)
        spot, why = _fits(bp, spec.position, facing, None)
        if spot is None:
            raise ValueError(f"gamble machine at {spec.position}: {why}")
        chosen = (spot, facing, room)
    else:
        sealed, _hub = _sealed(bp)
        scored = []
        for at, facing, room in _candidates(bp, sealed):
            stand = at + facing.step.scaled(STAND)
            d = walk.at(stand.x, stand.y, at.z)
            if d is None and not room.roofed:
                # Terrain: the ground under an open-air room is not its floor_z.
                ground = bp.ground_under(stand.x, stand.y, below=at.z + 512.0)
                if ground.found:
                    d = walk.at(stand.x, stand.y, ground.z)
            if d is not None:
                scored.append((d, at, facing, room))
        scored.sort(key=lambda s: -s[0])
        for d, at, facing, room in scored[:MAX_TRIED]:
            spot, _why = _fits(bp, at, facing, room, clear_props=True)
            if spot is None:
                continue
            # The stand, at the machine's own floor, must be floor the
            # dressed walk reached (a spot scored off another storey's
            # floor under the stand does not count).
            stand = spot + facing.step.scaled(STAND)
            if walk.at(stand.x, stand.y, spot.z) is None:
                continue
            chosen = (spot, facing, room)
            break
        if chosen is None:
            bp.gamble_failure = (f"none of the {min(len(scored), MAX_TRIED)} farthest wall "
                                 "spots fits a machine")
            return None
    spot, facing, room = chosen
    cleared = _clear_dressing(bp, spot, facing) if spec.position is None else 0
    if cleared:
        # The plants lining the wall behind it went with the rest: an
        # opening Z89 excuses (dressing.lining.record_opening).
        from ..blueprint import reach
        from ..blueprint.catalogue import perk_named
        from ..blueprint.elements import Machine
        from .lining import record_opening

        probe = Machine(id="gamble_probe", perk=perk_named("gobblegum"), position=spot, facing=facing)
        for zone in _zones_to_clear(probe, reach.keep_of(probe), spot):
            record_opening(bp, zone, "gamble machine")
    stand = spot + facing.step.scaled(STAND)
    placement = GamblePlacement(
        position=spot, facing=facing, room_id=room.id if room is not None else "",
        zone=_zone_named(room, zones) if room is not None else "",
        walk=walk.at(stand.x, stand.y, spot.z), stand=stand, model=None,
        cleared=cleared)
    _build(bp, spec, placement, room)
    bp.gamble_machine = placement
    return placement


def _build(bp, spec: SignatureGamble, placement: GamblePlacement, room) -> None:
    from ..lettering import INK, brush_text
    from ..script import gamble as mech

    spot, facing = placement.position, placement.facing
    step = facing.step
    model = spec.model if spec.model is not None else (
        ATM_MODEL if _custom_model_ready() else None)
    placement.model = model
    if model is not None:
        # The model's front is -Y at yaw 0: +90 turns it to face.
        yaw = (math.degrees(math.atan2(step.y, step.x)) + 90.0) % 360.0
        from ..blueprint.elements import Prop

        # Its box in the model's own frame (width along X, front at -Y), so a
        # model the measured table does not know yet still bakes a collmap.
        from ..recipes.props import MODEL_BOX

        box = None if model in MODEL_BOX else (
            (-WIDTH / 2.0, -DEPTH / 2.0, 0.0), (WIDTH / 2.0, DEPTH / 2.0, HEIGHT))
        scatter = bp.place_props([Prop(model=model, origin=spot, yaw=yaw, solid=True,
                                       collision_box=box)], id="gamble_machine")
        placement.ids.append(scatter.id)
    else:
        cabinet = bp.add_block(_cabinet(spot, facing), INK, reachable=False,
                               id="gamble_cabinet", note="gamble machine (brush "
                               "fallback until the custom model links)")
        placement.ids.append(cabinet.id)
        from ..lettering import MARGIN, text_size

        face = spot + step.scaled(DEPTH / 2.0)
        odds = mech.odds_text(*_odds(spec)).upper()
        # As big as fits on the cabinet's face with its plate (Z43, Z84).
        cell = min(1.5, (WIDTH - 4.0 - 2.0 * MARGIN) / text_size(odds, 1.0)[0])
        placement.ids += brush_text(bp, odds, at=Point(face.x, face.y, spot.z + 60.0),
                                    facing=facing, cell=cell, ident="gamble_face")
        # The name on the wall above (the model carries its own topper),
        # below the wall's top on an open-air room.
        wall = spot - step.scaled(DEPTH / 2.0 + WALL_GAP)
        sign_z = spot.z + SIGN_HEIGHT
        if room is not None:
            top = room.outer.maxs.z if room.outer is not None else sign_z + 24.0
            sign_z = min(sign_z, top - 16.0)
        placement.ids += brush_text(bp, spec.name, at=Point(wall.x, wall.y, sign_z),
                                    facing=facing, cell=2.0, ident="gamble_sign")
    lamp_at = spot + step.scaled(60.0)  # the model's light: ~60 in front, 96 up
    lamp_at = Point(lamp_at.x, lamp_at.y, spot.z + 96.0)
    lamp = bp.place_light(lamp_at, colour=spec.light_colour, radius=LIGHT_RADIUS,
                          stops=_brightest_filler(bp, lamp_at), shadows=False,
                          id="gamble_light")
    placement.ids.append(lamp.id)
    wins, out_of = _odds(spec)
    cost = spec.cost if spec.cost is not None else mech.COST
    prize = spec.prize if spec.prize is not None else mech.PRIZE
    per_round = None if spec.unlimited else (
        spec.per_round if spec.per_round is not None else mech.PER_ROUND)
    lines = mech.gamble_lines(bp, name=spec.name, cost=cost, prize=prize, wins=wins,
                              out_of=out_of, per_round=per_round)
    trigger_at = spot + step.scaled(DEPTH / 2.0)
    bp.add_custom_logic(mech.gamble_script(
        Point(trigger_at.x, trigger_at.y, spot.z), lines, cost=cost, prize=prize,
        wins=wins, out_of=out_of, per_round=per_round))
    record = getattr(bp, "quest_use_points", None)
    if record is not None:
        # Just inside the cabinet's front: D6 skips the prop the point is in,
        # so the machine is not dressing in front of itself.
        use = spot + step.scaled(DEPTH / 2.0 - 4.0)
        record.append((USE_LABEL, Point(use.x, use.y, spot.z), mech.RADIUS))


def _brightest_filler(bp, at: Point) -> float | None:
    """The brightest lamp already within ``D5``'s filler reach of *at*, so
    the machine is lit at least as bright as the room round it (``D5``: play
    things lit first and brightest); ``None`` (the preset's default) when
    nothing brighter stands near."""
    from ..blueprint.elements import Lamp
    from ..lighting import STOPS_OVER_EXPOSURE
    from ..verify.design import FILLER_REACH

    best = None
    for lamp in bp.elements(Lamp):
        p = lamp.position
        if math.hypot(p.x - at.x, p.y - at.y) <= FILLER_REACH + 64.0 and \
                at.z - 128.0 <= p.z <= at.z + 512.0:
            s = bp.stops_of(lamp)
            best = s if best is None or s > best else best
    offset = bp.brightness_stops
    default = bp.exposure + STOPS_OVER_EXPOSURE + offset  # Blueprint.stops_of
    if best is None or best <= default:
        return None
    return best - offset  # a lamp's own stops go out with the offset added


def _odds(spec: SignatureGamble) -> tuple[int, int]:
    from ..script import gamble as mech

    return (spec.wins if spec.wins is not None else mech.WINS,
            spec.out_of if spec.out_of is not None else mech.OUT_OF)
