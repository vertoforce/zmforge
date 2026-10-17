"""Where to stand to look at each room: one view per doorway plus high corners.

Pure geometry over the review's measured areas and openings, so it is cheap
and testable without Radiant.  Angles follow Radiant's GoToPosition dialog:
yaw in degrees counter-clockwise from +x (east), pitch in degrees, positive
looking *down*.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Sequence

EYE = 60.0          # player eye height over the floor
DOOR_STEP = 24.0    # how far into the room from the doorway's centre
WALL_CLEAR = 10.0   # never closer than this to a wall
CEILING_CLEAR = 12.0
EYE_PITCH = 8.0     # a player looks a little down into a room


@dataclass(frozen=True)
class View:
    room: str
    name: str
    x: float
    y: float
    z: float
    pitch: float
    yaw: float

    @property
    def slug(self) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.room)
        return f"{safe}--{self.name}"

    def radiant_text(self) -> str:
        """What goes into Radiant's Jump Camera To box: ``X Y Z P Y``."""
        return f"{self.x:.0f} {self.y:.0f} {self.z:.0f} {self.pitch:.1f} {self.yaw:.1f}"

    def as_dict(self) -> dict:
        return asdict(self)


def _clamp(v: float, lo: float, hi: float) -> float:
    if lo > hi:
        return (lo + hi) / 2.0
    return min(max(v, lo), hi)


def _yaw(fx: float, fy: float, tx: float, ty: float) -> float:
    return round(math.degrees(math.atan2(ty - fy, tx - fx)) % 360.0, 1)


def doorway_views(area, openings: Iterable[tuple[str, tuple[float, float, float, float], Mapping]]
                  ) -> list[View]:
    """One eye-height view per opening, standing just inside, facing the room's middle."""
    cx, cy = (area.x0 + area.x1) / 2.0, (area.y0 + area.y1) / 2.0
    out = []
    for index, (name, rect, _info) in enumerate(openings):
        ox, oy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
        # Snap the doorway to the wall it sits in, then step inward.
        ox = _clamp(ox, area.x0, area.x1)
        oy = _clamp(oy, area.y0, area.y1)
        gaps = {"w": ox - area.x0, "e": area.x1 - ox, "s": oy - area.y0, "n": area.y1 - oy}
        side = min(gaps, key=gaps.get)
        dx, dy = {"w": (1, 0), "e": (-1, 0), "s": (0, 1), "n": (0, -1)}[side]
        x = _clamp(ox + dx * DOOR_STEP, area.x0 + WALL_CLEAR, area.x1 - WALL_CLEAR)
        y = _clamp(oy + dy * DOOR_STEP, area.y0 + WALL_CLEAR, area.y1 - WALL_CLEAR)
        z = min(area.floor_z + EYE, area.ceiling_z - CEILING_CLEAR)
        # Face the middle; in a long thin room that is also straight down it.
        yaw = _yaw(x, y, cx, cy) if math.hypot(cx - x, cy - y) > 1 else _yaw(0, 0, dx, dy)
        out.append(View(area.key, f"door{index}-{side}", round(x), round(y), round(z),
                        EYE_PITCH, yaw))
    return out


def corner_views(area) -> list[View]:
    """High views from the south-west and north-east corners across the room."""
    out = []
    z = max(area.floor_z + EYE, area.ceiling_z - CEILING_CLEAR)
    for name, (fx, fy, tx, ty) in (
        ("corner-sw", (area.x0, area.y0, area.x1, area.y1)),
        ("corner-ne", (area.x1, area.y1, area.x0, area.y0)),
    ):
        sx = 1 if tx > fx else -1
        sy = 1 if ty > fy else -1
        x, y = fx + sx * WALL_CLEAR, fy + sy * WALL_CLEAR
        span = math.hypot(tx - x, ty - y)
        # Aim at the floor 60% of the way across: the far wall stays in frame.
        pitch = round(math.degrees(math.atan2(z - area.floor_z, 0.6 * span)), 1) if span else 45.0
        out.append(View(area.key, name, round(x), round(y), round(z), pitch,
                        _yaw(x, y, tx, ty)))
    return out


#: How far a camera keeps from any prop's box, and the step it moves by.
PROP_CLEAR = 20.0
CLEAR_STEP = 16.0

Box = tuple  # (x0, y0, x1, y1, z0, z1)


def _inside(x: float, y: float, z: float, box: Box, margin: float = PROP_CLEAR) -> bool:
    x0, y0, x1, y1, z0, z1 = box
    return (x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin
            and z0 - margin <= z <= z1 + margin)


def clear_of_props(view: View, area, boxes: Sequence[Box]) -> View:
    """*view* moved toward the room's middle until it is clear of every prop box.

    WHY: in a room lined with corn a corner of the room box lies inside
    the corn wall, and a camera there stands inside a stalk.
    The view keeps its height and aims at the same point it aimed at before.
    If nowhere on the way to the middle is clear, the view is left as it was.
    """
    if not boxes or not any(_inside(view.x, view.y, view.z, b) for b in boxes):
        return view
    cx, cy = (area.x0 + area.x1) / 2.0, (area.y0 + area.y1) / 2.0
    dist = math.hypot(cx - view.x, cy - view.y)
    if dist < 1:
        return view
    # The point the old view looked at (on its yaw line, one room-diagonal out).
    reach = math.hypot(area.x1 - area.x0, area.y1 - area.y0)
    tx = view.x + math.cos(math.radians(view.yaw)) * reach
    ty = view.y + math.sin(math.radians(view.yaw)) * reach
    steps = int(dist // CLEAR_STEP)
    for i in range(1, steps + 1):
        f = i * CLEAR_STEP / dist
        x, y = view.x + (cx - view.x) * f, view.y + (cy - view.y) * f
        if not any(_inside(x, y, view.z, b) for b in boxes):
            yaw = _yaw(x, y, tx, ty) if math.hypot(tx - x, ty - y) > 1 else view.yaw
            return View(view.room, view.name, round(x), round(y), view.z, view.pitch, yaw)
    return view


# ----------------------------------------------------------------------
# Narrow and maze rooms: stand in the paths, look along them and at the set
# pieces.  WHY: in a maze room the room box's corners are inside the
# corn, and the move toward the middle ends in another corridor's corn, so
# no corner view shows a path or a set piece.
# ----------------------------------------------------------------------
#: Grid step of the free-space map, and how far a camera keeps from a solid
#: brush (props keep :data:`PROP_CLEAR`).
GRID = 32.0
SOLID_CLEAR = 12.0
#: A room whose share of free eye-height ground is under this is a maze (or
#: too cluttered for a corner to see across): it gets path and focus views.
MAZE_FREE_SHARE = 0.5
#: A path view looks along at least this much free ground.
PATH_MIN_RUN = 384.0
#: Distance from a camera to a set piece it looks at (best near the middle).
FOCUS_NEAR, FOCUS_BEST, FOCUS_FAR = 160.0, 360.0, 800.0
#: Views of one room keep at least this far apart.
VIEW_SPREAD = 512.0
#: Path and focus views stand a little over eye height, looking a little
#: down, so the ground dressing does not fill the frame.
PATH_EYE = EYE + 30.0
PATH_PITCH = 10.0


class FreeMap:
    """Which grid cells of *area* a camera can stand in at height *z*: clear of
    every solid box by :data:`SOLID_CLEAR` and of every prop box by
    :data:`PROP_CLEAR`.  Boxes are ``(x0, y0, x1, y1, z0, z1)``."""

    def __init__(self, area, z: float, solids: Sequence[Box] = (), props: Sequence[Box] = ()):
        self.area, self.z = area, z
        self.nx = max(1, int((area.x1 - area.x0) // GRID))
        self.ny = max(1, int((area.y1 - area.y0) // GRID))
        self.ox = area.x0 + ((area.x1 - area.x0) - self.nx * GRID) / 2.0
        self.oy = area.y0 + ((area.y1 - area.y0) - self.ny * GRID) / 2.0
        edge = WALL_CLEAR
        self.free = [[True] * self.ny for _ in range(self.nx)]
        for i in range(self.nx):
            for j in range(self.ny):
                x, y = self.centre(i, j)
                if not (area.x0 + edge <= x <= area.x1 - edge and area.y0 + edge <= y <= area.y1 - edge):
                    self.free[i][j] = False
        for boxes, margin in ((solids, SOLID_CLEAR), (props, PROP_CLEAR)):
            for x0, y0, x1, y1, z0, z1 in boxes:
                if z0 - margin > z or z1 + margin < z:
                    continue
                i0, i1 = self._index(x0 - margin, self.ox, self.nx), self._index(x1 + margin, self.ox, self.nx)
                j0, j1 = self._index(y0 - margin, self.oy, self.ny), self._index(y1 + margin, self.oy, self.ny)
                for i in range(max(i0, 0), min(i1, self.nx - 1) + 1):
                    cx = self.ox + (i + 0.5) * GRID
                    if not (x0 - margin <= cx <= x1 + margin):
                        continue
                    col = self.free[i]
                    for j in range(max(j0, 0), min(j1, self.ny - 1) + 1):
                        cy = self.oy + (j + 0.5) * GRID
                        if y0 - margin <= cy <= y1 + margin:
                            col[j] = False

    @staticmethod
    def _index(v: float, origin: float, n: int) -> int:
        return int(math.floor((v - origin) / GRID))

    def centre(self, i: int, j: int) -> tuple[float, float]:
        return self.ox + (i + 0.5) * GRID, self.oy + (j + 0.5) * GRID

    def at(self, x: float, y: float) -> bool:
        i, j = self._index(x, self.ox, self.nx), self._index(y, self.oy, self.ny)
        return 0 <= i < self.nx and 0 <= j < self.ny and self.free[i][j]

    @property
    def share(self) -> float:
        cells = self.nx * self.ny
        return sum(map(sum, self.free)) / cells if cells else 0.0

    def cells(self) -> Iterable[tuple[int, int]]:
        for i in range(self.nx):
            for j in range(self.ny):
                if self.free[i][j]:
                    yield i, j

    def run(self, i: int, j: int, di: int, dj: int) -> float:
        """Free ground from cell ``(i, j)`` along a grid direction."""
        n = 0
        while 0 <= i + di * (n + 1) < self.nx and 0 <= j + dj * (n + 1) < self.ny \
                and self.free[i + di * (n + 1)][j + dj * (n + 1)]:
            n += 1
        return n * GRID * math.hypot(di, dj)

    def sees(self, ax: float, ay: float, bx: float, by: float, stop_short: float = 0.0) -> bool:
        """Free ground all along the line from *a* to *b*, but for its last
        *stop_short* units (the set piece itself stands there)."""
        d = math.hypot(bx - ax, by - ay)
        n = int(max(0.0, d - stop_short) // (GRID / 2.0))
        return all(self.at(ax + (bx - ax) * k * (GRID / 2.0) / d, ay + (by - ay) * k * (GRID / 2.0) / d)
                   for k in range(1, n + 1)) if d > 0 else True


def _far_from(x: float, y: float, views: Sequence[View]) -> bool:
    return all(math.hypot(x - v.x, y - v.y) >= VIEW_SPREAD for v in views)


def focus_views(area, free: FreeMap, focus: Sequence[tuple[float, float, float]]) -> list[View]:
    """One view per set piece (*focus* point) in *area*: from a free cell with
    a clear line to it, as near :data:`FOCUS_BEST` away as there is."""
    out: list[View] = []
    z = min(area.floor_z + PATH_EYE, area.ceiling_z - CEILING_CLEAR)
    for k, (fx, fy, fz) in enumerate(focus):
        if not (area.x0 <= fx <= area.x1 and area.y0 <= fy <= area.y1):
            continue
        best = None
        for i, j in free.cells():
            x, y = free.centre(i, j)
            d = math.hypot(fx - x, fy - y)
            if not (FOCUS_NEAR <= d <= FOCUS_FAR):
                continue
            score = abs(d - FOCUS_BEST)
            if best is not None and score >= best[0]:
                continue
            if free.sees(x, y, fx, fy, stop_short=FOCUS_NEAR * 0.75):
                best = (score, x, y, d)
        if best is None:
            continue
        _, x, y, d = best
        pitch = round(math.degrees(math.atan2(z - fz, d)), 1)
        out.append(View(area.key, f"focus{k}", round(x), round(y), round(z), pitch, _yaw(x, y, fx, fy)))
    return out


def path_views(area, free: FreeMap, *, count: int = 2, taken: Sequence[View] = ()) -> list[View]:
    """Views standing in the paths, looking along the longest free runs."""
    z = min(area.floor_z + PATH_EYE, area.ceiling_z - CEILING_CLEAR)
    runs = []
    for i, j in free.cells():
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            length = free.run(i, j, di, dj)
            if length >= PATH_MIN_RUN:
                runs.append((length, i, j, di, dj))
    runs.sort(key=lambda r: (-r[0], r[1], r[2], r[3], r[4]))
    out: list[View] = []
    for length, i, j, di, dj in runs:
        x, y = free.centre(i, j)
        if not _far_from(x, y, [*taken, *out]):
            continue
        out.append(View(area.key, f"path{len(out)}", round(x), round(y), round(z), PATH_PITCH,
                        _yaw(0, 0, di, dj)))
        if len(out) >= count:
            break
    return out


def room_views(area, openings: Sequence, *, limit: int | None = None,
               boxes: Sequence[Box] = (), solids: Sequence[Box] = (),
               focus: Sequence[tuple[float, float, float]] = ()) -> list[View]:
    """Set-piece views first (*focus*, the room's declared scene points), then
    corners (they show the most), then doorways, up to *limit*; each moved
    clear of the props in *boxes*.

    A maze or narrow room (under :data:`MAZE_FREE_SHARE` free ground at eye
    height, walls in *solids*) gets views standing in its paths instead of
    its corners, which are inside the walls."""
    free = FreeMap(area, min(area.floor_z + PATH_EYE, area.ceiling_z - CEILING_CLEAR), solids, boxes)
    first = focus_views(area, free, focus) if focus else []
    if free.share < MAZE_FREE_SHARE:
        views = first + path_views(area, free, taken=first) + doorway_views(area, openings)
    else:
        views = first + corner_views(area) + doorway_views(area, openings)
    views = [v if v.name.startswith(("focus", "path")) else clear_of_props(v, area, boxes)
             for v in views]
    return views if limit is None else views[:max(0, limit)]


def plan_views(bp, *, rooms: Sequence[str] | None = None, limit: int | None = None) -> list[View]:
    """Every room's views from a built blueprint (what the review measures)."""
    from ..blueprint.model import _solid_bounds
    from ..dressing.scene import scene_for
    from ..review.facts import _areas, _openings, _props

    areas = _areas(bp)
    openings = _openings(bp, areas)
    boxes: dict[str, list] = {}
    for prop in _props(bp, areas):
        if prop.area is not None and prop.bounds and prop.z_low is not None \
                and prop.z_high is not None:
            boxes.setdefault(prop.area.key, []).append((*prop.bounds, prop.z_low, prop.z_high))
    solids = []
    for solid in bp.world_solids():
        b = _solid_bounds(solid)
        solids.append((b.mins.x, b.mins.y, b.maxs.x, b.maxs.y, b.mins.z, b.maxs.z))
    wanted = None if rooms is None else {r.lower() for r in rooms}
    out = []
    for area in areas:
        if wanted is not None and area.key.lower() not in wanted \
                and area.room_id.lower() not in wanted:
            continue
        mine = [s for s in solids if s[0] <= area.x1 and s[2] >= area.x0
                and s[1] <= area.y1 and s[3] >= area.y0]
        scene = scene_for(bp, area.room_id, area.key)
        out.extend(room_views(area, openings.get(area.key, []), limit=limit,
                              boxes=boxes.get(area.key, ()), solids=mine,
                              focus=getattr(scene, "focus", ()) if scene else ()))
    return out
