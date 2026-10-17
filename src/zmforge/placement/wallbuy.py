"""Wall buys go on real walls, never on a wall lined with plants.

WHY: a wall buy on a corn wall costs the corn in front of it.  The buy's
chalk has to be seen and its walk-up kept clear (``Z48``), so the lining
stops for the buy's width and a strip of painted wall shows through, right
where a player looks.  ``Z89`` excuses that strip as an opening, so the check
passes while the render shows bare wall.  The rule: a buy is never chalked on a
lined face (``bp.lined_faces``), so every lined wall can be filled
completely, and a recipe that asks for one there gets the nearest real wall
in the same zone instead (a building's wall, a board fence, a shed's wall),
so the gun list, the prices and the order the guns become reachable stay
the recipe's.

* :func:`place_wall_buy` is the placement: as asked when the spot is not on
  a lined face, else the nearest suitable unlined wall in the zone
  (:func:`find_wall_spot`), recorded on ``bp.moved_wall_buys``.
* :func:`buy_shed` builds an open-fronted shed of plank walls for a zone
  whose every wall is lined (a corn field, a maze), so the buy has a wall:
  a building's inside wall is where a player expects a gun to hang.
* ``Z91`` (:mod:`zmforge.verify.lining`) fails a buy on a lined face.

A wall face is suitable when the buy's whole keep fits in front of it: the
chalk and the floor a player stands on clear of every solid, its apron clear
of every other item's keep, of a doorway or window, of a spawn and of every
lined face's band (a buy beside the corn would clear the corn beside it), and
the face stands at least a chalk's height.  Walls of a roofed room, or with
one right behind them, count as a building's and are preferred by
:data:`BUILDING_BONUS`: a building wall nearby beats a fence in the
open.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..spatial import Bounds, Facing, Point

__all__ = ["BUILDING_BONUS", "STRUCTURE_BONUS", "BUY_DROP", "BUY_OFFSET", "WallFace", "buy_shed", "candidate_faces",
           "find_wall_spot", "place_wall_buy", "shed_footprint"]

#: A buy's origin stands this far off its wall (what every recipe uses).
BUY_OFFSET = 2.0
#: and this far under the floor (the prefab's mount sits low).
BUY_DROP = 8.0
#: Plan units a wall inside a building (a roof over the floor in front of
#: it) is preferred by over a fence or a free wall; a building's outside
#: wall (a roofed room right behind it) gets :data:`STRUCTURE_BONUS`.
BUILDING_BONUS = 600.0
STRUCTURE_BONUS = 300.0
#: A wall shorter than this along cannot carry a buy's mount and chalk.
MIN_LENGTH = 64.0
#: A wall lower than this over its floor cannot show the chalk (66 up).
MIN_HEIGHT = 96.0
#: A solid thinner than this is a rail or a sign, not a wall: the W3 probe
#: looks for brickwork 8 units behind the buy.
MIN_THICKNESS = 8.0
#: Trim along a wall face (a post, a rail) closer than this to it does not
#: crowd the apron.
FLUSH = 8.0
#: Search step along a face.
STEP = 8.0
#: How far either side of a lined face's line a buy counts as on it.
LINED_TOL = 6.0
#: The apron keeps this clear of a room's doorway or window hole.
HOLE_CLEAR = 24.0
#: and this clear of a zombie spawn.
SPAWN_CLEAR = 32.0
#: A solid whose underside is this high over the floor (a roof, a beam) is
#: over a player's head, not in front of the buy.
HEADROOM = 96.0


@dataclass(frozen=True)
class WallFace:
    """One wall face a buy may hang on: the line ``y = line`` (``horizontal``)
    or ``x = line``, from ``a0`` to ``a1`` along it, looking ``sign`` (+1 up
    the axis), standing on ``floor`` and ``top`` high."""

    horizontal: bool
    line: float
    a0: float
    a1: float
    sign: int
    floor: float
    top: float
    #: A roofed room stands right behind the face (a house's outside wall),
    #: or the face is a roofed room's own.
    building: bool
    source: str
    #: The solid the face belongs to, if a block (so it is not its own clash).
    solid: Bounds | None = None

    @property
    def facing(self) -> Facing:
        if self.horizontal:
            return Facing.NORTH if self.sign > 0 else Facing.SOUTH
        return Facing.EAST if self.sign > 0 else Facing.WEST

    def origin(self, along: float) -> Point:
        off = self.line + self.sign * BUY_OFFSET
        x, y = (along, off) if self.horizontal else (off, along)
        return Point(x, y, self.floor - BUY_DROP)


def _floor_of(room) -> float:
    return float(room.floor_z)


def candidate_faces(bp, zone_box: Bounds) -> list[WallFace]:
    """Every wall face whose front lies in *zone_box*: each room's four inside
    faces and the four sides of every tall, thick block (a shed's wall, a
    building's), unlined or not (:func:`find_wall_spot` asks that)."""
    from ..blueprint.elements import Massing, Room

    rooms = list(bp.elements(Room))
    roofed = [r.interior for r in rooms if getattr(r, "roofed", True)]

    def behind_is_building(face_pt: tuple[float, float], horizontal: bool, sign: int) -> bool:
        x, y = face_pt
        for back in (8.0, 24.0, 40.0, 56.0, 72.0):
            px, py = (x, y - sign * back) if horizontal else (x - sign * back, y)
            if any(i.holds_flat(px, py) for i in roofed):
                return True
        return False

    faces: list[WallFace] = []
    for room in rooms:
        i = room.interior
        if not zone_box.overlaps(i):
            continue
        floor, top = _floor_of(room), i.maxs.z
        own = bool(getattr(room, "roofed", True))
        for horizontal, line, a0, a1, sign in ((True, i.maxs.y, i.mins.x, i.maxs.x, -1),
                                               (True, i.mins.y, i.mins.x, i.maxs.x, 1),
                                               (False, i.maxs.x, i.mins.y, i.maxs.y, -1),
                                               (False, i.mins.x, i.mins.y, i.maxs.y, 1)):
            # A long room face may be part building (a house wall in a
            # fence): split it where what stands behind changes.
            cuts = [a0]
            prev = None
            a = a0
            while a <= a1:
                b = own or behind_is_building((a, line) if horizontal else (line, a), horizontal, sign)
                if prev is not None and b != prev:
                    cuts.append(a)
                prev = b
                a += STEP
            cuts.append(a1)
            for s0, s1 in zip(cuts, cuts[1:]):
                if s1 - s0 < MIN_LENGTH:
                    continue
                mid = (s0 + s1) / 2
                b = own or behind_is_building((mid, line) if horizontal else (line, mid), horizontal, sign)
                faces.append(WallFace(horizontal, line, s0, s1, sign, floor, top, b, f"{room.id} wall"))
    floors = [(r.interior, _floor_of(r)) for r in rooms]
    for m in bp.elements(Massing):
        if getattr(m, "walkable", False) or not m.solids:
            continue
        b = m.bounds
        if not zone_box.overlaps(b) or b.maxs.z - b.mins.z < MIN_HEIGHT:
            continue
        floor = next((f for i, f in floors if i.holds_flat(b.centre.x, b.centre.y)), None)
        if floor is None or abs(b.mins.z - floor) > 4.0:
            continue
        sx, sy = b.maxs.x - b.mins.x, b.maxs.y - b.mins.y
        for horizontal, line, a0, a1, sign, thick in (
                (True, b.maxs.y, b.mins.x, b.maxs.x, 1, sy), (True, b.mins.y, b.mins.x, b.maxs.x, -1, sy),
                (False, b.maxs.x, b.mins.y, b.maxs.y, 1, sx), (False, b.mins.x, b.mins.y, b.maxs.y, -1, sx)):
            if a1 - a0 < MIN_LENGTH or thick < MIN_THICKNESS:
                continue
            faces.append(WallFace(horizontal, line, a0, a1, sign, floor, b.maxs.z, False,
                                  m.id or "block", b))
    return faces


def lined_face_at(origin: Point, facing: Facing, lined: Iterable[tuple], tol: float = LINED_TOL):
    """The lined face (an entry of ``bp.lined_faces``) a buy at *origin*
    looking *facing* is chalked on, or ``None``."""
    from ..dressing.lining import lined_face_at as _at

    return _at(origin, facing, lined, tol)


def _bands(lined) -> list[tuple[Bounds, tuple]]:
    out = []
    for f in lined:
        horizontal, face, (s0, s1), sign, floor, top, *rest = f
        depth = rest[0] if rest else 76.0
        n0, n1 = sorted((face - sign * 16.0, face + sign * depth))
        lo, hi = ((s0, n0), (s1, n1)) if horizontal else ((n0, s0), (n1, s1))
        out.append((Bounds.between((lo[0], lo[1], floor), (hi[0], hi[1], top)), f))
    return out


def _opened(bp, f, a0: float, a1: float) -> bool:
    """Is ``a0..a1`` along lined face *f* inside one of ``bp.lined_openings``
    (something solid stands in that band and hides the wall)?"""
    horizontal, face, _span, sign = f[0], f[1], f[2], f[3]
    for h, line, sg, o0, o1, *_ in getattr(bp, "lined_openings", ()) or ():
        if h == horizontal and abs(line - face) < 0.5 and sg == sign and o0 <= a0 and a1 <= o1:
            return True
    return False


def _cut(box: Bounds, other: Bounds) -> Bounds | None:
    lo = Point(max(box.mins.x, other.mins.x), max(box.mins.y, other.mins.y), max(box.mins.z, other.mins.z))
    hi = Point(min(box.maxs.x, other.maxs.x), min(box.maxs.y, other.maxs.y), min(box.maxs.z, other.maxs.z))
    if lo.x >= hi.x or lo.y >= hi.y or lo.z >= hi.z:
        return None
    return Bounds.between(lo, hi)


def find_wall_spot(bp, want: Point, zone_box: Bounds, *, lined: Sequence[tuple] | None = None,
                   avoid: Iterable[Bounds] = (), exclude: Iterable[str] = ()):
    """``(origin, facing, face)`` of the best spot for a wall buy in
    *zone_box*: the suitable unlined wall nearest *want* (a building's wall
    :data:`BUILDING_BONUS` nearer), or ``None``.  *avoid* are boxes the
    buy's keep must stay clear of (what the recipe places later)."""
    from ..blueprint import reach
    from ..blueprint.elements import Massing, Room, Spawn, WallWeapon

    lined = list(getattr(bp, "lined_faces", ()) if lined is None else lined)
    bands = _bands(lined)
    avoid = list(avoid)
    keeps = [k for k in bp.interactive_keeps() if k.element_id not in set(exclude)]
    holes = [Bounds.between(b.mins, b.maxs).grown(HOLE_CLEAR)
             for r in bp.elements(Room) for b in (getattr(r, "aperture_boxes", ()) or ())]
    spawns = [s.position for s in bp.elements(Spawn)]
    solids = []
    for m in bp.elements(Massing):
        if m.solids:
            b = m.bounds
            if zone_box.grown(200.0).overlaps(b):
                solids.append(b)
    rooms = [r.interior for r in bp.elements(Room)]
    best = None
    for face in candidate_faces(bp, zone_box):
        facing = face.facing
        a = face.a0 + 32.0
        while a <= face.a1 - 32.0:
            along = a
            origin = face.origin(a)
            a += STEP
            score = math.hypot(origin.x - want.x, origin.y - want.y) - BUILDING_BONUS
            if best is not None and score >= best[0]:
                continue
            if not zone_box.holds_flat(origin.x, origin.y) or lined_face_at(origin, facing, lined) is not None:
                continue
            probe = WallWeapon(id="probe", slug="pistol_burst", position=origin, facing=facing)
            keep = reach.keep_of(probe)
            apron = keep.aprons[0]
            if face.top < origin.z + reach.CHALK_HIGH + 16.0:
                continue
            # The floor in front stays in one room, inside its walls.
            corners = ((apron.mins.x, apron.mins.y), (apron.maxs.x, apron.maxs.y),
                       (apron.mins.x, apron.maxs.y), (apron.maxs.x, apron.mins.y))
            if not any(all(r.holds_flat(cx, cy, 1.0) for cx, cy in corners) for r in rooms):
                continue
            if any(reach._pair_clash(keep, k) is not None for k in keeps):
                continue
            if any(apron.overlaps(h) for h in holes) or any(apron.overlaps(b) for b in avoid):
                continue
            if any(apron.grown(SPAWN_CLEAR).holds_flat(p.x, p.y) for p in spawns):
                continue
            # No other solid in front of the wall: posts and rails flush on
            # the face are trim, anything further out is in the way.
            stand = keep.stands[0] if getattr(keep, "stands", ()) else apron
            if face.building and face.solid is None and _room_roofed(bp, origin):
                tier = BUILDING_BONUS
            elif any(s.mins.z >= origin.z + BUY_DROP + HEADROOM - 24.0 and s.mins.x <= stand.centre.x <= s.maxs.x
                     and s.mins.y <= stand.centre.y <= s.maxs.y for s in solids):
                tier = BUILDING_BONUS  # a roof over the floor in front of it
            elif face.building:
                tier = STRUCTURE_BONUS
            else:
                tier = 0.0
            score += BUILDING_BONUS - tier
            if face.solid is not None:
                # A buy on a shed's or a block's wall hangs in its middle.
                score += abs(along - (face.a0 + face.a1) / 2.0)
            if best is not None and score >= best[0]:
                continue
            front = Bounds.between(*_front_of(face, apron))
            floor = origin.z + BUY_DROP
            if any(s is not face.solid and s.mins.z < floor + HEADROOM and _cut(front, s) is not None
                   and _cut(front, s).maxs.z > floor + 24.0 for s in solids):
                continue
            # No lined band reaches into the apron (the corn beside a buy
            # would be cleared for it), unless something standing in that
            # band already hides the wall there (bp.lined_openings).
            clash = False
            for band, f in bands:
                cut = _cut(apron, band)
                if cut is None:
                    continue
                t0, t1 = (cut.mins.x, cut.maxs.x) if f[0] else (cut.mins.y, cut.maxs.y)
                if not _opened(bp, f, t0, t1):
                    clash = True
                    break
            if clash:
                continue
            best = (score, origin, facing, face)
    return None if best is None else best[1:]


def _room_roofed(bp, origin: Point) -> bool:
    from ..blueprint.elements import Room

    return any(getattr(r, "roofed", True) and r.interior.holds_flat(origin.x, origin.y)
               for r in bp.elements(Room))


def _front_of(face: WallFace, apron: Bounds) -> tuple[Point, Point]:
    """The apron less the :data:`FLUSH` strip against the wall."""
    lo, hi = apron.mins, apron.maxs
    if face.horizontal:
        if face.sign > 0:
            lo = Point(lo.x, max(lo.y, face.line + FLUSH), lo.z)
        else:
            hi = Point(hi.x, min(hi.y, face.line - FLUSH), hi.z)
    else:
        if face.sign > 0:
            lo = Point(max(lo.x, face.line + FLUSH), lo.y, lo.z)
        else:
            hi = Point(min(hi.x, face.line - FLUSH), hi.y, hi.z)
    return lo, hi


def place_wall_buy(bp, kind: str, want: Point, facing: Facing | str, *, zone_box: Bounds,
                   id: str, avoid: Iterable[Bounds] = (), **kwargs):
    """Place wall buy *kind* at *want* looking *facing*, unless that is on a
    lined face (``bp.lined_faces``, the recipe's planned lining): then on the
    nearest suitable unlined wall in *zone_box* (:func:`find_wall_spot`).
    Each move is recorded on ``bp.moved_wall_buys`` as ``(id, old, new,
    wall)``.  Raises :class:`~zmforge.errors.BlueprintError` when the zone has
    no such wall: give it one (:func:`buy_shed`)."""
    from ..errors import BlueprintError

    facing = Facing.of(facing)
    lined = list(getattr(bp, "lined_faces", ()) or ())
    if lined_face_at(want, facing, lined) is None:
        return bp.place_wall_weapon(kind, want, facing, id=id, **kwargs)
    spot = find_wall_spot(bp, want, zone_box, lined=lined, avoid=avoid)
    if spot is None:
        raise BlueprintError(
            f"{id}: asked for a lined face at ({want.x:.0f}, {want.y:.0f}) and the zone has no unlined "
            "wall a buy fits on; give it a structure (placement.wallbuy.buy_shed)")
    origin, new_facing, face = spot
    moved = getattr(bp, "moved_wall_buys", None)
    if moved is None:
        moved = bp.moved_wall_buys = []
    moved.append((id, (round(want.x), round(want.y), facing.value),
                  (round(origin.x), round(origin.y), new_facing.value), face.source))
    return bp.place_wall_weapon(kind, origin, new_facing, id=id, **kwargs)


#: The shed :func:`buy_shed` builds: wall thickness, height at the back, at
#: the front (a lean-to roof drops to the front) and roof overhang.
SHED_WALL = 10.0
SHED_BACK_H = 168.0
SHED_FRONT_H = 132.0
SHED_ROOF = 4.0


def buy_shed(bp, back: Point, facing: Facing | str, *, width: float = 176.0, depth: float = 120.0,
             material, ident: str, roof_material=None) -> Bounds:
    """An open-fronted plank shed whose back wall's outer face stands on the
    line through *back* (at its floor, ``back.z``), its open front looking
    *facing*: a back wall, two side walls *depth* deep and a lean-to roof in
    steps.  Returns its footprint.  A wall buy goes on the back wall's inside
    face (:func:`place_wall_buy` finds it: its blocks are noted "shed")."""
    facing = Facing.of(facing)
    box = _shed_box(back, facing)
    half = width / 2.0
    z = back.z
    t = SHED_WALL
    bp.add_block(box(-half, half, 0.0, t, z, z + SHED_BACK_H), material, reachable=False,
                 id=f"{ident}_back", note="shed wall")
    # The roof: three planks stepping down from the back wall to the front,
    # overhanging the sides and the front, each resting on the stretch of
    # side wall under it (the side walls step down with it: Z43, nothing
    # hangs in the air).
    rise = SHED_BACK_H - SHED_FRONT_H
    for k in range(3):
        o0, o1 = (depth + 12.0) * k / 3.0, (depth + 12.0) * (k + 1) / 3.0
        top = z + SHED_BACK_H - rise * k / 2.0
        for n, a in enumerate((-half, half - t)):
            w0, w1 = max(t, o0), min(depth, o1)
            if w1 > w0:
                bp.add_block(box(a, a + t, w0, w1, z, top), material, reachable=False,
                             id=f"{ident}_side_{n}_{k}", note="shed wall")
        bp.add_block(box(-half - 8.0, half + 8.0, o0, o1, top, top + SHED_ROOF), roof_material or material,
                     reachable=False, id=f"{ident}_roof_{k}", note="shed roof")
    return shed_footprint(back, facing, width, depth)


def _shed_box(back: Point, facing: Facing):
    """``box(along0, along1, out0, out1, z0, z1)``: a box off the line
    through *back*, *out* the way *facing* looks, *along* across it."""
    step = facing.step

    def box(along0: float, along1: float, out0: float, out1: float, z0: float, z1: float) -> Bounds:
        if step.x:
            xs = sorted((back.x + step.x * out0, back.x + step.x * out1))
            return Bounds.between((xs[0], back.y + along0, z0), (xs[1], back.y + along1, z1))
        ys = sorted((back.y + step.y * out0, back.y + step.y * out1))
        return Bounds.between((back.x + along0, ys[0], z0), (back.x + along1, ys[1], z1))

    return box


def shed_footprint(back: Point, facing: Facing | str, width: float = 176.0, depth: float = 120.0) -> Bounds:
    """The box :func:`buy_shed` fills with these arguments, roof included."""
    half = width / 2.0
    return _shed_box(back, Facing.of(facing))(-half - 8.0, half + 8.0, 0.0, depth + 12.0, back.z,
                                              back.z + SHED_BACK_H + SHED_ROOF)
