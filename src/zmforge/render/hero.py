"""The hero camera: the one picture that sells a map (Workshop thumbnail, preview card).

Each recipe's hero is a :class:`HeroSpec` in :data:`HEROES`: the room to stand
in, the thing to look at, and either where to stand or a rule for finding the
spot.  Everything is resolved against the *generated blueprint* (element and
prop ids, room boxes, terrain), never hard-coded coordinates, so a regenerated
or re-laid-out map still gets its shot.  A recipe with no entry gets
:func:`default_spec`'s answer: the largest room, eye level, looking down its
long axis toward its more crowded half.

"Eye level" is :data:`zmforge.render.cameras.EYE` over the ground under the
camera (terrain included), as a player would see it.

The search (a :class:`HeroSpec` without ``stand``) walks a grid over the room
and keeps spots that are clear to stand in (no brush at body height), see the
target (no brush and no terrain on the line to it) and lie in ``distance`` of
it; among those it prefers a long clear view at eye height toward the target
(a corridor looking at it, not a gap in a wall), the middle of ``distance``,
and ``bearing`` when given.  Props are not obstacles: they rarely block a
whole view and never a brush-built landmark.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .cameras import EYE, EYE_PITCH, WALL_CLEAR, View, _yaw

#: The file name a hero render is saved under in its run folder.
HERO_FILE = "hero.png"
#: Longest side of a hero render.  Radiant's camera pane is 1468 x 790 on the
#: render desktop (``radiant.CAMERA_CROP``) and capture only ever shrinks, so
#: anything at or above 1468 gets the pane's full resolution.
HERO_WIDTH = 1920

_STEP = 24.0            # search grid, units
_BODY = 16.0            # how far a stand spot keeps from any brush, in plan
_SAMPLE = 16.0          # line-of-sight sample spacing


@dataclass(frozen=True)
class Feature:
    """A point in the map named by id: the mean of what *pattern* matches.

    *pattern* is a regular expression over element ids and prop ids; with
    *model* only props whose model matches count (the element or the prop id
    still has to match *pattern*).  A lamp or machine gives its position, a
    brush group the centre of its box, a prop group its props' origins.
    *offset* is added in plan and *dz* in height.
    """

    pattern: str
    model: str | None = None
    offset: tuple[float, float] = (0.0, 0.0)
    dz: float = 0.0


@dataclass(frozen=True)
class HeroSpec:
    room: str                                   # area key or room id
    target: Feature | None = None               # None: the default rule's target
    stand: Feature | None = None                # None: search (see module doc)
    distance: tuple[float, float] = (400.0, 1200.0)
    bearing: float | None = None                # from target to camera, deg ccw from +x
    spread: float = 60.0                        # how far off *bearing* is acceptable
    pitch_bias: float = 0.0                     # added to the aim pitch (+ looks lower)
    yaw_bias: float = 0.0                       # added to the aim yaw (+ turns left)
    target_clear: float = 96.0                  # line of sight may stop this short of it
    focus: float = 0.5                          # horizontal crop centre, 0..1
    note: str = ""


#: The most characterful spot of each map, per recipe.
HEROES: dict[str, HeroSpec] = {
    # The counter hall: the partition's one service window and the NOW
    # SERVING board over it, seen from the public floor's south-west so the
    # counter run recedes behind it.
    "dmv": HeroSpec(
        room="windows",
        target=Feature(r"^windows_props$", model=r"bulletin_board"),
        distance=(330.0, 560.0), bearing=225.0, spread=40.0,
        # Tipped down from the board and a little right, so the service window
        # and the OPEN sign sit mid-frame with the floor under them.  A yaw
        # bias of -15 puts a bin and the black screens mid-frame instead.
        pitch_bias=5.0, yaw_bias=-4.0, target_clear=48.0,
        note="counter hall, looking at the NOW SERVING board over the service window"),
    # The hills: stand at the walk's west end between the first pair of path
    # lamps and look east down the lamp-lined walk over the graves.
    "cemetery": HeroSpec(
        room="hills",
        stand=Feature(r"^path_lamp_hills_walk_0[ab]_light$", offset=(-72.0, 0.0)),
        target=Feature(r"^path_lamp_hills_walk_5[ab]_light$", dz=-40.0),
        # Level, and turned a little north: the mausoleum and the graves
        # beside the walk come into the middle instead of the bare path.
        pitch_bias=-2.0, yaw_bias=10.0,
        note="hills walk, west end, looking east between the path lamps"),
    # The maze: down a straight corn corridor at the farm's water tower,
    # which stands over the corn in its clearing.
    "corn_maze": HeroSpec(
        room="mazeentry",
        target=Feature(r"^water_tower_tank$"),
        distance=(650.0, 1300.0), pitch_bias=8.0, target_clear=120.0,
        note="maze corridor looking at the water tower"),
}


# ----------------------------------------------------------------------
# Blueprint lookups
# ----------------------------------------------------------------------
def _area(bp, room: str):
    from ..review.facts import _areas

    areas = _areas(bp)
    want = room.lower()
    for area in areas:
        if area.key.lower() == want or area.room_id.lower() == want:
            return area
    raise KeyError(f"hero room {room!r} is not in the blueprint "
                   f"(rooms: {', '.join(a.key for a in areas)})")


def feature_points(bp, feature: Feature) -> list[tuple[float, float, float]]:
    """Every point *feature* names in *bp* (see :class:`Feature`)."""
    rx = re.compile(feature.pattern)
    mx = re.compile(feature.model) if feature.model else None
    out: list[tuple[float, float, float]] = []
    for element in bp.elements():
        hit = bool(rx.search(element.id))
        if hit and mx is None:
            pos = getattr(element, "position", None)
            if pos is not None:
                out.append((pos.x, pos.y, pos.z))
                continue
            if type(element).__name__ == "Massing":
                b = element.bounds
                out.append(((b.mins.x + b.maxs.x) / 2, (b.mins.y + b.maxs.y) / 2,
                            (b.mins.z + b.maxs.z) / 2))
                continue
        for prop in getattr(element, "props", None) or []:
            if not (hit or rx.search(prop.id or "")):
                continue
            if mx is not None and not mx.search(prop.model):
                continue
            out.append((prop.origin.x, prop.origin.y, prop.origin.z))
    return out


def feature_point(bp, feature: Feature) -> tuple[float, float, float]:
    points = feature_points(bp, feature)
    if not points:
        raise KeyError(f"hero feature {feature.pattern!r} matches nothing in the blueprint")
    n = len(points)
    x, y, z = (sum(p[i] for p in points) / n for i in range(3))
    return (x + feature.offset[0], y + feature.offset[1], z + feature.dz)


def _terrains(bp) -> list:
    from ..blueprint.elements import Terrain

    return [t.record for t in bp.elements(Terrain)]


def _ground(terrains: Sequence, area, x: float, y: float) -> float:
    """The ground under (x, y) in *area*: terrain over the floor when there is any."""
    best = None
    for record in terrains:
        s = record.sample(x, y)
        if s.found and area.floor_z - 32 <= s.z <= area.ceiling_z:
            best = s.z if best is None else max(best, s.z)
    return area.floor_z if best is None else best


def _eye(terrains, area, x: float, y: float) -> float:
    from .cameras import CEILING_CLEAR

    return min(_ground(terrains, area, x, y) + EYE, area.ceiling_z - CEILING_CLEAR)


def _boxes(bp, area, grow: float) -> np.ndarray:
    """Brush boxes (x0 y0 z0 x1 y1 z1) near *area*, walkable floors left out."""
    from ..blueprint.elements import Massing
    from ..blueprint.model import _solid_bounds

    x0, y0, x1, y1 = area.x0 - grow, area.y0 - grow, area.x1 + grow, area.y1 + grow
    rows = []
    for m in bp.elements(Massing):
        for solid in m.solids:
            b = _solid_bounds(solid)
            if b.maxs.x < x0 or b.mins.x > x1 or b.maxs.y < y0 or b.mins.y > y1:
                continue
            # A slab under the eye (a floor, a kerb, a step) blocks nothing.
            if b.maxs.z <= area.floor_z + 24 and m.walkable:
                continue
            rows.append((b.mins.x, b.mins.y, b.mins.z, b.maxs.x, b.maxs.y, b.maxs.z))
    return np.array(rows, dtype=np.float64).reshape(-1, 6)


def _hits(boxes: np.ndarray, pts: np.ndarray, pad: float = 0.0) -> np.ndarray:
    """Per point: inside any box (grown by *pad* in plan)."""
    if not len(boxes) or not len(pts):
        return np.zeros(len(pts), dtype=bool)
    p = pts[:, None, :]
    b = boxes[None, :, :]
    inside = ((p[..., 0] > b[..., 0] - pad) & (p[..., 0] < b[..., 3] + pad)
              & (p[..., 1] > b[..., 1] - pad) & (p[..., 1] < b[..., 4] + pad)
              & (p[..., 2] > b[..., 2]) & (p[..., 2] < b[..., 5]))
    return inside.any(axis=1)


def _line(a, b, stop: float) -> np.ndarray:
    """Points from *a* toward *b*, every :data:`_SAMPLE`, ending *stop* short of *b*."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = float(np.linalg.norm(b - a))
    n = int(max(0.0, length - stop - _SAMPLE) // _SAMPLE)
    if n <= 0:
        return np.zeros((0, 3))
    t = (_SAMPLE + np.arange(n) * _SAMPLE) / length
    return a + t[:, None] * (b - a)


def _terrain_blocks(terrains, pts: np.ndarray) -> bool:
    for x, y, z in pts:
        for record in terrains:
            s = record.sample(float(x), float(y))
            if s.found and s.z > z - 4.0:
                return True
    return False


def _clear_run(boxes, start, toward, length: float) -> float:
    """How far a level line from *start* toward *toward* goes before a brush."""
    end = (toward[0], toward[1], start[2])
    pts = _line(start, end, 0.0)[: int(length // _SAMPLE)]
    hit = _hits(boxes, pts)
    return float(np.argmax(hit) * _SAMPLE if hit.any() else len(pts) * _SAMPLE)


def _bearing_error(bearing: float | None, tx, ty, x, y) -> float:
    if bearing is None:
        return 0.0
    b = math.degrees(math.atan2(y - ty, x - tx)) % 360.0
    return abs((b - bearing + 180.0) % 360.0 - 180.0)


def _search(bp, area, spec: HeroSpec, target) -> tuple[float, float]:
    terrains = _terrains(bp)
    dmin, dmax = spec.distance
    boxes = _boxes(bp, area, grow=64.0)
    tx, ty, tz = target
    margin = WALL_CLEAR + _BODY
    xs = np.arange(area.x0 + margin, area.x1 - margin + 1e-6, _STEP)
    ys = np.arange(area.y0 + margin, area.y1 - margin + 1e-6, _STEP)
    best: tuple[float, float, float] | None = None
    for x in xs:
        for y in ys:
            d = math.hypot(tx - x, ty - y)
            if not dmin <= d <= dmax:
                continue
            berr = _bearing_error(spec.bearing, tx, ty, x, y)
            if berr > spec.spread:
                continue
            z = _eye(terrains, area, x, y)
            ground = z - EYE
            body = np.array([(x, y, ground + 8.0), (x, y, (ground + z) / 2), (x, y, z + 8.0)])
            if _hits(boxes, body, pad=_BODY).any():
                continue
            sight = _line((x, y, z), target, spec.target_clear)
            if _hits(boxes, sight).any() or (terrains and _terrain_blocks(terrains, sight)):
                continue
            run = _clear_run(boxes, (x, y, z), target, d - spec.target_clear)
            score = (2.0 * run / max(d - spec.target_clear, 1.0)
                     - abs(d - (dmin + dmax) / 2) / max(dmax - dmin, 1.0)
                     - (berr / spec.spread if spec.bearing is not None else 0.0))
            if best is None or score > best[0] + 1e-9:
                best = (score, float(x), float(y))
    if best is None:
        raise LookupError(f"no clear hero spot in {area.key} within {spec.distance} "
                          f"of {spec.target}")
    return best[1], best[2]


# ----------------------------------------------------------------------
# The default: largest room, down its long axis toward the crowded half
# ----------------------------------------------------------------------
def _props_in(bp, area) -> list[tuple[float, float]]:
    out = []
    for element in bp.elements():
        for prop in getattr(element, "props", None) or []:
            if area.holds(prop.origin.x, prop.origin.y):
                out.append((prop.origin.x, prop.origin.y))
    return out


def default_spec(bp) -> tuple[object, tuple[float, float], tuple[float, float, float]]:
    """``(area, stand, target)`` for a recipe with no :data:`HEROES` entry."""
    from ..review.facts import _areas

    area = max(_areas(bp), key=lambda a: (a.area, a.key))
    cx, cy = (area.x0 + area.x1) / 2, (area.y0 + area.y1) / 2
    long_x = (area.x1 - area.x0) >= (area.y1 - area.y0)
    props = _props_in(bp, area)
    if long_x:
        high = sum(1 for px, _ in props if px > cx) >= sum(1 for px, _ in props if px < cx)
        near, far = (area.x0, area.x1) if high else (area.x1, area.x0)
        step = WALL_CLEAR + 24 if far > near else -(WALL_CLEAR + 24)
        return area, (near + step, cy), (far, cy, 0.0)
    high = sum(1 for _, py in props if py > cy) >= sum(1 for _, py in props if py < cy)
    near, far = (area.y0, area.y1) if high else (area.y1, area.y0)
    step = WALL_CLEAR + 24 if far > near else -(WALL_CLEAR + 24)
    return area, (cx, near + step), (cx, far, 0.0)


# ----------------------------------------------------------------------
def spec_for(recipe: str) -> HeroSpec | None:
    return HEROES.get(recipe)


def hero_focus(recipe: str) -> float:
    spec = HEROES.get(recipe)
    return spec.focus if spec else 0.5


def hero_view(recipe: str, bp) -> View:
    """*recipe*'s hero camera in its built blueprint *bp*."""
    spec = HEROES.get(recipe)
    terrains = _terrains(bp)
    if spec is None:
        area, (x, y), (tx, ty, _) = default_spec(bp)
        z = _eye(terrains, area, x, y)
        return View(area.key, "hero", round(x), round(y), round(z), EYE_PITCH, _yaw(x, y, tx, ty))
    area = _area(bp, spec.room)
    if spec.target is None:
        _, _, (tx, ty, _) = default_spec(bp)
        tz = None
    else:
        tx, ty, tz = feature_point(bp, spec.target)
    if spec.stand is not None:
        x, y, _ = feature_point(bp, spec.stand)
    else:
        x, y = _search(bp, area, spec, (tx, ty, tz if tz is not None else area.floor_z + EYE))
    z = _eye(terrains, area, x, y)
    if tz is None:
        pitch = EYE_PITCH
    else:
        pitch = -math.degrees(math.atan2(tz - z, math.hypot(tx - x, ty - y)))
    pitch = max(-35.0, min(35.0, round(pitch + spec.pitch_bias, 1)))
    yaw = round((_yaw(x, y, tx, ty) + spec.yaw_bias) % 360.0, 1)
    return View(area.key, "hero", round(x), round(y), round(z), pitch, yaw)
