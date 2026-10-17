"""Natural clustering: planting in clumps, and a measure of evenness.

Plants do not grow evenly spaced.  They seed next to each other, gather
where something shelters them (the foot of a wall, a grave's edge, a path
kerb, the base of a tree or a monument) and leave bare ground between the
clumps and along the walked lines.  A seeded uniform scatter reads as
too evenly distributed however many props it lays: real bushes grow next
to each other.

* :func:`clustered_points` -- a Thomas cluster process: parent points drawn
  toward *edges* and away from *avoid* lines, offspring in a gaussian round
  each parent, stretched along the nearest edge.
* :func:`mixed_clumps` -- clumps of mixed species: a big core piece, a ring
  of smaller ones round it and a fringe of grass, placed through the
  recipe's own placer so its keep-outs still hold.
* :func:`clark_evans` -- the Clark-Evans nearest-neighbour ratio *R* of a
  set of points: about 1 for an even random scatter, above 1 for a regular
  (spaced) one, well under 1 for clumps.  ``Z66`` warns on foliage with
  *R* at or over :data:`EVEN_R`.
* :func:`is_foliage`, :func:`rect_edges`, :func:`edge_distance`.

Every function takes its own ``random.Random`` and draws from it in a fixed
order, so a map is the same every build.  Units are map units (inches).

An *edge* is a segment ``(x0, y0, x1, y1)`` or a disc ``(x, y, r)`` (a
tree's or a monument's base, measured from its rim).  An *avoid* line is a
segment plus its clearance ``(x0, y0, x1, y1, clear)`` or a disc
``(x, y, clear)``: nothing lands within *clear* of it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, NamedTuple, Sequence

from .. import progress

__all__ = [
    "EVEN_R",
    "FOLIAGE_MARKERS",
    "MIN_FOLIAGE",
    "Tier",
    "Planting",
    "is_foliage",
    "rect_edges",
    "edge_distance",
    "nearest_edge",
    "nn_distances",
    "clark_evans",
    "clustered_points",
    "mixed_clumps",
]

#: Model-name parts that mark a plant or ground cover a player reads as
#: growing there.  Corn is left out: a field is planted in rows on purpose.
FOLIAGE_MARKERS = ("foliage", "grass", "weed", "leaves", "bush", "hedge", "ivy", "fern",
                   "moss", "shrub", "meskel")
#: ``Z66``: foliage whose Clark-Evans ratio is at or over this reads as an
#: even scatter (a random one is 1).  Walks, plots and tombs cut into the
#: room pull every map's R down, since the ratio is taken over the whole
#: floor: zm_cemetery's lawns, when they read as too evenly
#: distributed, measured 0.76 (gate) and 0.78 (hills), and 0.70 / 0.70
#: once clumped.  So this catches a
#: plainly even room (zm_dmv's lot, 1.0); a subtler one needs the render.
EVEN_R = 0.85
#: ``Z66`` asks only of a room with at least this much foliage: a handful
#: of plants has no pattern to read.
MIN_FOLIAGE = 40

Segment = tuple[float, float, float, float]
Disc = tuple[float, float, float]


def is_foliage(model: str) -> bool:
    """A plant, grass, weed, hedge or fallen-leaf model (:data:`FOLIAGE_MARKERS`)."""
    m = model.lower()
    return "corn" not in m and any(k in m for k in FOLIAGE_MARKERS)


def rect_edges(x0: float, y0: float, x1: float, y1: float) -> list[Segment]:
    """The four sides of a plan rectangle as edge segments (a grave plot, a
    tomb's footprint, a room's walls)."""
    return [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]


def _seg(x: float, y: float, s) -> tuple[float, float]:
    """Distance from (x, y) to segment *s*, and the segment's direction."""
    ax, ay, bx, by = s[:4]
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ll))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy)), math.atan2(dy, dx)


def edge_distance(x: float, y: float, edge) -> tuple[float, float]:
    """Distance from (x, y) to *edge* (a segment, or a disc's rim) and the
    edge's direction there (radians; a disc's tangent)."""
    if len(edge) == 3:
        ex, ey, r = edge
        return max(0.0, math.hypot(x - ex, y - ey) - r), math.atan2(y - ey, x - ex) + math.pi / 2
    return _seg(x, y, edge)


class _Index:
    """Edges bucketed on a grid by their box grown by *reach*, so a point
    looks only at the edges that could be within *reach* of it."""

    def __init__(self, edges: Iterable, reach: float, cell: float = 128.0) -> None:
        self.cell, self.reach = cell, reach
        self.grid: dict[tuple[int, int], list] = {}
        for e in edges:
            if len(e) == 3:
                x0, y0, x1, y1 = e[0] - e[2], e[1] - e[2], e[0] + e[2], e[1] + e[2]
            else:
                x0, y0, x1, y1 = min(e[0], e[2]), min(e[1], e[3]), max(e[0], e[2]), max(e[1], e[3])
            pad = reach + (e[4] if len(e) == 5 else 0.0)
            for i in range(math.floor((x0 - pad) / cell), math.floor((x1 + pad) / cell) + 1):
                for j in range(math.floor((y0 - pad) / cell), math.floor((y1 + pad) / cell) + 1):
                    self.grid.setdefault((i, j), []).append(e)

    def near(self, x: float, y: float) -> list:
        return self.grid.get((math.floor(x / self.cell), math.floor(y / self.cell)), [])


def nearest_edge(x: float, y: float, edges: Iterable) -> tuple[float, float]:
    """The distance to the nearest of *edges* and its direction there
    (``(inf, 0.0)`` with none)."""
    best, angle = math.inf, 0.0
    for e in edges:
        d, a = edge_distance(x, y, e)
        if d < best:
            best, angle = d, a
    return best, angle


def _blocked(x: float, y: float, avoid_near: Iterable) -> bool:
    for a in avoid_near:
        if len(a) == 3:
            if math.hypot(x - a[0], y - a[1]) < a[2]:
                return True
        elif _seg(x, y, a)[0] < a[4]:
            return True
    return False


def nn_distances(points: Sequence[tuple[float, float]]) -> list[float]:
    """Each point's distance to its nearest neighbour (grid search)."""
    n = len(points)
    if n < 2:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    cell = max(span / math.sqrt(n), 1.0)
    grid: dict[tuple[int, int], list[int]] = {}
    for k, (x, y) in enumerate(zip(xs, ys)):
        grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append(k)
    out = []
    for k, (x, y) in enumerate(zip(xs, ys)):
        ci, cj = math.floor(x / cell), math.floor(y / cell)
        best, ring = math.inf, 0
        while True:
            for i in range(ci - ring, ci + ring + 1):
                for j in range(cj - ring, cj + ring + 1):
                    if max(abs(i - ci), abs(j - cj)) != ring:
                        continue
                    for m in grid.get((i, j), ()):
                        if m != k:
                            best = min(best, math.hypot(x - xs[m], y - ys[m]))
            # a point in ring r+1 is at least r * cell away
            if best <= ring * cell or ring > n:
                break
            ring += 1
        out.append(best)
    return out


def clark_evans(points: Sequence[tuple[float, float]], area: float,
                perimeter: float | None = None) -> float | None:
    """The Clark-Evans ratio *R* of *points* over a window of *area* square
    units: their mean nearest-neighbour distance over the ``0.5 / sqrt(n /
    area)`` a random (Poisson) scatter of the same density would have.
    With *perimeter*, the expected distance takes Donnelly's edge
    correction (points by the window's edge have fewer neighbours).  About
    1 is random, over 1 regular, under 1 clumped; ``None`` for fewer than
    two points or no area."""
    n = len(points)
    if n < 2 or area <= 0:
        return None
    mean = sum(nn_distances(points)) / n
    expected = 0.5 * math.sqrt(area / n)
    if perimeter:
        expected += (0.0514 + 0.041 / math.sqrt(n)) * perimeter / n
    return round(mean / expected, 3)


def _weight(d_edge: float, reach: float, bias: float, offset: float = 0.0) -> float:
    """How likely a parent is kept *d_edge* from the nearest edge: 1 up to
    *offset* out (the clearance a placer keeps off the edge), falling to
    ``1 - bias`` past *offset* + *reach*."""
    if math.isinf(d_edge):
        return 1.0 - bias
    return (1.0 - bias) + bias * math.exp(-(max(0.0, d_edge - offset) / reach) ** 2)


def _parents(rng: random.Random, rect, n: int, eidx: _Index | None, aidx: _Index | None, *,
             edge_reach: float, edge_bias: float, parent_gap: float,
             accept: Callable[[float, float], bool] | None, tries: int,
             edge_offset: float = 0.0, before: Sequence[tuple[float, float, float]] = ()) -> list[tuple[float, float, float]]:
    """Up to *n* parents ``(x, y, tangent)`` by rejection: drawn uniformly
    in *rect*, kept with the edge weight, never within *parent_gap* of
    another parent, *before*'s included (the bare ground between clumps)."""
    x0, y0, x1, y1 = rect
    out: list[tuple[float, float, float]] = []
    others = list(before)
    for _ in range(n * tries):
        if len(out) >= n:
            break
        x, y, keep = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.random()
        d, a = nearest_edge(x, y, eidx.near(x, y)) if eidx else (math.inf, 0.0)
        if eidx and keep > _weight(d, edge_reach, edge_bias, edge_offset):
            continue
        if aidx and _blocked(x, y, aidx.near(x, y)):
            continue
        if parent_gap and any(math.hypot(x - px, y - py) < parent_gap for px, py, _ in others):
            continue
        if accept is not None and not accept(x, y):
            continue
        if d > edge_offset + edge_reach:
            a = rng.uniform(0.0, math.pi)
        out.append((x, y, a))
        others.append((x, y, a))
    return out


def _offset(rng: random.Random, r0: float, r1: float, along: float, tangent: float) -> tuple[float, float]:
    """A point *r0*..*r1* out from the origin (sqrt-uniform over the ring),
    stretched *along* times along *tangent* and squeezed across it."""
    r = math.sqrt(rng.uniform(r0 * r0, r1 * r1))
    t = rng.uniform(0.0, 2.0 * math.pi)
    u, v = r * math.cos(t) * math.sqrt(along), r * math.sin(t) / math.sqrt(along)
    c, s = math.cos(tangent), math.sin(tangent)
    return u * c - v * s, u * s + v * c


def clustered_points(rng: random.Random, rect: tuple[float, float, float, float], count: int, *,
                     clumps: int | None = None, spread: float = 40.0, edges: Sequence = (),
                     edge_reach: float = 120.0, edge_bias: float = 0.85, along: float = 1.8,
                     edge_offset: float = 0.0, avoid: Sequence = (), parent_gap: float = 0.0,
                     accept: Callable[[float, float], bool] | None = None,
                     tries: int = 40) -> list[tuple[float, float, int]]:
    """Up to *count* points ``(x, y, clump)`` in clumps over *rect*
    ``(x0, y0, x1, y1)``: a Thomas process.

    *clumps* parents (default ``count / 6``) are drawn toward *edges* (kept
    with probability 1 up to *edge_offset* from an edge, falling to
    ``1 - edge_bias`` past a further *edge_reach*), outside every *avoid* clearance and *parent_gap* apart.
    Each takes an equal share of *count* as offspring in a gaussian of
    *spread* round it, stretched *along* times along the nearest edge (a
    drift along a wall foot, not a disc).  *accept* turns down a point."""
    if count <= 0:
        return []
    k = max(1, clumps if clumps is not None else round(count / 6))
    eidx = _Index(edges, edge_reach) if edges else None
    aidx = _Index(avoid, 0.0) if avoid else None
    parents = _parents(rng, rect, k, eidx, aidx, edge_reach=edge_reach, edge_bias=edge_bias,
                       parent_gap=parent_gap, accept=accept, tries=tries, edge_offset=edge_offset)
    if not parents:
        return []
    x0, y0, x1, y1 = rect
    out: list[tuple[float, float, int]] = []
    share = [count // len(parents) + (1 if i < count % len(parents) else 0) for i in range(len(parents))]
    sa, sb = spread * math.sqrt(along), spread / math.sqrt(along)
    for i, ((px, py, a), want) in enumerate(zip(parents, share)):
        c, s = math.cos(a), math.sin(a)
        got = 0
        for _ in range(want * tries):
            if got >= want:
                break
            u, v = rng.gauss(0.0, sa), rng.gauss(0.0, sb)
            x, y = px + u * c - v * s, py + u * s + v * c
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if aidx and _blocked(x, y, aidx.near(x, y)):
                continue
            if accept is not None and not accept(x, y):
                continue
            out.append((x, y, i))
            got += 1
    return out


@dataclass(frozen=True)
class Tier:
    """One ring of a mixed clump: pieces drawn from *palette*
    ``((model, (scale_lo, scale_hi), weight), ...)``, *count* ``(lo, hi)``
    of them, each *reach* ``(r0, r1)`` out from the clump's centre."""

    palette: Sequence[tuple[str, tuple[float, float], int]]
    count: tuple[int, int]
    reach: tuple[float, float]


class Planting(NamedTuple):
    """One placed piece of a clump."""

    model: str
    x: float
    y: float
    yaw: float
    scale: float
    clump: int
    tier: int


def _pick(rng: random.Random, palette) -> tuple[str, float]:
    total = sum(w for _m, _s, w in palette)
    r = rng.uniform(0.0, total)
    for model, (s0, s1), w in palette:
        r -= w
        if r <= 0:
            return model, rng.uniform(s0, s1)
    model, (s0, s1), _w = palette[-1]
    return model, rng.uniform(s0, s1)


def mixed_clumps(rng: random.Random, rect: tuple[float, float, float, float],
                 tiers: Sequence[Tier], count: int, *,
                 place: Callable[[str, float, float, float, float], bool],
                 clumps: int | None = None, edges: Sequence = (), edge_reach: float = 120.0,
                 edge_bias: float = 0.85, edge_offset: float = 0.0, along: float = 1.6,
                 avoid: Sequence = (), rounds: int = 6,
                 parent_gap: float = 0.0, accept: Callable[[float, float], bool] | None = None,
                 retries: int = 4, tries: int = 40) -> list[Planting]:
    """Mixed-species clumps over *rect* until *count* pieces are placed.

    Parents are drawn as in :func:`clustered_points` (toward *edges*, off
    *avoid*, *parent_gap* apart; *clumps* of them, default enough for
    *count* at the tiers' mean size, plus half again for the ones that do
    not fit; up to *rounds* - 1 more rounds of parents top a short count
    up).  Each clump lays its *tiers* in order, the first usually one
    big core piece (a bush), the next a ring of smaller ones, the last a
    fringe of grass, each piece *place* ``(model, x, y, yaw, scale)``'d by
    the recipe, which returns False when the spot is taken; a refused
    piece tries *retries* more spots.  A clump whose core does not fit
    still lays its ring and fringe.  Returns what was placed."""
    if count <= 0:
        return []
    mean = sum((t.count[0] + t.count[1]) / 2.0 for t in tiers) or 1.0
    eidx = _Index(edges, edge_reach) if edges else None
    aidx = _Index(avoid, 0.0) if avoid else None
    x0, y0, x1, y1 = rect
    out: list[Planting] = []
    parents: list[tuple[float, float, float]] = []
    # Up to *rounds* rounds: the pieces the recipe's placer turns away leave
    # the count short, and the next round draws parents for what is left.
    for round_ in range(rounds):
        left = count - len(out)
        if left <= 0:
            break
        if round_ == 0 and clumps is not None:
            k = clumps
        else:
            k = max(1, math.ceil(1.5 * left / mean))
        fresh = _parents(rng, rect, k, eidx, aidx, edge_reach=edge_reach, edge_bias=edge_bias,
                         parent_gap=parent_gap, accept=accept, tries=tries,
                         edge_offset=edge_offset, before=parents)
        if not fresh:
            break
        for (px, py, a) in fresh:
            ci = len(parents)
            parents.append((px, py, a))
            for ti, tier in enumerate(tiers):
                if len(out) >= count:
                    return out
                want = rng.randint(*tier.count)
                laid = 0
                for _ in range(want * (retries + 1)):
                    if laid >= want or len(out) >= count:
                        break
                    model, scale = _pick(rng, tier.palette)
                    ox, oy = _offset(rng, tier.reach[0], tier.reach[1], along, a)
                    x, y, yaw = px + ox, py + oy, rng.uniform(0.0, 360.0)
                    if not (x0 <= x <= x1 and y0 <= y <= y1):
                        continue
                    if aidx and _blocked(x, y, aidx.near(x, y)):
                        continue
                    if accept is not None and not accept(x, y):
                        continue
                    if place(model, x, y, yaw, scale):
                        out.append(Planting(model, x, y, yaw, scale, ci, ti))
                        laid += 1
                        progress.count("placing clumps", len(out), count)
    return out
