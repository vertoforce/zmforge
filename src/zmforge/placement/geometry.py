"""Plan geometry: convex polygons, overlap, and Minkowski sums.

Everything in :mod:`zmforge.placement` works on the *plan*, the shadow a model
casts on the floor, because that is what a placement rule is about: two boxes
at the same height sharing floor is a fault, two boxes at different heights
sharing floor is a shelf.  Height is carried alongside as a pair of numbers
(:class:`~zmforge.placement.relations.Placed`) rather than as a third polygon
axis.

Three things live here and nothing else:

* :class:`Poly2`, a polygon in plan, built from a rectangle or from an
  oriented box (centre, half extents, yaw), with the questions a placer asks
  of one: area, overlap area, separation, containment;
* :func:`convex_hull`, because every derived shape below is a hull;
* :func:`minkowski_disc` and :func:`minkowski_segment`, which grow a footprint
  by a shape rather than by a number.  Merrell et al. 2011 specify clearance
  that way and it is the difference between "48 units all round, always" and
  "the room this model actually needs, which is its own outline plus a player".

Pure stdlib on purpose.  ``zmforge`` itself declares no dependencies
(``pyproject.toml``); numpy is an extra the texture chain pulls in, and a
placement rule that could not run without it would take the generator's
no-dependency guarantee with it.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "Vec2",
    "Poly2",
    "convex_hull",
    "minkowski_disc",
    "minkowski_segment",
    "rotate",
    "segment_distance",
    "unit_hash",
]

#: A point in plan.  Plain tuples: these are made and thrown away by the
#: thousand inside a flood fill, and a frozen dataclass per point measured
#: slower with nothing gained.
Vec2 = tuple[float, float]

#: Below this a length is zero, an area is empty and two coordinates are the
#: same.  World units are inches and the map grid is 8, so a thousandth of a
#: unit is far below anything the ``.map`` writer can express.
EPSILON = 1e-9


def rotate(x: float, y: float, yaw: float) -> Vec2:
    """``(x, y)`` turned ``yaw`` degrees about the origin, counter-clockwise.

    Yaw is the map's own convention (``spatial``: pitch yaw roll, yaw about
    Z), so this is the same turn :func:`zmforge.recipes.props._placed_origin`
    applies to a model's box.
    """
    radians = math.radians(yaw)
    cos, sin = math.cos(radians), math.sin(radians)
    return (x * cos - y * sin, x * sin + y * cos)


def segment_distance(point: Vec2, start: Vec2, end: Vec2) -> float:
    """Distance from a point to a line segment, not to its infinite line."""
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length <= EPSILON:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def convex_hull(points: Iterable[Vec2]) -> tuple[Vec2, ...]:
    """The convex hull of a point set, counter-clockwise, no repeated last point.

    Monotone chain.  Fewer than three distinct points come back as they are,
    because a segment and a point are both legitimate degenerate footprints
    (a sheet of paper on edge, a marker) and raising on them would make every
    caller special-case them.
    """
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) < 3:
        return tuple(pts)

    def half(sequence: Sequence[Vec2]) -> list[Vec2]:
        out: list[Vec2] = []
        for p in sequence:
            while len(out) >= 2 and _cross(out[-2], out[-1], p) <= EPSILON:
                out.pop()
            out.append(p)
        return out

    lower = half(pts)
    upper = half(pts[::-1])
    return tuple(lower[:-1] + upper[:-1])


def _cross(o: Vec2, a: Vec2, b: Vec2) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


@dataclass(frozen=True, slots=True)
class Poly2:
    """A convex polygon in plan, counter-clockwise.

    Convex is a deliberate restriction and it is what the map has: a model's
    footprint is a rotated box, a room is a rectangle, a keep-clear zone is a
    rectangle or a grown box.  Every operation here is the cheap convex one,
    and a non-convex shape is expressed as several of these rather than as one
    polygon nothing can clip.  :meth:`of` takes the hull of whatever it is
    handed, so a caller cannot smuggle a concave outline in by accident.
    """

    points: tuple[Vec2, ...]

    # -- construction ----------------------------------------------------
    @classmethod
    def of(cls, points: Iterable[Vec2]) -> "Poly2":
        return cls(convex_hull(points))

    @classmethod
    def rect(cls, x0: float, y0: float, x1: float, y1: float) -> "Poly2":
        """An axis-aligned rectangle from any two opposite corners."""
        lox, hix = (x0, x1) if x0 <= x1 else (x1, x0)
        loy, hiy = (y0, y1) if y0 <= y1 else (y1, y0)
        return cls(((lox, loy), (hix, loy), (hix, hiy), (lox, hiy)))

    @classmethod
    def box(cls, cx: float, cy: float, hx: float, hy: float, yaw: float = 0.0) -> "Poly2":
        """An oriented box: centre, half extents in its own frame, then yaw.

        This is a placed prop's footprint.  The half extents are the model's
        own, so they are turned with it: a 90-long desk at yaw 90 is 90 deep,
        which is the thing ``plan_half_extent`` in the current placer works
        out by swapping numbers and this works out by turning corners.
        """
        corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        turned = [rotate(x, y, yaw) for x, y in corners]
        return cls(tuple((cx + x, cy + y) for x, y in turned))

    # -- measurement -----------------------------------------------------
    @property
    def area(self) -> float:
        pts = self.points
        if len(pts) < 3:
            return 0.0
        total = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """``(x0, y0, x1, y1)``, the axis-aligned box around this polygon."""
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def centroid(self) -> Vec2:
        pts = self.points
        if not pts:
            raise ValueError("an empty polygon has no centroid")
        if len(pts) < 3 or self.area <= EPSILON:
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        cx = cy = signed = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            step = x1 * y2 - x2 * y1
            signed += step
            cx += (x1 + x2) * step
            cy += (y1 + y2) * step
        signed /= 2.0
        return (cx / (6.0 * signed), cy / (6.0 * signed))

    # -- relations -------------------------------------------------------
    def holds(self, point: Vec2, tolerance: float = 0.0) -> bool:
        """Is this point inside, counting the edge as inside?"""
        pts = self.points
        if len(pts) < 3:
            return False
        for i in range(len(pts)):
            if _cross(pts[i], pts[(i + 1) % len(pts)], point) < -tolerance:
                return False
        return True

    def intersection(self, other: "Poly2") -> "Poly2":
        """The shared part, clipped by Sutherland-Hodgman.

        Both polygons are convex and counter-clockwise, which is what makes
        the clip a handful of lines instead of a polygon library.  An empty
        result is a ``Poly2`` with no points, not ``None``, so a caller can
        take ``.area`` of it without a branch.
        """
        out: list[Vec2] = list(self.points)
        clip = other.points
        if len(clip) < 3 or len(out) < 3:
            return Poly2(())
        for i in range(len(clip)):
            a = clip[i]
            b = clip[(i + 1) % len(clip)]
            source, out = out, []
            if not source:
                break
            previous = source[-1]
            for current in source:
                inside_current = _cross(a, b, current) >= -EPSILON
                inside_previous = _cross(a, b, previous) >= -EPSILON
                if inside_current:
                    if not inside_previous:
                        out.append(_meet(previous, current, a, b))
                    out.append(current)
                elif inside_previous:
                    out.append(_meet(previous, current, a, b))
                previous = current
        return Poly2(tuple(out))

    def overlap_area(self, other: "Poly2") -> float:
        """How much floor these two share."""
        x0, y0, x1, y1 = self.bounds
        ox0, oy0, ox1, oy1 = other.bounds
        if x1 <= ox0 or ox1 <= x0 or y1 <= oy0 or oy1 <= y0:
            return 0.0  # broad phase: apart in plan, nothing to clip
        return self.intersection(other).area

    def gap_to(self, other: "Poly2") -> float:
        """The clear distance between two convex polygons; 0 when they touch.

        Overlapping polygons also answer 0.  "How far apart" and "how far
        into each other" are different questions and
        :meth:`overlap_area` is the one that answers the second.
        """
        if self.overlap_area(other) > EPSILON:
            return 0.0
        best = math.inf
        for a, b in ((self, other), (other, self)):
            for point in a.points:
                pts = b.points
                if len(pts) == 1:
                    best = min(best, math.hypot(point[0] - pts[0][0], point[1] - pts[0][1]))
                    continue
                for i in range(len(pts)):
                    best = min(
                        best,
                        segment_distance(point, pts[i], pts[(i + 1) % len(pts)]),
                    )
        return 0.0 if best is math.inf else best

    # -- derivation ------------------------------------------------------
    def moved(self, dx: float, dy: float) -> "Poly2":
        return Poly2(tuple((x + dx, y + dy) for x, y in self.points))

    def turned(self, yaw: float, about: Vec2 = (0.0, 0.0)) -> "Poly2":
        ax, ay = about
        turned = [rotate(x - ax, y - ay, yaw) for x, y in self.points]
        return Poly2(tuple((x + ax, y + ay) for x, y in turned))


def _meet(p1: Vec2, p2: Vec2, a: Vec2, b: Vec2) -> Vec2:
    """Where the segment ``p1 p2`` crosses the line through ``a b``."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = a
    x4, y4 = b
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < EPSILON:
        return p2
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


#: How many segments approximate the disc in :func:`minkowski_disc`.  Sixteen
#: puts the flat of each segment 1.9% inside the true circle, so a 15-unit
#: player disc is understated by 0.3 of a unit at worst, which is a quarter of
#: the ``.map`` writer's own grid.
DISC_SEGMENTS = 16


def minkowski_disc(poly: Poly2, radius: float, segments: int = DISC_SEGMENTS) -> Poly2:
    """``poly`` grown by a disc of ``radius``: the Minkowski sum of the two.

    This is Merrell et al.'s clearance, and it is not the same shape as
    growing the bounding box by ``radius``: the corners come back rounded and
    a rotated footprint keeps its rotation.  What it means physically is "the
    set of centres where a player of this radius would touch this prop", which
    is exactly what a circulation test needs to subtract from the floor.
    """
    if radius <= 0.0:
        return poly
    ring = [
        (radius * math.cos(2.0 * math.pi * i / segments),
         radius * math.sin(2.0 * math.pi * i / segments))
        for i in range(max(3, segments))
    ]
    return Poly2.of(
        (px + dx, py + dy) for px, py in poly.points for dx, dy in ring
    )


def minkowski_segment(poly: Poly2, dx: float, dy: float) -> Poly2:
    """``poly`` swept along one vector: the sum with a line segment.

    The front apron of a desk, a chair or a wall buy is this and not a disc.
    The paper's own wording is "a line segment or a disk sized according to
    Table 1"; a segment is what you want when the clearance is directional --
    the space to pull a chair out, the space to stand and use a buy -- and a
    disc is what you want when it is not.
    """
    if abs(dx) <= EPSILON and abs(dy) <= EPSILON:
        return poly
    return Poly2.of(
        list(poly.points) + [(x + dx, y + dy) for x, y in poly.points]
    )


def unit_hash(*parts: object) -> float:
    """A repeatable number in ``[0, 1)`` from whatever it is handed.

    Every generator and modifier in :mod:`zmforge.placement.scatter` draws
    from this, so a map's dressing is a function of its own names and indices
    rather than of a global random stream.  Two consequences that are the
    whole point: the same blueprint always produces the same layout, and
    adding a scene to one room does not move the props in another.

    BLAKE2b rather than :func:`hash`, because ``hash`` of a string is salted
    per process and would give a different map on every run.
    """
    digest = hashlib.blake2b(
        "\x1f".join(str(p) for p in parts).encode("utf-8"), digest_size=8
    ).digest()
    return struct.unpack("<Q", digest)[0] / 2.0 ** 64
