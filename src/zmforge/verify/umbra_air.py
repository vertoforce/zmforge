"""Z83: players never stand in more than one sealed pocket of air.

BO3's occlusion pass (Umbra, run by the linker as ``UmbraConvert``) splits the
map's empty space into clusters and filters the "inside" ones.  Every link log
measured keeps exactly the open air plus one sealed pocket, however many
sealed pockets the map has: ``Filtered 0/2 inside clusters`` for
zm_forge_gate (two pockets), ``4444/4445`` for zm_cemetery (open to the sky,
one pocket).  A player in a dropped pocket sees the floor and walls flicker
away to the sky at spawn.  Which pocket Umbra keeps is not
known, so the rule is the one the logs support: at most one sealed pocket
holds player spawns; any other must be open to the air inside the sky shell
(``Blueprint.add_yard_vent``).

The test voxelises the drawn faces of the written map at 8 units (Umbra sees
only drawn triangles: caulk, clip, sky and tool faces are not in its scene,
``UmbraDebug/<map>_cod2map.txt``) and floods the empty space.
"""

from __future__ import annotations

from ..mapsource.document import BrushSolid, Document
from .report import Report, error

__all__ = ["CODE", "RESOLUTION", "air_pockets", "check_umbra_air"]

CODE = "Z83"
RESOLUTION = 8.0

#: Materials Umbra never sees (not drawn, or the sky shell itself).
_UNDRAWN = ("caulk", "clip", "trigger", "sky", "umbra_volume", "sun_volume",
            "litfog_volume", "nodraw", "portal", "hint", "mantle", "ai_nosight",
            "physics", "shadowcaster", "volume", "reflection_probe", "decal")

_SEED_NAMES = ("initial_spawn_points", "player_respawn_point")


def _drawn(material: str) -> bool:
    return not material.lower().startswith(_UNDRAWN)


def _box_faces(solid: BrushSolid):
    """((mins, maxs), [(axis, high_side, drawn)]) for an axis-aligned box, else
    ((mins, maxs), None) from the facet points' extent."""
    pts = [tuple(float(c) for c in (p.x, p.y, p.z)) for f in solid.facets for p in f.points]
    faces = []
    planes: dict[tuple[int, bool], float] = {}
    for facet in solid.facets:
        a, b, c = (tuple(float(v) for v in (p.x, p.y, p.z)) for p in facet.points)
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        big = [i for i in range(3) if abs(n[i]) > 1e-9]
        if len(big) != 1:
            faces = None
            break
        axis = big[0]
        high = n[axis] < 0  # the normal points into the solid
        planes[(axis, high)] = a[axis]
        faces.append((axis, high, _drawn(facet.material)))
    if faces is not None and len(planes) == 6:
        mins = tuple(planes[(i, False)] for i in range(3))
        maxs = tuple(planes[(i, True)] for i in range(3))
        return (mins, maxs), faces
    mins = tuple(min(p[i] for p in pts) for i in range(3))
    maxs = tuple(max(p[i] for p in pts) for i in range(3))
    return (mins, maxs), None


def air_pockets(document: Document, resolution: float = RESOLUTION):
    """(labels, open_labels, to_index) for the written map's empty space.

    ``open_labels`` are the pockets touching the grid's edge, i.e. the open
    air between the rooms and the sky shell.
    """
    import numpy as np
    from scipy import ndimage

    world = document.worldspawn
    boxes = []
    for solid in (world.solids if world is not None else ()):
        if not isinstance(solid, BrushSolid) or not solid.facets:
            continue
        if not any(_drawn(f.material) for f in solid.facets):
            continue
        boxes.append(_box_faces(solid))
    if not boxes:
        return None
    lo = np.array([min(b[0][0][i] for b in boxes) for i in range(3)]) - 2 * resolution
    hi = np.array([max(b[0][1][i] for b in boxes) for i in range(3)]) + 2 * resolution
    shape = np.ceil((hi - lo) / resolution).astype(int)
    solid = np.zeros(shape, bool)

    def cell(value, axis, up):
        v = (value - lo[axis]) / resolution
        i = int(np.ceil(v - 1e-6)) if up else int(np.floor(v + 1e-6))
        return max(0, min(int(shape[axis]), i))

    for (mins, maxs), faces in boxes:
        a = [cell(mins[i], i, False) for i in range(3)]
        c = [cell(maxs[i], i, True) for i in range(3)]
        if faces is None:
            solid[a[0]:c[0], a[1]:c[1], a[2]:c[2]] = True
            continue
        for axis, high, drawn in faces:
            if not drawn:
                continue
            s0, s1 = list(a), list(c)
            k = min(int(shape[axis]) - 1,
                    int(np.floor(((maxs if high else mins)[axis] - lo[axis]) / resolution)))
            s0[axis], s1[axis] = k, k + 1
            solid[s0[0]:s1[0], s0[1]:s1[1], s0[2]:s1[2]] = True
    labels, _ = ndimage.label(~solid)
    edge = np.concatenate([labels[0].ravel(), labels[-1].ravel(), labels[:, 0].ravel(),
                           labels[:, -1].ravel(), labels[:, :, 0].ravel(),
                           labels[:, :, -1].ravel()])
    open_labels = set(int(v) for v in np.unique(edge)) - {0}

    def to_index(point):
        return tuple(max(0, min(int(shape[i]) - 1, int((point[i] - lo[i]) // resolution)))
                     for i in range(3))

    return labels, open_labels, to_index


def check_umbra_air(document: Document, report: Report) -> None:
    seeds = []
    for entity in document.entities_of("script_struct"):
        if entity.value("targetname") not in _SEED_NAMES:
            continue
        raw = entity.value("origin")
        if not raw:
            continue
        x, y, z = (float(t) for t in raw.split()[:3])
        seeds.append((entity.value("targetname"), (x, y, z + 40.0)))
    if not seeds:
        return
    try:
        found = air_pockets(document)
    except ImportError as exc:  # pragma: no cover - the textures extra
        report.add(error(CODE, f"cannot flood the map's air ({exc}); install scipy"))
        return
    if found is None:
        return
    labels, open_labels, to_index = found
    sealed: dict[int, list] = {}
    for name, point in seeds:
        label = int(labels[to_index(point)])
        if label and label not in open_labels:
            sealed.setdefault(label, []).append((name, point))
    if len(sealed) > 1:
        where = "; ".join(
            f"{len(v)} spawn(s) near ({v[0][1][0]:.0f}, {v[0][1][1]:.0f})"
            for v in sealed.values())
        report.add(error(
            CODE,
            f"players spawn in {len(sealed)} separate sealed pockets of air ({where}); "
            "BO3's occlusion pass keeps one sealed pocket and drops the rest, and "
            "a player in a dropped one sees floors and walls flicker to the sky. "
            "Open all but one to the air inside the sky shell "
            "(Blueprint.add_yard_vent)",
        ))
