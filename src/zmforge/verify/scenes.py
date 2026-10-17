"""S1-S4: every area is a scene, dressed near the stock density (docs/map-design-method.md).

Warnings, never errors: a thin room still plays.  The targets are the stock
``zm_giant`` numbers in :data:`zmforge.dressing.scene.STOCK`; a room warns when
a measure is under :data:`~zmforge.dressing.scene.WARN_SHARE` of it (a quarter),
i.e. far below stock, not merely below.

``S1`` a room with no declared scene (:func:`zmforge.dressing.declare_scene`),
    or a scene whose beats (fire, wreck, barricade...) the room does not show,
    or whose ``tell`` (the one telling detail) no prop in the room matches, or
    that names a ``cause`` with no ``tell`` to prove it (section 8).
``S2`` props per k2, not counting floor litter, under a quarter of the stock
    non-trim figure (40% in a room of 0.5 k2 or more,
    :data:`~zmforge.dressing.scene.BIG_ROOM_SHARE`), or nothing above head
    height in a room over 0.25 k2.
``S3`` a room over 0.5 k2 with no set piece (a solid prop at least 72 units
    wide and 36 tall), so its lanes are open floor.
``S4`` an open-air room (or a scene with a fire/smoke/embers beat) with no
    ambient effect at all.
``S5`` a roofed room of 0.5 k2 or more with fewer than
    :data:`~zmforge.dressing.scene.OVERHEAD_WARN` overhead props (origin 160+
    over the floor) per k2: an empty ceiling (stock 113).
``S6`` a roofed room of 0.5 k2 or more with a wall run longer than
    :data:`~zmforge.dressing.scene.FLAT_WALL_RUN` that is one flat material
    floor to ceiling: no skirting, wainscot, rail, counter or column crosses
    it (pictures and lettering hung on it do not count;
    ``zmforge.dressing.walldetail`` details a room's walls).
"""

from __future__ import annotations

from ..dressing.scene import (
    BIG_ROOM_K2,
    BIG_ROOM_SHARE,
    FLAT_WALL_RUN,
    OVERHEAD_WARN,
    STOCK,
    WARN_SHARE,
    scene_for,
    scenes_of,
    tell_matches,
)
from .report import Report, warning

__all__ = ["check_scenes", "flat_wall_runs"]


def flat_wall_runs(blueprint, area, props, *, strip: float = 12.0, cell: float = 8.0
                   ) -> dict[str, float]:
    """The longest flat stretch of each of *area*'s four walls, units: wall
    cells (*cell* long, *strip* deep) crossed by no horizontal band (a
    skirting, wainscot, rail, counter: a brush 32+ units long and at most 72
    tall), no column (a brush over 60% of the wall's height) and no opening.
    Pictures, signs and lettering hung on a flat wall do not break a run:
    the wall behind them is still one material floor to ceiling.  *props*
    is unused (kept for callers that pass the room's props)."""
    from ..blueprint.elements import Massing, Room

    feats: list[tuple[float, float, float, float]] = []
    lo_z, hi_z = area.floor_z + 1.0, area.ceiling_z - 1.0
    tall = 0.6 * (area.ceiling_z - area.floor_z)
    for m in blueprint.elements(Massing):
        for sol in m.solids:
            pts = [q for f in sol.faces for q in f.points]
            x0, y0, z0 = min(q.x for q in pts), min(q.y for q in pts), min(q.z for q in pts)
            x1, y1, z1 = max(q.x for q in pts), max(q.y for q in pts), max(q.z for q in pts)
            if z1 <= lo_z or z0 >= hi_z or min(x1 - x0, y1 - y0) > 48.0:
                continue
            band = max(x1 - x0, y1 - y0) >= 32.0 and z1 - z0 <= 72.0
            column = z1 - z0 >= tall
            if band or column:
                feats.append((x0, y0, x1, y1))
    room = area.room if isinstance(area.room, Room) else None
    if room is not None:
        for box in room.aperture_boxes:
            feats.append((box.mins.x, box.mins.y, box.maxs.x, box.maxs.y))
    out: dict[str, float] = {}
    for side in ("south", "north", "west", "east"):
        along_x = side in ("south", "north")
        if side == "south":
            sx0, sy0, sx1, sy1 = area.x0, area.y0 - 2.0, area.x1, area.y0 + strip
        elif side == "north":
            sx0, sy0, sx1, sy1 = area.x0, area.y1 - strip, area.x1, area.y1 + 2.0
        elif side == "west":
            sx0, sy0, sx1, sy1 = area.x0 - 2.0, area.y0, area.x0 + strip, area.y1
        else:
            sx0, sy0, sx1, sy1 = area.x1 - strip, area.y0, area.x1 + 2.0, area.y1
        hits = [(f[0], f[2]) if along_x else (f[1], f[3]) for f in feats
                if f[2] > sx0 and f[0] < sx1 and f[3] > sy0 and f[1] < sy1]
        lo, hi = (area.x0, area.x1) if along_x else (area.y0, area.y1)
        best = run = 0.0
        t = lo
        while t < hi:
            c = min(hi, t + cell)
            if any(a < c and b > t for a, b in hits):
                run = 0.0
            else:
                run += c - t
                best = max(best, run)
            t = c
        out[side] = best
    return out


def check_scenes(blueprint) -> Report:
    from ..review.facts import _areas, _props, is_floor_litter
    from ..review.scene_metrics import collect_art

    report = Report()
    areas = _areas(blueprint)
    if not areas:
        return report
    props = _props(blueprint, areas)
    art = collect_art(blueprint, areas, props) if scenes_of(blueprint) else None
    from ..blueprint.elements import AmbientFx

    effects = blueprint.elements(AmbientFx)
    declared = bool(scenes_of(blueprint))
    by_id = getattr(blueprint, "_by_id", {})
    for area in areas:
        room = by_id.get(area.room_id) if area.room_id else None
        if room is not None and getattr(room, "reachable", True) is False:
            # A room the map declares nobody stands in (a sealed vault, a
            # view) is looked at, not played in; the S rules are about rooms
            # a player walks (the same exemption Z18 and Z46 make).
            continue
        k2 = area.area / 1e6
        mine = [p for p in props if p.area is area]
        litter = sum(1 for p in mine if is_floor_litter(p, area))
        rid = area.room_id
        if art is not None:
            a = art[area.key]
            if a["scene"] is None:
                report.add(warning("S1", f"{area.key}: no scene declared (what happened here?)", rid))
            elif a["beats_missing"]:
                report.add(warning("S1", f"{area.key}: scene promises {a['beats_missing']} but the "
                                         "room shows none of it", rid))
        scene = scene_for(blueprint, area.room_id, area.key.split(" (")[0]) if declared else None
        if scene is not None and scene.tell:
            if not any(tell_matches(scene.tell, p.model, p.id) for p in mine):
                report.add(warning("S1", f"{area.key}: the scene's telling detail {scene.tell!r}"
                                         + (f" (proof of: {scene.cause})" if scene.cause else "")
                                         + " is not in the room", rid))
        elif scene is not None and scene.cause:
            report.add(warning("S1", f"{area.key}: the scene names a cause ({scene.cause}) but no "
                                     "telling detail to prove it (declare_scene(..., tell=...))",
                               rid))
        if k2 < 0.05:
            continue
        per_k2 = (len(mine) - litter) / k2
        share = BIG_ROOM_SHARE if k2 >= BIG_ROOM_K2 else WARN_SHARE
        floor = STOCK["props_non_trim"] * share
        if per_k2 < floor:
            report.add(warning("S2", f"{area.key}: {per_k2:.0f} props per 1000x1000 (litter not "
                                     f"counted), stock {STOCK['props_non_trim']:.0f}; warn under "
                                     f"{floor:.0f} ({share:.0%} of stock)", rid))
        roofed = area.room is not None and getattr(area.room, "roofed", True)
        if k2 >= BIG_ROOM_K2 and roofed:
            overhead = sum(1 for p in mine if p.z - area.floor_z >= 160.0) / k2
            if overhead < OVERHEAD_WARN:
                report.add(warning("S5", f"{area.key}: {overhead:.0f} overhead props per 1000x1000 "
                                         f"(stock {STOCK['overhead_props']:.0f}); warn under "
                                         f"{OVERHEAD_WARN:.0f}: hang lamps, ducts, pipes, beams "
                                         "(zmforge.dressing.walldetail)", rid))
            runs = flat_wall_runs(blueprint, area, mine)
            bare = {s: r for s, r in runs.items() if r > FLAT_WALL_RUN}
            if bare:
                worst = max(bare.values())
                report.add(warning("S6", f"{area.key}: {len(bare)} wall(s) with a bare run over "
                                         f"{FLAT_WALL_RUN:.0f} units (longest {worst:.0f}, "
                                         f"{', '.join(sorted(bare))}): one flat material floor to "
                                         "ceiling, no skirting, rail, wainscot or column "
                                         "(zmforge.dressing.walldetail)", rid))
        above = sum(1 for p in mine if p.z - area.floor_z >= 48.0)
        if k2 >= 0.25 and above == 0:
            report.add(warning("S2", f"{area.key}: nothing above head-height bands (mid/overhead "
                                     "layers empty; stock puts 19% of props there)", rid))
        if k2 >= 0.5:
            big = [p for p in mine if p.solid and p.bounds and p.z_high is not None
                   and max(p.bounds[2] - p.bounds[0], p.bounds[3] - p.bounds[1]) >= 72.0
                   and p.z_high - p.z_low >= 36.0]
            if not big:
                report.add(warning("S3", f"{area.key}: {k2:.2f} k2 with no set piece to split "
                                         "its lanes (stock: 2.1 set pieces per k2)", rid))
        room = area.room
        open_air = room is not None and not getattr(room, "roofed", True)
        mine_fx = [e for e in effects if area.holds(e.position.x, e.position.y, 32.0)]
        if open_air and not mine_fx:
            report.add(warning("S4", f"{area.key}: open-air room with no fire, smoke or embers "
                                     f"(stock {STOCK['fx']:.0f} effects per k2)", rid))
    if not declared:
        report.add(warning("S1", "no scenes declared: give each area a one-line story "
                                 "(zmforge.dressing.declare_scene)"))
    return report
