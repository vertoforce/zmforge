"""Decomposing rooms, walls, yards and the sky cage into non-overlapping boxes.

Everything here is pure box arithmetic: it answers "which boxes make up this
shell?" and never decides what material goes on them (:mod:`..blueprint`
does that) nor how they are written (:mod:`..emit` does that).

The one rule that is easy to get wrong and expensive to get wrong is in
:func:`yard_shell`: the two walls flanking a yard's open side run **to the
open edge**, not to ``open edge - thickness``.  Stopping short leaves a
``t x t`` vertical slot at each corner that opens the yard into the void, and
a flood fill escapes through it (spec 2.7, item K11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..errors import InvalidBounds, OpeningDoesNotFit
from ..spatial import Axis, Point, Side, Span

__all__ = [
    "Aperture",
    "ShellPiece",
    "RoomShell",
    "SkyCage",
    "room_shell",
    "yard_shell",
    "aperture_box",
    "wall_remainder",
    "sky_cage",
]


@dataclass(frozen=True, slots=True)
class Aperture:
    """A hole a caller wants cut in one wall of a room.

    ``width`` runs along the wall, ``height`` up Z, ``offset`` slides the hole
    along the wall from the wall's midpoint, and ``sill`` lifts its bottom
    above the **interior floor surface** (0 is a doorway, >0 a window).
    """

    side: Side
    width: float
    height: float
    sill: float = 0.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        if not self.side.is_horizontal:
            raise OpeningDoesNotFit(
                "an opening goes in a wall; "
                f"{self.side.name.lower()} is the floor or the ceiling"
            )
        if self.width <= 0.0 or self.height <= 0.0:
            raise OpeningDoesNotFit(
                f"an opening must have positive width and height, got "
                f"{self.width} x {self.height}"
            )
        if self.sill < 0.0:
            raise OpeningDoesNotFit(
                f"sill height is measured up from the floor surface and cannot "
                f"be negative, got {self.sill}"
            )

    @property
    def along_axis(self) -> Axis:
        """The horizontal axis the opening's width runs along."""
        return Axis.Y if self.side.axis is Axis.X else Axis.X


@dataclass(frozen=True, slots=True)
class ShellPiece:
    """One box of a decomposed shell, tagged with the side it belongs to.

    ``side`` is which part of the shell this is (``BOTTOM`` for the floor
    slab, ``NORTH`` for the north wall, and so on), which is what lets the
    material rule of spec 2.2 pick the one face that looks into the room.
    ``aperture`` is true for the jamb/sill/lintel pieces around a hole, which
    are visible on all six faces instead.
    """

    box: Span
    side: Side
    aperture: bool = False


@dataclass(frozen=True, slots=True)
class RoomShell:
    """The boxes that make a room (or a yard) and the void they leave."""

    outer: Span
    interior: Span
    thickness: float
    roofed: bool
    pieces: tuple[ShellPiece, ...] = ()

    @property
    def floor_surface_z(self) -> float:
        """World Z a player stands on: the top of the floor slab."""
        return self.outer.mins.z + self.thickness

    @property
    def ceiling_underside_z(self) -> float:
        return self.outer.maxs.z - (self.thickness if self.roofed else 0.0)

    def boxes(self) -> list[Span]:
        return [piece.box for piece in self.pieces]

    def of_side(self, side: Side) -> list[ShellPiece]:
        return [piece for piece in self.pieces if piece.side is side]


@dataclass(frozen=True, slots=True)
class SkyCage:
    """Six sky slabs, the inner void they wrap, and the outer hull."""

    playable: Span
    inner: Span
    outer: Span
    slabs: tuple[ShellPiece, ...] = ()

    def boxes(self) -> list[Span]:
        return [slab.box for slab in self.slabs]


# --------------------------------------------------------------------------
# Rooms
# --------------------------------------------------------------------------
def _interior_of(outer: Span, thickness: float, roofed: bool) -> Span:
    top = outer.maxs.z - thickness if roofed else outer.maxs.z
    return Span.between(
        Point(
            outer.mins.x + thickness,
            outer.mins.y + thickness,
            outer.mins.z + thickness,
        ),
        Point(outer.maxs.x - thickness, outer.maxs.y - thickness, top),
    )


def _check_thickness(outer: Span, thickness: float, roofed: bool) -> None:
    if thickness <= 0.0:
        raise InvalidBounds(f"wall thickness must be positive, got {thickness}")
    for axis in (Axis.X, Axis.Y):
        if outer.extent(axis) <= 2.0 * thickness:
            raise InvalidBounds(
                f"a room {outer.extent(axis)} units across on {axis.name} has no "
                f"interior left after two {thickness}-unit walls"
            )
    height_walls = 2.0 * thickness if roofed else thickness
    if outer.extent(Axis.Z) <= height_walls:
        raise InvalidBounds(
            f"a room {outer.extent(Axis.Z)} units tall has no interior left after "
            f"a floor{' and a ceiling' if roofed else ''} {thickness} thick"
        )


def room_shell(
    outer: Span, thickness: float = 16.0, *, roofed: bool = True,
    wall_height: float | None = None,
) -> RoomShell:
    """Six (or five) non-overlapping boxes whose union is the shell (spec 2.2).

    Floor and ceiling span the full footprint; the south and north walls span
    the full X extent between them; the west and east walls are inset by
    ``thickness`` in Y so they butt against the other pair without overlapping
    it.  With ``roofed=False`` the ceiling is dropped and the four walls run up
    to the top of ``outer``.

    ``wall_height`` (open rooms only) stops the four walls that far above the
    bottom of ``outer`` instead: a garden or cemetery wall a player sees over,
    with the sky and whatever stands beyond it above.  The interior keeps the
    full height; what keeps a player in above the wall is the caller's (see
    :meth:`zmforge.blueprint.model.Blueprint.add_room`, which caps it in clip).
    """
    _check_thickness(outer, thickness, roofed)
    if wall_height is not None:
        if roofed:
            raise InvalidBounds("wall_height is for a room open to the sky (roofed=False)")
        if not thickness < wall_height < outer.extent(Axis.Z):
            raise InvalidBounds(
                f"wall_height {wall_height} must be above the floor slab ({thickness}) "
                f"and below the room's top ({outer.extent(Axis.Z)})")
    interior = _interior_of(outer, thickness, roofed)
    x0, y0, z0 = outer.mins.x, outer.mins.y, outer.mins.z
    x1, y1, z1 = outer.maxs.x, outer.maxs.y, outer.maxs.z
    wall_top = z1 - thickness if roofed else z1
    if wall_height is not None:
        wall_top = z0 + wall_height

    pieces = [
        ShellPiece(
            Span.between(Point(x0, y0, z0), Point(x1, y1, z0 + thickness)), Side.BOTTOM
        )
    ]
    if roofed:
        pieces.append(
            ShellPiece(
                Span.between(Point(x0, y0, z1 - thickness), Point(x1, y1, z1)),
                Side.TOP,
            )
        )
    pieces.extend(
        (
            ShellPiece(
                Span.between(
                    Point(x0, y0, z0 + thickness), Point(x1, y0 + thickness, wall_top)
                ),
                Side.SOUTH,
            ),
            ShellPiece(
                Span.between(
                    Point(x0, y1 - thickness, z0 + thickness), Point(x1, y1, wall_top)
                ),
                Side.NORTH,
            ),
            ShellPiece(
                Span.between(
                    Point(x0, y0 + thickness, z0 + thickness),
                    Point(x0 + thickness, y1 - thickness, wall_top),
                ),
                Side.WEST,
            ),
            ShellPiece(
                Span.between(
                    Point(x1 - thickness, y0 + thickness, z0 + thickness),
                    Point(x1, y1 - thickness, wall_top),
                ),
                Side.EAST,
            ),
        )
    )
    return RoomShell(outer, interior, thickness, roofed, tuple(pieces))


def yard_shell(outer: Span, attached: Side, thickness: float = 16.0) -> RoomShell:
    """A five-sided pocket, open on ``attached`` (spec 2.7).

    Floor and ceiling cover the whole footprint.  The wall opposite the open
    side spans the full footprint on its axis.  The two flanking walls run
    **all the way to the open edge** -- item K11: stopping ``thickness`` short
    leaves a corner slot the flood fill escapes through.
    """
    if not attached.is_horizontal:
        raise InvalidBounds("a yard opens onto a wall, not onto the floor or ceiling")
    _check_thickness(outer, thickness, roofed=True)
    interior = _interior_of(outer, thickness, roofed=True)
    x0, y0, z0 = outer.mins.x, outer.mins.y, outer.mins.z
    x1, y1, z1 = outer.maxs.x, outer.maxs.y, outer.maxs.z
    wall_top = z1 - thickness

    pieces = [
        ShellPiece(
            Span.between(Point(x0, y0, z0), Point(x1, y1, z0 + thickness)), Side.BOTTOM
        ),
        ShellPiece(
            Span.between(Point(x0, y0, z1 - thickness), Point(x1, y1, z1)), Side.TOP
        ),
    ]

    closed = attached.opposite
    open_axis = attached.axis
    # The far wall: full footprint on the axis it does not span.
    far_low = Point(x0, y0, z0 + thickness)
    far_high = Point(x1, y1, wall_top)
    if closed.sign < 0:
        far_high = far_high.with_axis(
            open_axis, outer.mins[open_axis.index] + thickness
        )
    else:
        far_low = far_low.with_axis(open_axis, outer.maxs[open_axis.index] - thickness)
    pieces.append(ShellPiece(Span.between(far_low, far_high), closed))

    # The two flanking walls, running from the far wall's inner face to the
    # open edge.
    flank_axis = Axis.Y if open_axis is Axis.X else Axis.X
    if closed.sign < 0:
        run_low = outer.mins[open_axis.index] + thickness
        run_high = outer.maxs[open_axis.index]
    else:
        run_low = outer.mins[open_axis.index]
        run_high = outer.maxs[open_axis.index] - thickness
    for flank in (side for side in Side if side.axis is flank_axis):
        low = Point(x0, y0, z0 + thickness).with_axis(open_axis, run_low)
        high = Point(x1, y1, wall_top).with_axis(open_axis, run_high)
        if flank.sign < 0:
            high = high.with_axis(
                flank_axis, outer.mins[flank_axis.index] + thickness
            )
        else:
            low = low.with_axis(flank_axis, outer.maxs[flank_axis.index] - thickness)
        pieces.append(ShellPiece(Span.between(low, high), flank))

    return RoomShell(outer, interior, thickness, True, tuple(pieces))


# --------------------------------------------------------------------------
# Openings
# --------------------------------------------------------------------------
def aperture_box(shell: RoomShell, aperture: Aperture, thickness: float) -> Span:
    """Where in world space a hole sits, validated against its wall (spec 2.3).

    The box spans the wall's full thickness, so it can be subtracted from the
    wall pieces and later thickened into a door leaf without a second
    calculation.
    """
    side = aperture.side
    along = aperture.along_axis
    wall_pieces = shell.of_side(side)
    if not wall_pieces:
        raise OpeningDoesNotFit(
            f"this shell has no {side.name.lower()} wall to cut an opening in"
        )
    wall = wall_pieces[0].box

    floor_z = shell.floor_surface_z
    bottom = floor_z + aperture.sill
    top = bottom + aperture.height
    wall_height = wall.maxs.z - floor_z
    if aperture.sill + aperture.height > wall_height + 1e-9:
        raise OpeningDoesNotFit(
            f"an opening {aperture.height} tall at sill {aperture.sill} needs "
            f"{aperture.sill + aperture.height} units of wall, but the "
            f"{side.name.lower()} wall is only {wall_height} tall above the floor"
        )

    wall_low = wall.mins[along.index]
    wall_high = wall.maxs[along.index]
    span_length = wall_high - wall_low
    if aperture.width > span_length + 1e-9:
        raise OpeningDoesNotFit(
            f"an opening {aperture.width} wide does not fit a "
            f"{side.name.lower()} wall {span_length} long"
        )
    midpoint = (wall_low + wall_high) / 2.0 + aperture.offset
    low = midpoint - aperture.width / 2.0
    high = midpoint + aperture.width / 2.0
    if low < wall_low - 1e-9 or high > wall_high + 1e-9:
        raise OpeningDoesNotFit(
            f"an opening {aperture.width} wide at offset {aperture.offset} runs "
            f"from {low} to {high}, outside the {side.name.lower()} wall's "
            f"{wall_low}..{wall_high}"
        )

    across = side.axis
    mins = Point(0.0, 0.0, bottom)
    maxs = Point(0.0, 0.0, top)
    mins = mins.with_axis(along, low).with_axis(across, wall.mins[across.index])
    maxs = maxs.with_axis(along, high).with_axis(across, wall.maxs[across.index])
    return Span.between(mins, maxs)


def wall_remainder(wall: Span, holes: Sequence[Span], along: Axis) -> list[Span]:
    """The wall minus its holes, as non-overlapping boxes (spec 2.3).

    A sweep along ``along`` with the holes sorted by their low edge: a
    full-height fill before the first hole, a strip below and a strip above
    each hole spanning exactly its along-wall range, a full-height fill between
    consecutive holes, and a fill after the last.  Pieces with a non-positive
    extent are dropped.  Overlapping holes are a caller error.
    """
    ordered = sorted(holes, key=lambda hole: hole.mins[along.index])
    for earlier, later in zip(ordered, ordered[1:]):
        if later.mins[along.index] < earlier.maxs[along.index] - 1e-9:
            raise OpeningDoesNotFit(
                "two openings on the same wall overlap between "
                f"{later.mins[along.index]} and {earlier.maxs[along.index]}"
            )

    pieces: list[Span] = []

    def keep(low: Point, high: Point) -> None:
        for axis in Axis:
            if high[axis.index] - low[axis.index] <= 1e-9:
                return
        pieces.append(Span.between(low, high))

    cursor = wall.mins[along.index]
    for hole in ordered:
        hole_low = hole.mins[along.index]
        hole_high = hole.maxs[along.index]
        keep(
            wall.mins.with_axis(along, cursor),
            wall.maxs.with_axis(along, hole_low),
        )
        strip_low = wall.mins.with_axis(along, hole_low)
        strip_high = wall.maxs.with_axis(along, hole_high)
        keep(strip_low, strip_high.with_axis(Axis.Z, hole.mins.z))
        keep(strip_low.with_axis(Axis.Z, hole.maxs.z), strip_high)
        cursor = max(cursor, hole_high)
    keep(wall.mins.with_axis(along, cursor), wall.maxs)
    return pieces


# --------------------------------------------------------------------------
# The sky shell
# --------------------------------------------------------------------------
def sky_cage(playable: Span, gap: float = 128.0, thickness: float = 32.0) -> SkyCage:
    """Six ``sky`` slabs around the playable bounds (spec 2.7).

    The gap has to clear anything a prefab places outside a wall -- a barricade
    reaches about 50 units past it -- and the slabs must not overlap, because
    an overlap is exactly what the structural-overlap scan flags.
    """
    if gap <= 0.0 or thickness <= 0.0:
        raise InvalidBounds(
            f"the sky shell needs a positive gap and thickness, got {gap} and {thickness}"
        )
    inner = playable.grown(gap)
    outer = inner.grown(thickness)
    i0, i1 = inner.mins, inner.maxs
    o0, o1 = outer.mins, outer.maxs

    slabs = (
        ShellPiece(Span.between(o0, Point(o1.x, o1.y, i0.z)), Side.BOTTOM),
        ShellPiece(Span.between(Point(o0.x, o0.y, i1.z), o1), Side.TOP),
        ShellPiece(
            Span.between(Point(o0.x, o0.y, i0.z), Point(o1.x, i0.y, i1.z)), Side.SOUTH
        ),
        ShellPiece(
            Span.between(Point(o0.x, i1.y, i0.z), Point(o1.x, o1.y, i1.z)), Side.NORTH
        ),
        ShellPiece(
            Span.between(Point(o0.x, i0.y, i0.z), Point(i0.x, i1.y, i1.z)), Side.WEST
        ),
        ShellPiece(
            Span.between(Point(i1.x, i0.y, i0.z), Point(o1.x, i1.y, i1.z)), Side.EAST
        ),
    )
    return SkyCage(playable, inner, outer, slabs)
