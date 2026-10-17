"""Walkable rolling ground: heightfields a player and a zombie can cross.

:meth:`zmforge.blueprint.model.Blueprint.add_terrain` lays any heightfield as
a mesh, and :class:`~zmforge.surfaces.relief.Relief` flattens pads under door
sills.  Neither says anything about whether the result can be *walked*: a
noise field with a large enough peak puts a 60-unit rise across one cell, the
reachability flood (``Z25``, :mod:`zmforge.verify.reachability`) links two
terrain cells only when the rise between their standing heights is at most
:data:`~zmforge.verify.reachability.JUMP_UP` (39), and the pads Relief lays
are hard edges: a pad at 0 in the middle of a hill is a pit with a cliff
round it.

This module is the missing half, written for any recipe with outdoor ground
(the cemetery's hills, a farm's fields):

* :class:`Mound` -- one smooth hill or hollow, in world coordinates.
* :func:`rolling_hills` -- a field of mounds plus optional noise, on the grid
  :meth:`add_terrain` wants.
* :func:`limit_rise` -- the guarantee: after it, no two neighbouring control
  points (8-neighbourhood) differ by more than ``max_rise``, so no cell of
  the mesh rises more than ``max_rise`` corner to corner.  Pinned cells --
  pads, sills, plateaus -- keep their height and the ground around them is
  graded to meet them instead of dropping off a ledge.
* :func:`pin_discs` -- the pinned cells for a set of flat discs (door sills,
  building plateaus), the same shape Relief's ``Pad`` flattens.
* :func:`slope_report` -- what a finished field actually does: the largest
  neighbour rise, the largest cell relief, the steepest grade.
* :func:`lowest_under` / :func:`highest_under` -- the ground under a
  footprint on a finished :class:`~zmforge.surfaces.ground.TerrainRecord`,
  which is what a brush or a prop standing on a slope has to be seated on.

**The numbers.**  ``max_rise`` defaults to :data:`DEFAULT_MAX_RISE` (18, the
navmesh step height): on an 82-unit cell that is a grade of 0.22 (12
degrees), under the navmesh's ``MAX_WALKABLE_SLOPE`` of 46 degrees
(:mod:`zmforge.verify.documented`) and under the 39-unit player jump, so a
cell is walked, never jumped, by players and zombies alike.  A caller may
raise it toward ``JUMP_UP`` for ground only players cross, and ``Z46`` will
say where the walkers are cut off.  **Unverified in
play:** how the zombies' navmesh treats a long 14-degree slope (the navmesh
check ``Z24``-series reads the built mesh; see :mod:`zmforge.verify.navmesh`).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..spatial import Point
from .field import HeightField
from .noise import fractal_field

__all__ = [
    "DEFAULT_MAX_RISE",
    "Mound",
    "Disc",
    "SlopeReport",
    "rolling_hills",
    "pin_discs",
    "limit_rise",
    "cap_pins",
    "slope_report",
    "lowest_under",
    "highest_under",
    "scatter_mounds",
]

#: Largest height difference allowed between two neighbouring control points
#: unless the caller says otherwise: the navmesh generator's own
#: ``maxStepHeight`` (:data:`zmforge.verify.documented.MAX_STEP_HEIGHT`, 18,
#: from the mod tools' ``default_navmesh_settings.json``).  The model checks
#: judge a terrain cell as two flat patches at its lowest and highest corner,
#: so a rise over 18 between cells reads as a step the walkers cannot take
#: (``Z46``) even where the real slope is gentle; at 18 per ~82-unit cell
#: the ground is a 12-degree slope and both the players' and the walkers'
#: floods cross it.
DEFAULT_MAX_RISE = 18.0


@dataclass(frozen=True)
class Mound:
    """A smooth bump (``height`` > 0) or hollow (< 0) centred on ``(x, y)``.

    The profile is a raised cosine: full height at the centre, zero and flat
    at ``radius``, so two mounds overlap without a crease.
    """

    x: float
    y: float
    radius: float
    height: float

    def at(self, x: float, y: float) -> float:
        d = math.hypot(x - self.x, y - self.y)
        if d >= self.radius:
            return 0.0
        return self.height * 0.5 * (1.0 + math.cos(math.pi * d / self.radius))


@dataclass(frozen=True)
class Disc:
    """A flat disc of ground at ``height`` (heightfield units, above the
    anchor), e.g. a door sill or the plateau a building stands on.  A disc
    whose ``square`` is true pins the whole square of side ``2*radius``."""

    x: float
    y: float
    radius: float
    height: float = 0.0
    square: bool = False

    def covers(self, x: float, y: float) -> bool:
        if self.square:
            return abs(x - self.x) <= self.radius and abs(y - self.y) <= self.radius
        return math.hypot(x - self.x, y - self.y) <= self.radius


@dataclass(frozen=True)
class SlopeReport:
    """What a finished field does to someone walking over it."""

    max_neighbour_rise: float
    max_cell_relief: float
    max_grade: float
    highest: float
    lowest: float


def _grid_point(anchor: Point, cell_x: float, cell_y: float, row: int, col: int) -> tuple[float, float]:
    return anchor.x + col * cell_x, anchor.y + row * cell_y


def rolling_hills(
    anchor: Point,
    cols: int,
    rows: int,
    cell: float,
    *,
    mounds: Sequence[Mound] = (),
    noise_peak: float = 0.0,
    seed: int = 0,
    base: float = 0.0,
    cell_y: float | None = None,
) -> HeightField:
    """A heightfield of ``mounds`` over ``base``, plus fractal noise.

    Control point ``(row, col)`` sits at world ``anchor + (col*cell,
    row*cell_y)``, which is how :class:`~zmforge.surfaces.ground.TerrainRecord`
    reads it.  Heights never go below zero (a terrain with a cell under its
    floor is refused by Relief and would hang below the room floor).
    """
    if cols < 2 or rows < 2:
        raise ValueError("a heightfield needs at least 2 x 2 control points")
    down = cell if cell_y is None else cell_y
    noise = fractal_field(rows, cols, seed=seed, octaves=3, peak=noise_peak) if noise_peak else None
    out: list[list[float]] = []
    for row in range(rows):
        line = []
        for col in range(cols):
            x, y = _grid_point(anchor, cell, down, row, col)
            h = base + sum(m.at(x, y) for m in mounds)
            if noise is not None:
                h += noise.at(row, col)
            line.append(max(0.0, h))
        out.append(line)
    return HeightField.from_rows(out)


def pin_discs(
    anchor: Point, field: HeightField, cell: float, discs: Iterable[Disc],
    *, cell_y: float | None = None,
) -> dict[tuple[int, int], float]:
    """The control points each disc covers, mapped to the disc's height.

    A disc that covers no control point pins the nearest one, so a door sill
    narrower than a cell still gets flat ground in front of it.
    """
    down = cell if cell_y is None else cell_y
    pinned: dict[tuple[int, int], float] = {}
    for disc in discs:
        hit = False
        for row in range(field.rows):
            for col in range(field.cols):
                x, y = _grid_point(anchor, cell, down, row, col)
                if disc.covers(x, y):
                    pinned[(row, col)] = disc.height
                    hit = True
        if not hit:
            col = min(max(round((disc.x - anchor.x) / cell), 0), field.cols - 1)
            row = min(max(round((disc.y - anchor.y) / down), 0), field.rows - 1)
            pinned[(row, col)] = disc.height
    return pinned


def cap_pins(pinned: dict[tuple[int, int], float], max_rise: float = DEFAULT_MAX_RISE
             ) -> dict[tuple[int, int], float]:
    """Lower every pin that stands too far above a nearby lower pin.

    Two pins ``n`` cells apart (Chebyshev) can differ by at most
    ``n * max_rise`` for :func:`limit_rise` to grade between them.  A plateau
    asked for near a door sill is lowered to the height the ground can climb
    to by then, rather than refused: the caller asked for "a hilltop here",
    and the tallest hilltop that fits is the answer.  Pins are only ever
    lowered, so a sill at 0 stays at 0.
    """
    pins = dict(pinned)
    keys = sorted(pins, key=lambda k: pins[k])
    changed = True
    while changed:
        changed = False
        for low in keys:
            for high in keys:
                steps = max(abs(low[0] - high[0]), abs(low[1] - high[1]))
                limit = pins[low] + steps * max_rise
                if steps and pins[high] > limit + 1e-9:
                    pins[high] = limit
                    changed = True
    return pins


_NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def limit_rise(
    field: HeightField,
    max_rise: float = DEFAULT_MAX_RISE,
    *,
    pinned: dict[tuple[int, int], float] | None = None,
    max_passes: int = 400,
) -> HeightField:
    """Grade ``field`` so no two 8-neighbours differ by more than ``max_rise``.

    Pinned points are set to their height and never moved.  Every other point
    is first raised to within the grade of every pin above it (so a plateau
    gets a ramp up to it rather than a cliff), then lowered to within the
    grade of every neighbour (so a sill at 0 in a hill becomes a graded
    bowl).  ``ValueError`` if two pins are closer together than their height
    difference allows, which no grading could fix (:func:`cap_pins` lowers
    such pins instead).
    """
    if max_rise <= 0.0:
        raise ValueError("max_rise must be positive")
    pins = dict(pinned or {})
    for (r0, c0), h0 in pins.items():
        for (r1, c1), h1 in pins.items():
            steps = max(abs(r0 - r1), abs(c0 - c1))
            if steps and abs(h0 - h1) > steps * max_rise + 1e-6:
                raise ValueError(
                    f"pins at {(r0, c0)} ({h0:g}) and {(r1, c1)} ({h1:g}) are {steps} "
                    f"cells apart, too close for a rise of {max_rise:g} per cell"
                )
    rows, cols = field.rows, field.cols
    h = [list(line) for line in field.as_lists()]
    for (r, c), value in pins.items():
        h[r][c] = value

    # Raise: nothing may sit further below a pin than the grade allows.
    for r in range(rows):
        for c in range(cols):
            if (r, c) in pins:
                continue
            floor = max(
                (value - max_rise * max(abs(r - pr), abs(c - pc))
                 for (pr, pc), value in pins.items()),
                default=h[r][c],
            )
            if h[r][c] < floor:
                h[r][c] = floor
    # Lower: the min-plus closure, which never undercuts the raise above
    # (a neighbour already obeys it one cell further out).
    for _ in range(max_passes):
        changed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in pins:
                    continue
                for dr, dc in _NEIGHBOURS:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols:
                        ceiling = h[rr][cc] + max_rise
                        if h[r][c] > ceiling + 1e-9:
                            h[r][c] = ceiling
                            changed = True
        if not changed:
            break
    else:  # pragma: no cover - monotone and bounded, so it settles
        raise ValueError("grading did not settle")
    for r in range(rows):
        for c in range(cols):
            h[r][c] = max(0.0, h[r][c])
    return HeightField.from_rows(h)


def slope_report(field: HeightField, cell: float, cell_y: float | None = None) -> SlopeReport:
    """The largest neighbour rise, cell relief and grade in ``field``."""
    down = cell if cell_y is None else cell_y
    rows, cols = field.rows, field.cols
    rise = relief = grade = 0.0
    for r in range(rows):
        for c in range(cols):
            here = field.at(r, c)
            for dr, dc in _NEIGHBOURS:
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols:
                    diff = abs(field.at(rr, cc) - here)
                    rise = max(rise, diff)
                    run = math.hypot(dc * cell, dr * down)
                    grade = max(grade, diff / run)
            if r + 1 < rows and c + 1 < cols:
                corners = (here, field.at(r, c + 1), field.at(r + 1, c), field.at(r + 1, c + 1))
                relief = max(relief, max(corners) - min(corners))
    return SlopeReport(rise, relief, grade, field.highest, field.lowest)


def _samples(record, x0: float, y0: float, x1: float, y1: float, step: float = 16.0):
    nx = max(1, int(math.ceil((x1 - x0) / step)))
    ny = max(1, int(math.ceil((y1 - y0) / step)))
    for i in range(nx + 1):
        for j in range(ny + 1):
            yield record.sample(x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny)


def lowest_under(record, x0: float, y0: float, x1: float, y1: float) -> float:
    """World Z of the lowest ground under the footprint, sampled every 16
    units; a solid seated here has no gap under any of its corners."""
    found = [s.z for s in _samples(record, x0, y0, x1, y1) if s.found]
    if not found:
        raise ValueError(f"footprint ({x0:g},{y0:g})..({x1:g},{y1:g}) is off the terrain")
    return min(found)


def highest_under(record, x0: float, y0: float, x1: float, y1: float) -> float:
    """World Z of the highest ground under the footprint."""
    found = [s.z for s in _samples(record, x0, y0, x1, y1) if s.found]
    if not found:
        raise ValueError(f"footprint ({x0:g},{y0:g})..({x1:g},{y1:g}) is off the terrain")
    return max(found)


def scatter_mounds(
    x0: float, y0: float, x1: float, y1: float, count: int, *,
    radius: tuple[float, float], height: tuple[float, float], seed: int,
    avoid: Sequence[Disc] = (),
) -> list[Mound]:
    """``count`` mounds at seeded random spots in a rectangle, none centred
    inside an ``avoid`` disc (a door, a building)."""
    rng = random.Random(seed)
    out: list[Mound] = []
    tries = 0
    while len(out) < count and tries < count * 50:
        tries += 1
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        r = rng.uniform(*radius)
        if any(math.hypot(x - d.x, y - d.y) < d.radius + r * 0.5 for d in avoid):
            continue
        out.append(Mound(x, y, r, rng.uniform(*height)))
    return out
