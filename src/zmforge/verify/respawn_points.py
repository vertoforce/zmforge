"""Z86: every respawn struct has a group of points a player can stand on.

The stock respawn pick (``_zm.gsc:3361 check_for_valid_spawn_near_team``)
chooses the ``player_respawn_point`` nearest a living team mate and then reads
``struct::get_array( spawn_points[closest_group].target, "targetname" )``
(``:3453``).  No ``target``, or a target naming nothing, and the pick returns
``undefined``: the player comes back at their own initial spawn struct
(``spectator_respawn``, ``:3282``, ``:3315``), wherever the team is.  A point
inside a wall puts them in the wall.  And the pick skips a struct whose
origin is outside every enabled zone (``:3397``), and a struct unlocks only
when the zone its ``script_noteworthy`` names does (``_zm_zonemgr.gsc:504``).

Two halves:

* :func:`check_respawn_points` reads the written map: every struct has a
  target, the target names at least one struct, no point of it is inside a
  colliding brush, and the struct stands inside the ``player_volume`` its
  ``script_noteworthy`` names;
* :func:`check_respawn_reach` reads the blueprint with the ``Z25`` flood:
  every point of every group stands on floor the flood reaches, and every
  unsealed zone with reachable floor has a group (a warning).
"""

from __future__ import annotations

from ..spatial import Point, Span
from .report import Report, error, warning

__all__ = ["CODE", "check_respawn_points", "check_respawn_reach"]

CODE = "Z86"

#: Heights above a point's floor that are probed for a brush, and the
#: offsets across it: the middle of a 30-unit hull and its four corners.
_HEIGHTS = (8.0, 36.0, 64.0)
_ACROSS = ((0.0, 0.0), (-14.0, -14.0), (-14.0, 14.0), (14.0, -14.0), (14.0, 14.0))
_EPS = 0.01


def _planes(solid):
    """Inward-normal planes of a brush: ``(B - A) x (C - A)`` points into
    the solid (``mapsource.document.Facet``)."""
    out = []
    for facet in solid.facets:
        a, b, c = facet.points
        u = (b.x - a.x, b.y - a.y, b.z - a.z)
        v = (c.x - a.x, c.y - a.y, c.z - a.z)
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        length = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
        if length == 0.0:
            continue
        n = (n[0] / length, n[1] / length, n[2] / length)
        out.append((n, n[0] * a.x + n[1] * a.y + n[2] * a.z))
    return out


def _colliding_brushes(document):
    from ..mapsource.document import BrushSolid

    owners = [document.worldspawn] if document.worldspawn is not None else []
    owners += document.entities_of("script_brushmodel")
    brushes = []
    for owner in owners:
        if owner is None:
            continue
        for solid in owner.solids:
            if not isinstance(solid, BrushSolid) or not solid.facets:
                continue
            if any("noncolliding" in c.lower() for c in solid.contents):
                continue
            points = [p for f in solid.facets for p in f.points]
            box = Span.flat_ok(
                Point(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)),
                Point(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)),
            )
            brushes.append((box, solid))
    return brushes


def _inside(point: Point, planes) -> bool:
    return all(n[0] * point.x + n[1] * point.y + n[2] * point.z - d > _EPS for n, d in planes)


def _blocked(spot: Point, brushes, cache: dict) -> bool:
    probes = [Point(spot.x + dx, spot.y + dy, spot.z + h) for h in _HEIGHTS for dx, dy in _ACROSS]
    for box, solid in brushes:
        if not any(box.holds(p) for p in probes):
            continue
        planes = cache.get(id(solid))
        if planes is None:
            planes = cache[id(solid)] = _planes(solid)
        if any(_inside(p, planes) for p in probes):
            return True
    return False


def check_respawn_points(document, report: Report | None = None) -> Report:
    """Z86 over a parsed map (see the module docstring)."""
    from .files import _brush_bounds, _origin_of

    report = report if report is not None else Report()
    structs = document.entities_of("script_struct")
    by_name: dict[str, list] = {}
    for entity in structs:
        by_name.setdefault(entity.value("targetname") or "", []).append(entity)
    volumes: dict[str, list[Span]] = {}
    for entity in document.entities_of("info_volume"):
        if entity.value("script_noteworthy") == "player_volume":
            box = _brush_bounds(entity)
            if box is not None:
                volumes.setdefault(entity.value("targetname") or "", []).append(box)
    brushes = None
    cache: dict = {}
    for entity in by_name.get("player_respawn_point", []):
        origin = _origin_of(entity)
        where = f"({origin.x:g}, {origin.y:g}, {origin.z:g})" if origin else "(no origin)"
        zone = entity.value("script_noteworthy") or ""
        target = entity.value("target")
        if not target:
            report.add(error(CODE, f"the player_respawn_point for zone {zone!r} at {where} "
                                   "has no target, so the stock respawn pick finds no point "
                                   "and a bled-out player comes back at their initial spawn "
                                   "(_zm.gsc:3453, :3282)"))
            continue
        group = by_name.get(target, [])
        if not group:
            report.add(error(CODE, f"the player_respawn_point for zone {zone!r} targets "
                                   f"{target!r}, which names no struct"))
            continue
        if origin is not None and not any(b.holds(origin, tolerance=1.0)
                                          for b in volumes.get(zone, ())):
            report.add(error(CODE, f"the player_respawn_point at {where} is not inside the "
                                   f"player_volume {zone!r} its script_noteworthy names, so "
                                   "it never unlocks or is skipped (_zm.gsc:3397)"))
        if brushes is None:
            brushes = _colliding_brushes(document)
        for point in group:
            spot = _origin_of(point)
            if spot is None:
                report.add(error(CODE, f"a point of {target!r} has no origin"))
            elif _blocked(spot, brushes, cache):
                report.add(error(CODE, f"respawn point ({spot.x:g}, {spot.y:g}, {spot.z:g}) of "
                                       f"{target!r} is inside a colliding brush: a player "
                                       "respawned there is stuck"))
    return report


def check_respawn_reach(blueprint, flood, report: Report) -> None:
    """Z86 over the blueprint: each group's points stand on floor the
    ``Z25`` flood reaches; each unsealed zone the flood enters has a group."""
    from ..blueprint.elements import PlayerStart, Zone
    from ..blueprint.respawn import respawn_groups

    starts = blueprint.elements(PlayerStart)
    if not starts:
        return
    groups = respawn_groups(blueprint)
    from ..blueprint.respawn import STOCK_POINTS

    for group in groups:
        if len(group.points) < STOCK_POINTS:
            report.add(warning(CODE, f"zone {group.zone!r} has room for only "
                                     f"{len(group.points)} respawn points; more players "
                                     "than that respawn on one another", starts[0].id))
        for p in group.points:
            if flood.under(p.x, p.y, p.z, only_reached=True) is None:
                report.add(error(CODE, f"respawn point ({p.x:g}, {p.y:g}, {p.z:g}) of zone "
                                       f"{group.zone!r} is on no floor a player can walk to "
                                       "from the spawn", starts[0].id))
    have = {g.zone for g in groups}
    sealed = set(getattr(starts[0], "sealed_zones", ()) or ())
    from .reachability import _inside

    for zone in blueprint.elements(Zone):
        if zone.bounds is None or zone.name in have or zone.name in sealed:
            continue
        if any(_inside(zone.bounds, flood.cells[i]) for i in flood.reached):
            have.add(zone.name)
            report.add(warning(CODE, f"zone {zone.name!r} has reachable floor and no respawn "
                                     "group: a player who bleeds out there comes back in "
                                     "another zone", zone.id))
