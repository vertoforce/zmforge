"""Flood the walkable floor from the spawns and report what nobody reaches.

A room can satisfy every local rule in this package -- nothing overlapping,
every fixture on a wall, every clearance kept -- and still hand the player a
strip of floor behind a bank of shelving that no route joins to anything.  No
spacing rule between pairs of props prevents that.  Requiring a gap between
every pair of solid props takes the collision off a bank standing flat against
a wall, which blocks nothing.  Requiring it only where two banks meet removes
most of a room's solid props and can still leave floor sealed, because one
bank standing a little off a wall traps the strip behind it without making a
corner at all.  Connectivity is not a property of any pair of props.  It is a
property of the whole floor, and the only way to know it is to walk it.

So this module walks it, before the compiler does.  It is the general form of
``props._open_the_pockets``, lifted out of the placer and given the two things
the placer's private copy has no use for:

* it **reports** rather than deletes.  ``_open_the_pockets`` takes props out
  until the floor floods; a check wants to know what is stranded, where it is,
  how big it is, and whether anything that matters is standing on it;
* it takes **off-mesh links**.  A climb, a drop or a jump joins two pieces of
  floor that are nowhere near grid-adjacent, and the only honest way to know
  one exists is for whatever built it to say so.

The vocabulary matches ``zmforge.verify.reachability`` (``Z25``), which does
the same job on the finished model: *reached*, *unreached*, one-way links, and
an unreached floor patch being a lesser finding than an unreached thing.  The
difference is when and on what.  ``Z25`` runs on the compiled model and is
exact; this runs on a grid of plan polygons while the placer still has the
chance to move something, and a grid is approximate on purpose (see
:data:`WALK_CELL`).

**Attribution.**  Flood-from-declared-seeds and discard-what-is-not-reached is
navcat's ``floodFillNavMesh`` (isaac-mason/navcat, MIT), whose implementation
is JavaScript and none of which is copied here; declaring a jump as an
explicit pair of markers the generator emits, rather than inferring one later,
is smix8/Godot_3D_Navigation_Jump_Links (MIT).  Both are public projects.

Nothing here is wired into the placer or into ``verify``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .geometry import EPSILON, Poly2, Vec2
from .relations import Placed, Surface

__all__ = [
    "WALK_CELL",
    "WALK_MARGIN",
    "MAX_CELLS",
    "ERROR",
    "REPORT",
    "grown",
    "WalkGrid",
    "Link",
    "Island",
    "Reach",
    "Required",
    "Finding",
    "flood",
    "check_required",
]

#: The grid the flood works on, in units.  Taken from
#: ``props.POCKET_CELL``, which is the same 16 and is the one number in this
#: module measured against a built map.  Two reasons it is 16 and not finer:
#: the ``.map`` writer's own grid is 8, so 16 is two of its steps and nothing
#: smaller can be expressed as a distinct position anyway; and a room here is
#: a few hundred units across, so 16 puts a room at a few hundred cells and
#: the whole flood at well under a millisecond.
WALK_CELL = 16.0

#: How far every blocking footprint is grown before the flood runs.  The
#: navmesh generator's own corridor width is 31 units (``N2``), so a gap this
#: flood is allowed to squeeze through has to be at least that wide or the
#: compiler will refuse to lay surface in it.  Growing each blocker by 16 on
#: every side means a gap has to measure 32 clear units to survive, which is
#: the first multiple of the grid above 31.  The number was arrived at by
#: being burnt without it: ``props.POCKET_MARGIN``'s comment records the flood
#: walking through 16-unit gaps the compiler then refused, and calling a
#: sealed corner open.  Measured on the grid this module builds, with both
#: margins taken and a cell centre needed in what is left, a gap of 48 units
#: or under across a room is shut and 64 is a route; which way a gap in
#: between falls depends on where it lands on the grid, and it falls shut.
WALK_MARGIN = 16.0

#: Refuse to build a grid bigger than this.  500 by 500 cells at 16 units is
#: 8,000 units square, which is larger than any room this generator builds, so
#: hitting the cap means a cell size was mistyped rather than a map being big.
#: ``_open_the_pockets`` has the same guard at 40,000 cells per room; this is
#: higher because it is handed whole floors, not one room at a time.
MAX_CELLS = 250_000

#: A finding that fails a build: something the map needs is not reachable.
ERROR = "error"

#: A finding worth printing that does not fail a build.  ``Z25`` calls the
#: same thing a warning; the word here is "report" because this runs while the
#: layout can still be changed, and dead floor with nothing on it costs only
#: the lighting.
REPORT = "report"


def grown(poly: Poly2, margin: float) -> Poly2:
    """``poly`` grown by ``margin`` on every side: its sum with a square.

    A square and not the disc of :func:`~zmforge.placement.geometry.minkowski_disc`,
    for one reason: the square contains the disc, so every error this makes is
    in the direction of calling a tight gap blocked rather than open.  That is
    the safe direction here.  The compiler decides what is walkable and a
    flood that claims a route the compiler will not lay is the failure mode
    :data:`WALK_MARGIN` exists to prevent; a flood that calls a marginal gap
    shut merely reports an island somebody can look at.
    """
    if margin <= 0.0:
        return poly
    offsets = ((-margin, -margin), (margin, -margin), (margin, margin), (-margin, margin))
    return Poly2.of(
        (px + dx, py + dy) for px, py in poly.points for dx, dy in offsets
    )


def _floor_plan(shape: Poly2 | Surface) -> Poly2:
    if isinstance(shape, Poly2):
        return shape
    if isinstance(shape, Surface):
        return shape.poly
    raise TypeError(f"{shape!r} is not a Poly2 or a Surface")


def _blocker_plan(shape: Poly2 | Placed) -> Poly2 | None:
    """The plan a blocker blocks, or ``None`` when it blocks nothing.

    A :class:`~zmforge.placement.relations.Placed` with ``solid=False`` is a
    prop whose collision has been taken off, and the player walks through it,
    so it does not block.  How *tall* a thing has to be before it stops a
    player is not decided here -- that is ``Z25``'s question, on the model
    that actually has heights in it -- so the caller passes the props that
    stand in the way and this takes them at their word.
    """
    if isinstance(shape, Placed):
        return shape.footprint if shape.solid else None
    if isinstance(shape, Poly2):
        return shape
    raise TypeError(f"{shape!r} is not a Poly2 or a Placed")


@dataclass(frozen=True, slots=True)
class WalkGrid:
    """A floor cut into square cells, each one open or shut.

    The grid is anchored to world coordinates rather than to the floor it was
    built from: ``x0`` and ``y0`` are the floor's minimum snapped **down** to
    a multiple of ``cell``.  That is what makes two grids over overlapping
    floors agree about where a cell is, and it means extending a room by a
    unit does not move every cell in it.
    """

    cell: float
    x0: float
    y0: float
    nx: int
    ny: int
    open: tuple[bool, ...]

    # -- construction ----------------------------------------------------
    @classmethod
    def build(
        cls,
        floors: Iterable[Poly2 | Surface],
        blockers: Iterable[Poly2 | Placed] = (),
        *,
        cell: float = WALK_CELL,
        margin: float = WALK_MARGIN,
        max_cells: int = MAX_CELLS,
    ) -> "WalkGrid":
        """Cells over ``floors``, minus ``blockers`` grown by ``margin``.

        A cell is open when its **centre** is inside a floor polygon and
        inside no grown blocker.  Centre and not coverage, because a rule of
        "any part of the cell" walks through walls and a rule of "all of the
        cell" refuses to walk down a corridor that is not grid-aligned.  The
        cost of the choice is that the flood's idea of the floor is out by up
        to half a cell at an edge, which is 8 units, which is the ``.map``
        writer's grid.

        The floors are taken as given.  How wide a *doorway* in the world
        geometry has to be is ``W2``'s question and this does not duplicate
        it; ``margin`` is about props standing on the floor, which is the
        thing nothing else measures before the compile.
        """
        if cell <= EPSILON:
            raise ValueError(f"cell size {cell} is not a usable grid")
        plans = tuple(_floor_plan(f) for f in floors)
        plans = tuple(p for p in plans if len(p.points) >= 3)
        if not plans:
            return cls(cell, 0.0, 0.0, 0, 0, ())

        lox = min(p.bounds[0] for p in plans)
        loy = min(p.bounds[1] for p in plans)
        hix = max(p.bounds[2] for p in plans)
        hiy = max(p.bounds[3] for p in plans)
        x0 = math.floor(lox / cell) * cell
        y0 = math.floor(loy / cell) * cell
        nx = max(1, math.ceil((hix - x0) / cell - EPSILON))
        ny = max(1, math.ceil((hiy - y0) / cell - EPSILON))
        if nx * ny > max_cells:
            raise ValueError(
                f"a {nx} by {ny} grid is {nx * ny} cells, over the {max_cells} cap; "
                f"the cell size is {cell}"
            )

        state = bytearray(nx * ny)
        for plan in plans:
            for i, j in _cells_over(plan, x0, y0, nx, ny, cell):
                if plan.holds(_centre(x0, y0, cell, i, j)):
                    state[j * nx + i] = 1
        for blocker in blockers:
            plan = _blocker_plan(blocker)
            if plan is None or len(plan.points) < 2:
                continue
            wide = grown(plan, margin)
            if len(wide.points) < 3:
                continue
            for i, j in _cells_over(wide, x0, y0, nx, ny, cell):
                if state[j * nx + i] and wide.holds(_centre(x0, y0, cell, i, j)):
                    state[j * nx + i] = 0
        return cls(cell, x0, y0, nx, ny, tuple(bool(v) for v in state))

    def with_only(self, keep: Iterable[int]) -> "WalkGrid":
        """The same grid with every cell outside ``keep`` shut."""
        wanted = set(keep)
        return WalkGrid(
            self.cell, self.x0, self.y0, self.nx, self.ny,
            tuple(k in wanted for k in range(self.nx * self.ny)),
        )

    # -- cells -----------------------------------------------------------
    @property
    def size(self) -> int:
        return self.nx * self.ny

    @property
    def cell_area(self) -> float:
        return self.cell * self.cell

    @property
    def open_cells(self) -> tuple[int, ...]:
        return tuple(k for k in range(self.size) if self.open[k])

    @property
    def open_area(self) -> float:
        return sum(1 for v in self.open if v) * self.cell_area

    def is_open(self, index: int) -> bool:
        return 0 <= index < self.size and self.open[index]

    def centre_of(self, index: int) -> Vec2:
        if not 0 <= index < self.size:
            raise IndexError(f"cell {index} is not in a {self.nx} by {self.ny} grid")
        return _centre(self.x0, self.y0, self.cell, index % self.nx, index // self.nx)

    def index_of(self, point: Vec2) -> int | None:
        """The cell a point falls in, or ``None`` when it is off the grid.

        A point exactly on the far edge is pulled into the last cell rather
        than falling off the grid: a buy flat against the north wall of a room
        whose depth is a multiple of the cell lands exactly on the boundary,
        and it is in the room.
        """
        i = _axis_index(point[0], self.x0, self.cell, self.nx)
        j = _axis_index(point[1], self.y0, self.cell, self.ny)
        if i is None or j is None:
            return None
        return j * self.nx + i

    def neighbours(self, index: int) -> tuple[int, ...]:
        """The four cells sharing an edge with this one, inside the grid.

        Four and not eight.  A diagonal step crosses a corner where two
        blockers meet at a point, and the navmesh generator will not lay a
        surface through that corner, so counting it would be exactly the
        "called a sealed corner open" mistake :data:`WALK_MARGIN` records.
        """
        i, j = index % self.nx, index // self.nx
        out = []
        if i > 0:
            out.append(index - 1)
        if i + 1 < self.nx:
            out.append(index + 1)
        if j > 0:
            out.append(index - self.nx)
        if j + 1 < self.ny:
            out.append(index + self.nx)
        return tuple(out)


def _centre(x0: float, y0: float, cell: float, i: int, j: int) -> Vec2:
    return (x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell)


def _axis_index(value: float, origin: float, cell: float, count: int) -> int | None:
    index = int(math.floor((value - origin) / cell))
    if index == count and value - (origin + count * cell) <= EPSILON:
        index = count - 1
    if index == -1 and (origin - value) <= EPSILON:
        index = 0
    return index if 0 <= index < count else None


def _cells_over(
    plan: Poly2, x0: float, y0: float, nx: int, ny: int, cell: float
) -> Iterable[tuple[int, int]]:
    """Every cell whose centre could be inside ``plan``, by its bounds."""
    bx0, by0, bx1, by1 = plan.bounds
    i_low = max(0, int(math.floor((bx0 - x0) / cell)))
    i_high = min(nx - 1, int(math.floor((bx1 - x0) / cell)))
    j_low = max(0, int(math.floor((by0 - y0) / cell)))
    j_high = min(ny - 1, int(math.floor((by1 - y0) / cell)))
    for j in range(j_low, j_high + 1):
        for i in range(i_low, i_high + 1):
            yield i, j


@dataclass(frozen=True, slots=True)
class Link:
    """An off-mesh connection: two points a player gets between without walking.

    A climb, a jump across a gap, a drop off a balcony.  The flood traverses
    it as an extra edge, and the pair of points is **declared** by whatever
    built the route rather than inferred from the geometry, which is the whole
    idea taken from the jump-link marker plugin: a scene that stacks two
    crates into a climb emits the link at the same time, so nothing downstream
    has to guess that the stack was meant to be climbed.

    ``one_way`` is a drop.  A balcony you can fall off and not climb back onto
    is reachable from above and not from below, and ``Z25`` treats a fall the
    same way for the same reason.
    """

    a: Vec2
    b: Vec2
    kind: str = "jump"
    name: str = ""
    one_way: bool = False

    def hops(self) -> tuple[tuple[Vec2, Vec2], ...]:
        """The directed hops this link offers."""
        return ((self.a, self.b),) if self.one_way else ((self.a, self.b), (self.b, self.a))


@dataclass(frozen=True, slots=True)
class Island:
    """A patch of open floor the flood never reached.

    ``point`` is a real point on the island -- the centre of one of its own
    cells -- and not the centroid of its outline, because a U-shaped island's
    centroid is in the middle of the prop that stranded it, and a number
    somebody is meant to type into a console has to be somewhere they can
    stand.
    """

    cells: tuple[int, ...]
    area: float
    point: Vec2


@dataclass(frozen=True, slots=True)
class Reach:
    """What one flood found.

    Walk-reached and link-reached are kept apart on purpose.  "You can get
    there" and "you can get there if you make the jump" are different claims
    about a map, and the second one is worth saying out loud when it is a perk
    machine on the far side.
    """

    grid: WalkGrid
    walked: frozenset[int]
    linked: frozenset[int]
    islands: tuple[Island, ...]
    lost_seeds: tuple[Vec2, ...] = ()
    lost_links: tuple[Link, ...] = ()
    crossed: tuple[Link, ...] = ()

    @property
    def reached(self) -> frozenset[int]:
        return self.walked | self.linked

    @property
    def unreached(self) -> tuple[int, ...]:
        return tuple(k for k in self.grid.open_cells if k not in self.reached)

    @property
    def reached_area(self) -> float:
        return len(self.reached) * self.grid.cell_area

    @property
    def island_area(self) -> float:
        return sum(island.area for island in self.islands)

    def how_reached(self, point: Vec2) -> str:
        """One of ``walk``, ``link``, ``island``, ``blocked``, ``outside``.

        ``blocked`` is a point standing on a cell a prop's margin shut, which
        is a different fault from ``island``: the floor there is not stranded,
        it is occupied.
        """
        index = self.grid.index_of(point)
        if index is None:
            return "outside"
        if not self.grid.is_open(index):
            return "blocked"
        if index in self.walked:
            return "walk"
        if index in self.linked:
            return "link"
        return "island"

    def island_at(self, point: Vec2) -> Island | None:
        index = self.grid.index_of(point)
        if index is None:
            return None
        for island in self.islands:
            if index in island.cells:
                return island
        return None

    def prune(self) -> WalkGrid:
        """The grid navcat would keep: every cell the flood did not reach, shut.

        This is the destructive form of the same answer the rest of this class
        reports.  Nothing in this package calls it -- a generator that deletes
        the floor under a stranded perk machine has hidden the fault rather
        than fixed it -- but it is the honest expression of "and delete
        everything the flood does not reach", and it is what a caller building
        a navmesh hint volume from the result wants.
        """
        return self.grid.with_only(self.reached)


def flood(
    grid: WalkGrid,
    seeds: Iterable[Vec2],
    links: Iterable[Link] = (),
) -> Reach:
    """Flood ``grid`` from ``seeds``, then across ``links``, and report.

    The seeds are the places a body appears: the player spawns and the zombie
    risers.  Seeding from those and not from the middle of each room is the
    point -- the question is not "is this floor connected to itself" but "is
    this floor connected to where the game puts people".

    Two passes, in this order.  Everything walkable from a seed is found
    first, so a cell that a link could also reach is still recorded as
    walk-reached; then each link whose near end has been reached opens its far
    end and the walk spreads from there, repeating until nothing new opens.  A
    seed or a link end standing on a shut cell is not snapped to the nearest
    open one -- that would invent a route -- it is reported in ``lost_seeds``
    or ``lost_links``.

    O(cells) in the flood, plus O(links) per round.
    """
    grid_seeds = tuple((float(x), float(y)) for x, y in seeds)
    starts: list[int] = []
    lost_seeds: list[Vec2] = []
    for seed in grid_seeds:
        index = grid.index_of(seed)
        if index is None or not grid.is_open(index):
            lost_seeds.append(seed)
            continue
        starts.append(index)

    walked = _spread(grid, starts)
    reached = set(walked)

    every_link = tuple(links)
    lost_links = tuple(
        link for link in every_link
        if any(not _lands_open(grid, end) for end in (link.a, link.b))
    )
    crossed: list[Link] = []
    spreading = True
    while spreading:
        spreading = False
        for link in every_link:
            for here, there in link.hops():
                near = grid.index_of(here)
                far = grid.index_of(there)
                if near is None or far is None:
                    continue
                if near not in reached or not grid.is_open(far) or far in reached:
                    continue
                reached |= _spread(grid, [far])
                if link not in crossed:
                    crossed.append(link)
                spreading = True

    stranded = [k for k in grid.open_cells if k not in reached]
    islands = _islands(grid, stranded)
    return Reach(
        grid=grid,
        walked=frozenset(walked),
        linked=frozenset(reached - walked),
        islands=islands,
        lost_seeds=tuple(lost_seeds),
        lost_links=lost_links,
        crossed=tuple(crossed),
    )


def _lands_open(grid: WalkGrid, point: Vec2) -> bool:
    """Is this point on a cell of open floor?"""
    index = grid.index_of(point)
    return index is not None and grid.is_open(index)


def _spread(grid: WalkGrid, starts: Sequence[int]) -> set[int]:
    """Every open cell edge-connected to one of ``starts``, ``starts`` included."""
    seen: set[int] = set()
    stack: list[int] = []
    for start in starts:
        if grid.is_open(start) and start not in seen:
            seen.add(start)
            stack.append(start)
    while stack:
        index = stack.pop()
        for neighbour in grid.neighbours(index):
            if neighbour not in seen and grid.open[neighbour]:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def _islands(grid: WalkGrid, stranded: Sequence[int]) -> tuple[Island, ...]:
    """``stranded`` cut into edge-connected components, biggest first."""
    left = set(stranded)
    found: list[Island] = []
    for start in stranded:  # index order in, so the components come out stably
        if start not in left:
            continue
        cells: list[int] = []
        stack = [start]
        left.discard(start)
        while stack:
            index = stack.pop()
            cells.append(index)
            for neighbour in grid.neighbours(index):
                if neighbour in left:
                    left.discard(neighbour)
                    stack.append(neighbour)
        cells.sort()
        found.append(
            Island(
                cells=tuple(cells),
                area=len(cells) * grid.cell_area,
                point=_middle_cell(grid, cells),
            )
        )
    found.sort(key=lambda island: (-island.area, island.point))
    return tuple(found)


def _middle_cell(grid: WalkGrid, cells: Sequence[int]) -> Vec2:
    """The centre of whichever cell sits nearest the middle of the patch."""
    centres = [grid.centre_of(k) for k in cells]
    mx = sum(c[0] for c in centres) / len(centres)
    my = sum(c[1] for c in centres) / len(centres)
    best = min(
        range(len(cells)),
        key=lambda n: (math.hypot(centres[n][0] - mx, centres[n][1] - my), cells[n]),
    )
    return centres[best]


@dataclass(frozen=True, slots=True)
class Required:
    """Something the map needs a player to be able to walk up to.

    A wall buy, a barricade, a riser, a door, a perk machine.  ``kind`` is
    free text and is carried into the finding so the report can say *buy* or
    *riser* rather than *thing*.
    """

    name: str
    x: float
    y: float
    kind: str = "required"

    @property
    def point(self) -> Vec2:
        return (self.x, self.y)

    @classmethod
    def at(cls, name: str, point: Vec2, kind: str = "required") -> "Required":
        return cls(name, float(point[0]), float(point[1]), kind)


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the flood found, with the numbers that say how bad it is.

    Structured and not a printed line, because a ``verify`` check will consume
    these: it needs the severity to decide whether to fail, the position to
    print, and the area to sort by.  ``__str__`` is for the eventual report
    only and nothing should parse it.
    """

    kind: str
    name: str
    x: float
    y: float
    area: float = 0.0
    severity: str = ERROR
    detail: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR

    @property
    def position(self) -> str:
        """``x y``, formatted as the layout checks print a position."""
        return f"{self.x:.0f} {self.y:.0f}"

    def __str__(self) -> str:
        who = f"{self.name} " if self.name else ""
        return f"{who}{self.detail} at {self.position}"


#: Findings come back in this order: errors before reports, and within a
#: severity the biggest island first, so a report that gets truncated is
#: truncated from the least interesting end.
_SEVERITY_ORDER = (ERROR, REPORT)


def check_required(
    reach: Reach,
    required: Iterable[Required | Placed] = (),
) -> tuple[Finding, ...]:
    """Judge a flood: what is stranded, and does anything stand on it.

    The rule, in one sentence: a required thing the seeds cannot reach is an
    **error**, and a patch of floor the seeds cannot reach with nothing
    required on it is a **report**.  Dead floor costs the lighting; a wall buy
    on the far side of a bank of lockers costs the round.

    Four kinds come back:

    ``required-on-island``
        error.  The thing stands on floor that is walkable and stranded;
    ``required-blocked``
        error, and a different repair.  The thing stands where a prop's own
        margin shut the floor, or off the walkable floor altogether, so there
        is no island to join up -- something is standing in it, or it is in a
        wall;
    ``required-by-link``
        report.  Reached, but only by taking a jump or a climb.  Legitimate,
        and worth saying out loud before somebody finds out in a round;
    ``island``
        report.  Stranded floor with nothing required on it, carrying its
        area and a point on it.

    An island that carries a required thing reports the error and not also an
    ``island`` line, so one fault is one finding.
    """
    wanted = tuple(_as_required(item) for item in required)
    findings: list[Finding] = []
    spoken_for: set[int] = set()

    for item in wanted:
        where = reach.how_reached(item.point)
        if where == "walk":
            continue
        if where == "link":
            findings.append(Finding(
                kind="required-by-link",
                name=item.name,
                x=item.x,
                y=item.y,
                severity=REPORT,
                detail=f"{item.kind} is reachable only across a link",
            ))
            continue
        if where == "island":
            island = reach.island_at(item.point)
            area = island.area if island is not None else 0.0
            if island is not None:
                spoken_for.update(island.cells)
            findings.append(Finding(
                kind="required-on-island",
                name=item.name,
                x=item.x,
                y=item.y,
                area=area,
                severity=ERROR,
                detail=(
                    f"{item.kind} stands on {area:,.0f} square units of floor "
                    f"no spawn reaches"
                ),
            ))
            continue
        findings.append(Finding(
            kind="required-blocked",
            name=item.name,
            x=item.x,
            y=item.y,
            severity=ERROR,
            detail=(
                f"{item.kind} stands on blocked floor"
                if where == "blocked"
                else f"{item.kind} stands off the walkable floor"
            ),
        ))

    for island in reach.islands:
        if any(cell in spoken_for for cell in island.cells):
            continue
        findings.append(Finding(
            kind="island",
            name="",
            x=island.point[0],
            y=island.point[1],
            area=island.area,
            severity=REPORT,
            detail=f"{island.area:,.0f} square units of floor no spawn reaches",
        ))

    findings.sort(key=lambda f: (
        _SEVERITY_ORDER.index(f.severity) if f.severity in _SEVERITY_ORDER else len(_SEVERITY_ORDER),
        -f.area,
        f.kind,
        f.name,
        f.x,
        f.y,
    ))
    return tuple(findings)


def _as_required(item: Required | Placed) -> Required:
    if isinstance(item, Required):
        return item
    if isinstance(item, Placed):
        return Required(item.name, item.x, item.y, "prop")
    raise TypeError(f"{item!r} is not a Required or a Placed")
