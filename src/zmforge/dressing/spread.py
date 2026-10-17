"""Seeded spreads: litter in drifts and heaps, and runs that never repeat.

Litter spread evenly over a floor reads as confetti in every review; it
belongs in drifts where it gathers (round bins, under benches, in corners,
at the foot of walls).  Every function takes its own ``random.Random`` (or a
seed) and draws from it in a fixed order, so a map is the same every build.
Units are map units (inches), yaw in degrees.

* :func:`drift_points` -- points only, weighted drifts (the recipe places).
* :func:`litter_in_drifts` -- props, each drift filled to its own count.
* :func:`litter_by_weight` -- props, one total shared out by drift weight.
* :func:`litter_heaps` -- props in gaussian heaps that step round what is
  already on the floor (:func:`~zmforge.dressing.place.floor_boxes`).
* :func:`bins_in`, :func:`seats_in`, :func:`corner_heaps` -- where heaps go.
* :func:`no_repeat` -- a run of kinds never the same twice running.
"""

from __future__ import annotations

import math
import random
from typing import Callable, Hashable, Iterable, Sequence, TypeVar

from ..blueprint.elements import PropScatter
from .place import PropSpec, floor_boxes, on_floor

__all__ = [
    "Drift",
    "drift_points",
    "litter_in_drifts",
    "litter_by_weight",
    "litter_heaps",
    "bins_in",
    "seats_in",
    "corner_heaps",
    "no_repeat",
]

T = TypeVar("T", bound=Hashable)

#: A drift: ``(cx, cy, half_w, half_h, n)``, a rectangle centred on
#: (cx, cy) and *n* its count or its weight, per the function taking it.
Drift = tuple[float, float, float, float, int]
#: A keep-out circle ``(x, y, radius)``.
Circle = tuple[float, float, float]


def _anywhere(x: float, y: float) -> bool:
    return True


def drift_points(rng: random.Random, drifts: Sequence[tuple[float, float, float, float, int]],
                 count: int, accept: Callable[[float, float], bool] = lambda x, y: True, *,
                 tries: int = 8000) -> list[tuple[float, float]]:
    """Up to *count* litter points in weighted drifts.

    *drifts* is ``(cx, cy, half_w, half_h, weight)`` rectangles: put them
    where litter gathers (round bins, between benches, in corners, at the
    foot of walls), each weighted by how much ends up there.  *accept* turns
    down a point (keep-outs, solid footprints, walls).  Litter spread evenly
    over a floor reads as confetti in every review (zm_corn_maze's
    grass among them)."""
    slots = [d for d in drifts for _ in range(max(int(d[4]), 0))]
    if not slots:
        return []
    out: list[tuple[float, float]] = []
    n = 0
    while len(out) < count and n < tries:
        n += 1
        cx, cy, w, h, _ = slots[n % len(slots)]
        x = cx + rng.uniform(-w, w)
        y = cy + rng.uniform(-h, h)
        if accept(x, y):
            out.append((x, y))
    return out


def _clear(x: float, y: float, keep: Sequence[Circle], out: Sequence[PropSpec],
           spacing: float) -> bool:
    return (not any(math.hypot(x - kx, y - ky) < r for kx, ky, r in keep)
            and not any(math.hypot(x - p[1].x, y - p[1].y) < spacing for p in out))


def litter_in_drifts(rng: random.Random, drifts: Sequence[Drift], models: Sequence[str],
                     floor_z: float, *, accept: Callable[[float, float], bool] = _anywhere,
                     keep: Sequence[Circle] = (), spacing: float = 11.0,
                     tries: int = 400) -> list[PropSpec]:
    """Non-solid floor litter, each drift ``(cx, cy, half_w, half_h, n)``
    filled in turn with up to *n* pieces (*tries* draws each), cycling
    *models*, each piece at a random yaw.  A point is kept when *accept*
    says so, it is outside every *keep* circle and *spacing* from every
    piece already down."""
    out: list[PropSpec] = []
    for cx, cy, w, h, n in drifts:
        placed, drawn = 0, 0
        while placed < n and drawn < tries:
            drawn += 1
            x, y = cx + rng.uniform(-w, w), cy + rng.uniform(-h, h)
            if not accept(x, y) or not _clear(x, y, keep, out, spacing):
                continue
            model = models[len(out) % len(models)]
            out.append(on_floor(model, x, y, floor_z, rng.uniform(0.0, 360.0), solid=False))
            placed += 1
    return out


def litter_by_weight(rng: random.Random, drifts: Sequence[Drift], count: int,
                     models: Sequence[str], floor_z: float, *,
                     accept: Callable[[float, float], bool] = _anywhere,
                     keep: Sequence[Circle] = (), spacing: float = 11.0,
                     tries: int = 8000) -> list[PropSpec]:
    """Up to *count* pieces of non-solid floor litter shared out over
    *drifts* by weight (each drift's last field; the draws cycle through
    the drifts, a weight-3 drift three times per cycle), cycling *models*,
    each at a random yaw.  Same tests as :func:`litter_in_drifts`."""
    slots = [d for d in drifts for _ in range(max(int(d[4]), 0))]
    out: list[PropSpec] = []
    if not slots:
        return out
    drawn = 0
    while len(out) < count and drawn < tries:
        drawn += 1
        cx, cy, w, h, _ = slots[drawn % len(slots)]
        x = cx + rng.uniform(-w, w)
        y = cy + rng.uniform(-h, h)
        if not accept(x, y) or not _clear(x, y, keep, out, spacing):
            continue
        model = models[len(out) % len(models)]
        out.append(on_floor(model, x, y, floor_z, rng.uniform(0.0, 360.0), solid=False))
    return out


def _hits(me, o, pad: float) -> bool:
    return not (me[2] + pad <= o[0] or o[2] + pad <= me[0]
                or me[3] + pad <= o[1] or o[3] + pad <= me[1])


def litter_heaps(bp, room, rect: tuple[float, float, float, float], n: int, seed: int,
                 heaps, *, keep_out=(), margin: float = 2.0,
                 solid_margin: float = 6.0) -> list[PropSpec]:
    """*n* non-solid floor props laid as tight heaps inside *rect*
    ``(x0, y0, x1, y1)`` of *room* (``.interior``, ``.floor_z``).

    *heaps* is a list of ``(x, y, spread, weight, models)``: each heap inside
    *rect* takes a share of *n* by weight and lays its pieces in a gaussian
    of *spread* about (x, y), cycling *models*, clear of solid props (by
    *solid_margin*), of the floor litter already down (by *margin*), of each
    *keep_out* rect and of each other.  A heap centred on a post moves to the
    nearest clear point on a ring round it; a heap that runs out of room
    grows its spread a little at a time rather than dropping pieces, so the
    count holds.  Pieces of one heap that overlap sit a quarter unit above
    each other so flat sheets do not fight for the pixel."""
    from ..recipes.props import collision_box

    rng = random.Random(seed)
    fz = room.floor_z
    here = floor_boxes(bp, room)
    taken = [t[:4] for t in here if not t[4]]
    solids = [t[:4] for t in here if t[4]]
    heaps = [h for h in heaps if rect[0] <= h[0] <= rect[2] and rect[1] <= h[1] <= rect[3]]
    if not heaps:
        return []
    total_w = sum(h[3] for h in heaps)
    shares = [int(n * h[3] / total_w) for h in heaps]
    for i in range(n - sum(shares)):
        shares[i % len(shares)] += 1

    def free_centre(hx, hy):
        for r in (0.0, 12.0, 24.0, 36.0, 48.0, 64.0):
            for step in range(12 if r else 1):
                a = math.radians(step * 30.0)
                x, y = hx + r * math.cos(a), hy + r * math.sin(a)
                probe = (x - 10.0, y - 10.0, x + 10.0, y + 10.0)
                if not (rect[0] + 10.0 <= x <= rect[2] - 10.0 and rect[1] + 10.0 <= y <= rect[3] - 10.0):
                    continue
                if any(_hits(probe, o, solid_margin) for o in solids):
                    continue
                if any(_hits(probe, o, 0.0) for o in keep_out):
                    continue
                return x, y
        return hx, hy

    out: list[PropSpec] = []
    for (hx, hy, spread, _w, models), share in zip(heaps, shares):
        hx, hy = free_centre(hx, hy)
        mine: list[tuple[float, float, float, float]] = []
        placed = tries = 0
        sigma = spread
        while placed < share and tries < share * 400:
            tries += 1
            if tries % 100 == 0:
                sigma *= 1.15
            model = models[placed % len(models)]
            yaw = float(rng.randrange(0, 360, 5))
            (bx0, by0, _z0), (bx1, by1, _z1) = collision_box(model)
            c, s = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
            hw = (bx1 - bx0) / 2.0 * c + (by1 - by0) / 2.0 * s
            hh = (bx1 - bx0) / 2.0 * s + (by1 - by0) / 2.0 * c
            x = rng.gauss(hx, sigma)
            y = rng.gauss(hy, sigma)
            if not (rect[0] + hw <= x <= rect[2] - hw and rect[1] + hh <= y <= rect[3] - hh):
                continue
            me = (x - hw, y - hh, x + hw, y + hh)
            if any(_hits(me, o, solid_margin) for o in solids) or any(_hits(me, o, margin) for o in taken):
                continue
            if any(_hits(me, o, 0.0) for o in keep_out):
                continue
            under = sum(_hits(me, o, 0.0) for o in mine)
            mine.append(me)
            out.append(on_floor(model, x, y, fz + 0.25 * under, yaw, solid=False))
            placed += 1
        taken.extend(mine)
    return out


def bins_in(bp, room) -> list[tuple[float, float]]:
    """Plan positions of the trash cans standing in *room*: heap centres."""
    b = room.interior
    return [(p.origin.x, p.origin.y) for s in bp.elements(PropScatter) for p in s.props
            if "trashcan" in p.model
            and b.mins.x <= p.origin.x <= b.maxs.x and b.mins.y <= p.origin.y <= b.maxs.y]


def seats_in(bp, room) -> list[tuple[float, float]]:
    """Plan positions of the chairs and benches on *room*'s floor, sorted."""
    b = room.interior
    return sorted((p.origin.x, p.origin.y) for s in bp.elements(PropScatter) for p in s.props
                  if ("chair" in p.model or "bench" in p.model or "seat" in p.model)
                  and b.mins.x <= p.origin.x <= b.maxs.x and b.mins.y <= p.origin.y <= b.maxs.y
                  and p.origin.z < room.floor_z + 8.0)


def corner_heaps(rect: tuple[float, float, float, float],
                 inset: float = 30.0) -> list[tuple[float, float]]:
    """The four corners of *rect*, *inset* in: where drafts leave paper."""
    x0, y0, x1, y1 = rect
    return [(x0 + inset, y0 + inset), (x1 - inset, y0 + inset),
            (x0 + inset, y1 - inset), (x1 - inset, y1 - inset)]


def no_repeat(kinds: Iterable[T], count: int, rng: random.Random) -> list[T]:
    """*count* picks from *kinds*, never the same one twice running (when
    there are two or more), so a row of wall modules does not read as one
    module stamped along the wall."""
    pool = list(kinds)
    if not pool:
        return []
    out: list[T] = []
    for _ in range(count):
        options = [k for k in pool if not out or k != out[-1]] or pool
        out.append(rng.choice(options))
    return out


