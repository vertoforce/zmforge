"""Numeric inspection of convex solids: is this brush actually a brush?

Spec section 2.8.  Everything here works from the half-spaces alone, the way
the compiler does, so it can be run over solids the generator built *and* over
brushes parsed back out of emitted text -- which is the point: the text is
what the compiler reads, so the text is what the conformance tests check.

The inward convention is the engine's (spec 1.4): the solid is
``{p : n_i . p >= d_i}`` for every face.  A brush that is empty under that
reading and non-empty with every normal flipped has its points wound
backwards, which is the single most likely generator defect and the reason
:func:`inspect_planes` reports it as its own finding rather than as "empty".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable, Sequence

from ..spatial import Point, Span
from .halfspace import InwardPlane
from .forms import Solid

__all__ = [
    "SolidFinding",
    "SolidInspection",
    "inspect_planes",
    "inspect_solid",
    "solids_interpenetrate",
    "overlap_scan",
    "VOLUME_FLOOR",
    "VERTEX_TOLERANCE",
]

#: Points closer than this on every axis are the same vertex (spec 2.8 step 1).
VERTEX_TOLERANCE = 1e-3

#: A brush with less volume than this is degenerate (spec 2.8 step 5).
VOLUME_FLOOR = 1.0

#: How far two brushes must interpenetrate before the scan cares (2.8 step 7).
OVERLAP_SLACK = 1.0

_SINGULAR = 1e-9


@dataclass(frozen=True, slots=True)
class SolidFinding:
    """One thing wrong (or suspicious) about a solid."""

    code: str
    severity: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class SolidInspection:
    """What the checker measured, plus what it objects to."""

    vertices: tuple[Point, ...] = ()
    volume: float = 0.0
    findings: tuple[SolidFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(finding.is_error for finding in self.findings)

    @property
    def errors(self) -> list[SolidFinding]:
        return [finding for finding in self.findings if finding.is_error]

    def bounds(self) -> Span | None:
        if not self.vertices:
            return None
        return Span.flat_ok(
            Point(
                min(p.x for p in self.vertices),
                min(p.y for p in self.vertices),
                min(p.z for p in self.vertices),
            ),
            Point(
                max(p.x for p in self.vertices),
                max(p.y for p in self.vertices),
                max(p.z for p in self.vertices),
            ),
        )


def _solve(a: InwardPlane, b: InwardPlane, c: InwardPlane) -> Point | None:
    """Intersect three planes by Cramer's rule; ``None`` when they do not meet."""
    n1, n2, n3 = a.normal, b.normal, c.normal
    determinant = n1.dot(n2.cross(n3))
    if abs(determinant) <= _SINGULAR:
        return None
    numerator = (
        n2.cross(n3).scaled(a.offset)
        + n3.cross(n1).scaled(b.offset)
        + n1.cross(n2).scaled(c.offset)
    )
    return numerator.scaled(1.0 / determinant)


def _corners_of(planes: Sequence[InwardPlane], tolerance: float) -> list[Point]:
    """Every point where three planes meet that all the others also admit."""
    found: list[Point] = []
    for trio in combinations(range(len(planes)), 3):
        point = _solve(planes[trio[0]], planes[trio[1]], planes[trio[2]])
        if point is None:
            continue
        if any(plane.depth_at(point) < -tolerance for plane in planes):
            continue
        if not any(
            abs(point.x - seen.x) <= tolerance
            and abs(point.y - seen.y) <= tolerance
            and abs(point.z - seen.z) <= tolerance
            for seen in found
        ):
            found.append(point)
    return found


def _ordered_ring(points: Sequence[Point], normal: Point) -> list[Point]:
    """Sort coplanar points into a ring about ``normal``."""
    centre = Point(
        sum(p.x for p in points) / len(points),
        sum(p.y for p in points) / len(points),
        sum(p.z for p in points) / len(points),
    )
    reference = None
    for point in points:
        offset = point - centre
        if offset.length() > _SINGULAR:
            reference = offset.unit()
            break
    if reference is None:
        return list(points)
    side = normal.cross(reference)

    def angle(point: Point) -> float:
        import math

        offset = point - centre
        return math.atan2(offset.dot(side), offset.dot(reference))

    return sorted(points, key=angle)


def _volume(planes: Sequence[InwardPlane], vertices: Sequence[Point], tolerance: float) -> float:
    """Sum signed tetrahedra from the centroid over each face's fan."""
    if len(vertices) < 4:
        return 0.0
    centroid = Point(
        sum(p.x for p in vertices) / len(vertices),
        sum(p.y for p in vertices) / len(vertices),
        sum(p.z for p in vertices) / len(vertices),
    )
    total = 0.0
    for plane in planes:
        on_plane = [p for p in vertices if plane.lies_on(p, tolerance)]
        if len(on_plane) < 3:
            continue
        ring = _ordered_ring(on_plane, plane.normal)
        anchor = ring[0]
        for left, right in zip(ring[1:], ring[2:]):
            a = anchor - centroid
            b = left - centroid
            c = right - centroid
            total += abs(a.dot(b.cross(c))) / 6.0
    return total


def inspect_planes(
    planes: Sequence[InwardPlane], *, tolerance: float = VERTEX_TOLERANCE
) -> SolidInspection:
    """Run steps 1-6 of spec 2.8 over a set of inward half-spaces."""
    findings: list[SolidFinding] = []
    if len(planes) < 4:
        return SolidInspection(
            findings=(
                SolidFinding(
                    "degenerate",
                    "error",
                    f"a solid needs at least four half-spaces, this one has {len(planes)}",
                ),
            )
        )

    unit = [plane.normalised() for plane in planes]
    vertices = _corners_of(unit, tolerance)
    if len(vertices) < 4:
        flipped = _corners_of([plane.flipped() for plane in unit], tolerance)
        if len(flipped) >= 4:
            findings.append(
                SolidFinding(
                    "inverted",
                    "error",
                    "the half-spaces enclose nothing read inward but do read "
                    "outward: the face points are wound backwards",
                )
            )
        else:
            findings.append(
                SolidFinding(
                    "degenerate",
                    "error",
                    f"the half-spaces meet at only {len(vertices)} points, so they "
                    "enclose no solid under either winding",
                )
            )
        return SolidInspection(tuple(vertices), 0.0, tuple(findings))

    volume = _volume(unit, vertices, tolerance)
    if volume < VOLUME_FLOOR:
        findings.append(
            SolidFinding(
                "zero_volume",
                "error",
                f"the solid encloses {volume:.6g} cubic units, below the "
                f"{VOLUME_FLOOR} floor",
            )
        )

    for index, plane in enumerate(unit):
        on_plane = [p for p in vertices if plane.lies_on(p, tolerance)]
        if len(on_plane) < 3:
            findings.append(
                SolidFinding(
                    "unused_plane",
                    "warning",
                    f"half-space {index} carries {len(on_plane)} of the solid's "
                    "vertices, so no part of the finished surface lies on it; "
                    "the brush is bounded by more planes than its shape needs",
                )
            )
    return SolidInspection(tuple(vertices), volume, tuple(findings))


def inspect_solid(solid: Solid, *, tolerance: float = VERTEX_TOLERANCE) -> SolidInspection:
    """Inspect a built :class:`~.forms.Solid` through its face triples."""
    return inspect_planes(solid.planes, tolerance=tolerance)


def solids_interpenetrate(
    left: Sequence[Point], right: Sequence[Point], *, slack: float = OVERLAP_SLACK
) -> bool:
    """Separating-axis test on two convex point sets (spec 2.8 step 7).

    Axes tried: the face normals of both hulls (approximated by the edge
    cross-products of their vertex sets) plus the cross products of edge pairs.
    Returns ``True`` only when no axis separates them by more than ``slack``.
    """
    if len(left) < 4 or len(right) < 4:
        return False
    axes: list[Point] = []
    for hull in (left, right):
        for a, b, c in combinations(hull, 3):
            normal = (b - a).cross(c - a)
            if normal.length() > _SINGULAR:
                axes.append(normal.unit())
            if len(axes) > 400:
                break
    for axis in list(axes):
        pass
    deduped: list[Point] = []
    for axis in axes:
        if not any(
            abs(abs(axis.dot(seen)) - 1.0) < 1e-6 for seen in deduped
        ):
            deduped.append(axis)

    for axis in deduped:
        lo_a = min(axis.dot(p) for p in left)
        hi_a = max(axis.dot(p) for p in left)
        lo_b = min(axis.dot(p) for p in right)
        hi_b = max(axis.dot(p) for p in right)
        if min(hi_a, hi_b) - max(lo_a, lo_b) <= slack:
            return False
    return True


@dataclass(frozen=True, slots=True)
class OverlapFinding:
    """Two structural brushes that share more than a sliver of volume."""

    left: int
    right: int
    message: str


def overlap_scan(
    solids: Sequence[Solid], *, slack: float = OVERLAP_SLACK
) -> list[OverlapFinding]:
    """Pairwise interpenetration scan over structural world brushes.

    Cheap bounding-box rejection first; only boxes that interpenetrate on all
    three axes by more than ``slack`` go to the separating-axis test.

    The clip ramp over a flight of steps
    (:data:`~zmforge.blueprint.elements.STAIR_CLIP`) is skipped.  It is *meant*
    to interpenetrate: it is a plane laid over the treads so the walkers have
    something to slide up, exactly the way every flight in Treyarch's own
    source is tread models under one sloped clip brush.  Nothing is drawn on
    it, so the T-junction and z-fighting reasons this scan exists for do not
    apply to it.
    """
    from ..blueprint.elements import STAIR_CLIP

    solids = [solid for solid in solids if solid.note != STAIR_CLIP]
    inspections = [inspect_solid(solid) for solid in solids]
    boxes = [inspection.bounds() for inspection in inspections]
    findings: list[OverlapFinding] = []
    for i, j in combinations(range(len(solids)), 2):
        left, right = boxes[i], boxes[j]
        if left is None or right is None:
            continue
        if not left.overlaps(right, slack=slack):
            continue
        if solids_interpenetrate(
            inspections[i].vertices, inspections[j].vertices, slack=slack
        ):
            findings.append(
                OverlapFinding(
                    i,
                    j,
                    f"brush {i} ({solids[i].note or 'unlabelled'}) and brush {j} "
                    f"({solids[j].note or 'unlabelled'}) interpenetrate",
                )
            )
    return findings
