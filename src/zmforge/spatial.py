"""World-space primitives shared by every layer.

Conventions (spec section 0.4): world units are inches, Z is up, +Y is north
and +X is east.  A :class:`Span` is always normalised so ``mins <= maxs`` on
every axis.  Angles are ``pitch yaw roll`` in degrees; yaw rotates about Z.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator, Sequence

from .errors import InvalidBounds

__all__ = [
    "Axis",
    "Point",
    "Span",
    "Bounds",
    "Angles",
    "Facing",
    "Side",
    "heading_of",
]


class Axis(Enum):
    """A world axis, carrying its index into a 3-tuple."""

    X = 0
    Y = 1
    Z = 2

    @property
    def index(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class Point:
    """A world position or a direction vector."""

    x: float
    y: float
    z: float

    # -- construction ----------------------------------------------------
    @classmethod
    def of(cls, value: "Point | Sequence[float]") -> "Point":
        if isinstance(value, Point):
            return value
        seq = tuple(value)
        if len(seq) != 3:
            raise ValueError(f"a point needs three numbers, got {len(seq)}")
        return cls(float(seq[0]), float(seq[1]), float(seq[2]))

    # -- access ----------------------------------------------------------
    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y
        yield self.z

    def __getitem__(self, index: int) -> float:
        return (self.x, self.y, self.z)[index]

    def along(self, axis: Axis) -> float:
        return self[axis.index]

    def with_axis(self, axis: Axis, value: float) -> "Point":
        parts = [self.x, self.y, self.z]
        parts[axis.index] = float(value)
        return Point(*parts)

    # -- arithmetic ------------------------------------------------------
    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> "Point":
        return Point(-self.x, -self.y, -self.z)

    def scaled(self, factor: float) -> "Point":
        return Point(self.x * factor, self.y * factor, self.z * factor)

    def dot(self, other: "Point") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Point") -> "Point":
        return Point(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def unit(self) -> "Point":
        norm = self.length()
        if norm == 0.0:
            raise ValueError("cannot normalise a zero-length vector")
        return self.scaled(1.0 / norm)

    def distance_to(self, other: "Point") -> float:
        return (self - other).length()


@dataclass(frozen=True, slots=True)
class Span:
    """An axis-aligned box, normalised per axis on construction.

    ``Span`` is the internal spelling; :data:`Bounds` is the public alias the
    spec's interface uses.  Construction rejects a non-positive extent so a
    zero-thickness brush can never reach the writer; use :meth:`flat_ok` when a
    degenerate box is genuinely wanted (footprints, sampling rectangles).
    """

    mins: Point
    maxs: Point

    def __post_init__(self) -> None:
        low = Point(
            min(self.mins.x, self.maxs.x),
            min(self.mins.y, self.maxs.y),
            min(self.mins.z, self.maxs.z),
        )
        high = Point(
            max(self.mins.x, self.maxs.x),
            max(self.mins.y, self.maxs.y),
            max(self.mins.z, self.maxs.z),
        )
        object.__setattr__(self, "mins", low)
        object.__setattr__(self, "maxs", high)
        for axis in Axis:
            if high[axis.index] - low[axis.index] <= 0.0:
                raise InvalidBounds(
                    f"box has a non-positive extent on {axis.name}: "
                    f"{low[axis.index]} .. {high[axis.index]}"
                )

    # -- construction ----------------------------------------------------
    @classmethod
    def between(
        cls,
        mins: "Point | Sequence[float]",
        maxs: "Point | Sequence[float]",
    ) -> "Span":
        return cls(Point.of(mins), Point.of(maxs))

    @classmethod
    def flat_ok(
        cls,
        mins: "Point | Sequence[float]",
        maxs: "Point | Sequence[float]",
    ) -> "Span":
        """Like :meth:`between` but tolerating zero extents.

        Used for footprints and query rectangles, never for emitted solids.
        """
        obj = cls.__new__(cls)
        low_raw, high_raw = Point.of(mins), Point.of(maxs)
        object.__setattr__(
            obj,
            "mins",
            Point(
                min(low_raw.x, high_raw.x),
                min(low_raw.y, high_raw.y),
                min(low_raw.z, high_raw.z),
            ),
        )
        object.__setattr__(
            obj,
            "maxs",
            Point(
                max(low_raw.x, high_raw.x),
                max(low_raw.y, high_raw.y),
                max(low_raw.z, high_raw.z),
            ),
        )
        return obj

    @classmethod
    def hull_of(cls, boxes: Iterable["Span"]) -> "Span":
        items = list(boxes)
        if not items:
            raise InvalidBounds("cannot take the hull of no boxes")
        low = Point(
            min(b.mins.x for b in items),
            min(b.mins.y for b in items),
            min(b.mins.z for b in items),
        )
        high = Point(
            max(b.maxs.x for b in items),
            max(b.maxs.y for b in items),
            max(b.maxs.z for b in items),
        )
        return cls.flat_ok(low, high)

    # -- measurement -----------------------------------------------------
    @property
    def size(self) -> Point:
        return self.maxs - self.mins

    @property
    def centre(self) -> Point:
        return Point(
            (self.mins.x + self.maxs.x) / 2.0,
            (self.mins.y + self.maxs.y) / 2.0,
            (self.mins.z + self.maxs.z) / 2.0,
        )

    def extent(self, axis: Axis) -> float:
        return self.maxs[axis.index] - self.mins[axis.index]

    @property
    def volume(self) -> float:
        return self.extent(Axis.X) * self.extent(Axis.Y) * self.extent(Axis.Z)

    def corners(self) -> tuple[Point, ...]:
        return tuple(
            Point(x, y, z)
            for x in (self.mins.x, self.maxs.x)
            for y in (self.mins.y, self.maxs.y)
            for z in (self.mins.z, self.maxs.z)
        )

    def face_plane(self, side: "Side") -> float:
        """The coordinate of the given face along its own axis."""
        low = side.sign < 0
        return (self.mins if low else self.maxs)[side.axis.index]

    # -- relations -------------------------------------------------------
    def holds(self, point: Point, tolerance: float = 0.0) -> bool:
        return all(
            self.mins[i] - tolerance <= point[i] <= self.maxs[i] + tolerance
            for i in range(3)
        )

    def holds_flat(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        return (
            self.mins.x - tolerance <= x <= self.maxs.x + tolerance
            and self.mins.y - tolerance <= y <= self.maxs.y + tolerance
        )

    def overlaps(self, other: "Span", slack: float = 0.0) -> bool:
        """True when the two boxes share interior volume beyond ``slack``."""
        return all(
            min(self.maxs[i], other.maxs[i]) - max(self.mins[i], other.mins[i]) > slack
            for i in range(3)
        )

    def encloses(self, other: "Span", tolerance: float = 0.0) -> bool:
        return all(
            self.mins[i] - tolerance <= other.mins[i]
            and other.maxs[i] <= self.maxs[i] + tolerance
            for i in range(3)
        )

    # -- derivation ------------------------------------------------------
    def grown(self, by: float) -> "Span":
        delta = Point(by, by, by)
        return Span.flat_ok(self.mins - delta, self.maxs + delta)

    def shrunk(self, by: float) -> "Span":
        return self.grown(-by)

    def grown_on(self, axis: Axis, by: float) -> "Span":
        low = self.mins.with_axis(axis, self.mins[axis.index] - by)
        high = self.maxs.with_axis(axis, self.maxs[axis.index] + by)
        return Span.flat_ok(low, high)

    def slice_on(self, axis: Axis, low: float, high: float) -> "Span":
        return Span.between(
            self.mins.with_axis(axis, low), self.maxs.with_axis(axis, high)
        )

    def moved(self, delta: Point) -> "Span":
        return Span.flat_ok(self.mins + delta, self.maxs + delta)

    def as_tuples(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return ((self.mins.x, self.mins.y, self.mins.z), (self.maxs.x, self.maxs.y, self.maxs.z))


#: Public alias used by the interface of spec section 8.3.
Bounds = Span


@dataclass(frozen=True, slots=True)
class Angles:
    """Euler angles in degrees, ``pitch yaw roll`` order."""

    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0

    @classmethod
    def facing_yaw(cls, yaw: float) -> "Angles":
        return cls(0.0, float(yaw), 0.0)

    def turned(self, by: float) -> "Angles":
        return Angles(self.pitch, (self.yaw + by) % 360.0, self.roll)

    def __iter__(self) -> Iterator[float]:
        yield self.pitch
        yield self.yaw
        yield self.roll


class Side(Enum):
    """One of the six faces of an axis-aligned box.

    The value is ``(axis, sign)``: the sign says which end of that axis the
    face sits on, and the outward normal is the axis unit vector times the
    sign.
    """

    WEST = (Axis.X, -1)
    EAST = (Axis.X, +1)
    SOUTH = (Axis.Y, -1)
    NORTH = (Axis.Y, +1)
    BOTTOM = (Axis.Z, -1)
    TOP = (Axis.Z, +1)

    @property
    def axis(self) -> Axis:
        return self.value[0]

    @property
    def sign(self) -> int:
        return self.value[1]

    @property
    def outward(self) -> Point:
        step = [0.0, 0.0, 0.0]
        step[self.axis.index] = float(self.sign)
        return Point(*step)

    @property
    def inward(self) -> Point:
        return -self.outward

    @property
    def opposite(self) -> "Side":
        return _OPPOSITE_SIDE[self]

    @property
    def is_horizontal(self) -> bool:
        return self.axis is not Axis.Z


_OPPOSITE_SIDE = {
    Side.WEST: Side.EAST,
    Side.EAST: Side.WEST,
    Side.SOUTH: Side.NORTH,
    Side.NORTH: Side.SOUTH,
    Side.BOTTOM: Side.TOP,
    Side.TOP: Side.BOTTOM,
}


class Facing(Enum):
    """A compass heading.  Callers say "facing north", never a raw yaw.

    ``yaw`` here is the world heading of the direction itself: +Y (north) is
    90, +X (east) is 0, matching the usual ``atan2(y, x)`` reading.  Prefab
    yaws are *not* this number; the blueprint holds one table per prefab
    family that converts a heading into the yaw that asset wants, because the
    assets disagree about which way they face at yaw 0 (spec appendix B).
    """

    EAST = "east"
    NORTH = "north"
    WEST = "west"
    SOUTH = "south"

    @property
    def side(self) -> Side:
        return _FACING_SIDE[self]

    @property
    def step(self) -> Point:
        """Unit vector pointing the way this heading faces."""
        return self.side.outward

    @property
    def axis(self) -> Axis:
        return self.side.axis

    @property
    def sign(self) -> int:
        return self.side.sign

    @property
    def opposite(self) -> "Facing":
        return _OPPOSITE_FACING[self]

    @property
    def cross_axis(self) -> Axis:
        """The horizontal axis this heading does *not* run along."""
        return Axis.Y if self.axis is Axis.X else Axis.X

    @property
    def world_yaw(self) -> float:
        return {Facing.EAST: 0.0, Facing.NORTH: 90.0, Facing.WEST: 180.0, Facing.SOUTH: 270.0}[self]

    @classmethod
    def of(cls, value: "Facing | Side | str") -> "Facing":
        if isinstance(value, Facing):
            return value
        if isinstance(value, Side):
            if not value.is_horizontal:
                raise ValueError(f"{value.name} is not a compass heading")
            return _SIDE_FACING[value]
        text = str(value).strip().lower()
        for member in cls:
            if member.value == text:
                return member
        raise ValueError(f"unknown facing {value!r}; expected north/south/east/west")


_FACING_SIDE = {
    Facing.EAST: Side.EAST,
    Facing.NORTH: Side.NORTH,
    Facing.WEST: Side.WEST,
    Facing.SOUTH: Side.SOUTH,
}
_SIDE_FACING = {side: facing for facing, side in _FACING_SIDE.items()}
_OPPOSITE_FACING = {
    Facing.EAST: Facing.WEST,
    Facing.WEST: Facing.EAST,
    Facing.NORTH: Facing.SOUTH,
    Facing.SOUTH: Facing.NORTH,
}


def heading_of(value: "Facing | Side | str | Angles | float") -> Angles:
    """Coerce a caller's heading argument into :class:`Angles`.

    Accepts a :class:`Facing`, a compass string, an explicit :class:`Angles`,
    or a bare yaw in degrees.  This is the only place a raw number becomes an
    orientation, so prefab tables can stay in one spot.
    """
    if isinstance(value, Angles):
        return value
    if isinstance(value, (int, float)):
        return Angles.facing_yaw(float(value))
    return Angles.facing_yaw(Facing.of(value).world_yaw)
