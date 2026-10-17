"""Z61: no quest step starts before players can reach it (P8).

A step whose points (its targets, items, desk, hint, zone or boss; see
:func:`zmforge.script.quest.step_points`) stand in a zone behind a door must
wait for that zone (``Step.zones``), or its task, start line and timer run
while the room is shut: zm_dmv's Vision Test started at game start with a
15-second timer and the eye exam room four doors in.  A warning per step and
zone.  A point in a zone that no door opens (a script flag does, e.g. a
scripted ride) is a warning too: the generator cannot gate on it without
risking a step that waits for itself, so a person has to look.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from ..script.zonegate import ZoneBox, door_opened, open_at_start, zone_at
from .report import Report, warning

__all__ = ["check_quest_gates", "check_quest_gates_blueprint", "check_quest_gates_document"]


def check_quest_gates(boxes: Sequence[ZoneBox], gated: set[str], script_only: set[str],
                      steps: Iterable[Mapping]) -> Report:
    """``steps``: dicts with ``label``, ``points`` and ``gates``."""
    report = Report()
    for step in steps:
        gates = set(step.get("gates", ()))
        seen: set[str] = set()
        for point in step.get("points", ()):
            zone = zone_at(point, boxes)
            if zone is None or zone in seen:
                continue
            seen.add(zone)
            where = "(" + ", ".join(f"{float(c):g}" for c in point) + ")"
            if zone in gated and zone not in gates:
                report.add(warning(
                    "Z61", f"{step['label']}: a point at {where} is in zone {zone!r}, behind a "
                    "door, and the step does not wait for it (it starts, shows its task and runs "
                    "its timer while the room is shut)", position=where))
            elif zone in script_only and zone not in gates:
                report.add(warning(
                    "Z61", f"{step['label']}: a point at {where} is in zone {zone!r}, which no "
                    "door opens (a script flag does); check the step cannot start before it "
                    "is open", position=where))
    return report


def check_quest_gates_blueprint(blueprint) -> Report:
    """Z61 over a live blueprint (what ``install_quest`` recorded)."""
    steps = getattr(blueprint, "quest_steps", None)
    if not steps:
        return Report()
    from ..script.quest import blueprint_zone_gates

    boxes, gated, script_only = blueprint_zone_gates(blueprint)
    return check_quest_gates(boxes, gated, script_only, steps)


def check_quest_gates_document(document: Mapping) -> Report:
    """Z61 over a stored model document, for ``zmforge check``."""
    steps = (document.get("engine") or {}).get("quest_steps") or []
    if not steps:
        return Report()
    editor = document.get("editor") or {}
    script = document.get("script") or {}
    zones = editor.get("zones") or []
    boxes = [(z["name"], z["x0"], z["x1"], z["y0"], z["y1"], z["z0"], z["z1"]) for z in zones]
    edges = [(e["zone_a"], e["zone_b"], e["flag"]) for e in script.get("edges") or []]
    starting = [z["name"] for z in zones if z.get("starting")]
    always_on = script.get("always_on_flag", "always_on")
    flags = [d["flag"] for d in editor.get("doors") or [] if d.get("flag")]
    open_ = open_at_start(starting, edges, always_on)
    doors = door_opened(starting, edges, flags, always_on)
    return check_quest_gates(boxes, doors - open_, {z["name"] for z in zones} - doors, steps)
