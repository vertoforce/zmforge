"""``D8``: how much lamp light reaches each room's floor, estimated before the bake.

WHY
---
A room can pass every lamp-distance check and still be far too dark.
``D5`` and ``D7`` ask
whether a lamp is *near* a thing or a path; neither asks how much light the
lamps actually put on the floor, and a room lit only by glows passes both.
This check
adds up the lamps' light on a grid of floor points in every room, the way the
emitter writes them, and compares the room with thresholds calibrated on the
rooms that read well in game.

THE ESTIMATE
------------
A lamp's ``stops`` is log2 of its intensity and only means anything against
the map's exposure (:mod:`zmforge.lighting`), so a lamp contributes

    2 ** (stops - exposure) * min(1, (REF / d) ** 2) * ramp(d) * luma(colour)

at a floor point ``d`` units away (3-D), where ``ramp`` is the emitter's
``far_edge`` cut-off (full strength to ``radius * (1 - far_edge)``, linear to
nothing at ``radius``) and ``exposure`` is the sun preset's ev plus the
atmosphere's exposure pin (``Enclosure.exposure_stops``, the worldspawn's
``evmin``/``evmax``).  So 1.0 is "one lamp at the map's exposure, ``REF``
units away".  Only lamps inside the room count: walls stop light, and a
doorway's spill is a bonus, not something to plan a room's light on.

It is an estimate of direct light, with no bounce and no surface colour.  It
cannot see sun through a window; the bake can, and :func:`image_levels` (the
post-bake half, run by ``zmforge render --baked``) measures the pictures.
Sunlit rooms (``Room.sunlit``) are not scored: the sun is their light.

AFTER THE BAKE
--------------
:func:`image_levels` reads each room's ``--baked`` render and takes the mean
linear luminance of its pictures; a room more than :data:`IMAGE_STOPS_UNDER`
stops under the map's median room, or with an sRGB mean under
:data:`IMAGE_FLOOR`, is flagged.  Advisory: it prints, it never stops a build.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Report, warning

__all__ = [
    "REF",
    "SAMPLE",
    "DIM",
    "DARK_SHARE",
    "DARK_MEAN",
    "JUMP_STOPS",
    "RoomLight",
    "room_light",
    "openings",
    "check_light_level",
    "IMAGE_STOPS_UNDER",
    "IMAGE_FLOOR",
    "image_levels",
    "image_advisories",
]

#: A lamp at the map's exposure gives 1.0 at this distance (and no more nearer).
REF = 128.0
#: Floor grid pitch.
SAMPLE = 48.0
#: How far above the floor a sample is taken.
LIFT = 8.0
#: A floor point under this estimate is dark.
DIM = 0.25
#: A room with more than this share of its floor dark warns.
#: Calibrated on rooms that read well in game against rooms that read far
#: too dark: zm_cemetery's shed 36% dark / mean 0.29, its stairs 42% / 0.55,
#: ossuary 31% / 0.47, chapel 28% / 0.50, vault 22% / 0.66 (all read well,
#: the underground included) against glow-lit and under-lit rooms at
#: 100% / 0.00 and 100% / 0.05.
DARK_SHARE = 0.6
#: A room whose mean is under this warns (see :data:`DARK_SHARE`).
DARK_MEAN = 0.2
#: Two connected rooms whose medians differ by more than this many stops warn.
JUMP_STOPS = 3.0


@dataclass(frozen=True)
class RoomLight:
    """One room's estimate: ``mean``, ``median`` and ``p10`` of the floor
    samples, ``dark`` the share under :data:`DIM`, ``lamps`` how many lamps
    stand in it."""

    room: str
    mean: float
    median: float
    p10: float
    dark: float
    samples: int
    lamps: int


def _exposure(bp) -> float:
    from ..blueprint.elements import Enclosure

    found = bp.elements(Enclosure)
    pin = found[0].exposure_stops if found else None  # type: ignore[attr-defined]
    return bp.exposure + (pin or 0.0)


def _luma(colour) -> float:
    r, g, b = colour
    return max(0.0, 0.2126 * r + 0.7152 * g + 0.0722 * b)


def lamp_terms(bp) -> list[tuple[float, float, float, float, float, float]]:
    """``(x, y, z, weight, radius, full)`` per lamp: weight is the lamp's
    intensity over the map's exposure times its colour's luma; ``full`` the
    distance its cut-off ramp starts."""
    from ..blueprint.elements import Lamp
    from ..lighting import LAMP_FAR_EDGE

    ev = _exposure(bp)
    out = []
    for lamp in bp.elements(Lamp):
        p = lamp.position
        weight = 2.0 ** (bp.stops_of(lamp) - ev) * _luma(lamp.colour)
        out.append((p.x, p.y, p.z, weight, lamp.radius, lamp.radius * (1.0 - LAMP_FAR_EDGE)))
    return out


def light_at(terms, x: float, y: float, z: float) -> float:
    """The estimate at one point from *terms* (:func:`lamp_terms`)."""
    total = 0.0
    for lx, ly, lz, weight, radius, full in terms:
        d = math.sqrt((lx - x) ** 2 + (ly - y) ** 2 + (lz - z) ** 2)
        if d >= radius:
            continue
        ramp = 1.0 if d <= full else (radius - d) / (radius - full)
        total += weight * min(1.0, (REF / max(d, 1.0)) ** 2) * ramp
    return total


def _grid(box, pitch: float):
    x0, x1 = box.mins.x, box.maxs.x
    y0, y1 = box.mins.y, box.maxs.y
    nx = max(1, int(round((x1 - x0) / pitch)))
    ny = max(1, int(round((y1 - y0) / pitch)))
    for i in range(nx):
        for j in range(ny):
            yield x0 + (i + 0.5) * (x1 - x0) / nx, y0 + (j + 0.5) * (y1 - y0) / ny


def style_leaves_floor_dark(bp, room, lamps, points, colour, radius) -> bool:
    """Whether *room*, lit by *lamps* plus fill at *points* in *colour* and
    *radius* at the map's default stops, would fail D8's floor test.  Used by
    :meth:`zmforge.blueprint.model.Blueprint.light_rooms` to top a room up."""
    from ..lighting import LAMP_FAR_EDGE, STOPS_OVER_EXPOSURE

    ev = _exposure(bp)
    terms = [(l.position.x, l.position.y, l.position.z,
              2.0 ** (bp.stops_of(l) - ev) * _luma(l.colour), l.radius,
              l.radius * (1.0 - LAMP_FAR_EDGE)) for l in lamps]
    weight = 2.0 ** (bp.exposure + STOPS_OVER_EXPOSURE + bp.brightness_stops - ev) * _luma(colour)
    terms += [(p.x, p.y, p.z, weight, radius, radius * (1.0 - LAMP_FAR_EDGE)) for p in points]
    floor = room.floor_z
    values = [light_at(terms, x, y, floor + LIFT) for x, y in _grid(room.interior, SAMPLE)]
    if not values:
        return False
    mean = sum(values) / len(values)
    dark = sum(1 for v in values if v < DIM) / len(values)
    return dark > DARK_SHARE or mean < DARK_MEAN


def room_light(bp, *, pitch: float = SAMPLE) -> dict[str, RoomLight]:
    """The estimate for every reachable, roofed, not sunlit room, by id."""
    from ..blueprint.elements import Room

    terms = lamp_terms(bp)
    out: dict[str, RoomLight] = {}
    for room in bp.elements(Room):
        if not room.reachable or room.sunlit or not room.roofed:  # type: ignore[attr-defined]
            continue
        box = room.interior  # type: ignore[attr-defined]
        floor = room.floor_z  # type: ignore[attr-defined]
        top = box.maxs.z
        here = [t for t in terms
                if box.mins.x - 8.0 <= t[0] <= box.maxs.x + 8.0
                and box.mins.y - 8.0 <= t[1] <= box.maxs.y + 8.0
                and floor - 8.0 <= t[2] <= top + 8.0]
        values = sorted(light_at(here, x, y, floor + LIFT) for x, y in _grid(box, pitch))
        if not values:
            continue
        n = len(values)
        out[room.id] = RoomLight(
            room=room.id,
            mean=sum(values) / n,
            median=values[n // 2],
            p10=values[int(0.1 * (n - 1))],
            dark=sum(1 for v in values if v < DIM) / n,
            samples=n,
            lamps=len(here),
        )
    return out


def _touch(a, b, pad: float = 2.0) -> bool:
    return (a.mins.x <= b.maxs.x + pad and b.mins.x <= a.maxs.x + pad
            and a.mins.y <= b.maxs.y + pad and b.mins.y <= a.maxs.y + pad
            and a.mins.z <= b.maxs.z + pad and b.mins.z <= a.maxs.z + pad)


def openings(bp) -> dict[str, dict]:
    """Per room id: ``rooms``, the ids of the rooms its openings lead into,
    and ``sky``, how many of its openings give onto open air (a yard, a
    sunlit or roofless room, or nothing at all)."""
    from ..blueprint.elements import Room, Yard

    rooms = list(bp.elements(Room))
    yards = list(bp.elements(Yard))
    out: dict[str, dict] = {}
    for room in rooms:
        into: set[str] = set()
        sky = 0
        for hole in room.aperture_boxes:  # type: ignore[attr-defined]
            others = [o for o in rooms if o is not room and _touch(hole, o.outer)]  # type: ignore[attr-defined]
            into.update(o.id for o in others)
            open_air = [o for o in others if o.sunlit or not o.roofed]  # type: ignore[attr-defined]
            if open_air or not others or any(_touch(hole, y.outer) for y in yards):  # type: ignore[attr-defined]
                sky += 1
        out[room.id] = {"rooms": into, "sky": sky}
    return out


def check_light_level(bp, lit: dict[str, RoomLight] | None = None) -> Report:
    """``D8``: every roofed room's floor lit by its own lamps, and no
    connected room far brighter or darker (see the module docstring)."""
    from ..blueprint.elements import Room

    report = Report()
    lit = room_light(bp) if lit is None else lit
    holes = openings(bp)
    sunlit = {r.id for r in bp.elements(Room) if r.sunlit or not r.roofed}  # type: ignore[attr-defined]
    for key, room in lit.items():
        if room.dark > DARK_SHARE or room.mean < DARK_MEAN:
            sky = holes.get(key, {}).get("sky", 0)
            day = (f"; its {sky} opening(s) onto open air will light it with the day instead, "
                   "a sunlit room indoors" if sky else "")
            report.add(warning(
                "D8", f"room {key}: {room.dark:.0%} of its floor is under {DIM:g} of the "
                f"estimated lamp light (mean {room.mean:.2f}, {room.lamps} lamp(s)); it will "
                f"bake dark{day}", key))
    seen: set[frozenset] = set()
    for key, info in holes.items():
        for other in info["rooms"]:
            pair = frozenset((key, other))
            if pair in seen:
                continue
            seen.add(pair)
            if key in lit and other in lit:
                a, b = lit[key].median, lit[other].median
                if min(a, b) <= 0.0:
                    continue
                gap = abs(math.log2(a / b))
                if gap > JUMP_STOPS:
                    dim, bright = (key, other) if a < b else (other, key)
                    report.add(warning(
                        "D8", f"rooms {dim} and {bright} are joined but {gap:.1f} stops apart "
                        f"in estimated lamp light (over {JUMP_STOPS:g}): walking through reads as "
                        "a flash; light them alike or grade the step", dim))
            elif (key in lit) != (other in lit) and (key in sunlit or other in sunlit):
                inside = key if key in lit else other
                if lit[inside].median < DARK_MEAN:
                    report.add(warning(
                        "D8", f"room {inside} opens onto sunlit {other if inside == key else key} "
                        f"with a dim floor (median {lit[inside].median:.2f}): the step from sun to "
                        "it reads black", inside))
    return report


# ---------------------------------------------------------------------------
# After the bake: the rendered pictures
# ---------------------------------------------------------------------------
#: A room whose baked pictures are more than this many stops under the map's
#: median room is flagged.
IMAGE_STOPS_UNDER = 1.5
#: ... or whose pictures' mean sRGB value (0-255) is under this.
IMAGE_FLOOR = 40.0
#: A room is blown out when more than this share of its pixels is near white
#: (sRGB 245+), or it renders more than :data:`IMAGE_STOPS_UNDER` stops *over*
#: the median room (spawn closets behind
#: windows read as blown-out white next to dim panelled rooms).
IMAGE_BLOWN_SHARE = 0.25


def _linear(v):
    import numpy as np

    c = v / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def image_levels(shots: dict[str, list[str]]) -> dict[str, dict]:
    """Per room, from its pictures (``{room: [png, ...]}``, a render
    manifest's ``shots``): ``srgb`` the mean 0-255 value, ``linear`` the mean
    linear luminance, ``p90`` its 90th percentile, ``stops_under_median`` how
    far under the map's median room it is, and ``flag``."""
    import numpy as np
    from PIL import Image

    out: dict[str, dict] = {}
    for room, paths in shots.items():
        srgb, lin, hi, blown = [], [], [], []
        for path in paths:
            try:
                img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
            except OSError:
                continue
            luma = img @ np.array([0.2126, 0.7152, 0.0722])
            srgb.append(float(luma.mean()))
            blown.append(float((luma >= 245.0).mean()))
            l = _linear(luma)
            lin.append(float(l.mean()))
            hi.append(float(np.percentile(l, 90)))
        if lin:
            out[room] = {"srgb": sum(srgb) / len(srgb), "linear": sum(lin) / len(lin),
                         "p90": sum(hi) / len(hi), "blown": sum(blown) / len(blown)}
    if not out:
        return out
    ordered = sorted(v["linear"] for v in out.values())
    median = ordered[len(ordered) // 2]
    for v in out.values():
        under = math.log2(median / v["linear"]) if v["linear"] > 0 and median > 0 else math.inf
        v["stops_under_median"] = under
        v["dark"] = under > IMAGE_STOPS_UNDER or v["srgb"] < IMAGE_FLOOR
        v["bright"] = -under > IMAGE_STOPS_UNDER or v["blown"] > IMAGE_BLOWN_SHARE
        v["flag"] = v["dark"] or v["bright"]
    return out


def image_advisories(levels: dict[str, dict]) -> list[str]:
    """One line per flagged room, darkest first, then the blown-out ones."""
    out = []
    for _, k in sorted(((-v["stops_under_median"], k) for k, v in levels.items()
                        if v.get("dark"))):
        out.append(f"D8 (baked): room {k} renders {levels[k]['stops_under_median']:.1f} stops "
                   f"under the map's median room (mean {levels[k]['srgb']:.0f}/255); it plays dark")
    for _, k in sorted(((v["stops_under_median"], k) for k, v in levels.items()
                        if v.get("bright"))):
        out.append(f"D8 (baked): room {k} renders {-levels[k]['stops_under_median']:.1f} stops "
                   f"over the map's median room, {levels[k]['blown']:.0%} of it near white; "
                   "it plays blown out")
    return out
