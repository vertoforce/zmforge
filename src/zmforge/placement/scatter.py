"""Scatter: points made by generators, moved by modifiers, cut by negatives.

The placer this package replaces decides a prop's position and a prop's
exclusions in the same breath, and that is why its exclusions are incomplete.
Doorways are avoided because :func:`~zmforge.recipes.props.furnish` knows
about doorways; the front of a Quick Revive is not, so 34 props stand inside
an interactive item's own footprint, 17 of them solid.  27 solid props stand
within 96 units of a zombie riser.  A row of props can run through the
player spawn.  Each of those is a keep-out the placer was never told about,
and each fix made one at a time is "teach the placer about one more thing".

This module is the other arrangement, taken from ProtonScatter
(HungryProton/scatter, MIT, GDScript): a *stack*.  Generators
make points, modifiers move or drop them, and a shape marked negative is a
piece of data in the same stack rather than a branch in the placer.  A doorway,
a stair well, a spawn cluster and the apron in front of a buy are then the same
kind of thing -- a :class:`KeepClear` with a reason -- and the placer has no
opinion about any of them.  The reason is carried so that a run can say *four
candidates went to "riser"* instead of *four candidates went missing*.

The stack also keeps wall rows apart.  Wall rows that run into each other
and into the fill leave solid props inside one another (a desk 72% inside a
bench, a chair 98% inside a plant), so a wall row ends one footprint short of
the corner and two perpendicular rows cannot meet.  :class:`AlongWall` does that by construction, with
:data:`CORNER_SETBACK`, rather than by rejecting the pieces afterwards.

Everything here is deterministic.  Not "seeded" -- deterministic: there is no
random stream in this module at all, every number comes from
:func:`~zmforge.placement.geometry.unit_hash` of the seed text plus the
candidate's own identity, so adding a scene to one room cannot move a prop in
another, and the same blueprint builds the same map on any machine.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .geometry import EPSILON, Poly2, Vec2, unit_hash
from .relations import Wall, walls_of_rect

__all__ = [
    "Candidate",
    "Context",
    "KeepClear",
    "Negatives",
    "PointGenerator",
    "Modifier",
    "AlongWall",
    "UniformFill",
    "Clusters",
    "Rows",
    "Jitter",
    "FaceTarget",
    "FaceWall",
    "FaceAway",
    "SnapToSurface",
    "Report",
    "Stack",
    "StackResult",
    "CORNER_SETBACK",
    "WALL_BAND",
    "DOOR_KEEP_OUT",
    "INTERACTIVE_APRON",
    "RISER_KEEP_OUT",
    "YAW_WANDER",
]

#: How far short of the corner a wall row stops, in units: a wall row ends one
#: footprint short of the room corner, so two perpendicular rows cannot meet
#: there.  One footprint is 48 here because 48 is the deepest piece of
#: furniture in this palette standing with its back on a wall, which is the
#: same measurement :data:`zmforge.recipes.props.EDGE_BAND` is cut from.
CORNER_SETBACK = 48.0

#: How deep the band along a wall is, in units.  Same measurement, same
#: reason: a band this deep holds the deepest wall-backed piece in the palette.
#: Copied rather than imported, because this package declares no dependency on
#: :mod:`zmforge.recipes`.
WALL_BAND = 48.0

#: How far a keep-clear zone reaches past the face of a door leaf, in units.
#: The keep-out reaches 48 units out on both faces of the leaf, and it is
#: enforced by rejecting a candidate there rather than by removing its
#: collision.  Measured on a test map without it, 24 shelving units hid doors.
DOOR_KEEP_OUT = 48.0

#: How far in front of an interactive item nothing may stand, in units.
#: Each item's footprint plus a 48-unit apron is reserved as a keep-out
#: polygon before any scene runs.  Without it, 34 props stood inside an
#: interactive footprint on a test map and 3 more inside the apron.
INTERACTIVE_APRON = 48.0

#: The radius of the keep-out disc around a zombie riser or a player spawn, in
#: units.  Without it, 27 solid props stood within 96 units of a riser on a
#: test map, so the spawn cluster gets a 96-unit keep-out disc.
RISER_KEEP_OUT = 96.0

#: How far a jittered candidate's heading may wander, in degrees, when a
#: caller does not say.  12 degrees is what loose furniture gets in the
#: current placer (``FILL_WANDER``): enough to read as placed by hand, and
#: nothing in a fill depends on lining up with its neighbour.
YAW_WANDER = 12.0


# --------------------------------------------------------------------------
# The point
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Candidate:
    """One place something could go, and what the stack has decided about it.

    A candidate is not a prop.  It is a position, a heading and a slot for
    each thing a modifier works out: the height :class:`SnapToSurface` looks
    up, the plan half extents a caller fills in once it knows which model it
    is about to put here.  Half extents of zero mean "a point", and a point is
    tested against a negative shape by containment rather than by overlap,
    which is the right test before a model has been chosen.

    ``source`` is the generator that made it and ``tag`` is that generator's
    own label for it (a wall side, a cluster number).  Both are hash inputs,
    so two generators over the same rectangle do not produce the same jitter.
    """

    x: float
    y: float
    yaw: float = 0.0
    z: float = 0.0
    height: float = 0.0
    hx: float = 0.0
    hy: float = 0.0
    index: int = 0
    tag: str = ""
    source: str = ""

    @property
    def point(self) -> Vec2:
        return (self.x, self.y)

    @property
    def footprint(self) -> Poly2:
        """The oriented box this candidate would occupy, zero-area for a point."""
        return Poly2.box(self.x, self.y, self.hx, self.hy, self.yaw)

    @property
    def plan(self) -> Poly2 | Vec2:
        """What a negative shape should test: a footprint if there is one."""
        if self.hx > EPSILON and self.hy > EPSILON:
            return self.footprint
        return self.point

    @property
    def z_low(self) -> float:
        return self.z

    @property
    def z_high(self) -> float:
        return self.z + self.height

    def moved_to(self, x: float, y: float) -> "Candidate":
        return Candidate(x, y, self.yaw, self.z, self.height, self.hx, self.hy,
                         self.index, self.tag, self.source)

    def turned_to(self, yaw: float) -> "Candidate":
        return Candidate(self.x, self.y, _wrap(yaw), self.z, self.height,
                         self.hx, self.hy, self.index, self.tag, self.source)

    def raised_to(self, z: float) -> "Candidate":
        return Candidate(self.x, self.y, self.yaw, z, self.height, self.hx,
                         self.hy, self.index, self.tag, self.source)

    def sized(self, hx: float, hy: float, height: float = 0.0) -> "Candidate":
        """The same place, now known to be big enough to hold a given model."""
        return Candidate(self.x, self.y, self.yaw, self.z, height, hx, hy,
                         self.index, self.tag, self.source)

    def key(self, salt: str) -> tuple[str, str, int, str]:
        """This candidate's identity as hash input, plus a per-use salt."""
        return (self.source, self.tag, self.index, salt)


def _wrap(degrees: float) -> float:
    """A heading folded into ``(-180, 180]``, so two equal headings compare equal."""
    turned = math.fmod(degrees, 360.0)
    if turned <= -180.0:
        turned += 360.0
    elif turned > 180.0:
        turned -= 360.0
    return turned + 0.0  # normalise -0.0, which compares equal but prints wrong


# --------------------------------------------------------------------------
# Negative shapes
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class KeepClear:
    """A polygon nothing may be placed in, and why.

    The reason is the point of the class.  ProtonScatter marks a shape
    negative and that is all it needs; we need to answer "where did the eight
    props that should be in this room go", and a run that can only say "eight
    were dropped" is a run nobody will trust enough to raise a count.

    The height band is optional and usually absent.  A doorway is clear at
    every height; the space under a low pipe run is clear only between two
    numbers, and a sign hung at 100 does not care about a keep-out that ends
    at 40.  ``None`` at either end means unbounded, and a subject with no band
    is blocked by any zone, because an unknown height is not a safe height.
    """

    poly: Poly2
    reason: str
    z_low: float | None = None
    z_high: float | None = None

    @classmethod
    def rect(
        cls,
        reason: str,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        z_low: float | None = None,
        z_high: float | None = None,
    ) -> "KeepClear":
        return cls(Poly2.rect(x0, y0, x1, y1), reason, z_low, z_high)

    @classmethod
    def disc(
        cls,
        reason: str,
        x: float,
        y: float,
        radius: float,
        *,
        segments: int = 16,
        z_low: float | None = None,
        z_high: float | None = None,
    ) -> "KeepClear":
        """A ring of ``segments`` points around a centre: a riser, a spawn.

        The polygon is inscribed, so it is very slightly smaller than the
        circle it stands for (1.9% at sixteen segments, the same understatement
        :func:`~zmforge.placement.geometry.minkowski_disc` carries).  A caller
        that needs the disc guaranteed covered asks for a larger radius.
        """
        count = max(3, segments)
        return cls(
            Poly2.of(
                (x + radius * math.cos(2.0 * math.pi * i / count),
                 y + radius * math.sin(2.0 * math.pi * i / count))
                for i in range(count)
            ),
            reason,
            z_low,
            z_high,
        )

    def _band_meets(self, z_low: float | None, z_high: float | None) -> bool:
        if self.z_low is None and self.z_high is None:
            return True
        if z_low is None and z_high is None:
            return True
        low = max(-math.inf if self.z_low is None else self.z_low,
                  -math.inf if z_low is None else z_low)
        high = min(math.inf if self.z_high is None else self.z_high,
                   math.inf if z_high is None else z_high)
        return high - low >= -EPSILON

    def blocks(
        self,
        subject: Poly2 | Vec2,
        *,
        z_low: float | None = None,
        z_high: float | None = None,
    ) -> bool:
        """Is this subject -- a point or a footprint -- inside the zone?

        A footprint is blocked when it shares any floor with the zone, not
        when its centre is inside it.  That difference is the 24 shelving
        units standing beside a door with their bulk across it.
        """
        if not self._band_meets(z_low, z_high):
            return False
        if isinstance(subject, Poly2):
            return self.poly.overlap_area(subject) > EPSILON
        return self.poly.holds(subject)


@dataclass(frozen=True, slots=True)
class Negatives:
    """Every keep-clear zone a stack must respect, in one place.

    A collection rather than a loop at each call site, because the whole claim
    of this module is that a doorway and a buy apron are the same kind of
    thing.  The moment one of them is checked somewhere else, they are not.
    """

    zones: tuple[KeepClear, ...] = ()

    @classmethod
    def of(cls, zones: Iterable[KeepClear]) -> "Negatives":
        return cls(tuple(zones))

    def plus(self, *zones: KeepClear) -> "Negatives":
        return Negatives(self.zones + zones)

    def __len__(self) -> int:
        return len(self.zones)

    def __iter__(self):
        return iter(self.zones)

    def blocks(
        self,
        subject: Poly2 | Vec2,
        *,
        z_low: float | None = None,
        z_high: float | None = None,
    ) -> KeepClear | None:
        """The first zone that blocks this subject, or ``None`` if it is clear.

        Returning the zone rather than a boolean is what lets a report name
        the reason.  It is still the truth test a caller expects:
        ``if negatives.blocks(point): ...``.
        """
        for zone in self.zones:
            if zone.blocks(subject, z_low=z_low, z_high=z_high):
                return zone
        return None

    def reasons(self) -> tuple[str, ...]:
        return tuple(zone.reason for zone in self.zones)


# --------------------------------------------------------------------------
# The two protocols a stack is made of
# --------------------------------------------------------------------------
class PointGenerator(Protocol):
    """Makes candidates out of nothing but a seed text."""

    tag: str

    def generate(self, seed_text: str) -> tuple[Candidate, ...]:
        ...


@dataclass(frozen=True, slots=True)
class Context:
    """What a modifier is allowed to know: the seed, and the negatives."""

    seed_text: str = ""
    negatives: Negatives = Negatives()


class Modifier(Protocol):
    """Changes or drops candidates.  ``reason`` names the drop in the report."""

    reason: str

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        ...


def _key(generator: object, tag: str) -> str:
    """How a generator is named in a report: its tag, else its class."""
    return tag or type(generator).__name__


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AlongWall:
    """A band of points inside a rectangle's walls, stopping short of the corners.

    Each point sits at the middle of a band ``depth`` deep against the wall,
    facing into the room, which is where a room's furniture actually is: the
    shipped maps put a median 16 to 25 units between a prop and the nearest
    wall, and this map put its props in the open.

    ``setback`` is that corner rule.  A run that begins ``setback`` from one corner and
    ends ``setback`` from the other cannot reach the corner, so the row on the
    perpendicular wall cannot reach it either, so the two cannot meet.  The
    points are centred in what is left over after the setbacks, so a wall that
    does not divide evenly by ``spacing`` loses the remainder at both ends
    rather than all of it at one.

    A wall shorter than twice the setback gets no points at all.  That is the
    rule doing its job, not a failure: there is no part of that wall a piece of
    furniture can stand against without being in a corner.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    spacing: float
    depth: float = WALL_BAND
    setback: float = CORNER_SETBACK
    #: Which of the four walls to run along, in ``walls_of_rect`` order.
    sides: tuple[str, ...] = ("west", "east", "south", "north")
    tag: str = ""

    def walls(self) -> tuple[Wall, ...]:
        """The four interior walls of this rectangle, normals pointing in."""
        return walls_of_rect("", self.x0, self.y0, self.x1, self.y1, 0.0, 0.0)

    def generate(self, seed_text: str) -> tuple[Candidate, ...]:
        if self.spacing <= EPSILON:
            raise ValueError("AlongWall needs a positive spacing")
        source = _key(self, self.tag)
        out: list[Candidate] = []
        index = 0
        for wall in self.walls():
            if wall.side not in self.sides:
                continue
            low = wall.low + self.setback
            high = wall.high - self.setback
            usable = high - low
            if usable < -EPSILON:
                continue
            count = 1 if usable <= EPSILON else int(usable // self.spacing) + 1
            span = (count - 1) * self.spacing
            start = low + (usable - span) / 2.0
            inset = wall.at + wall.inward * self.depth / 2.0
            for step in range(count):
                run = start + step * self.spacing
                x, y = (inset, run) if wall.axis == "x" else (run, inset)
                out.append(Candidate(
                    x=x, y=y, yaw=_wrap(wall.facing_yaw),
                    index=index, tag=wall.side, source=source,
                ))
                index += 1
        return tuple(out)


@dataclass(frozen=True, slots=True)
class UniformFill:
    """``count`` points strewn over a rectangle, from the hash and nothing else.

    The existing ``Fill`` is this generator plus a model picker plus an avoid
    list plus an edge bias; the avoid list moves out to :class:`Negatives` and
    the model picker is not a placement question, which leaves the four
    numbers and a count.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    count: int
    #: How far in from the rectangle's own edge a point may land.  Zero puts
    #: points on the boundary, which is what a caller wants when the rectangle
    #: is already the safe area.
    margin: float = 0.0
    tag: str = ""

    def generate(self, seed_text: str) -> tuple[Candidate, ...]:
        source = _key(self, self.tag)
        lox, hix = sorted((self.x0, self.x1))
        loy, hiy = sorted((self.y0, self.y1))
        lox, hix = _inset(lox, hix, self.margin)
        loy, hiy = _inset(loy, hiy, self.margin)
        out: list[Candidate] = []
        for index in range(max(0, self.count)):
            out.append(Candidate(
                x=lox + (hix - lox) * unit_hash(seed_text, source, index, "x"),
                y=loy + (hiy - loy) * unit_hash(seed_text, source, index, "y"),
                yaw=_wrap(360.0 * unit_hash(seed_text, source, index, "yaw")),
                index=index, source=source,
            ))
        return tuple(out)


@dataclass(frozen=True, slots=True)
class Clusters:
    """``clusters`` groups of ``per_cluster`` points, each within ``radius``.

    ProtonScatter calls this fractal repetition and it is the difference
    between litter and a mess somebody made: real rooms have four bottles in
    one corner and none along the opposite wall, and a uniform fill of the same
    count has one bottle every eight feet.

    Cluster centres are drawn from the rectangle inset by the radius, so every
    member lands inside the rectangle.  A rectangle narrower than twice the
    radius collapses to its own centre line, which is the honest answer: the
    cluster is wider than the space, and moving it about would only put members
    through the wall.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    clusters: int
    per_cluster: int
    radius: float
    tag: str = ""

    def generate(self, seed_text: str) -> tuple[Candidate, ...]:
        source = _key(self, self.tag)
        lox, hix = sorted((self.x0, self.x1))
        loy, hiy = sorted((self.y0, self.y1))
        clox, chix = _inset(lox, hix, self.radius)
        cloy, chiy = _inset(loy, hiy, self.radius)
        out: list[Candidate] = []
        index = 0
        for group in range(max(0, self.clusters)):
            cx = clox + (chix - clox) * unit_hash(seed_text, source, group, "cx")
            cy = cloy + (chiy - cloy) * unit_hash(seed_text, source, group, "cy")
            for member in range(max(0, self.per_cluster)):
                angle = 2.0 * math.pi * unit_hash(seed_text, source, group, member, "a")
                # Square root, so the points spread evenly over the disc's area
                # instead of piling up at its centre.
                reach = self.radius * math.sqrt(
                    unit_hash(seed_text, source, group, member, "r")
                )
                out.append(Candidate(
                    x=cx + reach * math.cos(angle),
                    y=cy + reach * math.sin(angle),
                    yaw=_wrap(360.0 * unit_hash(seed_text, source, group, member, "yaw")),
                    index=index, tag=str(group), source=source,
                ))
                index += 1
        return tuple(out)


@dataclass(frozen=True, slots=True)
class Rows:
    """``count`` points evenly spaced between two ends, the existing ``Row``.

    Shelves down an aisle, chairs along a table, bollards along a path.  The
    arithmetic is the current placer's, down to a single-point row landing on
    the first end rather than at the middle, so a scene converted from ``Row``
    to this generator does not move.

    ``yaw`` of ``None`` means the line's own heading, which is what a run of
    pipe or a row of lockers wants; a number overrides it, and ``yaw_step``
    turns each piece a little further round a table.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    count: int
    yaw: float | None = None
    yaw_step: float = 0.0
    tag: str = ""

    @property
    def heading(self) -> float:
        """The direction the row runs, in degrees."""
        return _wrap(math.degrees(math.atan2(self.y1 - self.y0, self.x1 - self.x0)))

    def generate(self, seed_text: str) -> tuple[Candidate, ...]:
        source = _key(self, self.tag)
        base = self.heading if self.yaw is None else self.yaw
        steps = max(self.count - 1, 1)
        out: list[Candidate] = []
        for index in range(max(0, self.count)):
            ratio = index / steps if self.count > 1 else 0.0
            out.append(Candidate(
                x=self.x0 + (self.x1 - self.x0) * ratio,
                y=self.y0 + (self.y1 - self.y0) * ratio,
                yaw=_wrap(base + self.yaw_step * index),
                index=index, source=source,
            ))
        return tuple(out)


def _inset(low: float, high: float, margin: float) -> tuple[float, float]:
    """A range pulled in by ``margin`` at both ends, collapsing to its middle."""
    if margin <= 0.0:
        return (low, high)
    if high - low <= 2.0 * margin:
        middle = (low + high) / 2.0
        return (middle, middle)
    return (low + margin, high - margin)


# --------------------------------------------------------------------------
# Modifiers
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Jitter:
    """Moves each candidate off its lattice, by a hash and never by a die.

    ``radius`` bounds the move and the move is polar, so a jittered point is
    never further than ``radius`` from where the generator put it.  That bound
    is what lets a generator promise its own guarantees -- a wall band stays a
    wall band, a setback stays a setback -- with a jitter on top of it.

    ``yaw`` is the heading wander, in degrees, defaulting to
    :data:`YAW_WANDER`.  Zero leaves headings alone, which is what a row of
    machinery bolted to a wall wants.
    """

    radius: float = 0.0
    yaw: float = YAW_WANDER
    reason: str = ""

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        out: list[Candidate] = []
        for candidate in candidates:
            angle = 2.0 * math.pi * unit_hash(
                context.seed_text, *candidate.key("jitter-angle")
            )
            reach = self.radius * unit_hash(
                context.seed_text, *candidate.key("jitter-reach")
            )
            wander = self.yaw * (
                2.0 * unit_hash(context.seed_text, *candidate.key("jitter-yaw")) - 1.0
            )
            out.append(
                candidate
                .moved_to(candidate.x + reach * math.cos(angle),
                          candidate.y + reach * math.sin(angle))
                .turned_to(candidate.yaw + wander)
            )
        return tuple(out)


@dataclass(frozen=True, slots=True)
class FaceTarget:
    """Turns every candidate to look at one point.

    Seats face the table, lockers face the aisle, a crowd of chairs faces the
    stage.  ``offset`` turns the result afterwards, for the models whose
    forward is not their +X: 180 for a model that faces backwards, 90 for one
    that faces along its own side.  A candidate exactly on the target keeps the
    heading it had, because ``atan2(0, 0)`` is a number with no meaning.
    """

    x: float
    y: float
    offset: float = 0.0
    reason: str = ""

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        out: list[Candidate] = []
        for candidate in candidates:
            dx, dy = self.x - candidate.x, self.y - candidate.y
            if math.hypot(dx, dy) <= EPSILON:
                out.append(candidate)
                continue
            out.append(candidate.turned_to(math.degrees(math.atan2(dy, dx)) + self.offset))
        return tuple(out)


@dataclass(frozen=True, slots=True)
class FaceWall:
    """Turns every candidate to look at the nearest wall of a rectangle.

    Nearest is measured to the wall's own plane, so a point in the middle of a
    long room faces the long wall, and ties break west, east, south, north --
    the order :func:`~zmforge.placement.relations.walls_of_rect` returns them
    in -- rather than by whichever comparison happened to run first.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    offset: float = 0.0
    reason: str = ""

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        return _turn_to_walls(self, candidates, toward=True)


@dataclass(frozen=True, slots=True)
class FaceAway:
    """Turns every candidate to look away from the nearest wall, into the room.

    This is the one a chair wants.  A chair facing a wall is the single
    cheapest tell that a room was furnished by a program.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    offset: float = 0.0
    reason: str = ""

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        return _turn_to_walls(self, candidates, toward=False)


def _turn_to_walls(
    rect: FaceWall | FaceAway, candidates: tuple[Candidate, ...], *, toward: bool
) -> tuple[Candidate, ...]:
    walls = walls_of_rect("", rect.x0, rect.y0, rect.x1, rect.y1, 0.0, 0.0)
    out: list[Candidate] = []
    for candidate in candidates:
        nearest = min(walls, key=lambda wall: _plane_distance(wall, candidate))
        # A wall's facing yaw points into the room, so "away from the wall" is
        # the wall's own facing and "toward the wall" is the reverse of it.
        heading = nearest.facing_yaw + (180.0 if toward else 0.0)
        out.append(candidate.turned_to(heading + rect.offset))
    return tuple(out)


def _plane_distance(wall: Wall, candidate: Candidate) -> float:
    return abs((candidate.x if wall.axis == "x" else candidate.y) - wall.at)


@dataclass(frozen=True, slots=True)
class SnapToSurface:
    """Drops each candidate onto whatever is under it, and discards the rest.

    ``height_of(x, y)`` answers the height of the surface at a point, or
    ``None`` where there is no surface: over a stair well, off the edge of a
    terrain mesh, outside the room.  That second answer is the one that
    matters.  Measured on a test map, 31 props floated more than
    2 units, all of them in one room whose terrain mesh stopped 8 units short
    of one wall and 24 short of the other, so a row along that wall hung over
    the slab 55 to 70 units below.  A lookup that can say "nothing here" turns that into 37 dropped candidates
    with a reason instead of 37 floating props.

    ``keep_missing`` leaves those candidates where they are instead, for a
    caller that has its own fallback height.
    """

    height_of: Callable[[float, float], float | None]
    keep_missing: bool = False
    reason: str = "no surface"

    def apply(
        self, candidates: tuple[Candidate, ...], context: Context
    ) -> tuple[Candidate, ...]:
        out: list[Candidate] = []
        for candidate in candidates:
            height = self.height_of(candidate.x, candidate.y)
            if height is None:
                if self.keep_missing:
                    out.append(candidate)
                continue
            out.append(candidate.raised_to(float(height)))
        return tuple(out)


# --------------------------------------------------------------------------
# The stack
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Report:
    """What a run made and what it threw away, by name and by reason.

    Counts are carried as pairs rather than as a dictionary so the report is a
    value like everything else here: two runs of the same stack compare equal.
    """

    made: tuple[tuple[str, int], ...] = ()
    dropped: tuple[tuple[str, int], ...] = ()
    kept: int = 0

    @property
    def made_by(self) -> dict[str, int]:
        return dict(self.made)

    @property
    def dropped_by(self) -> dict[str, int]:
        return dict(self.dropped)

    @property
    def total_made(self) -> int:
        return sum(count for _, count in self.made)

    @property
    def total_dropped(self) -> int:
        return sum(count for _, count in self.dropped)

    def __str__(self) -> str:
        made = ", ".join(f"{name} {count}" for name, count in self.made) or "nothing"
        if not self.dropped:
            return f"{self.kept} kept from {made}"
        lost = ", ".join(f"{reason} {count}" for reason, count in self.dropped)
        return f"{self.kept} kept from {made}; dropped {lost}"


@dataclass(frozen=True, slots=True)
class StackResult:
    """The surviving candidates, and the account of how they survived."""

    candidates: tuple[Candidate, ...] = ()
    report: Report = Report()

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self):
        return iter(self.candidates)

    def __getitem__(self, index: int) -> Candidate:
        return self.candidates[index]


@dataclass(frozen=True, slots=True)
class Stack:
    """Generators, then modifiers in order, then the negatives.

    The negatives run last, once, on final positions.  That is a decision and
    it goes the other way from the current placer, which checks its avoid list
    when it picks a point and never again: a :class:`Jitter` after the check
    can move a prop into a doorway, which is one way a prop ends up inside an
    interactive footprint.  Final positions are what
    the ``.map`` gets, so final positions are what the keep-out zones judge.

    Running the same stack twice with the same seed text gives the same tuple
    of candidates.  Running it with a different seed text gives a different
    one.  Nothing else in the process can affect it.
    """

    generators: tuple[PointGenerator, ...] = ()
    modifiers: tuple[Modifier, ...] = ()
    negatives: Negatives = Negatives()

    def run(self, seed_text: str) -> StackResult:
        made: Counter[str] = Counter()
        dropped: Counter[str] = Counter()
        candidates: list[Candidate] = []
        for generator in self.generators:
            batch = generator.generate(seed_text)
            made[_key(generator, getattr(generator, "tag", ""))] += len(batch)
            candidates.extend(batch)

        context = Context(seed_text=seed_text, negatives=self.negatives)
        current = tuple(candidates)
        for modifier in self.modifiers:
            before = len(current)
            current = tuple(modifier.apply(current, context))
            lost = before - len(current)
            if lost > 0:
                dropped[getattr(modifier, "reason", "") or type(modifier).__name__] += lost

        survivors: list[Candidate] = []
        for candidate in current:
            zone = self.negatives.blocks(
                candidate.plan, z_low=candidate.z_low, z_high=candidate.z_high
            )
            if zone is None:
                survivors.append(candidate)
            else:
                dropped[zone.reason] += 1

        return StackResult(
            tuple(survivors),
            Report(
                made=tuple(sorted(made.items())),
                dropped=tuple(sorted(dropped.items())),
                kept=len(survivors),
            ),
        )
