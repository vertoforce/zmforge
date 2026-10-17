"""Z56-Z58: how a map looks: three faults that renders keep showing.

Each of these was fixed by hand on one map after a render showed it, then
turned up again on the next map.  They are asked of every map now, and they
are **warnings**: a look fault does not stop
a map playing, and ``Project.commit`` refuses a map on any error.

``Z56`` flat lettering on the floor
    Words laid flat on the floor read as grey planks from eye height in every
    render.  Hang it
    (:func:`zmforge.dressing.hanging_sign`) or letter a wall.
``Z57`` a solid prop in front of a barricade window
    A zombie climbs in through the window and drops to the floor in front of
    it; a crate or a heap there blocks the way in and the rebuild
    (on zm_corn_maze, a farmhouse pile 45 units off the west window, inside a
    keep-out that only cleared corn).  The clear zone is the opening's width plus
    :data:`WINDOW_SIDE` each side, :data:`WINDOW_APPROACH` either side of the
    wall, from a step over the floor to the opening's top.
``Z58`` a model on the deny-list, or measured to draw dark, blank or not at all
    :data:`zmforge.props.reads_badly.READS_BADLY`: models a render review
    named as something they are not (the aerofarm sign as another farm).
    Also every ``props/notes.json`` model entry whose ``renders`` is
    ``dark``, ``blank`` or ``editor_invisible`` with ``confidence:
    measured`` (:data:`RENDER_FAULTS`): the preview will show it wrong, so a
    reviewer should not "fix" it and a recipe should know what it gets.
    One warning per model per map, with the count.
``Z59`` a prop without the partner it needs
    ``needs`` in ``props/notes.json`` (a model's own, or a category's by its
    ``pattern``), for the needs a blueprint can answer (:data:`JUDGED_NEEDS`):
    a curtain with no rail along its top (drapes hung from nothing), a desk
    monitor with nothing under it.  Other needs
    (``chair_facing``, ``legs``, free text) are not judged here: a chair
    model's front is not known from its box.  ``Z60``
    (:mod:`zmforge.verify.prop_rules`) judges them from a measured front
    and the ``rules`` block instead.
"""

from __future__ import annotations

from collections import defaultdict

from ..spatial import Side
from .report import Report, warning

__all__ = [
    "FLOOR_LETTERING_BAND",
    "WINDOW_APPROACH",
    "WINDOW_SIDE",
    "STEP",
    "check_looks",
    "check_floor_lettering",
    "check_window_approaches",
    "check_reads_badly",
    "check_needs",
    "JUDGED_NEEDS",
    "RENDER_FAULTS",
    "window_zones",
]

#: Flat lettering whose top is within this of its room's floor is "on the
#: floor".  A step's height: a label flat on a desk or a plinth is not asked.
FLOOR_LETTERING_BAND = 18.0
#: How far either side of the wall a barricade window's clear zone reaches: a
#: zombie's climb-through and drop, plus the player standing to rebuild.
WINDOW_APPROACH = 64.0
#: How far past each side of the opening the zone runs along the wall.
WINDOW_SIDE = 16.0
#: A prop no taller than this is stepped over (the Z53 step).
STEP = 18.0


def check_looks(blueprint) -> Report:
    """Every look rule that can be measured: ``Z56``, ``Z57``, ``Z58``."""
    report = Report()
    report.extend(check_floor_lettering(blueprint))
    report.extend(check_window_approaches(blueprint))
    report.extend(check_reads_badly(blueprint))
    report.extend(check_needs(blueprint))
    from .boundary import check_boundary_walls

    report.extend(check_boundary_walls(blueprint))
    from .boundary import check_facades

    report.extend(check_facades(blueprint))
    from .scenes import check_scenes

    report.extend(check_scenes(blueprint))
    from .evenness import check_foliage_evenness

    report.extend(check_foliage_evenness(blueprint))
    return report


def _room_at(rooms, x: float, y: float, z: float):
    """The room whose interior holds (x, y) with its floor nearest under z."""
    best = None
    for room in rooms:
        box = room.interior
        if not (box.mins.x <= x <= box.maxs.x and box.mins.y <= y <= box.maxs.y):
            continue
        if room.floor_z > z + 1.0:
            continue
        if best is None or room.floor_z > best.floor_z:
            best = room
    return best


def _lettering_groups(blueprint):
    """``ident -> (text, [boxes])`` for every brush-lettered sign."""
    from ..blueprint.elements import Massing

    groups: dict[str, tuple[str, list]] = {}
    for element in blueprint.elements(Massing):
        note = element.note or ""
        if not note.startswith("lettering:") or element.authored is None:
            continue
        ident = element.id.rsplit("_", 1)[0]
        text = note.split(":", 1)[1].strip()
        groups.setdefault(ident, (text, []))[1].append(element.authored.box)
    return groups


def check_floor_lettering(blueprint) -> Report:
    """Z56, a warning per lettered sign laid flat on the floor or the ground."""
    from ..blueprint.elements import Room

    report = Report()
    rooms = list(blueprint.elements(Room))
    for ident, (text, boxes) in sorted(_lettering_groups(blueprint).items()):
        flat = [b for b in boxes
                if (b.maxs.z - b.mins.z) * 2.0 < min(b.maxs.x - b.mins.x, b.maxs.y - b.mins.y)]
        if not flat or len(flat) < len(boxes):
            continue
        x0 = min(b.mins.x for b in flat)
        x1 = max(b.maxs.x for b in flat)
        y0 = min(b.mins.y for b in flat)
        y1 = max(b.maxs.y for b in flat)
        top = max(b.maxs.z for b in flat)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        room = _room_at(rooms, cx, cy, top)
        if room is not None:
            if top - room.floor_z > FLOOR_LETTERING_BAND:
                continue
            where = f"on the floor of {room.id}"
        else:
            # Outside every room: on terrain or a yard.  Anything flat and
            # low over the ground under it reads the same way.
            ground = blueprint.ground_under(cx, cy, below=top + 1.0) \
                if hasattr(blueprint, "ground_under") else None
            gz = getattr(ground, "z", None) if ground is not None and getattr(ground, "found", True) else None
            if gz is None or top - gz > FLOOR_LETTERING_BAND:
                continue
            where = "on the ground"
        report.add(
            warning(
                "Z56",
                f"lettering {text!r} ({ident}) at {cx:g} {cy:g} lies flat {where}; "
                "words on the floor read as grey planks from eye height -- hang it "
                "(zmforge.dressing.hanging_sign) or letter a wall",
            )
        )
    return report


def window_zones(blueprint, *, approach: float = WINDOW_APPROACH, side: float = WINDOW_SIDE):
    """``(window id, room id, (x0, y0, x1, y1), floor z, top z)`` for every
    barricade window: the floor either side of its opening that a zombie
    climbs through, *approach* either side of the wall and *side* past each
    end of the opening (the ``Z57`` zone by default; a recipe may keep a
    wider one with :func:`zmforge.dressing.window_keepouts`)."""
    from ..blueprint.elements import Room, Window

    rooms = {r.id: r for r in blueprint.elements(Room)}
    out = []
    for win in blueprint.elements(Window):
        room = rooms.get(win.room_id)
        if room is None:
            continue
        o = win.barricade_origin
        if 0 <= win.aperture_index < len(room.aperture_boxes):
            box = room.aperture_boxes[win.aperture_index]
            bx0, by0, bx1, by1 = box.mins.x, box.mins.y, box.maxs.x, box.maxs.y
            top = box.maxs.z
        else:
            bx0, by0, bx1, by1 = o.x - 24.0, o.y - 24.0, o.x + 24.0, o.y + 24.0
            top = room.floor_z + 96.0
        if win.side in (Side.NORTH, Side.SOUTH):
            rect = (bx0 - side, by0 - approach, bx1 + side, by1 + approach)
        else:
            rect = (bx0 - approach, by0 - side, bx1 + approach, by1 + side)
        out.append((win.id, room.id, rect, room.floor_z, top))
    return out


def check_window_approaches(blueprint) -> Report:
    """Z57, a warning per solid prop standing in a barricade window's way in."""
    from ..blueprint.elements import PropScatter
    from ..placement.relations import Placed
    from ..props.origins import drawn_box
    from ..recipes.props import collision_box

    report = Report()
    zones = window_zones(blueprint)
    if not zones:
        return report
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if not prop.solid:
                continue
            measured = drawn_box(prop.model, collision_box(prop.model))
            if measured is None:
                continue
            placed = Placed.from_model(
                prop.model, measured, (prop.origin.x, prop.origin.y, prop.origin.z),
                prop.yaw, prop.scale, solid=True, ident=prop.id,
            )
            x0, y0, x1, y1 = placed.footprint.bounds
            for win_id, room_id, (zx0, zy0, zx1, zy1), floor, top in zones:
                if placed.z_high <= floor + STEP or placed.z_low >= top:
                    continue
                if x0 < zx1 and zx0 < x1 and y0 < zy1 and zy0 < y1:
                    report.add(
                        warning(
                            "Z57",
                            f"{prop.model} ({prop.id or scatter.id}) at "
                            f"{prop.origin.x:g} {prop.origin.y:g} stands in front of "
                            f"barricade window {win_id} of {room_id} (within "
                            f"{WINDOW_APPROACH:g} of the opening); zombies climb in "
                            "there and players rebuild there",
                        )
                    )
                    break
    return report


#: ``renders`` values in ``props/notes.json`` that ``Z58`` warns on, when measured.
RENDER_FAULTS = ("dark", "blank", "editor_invisible")


def _render_fault(model: str) -> str | None:
    """Why *model* draws wrong, from a measured ``notes.json`` entry, or ``None``."""
    from ..props.notes import model_note

    note = model_note(model)
    if note is None or note.confidence != "measured" or note.renders not in RENDER_FAULTS:
        return None
    what = {"dark": "draws dark", "blank": "draws blank",
            "editor_invisible": "does not draw at all"}[note.renders]
    text = f"{what} in the editor render (props/notes.json, measured)"
    if note.reads_as:
        text += f": {note.reads_as}"
    if note.use_instead:
        text += f"; use {note.use_instead}"
    return text


def check_reads_badly(blueprint) -> Report:
    """Z58, a warning per deny-listed or measured-to-draw-wrong model a map
    places, with the count."""
    from ..blueprint.elements import PropScatter
    from ..props.reads_badly import READS_BADLY

    report = Report()
    used: dict[str, list[str]] = defaultdict(list)
    first: dict[str, str] = {}
    why: dict[str, str | None] = {}
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if prop.model not in why:
                why[prop.model] = READS_BADLY.get(prop.model) or _render_fault(prop.model)
            if why[prop.model]:
                used[prop.model].append(prop.id or scatter.id)
                first.setdefault(prop.model, scatter.id)
    for model, ids in sorted(used.items()):
        report.add(
            warning(
                "Z58",
                f"{model} placed {len(ids)} time(s) (first {ids[0]}): {why[model]}",
                first[model],
            )
        )
    return report


#: How near the top of a curtain a rail must run (units, either way), and
#: how far past the curtain's plan it may sit.
RAIL_BAND = 8.0
RAIL_REACH = 6.0
#: How far the top of what a monitor stands on may be from its underside.
DESK_BAND = 4.0


def _placed(prop):
    from ..placement.relations import Placed
    from ..props.origins import drawn_box
    from ..recipes.props import collision_box

    measured = drawn_box(prop.model, collision_box(prop.model))
    if measured is None:
        return None
    return Placed.from_model(prop.model, measured, (prop.origin.x, prop.origin.y, prop.origin.z),
                             prop.yaw, prop.scale, solid=prop.solid, ident=prop.id)


def _has_rail(placed, boxes) -> bool:
    x0, y0, x1, y1 = placed.footprint.bounds
    top = placed.z_high
    for (bx0, by0, bz0, bx1, by1, bz1) in boxes:
        if bz1 < top - RAIL_BAND or bz0 > top + RAIL_BAND:
            continue
        if (bx0 <= x1 + RAIL_REACH and x0 - RAIL_REACH <= bx1
                and by0 <= y1 + RAIL_REACH and y0 - RAIL_REACH <= by1):
            return True
    return False


def _on_a_desk(placed, boxes) -> bool:
    x, y, low = placed.x, placed.y, placed.z_low
    for (bx0, by0, bz0, bx1, by1, bz1) in boxes:
        if abs(bz1 - low) <= DESK_BAND and bx0 - 2.0 <= x <= bx1 + 2.0 and by0 - 2.0 <= y <= by1 + 2.0:
            return True
    return False


#: ``need -> (test, what is missing)`` for the ``needs`` a blueprint can answer.
JUDGED_NEEDS = {
    "rail": (_has_rail, "no rail or bar runs along its top (zmforge.dressing.hang_bar)"),
    "desk": (_on_a_desk, "nothing under it: a desk monitor stands on a desk or counter"),
}


def check_needs(blueprint) -> Report:
    """Z59, a warning per prop missing a partner its ``notes.json`` needs,
    one per model and need per map, with the count."""
    from ..blueprint.elements import Massing, PropScatter
    from ..props.notes import needs_of

    report = Report()
    wanted: list[tuple[object, str, tuple[str, ...]]] = []
    others = []
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            needs = tuple(n for n in needs_of(prop.model) if n in JUDGED_NEEDS)
            if needs:
                wanted.append((prop, prop.id or scatter.id, needs, scatter.id))
            others.append(prop)
    if not wanted:
        return report
    boxes = []
    for element in blueprint.elements(Massing):
        b = element.bounds
        boxes.append((b.mins.x, b.mins.y, b.mins.z, b.maxs.x, b.maxs.y, b.maxs.z))
    needy = {id(p) for p, _, _, _ in wanted}
    for prop in others:
        if id(prop) in needy:
            continue
        placed = _placed(prop)
        if placed is not None:
            fx0, fy0, fx1, fy1 = placed.footprint.bounds
            boxes.append((fx0, fy0, placed.z_low, fx1, fy1, placed.z_high))
    missing: dict[tuple[str, str], list[str]] = defaultdict(list)
    first: dict[tuple[str, str], str] = {}
    for prop, ident, needs, scatter_id in wanted:
        placed = _placed(prop)
        if placed is None:
            continue
        for need in needs:
            test, _ = JUDGED_NEEDS[need]
            if not test(placed, boxes):
                missing[(prop.model, need)].append(f"{ident} at {prop.origin.x:g} {prop.origin.y:g} {prop.origin.z:g}")
                first.setdefault((prop.model, need), scatter_id)
    for (model, need), where in sorted(missing.items()):
        report.add(
            warning(
                "Z59",
                f"{model} placed {len(where)} time(s) without its {need} (first {where[0]}): "
                f"{JUDGED_NEEDS[need][1]}",
                first[(model, need)],
            )
        )
    return report
