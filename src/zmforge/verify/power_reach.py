"""Z80: a door that waits for the power never stands between spawn and power.

A door can stay shut until the power is on: an ``electric`` one opens by
itself then, a ``requires_power`` one is sold only then (the stock
``electric_door`` and ``electric_buyable_door``).  If every way from the spawn
to the power switch goes through such a door, nobody can ever turn the power
on and the map is a softlock (cemetery: the first door waits
for the power, so the groundskeeper's shed must be reachable without it).

The walk goes from every starting zone over the zone edges: an ``always_on``
edge, a door that can be bought before the power, or a flag no door owns
(opened by a script, not by the power) is passable; a power-gated door is not.
It fails only when the power-gated doors are what cut the way: a switch no
edge leads to at all is another check's business.
"""

from __future__ import annotations

from collections import defaultdict

from .report import Report, error

__all__ = ["CODE", "check_power_reach", "zones_before_power"]

CODE = "Z80"


def zones_before_power(bp, *, gated_open: bool = False) -> set[str]:
    """The zones a player can walk into before the power is on (all of them
    reachable at all with ``gated_open``)."""
    from ..blueprint.elements import Door, Zone

    gated = {door.flag for door in bp.elements(Door) if door.flag and door.power_gated}
    buyable = {door.flag for door in bp.elements(Door) if door.flag and not door.power_gated}
    links: dict[str, set[str]] = defaultdict(set)
    for edge in bp.script.edges:
        if not gated_open and edge.flag in gated and edge.flag not in buyable:
            continue
        links[edge.zone_a].add(edge.zone_b)
        links[edge.zone_b].add(edge.zone_a)
    seen = {z.name for z in bp.elements(Zone) if z.starting}
    todo = list(seen)
    while todo:
        for other in links[todo.pop()]:
            if other not in seen:
                seen.add(other)
                todo.append(other)
    return seen


def check_power_reach(bp) -> Report:
    """``Z80`` over a blueprint: the power switch is reachable without the power."""
    from ..blueprint.elements import Door
    from ..dressing.power_bolts import _power_zone

    report = Report()
    if not any(door.power_gated for door in bp.elements(Door)):
        return report
    zone = _power_zone(bp)
    if zone is None:
        return report
    if zone in zones_before_power(bp) or zone not in zones_before_power(bp, gated_open=True):
        return report
    gated = sorted(door.id for door in bp.elements(Door) if door.power_gated)
    report.add(error(
        CODE,
        f"the power switch's zone {zone!r} is reachable only through doors that wait for "
        f"the power ({', '.join(gated)}): nobody can turn the power on (a softlock); "
        "open a way to the switch that needs no power"))
    return report
