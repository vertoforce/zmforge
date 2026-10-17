"""Which zones a quest step needs open before it may start (P8).

A step whose targets, items, hint or boss stand in a zone behind a door must
not start, show its task or run its timer until that zone is open: zm_dmv's
Vision Test started at game start with its 15-second timer while the eye exam
room was four doors in.

The stock signal is the zone manager's own: ``enable_zone`` sets
``level.zones[ zone_name ].is_enabled = true`` when a door's flag opens the
zone (``_zm_zonemgr.gsc:488-499``), and ``zone_is_enabled( zone_name )``
(``_zm_zonemgr.gsc:65-73``) reads it.

Pure functions over plain data, so the quest generator (over a live
blueprint) and the Z61 check (over a live blueprint or the stored model
document) ask the same question the same way.
"""

from __future__ import annotations

from typing import Iterable, Sequence

__all__ = ["ZoneBox", "open_at_start", "door_opened", "initial_zones", "zone_at", "step_gates"]

#: ``(name, x0, x1, y0, y1, z0, z1)``: a zone's volume.
ZoneBox = tuple[str, float, float, float, float, float, float]


def open_at_start(starting: Iterable[str], edges: Iterable[tuple[str, str, str]],
                  always_on: str = "always_on") -> set[str]:
    """Zones enabled without any door: the starting zones and every zone
    joined to one by an ``always_on`` edge (set at load, before any door)."""
    open_ = set(starting)
    edges = list(edges)
    grew = True
    while grew:
        grew = False
        for a, b, flag in edges:
            if flag == always_on and (a in open_) != (b in open_):
                open_ |= {a, b}
                grew = True
    return open_


def door_opened(starting: Iterable[str], edges: Iterable[tuple[str, str, str]],
                door_flags: Iterable[str], always_on: str = "always_on") -> set[str]:
    """Zones a player can open by buying doors: reachable from the open ones
    over door and ``always_on`` edges.  A zone only a script flag opens (a
    scripted ride, a quest reward) is not here: gating a step on it could wait
    for the step itself."""
    flags = set(door_flags) | {always_on}
    reach = open_at_start(starting, edges, always_on)
    edges = list(edges)
    grew = True
    while grew:
        grew = False
        for a, b, flag in edges:
            if flag in flags and (a in reach) != (b in reach):
                reach |= {a, b}
                grew = True
    return reach


def _joined(roots: Iterable[str], edges: list[tuple[str, str, str]]) -> set[str]:
    """Every zone some chain of edges (any flag) joins to ``roots``."""
    reach = set(roots)
    grew = True
    while grew:
        grew = False
        for a, b, _flag in edges:
            if (a in reach) != (b in reach):
                reach |= {a, b}
                grew = True
    return reach


def initial_zones(zones: Sequence[str], starting: str | None,
                  edges: Iterable[tuple[str, str, str]],
                  always_on: str = "always_on") -> list[str]:
    """The ``init_zones`` list: the zones the zone manager enables at load.

    Stock ``manage_zones`` calls ``zone_init`` and ``enable_zone`` on every
    entry (``_zm_zonemgr.gsc:841-844``), so a zone listed here is open at
    game start whatever doors stand in front of it: every
    ``zone_is_enabled`` wait on it passes at once and its respawn points
    unlock at load (every zmforge map listed
    every zone).  Treyarch lists one: ``zm_giant.gsc:183``.

    So: the starting zone, the zones an ``always_on`` edge joins to it (open
    at load anyway), and a zone no door leads into from there (a sealed
    spawn room that the script puts players into).  Each such root is added in ``zones`` order,
    and only if no chain of edges from the roots already reaches it, so a
    zone behind a door is never listed.
    """
    edges = list(edges)
    if not zones:
        return []
    start = starting if starting in zones else zones[0]
    open_ = open_at_start([start], edges, always_on)
    listed = [start] + [z for z in zones if z != start and z in open_]
    reach = _joined(listed, edges)
    for zone in zones:
        if zone not in reach:
            listed.append(zone)
            reach = _joined(listed, edges)
    return listed


def zone_at(point: Sequence[float], boxes: Sequence[ZoneBox]) -> str | None:
    """The zone holding ``point``: by plan, and by height where two stack."""
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    flat = [b for b in boxes if b[1] <= x <= b[2] and b[3] <= y <= b[4]]
    if len(flat) > 1:
        tall = [b for b in flat if b[5] - 16.0 <= z <= b[6] + 16.0]
        flat = tall or flat
    return flat[0][0] if flat else None


def step_gates(points: Iterable[Sequence[float]], boxes: Sequence[ZoneBox],
               closed: set[str]) -> tuple[str, ...]:
    """The closed zones ``points`` stand in, sorted, once each."""
    return tuple(sorted({z for p in points if (z := zone_at(p, boxes)) in closed}))
