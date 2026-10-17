"""Facades: the outside of a roofed room where a player can see it.

An open-air room's walls stop low (``add_room(wall_height=...)``),
so a roofed room beside it (a shed, a chapel, a vault) shows its
outer wall over them.  Left bare, that wall is a huge blank slab.
:func:`facade` dresses
every outer face of a roofed room that rises over its neighbours: a weathered
skin in mixed stone, a cornice and eaves, a string course, buttresses at an
uneven rhythm, windows with sills, jambs and dark panes, soot or damp bands,
and a roof over the flat ceiling (a pitched gable with crow-stepped ends, or
a crenellated parapet with pediments).  :func:`exposed_faces` says which faces
show and from what height.

Everything is brushes, outside the play space, ``reachable=False``.  Nothing
is placed on the room's inner side, so gameplay does not change.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from ..spatial import Point, Side, Span
from .boundary import WallFace, wall_faces
from .fixtures import sheared_bar

__all__ = ["FacadeStyle", "ExposedFace", "exposed_faces", "facade"]

_NOTE = "facade (dressing.facade)"
_OPPOSITE = {Side.NORTH: Side.SOUTH, Side.SOUTH: Side.NORTH, Side.EAST: Side.WEST,
             Side.WEST: Side.EAST}


@dataclass(frozen=True)
class FacadeStyle:
    """How a facade is built.  Materials are ``Material`` objects; ``skins``
    are laid in bands so no face is one material top to bottom."""

    skins: Sequence[object]
    trim: object
    dark: object
    roof: object
    #: ``"gable"`` (two pitched planes, crow-stepped ends), ``"parapet"``
    #: (crenellated, a stepped pediment per face) or ``None``.
    roof_kind: str | None = "gable"
    #: The gable's ridge runs along x (``"x"``) or y (``"y"``).
    ridge: str = "x"
    pitch: float = 0.7      # rise per unit run of the roof planes
    buttress_every: float = 170.0
    jitter: float = 45.0
    #: ``"lancet"`` (pointed, stepped head), ``"square"`` or ``None``.
    window: str | None = "lancet"
    window_width: float = 40.0
    #: Weathering band under the cornice: soot (dark) or none.
    soot: bool = True


@dataclass(frozen=True)
class ExposedFace:
    """One outer face of a roofed room that shows: ``base`` is the height it
    shows from (a neighbour's wall top, or the room's floor)."""

    side: Side
    face: WallFace
    base: float
    #: The open room whose low wall it rises over (``None``: it stands free
    #: or over a roofed room), i.e. where players see it from.
    seen_from: str | None = None


def _outward(face: WallFace) -> float:
    return -face.inward


def exposed_faces(bp, room, *, least: float = 48.0) -> list[ExposedFace]:
    """Every outer face of *room* that rises at least *least* units over
    whatever stands against it (another room's wall top), or stands free."""
    from ..blueprint.elements import Room

    out: list[ExposedFace] = []
    for side, face in wall_faces(room).items():
        base = room.outer.mins.z
        seen = None
        for other in bp.elements(Room):
            if other is room:
                continue
            o = other.outer
            if face.along_x:
                touch = (o.mins.y - 64.0 <= face.back <= o.maxs.y + 64.0
                         and o.mins.x < face.a1 and o.maxs.x > face.a0)
            else:
                touch = (o.mins.x - 64.0 <= face.back <= o.maxs.x + 64.0
                         and o.mins.y < face.a1 and o.maxs.y > face.a0)
            if not touch:
                continue
            theirs = wall_faces(other).get(_OPPOSITE[side])
            top = theirs.top if theirs is not None else o.maxs.z
            here = top if not other.roofed else o.maxs.z
            if here >= base:
                base = here
                seen = None if other.roofed else other.id
        if face.top - base >= least:
            out.append(ExposedFace(side, face, base, seen))
    return out


def facade(bp, room, style: FacadeStyle, *, seed: str, ident: str | None = None) -> dict:
    """Dress every exposed outer face of *room* and put a roof over it.

    Returns ``{"faces": n, "blocks": n, "windows": [(x, y, z, side), ...]}``;
    the windows are points just outside each pane (for a fire or a glow).
    """
    rng = random.Random(f"{seed}:{room.id}:facade")
    ident = ident or f"{room.id}_facade"
    count = {"n": 0}
    windows: list[tuple[float, float, float, Side]] = []

    def block(box: Span, material, tag: str) -> None:
        bp.add_block(box, material, reachable=False, id=f"{ident}_{tag}", note=_NOTE)
        count["n"] += 1

    faces = exposed_faces(bp, room)
    for ex in faces:
        f, base = ex.face, ex.base
        tag = ex.side.name.lower()
        out = _outward(f)
        thick = abs(f.back - f.face)
        # Along the outer face, corners included.
        a0, a1 = f.a0 - thick, f.a1 + thick
        top = f.top

        def box(b0: float, b1: float, o0: float, o1: float, z0: float, z1: float) -> Span:
            c0, c1 = sorted((f.back + out * o0, f.back + out * o1))
            if f.along_x:
                return Span.between(Point(b0, c0, z0), Point(b1, c1, z1))
            return Span.between(Point(c0, b0, z0), Point(c1, b1, z1))

        h = top - base
        # The skin in bands of mixed stone, so no face is one flat material.
        skins = list(style.skins)
        z = base
        k = 0
        while z < top - 12.0:
            band = min(top - 12.0 - z, rng.uniform(0.3, 0.6) * h if h > 120 else h)
            band = max(band, min(40.0, top - 12.0 - z))
            block(box(a0, a1, 0.0, 1.5, z, z + band), skins[k % len(skins)], f"{tag}_skin{k}")
            z += band
            k += 1
        if style.soot and h > 90:
            block(box(a0, a1, 0.0, 2.5, top - 12.0 - min(34.0, 0.2 * h), top - 12.0), style.dark,
                  f"{tag}_soot")
        # Cornice and eave.
        block(box(a0 - 10, a1 + 10, 0.0, 14.0, top - 12.0, top - 4.0), style.trim, f"{tag}_cornice")
        block(box(a0 - 14, a1 + 14, 0.0, 20.0, top - 4.0, top + 2.0), style.roof, f"{tag}_eave")
        # A string course and, on a face that stands on the ground, a plinth.
        if h > 140:
            zs = base + 0.42 * h
            block(box(a0, a1, 0.0, 5.0, zs, zs + 6.0), style.trim, f"{tag}_string")
        if base <= room.outer.mins.z + 1.0:
            block(box(a0, a1, 0.0, 6.0, base - 16.0, base + 18.0), style.dark, f"{tag}_plinth")
        # Buttresses at an uneven rhythm, windows in the bays between.
        piers = [a0 + 14.0]
        at = a0 + 14.0
        while True:
            at += style.buttress_every + rng.uniform(-style.jitter, style.jitter)
            if at > a1 - 60.0:
                break
            piers.append(at)
        piers.append(a1 - 14.0)
        for n, p in enumerate(piers):
            w = 13.0 if n in (0, len(piers) - 1) else rng.uniform(10.0, 14.0)
            lower = base + h * rng.uniform(0.45, 0.6)
            block(box(p - w, p + w, 0.0, 16.0, base - 8.0, lower), style.trim if n % 3 else
                  skins[-1], f"{tag}_buttress{n}")
            block(box(p - w + 2, p + w - 2, 0.0, 9.0, lower, top - 14.0), skins[n % len(skins)],
                  f"{tag}_buttress{n}_upper")
            block(box(p - w - 1, p + w + 1, 0.0, 18.0, lower, lower + 5.0), style.trim,
                  f"{tag}_buttress{n}_cap")
        if style.window and h > 110:
            for n, (p, q) in enumerate(zip(piers, piers[1:])):
                if q - p < style.window_width + 50.0:
                    continue
                c = (p + q) / 2.0 + rng.uniform(-8, 8)
                w = style.window_width / 2.0
                z0 = base + 0.22 * h
                z1 = min(top - 40.0, z0 + max(70.0, 0.5 * h))
                block(box(c - w, c + w, 0.0, 1.0, z0, z1), style.dark, f"{tag}_pane{n}")
                block(box(c - w - 7, c - w, 0.0, 5.0, z0, z1), style.trim, f"{tag}_jambl{n}")
                block(box(c + w, c + w + 7, 0.0, 5.0, z0, z1), style.trim, f"{tag}_jambr{n}")
                block(box(c - w - 10, c + w + 10, 0.0, 8.0, z0 - 6.0, z0), style.trim, f"{tag}_sill{n}")
                block(box(c - 1.5, c + 1.5, 0.0, 3.0, z0, z1), style.trim, f"{tag}_mullion{n}")
                if style.window == "lancet":
                    for s, (ww, hh) in enumerate(((w + 7, 10.0), (w - 4, 10.0), (w - 14, 10.0))):
                        if ww <= 3:
                            break
                        zz = z1 + s * hh
                        block(box(c - ww, c + ww, 0.0, 5.0, zz, zz + hh), style.trim,
                              f"{tag}_head{n}_{s}")
                else:
                    block(box(c - w - 9, c + w + 9, 0.0, 6.0, z1, z1 + 8.0), style.trim,
                          f"{tag}_lintel{n}")
                wx, wy = (c, f.back + out * 10.0) if f.along_x else (f.back + out * 10.0, c)
                windows.append((wx, wy, (z0 + z1) / 2.0, ex.side))
    if faces and style.roof_kind == "gable":
        _gable(bp, room, style, rng, block, ident)
    elif faces and style.roof_kind == "parapet":
        _parapet(room, style, rng, block, {ex.side for ex in faces})
    return {"faces": len(faces), "blocks": count["n"], "windows": windows}


def _gable(bp, room, style: FacadeStyle, rng, block, ident: str) -> None:
    """Two pitched roof planes over the ceiling and crow-stepped gable ends."""
    o = room.outer
    top = o.maxs.z + 2.0
    along_x = style.ridge == "x"
    lo, hi = (o.mins.y, o.maxs.y) if along_x else (o.mins.x, o.maxs.x)
    run = (hi - lo) / 2.0 + 16.0
    mid = (lo + hi) / 2.0
    rise = run * style.pitch
    e0, e1 = (o.mins.x - 18.0, o.maxs.x + 18.0) if along_x else (o.mins.y - 18.0, o.maxs.y + 18.0)
    half_len = (e1 - e0) / 2.0
    centre = (e0 + e1) / 2.0
    for n, s in enumerate((-1.0, 1.0)):
        eave = mid + s * run
        if along_x:
            low = (centre, eave, top)
            high = (centre, mid, top + rise)
            sheared_bar(bp, f"{ident}_roof{n}", low, high, half_len, style.roof, note=_NOTE,
                        half_y=9.0)
        else:
            low = (eave, centre, top)
            high = (mid, centre, top + rise)
            sheared_bar(bp, f"{ident}_roof{n}", low, high, 9.0, style.roof, note=_NOTE,
                        half_y=half_len)
    # The ridge cap.
    if along_x:
        block(Span.between(Point(e0, mid - 8, top + rise - 4), Point(e1, mid + 8, top + rise + 6)),
              style.trim, "ridge")
    else:
        block(Span.between(Point(mid - 8, e0, top + rise - 4), Point(mid + 8, e1, top + rise + 6)),
              style.trim, "ridge")
    # Crow-stepped gable ends at both ends of the ridge.
    steps = 6
    skins = list(style.skins)
    for end, (g0, g1) in enumerate(((e0 + 18.0, e0 + 34.0), (e1 - 34.0, e1 - 18.0))):
        for k in range(steps):
            frac = k / steps
            half = run * (1.0 - frac) - 6.0
            z0 = top + rise * frac - 2.0
            z1 = top + rise * (k + 1) / steps + 10.0
            if half <= 8.0:
                break
            if along_x:
                span = Span.between(Point(g0, mid - half, z0), Point(g1, mid + half, z1))
                cap = Span.between(Point(g0 - 3, mid - half - 3, z1), Point(g1 + 3, mid + half + 3, z1 + 5))
            else:
                span = Span.between(Point(mid - half, g0, z0), Point(mid + half, g1, z1))
                cap = Span.between(Point(mid - half - 3, g0 - 3, z1), Point(mid + half + 3, g1 + 3, z1 + 5))
            block(span, skins[(k + end) % len(skins)], f"gable{end}_{k}")
            block(cap, style.trim, f"gable{end}_{k}_cap")
    # A chimney or a bellcote on the ridge.
    c = e0 + (e1 - e0) * rng.uniform(0.25, 0.75)
    if along_x:
        block(Span.between(Point(c - 14, mid - 14, top + rise - 30), Point(c + 14, mid + 14, top + rise + 56)),
              skins[0], "stack")
        block(Span.between(Point(c - 18, mid - 18, top + rise + 56), Point(c + 18, mid + 18, top + rise + 64)),
              style.trim, "stack_cap")
    else:
        block(Span.between(Point(mid - 14, c - 14, top + rise - 30), Point(mid + 14, c + 14, top + rise + 56)),
              skins[0], "stack")
        block(Span.between(Point(mid - 18, c - 18, top + rise + 56), Point(mid + 18, c + 18, top + rise + 64)),
              style.trim, "stack_cap")


def _parapet(room, style: FacadeStyle, rng, block, sides) -> None:
    """A crenellated parapet round the roof and a stepped pediment over each
    exposed face."""
    o = room.outer
    top = o.maxs.z + 2.0
    skins = list(style.skins)
    for side in (Side.NORTH, Side.SOUTH, Side.EAST, Side.WEST):
        along_x = side in (Side.NORTH, Side.SOUTH)
        a0, a1 = (o.mins.x, o.maxs.x) if along_x else (o.mins.y, o.maxs.y)
        c = {Side.NORTH: o.maxs.y, Side.SOUTH: o.mins.y, Side.EAST: o.maxs.x, Side.WEST: o.mins.x}[side]
        inward = -1.0 if side in (Side.NORTH, Side.EAST) else 1.0
        c0, c1 = sorted((c, c + inward * 14.0))

        def span(b0, b1, z0, z1, d0=c0, d1=c1):
            if along_x:
                return Span.between(Point(b0, d0, z0), Point(b1, d1, z1))
            return Span.between(Point(d0, b0, z0), Point(d1, b1, z1))

        tag = side.name.lower()
        block(span(a0, a1, top, top + 22.0), skins[0], f"parapet_{tag}")
        n = max(2, int((a1 - a0) // 40))
        for k in range(n):
            if k % 2:
                continue
            b0 = a0 + (a1 - a0) * k / n
            b1 = a0 + (a1 - a0) * (k + 1) / n
            block(span(b0, b1, top + 22.0, top + 36.0), skins[k % len(skins)], f"merlon_{tag}{k}")
        if side in sides:
            m = (a0 + a1) / 2.0
            for k, (hw, hh) in enumerate(((110.0, 18.0), (74.0, 18.0), (40.0, 22.0))):
                z0 = top + 22.0 + k * 18.0
                block(span(m - hw, m + hw, z0, z0 + hh), style.trim if k == 2 else skins[k % len(skins)],
                      f"pediment_{tag}{k}")
            block(span(m - 6, m + 6, top + 80.0, top + 130.0), style.trim, f"cross_{tag}")
            block(span(m - 22, m + 22, top + 110.0, top + 118.0), style.trim, f"crossbar_{tag}")
