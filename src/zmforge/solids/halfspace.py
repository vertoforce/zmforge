"""Half-spaces and the one winding rule every emitted face triple obeys.

Spec section 1.4, measured on 25/25 real brushes: for face points ``A, B, C``
in the order written, ``(B - A) x (C - A)`` points *into* the solid, and the
solid is ``{p : n . p >= n . A}`` for every face.  That is the reverse of the
Quake convention, so nothing here may be short-cut with a remembered point
order; :func:`orient_inward` is the single source of truth and section 2.8's
checker is its test (spec section 10, K16).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..spatial import Point

__all__ = [
    "InwardPlane",
    "orient_inward",
    "plane_through",
    "ON_PLANE_TOLERANCE",
]

#: Distance within which a point counts as lying on a plane (spec 2.8 step 1).
ON_PLANE_TOLERANCE = 1e-3

#: Below this the cross product carries no direction we can trust.
_DEGENERATE = 1e-9


@dataclass(frozen=True, slots=True)
class InwardPlane:
    """The half-space ``normal . p >= offset``, normal pointing into the solid.

    ``normal`` is not required to be unit length by construction, but every
    plane this module builds is normalised so that :meth:`depth_at` reads in
    world units and the 1e-3 tolerances of spec 2.8 mean what they say.
    """

    normal: Point
    offset: float

    def depth_at(self, point: Point) -> float:
        """How far ``point`` lies inside this half-space (negative = outside)."""
        return self.normal.dot(point) - self.offset

    def holds(self, point: Point, tolerance: float = 0.0) -> bool:
        return self.depth_at(point) >= -tolerance

    def lies_on(self, point: Point, tolerance: float = ON_PLANE_TOLERANCE) -> bool:
        return abs(self.depth_at(point)) <= tolerance

    def flipped(self) -> "InwardPlane":
        """The same plane read outward, used by the inversion check of 2.8."""
        return InwardPlane(-self.normal, -self.offset)

    def normalised(self) -> "InwardPlane":
        length = self.normal.length()
        if length == 0.0:
            raise ValueError("a plane needs a non-zero normal")
        return InwardPlane(self.normal.scaled(1.0 / length), self.offset / length)


def orient_inward(
    a: Point, b: Point, c: Point, inward: Point
) -> tuple[Point, Point, Point]:
    """Order three plane points so their cross product points along ``inward``.

    Computes ``(b - a) x (c - a)``, dots it with ``inward``, and swaps ``b``
    and ``c`` when the dot product is negative.  A zero dot product is an
    error: either the three points are collinear, or the plane they span is
    perpendicular to the normal the caller asked for, and in both cases there
    is no ordering that satisfies the request (spec 2.1).
    """
    facing = (b - a).cross(c - a)
    reach = facing.dot(inward)
    scale = facing.length() * inward.length()
    if scale <= _DEGENERATE or abs(reach) <= _DEGENERATE * max(scale, 1.0):
        if scale <= _DEGENERATE:
            raise ValueError(
                f"cannot orient a plane through collinear points {tuple(a)}, "
                f"{tuple(b)}, {tuple(c)}"
            )
        raise ValueError(
            f"the plane through {tuple(a)}, {tuple(b)}, {tuple(c)} is "
            f"perpendicular to the requested inward normal {tuple(inward)}"
        )
    return (a, b, c) if reach > 0.0 else (a, c, b)


def plane_through(a: Point, b: Point, c: Point) -> InwardPlane:
    """The half-space the triple ``a, b, c`` defines under the inward reading."""
    normal = (b - a).cross(c - a)
    if normal.length() <= _DEGENERATE:
        raise ValueError(
            f"collinear face points {tuple(a)}, {tuple(b)}, {tuple(c)} "
            "define no plane"
        )
    unit = normal.unit()
    return InwardPlane(unit, unit.dot(a))
