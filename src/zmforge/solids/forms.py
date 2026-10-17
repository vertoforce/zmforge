"""Convex primitives: the box, the wedge and the stair flight.

Every face triple leaves this module through :func:`~.halfspace.orient_inward`
(spec 2.1 and section 10, K16).  Nothing here knows about the map text; a
:class:`Solid` is a set of oriented, materialled faces and the writer layer
turns it into brush lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import InvalidBounds
from ..materials import CAULK, FaceMaterials, Material
from ..spatial import Axis, Facing, Point, Side, Span
from .halfspace import InwardPlane, orient_inward, plane_through

__all__ = ["SolidFace", "Solid", "block", "wedge", "flight", "stair_clip",
           "stair_gate",
           "STAIR_GATE_HEIGHT"]


@dataclass(frozen=True, slots=True)
class SolidFace:
    """One bounding half-space, carried as the triple that will be written.

    ``inward`` is the normal the triple was oriented against.  It is kept so a
    reader can tell what the face was *meant* to bound without re-deriving it,
    but every check in :mod:`~.inspect` recomputes the plane from ``points``,
    because the points are what the compiler reads.
    """

    points: tuple[Point, Point, Point]
    material: Material
    inward: Point

    @property
    def plane(self) -> InwardPlane:
        return plane_through(*self.points)


@dataclass(frozen=True, slots=True)
class Solid:
    """A convex brush: the intersection of its faces' half-spaces."""

    faces: tuple[SolidFace, ...]
    contents: tuple[str, ...] = ()
    note: str = ""

    @property
    def planes(self) -> list[InwardPlane]:
        return [face.plane for face in self.faces]

    @property
    def material_names(self) -> set[str]:
        return {face.material.name for face in self.faces}

    def labelled(self, note: str) -> "Solid":
        return Solid(self.faces, self.contents, note)


def _face_triple(box: Span, side: Side) -> tuple[Point, Point, Point]:
    """Three distinct, non-collinear corners of one face of ``box``.

    The face's lowest corner and its two edge neighbours, taken in the order
    spec 2.1 uses for its worked example so the test vectors there apply to
    this builder unchanged.
    """
    fixed = side.axis
    coordinate = box.face_plane(side)
    first, second = (axis for axis in Axis if axis is not fixed)
    lo_a, hi_a = box.mins[first.index], box.maxs[first.index]
    lo_b, hi_b = box.mins[second.index], box.maxs[second.index]

    def corner(a: float, b: float) -> Point:
        parts = [0.0, 0.0, 0.0]
        parts[fixed.index] = coordinate
        parts[first.index] = a
        parts[second.index] = b
        return Point(*parts)

    return corner(lo_a, lo_b), corner(lo_a, hi_b), corner(hi_a, hi_b)


def _faced(
    points: tuple[Point, Point, Point], inward: Point, material: Material
) -> SolidFace:
    return SolidFace(orient_inward(*points, inward), material, inward)


def block(
    box: Span,
    materials: FaceMaterials | Material | str = CAULK,
    contents: tuple[str, ...] = (),
    note: str = "",
) -> Solid:
    """Six faces bounding an axis-aligned box (spec 2.1).

    ``Span`` already refuses a non-positive extent on construction, which is
    the guard section 10 item K7 asks for; a zero-thickness brush can never
    reach this function.
    """
    palette = (
        materials
        if isinstance(materials, FaceMaterials)
        else FaceMaterials.uniform(materials)
    )
    faces = tuple(
        _faced(_face_triple(box, side), side.inward, palette.on(side)) for side in Side
    )
    return Solid(faces, tuple(contents), note)


def wedge(
    box: Span,
    rise_toward: Facing | Side | str,
    materials: FaceMaterials | Material | str = CAULK,
    contents: tuple[str, ...] = (),
    note: str = "",
) -> Solid:
    """The half of ``box`` under the ramp that climbs toward ``rise_toward``.

    Five half-spaces (spec 2.6): the bottom, the two planes parallel to the
    rise axis, the vertical end wall on the high side, and the slope itself,
    which runs from the low side's bottom edge to the high side's top edge.
    The low end has no vertical face.  The slope's triple is oriented by the
    numeric check like every other, never by a per-direction point order.
    """
    heading = Facing.of(rise_toward)
    palette = (
        materials
        if isinstance(materials, FaceMaterials)
        else FaceMaterials.uniform(materials)
    )
    high_side = heading.side
    low_side = high_side.opposite
    rise_axis = heading.axis
    cross_axis = heading.cross_axis

    faces = [
        _faced(_face_triple(box, Side.BOTTOM), Side.BOTTOM.inward, palette.on(Side.BOTTOM)),
        _faced(_face_triple(box, high_side), high_side.inward, palette.on(high_side)),
    ]
    for flank in (side for side in Side if side.axis is cross_axis):
        faces.append(_faced(_face_triple(box, flank), flank.inward, palette.on(flank)))

    # The slope: it contains the low end's bottom edge and the high end's top
    # edge.  Its inward normal is (sign * dz) along the rise axis and -run on
    # Z, which is spec 2.6's table written once instead of four times.
    run = box.extent(rise_axis)
    climb = box.extent(Axis.Z)
    slope_normal = [0.0, 0.0, 0.0]
    slope_normal[rise_axis.index] = heading.sign * climb
    slope_normal[Axis.Z.index] = -run
    inward = Point(*slope_normal)

    low_edge_z, high_edge_z = box.mins.z, box.maxs.z
    cross_lo, cross_hi = box.mins[cross_axis.index], box.maxs[cross_axis.index]

    def slope_point(at_high_end: bool, cross: float) -> Point:
        parts = [0.0, 0.0, 0.0]
        parts[rise_axis.index] = box.face_plane(high_side if at_high_end else low_side)
        parts[cross_axis.index] = cross
        parts[Axis.Z.index] = high_edge_z if at_high_end else low_edge_z
        return Point(*parts)

    slope = (
        slope_point(False, cross_lo),
        slope_point(False, cross_hi),
        slope_point(True, cross_lo),
    )
    faces.append(_faced(slope, inward, palette.on(Side.TOP)))
    return Solid(tuple(faces), tuple(contents), note)


def flight(
    base: Point,
    count: int,
    depth: float,
    height: float,
    width: float,
    toward: Facing | Side | str,
) -> list[Span]:
    """``count`` full-depth stair columns climbing from ``base`` (spec 2.5).

    Step ``i`` occupies the along-axis slice ``i*depth .. (i+1)*depth``
    measured from ``base`` in the ascending direction, the full ``width``
    across, and Z from the base up to ``base.z + (i+1)*height``.  Each step is
    a column down to the base, so the flight is solid underneath and no two
    steps overlap -- the reference's cumulative boxes are exactly what the
    overlap scan of 2.8 step 7 flags.
    """
    heading = Facing.of(toward)
    if count < 1:
        raise InvalidBounds(f"a flight needs at least one step, got {count}")
    for label, value in (("depth", depth), ("height", height), ("width", width)):
        if value <= 0.0:
            raise InvalidBounds(f"step {label} must be positive, got {value}")

    rise_axis = heading.axis
    cross_axis = heading.cross_axis
    origin = Point.of(base)
    steps: list[Span] = []
    for index in range(count):
        near = origin[rise_axis.index] + heading.sign * depth * index
        far = origin[rise_axis.index] + heading.sign * depth * (index + 1)
        low = [0.0, 0.0, 0.0]
        high = [0.0, 0.0, 0.0]
        low[rise_axis.index], high[rise_axis.index] = min(near, far), max(near, far)
        low[cross_axis.index] = origin[cross_axis.index]
        high[cross_axis.index] = origin[cross_axis.index] + width
        low[Axis.Z.index] = origin.z
        high[Axis.Z.index] = origin.z + height * (index + 1)
        steps.append(Span.between(Point(*low), Point(*high)))
    return steps


def stair_clip(
    base: Point,
    count: int,
    depth: float,
    height: float,
    width: float,
    toward: Facing | Side | str,
) -> Span | None:
    """The box a smooth clip ramp fills over the flight :func:`flight` builds.

    WHY A FLIGHT NEEDS ONE.  Every staircase in Treyarch's own zombies source
    is a run of tread *models* -- which carry no collision at all -- under a
    single sloped clip brush that is the only thing anything stands on.
    ``_prefabs/zm/zm_giant/geo/zm_giant_zone_c_stairs_2.map`` is 23 tread
    prefabs 8 units apart in Z and 10 in Y, and one ``metal_clip_nosight``
    wedge whose sloped face runs the flight's whole 220 by 176; its sister
    flight ``..._stairs_1.map`` is the same shape in ``metal_clip``.  So the
    surface a zombie's capsule slides along on a shipped map is a plane, and
    the drawn steps are scenery.  A flight of bare brush treads has no such
    plane: the walker meets a vertical riser at every tread.  The navmesh is
    no help in spotting that -- measured on the mod tools install,
    ``cod2map64 -navmesh`` simplifies a 17-tread brush flight from this
    generator into one nav face climbing 34.8 to 279.9, and the mesh is joined at both
    ends -- so the mesh says "walk here" over geometry that is a staircase of
    walls.  This ramp is what makes the two agree.

    THE PLANE.  One gradient, ``height`` over ``depth``, carried from the
    floor the flight stands on to the top of its last tread.  At the nose of
    tread *i* the ramp is exactly level with that tread and it is above the
    tread everywhere after, so nothing protrudes through it, and the head of
    the flight is flush with the last tread rather than standing a half-rise
    proud of it, which is where Treyarch's own through-the-middle-of-each-
    tread plane leaves a flight.

    WHY IT STARTS ONE TREAD *BEFORE* THE FLIGHT.  Run the plane from the top
    of the first tread instead and the ramp's leading edge is a
    ``height``-unit wall standing on the floor.  Measured on the mod tools install:
    built that way, ``cod2map64 -navmesh`` laid no edge at all
    between the balcony floor at z 288 and the upper flight's ramp at z 304 --
    a 16-unit rise, inside the generator's own 18-unit ``maxStepHeight`` --
    and the whole top of the map came out of the compile as a second,
    unreachable mesh component of 78 faces.  Extending the ramp back by one
    tread brings its low edge down to the floor the flight stands on, so
    there is no edge to bridge, and the compile put every storey back in one
    component.  The extension lies flat against the floor in front of the
    flight and is clip, so it is invisible and nothing stands on it that was
    not already standing on the floor.

    Returns ``None`` for a single step: one step is a kerb, not a climb, and a
    ramp over it would be a zero-extent brush.
    """
    heading = Facing.of(toward)
    if count < 1:
        raise InvalidBounds(f"a flight needs at least one step, got {count}")
    for label, value in (("depth", depth), ("height", height), ("width", width)):
        if value <= 0.0:
            raise InvalidBounds(f"step {label} must be positive, got {value}")
    if count < 2:
        return None

    rise_axis = heading.axis
    cross_axis = heading.cross_axis
    origin = Point.of(base)
    # From one tread behind the foot, where the plane meets the floor, to the
    # back of the last tread, where it meets that tread's top.
    near = origin[rise_axis.index] - heading.sign * depth
    far = origin[rise_axis.index] + heading.sign * depth * (count - 1)
    low = [0.0, 0.0, 0.0]
    high = [0.0, 0.0, 0.0]
    low[rise_axis.index], high[rise_axis.index] = min(near, far), max(near, far)
    low[cross_axis.index] = origin[cross_axis.index]
    high[cross_axis.index] = origin[cross_axis.index] + width
    low[Axis.Z.index] = origin.z
    high[Axis.Z.index] = origin.z + height * count
    return Span.between(Point(*low), Point(*high))


#: How tall a gate across the head of a stair flight stands, measured up from the
#: top tread.  A gate is a *blocking* leaf rather than a hole to walk through, so
#: the number that matters is the one a player cannot get over: 96 clears the
#: 72-unit standing player (``Scale_Standards.pdf``) by a step height and more,
#: and it is the height the shipped recipes cut an ordinary doorway at, so a
#: bought gate and a bought door are the same size on screen.
#:
#: It is a *convention*, not a measurement, and an editor that reads the map
#: document has to carry the same constant and the same derivation: that is
#: what lets a stair gate cross between the two as the id of a flight instead
#: of six numbers (see :mod:`zmforge.editordoc`).
STAIR_GATE_HEIGHT = 96.0


def stair_gate(
    base: Point,
    count: int,
    depth: float,
    height: float,
    width: float,
    toward: Facing | Side | str,
    *,
    gate_height: float = STAIR_GATE_HEIGHT,
) -> Span:
    """The box a buyable door fills when it gates the head of a flight.

    A zone stacked over another one is not entered through a hole in a wall --
    there is no wall between two storeys of the same shaft -- but by climbing a
    flight, so the door hangs in the free span across the flight's head.  The
    box is the top tread's own footprint (full width of the flight, one tread
    deep) carried from the top surface up by ``gate_height``: the leaf fills the
    step you would arrive on, so there is no gap to squeeze past on either side,
    and buying it drops the leaf into the flight it stands on.

    The arguments are the flight's, in :func:`flight`'s order, so a recipe that
    can build the stairs can build their gate without repeating any arithmetic.
    """
    if gate_height <= 0.0:
        raise InvalidBounds(f"a stair gate must be taller than nothing, got {gate_height}")
    top = flight(base, count, depth, height, width, toward)[-1]
    return Span.between(
        Point(top.mins.x, top.mins.y, top.maxs.z),
        Point(top.maxs.x, top.maxs.y, top.maxs.z + float(gate_height)),
    )
