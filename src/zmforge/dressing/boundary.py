"""Boundary walls and what shows over them, on an open-air map.

The cemetery's hero render showed tall, flat, uniform brick perimeter walls
with no cap, pier or plinth, nothing above them and a black sky.  Two shared
pieces fix that on any open-air map:

* :func:`boundary_wall` dresses one wall of an open room: a plinth along its
  foot, piers at an irregular rhythm rising over a coping, raised (stepped)
  panels, iron railing panels on the coping, and props gathered at the foot.
  It keeps off openings and any keep-out circles given.
* :func:`backdrop` stands silhouettes beyond a wall, above its top: a line of
  trees, a church spire and rooftops.  The trees are models
  (:mod:`.trees`; brush silhouettes read as blocky stand-ins and stay only
  as the ``models=()`` fallback); the spire and rooftops are
  brushes, ``reachable=False``.  The map's sky shell grows round both on its
  own (:meth:`zmforge.blueprint.model.Blueprint.playable_bounds` counts
  every model's box: a model outside the shell leaks the map).

Both want a wall a player can see over: build the room with
``add_room(..., wall_height=...)``.  ``Z62`` warns on a long wall run left
bare, ``Z63`` on an open room whose walls hide the sky or show nothing over
them (:mod:`zmforge.verify.boundary`).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

from ..spatial import Point, Side, Span

__all__ = [
    "WallStyle",
    "wall_faces",
    "open_spans",
    "boundary_wall",
    "backdrop",
]

#: How deep a wall's foot items and piers are buried under uneven ground.
_BURY = 16.0
#: The backdrop stands beyond the walls where there is no floor: scenery out
#: of reach, floating on purpose (``Z43`` skips it).
from ..blueprint.elements import FLOATS_ON_PURPOSE as _SCENERY  # noqa: E402


@dataclass(frozen=True)
class WallStyle:
    """How a boundary wall is dressed.  Materials are ``Material`` objects."""

    pier: object
    coping: object
    plinth: object
    rail: object
    #: Mean panel length between piers; each panel varies by +-``jitter``.
    pier_every: float = 208.0
    jitter: float = 40.0
    pier_width: float = 28.0
    pier_proud: float = 10.0
    #: How far a pier rises over the coping, and its cap.
    pier_rise: float = 22.0
    coping_height: float = 8.0
    coping_overhang: float = 4.0
    plinth_height: float = 14.0
    plinth_proud: float = 6.0
    #: Every n-th panel carries a raised parapet step, every m-th an iron
    #: railing on its coping (never both).
    raised_every: int = 3
    raised_height: float = 28.0
    railing_every: int = 4
    railing_height: float = 34.0
    #: Models gathered at the wall's foot, and how many per panel (0..n).
    foot_models: tuple[str, ...] = ()
    foot_per_panel: int = 3


@dataclass(frozen=True)
class WallFace:
    """One wall of a room, seen from inside."""

    side: Side
    #: The inner face's coordinate (y for north/south, x for east/west).
    face: float
    #: The outer face's coordinate.
    back: float
    #: The run along the wall (x for north/south, y for east/west).
    a0: float
    a1: float
    top: float
    #: +1 or -1: the direction from the face into the room, on its axis.
    inward: float

    @property
    def along_x(self) -> bool:
        return self.side in (Side.NORTH, Side.SOUTH)

    def point(self, along: float, out: float) -> tuple[float, float]:
        """(x, y) *along* the wall and *out* from its inner face into the room."""
        c = self.face + self.inward * out
        return (along, c) if self.along_x else (c, along)

    def box(self, a0: float, a1: float, o0: float, o1: float, z0: float, z1: float) -> Span:
        """A box from *a0* to *a1* along the wall, *o0* to *o1* out from its
        inner face (negative = into the wall and beyond)."""
        c0, c1 = sorted((self.face + self.inward * o0, self.face + self.inward * o1))
        if self.along_x:
            return Span.between(Point(a0, c0, z0), Point(a1, c1, z1))
        return Span.between(Point(c0, a0, z0), Point(c1, a1, z1))


def wall_faces(room) -> dict[Side, WallFace]:
    """The four walls of *room* from its shell pieces (not the aperture pieces)."""
    inside = room.interior
    faces: dict[Side, WallFace] = {}
    for piece in room.shell.pieces:
        if piece.side in (Side.BOTTOM, Side.TOP) or piece.aperture:
            continue
        b = piece.box
        side = piece.side
        if side in faces:
            faces[side] = WallFace(side, faces[side].face, faces[side].back, faces[side].a0,
                                   faces[side].a1, max(faces[side].top, b.maxs.z),
                                   faces[side].inward)
            continue
        if side is Side.NORTH:
            f = WallFace(side, b.mins.y, b.maxs.y, inside.mins.x, inside.maxs.x, b.maxs.z, -1.0)
        elif side is Side.SOUTH:
            f = WallFace(side, b.maxs.y, b.mins.y, inside.mins.x, inside.maxs.x, b.maxs.z, 1.0)
        elif side is Side.EAST:
            f = WallFace(side, b.mins.x, b.maxs.x, inside.mins.y, inside.maxs.y, b.maxs.z, -1.0)
        else:
            f = WallFace(side, b.maxs.x, b.mins.x, inside.mins.y, inside.maxs.y, b.maxs.z, 1.0)
        faces[side] = f
    return faces


def _cuts(face: WallFace, room, keep: Sequence[tuple[float, float, float]], margin: float):
    """Intervals along *face* to leave bare: its openings and keep-out circles
    that reach within *margin* of the face."""
    cuts: list[tuple[float, float]] = []
    for box in room.aperture_boxes:
        lo = box.mins.x if face.along_x else box.mins.y
        hi = box.maxs.x if face.along_x else box.maxs.y
        near = (box.mins.y - 1 <= face.face <= box.maxs.y + 1) if face.along_x else \
            (box.mins.x - 1 <= face.face <= box.maxs.x + 1)
        if near:
            cuts.append((lo - 20.0, hi + 20.0))
    for x, y, r in keep:
        across = abs((y if face.along_x else x) - face.face)
        if across > r + margin:
            continue
        a = x if face.along_x else y
        cuts.append((a - r, a + r))
    return sorted(cuts)


def open_spans(lo: float, hi: float, cuts: Sequence[tuple[float, float]],
               least: float = 48.0) -> list[tuple[float, float]]:
    """``lo..hi`` less every cut, keeping pieces at least *least* long."""
    spans = []
    at = lo
    for c0, c1 in sorted(cuts):
        if c1 <= at or c0 >= hi:
            continue
        if c0 - at >= least:
            spans.append((at, c0))
        at = max(at, c1)
    if hi - at >= least:
        spans.append((at, hi))
    return spans


def boundary_wall(bp, room, side: Side, style: WallStyle, *, ground_at: Callable[[float, float], float],
                  seed: str, keep: Sequence[tuple[float, float, float]] = (),
                  ident: str | None = None) -> tuple[list, list[tuple[float, float, float, float]]]:
    """Dress one wall of an open room (see the module docstring).

    Returns ``(props, footprints)``: the foot props as ``PropSpec`` tuples for
    ``bp.place_props`` and the plan rectangles ``(x0, y0, x1, y1)`` the
    dressing took, for a placer that must keep off them.  Brushes are added
    to *bp*.  Everything is seeded by *seed*.
    """
    from .place import on_floor, turned_box

    rng = random.Random(f"{seed}:{room.id}:{side.name}")
    face = wall_faces(room)[side]
    ident = ident or f"{room.id}_bwall_{side.name.lower()}"
    cuts = _cuts(face, room, keep, style.plinth_proud + style.pier_proud + 24.0)
    top = face.top
    thick = abs(face.back - face.face)
    props: list = []
    taken: list[tuple[float, float, float, float]] = []

    def block(box: Span, material, tag: str) -> None:
        bp.add_block(box, material, reachable=False, id=f"{ident}_{tag}",
                     note="boundary wall dressing (dressing.boundary_wall)")

    def ground_along(a0: float, a1: float, out: float) -> tuple[float, float]:
        zs = [ground_at(*face.point(a, out)) for a in (a0, (a0 + a1) / 2.0, a1)]
        return min(zs), max(zs)

    # The coping runs the whole wall, openings or not: it caps the masonry.
    ov = style.coping_overhang
    block(face.box(face.a0 - ov, face.a1 + ov, ov, -(thick + ov), top, top + style.coping_height),
          style.coping, "coping")
    cap = top + style.coping_height
    n_piece = 0
    panel = 0
    for s0, s1 in open_spans(face.a0, face.a1, cuts):
        # Panels between piers, each a slightly different length.
        edges = [s0]
        while edges[-1] < s1:
            step = style.pier_every + rng.uniform(-style.jitter, style.jitter)
            nxt = edges[-1] + step
            if s1 - nxt < style.pier_every * 0.5:
                nxt = s1
            edges.append(min(nxt, s1))
        n_piece += 1
        # The plinth, per panel so it follows the ground.
        for p0, p1 in zip(edges, edges[1:]):
            lo, hi = ground_along(p0, p1, style.plinth_proud)
            block(face.box(p0, p1, 0.0, style.plinth_proud, lo - _BURY, hi + style.plinth_height),
                  style.plinth, f"plinth{n_piece}_{panel}")
            x0, y0 = face.point(p0, 0.0)
            x1, y1 = face.point(p1, style.plinth_proud + 2.0)
            taken.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
            kind = ""
            if style.railing_every and panel % style.railing_every == style.railing_every - 1:
                kind = "railing"
            elif style.raised_every and panel % style.raised_every == 1:
                kind = "raised"
            if kind == "raised":
                block(face.box(p0 + style.pier_width / 2, p1 - style.pier_width / 2, 0.0, -thick,
                               cap, cap + style.raised_height), style.pier, f"raised{panel}")
                block(face.box(p0 + style.pier_width / 2 - 2, p1 - style.pier_width / 2 + 2,
                               2.0, -(thick + 2.0), cap + style.raised_height,
                               cap + style.raised_height + 4.0), style.coping, f"raisedcap{panel}")
            elif kind == "railing":
                a = p0 + style.pier_width / 2 + 6.0
                n = 0
                mid = -thick / 2.0
                while a < p1 - style.pier_width / 2 - 4.0:
                    block(face.box(a - 1.0, a + 1.0, mid + 1.0, mid - 1.0, cap,
                                   cap + style.railing_height), style.rail, f"rail{panel}_{n}")
                    block(face.box(a - 0.6, a + 0.6, mid + 0.6, mid - 0.6,
                                   cap + style.railing_height, cap + style.railing_height + 5.0),
                          style.rail, f"spear{panel}_{n}")
                    a += 9.0
                    n += 1
                for k, z in enumerate((cap + 4.0, cap + style.railing_height - 6.0)):
                    block(face.box(p0 + style.pier_width / 2, p1 - style.pier_width / 2,
                                   mid + 1.2, mid - 1.2, z, z + 2.0), style.rail, f"railbar{panel}_{k}")
            # Props at the foot: gathered in a drift near one end of the panel.
            if style.foot_models:
                n = rng.randint(0, style.foot_per_panel)
                end = p0 + style.pier_width if rng.random() < 0.5 else p1 - style.pier_width
                for k in range(n):
                    model = rng.choice(style.foot_models)
                    yaw = rng.uniform(0, 360)
                    # Clear of the plinth and of the room's corners (Z54).
                    bx0, by0, bx1, by1 = turned_box(model, yaw)
                    half_a = ((bx1 - bx0) if face.along_x else (by1 - by0)) / 2.0
                    half_o = ((by1 - by0) if face.along_x else (bx1 - bx0)) / 2.0
                    a = end + rng.uniform(-30.0, 30.0)
                    if not (max(p0, face.a0 + half_a + 4.0) < a < min(p1, face.a1 - half_a - 4.0)):
                        continue
                    x, y = face.point(a, style.plinth_proud + half_o + rng.uniform(2.0, 14.0))
                    props.append(on_floor(model, x, y, ground_at(x, y), yaw, solid=False))
            panel += 1
        # Piers at every panel edge, the ends included (they frame openings).
        for k, a in enumerate(edges):
            half = style.pier_width / 2.0
            # The end piers stand inside the span, framing the cut beside it.
            if k == 0:
                a += half
            elif k == len(edges) - 1:
                a -= half
            lo, _hi = ground_along(a - half, a + half, style.pier_proud)
            block(face.box(a - half, a + half, style.pier_proud, -thick, lo - _BURY,
                           cap + style.pier_rise), style.pier, f"pier{n_piece}_{k}")
            block(face.box(a - half - 3, a + half + 3, style.pier_proud + 3, -(thick + 3),
                           cap + style.pier_rise, cap + style.pier_rise + 5.0), style.coping,
                  f"piercap{n_piece}_{k}")
            if rng.random() < 0.5:
                block(face.box(a - 5, a + 5, style.pier_proud / 2 + 5, style.pier_proud / 2 - 5 - thick / 2,
                               cap + style.pier_rise + 5.0, cap + style.pier_rise + 15.0),
                      style.coping, f"finial{n_piece}_{k}")
            x0, y0 = face.point(a - half, 0.0)
            x1, y1 = face.point(a + half, style.pier_proud + 2.0)
            taken.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    return props, taken


#: How far along a wall the backdrop keeps from a neighbouring room, so no
#: branch reaches into it (a branch reaches up to 130).
_CLEAR = 200.0


def _outside_spans(bp, room, face: WallFace) -> list[tuple[float, float]]:
    """Where along *face* nothing but open air lies behind the wall (no other
    room's box within 64 units of its back)."""
    from ..blueprint.elements import Room

    cuts = []
    for other in bp.elements(Room):
        if other is room:
            continue
        o = other.outer
        if face.along_x:
            if face.inward < 0 and not (o.mins.y <= face.back + 64.0 and o.maxs.y >= face.back):
                continue
            if face.inward > 0 and not (o.maxs.y >= face.back - 64.0 and o.mins.y <= face.back):
                continue
            cuts.append((o.mins.x - _CLEAR, o.maxs.x + _CLEAR))
        else:
            if face.inward < 0 and not (o.mins.x <= face.back + 64.0 and o.maxs.x >= face.back):
                continue
            if face.inward > 0 and not (o.maxs.x >= face.back - 64.0 and o.mins.x <= face.back):
                continue
            cuts.append((o.mins.y - _CLEAR, o.maxs.y + _CLEAR))
    return open_spans(face.a0 - 16.0, face.a1 + 16.0, cuts, least=160.0)


def _tree(bp, ident: str, x: float, y: float, z: float, height: float, rng, material) -> None:
    """A bare tree: a leaning trunk and five to seven raking branches."""
    from .fixtures import sheared_bar

    lean_x, lean_y = rng.uniform(-18, 18), rng.uniform(-18, 18)
    tx, ty, tz = x + lean_x, y + lean_y, z + height
    sheared_bar(bp, f"{ident}_trunk", (x, y, z - _BURY), (tx, ty, tz), rng.uniform(7.0, 11.0),
                material, note=_SCENERY)
    for k in range(rng.randint(7, 10)):
        t = rng.uniform(0.35, 0.95)
        bx, by, bz = x + lean_x * t, y + lean_y * t, z + height * t
        ang = rng.uniform(0, 2 * math.pi)
        reach = rng.uniform(50, 130) * (1.1 - t * 0.5)
        ex, ey = bx + math.cos(ang) * reach, by + math.sin(ang) * reach
        ez = bz + rng.uniform(30, 90)
        sheared_bar(bp, f"{ident}_branch{k}", (bx, by, bz), (ex, ey, ez), rng.uniform(2.0, 4.0),
                    material, note=_SCENERY)


def _spire(bp, ident: str, x: float, y: float, z: float, height: float, material) -> None:
    """A church tower: a square shaft, a belfry, and a needle spire."""
    from .fixtures import sheared_bar

    tower = height * 0.55
    bp.add_block(Span.between(Point(x - 60, y - 60, z - _BURY), Point(x + 60, y + 60, z + tower)),
                 material, reachable=False, id=f"{ident}_tower", note=_SCENERY)
    bp.add_block(Span.between(Point(x - 66, y - 66, z + tower), Point(x + 66, y + 66, z + tower + 10)),
                 material, reachable=False, id=f"{ident}_ledge", note=_SCENERY)
    bp.add_block(Span.between(Point(x - 46, y - 46, z + tower + 10), Point(x + 46, y + 46, z + tower + 70)),
                 material, reachable=False, id=f"{ident}_belfry", note=_SCENERY)
    apex = (x, y, z + height)
    for k, (cx, cy) in enumerate(((-40, -40), (40, -40), (40, 40), (-40, 40))):
        sheared_bar(bp, f"{ident}_rib{k}", (x + cx, y + cy, z + tower + 70), apex, 10.0, material,
                    note=_SCENERY)
    bp.add_block(Span.between(Point(x - 22, y - 22, z + tower + 70), Point(x + 22, y + 22, z + height * 0.88)),
                 material, reachable=False, id=f"{ident}_core", note=_SCENERY)
    bp.add_block(Span.between(Point(x - 1.5, y - 1.5, z + height * 0.88), Point(x + 1.5, y + 1.5, z + height + 40)),
                 material, reachable=False, id=f"{ident}_cross", note=_SCENERY)
    bp.add_block(Span.between(Point(x - 12, y - 1.5, z + height + 24), Point(x + 12, y + 1.5, z + height + 28)),
                 material, reachable=False, id=f"{ident}_crossbar", note=_SCENERY)


def _house(bp, ident: str, face: WallFace, a: float, dist: float, z: float, rng, material) -> None:
    """A gabled rooftop with a chimney, its ridge running along the wall."""
    from .fixtures import sheared_bar

    w = rng.uniform(140, 220)
    d = rng.uniform(110, 160)
    eave = rng.uniform(150, 230)
    ridge = eave + rng.uniform(70, 110)
    a0, a1 = a - w / 2, a + w / 2
    bp.add_block(face.box(a0, a1, -dist, -(dist + d), z - _BURY, z + eave), material,
                 reachable=False, id=f"{ident}_body", note=_SCENERY)
    mid = -(dist + d / 2)
    for k, edge in enumerate((-dist, -(dist + d))):
        for j, aa in enumerate((a0 + 6, a1 - 6)):
            lo = face.point(aa, edge)
            hi = face.point(aa, mid)
            sheared_bar(bp, f"{ident}_rafter{k}{j}", (lo[0], lo[1], z + eave), (hi[0], hi[1], z + ridge),
                        6.0, material, note=_SCENERY)
    bp.add_block(face.box(a0 + 6, a1 - 6, mid + 10, mid - 10, z + eave, z + ridge - 4), material,
                 reachable=False, id=f"{ident}_gable", note=_SCENERY)
    ca = a0 + w * rng.uniform(0.2, 0.8)
    bp.add_block(face.box(ca - 10, ca + 10, mid + 20, mid - 4, z + eave, z + ridge + 40), material,
                 reachable=False, id=f"{ident}_chimney", note=_SCENERY)


def _cypress(bp, ident: str, x: float, y: float, z: float, height: float, rng, material) -> None:
    """A graveyard cypress or yew: a narrow dark column tapering to a point."""
    from .fixtures import sheared_bar

    w = rng.uniform(22.0, 34.0)
    sheared_bar(bp, f"{ident}_trunk", (x, y, z - _BURY), (x, y, z + 40.0), 5.0, material, note=_SCENERY)
    tiers = 4
    lean = rng.uniform(-10, 10), rng.uniform(-10, 10)
    for k in range(tiers):
        z0 = z + 30.0 + (height - 30.0) * k / tiers
        z1 = z + 30.0 + (height - 30.0) * (k + 1) / tiers + 12.0
        half = w * (1.0 - 0.55 * k / tiers) * rng.uniform(0.9, 1.1)
        t0, t1 = k / tiers, (k + 1) / tiers
        sheared_bar(bp, f"{ident}_crown{k}", (x + lean[0] * t0, y + lean[1] * t0, z0),
                    (x + lean[0] * t1, y + lean[1] * t1, z1), half, material, note=_SCENERY)
    sheared_bar(bp, f"{ident}_tip", (x + lean[0], y + lean[1], z + height),
                (x + lean[0] * 1.1, y + lean[1] * 1.1, z + height + 40.0), w * 0.2, material,
                note=_SCENERY)


def _pine(bp, ident: str, x: float, y: float, z: float, height: float, rng, material) -> None:
    """A dead pine: a straight trunk with short, drooping branches in tiers."""
    import math as _m

    from .fixtures import sheared_bar

    sheared_bar(bp, f"{ident}_trunk", (x, y, z - _BURY), (x, y, z + height), rng.uniform(5.0, 8.0),
                material, note=_SCENERY)
    for k in range(rng.randint(5, 8)):
        t = 0.35 + 0.6 * k / 8.0
        bz = z + height * t
        ang = rng.uniform(0, 2 * _m.pi)
        reach = (1.0 - t) * rng.uniform(70, 120) + 20
        ex, ey = x + _m.cos(ang) * reach, y + _m.sin(ang) * reach
        sheared_bar(bp, f"{ident}_limb{k}", (ex, ey, bz - rng.uniform(4, 14)), (x, y, bz + 2),
                    rng.uniform(1.8, 3.0), material, note=_SCENERY)


#: The silhouette kinds per depth row: near rows mix bare trees and
#: cypresses, far rows are taller pines and bare trees: depth and
#: variety, not a flat row.
_ROW_KINDS = ((_tree, _tree, _cypress), (_cypress, _pine, _tree), (_pine, _tree, _pine))


def backdrop(bp, room, sides: Sequence[Side], material, *, seed: str,
             band: tuple[float, float] = (80.0, 420.0), tree_every: float = 150.0,
             spire: Side | None = None, houses: int = 2, rows: int = 3,
             far_material=None, models: Sequence[Sequence[str]] | None = None) -> int:
    """Silhouettes beyond the named walls of an open room, rising over them.

    Along each side's stretches with open air behind (no other room there),
    *rows* staggered lines of trees at growing depth: bare trees and
    cypresses near, taller pines and bare trees behind them (each row's
    band starts where the last one ended, and each is taller and sparser),
    in *material* near and *far_material* (default the same) behind.  One
    church spire behind the *spire* side, and *houses* rooftops per side.
    Returns how many silhouettes were stood.

    The trees are models by default: *models* names the choices per depth
    row (default :data:`.trees.TREELINE`: generated dead trees near, mixed
    with leafy albizias behind), each at a random yaw and scaled to its
    height.  Pass ``models=()`` for the old brush silhouettes (bare trees,
    cypresses, pines), kept only as a fallback.  The spire and rooftops are
    brushes either way, all ``reachable=False``.
    """
    from .trees import TREELINE, as_prop, model_reach, pick, tree

    if models is None:
        models = TREELINE
    specs: list = []
    last: str | None = None
    from ..blueprint.elements import Room

    rng = random.Random(f"{seed}:{room.id}:backdrop")
    faces = wall_faces(room)
    base = room.outer.mins.z + 16.0
    count = 0
    width = band[1] - band[0]
    boxes = [r.outer for r in bp.elements(Room) if r is not room]

    def clear(x: float, y: float, m: float = 140.0) -> bool:
        return not any(b.mins.x - m < x < b.maxs.x + m and b.mins.y - m < y < b.maxs.y + m
                       for b in boxes)
    doors = list(getattr(room, "aperture_boxes", ()) or ())

    def near_door(x: float, y: float, m: float) -> bool:
        # A crown over a doorway (or the 48 units either side, Z53) is in it.
        return any(b.mins.x - m < x < b.maxs.x + m and b.mins.y - m < y < b.maxs.y + m
                   for b in doors)
    for side in sides:
        face = faces[side]
        spans = _outside_spans(bp, room, face)
        tag = side.name.lower()
        for s0, s1 in spans:
            for r in range(max(1, rows)):
                lo_d = band[0] + r * width * 0.8
                every = tree_every * (1.0 + 0.35 * r)
                mat = material if r == 0 or far_material is None else far_material
                at = s0 + rng.uniform(20, 80) + r * every * 0.5
                n = 0
                while at < s1 - 20:
                    dist = rng.uniform(lo_d, lo_d + width)
                    x, y = face.point(at, -(abs(face.back - face.face) + dist))
                    h = (face.top - base) + rng.uniform(180, 420) * (1.0 + 0.3 * r)
                    if models:
                        model = pick(models[min(r, len(models) - 1)], rng, last)
                        spec = tree(model, x, y, base, height=h, rng=rng)
                        at += every * rng.uniform(0.6, 1.4)
                        reach = max(140.0, model_reach(model, spec[3]))
                        if not clear(x, y, reach) or near_door(x, y, reach + 48.0):
                            continue
                        specs.append(spec)
                        last = model
                        n += 1
                        count += 1
                        continue
                    kind = rng.choice(_ROW_KINDS[min(r, len(_ROW_KINDS) - 1)])
                    if kind is _cypress:
                        h *= 0.75
                    at += every * rng.uniform(0.6, 1.4)
                    if not clear(x, y):
                        continue
                    kind(bp, f"{room.id}_bd_{tag}_r{r}_tree{int(s0)}_{n}", x, y, base, h, rng, mat)
                    n += 1
                    count += 1
            for k in range(houses if s1 - s0 > 600 else 0):
                a = s0 + (s1 - s0) * (k + 1) / (houses + 1) + rng.uniform(-80, 80)
                _house(bp, f"{room.id}_bd_{tag}_house{int(s0)}_{k}", face, a,
                       abs(face.back - face.face) + band[0] + 60, base, rng, material)
                count += 1
        if side is spire and spans:
            s0, s1 = max(spans, key=lambda s: s[1] - s[0])
            a = s0 + (s1 - s0) * rng.uniform(0.3, 0.7)
            x, y = face.point(a, -(abs(face.back - face.face) + band[1] + 120))
            _spire(bp, f"{room.id}_bd_spire", x, y, base, (face.top - base) + 620, material)
            count += 1
    if specs:
        bp.place_props([as_prop(s) for s in specs], id=f"{room.id}_backdrop_trees")
    return count
