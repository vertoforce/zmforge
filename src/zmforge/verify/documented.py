"""Checks whose rule comes from the documentation shipped with the mod tools.

Every other module in this package encodes a rule that was measured, played or
read out of a stock script.  These five were read out of Treyarch's own
documentation on the install, and each one guards a defect that compiles,
links and then misbehaves in play.  The sources are the PDFs and
JSON files the mod tools install ships.

``N1``
    a step taller than the navmesh's own ``maxStepHeight``;
``N2``
    a way through narrower than the navmesh's own ``minCharacterWidth``;
``N3``
    a way through with less headroom than the navmesh's ``characterHeight``;
``N4``
    terrain steeper than the navmesh's ``maxWalkableSlope``;
``N5``
    a route narrower than ``Scale_Standards.pdf``'s own hallway widths;
``L2``
    a lamp with neither of the two documented light LOD keys.

N1 to N4 all fail the same way: ``cod2map64 -navmesh`` builds a navmesh that
omits the offending surface, the compiler exits 0 and prints nothing about it,
the map links, and in play the walkers simply never go there.  The round then
does not end.

``N5`` is a different question and is a warning rather than an error.  N1 to N4
ask whether there is a navmesh *at all*; N5 asks whether the space the walkers
got is wide enough to move through, which is a level-design standard and not an
engine threshold.  Its numbers come from the other shipped document,
``docs_modtools\\Scale_Standards.pdf``, not from the settings file.
"""

from __future__ import annotations

import bisect
import math
from collections import deque

from ..blueprint.elements import Massing, Room, Terrain, Window
from ..blueprint.model import _solid_bounds
from .report import Report, error, warning

__all__ = [
    "MAX_STEP_HEIGHT",
    "MIN_CHARACTER_WIDTH",
    "CHARACTER_HEIGHT",
    "MAX_WALKABLE_SLOPE",
    "MIN_PINCH_POINT",
    "MAX_PINCH_DEPTH",
    "MIN_HALLWAY_CLEARANCE",
    "MAX_CLEARANCE_RUN",
    "LIGHT_LOD_KEYS",
    "check_navmesh_geometry",
    "check_step_height",
    "check_nav_apertures",
    "check_walkable_slope",
    "check_pathing_width",
    "check_light_lod",
]

#: The tallest single step ``cod2map64 -navmesh`` will connect across.
#: **[documented]** ``bin\\default_navmesh_settings.json``: ``"maxStepHeight":
#: 18``.  Spec 2.5 records 8 as the rise the reference authors used and says
#: the engine's real limit is not known.  This is that number.  Every shipped
#: recipe climbs in 16s, which is inside it by two units.
MAX_STEP_HEIGHT = 18.0

#: The narrowest corridor the navmesh generator will lay a walkable surface
#: down.  **[documented]** same file: ``"minCharacterWidth": 31``, with
#: ``"simplification.minCorridorWidth": 30`` beside it.  One unit wider than
#: the player's own 30-unit hull, so a 30-unit doorway passes ``W2`` and gets
#: no navmesh.
MIN_CHARACTER_WIDTH = 31.0

#: The headroom the navmesh generator assumes a walker needs.
#: **[documented]** same file: ``"characterHeight": 72``.  It agrees with the
#: standing player height in ``docs_modtools\\Scale_Standards.pdf``
#: (the PDF gives the standing player as 72 inches tall).
CHARACTER_HEIGHT = 72.0

#: The steepest surface the navmesh generator treats as walkable, in degrees.
#: **[documented]** same file: ``"maxWalkableSlope": 46``.
MAX_WALKABLE_SLOPE = 46.0

#: The narrowest constriction Treyarch's own level standard allows in a space
#: people move through.  **[documented]** ``docs_modtools\\Scale_Standards.pdf``,
#: *Hallways*: ``Minimum Pinch Point - 64"``.  It is the same 64 IceGrenade
#: gives as a rule of thumb for zombie pathing in "Start Making BO3 Custom
#: Maps!" (about 6:19); this constant is that
#: number with a shipped file behind it instead of a tutorial.
MIN_PINCH_POINT = 64.0

#: How far a pinch point may run before it stops being a pinch point.
#: **[documented]** same page, paraphrased: a pinch point should ideally be at
#: most 32" deep and must not exceed 64".  This is the 64, not the 32,
#: because the 32 is written as a preference.
MAX_PINCH_DEPTH = 64.0

#: The narrowest a space may be over any distance worth calling one.
#: **[documented]** same page: ``Minimum Clearance - 96"``.
MIN_HALLWAY_CLEARANCE = 96.0

#: How long a run at minimum clearance may be.  **[documented]** same page,
#: paraphrased: a minimum-clearance run should be no longer than 128".
#: The same section puts a non-combat hallway at 128 minimum and a hallway
#: with combat at 160; neither is enforced here, because a zombies map is
#: combat everywhere and 160 over a whole map is a house style rather than a
#: rule.
MAX_CLEARANCE_RUN = 128.0

#: The two light LOD keys of ``docs_modtools\\Culling_LOD_Lights.pdf``.
LIGHT_LOD_KEYS = ("culling_cutoff", "culling_falloff")
#: L2: a lamp this small (radius, units) is "small" in stock zm_giant's split.
SMALL_LAMP_RADIUS = 150.0
#: L2: the largest LOD value a small lamp may carry (stock: 5 / 25).
SMALL_LAMP_MAX_CUTOFF = 25.0


def check_navmesh_geometry(blueprint) -> Report:
    """N1 to N5 together, over a blueprint."""
    report = Report()
    for part in (
        check_step_height,
        check_nav_apertures,
        check_walkable_slope,
        check_pathing_width,
    ):
        report.extend(part(blueprint).findings)
    return report


# --------------------------------------------------------------------------
def check_step_height(blueprint) -> Report:
    """N1: no step rises further than the navmesh will step.

    ``Z19`` already asks whether a flight connects to something at both ends,
    and deliberately takes no position on how high a step may be because the
    limit was unknown when it was written.  This is the other half: the flight
    connects, and the walkers still cannot use it because each tread is a
    wall as far as the navmesh is concerned.
    """
    report = Report()
    for flight in blueprint.elements(Massing):
        if flight.note != "steps" or not flight.walkable:
            continue
        tops = sorted(_solid_bounds(solid).maxs.z for solid in flight.solids)
        if len(tops) < 2:
            continue
        rise = max(high - low for low, high in zip(tops, tops[1:]))
        if rise > MAX_STEP_HEIGHT:
            report.add(
                error(
                    "N1",
                    f"this flight rises {rise:g} units a step, over the "
                    f"{MAX_STEP_HEIGHT:g} the navmesh generator steps "
                    "(default_navmesh_settings.json, maxStepHeight); the "
                    "compile will not say so and zombies will not climb it",
                    flight.id,
                )
            )
    return report


# --------------------------------------------------------------------------
def check_nav_apertures(blueprint) -> Report:
    """N2 and N3: a hole the walkers can actually get a navmesh through.

    A barricade window is exempt from both.  Zombies cross one by playing the
    barricade prefab's traversal animation, not by walking, which is why the
    shipped recipes cut a 96 x 48 hole for it and are right to.  ``Z8`` owns
    that opening's own rules.
    """
    report = Report()
    exempt: set[tuple[str, int]] = {
        (window.room_id, window.aperture_index)
        for window in blueprint.elements(Window)
        if window.aperture_index >= 0
    }
    for room in blueprint.elements(Room):
        for index, aperture in enumerate(room.apertures):
            if aperture.sill > 0.0:
                continue  # a window is not a way through
            if (room.id, index) in exempt:
                continue
            if aperture.width < MIN_CHARACTER_WIDTH:
                report.add(
                    error(
                        "N2",
                        f"a doorway {aperture.width:g} units wide is under the "
                        f"{MIN_CHARACTER_WIDTH:g} the navmesh generator needs "
                        "(default_navmesh_settings.json, minCharacterWidth), "
                        "so no zombie paths through it",
                        room.id,
                    )
                )
            if aperture.height < CHARACTER_HEIGHT:
                report.add(
                    error(
                        "N3",
                        f"a doorway {aperture.height:g} units tall leaves less "
                        f"headroom than the {CHARACTER_HEIGHT:g} the navmesh "
                        "generator assumes (default_navmesh_settings.json, "
                        "characterHeight), and a standing player is the same "
                        "72 units (Scale_Standards.pdf)",
                        room.id,
                    )
                )
    return report


# --------------------------------------------------------------------------
def check_walkable_slope(blueprint) -> Report:
    """N4: no terrain face is steeper than the navmesh will walk.

    The slope is taken between neighbouring cells of the heightfield, along
    both grid axes.  That is the same pair of samples the mesh builds its
    triangles from, so it is the slope the compiler sees.
    """
    report = Report()
    for terrain in blueprint.elements(Terrain):
        record = terrain.record
        if record is None:
            continue
        cells = record.heights.cells
        worst = 0.0
        where: tuple[int, int] | None = None
        for row, values in enumerate(cells):
            for col, height in enumerate(values):
                for drow, dcol in ((0, 1), (1, 0)):
                    nrow, ncol = row + drow, col + dcol
                    if nrow >= len(cells) or ncol >= len(values):
                        continue
                    drop = abs(cells[nrow][ncol] - height)
                    # The run is the spacing along the axis stepped, which is
                    # not the same on both when the grid was stretched onto a
                    # room that is not square.
                    run = record.x_cell if dcol else record.y_cell
                    angle = math.degrees(math.atan2(drop, run))
                    if angle > worst:
                        worst, where = angle, (row, col)
        if worst > MAX_WALKABLE_SLOPE and where is not None:
            report.add(
                error(
                    "N4",
                    f"terrain reaches {worst:.1f} degrees at row {where[0]}, "
                    f"column {where[1]}, over the {MAX_WALKABLE_SLOPE:g} the "
                    "navmesh generator walks (default_navmesh_settings.json, "
                    "maxWalkableSlope); that face gets no navmesh",
                    terrain.id,
                )
            )
    return report


# --------------------------------------------------------------------------
# N5: how wide the walkers need it, which is not how wide the mesh needs it
# --------------------------------------------------------------------------
#: Plan bucket used to pair cells up without comparing every one with every
#: other one.  The same 512 :mod:`~zmforge.verify.reachability` buckets with.
_BUCKET = 512.0

#: Slack on a shared edge, in units; two cells that abut exactly overlap by
#: zero and every coordinate in this package sits on a grid, so this only has
#: to absorb floating-point noise.  Same value and same reason as
#: :data:`~zmforge.verify.reachability.TOUCH`.
_TOUCH = 1e-6


def _plan_buckets(box):
    for gx in range(
        math.floor((box.mins.x - _TOUCH) / _BUCKET),
        math.floor((box.maxs.x + _TOUCH) / _BUCKET) + 1,
    ):
        for gy in range(
            math.floor((box.mins.y - _TOUCH) / _BUCKET),
            math.floor((box.maxs.y + _TOUCH) / _BUCKET) + 1,
        ):
            yield gx, gy


def _walkable_levels(cells):
    """``cells`` split into the surfaces that are one floor to walk on.

    Two rectangles belong to the same surface when they meet in plan and
    either they are part of the same element -- a heightfield is one surface
    however steep it gets, and ``N4`` is what judges its slope -- or their
    heights are within one navmesh step of each other, which is what joins a
    flight of steps to the floor at its foot.

    Splitting matters because width is measured in plan: without it a balcony
    would widen the room underneath it and a narrow gantry over a hall would
    read as the hall.
    """
    parent = list(range(len(cells)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    grid: dict[tuple[int, int], list[int]] = {}
    for index, cell in enumerate(cells):
        for key in _plan_buckets(cell.floor):
            grid.setdefault(key, []).append(index)
    for members in grid.values():
        for position, first in enumerate(members):
            box = cells[first].floor
            for second in members[position + 1 :]:
                root_a, root_b = find(first), find(second)
                if root_a == root_b:
                    continue
                other = cells[second].floor
                if min(box.maxs.x, other.maxs.x) - max(box.mins.x, other.mins.x) < -_TOUCH:
                    continue
                if min(box.maxs.y, other.maxs.y) - max(box.mins.y, other.mins.y) < -_TOUCH:
                    continue
                if (
                    cells[first].element_id == cells[second].element_id
                    or abs(cells[first].z - cells[second].z) <= MAX_STEP_HEIGHT
                ):
                    parent[root_b] = root_a
    levels: dict[int, list] = {}
    for index in range(len(cells)):
        levels.setdefault(find(index), []).append(cells[index])
    return list(levels.values())


def _constrictions(cells):
    """Every stretch of one walkable surface that is under minimum clearance.

    ``(narrowest, longest, label, element_id, centre)`` per stretch, where
    ``longest`` is the longer side of the stretch's own bounding box: how far
    a walker travels while the space stays narrow.

    The arithmetic is exact rather than sampled, the same way
    :mod:`~zmforge.verify.reachability` cuts its cells: every rectangle is
    axis aligned, so cutting the plan on every rectangle edge gives cells that
    are wholly covered or wholly empty, and the free width at a point is the
    shorter of its two runs of covered cells.  A wide room has two long runs;
    a corridor has one long and one short, and the short one is its width; a
    doorway is short in the direction of travel, which is why the wall it is
    cut in does not read as a corridor.
    """
    xs = sorted({value for cell in cells for value in (cell.floor.mins.x, cell.floor.maxs.x)})
    ys = sorted({value for cell in cells for value in (cell.floor.mins.y, cell.floor.maxs.y)})
    across, along = len(xs) - 1, len(ys) - 1
    if across < 1 or along < 1:
        return []
    owner = [[-1] * along for _ in range(across)]
    for index, cell in enumerate(cells):
        box = cell.floor
        for i in range(bisect.bisect_left(xs, box.mins.x), bisect.bisect_left(xs, box.maxs.x)):
            column = owner[i]
            for j in range(bisect.bisect_left(ys, box.mins.y), bisect.bisect_left(ys, box.maxs.y)):
                column[j] = index
    width = [[0.0] * along for _ in range(across)]
    for j in range(along):
        i = 0
        while i < across:
            if owner[i][j] < 0:
                i += 1
                continue
            end = i
            while end < across and owner[end][j] >= 0:
                end += 1
            run = xs[end] - xs[i]
            for step in range(i, end):
                width[step][j] = run
            i = end
    for i in range(across):
        j = 0
        while j < along:
            if owner[i][j] < 0:
                j += 1
                continue
            end = j
            while end < along and owner[i][end] >= 0:
                end += 1
            run = ys[end] - ys[j]
            for step in range(j, end):
                width[i][step] = min(width[i][step], run)
            j = end
    seen = [[False] * along for _ in range(across)]
    found = []
    for start_i in range(across):
        for start_j in range(along):
            if (
                seen[start_i][start_j]
                or owner[start_i][start_j] < 0
                or width[start_i][start_j] >= MIN_HALLWAY_CLEARANCE
            ):
                continue
            queue = deque([(start_i, start_j)])
            seen[start_i][start_j] = True
            low_i = high_i = start_i
            low_j = high_j = start_j
            narrowest = width[start_i][start_j]
            votes: dict[tuple[str, str], int] = {}
            while queue:
                i, j = queue.popleft()
                low_i, high_i = min(low_i, i), max(high_i, i)
                low_j, high_j = min(low_j, j), max(high_j, j)
                narrowest = min(narrowest, width[i][j])
                cell = cells[owner[i][j]]
                key = (cell.label, cell.element_id)
                votes[key] = votes.get(key, 0) + 1
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = i + di, j + dj
                    if not (0 <= ni < across and 0 <= nj < along) or seen[ni][nj]:
                        continue
                    if owner[ni][nj] < 0 or width[ni][nj] >= MIN_HALLWAY_CLEARANCE:
                        continue
                    seen[ni][nj] = True
                    queue.append((ni, nj))
            longest = max(xs[high_i + 1] - xs[low_i], ys[high_j + 1] - ys[low_j])
            label, element_id = max(votes.items(), key=lambda item: item[1])[0]
            found.append(
                (
                    narrowest,
                    longest,
                    label,
                    element_id,
                    ((xs[low_i] + xs[high_i + 1]) / 2.0, (ys[low_j] + ys[high_j + 1]) / 2.0),
                )
            )
    return found


def check_pathing_width(blueprint) -> Report:
    """N5: the walkers have room to move, not merely room to exist.

    ``N2`` is the threshold for a navmesh being laid at all, and it was
    settled by experiment on the mod tools install: sweep an opening's width,
    compile with ``-navmesh`` and walk the face adjacency of the mesh, and 16
    to 30.9 units leave the two rooms as separate pieces while 30.95 and up
    join them.  Setting ``minCharacterWidth`` to 60 moves the boundary to 61,
    so the knob is that setting and the number is 31.

    That answers "can anything path here".  It does not answer "do the walkers
    move through here well", and the two are different questions with
    different sources, so this is a second rule and not a replacement for the
    first.  Treyarch's own ``docs_modtools\\Scale_Standards.pdf`` answers the
    second one under *Hallways*, in the same units, three times over:
    ``Minimum Clearance - 96"``, not to be used over distances longer than
    128; ``Minimum Pinch Point - 64"``, not to exceed 64 in depth; and 128 or
    160 minimum for a hallway depending on whether there is fighting in it.
    The community rule of thumb that prompted this -- 64 units anywhere
    zombies travel or they get stuck -- is the pinch-point number, and this
    check is written against the document rather than against the tutorial.

    So: **warnings, never errors**, over the walkable surface the player's own
    flood reaches (:func:`~zmforge.verify.reachability.flood_from_spawn`, the
    graph ``Z25`` floods), one per element at its worst stretch.

    What is left out, and why
    -------------------------
    * **Anything narrower than the navmesh's own** :data:`MIN_CHARACTER_WIDTH`.
      The gap behind a bench is free floor and this arithmetic measures it
      honestly, but no walker is in it -- the mesh is not laid there, ``N2``
      measured that -- so it is not a route and saying so would be noise.
    * **The top of a walkable massing that is not a flight of steps.**  A
      table is meant to be 60 units across.  :mod:`~zmforge.verify.navmesh`
      draws the same line for the same reason: a route is a room floor, a
      terrain cell and a flight of steps, and the model does not say which
      slab is a platform and which is furniture.
    * **What is above.**  Width is measured in plan, per walkable surface, so
      a low beam is ``N3``'s question and not this one.

    Nothing here has been played.  The chain from "this stretch is 48 units
    wide" to "the walkers bunch up in it" is Treyarch's own standard for their
    own levels, which is a good authority for a warning and not evidence about
    this engine's pathing.
    """
    from .reachability import flood_from_spawn

    report = Report()
    furniture = {
        massing.id for massing in blueprint.elements(Massing) if massing.note != "steps"
    }
    flood = flood_from_spawn(blueprint)
    cells = [
        flood.cells[index]
        for index in sorted(flood.reached)
        if flood.cells[index].element_id not in furniture
    ]
    if not cells:
        return report
    worst: dict[str, tuple] = {}
    counts: dict[str, int] = {}
    for level in _walkable_levels(cells):
        for narrowest, longest, label, element_id, centre in _constrictions(level):
            if narrowest < MIN_CHARACTER_WIDTH:
                continue
            allowed = (
                MAX_PINCH_DEPTH if narrowest < MIN_PINCH_POINT else MAX_CLEARANCE_RUN
            )
            if longest <= allowed:
                continue
            counts[element_id] = counts.get(element_id, 0) + 1
            if element_id not in worst or longest > worst[element_id][1]:
                worst[element_id] = (narrowest, longest, label, allowed, centre)
    for element_id, (narrowest, longest, label, allowed, centre) in sorted(
        worst.items(), key=lambda item: (-item[1][1], item[0])
    ):
        others = counts[element_id] - 1
        more = f", and {others} other stretch{'es' if others > 1 else ''} of it" if others else ""
        if narrowest < MIN_PINCH_POINT:
            why = (
                f"under the {MIN_PINCH_POINT:g}-unit minimum pinch point of "
                f"Scale_Standards.pdf, which also says a pinch should not run "
                f"more than {MAX_PINCH_DEPTH:g} units deep"
            )
        else:
            why = (
                f"under the {MIN_HALLWAY_CLEARANCE:g}-unit minimum clearance of "
                f"Scale_Standards.pdf, which says minimum clearance should not "
                f"be used over distances longer than {MAX_CLEARANCE_RUN:g} units"
            )
        report.add(
            warning(
                "N5",
                f"{label} narrows to {narrowest:g} units and stays under "
                f"{MIN_HALLWAY_CLEARANCE:g} for {longest:g} units of travel "
                f"around ({centre[0]:g}, {centre[1]:g}){more}: {why}. The "
                f"navmesh is laid -- {MIN_CHARACTER_WIDTH:g} is the measured "
                "threshold for that (N2) -- so this is about how the walkers "
                "move through, not whether they can",
                element_id,
            )
        )
    return report


# --------------------------------------------------------------------------
def check_light_lod(document) -> Report:
    """L2: no small lamp carries a light LOD pair that culls it at room range.

    ``docs_modtools\\Culling_LOD_Lights.pdf``: the two keys are "# of onscreen
    pixels" at which the light is cut off / starts to fade, "larger values ...
    result in more aggressive cutoff", 200 / 300 is the generic start, and
    "lights with smaller radius will need more tolerant LOD settings".  Both
    keys default to 0 in ``deffiles/lightdescription.awi`` (never culled), so a
    lamp with neither is fine.  Stock ``zm_giant`` gives its lamps of radius
    150 or less 5 / 25 (158 of them), not 200 / 300.  A small lamp with a
    cutoff over :data:`SMALL_LAMP_MAX_CUTOFF` is flagged: on small lamps it
    blacks out narrow corridors.

    ``document`` is a parsed :class:`~zmforge.mapsource.document.Document`.
    """
    report = Report()
    for entity in document.entities:
        if entity.classname != "light":
            continue
        try:
            radius = float(entity.value("radius") or 0.0)
            cutoff = float(entity.value("culling_cutoff") or 0.0)
            falloff = float(entity.value("culling_falloff") or 0.0)
        except ValueError:
            continue
        if radius <= SMALL_LAMP_RADIUS and max(cutoff, falloff) > SMALL_LAMP_MAX_CUTOFF:
            report.add(
                warning(
                    "L2",
                    f"this lamp of radius {radius:g} carries culling_cutoff "
                    f"{cutoff:g} / culling_falloff {falloff:g} (onscreen pixels, "
                    "larger culls harder); Culling_LOD_Lights.pdf says small "
                    "lamps need more tolerant values and stock zm_giant gives "
                    "its lamps of radius 150 or less 5 / 25; leave both unset "
                    "(0, never culled) or use 5 / 25",
                    entity.value("targetname") or entity.value("origin"),
                )
            )
    return report
