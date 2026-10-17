"""Z78: after a sealed start resolves, nothing respawns a player in a sealed zone.

A *sealed start* (:mod:`zmforge.script.splitstart`) begins every player in a
zone of their own that no floor or door leaves; a script teleport is the only
way out, and once it has happened those zones are closed for good.  The trap
this guards against: clearing ``level.check_for_valid_spawn_near_team_callback`` once
the opening resolved, handing respawns back to the stock pick.  The stock
pick finds no point on a zmforge map (its ``player_respawn_point`` has no
``target``, ``_zm.gsc:3453``) and falls back to ``self.spectator_respawn``
(``_zm.gsc:3282``, ``:3315``), which is the player's initial spawn struct
(``_zm_gametype.gsc:552``) -- in their sealed hallway.  Left alone, every
player killed by the button comes back in the hallway they had just left.

So this reads the written server script and map, and for a map that has a
sealed start asks that every respawn source is closed or re-pointed:

* the respawn callback is never cleared;
* after the hallways phase, the spawn choice returns a hub point;
* the resolution re-points every player's ``spectator_respawn`` (the stock
  fallback) at a hub point;
* the close disables every sealed zone (``is_enabled`` and
  ``is_spawning_allowed`` false, ``_zm_zonemgr.gsc:299``, ``:307``), which is
  also what makes ``check_for_valid_spawn_near_team`` skip any respawn point
  in them (``_zm.gsc`` ``check_point_in_enabled_zone``);
* the spawn hook moves anyone found in a sealed zone after resolution;
* no ``player_respawn_point`` struct stands inside a sealed zone's volume.

A reading of the text, not an observation of play.
"""

from __future__ import annotations

import re

from .report import Report, error

__all__ = ["CODE", "sealed_zones", "check_sealed_start"]

CODE = "Z78"

_HALL_ZONE = re.compile(r's_hall\.zone\s*=\s*"([^"]+)"\s*;')


def _function_body(script: str, name: str) -> str | None:
    """The text between ``function <name>(...)``'s braces, or None."""
    m = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", script)
    if m is None:
        return None
    depth, i = 1, m.end()
    while i < len(script) and depth:
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
        i += 1
    return script[m.end(): i - 1]


def sealed_zones(script: str) -> list[str]:
    """The sealed start zones a written script declares (empty: no sealed start)."""
    init = _function_body(script, "zmf_split_init")
    if init is None:
        return []
    return _HALL_ZONE.findall(init)


def _code(text: str) -> str:
    """Drop ``//`` comments so a quoted line in a comment does not count."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def check_sealed_start(document, script: str, report: Report | None = None) -> Report:
    """Z78 over a parsed map and its server script; a no-op without a sealed start."""
    report = report if report is not None else Report()
    zones = sealed_zones(script)
    if not zones:
        return report
    code = _code(script)

    def fail(message: str) -> None:
        report.add(error(CODE, f"sealed start: {message}"))

    if re.search(r"level\.check_for_valid_spawn_near_team_callback\s*=\s*undefined", code):
        fail("the respawn callback is cleared; the stock respawn then falls back to "
             "the player's initial spawn struct in their sealed zone (_zm.gsc:3282, "
             ":3315; _zm_gametype.gsc:552)")
    if "level.check_for_valid_spawn_near_team_callback = &zmf_split_spawn_point;" not in code:
        fail("the respawn callback is never set, so respawns take the stock pick")

    where = _code(_function_body(script, "zmf_split_where") or "")
    tail = where[where.rfind("}") + 1:] if "}" in where else where
    if "zmf_split_hub_point()" not in tail:
        fail("after the hallways phase the spawn choice does not return a hub point")

    finish = _code(_function_body(script, "zmf_split_finish") or "")
    if not re.search(r"\.spectator_respawn\s*=\s*zmf_split_hub_point\(\s*\)\s*;", finish):
        fail("the resolution does not re-point each player's spectator_respawn (the "
             "stock fallback, _zm.gsc:3282) at a hub point")

    close = _code(_function_body(script, "zmf_split_close") or "")
    for field in ("is_enabled", "is_spawning_allowed"):
        if f"level.zones[ s_hall.zone ].{field} = false;" not in close:
            fail(f"the close leaves the sealed zones' {field} set, so their respawn "
                 "and spawn points stay live")

    spawned = _code(_function_body(script, "zmf_split_on_spawned") or "")
    if "zmf_split_in_hall()" not in spawned:
        fail("the spawn hook does not move a player found in a sealed zone after "
             "the opening resolved")

    if document is not None:
        from .files import _brush_bounds, _origin_of

        volumes: dict[str, list] = {}
        for entity in document.entities_of("info_volume"):
            if entity.value("script_noteworthy") != "player_volume":
                continue
            box = _brush_bounds(entity)
            if box is not None:
                volumes.setdefault(entity.value("targetname"), []).append(box)
        for entity in document.entities_of("script_struct"):
            if entity.value("targetname") != "player_respawn_point":
                continue
            origin = _origin_of(entity)
            if origin is None:
                continue
            for zone in zones:
                if any(box.holds(origin, tolerance=1.0) for box in volumes.get(zone, ())):
                    fail(f"a player_respawn_point at ({origin.x:g}, {origin.y:g}, "
                         f"{origin.z:g}) stands in the sealed zone {zone!r}")
    return report
