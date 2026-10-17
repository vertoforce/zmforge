"""The v2 corn maze layout: twice the field, four bought gates, loops and secrets.

This module only decides *where*
(cells, rooms, zones, gates, clearings, set pieces, shortcuts); the carve is
the shared :func:`zmforge.dressing.maze.carve_maze`.  ``corn_maze.py`` reads
it when the v2 maze is switched on.

The field is :data:`SIZE` x :data:`SIZE` cells of :data:`PITCH` (4,352 units
square, round a 5 x 5 heart; the maze plays best at about
half that area, so the 24 x 24 field of 6,144 square became 17 x 17,
0.50x the area, with the corridors as wide as before).  The ring
round the heart is eight rooms, two to a zone, and the zones follow a spiral
a player buys their way along: entry (east) -> north -> west -> deep (south)
-> the heart, each gate dearer than the last and each a different farm gate
(:data:`GATES`).  Inside a zone the two rooms meet through a few open gaps
(so a zone has more than one way through), every room has loops, and the
dead ends are thinned to :data:`DEAD_END_RATIO` of the cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..dressing.maze import Cell, Maze, Pair, carve_maze, neighbours, pair

SIZE = 17
PITCH = 256.0
HEART = (6, 6, 11, 11)
SEED = "harvest-moon-maze-v2"
#: Extra loops per maze cell after the carve, and the most dead ends kept,
#: as a share of the cells.
LOOP_RATIO = 0.06
#: 0.10 since the 17 x 17 shrink: at 0.08 the deep zone kept one
#: dead end, and the power and the deep ear each need their own.
DEAD_END_RATIO = 0.10
BRANCH_NEWEST = 0.75
#: Open gaps allowed between the two rooms of one zone.
ZONE_GAPS = 3

#: room key -> (zone, cell rectangle (i0, j0, i1, j1), ends exclusive).
ROOMS: dict[str, tuple[str, tuple[int, int, int, int]]] = {
    "mazeentry": ("mazeentry", (11, 0, 17, 6)),
    "mazeentry_b": ("mazeentry", (11, 6, 17, 11)),
    "mazenorth": ("mazenorth", (11, 11, 17, 17)),
    "mazenorth_b": ("mazenorth", (6, 11, 11, 17)),
    "mazewest": ("mazewest", (0, 11, 6, 17)),
    "mazewest_b": ("mazewest", (0, 6, 6, 11)),
    "mazedeep": ("mazedeep", (0, 0, 6, 6)),
    "mazedeep_b": ("mazedeep", (6, 0, 11, 6)),
}
#: The cell the farmyard gate opens into (east edge).
ENTRANCE: Cell = (16, 3)


@dataclass(frozen=True)
class Gate:
    """A bought gate between two zones: the cell pair it opens, its price and
    what it looks like."""

    key: str
    cells: Pair
    price: int
    theme: str


#: The spiral of bought gates, cheapest first.
GATES: tuple[Gate, ...] = (
    Gate("mazenorth", ((14, 10), (14, 11)), 1000, "chained chain-link fence"),
    Gate("mazewest", ((5, 14), (6, 14)), 1250, "rickety farm gate"),
    Gate("mazedeep", ((3, 5), (3, 6)), 1500, "chained chain-link fence"),
    Gate("heart", ((8, 5), (8, 6)), 1750, "barn door on a frame"),
)
#: Clearings: blocks with no walls inside.  Two 2 x 2 fight clearings, the
#: water tower and windmill clearings, and the 3 x 3 "creepy clearing".
CLEARINGS: dict[str, tuple[int, int, int, int]] = {
    "water_tower": (14, 6, 16, 8),
    "windmill": (2, 13, 4, 15),
    "burnt_truck": (13, 14, 15, 16),
    "hay_lookout": (1, 7, 3, 9),
    "creepy_clearing": (3, 1, 6, 4),
}
#: Secret shortcuts: walls whose two sides are at least this many steps
#: apart through the maze, opened for pathing but planted with walk-through
#: corn (no brush), so they look like wall until someone pushes through.
#: 3 and 10 since the 17 x 17 shrink: the half-size field has
#: fewer long detours (5 at 14 found only one).
SECRETS = 3
SECRET_MIN_DETOUR = 10


def room_of(cell: Cell) -> str | None:
    i, j = cell
    for key, (_, (i0, j0, i1, j1)) in ROOMS.items():
        if i0 <= i < i1 and j0 <= j < j1:
            return key
    return None


def zone_of(cell: Cell) -> str | None:
    room = room_of(cell)
    return ROOMS[room][0] if room else None


def cells() -> list[Cell]:
    return [(i, j) for j in range(SIZE) for i in range(SIZE) if room_of((i, j))]


def _gate_pairs() -> set[Pair]:
    return {pair(*g.cells) for g in GATES if g.key != "heart"}


def _allowed(a: Cell, b: Cell) -> bool:
    za, zb = zone_of(a), zone_of(b)
    if za is None or zb is None:
        return False
    return za == zb or pair(a, b) in _gate_pairs()


def _rationed(a: Cell, b: Cell) -> object:
    """Gaps between the two rooms of one zone, rationed per room pair."""
    ra, rb = room_of(a), room_of(b)
    if ra == rb or pair(a, b) in _gate_pairs():
        return None
    return frozenset({ra, rb})


def _blocks() -> list[list[Cell]]:
    return [[(i, j) for i in range(i0, i1) for j in range(j0, j1)]
            for i0, j0, i1, j1 in CLEARINGS.values()]


@lru_cache(maxsize=4)
def carve(seed: str = SEED) -> tuple[Maze, frozenset[Pair]]:
    """The v2 maze and its secret shortcuts (both as passages: a secret is
    open for pathing, dressed as walk-through corn)."""
    heart_gate = next(g for g in GATES if g.key == "heart").cells[0]
    power = _power_cell_hint()
    maze = carve_maze(
        SIZE, SIZE, seed, start=ENTRANCE, cells=cells(), allowed=_allowed, crossing=_rationed,
        max_crossings=ZONE_GAPS, branch_newest=BRANCH_NEWEST, open_blocks=_blocks(),
        loop_ratio=LOOP_RATIO, dead_end_ratio=DEAD_END_RATIO, keep_dead_ends=[power],
        exits=[ENTRANCE, heart_gate],
    )
    maze = _join_rooms(maze)
    dist_cache: dict[Cell, dict[Cell, int]] = {}
    secrets: set[Pair] = set()
    opened = set(maze.passages)
    for a in sorted(maze.cells):
        if len(secrets) >= SECRETS:
            break
        for b in neighbours(a, SIZE, SIZE):
            if b not in maze.cells or pair(a, b) in opened or zone_of(a) != zone_of(b):
                continue
            if any(abs(a[0] - c[0]) + abs(a[1] - c[1]) < 6 for c in secrets_cells(secrets)):
                continue
            d = dist_cache.setdefault(a, maze.distances(a))
            if d.get(b, 0) >= SECRET_MIN_DETOUR and (a[0] * 7 + a[1] * 3) % 5 == 0:
                secrets.add(pair(a, b))
                break
    return Maze(maze.cols, maze.rows, maze.cells, frozenset(opened | secrets)), frozenset(secrets)


def _join_rooms(maze: Maze) -> Maze:
    """Open walls inside a room until the room is connected on its own.

    The carve crosses between the two rooms of a zone, so part of a room can
    be reachable only through its sibling room; the room route check (Z55)
    then finds a doorway of that room cut off inside it.  Each extra opening
    joins two parts of one room (a loop, no dead end lost)."""
    opened = set(maze.passages)
    for key, (_, (i0, j0, i1, j1)) in ROOMS.items():
        cells_ = {(i, j) for i in range(i0, i1) for j in range(j0, j1)}
        while True:
            comp: dict[Cell, int] = {}
            for c in sorted(cells_):
                if c in comp:
                    continue
                comp[c] = len(set(comp.values()))
                stack = [c]
                while stack:
                    x = stack.pop()
                    for nb in neighbours(x, SIZE, SIZE):
                        if nb in cells_ and nb not in comp and pair(x, nb) in opened:
                            comp[nb] = comp[c]
                            stack.append(nb)
            if len(set(comp.values())) <= 1:
                break
            wall = next(pair(a, b) for a in sorted(cells_) for b in neighbours(a, SIZE, SIZE)
                        if b in cells_ and comp[a] == 0 and comp[b] != 0)
            opened.add(wall)
    return Maze(maze.cols, maze.rows, maze.cells, frozenset(opened))


def secrets_cells(secrets: set[Pair]) -> set[Cell]:
    return {c for p in secrets for c in p}


def _power_cell_hint() -> Cell:
    """The far corner of the deep zone, where the power dead end should be."""
    return (0, 0)


def stats(seed: str = SEED) -> dict[str, object]:
    maze, secrets = carve(seed)
    heart_gate = next(g for g in GATES if g.key == "heart").cells[0]
    ends = maze.dead_ends([ENTRANCE, heart_gate])
    far = maze.distances(ENTRANCE)
    return {
        "cells": len(maze.cells), "passages": len(maze.passages), "loops": maze.loops(),
        "dead_ends": len(ends), "secrets": len(secrets), "connected": maze.connected(ENTRANCE),
        "steps_to_heart_gate": far.get(heart_gate), "field_units": SIZE * PITCH,
    }
