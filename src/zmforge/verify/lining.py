"""``Z89``: a wall lined with plants is hidden by them, not just dotted.

WHY
---
Length lined is not how much wall is hidden.  A corn maze build lined 94.6% of every corn wall's length with three staggered rows
of stalks, a stalk every 12 units, and still read as a dirt wall with corn in
front of it.  Length lined is the wrong measure: a corn stalk is a stem and a
dozen leaf blades with air between them, so its box says far more than it
hides.  Drawing the real stalk meshes straight onto each face
found 63% of the wall face hidden (p10 46%) and 22% of the strip over the
wall top.

THE RULE
--------
A recipe that lines walls with plants records each lined face on the
blueprint (``bp.lined_faces``, entries of
``(horizontal, face, (s0, s1), sign, floor, top)``, as
:func:`zmforge.dressing.lining.line_face` takes them).  For a spread sample
of those faces this check draws every plant standing in the face's band whose
mesh zmforge generates itself (``props.generated``; stock models have no mesh
here and count as nothing) onto the face, head-on
(:func:`zmforge.dressing.lining.hidden_fraction`), and holds the
length-weighted mean to :data:`MIN_HIDDEN`.  Head-on is the worst view; down
a corridor the rows overlap and hide more.

The mean is not enough: long stretches can still have no stalk.  A map passed at 79% hidden and still
had 78 stretches of 80 units and more with no stalk at all (the longest 421),
behind crates, a wheelbarrow and every keep-out.  So the check also bounds
the worst gap: on *every* lined face, no stretch longer than
:data:`MAX_BARE` without a plant standing in the band
(:func:`zmforge.dressing.lining.longest_bare_run`), less the stretches the
recipe left bare on purpose and says so (``bp.lined_openings``, entries of
``(horizontal, face, sign, a0, a1, why)``: a door, a window, a buy, a lane)
including what is placed after the dressing and clears the plants behind
it (the gamble machine records itself, ``dressing.lining.record_opening``).
A plant counts if zmforge generates its mesh and it stands at least half
the face's height (a pumpkin in the band hides nothing); it hides half its
leaf spread either side of its stem.  Openings are the recipe's own
(``bp.lined_openings``), every room aperture crossing the face (a hole a
player or the hayride goes through) and every interactive item's body (a
wall buy's chalk), 24 wider each way; a lane or a prop in front of a wall is
not one.

A map with no lined faces is not checked.
"""

from __future__ import annotations

from .report import Report, error

__all__ = ["BUY_CODE", "CODE", "MAX_BARE", "buys_on_lined_faces", "MIN_HIDDEN", "SAMPLE", "check_lining", "lined_face_bare", "lined_face_cover"]

CODE = "Z89"
#: A wall buy chalked on a lined face (:func:`buys_on_lined_faces`).
BUY_CODE = "Z91"
#: The floor on the mean share of a lined wall face its plants hide, head-on.
#: The corn maze build that read as thin measured 0.62 over
#: every lined face; the current lining measures 0.74 over every face and
#: 0.79 on this check's sample.
MIN_HIDDEN = 0.75
#: The longest stretch of a lined face no plant hides (:data:`COVER` of
#: each plant's leaf spread either side of its stem), units, outside the
#: openings.  Measured on zm_corn_maze: an earlier build had 78
#: stalk-free runs over 80, the longest 421; the first fix
#: still left a wall buy's 148 and the vignettes' 100-140 bare, which showed
#: in game; with back rows judged by their stems, wall-buy aprons and
#: vignette reserves open to them, the refill and lane-aware tapering, the
#: longest is 70 (a vignette's part set 7 off the wall, so no stalk's
#: footprint fits behind it without standing on it, Z44).
MAX_BARE = 72.0
#: The share of a plant's leaf spread (half-width either side of its stem)
#: counted as hiding the wall behind it in :func:`lined_face_bare`: leaves
#: are blades with air between them, densest near the stem.
COVER = 0.5
#: How far past an opening's own edge (a hole, a buy's chalk) the wall may
#: stay bare: the plants either side taper into it, a tucked stalk's stem
#: keeps :data:`zmforge.recipes.corn_maze_parts.STEM_HALF` off it.
OPENING_EDGE = 24.0
#: How many faces are drawn (spread evenly over the list, longest spans only).
SAMPLE = 48
#: How far either side of a face's band a plant's origin may stand and count.
_REACH = 60.0
#: How far behind the face a plant's origin may stand and count (a tucked
#: plant's origin is in front of the face; one behind a wall is not seen).
_BEHIND = 20.0
#: Band depth assumed when a face entry does not say (lining.DEFAULT_LINING).
_DEPTH = 76.0


def _meshes():
    """``model name -> (positions, triangles)`` (game space, Z up) for every
    library prop zmforge generates itself."""
    import numpy as np

    from ..props.generated import GENERATORS
    from ..props.library import PROPS
    from ..props.xmodel import to_game_space

    out = {}
    for prop in PROPS:
        if prop.kit != "zmforge_generated" or prop.member not in GENERATORS:
            continue
        mesh, _ = to_game_space(GENERATORS[prop.member](), prop.size_units, up="y")
        out[prop.name] = (np.asarray(mesh.positions, float),
                          [t.position for t in mesh.triangles])
    return out


def lined_face_cover(bp, *, sample: int = SAMPLE, meshes=None) -> list[tuple[str, float, float]]:
    """``(face label, length, hidden fraction)`` for a spread sample of
    ``bp.lined_faces``."""
    from ..blueprint.elements import PropScatter
    from ..dressing.lining import hidden_fraction

    faces = [f for f in getattr(bp, "lined_faces", ()) if f[2][1] - f[2][0] >= 96.0]
    if not faces:
        return []
    meshes = meshes if meshes is not None else _meshes()
    step = max(1, len(faces) // sample)
    chosen = faces[::step][:sample]
    plants = [p for s in bp.elements(PropScatter) for p in s.props if p.model in meshes]
    out = []
    for horizontal, face, (s0, s1), sign, floor, top, *rest in chosen:
        depth = rest[0] if rest else _DEPTH
        here = []
        for p in plants:
            off, along = (p.origin.y, p.origin.x) if horizontal else (p.origin.x, p.origin.y)
            d = (off - face) * sign
            # From the face out only: a plant on the far side of the wall
            # (origin a wall's thickness and more behind the face) is hidden.
            if -_BEHIND <= d <= depth + _REACH and s0 - _REACH <= along <= s1 + _REACH \
                    and floor - 40.0 <= p.origin.z <= top:
                pos, tris = meshes[p.model]
                here.append((pos, tris, p.origin.x, p.origin.y, p.origin.z, p.yaw, p.scale,
                             p.pitch, p.roll))
        label = f"{'y' if horizontal else 'x'}={face:g} {s0:g}..{s1:g}"
        out.append((label, s1 - s0, hidden_fraction(horizontal, face, (s0, s1), sign, floor, top, here,
                                                     cell=4.0)))
    return out


def _openings_of(bp) -> list[tuple[bool, float, float, float, float]]:
    """``(horizontal, n0, n1, a0, a1)`` boxes, in plan, a lined face may stay
    bare across: every room's aperture (a hole in the wall a player walks or
    the hayride drives through, perpendicular to it) and every interactive
    item's body but a wall buy's (a machine, a box), :data:`OPENING_EDGE`
    wider either way along the wall.  Not a lane or a prop: those stand in front of
    the wall, and the wall behind them is still seen."""
    from ..blueprint import reach
    from ..blueprint.elements import Room

    boxes = []
    for room in bp.elements(Room):
        for b in getattr(room, "aperture_boxes", ()) or ():
            boxes.append((b.mins.x, b.maxs.x, b.mins.y, b.maxs.y, b.mins.z, b.maxs.z))
    from ..blueprint.elements import WallWeapon

    try:
        # Not a wall buy: it never hangs on a lined face (Z91), so its body
        # excuses no bare corn (the buy exemption hid the
        # bare wall the render showed).
        keeps = reach.keeps_of(e for e in bp.elements() if not isinstance(e, WallWeapon))
    except Exception:  # pragma: no cover - a blueprint without placement data
        keeps = []
    for k in keeps:
        b = k.body
        boxes.append((b.mins.x, b.maxs.x, b.mins.y, b.maxs.y, b.mins.z, b.maxs.z))
    return boxes


def lined_face_bare(bp, *, meshes=None) -> list[tuple[str, float, float, float]]:
    """``(face label, run length, start, end)``: the longest stretch of each
    of ``bp.lined_faces`` no plant hides, less its openings.  A plant hides
    :data:`COVER` of its leaf spread either side of its stem, along the face,
    as seen from the walk side (its own band)."""
    import numpy as np

    from ..blueprint.elements import PropScatter
    from ..dressing.lining import longest_bare_run

    faces = list(getattr(bp, "lined_faces", ()))
    if not faces:
        return []
    meshes = meshes if meshes is not None else _meshes()
    size = {m: (float(pos[:, 2].max() - pos[:, 2].min()),
                float(max(np.abs(pos[:, 0]).max(), np.abs(pos[:, 1]).max())))
            for m, (pos, _) in meshes.items()}
    rows = [(p.origin.x, p.origin.y, p.origin.z, size[p.model][0] * p.scale, size[p.model][1] * p.scale)
            for s in bp.elements(PropScatter) for p in s.props if p.model in size]
    if not rows:
        rows = [(0.0, 0.0, -1e9, 0.0, 0.0)]
    xs, ys, zs, hs, ws = (np.array(c, float) for c in zip(*rows))
    recorded = list(getattr(bp, "lined_openings", ()))
    holes = _openings_of(bp)
    out = []
    for horizontal, face, (s0, s1), sign, floor, top, *rest in faces:
        depth = rest[0] if rest else _DEPTH
        off, along = (ys, xs) if horizontal else (xs, ys)
        d = (off - face) * sign
        mask = ((d >= -_BEHIND) & (d <= depth + 4.0) & (along >= s0 - _REACH) & (along <= s1 + _REACH)
                & (zs >= floor - 40.0) & (zs <= top) & (hs >= 0.5 * (top - floor)))
        cover = [(a - COVER * w, a + COVER * w) for a, w in zip(along[mask].tolist(), ws[mask].tolist())]
        mine = [(a0, a1) for h, f, sg, a0, a1, *_ in recorded
                if h == horizontal and abs(f - face) < 0.5 and sg == sign and a1 > s0 and a0 < s1]
        for x0, x1, y0, y1, z0, z1 in holes:
            n0, n1, t0, t1 = (y0, y1, x0, x1) if horizontal else (x0, x1, y0, y1)
            e0, e1 = sorted(((n0 - face) * sign, (n1 - face) * sign))
            if e1 >= -_BEHIND and e0 <= depth and z1 >= floor and z0 <= top and t1 > s0 and t0 < s1:
                mine.append((t0 - OPENING_EDGE, t1 + OPENING_EDGE))
        run, r0, r1 = longest_bare_run(cover, (s0, s1), mine)
        out.append((f"{'y' if horizontal else 'x'}={face:g} {s0:g}..{s1:g}", run, r0, r1))
    return out


def buys_on_lined_faces(bp) -> list[tuple[str, float, float]]:
    """``(buy id, x, y)`` of every wall buy hung on one of ``bp.lined_faces``
    (:func:`zmforge.dressing.lining.lined_face_at`)."""
    from ..blueprint.elements import WallWeapon
    from ..dressing.lining import lined_face_at

    faces = list(getattr(bp, "lined_faces", ()) or ())
    if not faces:
        return []
    return [(w.id, w.position.x, w.position.y) for w in bp.elements(WallWeapon)
            if lined_face_at(w.position, w.facing, faces) is not None]


def check_lining(bp) -> Report:
    report = Report()
    for ident, x, y in buys_on_lined_faces(bp):
        report.add(error(
            BUY_CODE,
            f"wall buy {ident} at ({x:.0f}, {y:.0f}) hangs on a wall lined with plants: its chalk and "
            "walk-up clear the plants in front of it and that strip reads as bare wall; "
            "place it with placement.wallbuy.place_wall_buy, which picks the nearest "
            "unlined wall in its zone (a building's, a fence, a shed's)",
            ident,
        ))
    meshes = _meshes() if getattr(bp, "lined_faces", ()) else None
    bare = lined_face_bare(bp, meshes=meshes) if meshes is not None else []
    long_runs = sorted((b for b in bare if b[1] > MAX_BARE), key=lambda b: -b[1])
    if long_runs:
        report.add(error(
            CODE,
            f"{len(long_runs)} lined wall face(s) have a stretch longer than {MAX_BARE:g} units with no "
            "plant in front of the wall (longest "
            + ", ".join(f"{label}: {run:.0f} at {r0:.0f}..{r1:.0f}" for label, run, r0, r1 in long_runs[:3])
            + "): a bare patch of wall between the plants (corn stalks "
            "missing in places); keep the back rows behind low props, taper at "
            "openings, or record a real opening in bp.lined_openings",
        ))
    cover = lined_face_cover(bp, meshes=meshes) if meshes is not None else []
    if not cover:
        return report
    total = sum(n for _, n, _ in cover)
    mean = sum(n * h for _, n, h in cover) / total
    if mean < MIN_HIDDEN:
        worst = sorted(cover, key=lambda c: c[2])[:3]
        report.add(error(
            CODE,
            f"the plants lining the walls hide {mean:.0%} of the wall face head-on "
            f"(floor {MIN_HIDDEN:.0%}, {len(cover)} faces drawn; thinnest "
            + ", ".join(f"{label} {h:.0%}" for label, _, h in worst)
            + "): the wall reads as bare wall with plants in front (zm_corn_maze "
            "read as thin); line it with more rows, "
            "closer, taller or leafier plants",
        ))
    return report
