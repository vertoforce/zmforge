"""A seeded grid maze: carve, loops, dead-end control, and its wall brushes.

Any map that wants a maze (corn, hedge, catacombs) asks for one here rather
than writing its own carve (zm_corn_maze had the
first).  The maze is a grid of square cells; a *passage* is an
open wall between two neighbouring cells.

* :func:`carve_maze` grows a spanning tree from *start* (a growing-tree carve:
  mostly the newest cell, so long winding corridors, now and then an older
  one, so side branches), opens any blocks asked for (clearings), cuts
  *loops* extra gaps where no dead end is lost, and then, if a
  *dead_end_ratio* is given, braids dead ends open until no more than that
  share of the cells are dead ends.
* :class:`Maze` answers questions about the result: the graph, distances,
  dead ends, how many loops.
* :func:`wall_runs` turns the closed walls inside a cell rectangle into one
  box per straight run, the brushes a recipe lays.

The same seed and arguments always give the same maze.  ``allowed(a, b)``
says whether the wall between two cells may ever open (a room boundary that
only opens at its door), and ``crossing(a, b)`` marks walls whose openings
are rationed to *max_crossings* during the carve (gaps between two rooms of
one zone): it returns a falsy value for an ordinary wall, else a key, and
each key gets its own *max_crossings* (``True`` for one shared ration).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from ..spatial import Bounds

__all__ = ["Cell", "Pair", "Maze", "pair", "neighbours", "carve_maze", "wall_runs"]

Cell = tuple[int, int]
Pair = tuple[Cell, Cell]


def pair(a: Cell, b: Cell) -> Pair:
    """The passage between *a* and *b*, in a fixed order."""
    return (a, b) if a <= b else (b, a)


def neighbours(c: Cell, cols: int, rows: int) -> list[Cell]:
    """The four grid neighbours of *c* inside ``cols x rows`` (E, W, N, S)."""
    return [(c[0] + dx, c[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= c[0] + dx < cols and 0 <= c[1] + dy < rows]


@dataclass(frozen=True)
class Maze:
    """A carved maze: its cells and its open passages."""

    cols: int
    rows: int
    cells: frozenset[Cell]
    passages: frozenset[Pair]

    def graph(self) -> dict[Cell, set[Cell]]:
        g: dict[Cell, set[Cell]] = {c: set() for c in self.cells}
        for a, b in self.passages:
            g[a].add(b)
            g[b].add(a)
        return g

    def distances(self, start: Cell) -> dict[Cell, int]:
        """Steps from *start* to every reachable cell."""
        g = self.graph()
        dist = {start: 0}
        queue = [start]
        for c in queue:
            for nb in sorted(g[c]):
                if nb not in dist:
                    dist[nb] = dist[c] + 1
                    queue.append(nb)
        return dist

    def dead_ends(self, exits: Iterable[Cell] = ()) -> list[Cell]:
        """Cells with one way in; *exits* (cells with a gate out of the maze)
        are not dead ends."""
        skip = set(exits)
        return sorted(c for c, nbs in self.graph().items() if len(nbs) == 1 and c not in skip)

    def loops(self) -> int:
        """Independent cycles: passages beyond a spanning tree."""
        return len(self.passages) - (len(self.cells) - 1)

    def connected(self, start: Cell) -> bool:
        return len(self.distances(start)) == len(self.cells)


def carve_maze(
    cols: int,
    rows: int,
    seed: str | int,
    *,
    start: Cell,
    cells: Iterable[Cell] | None = None,
    allowed: Callable[[Cell, Cell], bool] | None = None,
    crossing: Callable[[Cell, Cell], object] | None = None,
    max_crossings: int = 10**9,
    branch_newest: float = 0.8,
    open_blocks: Sequence[Sequence[Cell]] = (),
    loops: int = 0,
    loop_ratio: float | None = None,
    dead_end_ratio: float | None = None,
    keep_dead_ends: Iterable[Cell] = (),
    exits: Iterable[Cell] = (),
) -> Maze:
    """Carve a maze over *cells* (default: the whole ``cols x rows`` grid).

    *loops* extra gaps are cut after the carve (or ``loop_ratio`` x the cell
    count, if given), each between two cells that already have two ways out,
    so no dead end is lost to a loop.  *dead_end_ratio*, if given, then opens
    dead ends (never those in *keep_dead_ends*) into a neighbour, preferring
    one that is also a dead end, until at most that share of cells are dead
    ends or no more can be opened.  *exits* are cells with a gate out of the
    maze, which never count as dead ends.
    """
    rng = random.Random(seed)
    inside = frozenset(cells) if cells is not None else frozenset(
        (i, j) for j in range(rows) for i in range(cols))
    if start not in inside:
        raise ValueError(f"start {start} is not a maze cell")
    ok = allowed or (lambda a, b: True)
    rationed = crossing or (lambda a, b: None)

    def may(a: Cell, b: Cell) -> bool:
        return b in inside and ok(a, b)

    opened: set[Pair] = set()
    seen = {start}
    stack = [start]
    crossings: dict[object, int] = {}
    while stack:
        at = len(stack) - 1 if rng.random() < branch_newest else rng.randrange(len(stack))
        c = stack[at]
        options = [nb for nb in neighbours(c, cols, rows) if nb not in seen and may(c, nb)
                   and (not rationed(c, nb) or crossings.get(rationed(c, nb), 0) < max_crossings)]
        if not options:
            stack.pop(at)
            continue
        nxt = rng.choice(options)
        key = rationed(c, nxt)
        if key:
            crossings[key] = crossings.get(key, 0) + 1
        opened.add(pair(c, nxt))
        seen.add(nxt)
        stack.append(nxt)
    for block in open_blocks:
        for a in block:
            for b in block:
                if a < b and abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
                    opened.add(pair(a, b))
    degree: dict[Cell, int] = {}
    for a, b in opened:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    closed = sorted({pair(a, b) for a in inside for b in neighbours(a, cols, rows)
                     if may(a, b) and pair(a, b) not in opened})
    rng.shuffle(closed)
    want = loops if loop_ratio is None else round(loop_ratio * len(inside))
    added = 0
    for a, b in closed:
        if added >= want:
            break
        if degree.get(a, 0) >= 2 and degree.get(b, 0) >= 2:
            opened.add((a, b))
            degree[a] += 1
            degree[b] += 1
            added += 1
    if dead_end_ratio is not None:
        keep = set(keep_dead_ends) | set(exits)
        limit = dead_end_ratio * len(inside)
        ends = sorted(c for c in inside if degree.get(c, 0) == 1 and c not in keep)
        rng.shuffle(ends)
        count = sum(1 for c in inside if degree.get(c, 0) == 1 and c not in set(exits))
        for c in ends:
            if count <= limit:
                break
            if degree.get(c, 0) != 1:
                continue
            options = [nb for nb in neighbours(c, cols, rows)
                       if may(c, nb) and not rationed(c, nb) and pair(c, nb) not in opened]
            if not options:
                continue
            both = [nb for nb in options if degree.get(nb, 0) == 1 and nb not in keep]
            nb = rng.choice(both or options)
            opened.add(pair(c, nb))
            count -= 1 + (1 if degree.get(nb, 0) == 1 and nb not in set(exits) else 0)
            degree[c] += 1
            degree[nb] = degree.get(nb, 0) + 1
    return Maze(cols, rows, inside, frozenset(opened))


def wall_runs(
    passages: frozenset[Pair],
    rect: tuple[int, int, int, int],
    origin: tuple[float, float],
    pitch: float,
    wall: float,
    floor_z: float,
    height: float,
    clip: Bounds | None = None,
) -> list[Bounds]:
    """The wall brushes inside the cell rectangle ``(i0, j0, i1, j1)`` (ends
    exclusive): one box per straight run of closed walls on the cell lattice,
    clipped to *clip* (the room's interior; its own walls do the rest).
    North-south runs go the full length of the run and over its end posts;
    east-west runs stop at their faces, so nothing overlaps."""
    i0, j0, i1, j1 = rect
    x0, y0 = origin
    p, h, top = pitch, wall / 2.0, floor_z + height
    if clip is None:
        clip = Bounds.between((x0 + i0 * p, y0 + j0 * p, floor_z), (x0 + i1 * p, y0 + j1 * p, top))
    ix0, iy0, ix1, iy1 = clip.mins.x, clip.mins.y, clip.maxs.x, clip.maxs.y

    def runs(items: list[int]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for v in sorted(items):
            if out and v == out[-1][1] + 1:
                out[-1] = (out[-1][0], v)
            else:
                out.append((v, v))
        return out

    boxes: list[Bounds] = []
    covered: set[tuple[int, int]] = set()
    for k in range(i0 + 1, i1):
        rows_ = [j for j in range(j0, j1) if pair((k - 1, j), (k, j)) not in passages]
        lx = x0 + k * p
        for ja, jb in runs(rows_):
            ya, yb = max(iy0, y0 + ja * p - h), min(iy1, y0 + (jb + 1) * p + h)
            boxes.append(Bounds.between((lx - h, ya, floor_z), (lx + h, yb, top)))
            covered.update((k, m) for m in range(ja, jb + 2))
    for k in range(j0 + 1, j1):
        cols_ = [i for i in range(i0, i1) if pair((i, k - 1), (i, k)) not in passages]
        ly = y0 + k * p
        for ia, ib in runs(cols_):
            xa, xb = max(ix0, x0 + ia * p - h), min(ix1, x0 + (ib + 1) * p + h)
            cuts = sorted(x0 + m * p for m in range(ia, ib + 2) if (m, k) in covered)
            start = xa
            for cx in cuts + [math.inf]:
                end = min(xb, cx - h)
                if end - start > 1.0:
                    boxes.append(Bounds.between((start, ly - h, floor_z), (end, ly + h, top)))
                start = max(start, cx + h)
                if start >= xb:
                    break
    return boxes
