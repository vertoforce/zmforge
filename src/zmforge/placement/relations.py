"""The relation vocabulary: what a placed thing must be true of.

A placer that deals models by list position can only be argued with in
coordinates.  A placer that states relations can be argued with in sentences:
*this notice board is on a wall at reading height*, *this chair is supported
by the floor and touching the table*, *nothing overlaps anything by more than
a twentieth of its footprint unless it is standing on it*.  The relations in
this module are that vocabulary, adapted from the constraint language of
Infinigen Indoors (princeton-vl/infinigen, BSD-3-Clause), which names
``StableAgainst``, ``SupportedBy``, ``CoPlanar`` and ``Touching`` and splits
its graph into hard constraints and soft score terms.  Nothing here is copied
from it: the semantics are theirs, the code and the thresholds are ours, and
the thresholds come off this map's own measurements.

Every relation answers the same way.  :meth:`check` returns ``None`` when the
relation holds and a :class:`Violation` when it does not, and the violation
carries a number, so the same object serves a placer deciding whether to keep
a candidate and a check run reporting what a finished map got wrong.  That is
the point of putting them here rather than inside the placer: the rule that
chooses a position and the rule that audits a position are one rule, and when
they are two they disagree.

The other half of the module is :func:`mount_kind_of_box`, which reads a
model's measured box and says whether the thing stands on a floor, hangs on a
wall or hangs from a ceiling.  The rule, in one line: a box that is
centred on its origin in Z, or wholly below it, is not floor-standing.  That
one test catches the most visible mount faults -- clocks, signs,
frames and notice boards lying half in the floor tile, chandeliers buried
under it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .geometry import EPSILON, Poly2, rotate

__all__ = [
    "MountKind",
    "mount_kind_of_box",
    "Placed",
    "Wall",
    "Surface",
    "Violation",
    "StableAgainst",
    "SupportedBy",
    "OnWall",
    "HangsFrom",
    "Touching",
    "CoPlanar",
    "NoOverlap",
    "PLAYER_RADIUS",
    "PLAYER_HEIGHT",
    "walls_of_rect",
]

#: The player's collision radius, in world units.  **[stock-source]**: the
#: shipped scripts on the mod tools install define ``PLAYER_RADIUS 15``
#: (``scripts/shared/player_shared.gsc:15``), and the bot debug box is drawn
#: ``(-15, -15, 0)`` to ``(15, 15, 72)`` (``scripts/shared/bots/_bot.gsc:741``).
#: So a player is 30 units across and 72 tall, and every clearance in
#: :mod:`zmforge.placement.clearance` is measured with that disc rather than
#: with an arbitrary round number.
PLAYER_RADIUS = 15.0

#: The player's height, from the same debug box.
PLAYER_HEIGHT = 72.0

#: How far a coordinate may be off before it counts as off.  A tenth of the
#: ``.map`` writer's 8-unit grid.
NEAR = 1.0


class MountKind(Enum):
    """Where a model is meant to be attached.

    ``EITHER`` is not a fourth kind of mounting, it is the honest answer when
    the box does not settle the question: a z-centred chunk of masonry can lie
    on a floor (with its origin raised by the depth of its own box) or be part
    of a wall, and nothing in its measurements says which.  A caller that
    needs a decision gives a name hint; a caller that does not gets to know
    the placement is a guess.
    """

    FLOOR = "floor"
    WALL = "wall"
    CEILING = "ceiling"
    EITHER = "either"


def mount_kind_of_box(
    box: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    *,
    tolerance: float = NEAR,
) -> MountKind:
    """Read a model's mount kind off its own measured box.

    The rule:

    * the box sits at or above its origin (``z0 >= -tolerance``): it stands on
      a **floor**.  Authoring a model with its origin on its base is what a
      floor-standing model looks like;
    * the box is wholly at or below its origin (``z1 <= tolerance``): it hangs
      from a **ceiling**.  Both hanging-light families in this map's palette
      measure that way, which is why the families and the measurement agree;
    * the box straddles its origin in Z -- *z-centred* -- and is thin on one
      plan axis: it hangs on a **wall**.  A sign, a clock, a picture frame and
      a notice board are all authored that way, origin in the middle of the
      back plate, because a fixture is positioned by where it meets the wall;
    * z-centred and not thin in plan: **either**, see :class:`MountKind`.

    ``None`` -- a model with no measured box -- comes back ``FLOOR``, which is
    the safe answer: it is what every model got before mount kinds existed.

    **What the box rule alone gets wrong, measured on this palette.
    **  Run over the 125 models of ``props.MODEL_BOX`` it calls 15
    of them ``WALL``.  Ten are wall fixtures and the rule has found them
    without being told: the clock, the LED wall fixture, the picture frame,
    the three pieces of signage, the bulletin board, the two Der Riese signs
    and the duct vent.  Five are not: ``p7_rebar_column_128`` is a
    floor-standing column authored about its middle, ``p7_tools_shovel`` is a
    shovel, ``p7_wires_electrical_rubber_02`` is a coil of cable, and two
    pieces of plaster rubble are rubble.  So the box settles the *ceiling*
    question outright and narrows the wall question to fifteen candidates; a
    name hint still decides those five, which is why
    :data:`zmforge.recipes.props.WALL_FAMILIES` does not go away.  Stating it
    the other way round is the point: the rule is wrong five times out of 125
    and it is wrong in a direction a name list can fix, where the old default
    of "everything stands on the floor" was wrong 135 times in a built map and
    nothing could see it.
    """
    if box is None:
        return MountKind.FLOOR
    (x0, y0, z0), (x1, y1, z1) = box
    if z0 >= -tolerance:
        return MountKind.FLOOR
    if z1 <= tolerance:
        return MountKind.CEILING
    width, depth, height = x1 - x0, y1 - y0, z1 - z0
    thin_in_plan = min(width, depth) < THIN_SHARE * max(width, depth, height)
    return MountKind.WALL if thin_in_plan else MountKind.EITHER


#: How much thinner than its other sides a z-centred model's thinnest plan
#: side has to be before the model reads as a plate hung on a wall rather than
#: an object.  Measured against this map's palette: every wall family is at or
#: under 0.18 of its longest side (a sign is 0.2 units through a 32-unit face,
#: the deepest is the 9.4-unit LED fixture on a 60-unit face), and the
#: z-centred objects that are not wall fixtures -- rock and masonry chunks --
#: are all above 0.4.
THIN_SHARE = 0.25


@dataclass(frozen=True, slots=True)
class Placed:
    """One thing standing somewhere: a footprint, a height range and a name.

    Coordinates are world coordinates and ``x``/``y`` are the *footprint's*
    centre, not the emitted origin.  The two differ whenever a model's box is
    off-centre in plan, and confusing them is how a prop ends up a foot into a
    wall; :meth:`from_model` does the conversion once, from the emitted origin
    and the model's own box, so no caller has to do it again.
    """

    name: str
    x: float
    y: float
    hx: float
    hy: float
    yaw: float = 0.0
    z_low: float = 0.0
    z_high: float = 0.0
    solid: bool = True
    room: str = ""
    ident: str = ""

    @classmethod
    def from_model(
        cls,
        name: str,
        box: tuple[tuple[float, float, float], tuple[float, float, float]],
        origin: tuple[float, float, float],
        yaw: float = 0.0,
        scale: float = 1.0,
        *,
        solid: bool = True,
        room: str = "",
        ident: str = "",
    ) -> "Placed":
        """Place a model by the origin the ``.map`` carries, as the game does.

        ``box`` is the model's own local box, ``origin`` the entity origin and
        ``yaw`` the middle number of its ``angles``.  The footprint centre is
        the box's plan centre turned by the yaw and added to the origin, which
        is the same arithmetic a check over the built map does.
        """
        (x0, y0, z0), (x1, y1, z1) = box
        local_cx, local_cy = (x0 + x1) / 2.0 * scale, (y0 + y1) / 2.0 * scale
        offset_x, offset_y = rotate(local_cx, local_cy, yaw)
        return cls(
            name=name,
            x=origin[0] + offset_x,
            y=origin[1] + offset_y,
            hx=(x1 - x0) * scale / 2.0,
            hy=(y1 - y0) * scale / 2.0,
            yaw=yaw,
            z_low=origin[2] + z0 * scale,
            z_high=origin[2] + z1 * scale,
            solid=solid,
            room=room,
            ident=ident,
        )

    @property
    def footprint(self) -> Poly2:
        return Poly2.box(self.x, self.y, self.hx, self.hy, self.yaw)

    @property
    def plan_area(self) -> float:
        return 4.0 * self.hx * self.hy

    @property
    def height(self) -> float:
        return self.z_high - self.z_low

    @property
    def position(self) -> str:
        """``x y z`` as the findings print it."""
        return f"{self.x:.0f} {self.y:.0f} {self.z_low:.0f}"

    def height_overlap(self, other: "Placed") -> float:
        """How much of their height two things share; negative when apart."""
        return min(self.z_high, other.z_high) - max(self.z_low, other.z_low)

    def moved_to(self, x: float, y: float) -> "Placed":
        return Placed(self.name, x, y, self.hx, self.hy, self.yaw,
                      self.z_low, self.z_high, self.solid, self.room, self.ident)

    def turned_to(self, yaw: float) -> "Placed":
        return Placed(self.name, self.x, self.y, self.hx, self.hy, yaw,
                      self.z_low, self.z_high, self.solid, self.room, self.ident)

    def raised_to(self, z_low: float) -> "Placed":
        return Placed(self.name, self.x, self.y, self.hx, self.hy, self.yaw,
                      z_low, z_low + self.height, self.solid, self.room, self.ident)


@dataclass(frozen=True, slots=True)
class Wall:
    """One flat vertical face something can be mounted against.

    ``axis`` is the axis the wall's *normal* runs along, ``at`` the plane's
    coordinate on it, and ``inward`` which way the room is: ``+1`` means the
    room is on the high side of the plane.  ``low``/``high`` bound the wall
    along its own run, so a fixture cannot be mounted past the end of it.
    """

    room: str
    axis: str  # "x" or "y": the axis the normal runs along
    at: float
    inward: int  # +1 or -1
    low: float
    high: float
    floor_z: float
    ceiling_z: float
    side: str = ""

    @property
    def normal(self) -> tuple[float, float]:
        return (float(self.inward), 0.0) if self.axis == "x" else (0.0, float(self.inward))

    @property
    def facing_yaw(self) -> float:
        """The yaw a fixture on this wall looks along, into the room."""
        nx, ny = self.normal
        return math.degrees(math.atan2(ny, nx))

    def signed_gap(self, subject: Placed) -> float:
        """How far the subject's back face is off this plane, into the room.

        Positive is a gap between the fixture and the wall; negative is the
        fixture inside the wall.
        """
        x0, y0, x1, y1 = subject.footprint.bounds
        back = (x0 if self.inward > 0 else x1) if self.axis == "x" else (y0 if self.inward > 0 else y1)
        return (back - self.at) * self.inward

    def along_span(self, subject: Placed) -> tuple[float, float]:
        """The subject's extent along the wall's own run."""
        x0, y0, x1, y1 = subject.footprint.bounds
        return (y0, y1) if self.axis == "x" else (x0, x1)


def walls_of_rect(
    room: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    floor_z: float,
    ceiling_z: float,
) -> tuple[Wall, ...]:
    """The four walls of a rectangular room's interior, normals pointing in."""
    return (
        Wall(room, "x", x0, +1, y0, y1, floor_z, ceiling_z, "west"),
        Wall(room, "x", x1, -1, y0, y1, floor_z, ceiling_z, "east"),
        Wall(room, "y", y0, +1, x0, x1, floor_z, ceiling_z, "south"),
        Wall(room, "y", y1, -1, x0, x1, floor_z, ceiling_z, "north"),
    )


@dataclass(frozen=True, slots=True)
class Surface:
    """A horizontal top something can stand on: a floor, a block, a desk."""

    name: str
    poly: Poly2
    top_z: float

    @classmethod
    def rect(cls, name: str, x0: float, y0: float, x1: float, y1: float, top_z: float) -> "Surface":
        return cls(name, Poly2.rect(x0, y0, x1, y1), top_z)


@dataclass(frozen=True, slots=True)
class Violation:
    """One relation, broken, with the number that says by how much."""

    relation: str
    detail: str
    amount: float = 0.0
    subject: str = ""
    target: str = ""

    def __str__(self) -> str:
        who = f"{self.subject} " if self.subject else ""
        return f"{who}{self.detail}"


# --------------------------------------------------------------------------
# The relations
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class StableAgainst:
    """The subject's back is flat on a wall, within ``margin``.

    Infinigen's spelling is ``StableAgainst(cu.back, cu.walltags, margin=0.1)``
    in metres.  Ours is in inches and defaults to 2, which is a quarter of the
    map grid: a fixture further off its wall than that reads as floating, and
    one further into it than that is inside the brush.

    ``ends`` is the other half of the rule and the one the current placer does
    not have: the subject has to be *on* the wall along its run, not hanging
    off the end of it.
    """

    margin: float = 2.0
    ends: bool = True

    def check(self, subject: Placed, target: Wall) -> Violation | None:
        gap = target.signed_gap(subject)
        if gap < -self.margin:
            return Violation(
                "StableAgainst",
                f"is {-gap:.0f} units inside the {target.side or target.axis} wall of {target.room}",
                -gap, subject.name, target.room,
            )
        if gap > self.margin:
            return Violation(
                "StableAgainst",
                f"stands {gap:.0f} units off the {target.side or target.axis} wall of {target.room}",
                gap, subject.name, target.room,
            )
        if self.ends:
            low, high = target.along_span(subject)
            if low < target.low - self.margin or high > target.high + self.margin:
                over = max(target.low - low, high - target.high)
                return Violation(
                    "StableAgainst",
                    f"hangs {over:.0f} units past the end of the "
                    f"{target.side or target.axis} wall of {target.room}",
                    over, subject.name, target.room,
                )
        return None

    def holds(self, subject: Placed, target: Wall) -> bool:
        return self.check(subject, target) is None


@dataclass(frozen=True, slots=True)
class SupportedBy:
    """The subject rests on a surface, and its footprint is on that surface.

    ``share`` is how much of the footprint has to be over the surface.  One
    means all of it.  A prop with two corners or fewer on what it stands on -- a
    90-long desk on a 40-deep counter, a crate with none of its four corners
    on its plinth -- is not standing on it, so the default is strict
    and a caller that wants an overhang has to ask for one.
    """

    tolerance: float = NEAR
    share: float = 1.0

    def check(self, subject: Placed, target: Surface) -> Violation | None:
        drop = subject.z_low - target.top_z
        if drop < -self.tolerance:
            return Violation(
                "SupportedBy",
                f"is {-drop:.0f} units into {target.name}",
                -drop, subject.name, target.name,
            )
        if drop > self.tolerance:
            return Violation(
                "SupportedBy",
                f"floats {drop:.0f} units above {target.name}",
                drop, subject.name, target.name,
            )
        area = subject.footprint.area
        if area > EPSILON:
            on = subject.footprint.overlap_area(target.poly) / area
            if on < self.share - 1e-6:
                return Violation(
                    "SupportedBy",
                    f"has {on * 100:.0f}% of its footprint on {target.name}",
                    self.share - on, subject.name, target.name,
                )
        return None

    def holds(self, subject: Placed, target: Surface) -> bool:
        return self.check(subject, target) is None


@dataclass(frozen=True, slots=True)
class OnWall:
    """A fixture mounted on a wall plane, at a height in the sill range.

    ProcTHOR samples a wall asset's height on the wall plane instead of
    standing it on the floor (``wall_objects.py``, Apache-2.0); this is that
    rule stated as a relation, with the range rather than the sample, so the
    same object can both choose a height and judge one.

    The default range is this map's own: 16 units is the floor of what still
    reads as mounted, and 154 is the top of where its wall pictures hang, so a
    fixture in the range cannot cover one.
    """

    sill_low: float = 16.0
    sill_high: float = 154.0
    margin: float = 2.0

    def check(self, subject: Placed, target: Wall) -> Violation | None:
        flat = StableAgainst(margin=self.margin).check(subject, target)
        if flat is not None:
            return Violation("OnWall", flat.detail, flat.amount, subject.name, target.room)
        sill = subject.z_low - target.floor_z
        if sill < self.sill_low:
            return Violation(
                "OnWall",
                f"is mounted {sill:.0f} units above the floor of {target.room}, "
                f"under the {self.sill_low:.0f}-unit sill"
                + (" (below the floor)" if sill < 0 else ""),
                self.sill_low - sill, subject.name, target.room,
            )
        if sill > self.sill_high:
            return Violation(
                "OnWall",
                f"is mounted {sill:.0f} units above the floor of {target.room}, "
                f"over the {self.sill_high:.0f}-unit sill",
                sill - self.sill_high, subject.name, target.room,
            )
        if subject.z_high > target.ceiling_z:
            return Violation(
                "OnWall",
                f"pokes {subject.z_high - target.ceiling_z:.0f} units through the "
                f"ceiling of {target.room}",
                subject.z_high - target.ceiling_z, subject.name, target.room,
            )
        return None

    def holds(self, subject: Placed, target: Wall) -> bool:
        return self.check(subject, target) is None


@dataclass(frozen=True, slots=True)
class HangsFrom:
    """The subject's top is at a ceiling, within ``clearance``.

    A chandelier whose top is 200 units under the ceiling is not hanging from
    anything, and one whose top is above the ceiling is in the roof.  The
    default clearance is the 4 units the current placer leaves.
    """

    clearance: float = 4.0
    tolerance: float = NEAR

    def check(self, subject: Placed, ceiling_z: float, room: str = "") -> Violation | None:
        drop = ceiling_z - subject.z_high
        if drop < -self.tolerance:
            return Violation(
                "HangsFrom",
                f"pokes {-drop:.0f} units through the ceiling{_in(room)}",
                -drop, subject.name, room,
            )
        if drop > self.clearance + self.tolerance:
            return Violation(
                "HangsFrom",
                f"hangs with its top {drop:.0f} units under the ceiling{_in(room)}",
                drop, subject.name, room,
            )
        return None

    def holds(self, subject: Placed, ceiling_z: float, room: str = "") -> bool:
        return self.check(subject, ceiling_z, room) is None


@dataclass(frozen=True, slots=True)
class Touching:
    """Two things side by side: within ``gap`` of each other, not inside.

    Treyarch's own interiors have props touching -- nearest-neighbour median
    5 to 10 units -- so this is a relation a
    generated room wants to satisfy on purpose, not one it wants to avoid.
    """

    gap: float = 8.0
    overlap: float = 0.05

    def check(self, subject: Placed, target: Placed) -> Violation | None:
        clash = NoOverlap(tolerance=self.overlap).check(subject, target)
        if clash is not None:
            return Violation("Touching", clash.detail, clash.amount, subject.name, target.name)
        distance = subject.footprint.gap_to(target.footprint)
        if distance > self.gap:
            return Violation(
                "Touching",
                f"is {distance:.0f} units from {target.name}, not touching it",
                distance, subject.name, target.name,
            )
        return None

    def holds(self, subject: Placed, target: Placed) -> bool:
        return self.check(subject, target) is None


#: Which face of a box each side names.
SIDES = ("west", "east", "south", "north", "bottom", "top")


@dataclass(frozen=True, slots=True)
class CoPlanar:
    """Two things line up: the named faces share a plane.

    This is what makes a row of filing cabinets read as a row of filing
    cabinets rather than as four filing cabinets.  ``side`` is one of
    :data:`SIDES`; ``top`` and ``bottom`` compare heights, the other four
    compare the plan bounding box, which is the right comparison for
    axis-aligned dressing and an approximation for anything turned off the
    axes.
    """

    side: str = "north"
    tolerance: float = NEAR

    def _plane(self, subject: Placed) -> float:
        if self.side == "top":
            return subject.z_high
        if self.side == "bottom":
            return subject.z_low
        x0, y0, x1, y1 = subject.footprint.bounds
        return {"west": x0, "east": x1, "south": y0, "north": y1}[self.side]

    def check(self, subject: Placed, target: Placed) -> Violation | None:
        if self.side not in SIDES:
            raise ValueError(f"{self.side!r} is not one of {SIDES}")
        off = abs(self._plane(subject) - self._plane(target))
        if off > self.tolerance:
            return Violation(
                "CoPlanar",
                f"is {off:.0f} units out of line with {target.name} on its {self.side} face",
                off, subject.name, target.name,
            )
        return None

    def holds(self, subject: Placed, target: Placed) -> bool:
        return self.check(subject, target) is None


@dataclass(frozen=True, slots=True)
class NoOverlap:
    """Two things are not in the same place, with an allowance for each way they may be.

    Two allowances, because a furnished room needs both:

    ``tolerance``
        how much of the *smaller* footprint the two may share before this is
        interpenetration rather than touching, as a share of that footprint.
        0.05 is the current placer's number and it is small on purpose: the
        shipped maps are full of touching props;
    ``stack_allowance``
        how much of their heights two things may share and still count as one
        standing on the other.  Capped at half the height of the shorter of
        the two, because a flat number is no test for flat things: two
        2.3-unit newspapers on the same patch of floor overlap by 2.3, and
        that is two newspapers drawn through each other, not a stack.

    ``min_side`` skips the rule for small props, both of whose plan sides are
    under it.  A cup half inside a bowl is a still life.
    """

    tolerance: float = 0.05
    stack_allowance: float = 4.0
    min_side: float = 0.0

    def _small(self, subject: Placed) -> bool:
        return 2.0 * subject.hx <= self.min_side and 2.0 * subject.hy <= self.min_side

    def check(self, subject: Placed, target: Placed) -> Violation | None:
        if self.min_side > 0.0 and (self._small(subject) or self._small(target)):
            return None
        shared = subject.footprint.overlap_area(target.footprint)
        if shared <= EPSILON:
            return None
        allowance = min(self.stack_allowance,
                        max(0.0, min(subject.height, target.height)) / 2.0)
        if subject.height_overlap(target) <= allowance:
            return None  # stacked, or set down on top of one another
        smaller = min(subject.footprint.area, target.footprint.area)
        if smaller <= EPSILON:
            return None
        share = shared / smaller
        if share > self.tolerance:
            return Violation(
                "NoOverlap",
                f"is {share * 100:.0f}% inside {target.name} at {target.position}",
                share, subject.name, target.name,
            )
        return None

    def holds(self, subject: Placed, target: Placed) -> bool:
        return self.check(subject, target) is None


def _in(room: str) -> str:
    return f" of {room}" if room else ""
