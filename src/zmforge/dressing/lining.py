"""Plants lining a wall face: staggered rows of walk-through stalks, hedge or reeds.

Any map whose walls are meant to read as growth (a corn maze, a hedge maze, a
reed bank) lines both faces of each wall run with plants, so the brush behind
only does the blocking.  This module owns the geometry; the recipe picks the
plants and does the placing (its own keep-outs and clear zones decide yes or
no for each spot).

Density.  A single row of stalks 20 apart lets the earth-textured brush
show between and over them, so a lining is several staggered rows, the back
row tucked into the wall so its leaves hang over the wall top, every
footprint inside :attr:`Lining.depth` of the face so the walk lane between
two lined walls keeps its width.

Hidden wall, not lined face.  Counting stretches of face with a plant on them
overstates the cover: rasterising the real stalk meshes head-on, a lining
that "lined" 94.6% of a face hid 62% of it (p10 45%) and 21% of a 60-unit
strip over the wall top, because corn leaves are blades with air between
them and each plant hides far less than its box.  :data:`DEFAULT_LINING` is
four rows a plant every 10 along, leaning up to :attr:`Lining.lean` degrees
(the corn maze runs a plant every 8: 74% and 38%); the recipe also gives the
wall a surface that reads as more growth (a painted corn tile,
``props.corn.paint_corn_wall``) and raises the back row over the top.
:func:`hidden_fraction` is the measure (check ``Z89``, ``verify.lining``).

The worst gap, not the mean.  A 74% mean can still leave long stretches of
wall with no stalk at all.  Measured on the corn maze before the rows had
ranks (every lined face, stalk-free runs): 78 runs of 80 units and more, the
longest 421; behind a vignette's crates and wheelbarrow every row was trimmed
(17 runs of 150-245), and every keep-out (a bale's, a stand's, a door's) took
all four rows for its own width plus a whole plant's leaf spread (36) either
side.  So the rows have ranks (and a front-row plant a prop turns away steps
back into the back rows' line).  The *back* rows (:attr:`Lining.back_rows`, the ones at and
into the wall) carry on behind anything low in front of them: the recipe's
*place* gets ``back=True`` and lets a back plant stand wherever its stem is
clear, only real openings (a door, a window, a buy, a lane) turn it away.
The front rows still give way to props.  And where a plant is turned away,
:attr:`Lining.taper` tries it again smaller, so an opening's edge steps down
instead of leaving a plant's width of bare wall.  :func:`longest_bare_run`
is the measure (``Z89`` bounds the worst run, not the mean).

The rows: plant *k* goes in row ``k % rows``.  Row 0 is the overhang row (its
footprint reaches :attr:`Lining.tuck` into the wall), row 1 stands at the face
(:attr:`Lining.gap` off it), rows 2+ step back into the band as far as their
footprint allows.  Positions wobble along the face, yaws wobble off square,
each plant leans a few degrees its own way (``tilt``, so the rows are not a
picket fence), and the recipe's chooser varies model and scale per plant and
row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from ..spatial import Bounds

__all__ = ["Lining", "DEFAULT_LINING", "band_spans", "bare_runs", "hidden_fraction", "line_face", "plant_spot",
           "record_opening", "yaw_for", "lined_face_at",
           "longest_bare_run", "tilt_for"]


@dataclass(frozen=True)
class Lining:
    """How densely a wall face is lined."""

    #: Along-face spacing between consecutive plants (all rows together).
    step: float = 10.0
    #: Staggered rows; plant *k* is in row ``k % rows``.
    rows: int = 4
    #: No plant's footprint reaches further than this from the face (the lane
    #: between two lined walls keeps its width).
    depth: float = 76.0
    #: How far the overhang row's footprint may reach into the wall.
    tuck: float = 16.0
    #: The face row's set-back from the face.
    gap: float = 2.0
    #: Along-face wobble either way, so the rows are not ruled lines.
    wobble: float = 4.0
    #: A span of face shorter than this is left bare.
    min_span: float = 24.0
    #: Most a plant leans off upright, degrees (pitch and roll each); 0 keeps
    #: every plant upright.  Only for walk-through plants: the footprint
    #: checks use the upright box.
    lean: float = 5.0
    #: Rows ``0 .. back_rows - 1`` are the back rows: *place* is told
    #: (``back=True``) so they carry on behind low props and yield only to
    #: real openings.
    back_rows: int = 2
    #: Scale factors a turned-away plant is tried again at, in order, so the
    #: corn steps down at an opening's edge instead of stopping a whole
    #: plant's width short of it.
    taper: tuple[float, ...] = (0.7, 0.5)


DEFAULT_LINING = Lining()

#: ``(model, scale)`` for plant *k* in *row*.
Chooser = Callable[[int, int], tuple[str, float]]
#: ``(min x, max x, min y, max y)`` of *model* at *scale* and *yaw*, as offsets.
Extent = Callable[[str, float, float], tuple[float, float, float, float]]
#: Try to place *model* at ``(x, y)``, *yaw*, *scale*, leaning ``tilt=(pitch,
#: roll)`` degrees, ``back=True`` for a back-row plant (which should give way
#: only to real openings, not to low props); return whether it went.
Place = Callable[..., bool]


def yaw_for(k: int, salt: int = 0) -> float:
    """Plant *k*'s yaw, anywhere round the full circle: consecutive plants a
    golden angle (137.5 degrees) apart, so no two neighbours face alike.
    Yaws drawn from four right angles a few degrees apart make the stalks read
    as one clump repeated down the wall."""
    return round((k * 137.50776 + salt * 23.0) % 360.0, 2)


def squarer_yaw(yaw: float, k: int) -> float:
    """*yaw* moved to within 5 degrees of the nearest right angle (a turned
    square footprint is up to 1.41 times deeper), still different for each
    plant and its quarter kept, so neighbours still face four ways."""
    return round((90.0 * round(yaw / 90.0) + ((k * 7) % 11) - 5.0) % 360.0, 2)


def tilt_for(k: int, lean: float) -> tuple[float, float]:
    """Plant *k*'s ``(pitch, roll)``: each within *lean* degrees either way,
    spread so neighbours lean differently (no two consecutive plants alike)."""
    if lean <= 0:
        return (0.0, 0.0)
    return (round(lean * (((k * 29) % 11) / 5.0 - 1.0), 2), round(lean * (((k * 17) % 7) / 3.0 - 1.0), 2))


def band_spans(horizontal: bool, face: float, a0: float, a1: float, sign: int, depth: float,
               blockers: Iterable[Bounds] = (), margin: float = 2.0) -> list[tuple[float, float]]:
    """The stretches of the face from *a0* to *a1* whose band (*depth* deep
    on side *sign*) no blocker (another wall meeting this one) stands in."""
    lo_band = face if sign > 0 else face - depth
    hi_band = face + depth if sign > 0 else face
    spans = [(a0, a1)]
    for b in blockers:
        n0, n1 = (b.mins.y, b.maxs.y) if horizontal else (b.mins.x, b.maxs.x)
        t0, t1 = (b.mins.x, b.maxs.x) if horizontal else (b.mins.y, b.maxs.y)
        if n1 <= lo_band + 0.5 or n0 >= hi_band - 0.5:
            continue
        cut = []
        for s0, s1 in spans:
            if t1 <= s0 or t0 >= s1:
                cut.append((s0, s1))
                continue
            if t0 > s0:
                cut.append((s0, t0 - margin))
            if t1 < s1:
                cut.append((t1 + margin, s1))
        spans = cut
    return spans


def line_face(horizontal: bool, face: float, spans: Sequence[tuple[float, float]], sign: int,
              choose: Chooser, extent: Extent, place: Place, *, lining: Lining = DEFAULT_LINING,
              salt: int = 0) -> int:
    """Line the face ``y = face`` (*horizontal*) or ``x = face`` along each of
    *spans*, the band on side *sign*.  Returns how many plants *place* took."""
    placed = 0
    k = salt
    for s0, s1 in spans:
        if s1 - s0 < lining.min_span:
            continue
        n = max(1, int((s1 - s0) // lining.step))
        for i in range(n + 1):
            k += 1
            row = k % lining.rows
            model, scale = choose(k, row)
            yaw = yaw_for(k, salt)
            a = s0 + i * (s1 - s0) / n + ((k * 13 % 7) - 3.0) * lining.wobble / 3.0
            # A front-row plant a prop turns away steps back to the back
            # rows' line rather than leave its stretch of wall bare.
            tries = [row] + ([r for r in range(lining.back_rows - 1, -1, -1)] if row >= lining.back_rows else [])
            done = False
            for r in tries:
                m, base = (model, scale) if r == row else choose(k, r)
                for size in (1.0, *lining.taper):
                    yw = yaw
                    x, y, sc = plant_spot(horizontal, face, s0, s1, sign, r, a, m, base * size, yw, extent, lining)
                    if sc < 0.97 * base * size:
                        # Turned this way its box is too deep for the band and
                        # it would be shrunk: turn it nearer square instead.
                        yw = squarer_yaw(yaw, k)
                        x, y, sc = plant_spot(horizontal, face, s0, s1, sign, r, a, m, base * size, yw, extent,
                                              lining)
                    if place(m, x, y, yw, sc, tilt=tilt_for(k, lining.lean), back=r < lining.back_rows):
                        placed += 1
                        done = True
                        break
                if done:
                    break
    return placed


def plant_spot(horizontal: bool, face: float, s0: float, s1: float, sign: int, row: int, a: float, model: str,
          scale: float, yaw: float, extent: Extent, lining: Lining) -> tuple[float, float, float]:
    """Where plant *model* at *scale* in *row* stands for along-face *a*:
    ``(x, y, scale)``, scaled down to fit the band."""
    ex0, ex1, ey0, ey1 = extent(model, scale, yaw)
    deep = (ey1 - ey0) if horizontal else (ex1 - ex0)
    if row == 0:
        back = -lining.tuck
    elif row == 1:
        back = lining.gap
    else:
        back = lining.gap + (lining.depth - lining.gap) * (row - 1) / lining.rows
    if deep + back > lining.depth:
        back = max(min(back, lining.depth - deep), -lining.tuck if row == 0 else lining.gap)
        if deep + back > lining.depth:
            scale *= (lining.depth - back - 0.5) / deep
        ex0, ex1, ey0, ey1 = extent(model, scale, yaw)
    if horizontal:
        x = min(max(a, s0 - ex0), s1 - ex1)
        y = face + back - ey0 if sign > 0 else face - back - ey1
    else:
        y = min(max(a, s0 - ey0), s1 - ey1)
        x = face + back - ex0 if sign > 0 else face - back - ex1
    return x, y, scale


def lined_face_at(origin, facing, faces, tol: float = 6.0):
    """The entry of *faces* (``bp.lined_faces``) a wall item at *origin*
    looking *facing* hangs on: its line within *tol* of the face, looking the
    face's way, inside its span and its height; or ``None``.  WHY: a wall buy chalked on a lined face clears the plants in
    front of it, and that strip read as bare wall; buys go on unlined walls
    (``zmforge.placement.wallbuy``, check ``Z91``)."""
    step = facing.step
    horizontal = abs(step.y) > abs(step.x)
    sign = 1 if (step.y if horizontal else step.x) > 0 else -1
    off, along = (origin.y, origin.x) if horizontal else (origin.x, origin.y)
    for f in faces:
        h, face, (s0, s1), sg, floor, top = f[:6]
        if h == horizontal and sg == sign and abs(off - face) <= tol and s0 - 1.0 <= along <= s1 + 1.0 \
                and floor - 40.0 <= origin.z <= top:
            return f
    return None


def record_opening(bp, box: Bounds, why: str, *, spread: float = 40.0) -> int:
    """Record *box* (something placed against a lined wall after the lining,
    which cleared the plants behind it: a buy, a machine) as an opening on
    every one of ``bp.lined_faces`` whose band it stands in, *spread* either
    side along the face (a plant's half leaf spread).  ``Z89`` excuses it.
    Returns how many faces it opened."""
    faces = getattr(bp, "lined_faces", None)
    if not faces:
        return 0
    openings = getattr(bp, "lined_openings", None)
    if openings is None:
        openings = bp.lined_openings = []
    n = 0
    for horizontal, face, (s0, s1), sign, floor, top, *rest in faces:
        depth = rest[0] if rest else DEFAULT_LINING.depth
        n0, n1 = (box.mins.y, box.maxs.y) if horizontal else (box.mins.x, box.maxs.x)
        t0, t1 = (box.mins.x, box.maxs.x) if horizontal else (box.mins.y, box.maxs.y)
        d0, d1 = sorted(((n0 - face) * sign, (n1 - face) * sign))
        if d1 < -DEFAULT_LINING.tuck or d0 > depth or t1 < s0 or t0 > s1 \
                or box.maxs.z < floor or box.mins.z > top:
            continue
        openings.append((horizontal, face, sign, t0 - spread, t1 + spread, why))
        n += 1
    return n


def bare_runs(cover: Iterable, span: tuple[float, float],
              openings: Iterable[tuple[float, float]] = ()) -> list[tuple[float, float]]:
    """The stretches of *span* nothing covers: ``(start, end)``.  Each of
    *cover* is a plant, either a position along the face (a point: the run
    is measured between plants) or the ``(a0, a1)`` stretch of face it hides;
    *openings* (along-face intervals left bare on purpose: a door, a window,
    a buy) count as covered."""
    s0, s1 = span
    spans = sorted([(c, c) if isinstance(c, (int, float)) else (c[0], c[1]) for c in cover]
                   + [(o0, o1) for o0, o1 in openings])
    runs = []
    at = s0
    for c0, c1 in spans:
        if c1 < s0 or c0 > s1:
            continue
        if c0 > at:
            runs.append((at, min(c0, s1)))
        at = max(at, c1)
    if at < s1:
        runs.append((at, s1))
    return [(r0, r1) for r0, r1 in runs if r1 > r0]


def longest_bare_run(cover: Iterable, span: tuple[float, float],
                     openings: Iterable[tuple[float, float]] = ()) -> tuple[float, float, float]:
    """``(length, start, end)`` of the longest of :func:`bare_runs`."""
    runs = bare_runs(cover, span, openings)
    if not runs:
        return (0.0, span[0], span[0])
    r0, r1 = max(runs, key=lambda r: r[1] - r[0])
    return (r1 - r0, r0, r1)


def hidden_fraction(horizontal: bool, face: float, span: tuple[float, float], sign: int, floor: float,
                    top: float, plants: Iterable[tuple[Sequence, Sequence, float, float, float, float,
                                                       float, float, float]],
                    *, cell: float = 2.0, above: float = 0.0) -> float:
    """How much of a lined face a player looking straight at it cannot see.

    The face is ``y = face`` (*horizontal*) or ``x = face``, *span* along it,
    from *floor* to *top* (or the strip from *top* to ``top + above`` when
    *above* is given).  Each of *plants* is ``(positions, triangles, x, y,
    z, yaw, scale, pitch, roll)``: a model's own mesh (game space, Z up) and
    how it stands.  Every triangle is drawn straight onto the face at *cell*
    units; the result is the share of cells something covers.  Head-on is the
    worst view: down a corridor the rows overlap and hide more.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    s0, s1 = span
    z0, z1 = (top, top + above) if above > 0 else (floor, top)
    w, h = max(1, int((s1 - s0) / cell)), max(1, int((z1 - z0) / cell))
    img = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for positions, triangles, x, y, z, yaw, scale, pitch, roll in plants:
        p = np.asarray(positions, float) * scale
        # The map's angles, applied roll, then pitch, then yaw (Z up).
        r, q, t = (math.radians(a) for a in (roll, pitch, yaw))
        rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
        ry = np.array([[math.cos(q), 0, math.sin(q)], [0, 1, 0], [-math.sin(q), 0, math.cos(q)]])
        rz = np.array([[math.cos(t), -math.sin(t), 0], [math.sin(t), math.cos(t), 0], [0, 0, 1]])
        g = p @ (rz @ ry @ rx).T + (x, y, z)
        along = g[:, 0] if horizontal else g[:, 1]
        u = (along - s0) / cell
        v = (z1 - g[:, 2]) / cell
        for a, b, c in triangles:
            draw.polygon([(u[a], v[a]), (u[b], v[b]), (u[c], v[c])], fill=1)
    return float(np.asarray(img, bool).mean())
