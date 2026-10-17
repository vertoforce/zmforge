"""The corn maze's vignettes: where the shared library's micro-stories go.

``dressing.vignette`` owns the stories and their layouts; this module only
finds the spots (corridor bends, straight wall faces, the dead ends the
dead-end scenes hand over, the clearing rims and the open rooms' edges),
asks the corn :class:`~zmforge.recipes.corn_maze_parts.Dresser` whether each
fits (its keep-outs, the hayride lane, windows, interactives, quest spots),
and trims the corn and grass out from under what it placed, so each
vignette sits in a trampled nook of the band instead of inside the stalks.

Corn alone reads as an empty corridor, so the maze needs props with
character.  Target: about one
vignette per two to three corridor segments, bigger ones in the dead ends
and clearings, never the same story twice in one stretch.
"""

from __future__ import annotations

import math
import random

from ..dressing import vignette as vg
from ..spatial import Bounds
from . import corn_maze as cm
from . import corn_maze_layout as lay
from . import corn_maze_parts as parts
from .props import MODEL_BOX

__all__ = ["dress_vignettes", "SEGMENTS_PER_VIGNETTE", "SAME_KIND_GAP"]

#: One vignette per this many straight corridor segments (two to three is the aim).
SEGMENTS_PER_VIGNETTE = 2.5
#: No two of the same story closer than this, units.
SAME_KIND_GAP = 900.0
#: Cells between two corridor vignettes (Manhattan).
CELL_GAP = 1
#: How far a nook goes back into a band (the rest of the band stays corn,
#: so no bare wall shows behind it), and into the dead-end or clearing band.
NOOK_BACK = 50.0
DEEP_BACK = NOOK_BACK + 14.0          # NOOK_BACK + LARGE_OUT
#: How far a corridor vignette may come out past the band front into the
#: 80-unit walk (leaves 66 of the 80; Z55 wants 30).
NOOK_REACH = 14.0
#: Open rooms: how many vignettes on their rims.
ROOM_RIMS = {"heart": 3, "patch": 3, "farmyard": 2}
#: Models trimmed out from under a vignette: walk-through corn and ground cover.
TRIM = ("corn_stalk", "foliage_grass", "foliage_weed", "park_leaves")
#: Corn this close to its wall face is never trimmed: the back rows hide the
#: earth wall (without them bare wall shows behind every nook).  Parts stay out of it: a nook reaches NOOK_BACK into a band.
KEEP_BACK = 22.0
#: Stalks this close to their wall face are the lining's back rows
#: (``dressing.lining.Lining.back_rows``: the tucked row's stems stand 18-23
#: off the face, the face row's 27-40): trimmed only where a part stands on
#: the stem, so the wall behind a nook keeps its corn (otherwise every row was trimmed behind a crate and
#: wheelbarrow group, 150-245 units of bare wall per vignette).
BACK_ROWS_REACH = 42.0
#: Large spots (dead ends, clearing rims) stand this far out from the band
#: front, so their deepest part is still NOOK_BACK into the band.
LARGE_OUT = 14.0


class _Placer:
    """The corn dresser behind :class:`dressing.vignette.Placer`."""

    def __init__(self, d, quest):
        self.d = d
        self.quest = quest

    def _quest_ok(self, x, y, r) -> bool:
        return all((x - qx) ** 2 + (y - qy) ** 2 > (parts.QUEST_CLEAR + r) ** 2 for qx, qy in self.quest)

    def fits(self, room, model, x, y, surface, yaw, scale, solid) -> bool:
        lo, hi = MODEL_BOX[model]
        half = max(hi[0] - lo[0], hi[1] - lo[1]) * scale / 2.0
        c, s = abs(math.cos(math.radians(yaw))), abs(math.sin(math.radians(yaw)))
        cx = max(abs(lo[0]), abs(hi[0])) * scale
        cy = max(abs(lo[1]), abs(hi[1])) * scale
        reach = (cx * c + cy * s, cx * s + cy * c)
        if not self._quest_ok(x, y, max(reach)):
            return False
        if self.d.by_window(x, y, surface, half):
            return False
        return self.d.free(x, y, surface, half, reach=reach)

    def fits_box(self, room, box: Bounds) -> bool:
        cx, cy = (box.mins.x + box.maxs.x) / 2.0, (box.mins.y + box.maxs.y) / 2.0
        hx, hy = (box.maxs.x - box.mins.x) / 2.0, (box.maxs.y - box.mins.y) / 2.0
        if not self._quest_ok(cx, cy, max(hx, hy)) or self.d.by_window(cx, cy, box.mins.z, max(hx, hy)):
            return False
        return self.d.free(cx, cy, box.mins.z, max(hx, hy), reach=(hx, hy))

    def put(self, room, model, x, y, surface, yaw, scale, solid) -> None:
        if model in parts.KIT_SOLID:
            solid = None             # a kit prop keeps the library's word (Z21)
        self.d.put(room, model, x, y, surface, yaw, scale, solid=solid, check=False)

    def reserve(self, room, box: Bounds) -> None:
        # The area kept for the vignette, against other dressing.  The
        # lining's back rows judge their stems against its parts instead
        # (Dresser.stem_boxes, filled after the vignettes are placed): the
        # reserve reaches to 8 off the wall, the parts stop 26 off it.
        self.d.keepouts.append(box)
        self.d.back_exempt.add(id(box))

    def zone_of(self, room) -> str:
        return room


def _segments(passages, cells) -> int:
    """Straight corridor runs among *cells*: passages less the cells a run
    goes straight through."""
    inside = set(cells)
    runs = sum(1 for a, b in passages if a in inside and b in inside)
    for (i, j) in inside:
        if cm._pair((i, j), (i + 1, j)) in passages and cm._pair((i, j), (i - 1, j)) in passages:
            runs -= 1
        if cm._pair((i, j), (i, j + 1)) in passages and cm._pair((i, j), (i, j - 1)) in passages:
            runs -= 1
    return max(0, runs)


def _yaw(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _trim_under(bp, boxes, spare=lambda x, y: False, stem=lambda x, y: False) -> int:
    """Take the walk-through corn and ground cover out from under the
    vignettes' parts (a trampled nook), so no stalk grows through a crate.
    A plant where ``stem(x, y)`` (the back rows) goes only if its stem is
    under a part, not whenever its leaves reach over one."""
    from ..blueprint.elements import PropScatter

    grid: dict[tuple[int, int], list] = {}
    for b in boxes:
        for gx in range(int(b[0] // 64) - 1, int(b[2] // 64) + 2):
            for gy in range(int(b[1] // 64) - 1, int(b[3] // 64) + 2):
                grid.setdefault((gx, gy), []).append(b)
    dropped = 0
    for scatter in bp.elements(PropScatter):
        keep = []
        for p in scatter.props:
            if not any(t in p.model for t in TRIM) or spare(p.origin.x, p.origin.y):
                keep.append(p)
                continue
            lo, hi = MODEL_BOX.get(p.model, ((-8, -8, 0), (8, 8, 8)))
            x, y = p.origin.x, p.origin.y
            r = (parts.STEM_HALF if "corn_stalk" in p.model and stem(x, y)
                 else math.hypot(max(-lo[0], hi[0]), max(-lo[1], hi[1])) * p.scale)
            hit = any(b[0] - r < x < b[2] + r and b[1] - r < y < b[3] + r
                      for b in grid.get((int(x // 64), int(y // 64)), ()))
            if hit:
                dropped += 1
            else:
                keep.append(p)
        if len(keep) != len(scatter.props):
            scatter.props[:] = keep
    return dropped


def dress_vignettes(bp, plan, rooms, d, spots) -> dict:
    """Place the maze's vignettes through dresser *d*; returns counts."""
    from .corn_maze_script import quest_points

    rng = random.Random("harvest-moon-vignettes")
    placer = _Placer(d, quest_points(plan, rooms))
    passages = cm.maze_passages()
    graph = cm.maze_graph(passages)
    p = plan.maze_pitch
    face = p / 2.0 - plan.wall / 2.0
    front = face - parts.BAND_DEPTH
    busy = {cm.MAZE_ENTRANCE, *cm.DOOR_HEART, *cm.DOOR_DEEP, *(c for g in cm.MAZE_GATES for c in g.cells)}
    busy |= {cell for _, _, cell, _ in cm.MAZE_WINDOWS}
    busy |= set(getattr(bp, "set_piece_cells", ()))
    for name, v in spots.items():
        if name in ("dead_ends", "scenes", "path"):
            continue
        for c in (v if isinstance(v, (list, tuple, set)) and v and isinstance(next(iter(v)), tuple) else [v]):
            if isinstance(c, tuple) and len(c) == 2 and all(isinstance(q, int) for q in c):
                busy.add(c)
    if isinstance(spots.get("risers"), dict):
        for cells in spots["risers"].values():
            busy |= set(cells)
    clear_cells = {(i, j) for i0, j0, i1, j1 in lay.CLEARINGS.values()
                   for i in range(i0, i1) for j in range(j0, j1)}
    dead = set(cm.dead_ends(passages))
    sides = ((1, 0), (-1, 0), (0, 1), (0, -1))
    placed: list[vg.Vignette] = []
    taken: list[tuple[int, int]] = []
    counts = {"segments": 0, "corridor": 0, "dead_end": 0, "clearing": 0, "rim": 0, "tried": 0}

    def attempt(spot: vg.Spot, large: bool | None, ident: str, tag: str) -> vg.Vignette | None:
        order = vg.choose_kind(rng, spot, placed, gap=SAME_KIND_GAP, large=large)
        if large:
            order += vg.choose_kind(rng, spot, placed, gap=SAME_KIND_GAP, large=False)
        for kind in order:
            counts["tried"] += 1
            v = vg.place_vignette(bp, kind, spot, rng, placer, ident=f"{ident}_{kind}")
            if v is not None:
                placed.append(v)
                counts[tag] += 1
                return v
        return None

    # ---- the dead ends the dead-end scenes handed over: the big stories --
    for n, cell in enumerate(getattr(bp, "vignette_dead_ends", ())):
        key = cm.room_of(cell)
        (nb,) = graph[cell]
        ox, oy = nb[0] - cell[0], nb[1] - cell[1]
        cx, cy = plan.cell_centre(cell)
        out = front - LARGE_OUT
        spot = vg.Spot(cx - ox * out, cy - oy * out, rooms[key].floor_z, _yaw(ox, oy), "dead_end", key,
                       width=2.0 * (face - 8.0), back=DEEP_BACK, reach=2.0 * front - LARGE_OUT)
        if attempt(spot, True, f"{key}_vig_end_{n}", "dead_end"):
            taken.append(cell)

    # ---- corridors: bends first, then straight wall faces ----------------
    for key, (_zone, (i0, j0, i1, j1)) in cm.MAZE_ROOMS.items():
        cells = [(i, j) for i in range(i0, i1) for j in range(j0, j1)
                 if cm.room_of((i, j)) == key and (i, j) not in clear_cells]
        segs = _segments(passages, cells)
        counts["segments"] += segs
        want = round(segs / SEGMENTS_PER_VIGNETTE)
        cands = []
        for c in cells:
            if c in busy or c in dead or c in clear_cells:
                continue
            opened = [s for s in sides if cm._pair(c, (c[0] + s[0], c[1] + s[1])) in passages]
            closed = [s for s in sides if s not in opened]
            if len(opened) not in (2, 3) or not closed:
                continue
            bend = len(opened) == 2 and (opened[0][0] != -opened[1][0] or opened[0][1] != -opened[1][1])
            cands.append((rng.random() - (0.4 if bend else 0.0), c, closed, bend))
        cands.sort()
        got = 0
        for _, c, closed, bend in cands:
            if got >= want:
                break
            if any(abs(c[0] - t[0]) + abs(c[1] - t[1]) <= CELL_GAP for t in taken):
                continue
            cx, cy = plan.cell_centre(c)
            di, dj = closed[rng.randrange(len(closed))]
            yaw = _yaw(-di, -dj)
            a = math.radians(yaw)
            vx, vy = -math.sin(a), math.cos(a)          # the spot's local +v
            shift = 0.0
            if bend:
                # Shift along the wall toward the other closed side: the
                # corner a player walks straight at before the turn.
                (oi, oj), = [s for s in closed if s != (di, dj)]
                shift = 30.0 if vx * oi + vy * oj > 0 else -30.0
            spot = vg.Spot(cx + di * front + vx * shift, cy + dj * front + vy * shift, rooms[key].floor_z, yaw,
                           "bend" if bend else "wall_face", key,
                           width=150.0 if bend else 180.0, back=NOOK_BACK, reach=NOOK_REACH)
            if attempt(spot, False, f"{key}_vig_{len(placed)}", "corridor"):
                taken.append(c)
                got += 1

    # ---- the maze clearings: one or two on each rim ----------------------
    inset = plan.wall / 2.0 + parts.BAND_DEPTH + LARGE_OUT
    for name, (i0, j0, i1, j1) in lay.CLEARINGS.items():
        x0, y0 = plan.maze_origin
        rect = (x0 + i0 * p + inset, y0 + j0 * p + inset, x0 + i1 * p - inset, y0 + j1 * p - inset)
        key = cm.room_of((i0, j0))
        z = rooms[key].floor_z
        mx, my = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        edges = [((mx, rect[1]), 90.0, rect[2] - rect[0]), ((mx, rect[3]), 270.0, rect[2] - rect[0]),
                 ((rect[0], my), 0.0, rect[3] - rect[1]), ((rect[2], my), 180.0, rect[3] - rect[1])]
        rng.shuffle(edges)
        got = 0
        for (ex, ey), yaw, length in edges:
            if got >= 2:
                break
            for off in (0.0, -0.25, 0.25):
                a = math.radians(yaw)
                sx, sy = ex - math.sin(a) * off * length, ey + math.cos(a) * off * length
                spot = vg.Spot(sx, sy, z, yaw, "clearing_edge", key, width=min(200.0, length * 0.45),
                               back=DEEP_BACK, reach=110.0)
                if attempt(spot, True, f"{key}_vig_{name}_{got}", "clearing"):
                    got += 1
                    break

    # ---- the open rooms' rims (heart, patch, farmyard) -------------------
    for key, want in ROOM_RIMS.items():
        room = rooms[key]
        box = room.interior
        z = room.floor_z
        b0 = parts.BAND_DEPTH + LARGE_OUT
        walls = [((box.mins.x + b0, None), 0.0), ((box.maxs.x - b0, None), 180.0),
                 ((None, box.mins.y + b0), 90.0), ((None, box.maxs.y - b0), 270.0)]
        tries = []
        for (wx, wy), yaw in walls:
            lo, hi = (box.mins.y, box.maxs.y) if wx is not None else (box.mins.x, box.maxs.x)
            t = lo + 260.0
            while t < hi - 260.0:
                tries.append((rng.random(), wx if wx is not None else t, wy if wy is not None else t, yaw))
                t += 220.0
        tries.sort()
        got = 0
        for _, sx, sy, yaw in tries:
            if got >= want:
                break
            if any(math.hypot(sx - v.focus[0], sy - v.focus[1]) < 700.0 for v in placed if v.room == key):
                continue
            spot = vg.Spot(sx, sy, z, yaw, "clearing_edge", key, width=200.0, back=DEEP_BACK, reach=110.0)
            if attempt(spot, True, f"{key}_vig_rim_{got}", "rim"):
                got += 1

    open_rooms = [rooms[k].interior for k in ROOM_RIMS]
    clear_rects = [(plan.maze_origin[0] + i0 * p + plan.wall / 2.0, plan.maze_origin[1] + j0 * p + plan.wall / 2.0,
                    plan.maze_origin[0] + i1 * p - plan.wall / 2.0, plan.maze_origin[1] + j1 * p - plan.wall / 2.0)
                   for i0, j0, i1, j1 in lay.CLEARINGS.values()]

    def to_face(x: float, y: float) -> float:
        """Distance from ``(x, y)`` to the nearest corn wall face."""
        for b in open_rooms:
            if b.mins.x <= x <= b.maxs.x and b.mins.y <= y <= b.maxs.y:
                return min(x - b.mins.x, b.maxs.x - x, y - b.mins.y, b.maxs.y - y)
        best = math.inf
        for r in clear_rects:
            if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                best = min(x - r[0], r[2] - x, y - r[1], r[3] - y)
        c = plan.cell_of(x, y)
        if c in graph:
            cx, cy = plan.cell_centre(c)
            for si, sj in sides:
                if cm._pair(c, (c[0] + si, c[1] + sj)) not in passages:
                    best = min(best, face - ((x - cx) * si + (y - cy) * sj))
        return best

    parts_boxes = [b for v in placed for b in v.boxes]
    d.stem_boxes += [tuple(b[:4]) for b in parts_boxes]
    counts["trimmed"] = _trim_under(bp, parts_boxes,
                                    spare=lambda x, y: to_face(x, y) <= KEEP_BACK,
                                    stem=lambda x, y: to_face(x, y) <= BACK_ROWS_REACH)
    counts["vignettes"] = len(placed)
    counts["props"] = sum(v.props for v in placed)
    counts["brushes"] = sum(v.brushes for v in placed)
    counts["lights"] = sum(v.lights for v in placed)
    counts["kinds"] = {}
    for v in placed:
        counts["kinds"][v.kind] = counts["kinds"].get(v.kind, 0) + 1

    # ---- the cameras: two per room, kinds not yet shown elsewhere first ---
    shown: dict[str, int] = {}
    for key, room in rooms.items():
        pick: list[vg.Vignette] = []
        for _ in range(2):
            left = [v for v in placed if v.room == key and v not in pick and all(v.kind != o.kind for o in pick)]
            if not left:
                break
            v = min(left, key=lambda v: (shown.get(v.kind, 0), -v.props, v.kind))
            shown[v.kind] = shown.get(v.kind, 0) + 1
            pick.append(v)
        if pick:
            vg.add_focus(bp, room, [v.focus for v in pick])
    return counts
