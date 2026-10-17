"""The v2 maze's set pieces, secret shortcuts, clearings, fire and scenes.

Map principle P18: every maze room gets
a set piece that splits a corridor into two narrow lanes (a wreck with a
barrel heap against the corn opposite), with smoke or a fire over it; the
layout's clearings get their scenes (a burnt-out car, the creepy clearing,
the hay lookout); the secret shortcuts are planted with walk-through corn.
Only the shared blocks are used (``dressing.outdoor``, ``dressing.fx``,
``dressing.scene``); this module only says where.
"""

from __future__ import annotations

import math
import random

from ..blueprint.elements import FLOATS_ON_PURPOSE, Prop
from ..dressing import outdoor
from ..dressing.fixtures import sheared_bar
from ..dressing.fx import burning, embers, smouldering
from ..dressing.maze import neighbours
from ..dressing.place import on_floor
from ..dressing.scene import declare_scene
from ..materials import Material
from ..spatial import Bounds, Point
from . import corn_maze as cm
from . import corn_maze_layout as lay
from . import corn_maze_parts as parts

__all__ = ["dress_set_pieces", "dress_maze_density", "SET_PIECES", "PINCH_CLEAR"]

#: The wreck each maze room gets, in room order (a car run off the farm road,
#: the farm's own broken tractor).
SET_PIECES = ("veh_t7_city_car_static_dead", "zmf_prop_tractor")
#: Each lane either side of a set piece, units (a player is 30 wide).
PINCH_CLEAR = 64.0
_PLANKS = Material("t7_wood_planks_worn", 96.0)
LOOKOUT_STEP = 16.0
LOOKOUT_TOP = 96.0


def _straight_cells(key: str, passages, busy: set) -> list[tuple[tuple[int, int], bool]]:
    """Cells of room *key* that are the middle of a straight corridor: open
    both ways along one axis and closed across it.  ``(cell, along_x)``."""
    i0, j0, i1, j1 = cm.MAZE_ROOMS[key][1]
    out = []
    for i in range(i0 + 1, i1 - 1):
        for j in range(j0 + 1, j1 - 1):
            c = (i, j)
            if any(abs(c[0] - b[0]) + abs(c[1] - b[1]) <= 1 for b in busy):
                continue
            e, w = cm._pair(c, (i + 1, j)) in passages, cm._pair(c, (i - 1, j)) in passages
            n, s = cm._pair(c, (i, j + 1)) in passages, cm._pair(c, (i, j - 1)) in passages
            if e and w and not n and not s:
                out.append((c, True))
            elif n and s and not e and not w:
                out.append((c, False))
    return out


def dress_set_pieces(bp, plan, rooms, spots) -> dict[str, int]:
    """Place everything this module owns; returns counts for the tests."""
    rng = random.Random("harvest-moon-set-pieces")
    outdoor.register_boxes()
    passages = cm.maze_passages()
    p, half = plan.maze_pitch, plan.wall / 2.0
    corridor = p - plan.wall
    busy = {cm.MAZE_ENTRANCE, *cm.DOOR_HEART, *(c for g in cm.MAZE_GATES for c in g.cells)}
    busy |= {cell for _, _, cell, _ in cm.MAZE_WINDOWS}
    busy |= set(cm.dead_ends(passages))
    for v in spots.values():         # quest cells, the power, the lantern path
        for c in (v if isinstance(v, (list, tuple, set)) and v and isinstance(next(iter(v)), tuple) else [v]):
            if isinstance(c, tuple) and len(c) == 2 and all(isinstance(q, int) for q in c):
                busy.add(c)
    for i0, j0, i1, j1 in lay.CLEARINGS.values():
        busy |= {(i, j) for i in range(i0, i1) for j in range(j0, j1)}
    counts = {"set_pieces": 0, "secret_stalks": 0, "clearing_props": 0, "fx": 0}
    focus: dict[str, list[tuple[float, float, float]]] = {}   # room -> set pieces, for the cameras

    # ---- a set piece splitting a corridor in every maze room -------------
    for n, key in enumerate(cm.MAZE_ROOMS):
        cands = _straight_cells(key, passages, busy)
        if not cands:
            continue
        cell, along_x = cands[rng.randrange(len(cands))]
        busy.add(cell)
        bp.set_piece_cells = [*getattr(bp, "set_piece_cells", []), cell]  # type: ignore[attr-defined]
        cx, cy = plan.cell_centre(cell)
        z = rooms[key].floor_z
        model = SET_PIECES[n % len(SET_PIECES)]
        side = 1 if n % 2 == 0 else -1
        barrel = outdoor.WAIST[0][0]
        items = [outdoor.pinch_point(model, (cx, cy), along_x, corridor, 24.0 + PINCH_CLEAR, z,
                                     side=side, yaw_jitter=rng.uniform(-6, 6))]
        # The barrel heap on the far side: the second lane is the gap between
        # the heap and the wreck.
        for k in (-1, 0, 1):
            off = -side * (corridor / 2.0 - 12.0)
            bx, by = (cx + k * 26.0, cy + off) if along_x else (cx + off, cy + k * 26.0)
            items.append(on_floor(barrel, bx, by, z, rng.uniform(0, 360)))
        bp.place_props(items, id=f"dress_{key}_setpiece")
        focus.setdefault(key, []).append((cx, cy, z + 40.0))
        at = Point(cx, cy, z + 8.0)
        if n % 3 == 0:
            burning(bp, at, note=f"{key} wreck fire")
            counts["fx"] += 3
        else:
            smouldering(bp, at, note=f"{key} wreck smoke")
            counts["fx"] += 2
        counts["set_pieces"] += 1

    # ---- secret shortcuts: corn with no wall behind it --------------------
    stalks = []
    for a, b in sorted(cm.secret_gaps()):
        (ax, ay), (bx, by) = plan.cell_centre(a), plan.cell_centre(b)
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        along_x = a[1] != b[1]           # the wall line runs along x when the cells stack in y
        z = rooms[cm.room_of(a)].floor_z
        t = -corridor / 2.0 + 10.0
        k = 0
        while t <= corridor / 2.0 - 10.0:
            for row in (-12.0, 12.0):
                x, y = (mx + t, my + row) if along_x else (mx + row, my + t + (6.0 if row > 0 else 0.0))
                model, scale = (parts.STALK, parts.STALK_SCALE) if k % 3 == 0 else (parts.STALK_THIN, parts.STALK_SCALE)
                stalks.append(Prop(model, Point(x, y, z), rng.uniform(0, 360), scale, False))
                k += 1
            t += 20.0
    if stalks:
        bp.place_props(stalks, id="dress_maze_secret_corn")
    counts["secret_stalks"] = len(stalks)

    # ---- the clearings ----------------------------------------------------
    inset = half + parts.BAND_DEPTH + 8.0
    for name, (i0, j0, i1, j1) in lay.CLEARINGS.items():
        x0, y0 = plan.maze_origin
        rect = (x0 + i0 * p + inset, y0 + j0 * p + inset, x0 + i1 * p - inset, y0 + j1 * p - inset)
        key = cm.room_of((i0, j0))
        z = rooms[key].floor_z
        mx, my = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        focus.setdefault(key, []).append((mx, my, z + 40.0))
        items: list = []
        guard_extra: list = []
        if name == "burnt_truck":
            items.append(on_floor("veh_t7_city_car_static_dead", mx, my, z, 35.0))
            burning(bp, Point(mx, my, z + 30.0), size="small", note="burnt-out car")
            counts["fx"] += 3
        elif name == "creepy_clearing":
            # Three crude grave markers of lashed planks (brushes: the kit
            # cross reads as a statue on a plinth).
            for k, (dx, dy) in enumerate(((-150, -120), (0, 150), (150, -120))):
                gx, gy = mx + dx, my + dy
                bp.add_block(Bounds.between((gx - 3, gy - 3, z), (gx + 3, gy + 3, z + 84)), _PLANKS,
                             reachable=False, id=f"{key}_grave_post_{k}", note="grave marker post")
                bp.add_block(Bounds.between((gx - 20, gy - 2, z + 56), (gx + 20, gy + 2, z + 62)), _PLANKS,
                             reachable=False, id=f"{key}_grave_bar_{k}", note="grave marker bar")
                guard_extra.append((gx, gy, 30.0))
            smouldering(bp, Point(mx, my, z + 4.0), note="the burning in the clearing")
            embers(bp, Point(mx + 40.0, my - 30.0, z + 4.0), note="embers off the burnt ground")
            counts["fx"] += 3
        elif name == "hay_lookout":
            _lookout(bp, rect, z, key)
            continue
        guard = ([(mx, my, 110.0)] if items or guard_extra else []) + guard_extra

        def accept(x, y, r, guard=guard, rect=rect) -> bool:
            if not (rect[0] + r <= x <= rect[2] - r and rect[1] + r <= y <= rect[3] - r):
                return False
            return all((x - gx) ** 2 + (y - gy) ** 2 > (gr + r) ** 2 for gx, gy, gr in guard)

        items += outdoor.layered(rng, rect, z, ground=40, waist=3, overhead=0, accept=accept)
        bp.place_props(items, id=f"dress_{key}_clearing_{name}")
        counts["clearing_props"] += len(items)

    # ---- scenes -----------------------------------------------------------
    stories = {
        "mazeentry": ("The corn swallowed the path from the farmyard; a car went in after it.", ("wreck",)),
        "mazeentry_b": ("The water tower watches over the rows; the farm's tractor died where it stood.", ("wreck",)),
        "mazenorth": ("A car left the farm road, ran into the corn and burned where it stopped.", ("fire", "wreck")),
        "mazenorth_b": ("The north rows, where the tractor was abandoned mid-furrow.", ("wreck",)),
        "mazewest": ("The windmill rows: something dragged a car in off the road.", ("wreck",)),
        "mazewest_b": ("The old hay lookout over the west rows, and a burnt tractor under it.", ("wreck",)),
        "mazedeep": ("Somebody held a burning in the clearing; the crosses still smoke.", ("smoke", "wreck")),
        "mazedeep_b": ("The last rows before the heart, where the tractor gave out.", ("wreck",)),
    }
    for key, room in rooms.items():
        if key in stories:
            story, beats = stories[key]
            declare_scene(bp, room, story, beats=beats, focus=focus.get(key, ()))
    return counts


def _lookout(bp, rect, z, key) -> None:
    """A stepped plank platform, LOOKOUT_TOP high, climbed by steps of
    LOOKOUT_STEP (stairs, under STEP_HEIGHT, so the navmesh covers it).  No
    bales on the deck: a riser climbs out beside it."""
    x0, y0, x1, y1 = rect
    steps = int(LOOKOUT_TOP // LOOKOUT_STEP)
    depth = 28.0
    width = 96.0
    cx = (x0 + x1) / 2.0
    top_y0 = y0 + steps * depth
    for k in range(steps):
        h = (k + 1) * LOOKOUT_STEP
        ya = y0 + k * depth
        bp.add_block(Bounds.between((cx - width / 2, ya, z), (cx + width / 2, ya + depth, z + h)), _PLANKS,
                     walkable=True, id=f"{key}_lookout_step_{k}", note="hay lookout step")
    bp.add_block(Bounds.between((cx - width, top_y0, z), (cx + width, min(y1, top_y0 + 160.0), z + LOOKOUT_TOP)),
                 _PLANKS, walkable=True, id=f"{key}_lookout_deck", note="hay lookout deck")


# ---- density: ground, waist and overhead through the maze rows -------------
#: Ground cover in a maze cell: without it the maze rooms carry about 440
#: props per 1000 x 1000 against the stock 1,148, with bare earth showing between the stalks.  Walk-through only, so
#: no path narrows: weeds and grass under the stalk bands (where the earth
#: showed between stalks), stones, bones and burnt boards along the band's
#: front, and a little litter down the middle.  ``(model, scale range, weight)``.
UNDER_CORN = (
    ("p7_foliage_weed_cluster_lrg", (1.4, 2.0), 3),
    ("p7_foliage_weed_cluster_med", (1.4, 2.0), 3),
    ("p7_foliage_grass_tall_cluster_sml", (0.5, 0.8), 4),
)
BAND_FRONT = (
    ("p7_foliage_grass_tall_cluster_sml", (0.5, 0.8), 4),
    ("p7_foliage_weed_cluster_med", (1.2, 1.8), 2),
    ("p7_debris_rockychunks_small_01", (0.8, 1.2), 2),
    ("p7_debris_rockychunks_small_12", (0.8, 1.2), 1),
    ("p7_boulder_rock_05", (1.5, 2.6), 2),
    ("p7_gib_chunk_bone_01", (1.0, 1.4), 1),
    ("p7_gib_chunk_bone_03", (1.0, 1.4), 1),
    ("p7_debris_wood_board_cluster_burn_01", (1.0, 1.0), 1),
    ("p7_debris_wood_board_splinter_01", (1.0, 1.0), 1),
)
MIDDLE = (
    ("p7_3arc_park_leaves_grp_2", (0.9, 1.3), 3),
    ("p7_debris_wood_board_splinter_01", (1.0, 1.0), 1),
    ("p7_gib_chunk_bone_03", (1.0, 1.3), 1),
)
#: Per closed side of a cell: pieces under the stalks, and at the band front.
UNDER_PER_SIDE, FRONT_PER_SIDE = 4, 3
#: Chance of a waist-high piece in the corn behind a cell's band front.
WAIST_IN_CORN = 0.35
#: Chance of one piece of litter down a corridor cell's middle.
MIDDLE_CHANCE = 0.9
#: Overhead: a line of wooden poles (brushes; the stock utility poles do not
#: link) through each maze room, over the corn, with a sagging wire between.
POLE_TOP, POLE_HALF, POLE_EVERY = 330.0, 5.0, 2
WIRE_Z, WIRE_SAG = 318.0, 26.0
_POLE = Material("t7_wood_planks_worn", 64.0)
_WIRE = Material("t7_metal_worn_iron_dark", 64.0)


def _choose(rng: random.Random, palette) -> tuple[str, float]:
    total = sum(w for _, _, w in palette)
    r = rng.uniform(0, total)
    for model, (s0, s1), w in palette:
        r -= w
        if r <= 0:
            return model, rng.uniform(s0, s1)
    model, (s0, s1), _ = palette[-1]
    return model, rng.uniform(s0, s1)


def _reach(model: str, scale: float) -> float:
    from .props import MODEL_BOX

    (a, b, _), (c, d, _) = MODEL_BOX[model]
    return math.hypot(max(-a, c), max(-b, d)) * scale


def dress_maze_density(bp, plan, rooms, d, spots) -> dict[str, int]:
    """Fill the maze rows at three heights through the shared dresser *d*
    (its keep-outs: doors, buys, spawns, windows, ground patches): ground
    cover under and in front of the corn on every closed side of a cell,
    litter down the middle, a waist piece at the back of a quiet dead end,
    and a pole line with wires over each maze room.  Returns counts."""
    from .corn_maze_script import quest_points

    outdoor.register_boxes()
    rng = random.Random("harvest-moon-density")
    passages = cm.maze_passages()
    p, half = plan.maze_pitch, plan.wall / 2.0
    face = p / 2.0 - half                         # cell centre to the corn wall's face
    front = face - parts.BAND_DEPTH               # ... to the stalk band's front
    quest = quest_points(plan, rooms)
    busy = {cm.MAZE_ENTRANCE, *cm.DOOR_HEART, *(c for g in cm.MAZE_GATES for c in g.cells)}
    for name, v in spots.items():
        if name == "dead_ends":          # every dead end; the used ones are in the other lists
            continue
        for c in (v if isinstance(v, (list, tuple, set)) and v and isinstance(next(iter(v)), tuple) else [v]):
            if isinstance(c, tuple) and len(c) == 2 and all(isinstance(q, int) for q in c):
                busy.add(c)
    clear_cells = {(i, j) for i0, j0, i1, j1 in lay.CLEARINGS.values()
                   for i in range(i0, i1) for j in range(j0, j1)}
    dead = set(cm.dead_ends(passages))
    counts = {"under": 0, "front": 0, "middle": 0, "waist": 0, "poles": 0}

    def ok(x: float, y: float, r: float) -> bool:
        return all((x - qx) ** 2 + (y - qy) ** 2 > (parts.QUEST_CLEAR + r) ** 2 for qx, qy in quest)

    sides = {(1, 0): "e", (-1, 0): "w", (0, 1): "n", (0, -1): "s"}
    for key, (_zone, (i0, j0, i1, j1)) in cm.MAZE_ROOMS.items():
        z = rooms[key].floor_z
        for i in range(i0, i1):
            for j in range(j0, j1):
                c = (i, j)
                if c in clear_cells or cm.room_of(c) != key:
                    continue
                cx, cy = plan.cell_centre(c)
                closed = [(di, dj) for di, dj in sides
                          if cm._pair(c, (i + di, j + dj)) not in passages]
                for di, dj in closed:
                    for layer, n, palette, lo, hi in (
                            ("under", UNDER_PER_SIDE, UNDER_CORN, front + 8.0, face - 4.0),
                            ("front", FRONT_PER_SIDE, BAND_FRONT, front - 14.0, front + 6.0)):
                        for _ in range(n):
                            model, scale = _choose(rng, palette)
                            r = _reach(model, scale)
                            depth = min(rng.uniform(lo, hi), face - 2.0 - r)
                            along = rng.uniform(-(p / 2.0 - 8.0), p / 2.0 - 8.0)
                            x = cx + di * depth + (0 if di else along)
                            y = cy + dj * depth + (0 if dj else along)
                            if not ok(x, y, r):
                                continue
                            if d.put(key, model, x, y, z, rng.uniform(0, 360), scale, solid=False):
                                counts[layer] += 1
                if closed and rng.random() < MIDDLE_CHANCE:
                    model, scale = _choose(rng, MIDDLE)
                    x, y = cx + rng.uniform(-24, 24), cy + rng.uniform(-24, 24)
                    if ok(x, y, _reach(model, scale)) and d.put(key, model, x, y, z, rng.uniform(0, 360),
                                                                 scale, solid=False):
                        counts["middle"] += 1
                if closed and rng.random() < WAIST_IN_CORN:
                    # Waist height, half into the corn behind the band's front,
                    # so the path keeps its width: a barrel or crate left in
                    # the rows (solid), or a bush grown up among them.
                    di, dj = closed[rng.randrange(len(closed))]
                    model = outdoor.WAIST[rng.randrange(len(outdoor.WAIST))][0]
                    r = _reach(model, 1.0)
                    if front + r + 4.0 <= face - r - 2.0:
                        depth = rng.uniform(front + r + 4.0, face - r - 2.0)
                        along = rng.uniform(-(p / 2.0 - r - 16.0), p / 2.0 - r - 16.0)
                        x = cx + di * depth + (0 if di else along)
                        y = cy + dj * depth + (0 if dj else along)
                        solid = "hedge" not in model and "bush" not in model
                        inner = rooms[key].interior
                        inside = (inner.mins.x + r + 2.0 <= x <= inner.maxs.x - r - 2.0
                                  and inner.mins.y + r + 2.0 <= y <= inner.maxs.y - r - 2.0)
                        if inside and ok(x, y, r) and d.put(key, model, x, y, z, rng.uniform(0, 360), 1.0,
                                                 solid=solid):
                            counts["waist"] += 1
                if c in dead and c not in busy and len(closed) == 3:
                    # The back of a quiet dead end: something left there.
                    (di, dj), = [s for s in sides if s not in closed]
                    model = outdoor.WAIST[rng.randrange(len(outdoor.WAIST))][0]
                    r = _reach(model, 1.0)
                    back = front - r - 4.0
                    x, y = cx - di * back, cy - dj * back
                    if ok(x, y, r) and d.put(key, model, x, y, z, rng.uniform(0, 360), 1.0):
                        counts["waist"] += 1
        counts["poles"] += _pole_line(bp, plan, key, (i0, j0, i1, j1), z, passages)
    counts["clumps"] = _band_clumps(plan, rooms, d, passages, quest, clear_cells)
    for zone, items in d.pending.items():     # the dresser's own ids are taken by its first flush
        for n in range(0, len(items), 40):
            bp.place_props(items[n:n + 40], id=f"dense_{zone}_{n // 40}")
    d.pending.clear()
    return counts


def _pole_line(bp, plan, key, cells, z, passages) -> int:
    """Wooden poles on the cell corners of the room's middle row line, every
    :data:`POLE_EVERY` cells, where a corn wall meets the corner (so the pole
    stands in the corn), each with a cross-arm and a sagging wire to the
    next.  Returns the poles placed."""
    i0, j0, i1, j1 = cells
    x0, y0 = plan.maze_origin
    p = plan.maze_pitch
    along_x = (i1 - i0) >= (j1 - j0)
    poles: list[tuple[float, float]] = []
    if along_x:
        j = (j0 + j1) // 2
        corners = [(i, j) for i in range(i0 + 1, i1, POLE_EVERY)]
    else:
        i = (i0 + i1) // 2
        corners = [(i, j) for j in range(j0 + 1, j1, POLE_EVERY)]
    for ci, cj in corners:
        # The four cells round corner (ci, cj) are (ci-1|ci, cj-1|cj); a wall
        # meets it when any of the four walls from it is closed.
        a, b, c_, d_ = (ci - 1, cj - 1), (ci, cj - 1), (ci - 1, cj), (ci, cj)
        walls = [(a, b), (c_, d_), (a, c_), (b, d_)]
        if all(cm._pair(u, v) in passages for u, v in walls):
            continue
        poles.append((x0 + ci * p, y0 + cj * p))
    for n, (px, py) in enumerate(poles):
        bp.add_block(Bounds.between((px - POLE_HALF, py - POLE_HALF, z), (px + POLE_HALF, py + POLE_HALF, z + POLE_TOP)),
                     _POLE, contents=("detail",), reachable=False, id=f"{key}_pole_{n}", note="wire pole in the corn")
        arm = ((px - 40.0, py - 3.0), (px + 40.0, py + 3.0)) if not along_x else ((px - 3.0, py - 40.0), (px + 3.0, py + 40.0))
        bp.add_block(Bounds.between((*arm[0], z + POLE_TOP - 22.0), (*arm[1], z + POLE_TOP - 14.0)), _POLE,
                     contents=("detail",), reachable=False, id=f"{key}_pole_arm_{n}",
                     note=FLOATS_ON_PURPOSE)       # held by its pole
    for n, ((ax, ay), (bx, by)) in enumerate(zip(poles, poles[1:])):
        for k, off in enumerate((-30.0, 30.0)):
            dx, dy = (0.0, off) if along_x else (off, 0.0)
            mx, my, mz = (ax + bx) / 2.0 + dx, (ay + by) / 2.0 + dy, z + WIRE_Z - WIRE_SAG
            top = z + WIRE_Z
            sheared_bar(bp, f"{key}_wire_{n}_{k}_a", (mx, my, mz), (ax + dx, ay + dy, top), 0.7, _WIRE)
            sheared_bar(bp, f"{key}_wire_{n}_{k}_b", (mx, my, mz), (bx + dx, by + dy, top), 0.7, _WIRE)
    return len(poles)


# ---- clumps along the corn: mixed ground cover in drifts, bare between ----
#: The rows need far more props, and evenly spread dressing reads as
#: artificial.  So the extra
#: ground cover grows in mixed clumps at the foot of the corn, from the
#: shared ``dressing.cluster.mixed_clumps``: a core piece, a ring round it,
#: a fringe of grass, with bare ground between clumps.
CLUMP_TIERS = (
    ("core", (("p7_foliage_grass_tall_cluster_med", (0.6, 0.85), 4),
              ("p7_foliage_grass_tall_single_sml", (0.7, 1.0), 3),
              ("zmf_prop_tree_stump", (0.85, 1.05), 1),
              ("zmf_prop_pumpkin", (0.9, 1.15), 2)), (1, 1), (0.0, 6.0)),
    ("ring", (("p7_foliage_grass_tall_single_sml", (0.55, 0.85), 3),
              ("p7_foliage_weed_cluster_lrg", (1.4, 2.0), 3),
              ("p7_debris_rockychunks_small_01", (0.7, 1.1), 2),
              ("p7_debris_rockychunks_small_08", (0.8, 1.2), 1),
              ("p7_debris_wood_board_splinter_02", (1.0, 1.0), 1),
              ("zmf_prop_pumpkin", (0.85, 1.0), 1),
              ("p7_gib_chunk_bone_03", (1.0, 1.4), 1)), (2, 4), (14.0, 34.0)),
    ("fringe", (("p7_foliage_grass_tall_cluster_sml", (0.5, 0.8), 4),
                ("p7_foliage_weed_cluster_med", (1.4, 2.0), 3),
                ("p7_foliage_weed_cluster_sml_a", (1.8, 2.4), 2),
                ("p7_3arc_park_leaves_grp_2", (0.9, 1.3), 2),
                ("p7_3arc_park_leaves_corner_1", (1.0, 1.5), 1)), (3, 6), (26.0, 56.0)),
)
#: Clump pieces per 1000 x 1000 units of maze room (props budget: the map
#: stays under PROP_TARGET, a target of about 32,000 with the link proven at 40,000).
CLUMP_PER_K2 = 250.0
#: How far a clump piece may stand out of the band into the walk, units.
CLUMP_OUT = 14.0


def clump_fits(t: float, r: float, solid: bool) -> bool:
    """Whether a clump piece of plan reach *r* whose centre is *t* past the
    band front (toward the corn wall; negative is out in the walk) keeps to
    the band: solid pieces wholly inside it, walk-through ones out into the
    walk by at most :data:`CLUMP_OUT`, measured at the piece's **near edge**.

    Testing the walk-through limit at the piece's centre is not enough:
    a tall grass cluster (reach ~50) centred at the band front stood ~64
    units into a 112-unit walk; with the corn's own hull margin on the far
    side that closed maze rows to the every-prop flood, and six buyables
    (double tap, mule kick, the heart box and wall buy, the power switch, the
    maze-entry wall buy) failed ``Z48``.
    """
    if t + r > parts.BAND_DEPTH - 4.0:
        return False
    if solid:
        return t >= r + 2.0
    return t - r >= -CLUMP_OUT


def _band_clumps(plan, rooms, d, passages, quest, clear_cells) -> int:
    """Mixed clumps at the foot of the corn in every maze room: parents drawn
    to the band fronts of closed walls, pieces kept inside the band (solid
    ones wholly, walk-through ones up to :data:`CLUMP_OUT` into the walk)."""
    from ..dressing.cluster import Tier, mixed_clumps
    from .props import MODEL_BOX

    rng = random.Random("harvest-moon-clumps")
    p, half = plan.maze_pitch, plan.wall / 2.0
    face = p / 2.0 - half
    front = face - parts.BAND_DEPTH
    tiers = [Tier(pal, n, r) for _name, pal, n, r in CLUMP_TIERS]
    sides = ((1, 0), (-1, 0), (0, 1), (0, -1))
    total = 0
    for key, (_zone, (i0, j0, i1, j1)) in cm.MAZE_ROOMS.items():
        room = rooms[key]
        z = room.floor_z
        inner = room.interior
        x0, y0 = plan.maze_origin
        rect = (max(inner.mins.x, x0 + i0 * p), max(inner.mins.y, y0 + j0 * p),
                min(inner.maxs.x, x0 + i1 * p), min(inner.maxs.y, y0 + j1 * p))
        edges = []
        for i in range(i0, i1):
            for j in range(j0, j1):
                c = (i, j)
                if c in clear_cells or cm.room_of(c) != key:
                    continue
                cx, cy = plan.cell_centre(c)
                for si, sj in sides:
                    if cm._pair(c, (i + si, j + sj)) in passages:
                        continue
                    ex, ey = cx + si * front, cy + sj * front
                    ax, ay = -sj * (p / 2.0), si * (p / 2.0)
                    edges.append((ex - ax, ey - ay, ex + ax, ey + ay))

        def depth(x: float, y: float) -> float:
            """How far past a band front toward its wall ``(x, y)`` is (the
            deepest over the cell's closed sides; -inf in the open)."""
            c = plan.cell_of(x, y)
            if c in clear_cells or cm.room_of(c) != key:
                return -math.inf
            cx, cy = plan.cell_centre(c)
            best = -math.inf
            for si, sj in sides:
                if cm._pair(c, (c[0] + si, c[1] + sj)) in passages:
                    continue
                best = max(best, (x - cx) * si + (y - cy) * sj - front)
            return best

        def accept(x: float, y: float) -> bool:
            return depth(x, y) >= -CLUMP_OUT

        def place(model, x, y, yaw, scale, key=key, z=z) -> bool:
            lo, hi = MODEL_BOX[model]
            r = math.hypot(max(-lo[0], hi[0]), max(-lo[1], hi[1])) * scale
            t = depth(x, y)
            solid = model in parts.KIT_SOLID
            if not clump_fits(t, r, solid):
                return False
            if not all((x - qx) ** 2 + (y - qy) ** 2 > (parts.QUEST_CLEAR + r) ** 2 for qx, qy in quest):
                return False
            if not (inner.mins.x + r < x < inner.maxs.x - r and inner.mins.y + r < y < inner.maxs.y - r):
                return False
            return d.put(key, model, x, y, z, yaw, scale, solid=None if solid else False)

        want = round(CLUMP_PER_K2 * (rect[2] - rect[0]) * (rect[3] - rect[1]) / 1e6)
        got = mixed_clumps(rng, rect, tiers, want, place=place, edges=edges, edge_reach=60.0,
                           edge_bias=0.95, along=2.2, accept=accept, parent_gap=90.0)
        total += len(got)
    # The open rooms with corn round them: clumps at the foot of their bands.
    for key, per_k2 in OPEN_CLUMPS.items():
        room = rooms[key]
        inner, z = room.interior, room.floor_z
        rect = (inner.mins.x, inner.mins.y, inner.maxs.x, inner.maxs.y)
        b0 = parts.BAND_DEPTH
        edges = [(rect[0] + b0, rect[1], rect[0] + b0, rect[3]), (rect[2] - b0, rect[1], rect[2] - b0, rect[3]),
                 (rect[0], rect[1] + b0, rect[2], rect[1] + b0), (rect[0], rect[3] - b0, rect[2], rect[3] - b0)]

        def wall_depth(x, y, rect=rect, b0=b0):
            return b0 - min(x - rect[0], rect[2] - x, y - rect[1], rect[3] - y)

        def place_open(model, x, y, yaw, scale, key=key, z=z, wall_depth=wall_depth) -> bool:
            lo, hi = MODEL_BOX[model]
            r = math.hypot(max(-lo[0], hi[0]), max(-lo[1], hi[1])) * scale
            t = wall_depth(x, y)
            solid = model in parts.KIT_SOLID
            if not clump_fits(t, r, solid):
                return False
            if not all((x - qx) ** 2 + (y - qy) ** 2 > (parts.QUEST_CLEAR + r) ** 2 for qx, qy in quest):
                return False
            return d.put(key, model, x, y, z, yaw, scale, solid=None if solid else False)

        want = round(per_k2 * (rect[2] - rect[0]) * (rect[3] - rect[1]) / 1e6)
        got = mixed_clumps(rng, rect, tiers, want, place=place_open, edges=edges, edge_reach=60.0,
                           edge_bias=0.95, along=2.2, accept=lambda x, y, f=wall_depth: f(x, y) >= -CLUMP_OUT,
                           parent_gap=90.0)
        total += len(got)
    return total


#: The open corn-walled rooms get clumps at their band feet too (per k2).
OPEN_CLUMPS = {"heart": 250.0, "patch": 250.0, "farmyard": 150.0}
