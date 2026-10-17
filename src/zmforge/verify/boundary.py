"""Z62-Z63: boundary walls of open-air rooms.

``Z62`` an open room's wall with a long bare run: over :data:`BARE_RUN`
        units along its inner face with nothing standing against it (no
        brush, prop or opening within :data:`FACE_BAND` of the face).  The
        zm_cemetery hero shot: 2,000 units of flat brick.
``Z63`` an open room whose walls hide the sky (taller than
        :data:`SKY_WALL` over the floor), or whose low walls show nothing
        over them on any side facing open air (no brush or model standing
        beyond the wall and rising above its top).

``Z65`` a roofed room's outer wall that rises over a neighbouring open
        room's low wall (so players see it over the wall) with nothing
        standing proud of it: a blank slab (zm_cemetery's shed,
        chapel and vault were such slabs).

All are warnings.  Helpers: :func:`zmforge.dressing.boundary_wall`,
:func:`zmforge.dressing.backdrop`, :func:`zmforge.dressing.facade`,
``add_room(wall_height=...)``.
"""

from __future__ import annotations

from .report import Report, warning

#: A wall shorter than this along its face is not judged.
LONG_WALL = 600.0
#: The longest bare run of wall face allowed.
BARE_RUN = 320.0
#: How close to the inner face a thing must stand to dress it.
FACE_BAND = 40.0
#: An open room's wall this tall over its floor hides the sky from the ground.
SKY_WALL = 320.0


def _boxes(blueprint):
    from ..blueprint.elements import Massing, PropScatter, Terrain

    out = []
    for m in blueprint.elements(Massing):
        if m.id.endswith(("_clip_north", "_clip_south", "_clip_east", "_clip_west")):
            continue
        for solid in m.solids:
            b = _solid_box(solid)
            if b is not None:
                out.append(b)
    for scatter in blueprint.elements(PropScatter):
        for placed in scatter.props:
            b = _prop_box(placed)
            if b is not None:
                out.append(b)
    del Terrain
    return out


def _solid_box(solid):
    try:
        from ..blueprint.model import _solid_bounds

        s = _solid_bounds(solid)
        return (s.mins.x, s.mins.y, s.mins.z, s.maxs.x, s.maxs.y, s.maxs.z)
    except Exception:
        return None


def _prop_box(placed):
    """A placed model's plan box and height; a model with no measured box
    counts as a small post at its origin."""
    from ..dressing.place import _facts, turned_box

    o = placed.origin
    try:
        x0, y0, x1, y1 = turned_box(placed.model, placed.yaw)
        (_a, _b, z0), (_c, _d, z1) = _facts().collision_box(placed.model)
        k = placed.scale
        return (o.x + x0 * k, o.y + y0 * k, o.z + z0 * k, o.x + x1 * k, o.y + y1 * k, o.z + z1 * k)
    except Exception:
        return (o.x - 4, o.y - 4, o.z, o.x + 4, o.y + 4, o.z + 8)


def _open_rooms(blueprint):
    from ..blueprint.elements import Room

    return [r for r in blueprint.elements(Room) if not r.roofed]


def check_boundary_walls(blueprint) -> Report:
    """Z62 and Z63 over every open-air room."""
    from ..dressing.boundary import _outside_spans, open_spans, wall_faces

    report = Report()
    rooms = _open_rooms(blueprint)
    if not rooms:
        return report
    boxes = _boxes(blueprint)
    for room in rooms:
        faces = wall_faces(room)
        floor = room.floor_z
        shown = False
        tall = max(f.top for f in faces.values()) - floor
        if tall > SKY_WALL:
            report.add(warning(
                "Z63",
                f"{room.id} is open to the sky but its walls stand {tall:.0f} over the floor; "
                "from the ground they hide the sky and anything beyond -- build it with "
                "add_room(wall_height=...) and stand a backdrop over the wall "
                "(zmforge.dressing.backdrop)"))
        for side, face in faces.items():
            length = face.a1 - face.a0
            covered = []
            for box in room.aperture_boxes:
                lo, hi = (box.mins.x, box.maxs.x) if face.along_x else (box.mins.y, box.maxs.y)
                c0, c1 = (box.mins.y, box.maxs.y) if face.along_x else (box.mins.x, box.maxs.x)
                if c0 - 1 <= face.face <= c1 + 1:
                    covered.append((lo, hi))
            for x0, y0, z0, x1, y1, z1 in boxes:
                lo, hi = (x0, x1) if face.along_x else (y0, y1)
                c0, c1 = (y0, y1) if face.along_x else (x0, x1)
                if hi < face.a0 or lo > face.a1 or z1 < floor - 32.0:
                    continue
                # Standing against the inner face (inside the band), or on the
                # wall itself (a pier, a coping, a railing).
                if face.inward > 0:
                    near = c1 >= face.back - 1 and c0 <= face.face + FACE_BAND
                else:
                    near = c0 <= face.back + 1 and c1 >= face.face - FACE_BAND
                if near and not (c0 <= min(face.face, face.back) - 1 and c1 >= max(face.face, face.back) + 1
                                 and (hi - lo) >= length - 1):
                    covered.append((lo, hi))
                # A silhouette: beyond the back of the wall, rising over it.
                beyond = (c1 < face.back if face.inward > 0 else c0 > face.back)
                if beyond and z1 > face.top + 32.0:
                    shown = True
            if length >= LONG_WALL:
                gaps = open_spans(face.a0, face.a1, covered, least=BARE_RUN)
                if gaps:
                    g0, g1 = max(gaps, key=lambda g: g[1] - g[0])
                    report.add(warning(
                        "Z62",
                        f"{room.id} {side.name.lower()} wall has a bare run of {g1 - g0:.0f} units "
                        f"({g0:.0f} to {g1:.0f} along it) with nothing against it; dress it with "
                        "piers, a coping, a plinth and props at its foot "
                        "(zmforge.dressing.boundary_wall)"))
        if tall <= SKY_WALL and not shown:
            if any(_outside_spans(blueprint, room, f) for f in faces.values()):
                report.add(warning(
                    "Z63",
                    f"{room.id} is open to the sky but nothing stands beyond its walls and over "
                    "them: stand a tree line, a spire or rooftops there (zmforge.dressing.backdrop)"))
    return report


#: How far out from a roofed room's outer face a brush may stand and still
#: dress it, and how much of the exposed height must show before it counts.
FACADE_BAND = 30.0
FACADE_LEAST = 96.0


def check_facades(blueprint) -> Report:
    """Z65 over every roofed room seen over an open room's low wall."""
    from ..blueprint.elements import Room
    from ..dressing.facade import exposed_faces

    report = Report()
    rooms = blueprint.elements(Room)
    if not any(not r.roofed for r in rooms):
        return report
    boxes = None
    for room in rooms:
        if not room.roofed:
            continue
        for ex in exposed_faces(blueprint, room, least=FACADE_LEAST):
            if ex.seen_from is None:
                continue  # stands free or over a roof: nobody looks over a wall at it
            if boxes is None:
                boxes = _boxes(blueprint)
            f = ex.face
            out = -f.inward
            lo_c, hi_c = sorted((f.back, f.back + out * FACADE_BAND))
            dressed = False
            for x0, y0, z0, x1, y1, z1 in boxes:
                if z1 <= ex.base + 8.0 or z0 >= f.top:
                    continue
                c0, c1, a0, a1 = (y0, y1, x0, x1) if f.along_x else (x0, x1, y0, y1)
                proud = c1 > f.back + 0.5 if out > 0 else c0 < f.back - 0.5
                near = c0 < hi_c and c1 > lo_c and proud
                along = a0 < f.a1 and a1 > f.a0
                if near and along:
                    dressed = True
                    break
            if not dressed:
                report.add(warning(
                    "Z65",
                    f"{room.id} {ex.side.name.lower()} outer wall rises {f.top - ex.base:.0f} units "
                    "over its neighbour's low wall with nothing standing proud of it: a blank slab "
                    "seen from the open room (zmforge.dressing.facade)", room.id))
    return report
