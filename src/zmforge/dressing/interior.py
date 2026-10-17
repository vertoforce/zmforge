"""Dense indoor dressing: packed shelves, stacked clutter, things hung up.

A stock room is dense because its surfaces are full, not because its floor
is: zm_giant carries about 1,150 props per 1000 x 1000 units of floor, 19%
of them overhead, and most of
the rest stand on shelves, counters and each other.  The corn maze's
farmhouse had 240 a million square units and its barn 150 (far
too sparse to read as lived in): a few items per board, one layer of
crates, nothing above head height.  These three blocks fill the heights a
room has:

* :func:`fill_board` -- a shelf board, counter or sill packed end to end,
  in runs of like items (a row of jars, a stack of books), not one of each.
* :func:`stack_clump` -- a heap that climbs: a base piece, maybe a second
  on it, small things on top, and a skirt of smaller ones round its foot.
* :func:`hang_under` -- ceiling-hung models (cage lamps, shades, washing)
  in a row under a beam or line, with the bar they hang from.

Each returns :class:`Piece` records, origins backed out of the measured
footprints, and places nothing: the recipe runs them through its own
placer so its keep-outs (doors, buys, lanes, windows) still hold.
"""

from __future__ import annotations

import math
import random
from typing import NamedTuple, Sequence

from ..spatial import Bounds
from .fixtures import RAIL, hang_bar

__all__ = ["Piece", "fill_board", "readable", "stack_clump", "hang_under"]


class Piece(NamedTuple):
    """One prop to place: origin plan position, the height of the surface
    its underside rests on, yaw and scale."""

    model: str
    x: float
    y: float
    surface: float
    yaw: float
    scale: float = 1.0


def _box(model: str):
    from ..recipes.props import MODEL_BOX

    return MODEL_BOX[model]


def _turned(model: str, yaw: float, scale: float = 1.0) -> tuple[float, float, float, float]:
    """The footprint turned by *yaw* about the origin, ``(x0, y0, x1, y1)``."""
    (x0, y0, _), (x1, y1, _) = _box(model)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    xs, ys = [], []
    for px, py in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        xs.append((px * c - py * s) * scale)
        ys.append((px * s + py * c) * scale)
    return min(xs), min(ys), max(xs), max(ys)


def _origin(model: str, cx: float, cy: float, yaw: float, scale: float = 1.0) -> tuple[float, float]:
    """The origin that puts *model*'s turned footprint centre on (cx, cy)."""
    fx0, fy0, fx1, fy1 = _turned(model, yaw, scale)
    return cx - (fx0 + fx1) / 2.0, cy - (fy0 + fy1) / 2.0


def height(model: str, scale: float = 1.0) -> float:
    (_, _, z0), (_, _, z1) = _box(model)
    return (z1 - z0) * scale


def _pick(rng: random.Random, palette: Sequence[tuple[str, int]]) -> str:
    total = sum(w for _m, w in palette)
    r = rng.uniform(0.0, total)
    for model, w in palette:
        r -= w
        if r <= 0:
            return model
    return palette[-1][0]


def readable(palette: Sequence[tuple[str, int]], power: float = 1.0,
             size: float = 10.0) -> tuple[tuple[str, float], ...]:
    """*palette* reweighted toward things big enough to read from across a
    room: each weight times ``(largest side / size) ** power``.  A 3-unit
    bottle and a 20-unit jug at equal weight fill a board with bottles by
    count, and from 400 units off the board reads empty (corn maze barn,
    render)."""
    out = []
    for model, w in palette:
        (x0, y0, z0), (x1, y1, z1) = _box(model)
        out.append((model, w * (max(x1 - x0, y1 - y0, z1 - z0) / size) ** power))
    return tuple(out)


def fill_board(rng: random.Random, palette: Sequence[tuple[str, int]], board: Bounds, top: float, *,
               gap: float = 1.0, inset: float = 1.5, run: tuple[int, int] = (2, 5),
               max_height: float | None = None, back: float = 0.0, weight_size: float = 1.0) -> list[Piece]:
    """*board* (its plan box; its long side is the row) packed end to end
    from *palette* ``((model, weight), ...)``, each item resting on *top*.

    Items come in runs of 2-5 alike (*run*), as a pantry shelf holds six
    jars of one thing and then the next; an item is turned a quarter if that
    is what fits the board's depth, and skipped if neither way does or it
    is taller than *max_height* (the gap to the board above).  *back* pushes
    the row toward the board's back edge by that much (``+`` toward max).
    Rows stop at the board's end: nothing overhangs (Z44).  *weight_size*
    is :func:`readable`'s power: by default a big item is picked in
    proportion to its size, 0 keeps the palette's own weights."""
    if weight_size:
        palette = readable(palette, weight_size)
    along_x = (board.maxs.x - board.mins.x) >= (board.maxs.y - board.mins.y)
    a0, a1 = (board.mins.x, board.maxs.x) if along_x else (board.mins.y, board.maxs.y)
    b0, b1 = (board.mins.y, board.maxs.y) if along_x else (board.mins.x, board.maxs.x)
    depth = b1 - b0 - 2 * inset
    out: list[Piece] = []
    at = a0 + inset
    model, left, misses = None, 0, 0
    while misses < 6:
        if left <= 0:
            model, left = _pick(rng, palette), rng.randint(*run)
        fits = None
        for turn in (0.0, 90.0):
            yaw = turn + rng.uniform(-8.0, 8.0) + (0.0 if along_x else 90.0)
            fx0, fy0, fx1, fy1 = _turned(model, yaw)
            w, dpt = (fx1 - fx0, fy1 - fy0) if along_x else (fy1 - fy0, fx1 - fx0)
            if dpt <= depth and (max_height is None or height(model) <= max_height):
                fits = (yaw, w, dpt)
                break
        if fits is None or at + fits[1] > a1 - inset:
            misses += 1
            left = 0
            continue
        yaw, w, dpt = fits
        slack = max(0.0, depth - dpt)
        cb = (b0 + b1) / 2.0 + min(slack / 2.0, abs(back)) * (1 if back >= 0 else -1)
        ca = at + w / 2.0
        cx, cy = (ca, cb) if along_x else (cb, ca)
        ox, oy = _origin(model, cx, cy, yaw)
        out.append(Piece(model, ox, oy, top, yaw % 360.0))
        at += w + gap
        left -= 1
        misses = 0
    return out


def stack_clump(rng: random.Random, x: float, y: float, floor: float, *,
                base: Sequence[tuple[str, int]], tops: Sequence[tuple[str, int]] = (),
                skirt: Sequence[tuple[str, int]] = (), second: float = 0.5,
                on_top: tuple[int, int] = (1, 3), skirt_n: tuple[int, int] = (2, 5),
                skirt_reach: tuple[float, float] = (6.0, 26.0), yaw: float | None = None) -> list[Piece]:
    """A heap round (*x*, *y*): a *base* piece on the floor, with chance
    *second* of another base piece stacked on it (turned a little, as
    stacks are), *on_top* small things from *tops* on the highest, and a
    *skirt* of *skirt_n* smaller pieces on the floor round its foot.

    Order matters: the recipe's placer refuses what does not fit, and a
    refused base should take its stack with it, so the base comes first and
    the caller drops the rest of a clump when its first piece is refused
    (``Piece.surface == floor`` for the base and the skirt)."""
    out: list[Piece] = []
    turn = rng.uniform(0.0, 360.0) if yaw is None else yaw
    b = _pick(rng, base)
    out.append(Piece(b, *_origin(b, x, y, turn), floor, turn % 360.0))
    fx0, fy0, fx1, fy1 = _turned(b, turn)
    half_x, half_y = (fx1 - fx0) / 2.0, (fy1 - fy0) / 2.0
    level = floor + height(b)
    top_half = (half_x, half_y)
    if second and rng.random() < second:
        b2 = _pick(rng, base)
        t2 = turn + rng.uniform(-12.0, 12.0)
        gx0, gy0, gx1, gy1 = _turned(b2, t2)
        if gx1 - gx0 <= 2 * half_x + 2.0 and gy1 - gy0 <= 2 * half_y + 2.0:
            out.append(Piece(b2, *_origin(b2, x, y, t2), level, t2 % 360.0))
            level += height(b2)
            top_half = ((gx1 - gx0) / 2.0, (gy1 - gy0) / 2.0)
    for _ in range(rng.randint(*on_top) if tops else 0):
        m = _pick(rng, tops)
        t = rng.uniform(0.0, 360.0)
        mx0, my0, mx1, my1 = _turned(m, t)
        rx, ry = top_half[0] - (mx1 - mx0) / 2.0 - 1.5, top_half[1] - (my1 - my0) / 2.0 - 1.5
        if rx < 0 or ry < 0:
            continue
        cx, cy = x + rng.uniform(-rx, rx), y + rng.uniform(-ry, ry)
        out.append(Piece(m, *_origin(m, cx, cy, t), level, t))
    reach = math.hypot(half_x, half_y)
    for _ in range(rng.randint(*skirt_n) if skirt else 0):
        m = _pick(rng, skirt)
        t = rng.uniform(0.0, 360.0)
        mx0, my0, mx1, my1 = _turned(m, t)
        r = reach + max(mx1 - mx0, my1 - my0) / 2.0 + rng.uniform(*skirt_reach)
        a = rng.uniform(0.0, 2 * math.pi)
        out.append(Piece(m, *_origin(m, x + r * math.cos(a), y + r * math.sin(a), t), floor, t))
    return out


def hang_under(bp, ident: str, a: tuple[float, float], b: tuple[float, float], z: float, *,
               ceiling: float, models: Sequence[tuple[str, int]], rng: random.Random,
               step: tuple[float, float] = (22.0, 40.0), bar: bool = True, half: float = 1.5,
               material=RAIL) -> list[Piece]:
    """Ceiling-hung models (their measured box hangs below the origin: a
    cage lamp, a shade, washing on a hanger) in a row from *a* to *b* under
    a bar whose top is *z*, the bar itself built (on rods up to *ceiling*)
    unless *bar* is False (a beam already there, *z* its underside).  Every
    *step* units along it, one of *models*.  Returns pieces whose
    ``surface`` is the hung model's own bottom, so a placer that rests an
    underside on ``surface`` puts its top against the bar."""
    if bar:
        hang_bar(bp, ident, a, b, z, ceiling=ceiling, half=half, material=material)
        under = z - 2.0 * half
    else:
        under = z
    (x0, y0), (x1, y1) = a, b
    length = math.hypot(x1 - x0, y1 - y0)
    if length <= 0:
        return []
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    along_yaw = math.degrees(math.atan2(uy, ux))
    out: list[Piece] = []
    t = rng.uniform(*step) / 2.0
    while t < length - 8.0:
        m = _pick(rng, models)
        # Washing hangs square to its line; lamps turn as they like.
        yaw = along_yaw + (90.0 if "clothes" in m else rng.uniform(0.0, 360.0))
        cx, cy = x0 + ux * t, y0 + uy * t
        out.append(Piece(m, *_origin(m, cx, cy, yaw), under - height(m), yaw % 360.0))
        t += rng.uniform(*step)
    return out
