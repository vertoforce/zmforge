"""Per-room art-direction numbers, set against the stock map (docs/map-design-method.md).

For every room: its declared scene (:mod:`zmforge.dressing.scene`), props per
k2 (1000 x 1000 units of floor) in three height bands, set pieces, lamps and
ambient effects per k2, and the walkable corridor-width distribution with its
pinch points, each beside the stock ``zm_giant`` figure
(:data:`zmforge.dressing.scene.STOCK`).  Pure Python: the generator has no
dependencies.  Widths use the study's measure (the largest disk that fits in
the walkable floor and covers the point), on a :data:`RES` grid, with solid
props taller than a step and fixture solids as the obstacles.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from ..dressing.scene import BEAT_WORDS, STOCK, scene_for

#: Raster cell for corridor widths, units.
RES = 16.0
#: Height bands over the room floor, as the study measured them (prop origin).
GROUND_TOP, MID_TOP = 48.0, 160.0
#: Disk radii for the width classes (widths 96, 160, 256, 384, 512).
RADII = (48.0, 80.0, 128.0, 192.0, 256.0)
#: A solid prop at least this wide and tall is a set-piece candidate.
SET_PIECE_SIDE, SET_PIECE_HEIGHT = 72.0, 36.0
#: Set-piece props within this of each other are one set piece.
SET_PIECE_LINK = 160.0
#: Narrow floor joining two wide regions is a pinch point.
PINCH_NARROW, PINCH_WIDE = 160.0, 256.0


def _chamfer(grid: list[list[bool]], nx: int, ny: int) -> list[list[float]]:
    """Distance (units) from every True cell to the nearest False cell (3-4 chamfer)."""
    big = 1e9
    d = [[big if grid[i][j] else 0.0 for j in range(ny)] for i in range(nx)]
    a, b = RES, RES * 1.4142
    for i in range(nx):
        row, prev = d[i], d[i - 1] if i else None
        for j in range(ny):
            if row[j]:
                v = row[j]
                if j:
                    v = min(v, row[j - 1] + a)
                if prev is not None:
                    v = min(v, prev[j] + a)
                    if j:
                        v = min(v, prev[j - 1] + b)
                    if j + 1 < ny:
                        v = min(v, prev[j + 1] + b)
                row[j] = v
    for i in range(nx - 1, -1, -1):
        row, nxt = d[i], d[i + 1] if i + 1 < nx else None
        for j in range(ny - 1, -1, -1):
            if row[j]:
                v = row[j]
                if j + 1 < ny:
                    v = min(v, row[j + 1] + a)
                if nxt is not None:
                    v = min(v, nxt[j] + a)
                    if j + 1 < ny:
                        v = min(v, nxt[j + 1] + b)
                    if j:
                        v = min(v, nxt[j - 1] + b)
                row[j] = v
    return d


def _label(mask: list[list[bool]], nx: int, ny: int) -> tuple[list[list[int]], int]:
    lab = [[0] * ny for _ in range(nx)]
    n = 0
    for i in range(nx):
        for j in range(ny):
            if mask[i][j] and not lab[i][j]:
                n += 1
                stack = [(i, j)]
                lab[i][j] = n
                while stack:
                    x, y = stack.pop()
                    for u, v in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= u < nx and 0 <= v < ny and mask[u][v] and not lab[u][v]:
                            lab[u][v] = n
                            stack.append((u, v))
    return lab, n


def corridor_widths(area, obstacles: Sequence[tuple[float, float, float, float]]) -> dict:
    """Width classes of *area*'s walkable floor, and its pinch points."""
    nx = max(1, int((area.x1 - area.x0) / RES))
    ny = max(1, int((area.y1 - area.y0) / RES))
    if nx * ny > 250_000:  # keep review fast on a huge yard: coarser cells are fine
        return {"skipped": f"{nx}x{ny} cells"}
    walk = [[True] * ny for _ in range(nx)]
    for (x0, y0, x1, y1) in obstacles:
        i0, i1 = max(0, int((x0 - area.x0) / RES)), min(nx - 1, int((x1 - area.x0) / RES))
        j0, j1 = max(0, int((y0 - area.y0) / RES)), min(ny - 1, int((y1 - area.y0) / RES))
        for i in range(i0, i1 + 1):
            row = walk[i]
            for j in range(j0, j1 + 1):
                row[j] = False
    # the room's walls are obstacles: pad the grid edge
    padded = [[False] * (ny + 2)] + [[False] + r + [False] for r in walk] + [[False] * (ny + 2)]
    edt = _chamfer(padded, nx + 2, ny + 2)
    width = [[0.0] * (ny + 2) for _ in range(nx + 2)]
    for r in RADII:
        centres = [[not (edt[i][j] >= r) for j in range(ny + 2)] for i in range(nx + 2)]
        near = _chamfer(centres, nx + 2, ny + 2)
        for i in range(nx + 2):
            for j in range(ny + 2):
                if padded[i][j] and near[i][j] <= r:
                    width[i][j] = 2 * r
    cells = [width[i][j] for i in range(nx + 2) for j in range(ny + 2) if padded[i][j]]
    if not cells:
        return {"walkable_share": 0.0}
    n = len(cells)
    edges = (96.0, 160.0, 256.0, 384.0, 512.0)
    names = ("<96", "96-160", "160-256", "256-384", "384-512", ">=512")
    share = Counter()
    for w in cells:
        share[names[sum(1 for e in edges if w >= e)]] += 1
    cells.sort()
    narrow = [[padded[i][j] and width[i][j] < PINCH_NARROW for j in range(ny + 2)] for i in range(nx + 2)]
    wide = [[padded[i][j] and width[i][j] >= PINCH_WIDE for j in range(ny + 2)] for i in range(nx + 2)]
    nl, nn = _label(narrow, nx + 2, ny + 2)
    wl, _ = _label(wide, nx + 2, ny + 2)
    touches: dict[int, set] = {}
    for i in range(nx + 2):
        for j in range(ny + 2):
            k = nl[i][j]
            if k:
                for u in range(max(0, i - 2), min(nx + 2, i + 3)):
                    for v in range(max(0, j - 2), min(ny + 2, j + 3)):
                        if wl[u][v]:
                            touches.setdefault(k, set()).add(wl[u][v])
    pinches = sum(1 for s in touches.values() if len(s) >= 2)
    return {
        "walkable_share": round(n / (nx * ny), 2),
        "share": {k: round(share[k] / n, 2) for k in names},
        "p50": cells[n // 2],
        "share_under_160": round((share["<96"] + share["96-160"]) / n, 2),
        "share_512_up": round(share[">=512"] / n, 2),
        "pinch_points": pinches,
    }


def _clusters(points: Sequence[tuple[float, float]], link: float) -> list[list[tuple[float, float]]]:
    groups: list[list[tuple[float, float]]] = []
    for p in points:
        hit = [g for g in groups if any(math.dist(p, q) <= link for q in g)]
        merged = [p]
        for g in hit:
            merged.extend(g)
            groups.remove(g)
        groups.append(merged)
    return groups


def room_art(bp, area, props, lamps, effects) -> dict:
    """The art-direction block of one room's scorecard."""
    k2 = max(area.area / 1e6, 1e-6)
    zone = area.key.split(" (")[0]
    scene = scene_for(bp, area.room_id, zone)
    bands = Counter()
    for p in props:
        h = p.z - area.floor_z
        bands["ground" if h < GROUND_TOP else "mid" if h < MID_TOP else "overhead"] += 1
    obstacles, pieces = [], []
    for p in props:
        if not p.bounds or p.z_high is None or p.mount not in ("floor", "either", "unmeasured"):
            continue
        tall = p.z_high - area.floor_z
        if p.solid and tall > 18.0:
            obstacles.append(p.bounds)
        side = max(p.bounds[2] - p.bounds[0], p.bounds[3] - p.bounds[1])
        if p.solid and side >= SET_PIECE_SIDE and p.z_high - p.z_low >= SET_PIECE_HEIGHT:
            pieces.append(((p.bounds[0] + p.bounds[2]) / 2, (p.bounds[1] + p.bounds[3]) / 2))
    for box in getattr(area, "fixtures", ()) or ():
        obstacles.append(box)
    set_pieces = _clusters(pieces, SET_PIECE_LINK)
    fx_names = [e.fx for e in effects]
    names = [p.model.lower() for p in props]
    beats_found = {
        "fire": any(f.startswith("fire/") and "fx_fire_line_embers" not in f for f in fx_names),
        "smoke": any(f.startswith("smoke/") for f in fx_names),
        "embers": any("ember" in f for f in fx_names),
        "flies": any("fly" in f for f in fx_names),
        **{b: any(any(w in n for w in ws) for n in names) for b, ws in BEAT_WORDS.items()},
    }
    lit = None
    if lamps:
        pts = [(area.x0 + (i + 0.5) * 64, area.y0 + (j + 0.5) * 64)
               for i in range(max(1, int((area.x1 - area.x0) / 64)))
               for j in range(max(1, int((area.y1 - area.y0) / 64)))]
        lit = round(sum(1 for q in pts if any(math.dist(q, (l.position.x, l.position.y)) <= 256 for l in lamps))
                    / len(pts), 2)
    n = len(props)
    return {
        "scene": scene.story if scene else None,
        "beats": list(scene.beats) if scene else [],
        "cause": getattr(scene, "cause", None) if scene else None,
        "tell": getattr(scene, "tell", None) if scene else None,
        "beats_missing": [b for b in (scene.beats if scene else ()) if not beats_found.get(b)],
        "area_k2": round(k2, 3),
        "props_per_k2": round(n / k2, 1),
        "band_per_k2": {b: round(bands[b] / k2, 1) for b in ("ground", "mid", "overhead")},
        "above_ground_share": round((bands["mid"] + bands["overhead"]) / n, 2) if n else 0.0,
        "distinct_models": len(set(names)),
        "set_pieces": len(set_pieces),
        "lamps_per_k2": round(len(lamps) / k2, 1),
        "lit_within_256": lit,
        "fx": len(effects),
        "fx_per_k2": round(len(effects) / k2, 1),
        "corridors": corridor_widths(area, obstacles),
        "stock": {k: STOCK[k] for k in ("props_non_trim", "mid_props", "overhead_props", "set_pieces",
                                        "fx", "light_positions", "lit_within_256", "corridor_p50",
                                        "corridor_share_512_up")},
    }


def collect_art(bp, areas, props) -> dict[str, dict]:
    """``room key -> room_art`` for every room."""
    from ..blueprint.elements import AmbientFx, Lamp

    lamps = bp.elements(Lamp)
    effects = bp.elements(AmbientFx)
    out = {}
    for area in areas:
        mine = [p for p in props if p.area is area]
        la = [l for l in lamps if area.holds(l.position.x, l.position.y)
              and area.floor_z - 8 <= l.position.z <= area.ceiling_z + 8]
        fx = [e for e in effects if area.holds(e.position.x, e.position.y, 32.0)]
        out[area.key] = room_art(bp, area, mine, la, fx)
    return out
