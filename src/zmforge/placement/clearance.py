"""Clearance: how much floor a model needs, read off its own shape.

The placer this package replaces keeps a prop clear of things with fixed
numbers: 96 units round a barricade landing, 48 in front of a door leaf, 20 of
air in front of a seat.  Those numbers are right for what they guard and wrong
as a general rule, because none of them knows how big the prop is.  A 132-unit
pallet and a 14-unit newspaper get the same apron, so one of them blocks a
route the check says is open and the other loses floor nothing was going to
use.

Merrell et al. 2011 state it the other way round and this module follows them:

    "we consider the projection of each furniture item onto the ground plane.
    We then add desired clearance to the item by taking the Minkowski sum of
    its projection with a line segment or a disk sized according to Table 1."

So the clearance of a thing is its own outline grown by a player-sized disc
(:data:`~zmforge.placement.relations.PLAYER_RADIUS`, 15 units, off the shipped
``player_shared.gsc``), plus a directional sweep in front of it when the thing
has a front worth standing at.  A rotated desk keeps its rotation, a long desk
gets a long apron, and the apron in front of a buy is the only place a fixed
number still appears (:data:`FRONT_APRON`).

Two things are built on top of that shape:

* :class:`FreeFloor`, Merrell's circulation term.  The paper's wording is "the
  number of connected components in Cfree", and that count is what catches the
  fault a per-pair overlap test cannot see: no two props touch, and between
  them they have walled the room in half.  It is also far cheaper than the
  navmesh flood it front-runs, since it needs no compile;
* :func:`focus_score`, Merrell's emphasis term: a room has a draw -- the wall
  buy, the door, the window -- and the room's main object either faces it or
  does not.  A seat facing a wall 13 units away scores close to zero.

Pure stdlib, like the rest of :mod:`zmforge.placement`: ``zmforge`` declares no
dependencies and a placement rule that needed numpy would take that guarantee
with it.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .geometry import EPSILON, Poly2, Vec2, minkowski_disc, minkowski_segment, rotate
from .relations import PLAYER_RADIUS, Placed, Violation

__all__ = [
    "ClearanceKind",
    "FRONT_APRON",
    "clearance_polygon",
    "clearance_of",
    "CIRCULATION_CELL",
    "Link",
    "Circulation",
    "FreeFloor",
    "Draw",
    "DRAW_WEIGHT",
    "DRAW_MARGIN",
    "focal_point_of",
    "focus_score",
]


# --------------------------------------------------------------------------
# 1. The shape
# --------------------------------------------------------------------------
class ClearanceKind(Enum):
    """What a model is for, as far as clearance is concerned.

    Four kinds, because the front apron is the only thing that varies and
    there are only four answers to "what does a player do at this?": use it,
    sit on it, put something on it, walk round it.  A caller that has a better
    idea of the apron than the table does passes the number straight to
    :func:`clearance_polygon` instead.
    """

    INTERACTIVE = "interactive"
    SEAT = "seat"
    SURFACE = "surface"
    PLAIN = "plain"

    @classmethod
    def of(cls, value: "ClearanceKind | str") -> "ClearanceKind":
        """The kind, from itself or from its name, so callers may use either."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError:
            raise ValueError(
                f"{value!r} is not a clearance kind; "
                f"expected one of {tuple(k.value for k in cls)}"
            ) from None


#: How deep the apron in front of each kind runs, in world units.  Exposed so a
#: caller can pass its own table to :func:`clearance_of`; the defaults are:
#:
#: ``interactive`` 48
#:     **[measured]** the depth a player crosses standing up to something he
#:     uses.  It is :data:`zmforge.recipes.props.DOOR_FACE_CLEAR`, the same
#:     48 units that "in front of an interactive item" means elsewhere.
#: ``seat`` 32
#:     **[chosen]** :data:`zmforge.recipes.props.SEAT_CLEAR` is 20, the point
#:     below which a seat is one nobody could sit in, so 20 is a floor and not
#:     a target.  32 is the next number up that is two whole 16-unit pocket
#:     cells, i.e. the chair can be pulled out and stood behind.  Not
#:     separately measured.
#: ``surface`` 24
#:     **[chosen]** half the interactive apron.  A desk or counter is worked at
#:     rather than queued at, and 24 still leaves a whole pocket cell of
#:     standing room in front of the deepest counter in the palette (40 deep,
#:     deep enough that a 90-long desk can overhang it).  Not separately
#:     measured.
#: ``plain`` 0
#:     a crate has no front.  Its clearance is the disc alone.
FRONT_APRON: Mapping[ClearanceKind, float] = {
    ClearanceKind.INTERACTIVE: 48.0,
    ClearanceKind.SEAT: 32.0,
    ClearanceKind.SURFACE: 24.0,
    ClearanceKind.PLAIN: 0.0,
}


def clearance_polygon(
    subject: Placed,
    *,
    radius: float = PLAYER_RADIUS,
    front: float = 0.0,
    front_yaw: float | None = None,
) -> Poly2:
    """The floor ``subject`` needs: its footprint grown by a player, plus an apron.

    Physically this is the set of positions a player's centre may not be at,
    so it is the shape a circulation test subtracts from the floor and the
    shape a packer rejects a candidate against.  Two properties matter and
    neither holds for a grown bounding box: the corners come back rounded, so
    a player brushing a corner diagonally is not counted as blocked, and a
    footprint turned to 37 degrees keeps its 37 degrees.

    ``front`` is the directional half of the paper's rule ("a line segment or
    a disk"): the whole grown shape is swept ``front`` units along
    ``front_yaw``, which defaults to the subject's own yaw.  A caller working
    from :data:`zmforge.recipes.props.MODEL_FRONT` passes the model's front as
    ``front_yaw``; a seat's front is not always its yaw.

    Sweeping the grown shape rather than the raw footprint is deliberate and
    is what the sum's associativity says to do: the apron is as wide as the
    prop plus a player, not as wide as the prop.
    """
    grown = minkowski_disc(subject.footprint, max(0.0, radius))
    if abs(front) <= EPSILON:
        return grown
    yaw = subject.yaw if front_yaw is None else front_yaw
    dx, dy = rotate(front, 0.0, yaw)
    return minkowski_segment(grown, dx, dy)


def clearance_of(
    subject: Placed,
    kind: ClearanceKind | str = ClearanceKind.PLAIN,
    *,
    radius: float = PLAYER_RADIUS,
    front_yaw: float | None = None,
    aprons: Mapping[ClearanceKind, float] = FRONT_APRON,
) -> Poly2:
    """:func:`clearance_polygon` with the apron looked up by kind.

    The table is a default and not a law: ``aprons`` takes any mapping, so a
    scene that knows its own numbers overrides them without touching this
    module.
    """
    resolved = ClearanceKind.of(kind)
    if resolved not in aprons:
        raise ValueError(f"no apron for {resolved.value!r} in the table given")
    return clearance_polygon(
        subject, radius=radius, front=aprons[resolved], front_yaw=front_yaw
    )


# --------------------------------------------------------------------------
# 2. Circulation
# --------------------------------------------------------------------------
#: The grid the free-floor raster works on, in units.  The same 16 as
#: :data:`zmforge.recipes.props.POCKET_CELL`, for the same reason: it is twice
#: the ``.map`` writer's 8-unit grid, so no wall or prop face falls inside a
#: cell without the cell knowing, and a room a few hundred units across is a
#: grid of a few hundred cells, which floods in well under a millisecond.
CIRCULATION_CELL = 16.0


@dataclass(frozen=True, slots=True)
class Link:
    """A connection the finished room has to keep: "you can walk a to b".

    The links are the map's own promises -- the spawn to the door, the door to
    the wall buy, the buy to the next door -- and they are what makes a
    component count actionable.  Two components are fine in a room with an
    alcove nobody needs; two components are a sealed map when the buy is in
    one of them and the spawn is in the other.
    """

    name: str
    a: Vec2
    b: Vec2


@dataclass(frozen=True, slots=True)
class Circulation:
    """What the free floor came to: how many pieces, how big, what broke.

    ``areas`` is in square units, biggest piece first, so a two-component
    result whose second piece is one cell reads as the rounding it is rather
    than as a severed room.  ``faults`` are :class:`~zmforge.placement.relations.Violation`
    objects, the same type the relations return, with ``relation`` set to
    ``"Circulation"`` and ``subject`` set to the link's name.  Their ``amount``
    is the floor area still reachable from the link's first end, which is the
    number that says whether the player is shut in a cupboard or shut out of
    one.
    """

    components: int
    areas: tuple[float, ...]
    faults: tuple[Violation, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.faults

    @property
    def broken(self) -> tuple[str, ...]:
        """The names of the links that failed, in the order they were given."""
        return tuple(fault.subject for fault in self.faults)

    @property
    def free_area(self) -> float:
        return sum(self.areas)


@dataclass(frozen=True, slots=True)
class FreeFloor:
    """A room's walkable floor as a grid of free/blocked cells.

    Built by :meth:`of` from one or more room rectangles minus a set of
    clearance polygons.  A cell is free when its centre is inside a room and
    inside no clearance, which is the cheapest test there is and is sound for
    what it is handed: every clearance from :func:`clearance_polygon` is at
    least ``2 * PLAYER_RADIUS`` = 30 units across, and a band 30 units wide
    always contains a cell centre on a 16-unit grid, so no clearance can slip
    between two samples.  A caller that grows nothing and hands raw footprints
    in loses that guarantee and should say so.

    Connectivity is 4-connected on purpose.  Diagonal connectivity would let
    the flood pass through the corner where two props meet, which is exactly
    the gap the navmesh compiler later refuses to lay surface in (the same
    reason :data:`zmforge.recipes.props.POCKET_MARGIN` exists).
    """

    x0: float
    y0: float
    nx: int
    ny: int
    cell: float
    free: tuple[bool, ...]

    # -- construction ----------------------------------------------------
    @classmethod
    def of(
        cls,
        rooms: Iterable[Sequence[float]],
        blocked: Iterable[Poly2] = (),
        *,
        cell: float = CIRCULATION_CELL,
    ) -> "FreeFloor":
        """Raster the union of ``rooms`` (``x0, y0, x1, y1`` each), minus ``blocked``.

        Several rectangles make an L-shaped or T-shaped room, which is how
        this map's rooms are actually shaped; the grid spans their common
        bounding box and the cells outside every rectangle are simply blocked.
        """
        rects = tuple(
            (min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3]))
            for r in (tuple(float(v) for v in room) for room in rooms)
        )
        if not rects:
            raise ValueError("a free floor needs at least one room rectangle")
        if cell <= EPSILON:
            raise ValueError(f"a cell of {cell} is not a grid")
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[2] for r in rects)
        y1 = max(r[3] for r in rects)
        nx = max(1, math.ceil((x1 - x0) / cell - 1e-9))
        ny = max(1, math.ceil((y1 - y0) / cell - 1e-9))
        zones = tuple((poly, poly.bounds) for poly in blocked if len(poly.points) >= 3)

        free: list[bool] = []
        for j in range(ny):
            cy = y0 + (j + 0.5) * cell
            for i in range(nx):
                cx = x0 + (i + 0.5) * cell
                free.append(_is_free(cx, cy, rects, zones))
        return cls(x0, y0, nx, ny, cell, tuple(free))

    @classmethod
    def of_placed(
        cls,
        rooms: Iterable[Sequence[float]],
        placed: Iterable[Placed],
        *,
        radius: float = PLAYER_RADIUS,
        cell: float = CIRCULATION_CELL,
        solid_only: bool = True,
    ) -> "FreeFloor":
        """:meth:`of` with the clearance of each placed thing worked out here.

        No front aprons: circulation is about whether a player can get past a
        prop, and an apron is about whether he can use it.  Blocking the floor
        with aprons would report a room as severed because the desk has a
        chair space.
        """
        zones = [
            clearance_polygon(thing, radius=radius)
            for thing in placed
            if thing.solid or not solid_only
        ]
        return cls.of(rooms, zones, cell=cell)

    # -- cells -----------------------------------------------------------
    @property
    def cell_area(self) -> float:
        return self.cell * self.cell

    @property
    def free_cells(self) -> int:
        return sum(1 for value in self.free if value)

    @property
    def free_area(self) -> float:
        return self.free_cells * self.cell_area

    def centre_of(self, i: int, j: int) -> Vec2:
        """The world position of cell ``(i, j)``."""
        return (self.x0 + (i + 0.5) * self.cell, self.y0 + (j + 0.5) * self.cell)

    def cell_at(self, point: Vec2) -> tuple[int, int] | None:
        """Which cell a world point falls in, or ``None`` when it is off the grid."""
        i = int(math.floor((point[0] - self.x0) / self.cell))
        j = int(math.floor((point[1] - self.y0) / self.cell))
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return (i, j)
        return None

    def is_free(self, point: Vec2) -> bool:
        cell = self.cell_at(point)
        return cell is not None and self.free[cell[1] * self.nx + cell[0]]

    def nearest_free(self, point: Vec2, within: float) -> tuple[int, int] | None:
        """The closest free cell whose centre is within ``within`` of ``point``.

        Endpoints are not always on open floor even when the map is fine: a
        doorway's own centre sits in the door's clearance, and a wall buy's
        origin is in the wall.  A caller that knows that gives a snap radius
        rather than declaring the link broken.  Ties go to the lower ``(j, i)``
        so the answer does not depend on iteration order.
        """
        best: tuple[int, int] | None = None
        best_distance = within + EPSILON
        reach = int(math.ceil(within / self.cell)) + 1
        here = (
            int(math.floor((point[0] - self.x0) / self.cell)),
            int(math.floor((point[1] - self.y0) / self.cell)),
        )
        for j in range(max(0, here[1] - reach), min(self.ny, here[1] + reach + 1)):
            for i in range(max(0, here[0] - reach), min(self.nx, here[0] + reach + 1)):
                if not self.free[j * self.nx + i]:
                    continue
                cx, cy = self.centre_of(i, j)
                distance = math.hypot(cx - point[0], cy - point[1])
                if distance < best_distance - EPSILON:
                    best, best_distance = (i, j), distance
        return best

    # -- components ------------------------------------------------------
    def labels(self) -> tuple[tuple[int, ...], int]:
        """``(label per cell, how many components)``; blocked cells label ``-1``.

        Labels are handed out in raster order, so component 0 is always the
        one containing the lowest free cell and a report of them is stable
        between runs.
        """
        labels = [-1] * len(self.free)
        count = 0
        for start in range(len(self.free)):
            if not self.free[start] or labels[start] >= 0:
                continue
            labels[start] = count
            queue = deque([start])
            while queue:
                index = queue.popleft()
                i, j = index % self.nx, index // self.nx
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = i + di, j + dj
                    if not (0 <= ni < self.nx and 0 <= nj < self.ny):
                        continue
                    step = nj * self.nx + ni
                    if self.free[step] and labels[step] < 0:
                        labels[step] = count
                        queue.append(step)
            count += 1
        return (tuple(labels), count)

    def components(self) -> int:
        """Merrell's circulation term: how many separate pieces the floor is in."""
        return self.labels()[1]

    def component_areas(self) -> tuple[float, ...]:
        """How much floor each component holds, biggest first."""
        labels, count = self.labels()
        totals = [0] * count
        for label in labels:
            if label >= 0:
                totals[label] += 1
        return tuple(sorted((n * self.cell_area for n in totals), reverse=True))

    def reaches(self, a: Vec2, b: Vec2, *, snap: float = 0.0) -> bool:
        """Can a player walk from ``a`` to ``b`` without leaving free floor?"""
        labels, _ = self.labels()
        first = self._resolve(a, snap)
        second = self._resolve(b, snap)
        if first is None or second is None:
            return False
        return labels[first] == labels[second]

    def links_ok(self, links: Iterable[Link], *, snap: float = 0.0) -> Circulation:
        """Check every required connection and report the floor as a whole.

        The result is always returned, faults or none, because a placer wants
        the component areas whether or not a link broke: one free cell adrift
        behind a shelf is a different message from half the room.
        """
        labels, count = self.labels()
        faults: list[Violation] = []
        for link in links:
            first = self._resolve(link.a, snap)
            second = self._resolve(link.b, snap)
            for end, index, where in (("first", first, link.a), ("second", second, link.b)):
                if index is None:
                    faults.append(
                        Violation(
                            "Circulation",
                            f"link {link.name}: its {end} end at "
                            f"{where[0]:.0f} {where[1]:.0f} is not on free floor",
                            0.0,
                            link.name,
                            "",
                        )
                    )
            if first is None or second is None:
                continue
            if labels[first] != labels[second]:
                held = sum(1 for label in labels if label == labels[first]) * self.cell_area
                faults.append(
                    Violation(
                        "Circulation",
                        f"link {link.name}: {link.a[0]:.0f} {link.a[1]:.0f} is cut off "
                        f"from {link.b[0]:.0f} {link.b[1]:.0f}",
                        held,
                        link.name,
                        "",
                    )
                )
        return Circulation(count, self.component_areas(), tuple(faults))

    def _resolve(self, point: Vec2, snap: float) -> int | None:
        """The flat index of the free cell a link end stands on, snapping if asked."""
        cell = self.cell_at(point)
        if cell is not None and self.free[cell[1] * self.nx + cell[0]]:
            return cell[1] * self.nx + cell[0]
        if snap > 0.0:
            near = self.nearest_free(point, snap)
            if near is not None:
                return near[1] * self.nx + near[0]
        return None


def _is_free(
    cx: float,
    cy: float,
    rects: tuple[tuple[float, float, float, float], ...],
    zones: tuple[tuple[Poly2, tuple[float, float, float, float]], ...],
) -> bool:
    if not any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in rects):
        return False
    for poly, (bx0, by0, bx1, by1) in zones:
        if bx0 <= cx <= bx1 and by0 <= cy <= by1 and poly.holds((cx, cy)):
            return False
    return True


# --------------------------------------------------------------------------
# 3. Emphasis
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Draw:
    """One candidate focal point in a room, with how much it pulls.

    Merrell's wording is "a group S of furniture pieces ... associated with a
    focal point pS".  Ours is the same idea with the point named, because a
    generated room already knows what its draws are: it placed the wall buy,
    it cut the door, it framed the window.
    """

    name: str
    x: float
    y: float
    weight: float = 1.0

    @classmethod
    def of_kind(cls, kind: str, x: float, y: float, name: str = "") -> "Draw":
        """A draw weighted by what it is, per :data:`DRAW_WEIGHT`."""
        return cls(name or kind, float(x), float(y), DRAW_WEIGHT.get(kind, 1.0))

    @property
    def point(self) -> Vec2:
        return (self.x, self.y)


#: What each kind of draw is worth when a room has more than one.  The order
#: is the order a player reads a room in: he walks to the buy, so a wall buy
#: or a perk machine outranks the
#: door he came through, which outranks scenery.  These are weights for
#: choosing between candidates, not scores, so only their order matters.
DRAW_WEIGHT: Mapping[str, float] = {
    "buy": 3.0,
    "perk": 3.0,
    "door": 2.0,
    "window": 1.0,
    "light": 1.0,
}

#: How far outside a room's interior a draw may sit and still be that room's.
#: A wall buy's origin is on the wall plane and a door's is inside the leaf, so
#: a draw is regularly a few units out.  48 is
#: :data:`zmforge.recipes.props.DOOR_FACE_CLEAR`, the depth of the leaf and its
#: standing room, which is as far out as any of them gets.
DRAW_MARGIN = 48.0


def focal_point_of(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    draws: Iterable[Draw],
    *,
    margin: float = DRAW_MARGIN,
) -> Draw | None:
    """The one draw a rectangular room is arranged around, or ``None``.

    The rule, in order: drop the draws that are not in this room (its
    rectangle grown by ``margin``); take the heaviest remaining; break a tie
    on weight by taking the one furthest from the room's centre, because a
    draw you look *across* the room at arranges the room and one in the middle
    of it does not; break a remaining tie by name, so the answer is the same
    on every run.
    """
    lox, hix = (x0, x1) if x0 <= x1 else (x1, x0)
    loy, hiy = (y0, y1) if y0 <= y1 else (y1, y0)
    centre = ((lox + hix) / 2.0, (loy + hiy) / 2.0)
    inside = [
        draw
        for draw in draws
        if lox - margin <= draw.x <= hix + margin and loy - margin <= draw.y <= hiy + margin
    ]
    if not inside:
        return None
    return min(
        inside,
        key=lambda draw: (
            -draw.weight,
            -math.hypot(draw.x - centre[0], draw.y - centre[1]),
            draw.name,
        ),
    )


def focus_score(
    subject: Placed,
    focus: Vec2,
    *,
    front_yaw: float | None = None,
    half_distance: float = 0.0,
) -> float:
    """How well ``subject`` is aimed at ``focus``, from 0 to 1.

    The angle term is ``(1 + cos d) / 2`` where ``d`` is the angle between the
    way the subject faces and the bearing to the focal point: 1 dead on, 0.5
    side on, 0 facing away.  A cosine rather than a step because this is a
    soft score a placer sorts candidates by, and a step would make every yaw
    within the tolerance identical and every yaw outside it worthless.

    ``half_distance``, when given, multiplies in a distance term
    ``h / (h + distance)``: 1 at the focal point and one half at ``h`` from
    it.  It is off by default because emphasis is about facing, and a room
    where the seating has to be *near* the buy as well as aimed at it is a
    different constraint (:class:`~zmforge.placement.relations.Touching`).

    ``front_yaw`` overrides the subject's yaw, for the models whose measured
    front is not their yaw (:data:`zmforge.recipes.props.MODEL_FRONT`).
    """
    yaw = subject.yaw if front_yaw is None else front_yaw
    dx, dy = focus[0] - subject.x, focus[1] - subject.y
    distance = math.hypot(dx, dy)
    if distance <= EPSILON:
        return 1.0  # standing on the draw: every way it faces is toward it
    fx, fy = rotate(1.0, 0.0, yaw)
    cosine = max(-1.0, min(1.0, (fx * dx + fy * dy) / distance))
    score = (1.0 + cosine) / 2.0
    if half_distance > EPSILON:
        score *= half_distance / (half_distance + distance)
    return max(0.0, min(1.0, score))
