"""Z84: no drawn world box shows the player an undrawn (caulk) face.

A raised floor with an undrawn back face makes what stands on it look as if
it floats, seen from behind.  Take a box with a drawn top and three drawn
sides whose fourth side is left at the ``FaceMaterials`` default, caulk.
Caulk draws nothing, so a player walking behind it looks straight through
that side at the floor beyond, and props standing on a top nobody can see
hang in the air.

Z44's support rule (:mod:`zmforge.placement.audit`) does not catch it.  It
asks whether a prop stands on a surface, and those props do: the box's top
is a walkable block top at their feet.  Support is a *collision* question;
this is a *drawing* one, and no check looked at which faces of a box get
drawn.

The rule: for every axis-aligned world box that draws at least one face (a
box that draws none is a tool brush -- clip, trigger, an invisible seal -- and
is meant to be unseen), each undrawn face is sampled on a 16-unit grid one
unit outside it.  A sample is *open* when it is in a room's or yard's air
(inside its interior, over its floor) and inside no other box and no
placed prop's measured box.  A face with
open samples is a hole in the world the player can look through: an error.
A face flush with a wall, the floor, the ceiling or a neighbouring box has no
open samples, which is why caulk on hidden faces stays free.

Fix it where the box is authored: give the exposed side a real material
(``FaceMaterials(per_side=...)``) or ``FaceMaterials.uniform``.
"""

from __future__ import annotations

from .report import Report, error

__all__ = ["CODE", "PITCH", "open_undrawn_faces", "check_exposed_faces"]

CODE = "Z84"

#: Sample spacing on a face, and the inset from its edges.
PITCH = 16.0
INSET = 2.0
#: How far outside the face a sample is taken.
OUT = 1.0
#: A face narrower than this either way is an edge, not a window: a wall
#: poster panel is a 2-unit-thick box drawn on its front only, and its caulk
#: edges are slivers nobody looks through (202 of them on a test map
#: before this floor).
MIN_FACE = 8.0
#: An underside lower than this over the floor is below a crouching
#: player's eye, so nobody looks up at it: a small fitting 11 up, with its
#: caulk bottom over the plinth it sits on, is not a window.
LOW_UNDERSIDE = 40.0

_SIDES = ("west", "east", "south", "north", "bottom", "top")


def _box(solid):
    """``(mins, maxs, faces)`` for an axis-aligned box, where ``faces`` maps
    ``(axis, sign)`` (outward) to the face's material name; ``None`` if the
    solid is not an axis-aligned box."""
    if len(solid.faces) != 6:
        return None
    faces = {}
    for face in solid.faces:
        n = (face.inward.x, face.inward.y, face.inward.z)
        axes = [i for i, c in enumerate(n) if abs(c) > 1e-6]
        if len(axes) != 1:
            return None
        axis = axes[0]
        faces[(axis, -1 if n[axis] > 0 else 1)] = face.material.name
    if len(faces) != 6:
        return None
    pts = [(p.x, p.y, p.z) for face in solid.faces for p in face.points]
    mins = tuple(min(p[i] for p in pts) for i in range(3))
    maxs = tuple(max(p[i] for p in pts) for i in range(3))
    return mins, maxs, faces


def _aabb(solid):
    pts = [(p.x, p.y, p.z) for face in solid.faces for p in face.points]
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))


def _steps(lo: float, hi: float) -> list[float]:
    a, b = lo + INSET, hi - INSET
    if b <= a:
        return [(lo + hi) / 2.0]
    n = max(1, int((b - a) // PITCH))
    return [a + (b - a) * k / n for k in range(n + 1)]


class _Index:
    """Boxes bucketed on a 256-unit xy grid for the point-inside test."""

    CELL = 256.0

    def __init__(self, boxes):
        self.cells: dict[tuple[int, int], list] = {}
        for box in boxes:
            (x0, y0, _), (x1, y1, _) = box
            for i in range(int(x0 // self.CELL), int(x1 // self.CELL) + 1):
                for j in range(int(y0 // self.CELL), int(y1 // self.CELL) + 1):
                    self.cells.setdefault((i, j), []).append(box)

    def holds(self, p) -> bool:
        key = (int(p[0] // self.CELL), int(p[1] // self.CELL))
        for (lo, hi) in self.cells.get(key, ()):
            if all(lo[i] - 0.01 <= p[i] <= hi[i] + 0.01 for i in range(3)):
                return True
        return False


def _prop_boxes(blueprint):
    """The measured box of every placed prop: a name plate is a box drawn on
    its front and edges only, its caulk back set against a desk or a sign
    board, and the prop hides that back as well as a wall would."""
    from ..blueprint.elements import PropScatter
    from ..placement.relations import Placed
    from ..props.origins import drawn_box
    from ..recipes.props import collision_box

    out = []
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            measured = drawn_box(prop.model, collision_box(prop.model))
            if measured is None:
                continue
            placed = Placed.from_model(
                prop.model, measured, (prop.origin.x, prop.origin.y, prop.origin.z),
                prop.yaw, prop.scale, solid=prop.solid, ident=prop.id)
            xs = [x for x, _y in placed.footprint.points]
            ys = [y for _x, y in placed.footprint.points]
            out.append(((min(xs), min(ys), placed.z_low), (max(xs), max(ys), placed.z_high)))
    return out


def _air(blueprint):
    """``(mins, maxs, floor_z)`` of every room and yard interior."""
    from ..blueprint.elements import Room, Yard

    out = []
    for kind in (Room, Yard):
        for element in blueprint.elements(kind):
            try:
                box, floor = element.interior, element.floor_z
            except (AttributeError, TypeError):
                continue
            if box is None:
                continue
            out.append(((box.mins.x, box.mins.y, box.mins.z),
                        (box.maxs.x, box.maxs.y, box.maxs.z), floor))
    return out


def open_undrawn_faces(blueprint):
    """``[(massing_id, side, open_samples, total_samples, (x, y, z))]`` for
    each undrawn box face the player can see, ``(x, y, z)`` one open sample."""
    from ..blueprint.elements import SEALED_OPENING, Massing
    from .umbra_air import _drawn

    massings = list(blueprint.elements(Massing))
    solids = [(m, s) for m in massings for s in m.solids]
    index = _Index([_aabb(s) for _m, s in solids] + _prop_boxes(blueprint))
    air = _air(blueprint)

    def floor_under(p):
        """The floor of the room or yard whose air ``p`` is in, else None."""
        for lo, hi, floor in air:
            if all(lo[i] <= p[i] <= hi[i] for i in range(3)) and p[2] > floor:
                return floor
        return None

    found = []
    for massing, solid in solids:
        if massing.note == SEALED_OPENING:
            continue
        box = _box(solid)
        if box is None:
            continue
        mins, maxs, faces = box
        if not any(_drawn(name) for name in faces.values()):
            continue
        for (axis, sign), name in faces.items():
            if _drawn(name):
                continue
            u, v = (i for i in range(3) if i != axis)
            if min(maxs[u] - mins[u], maxs[v] - mins[v]) < MIN_FACE:
                continue
            plane = (maxs if sign > 0 else mins)[axis] + sign * OUT
            total, hits, where = 0, 0, None
            for a in _steps(mins[u], maxs[u]):
                for b in _steps(mins[v], maxs[v]):
                    p = [0.0, 0.0, 0.0]
                    p[axis], p[u], p[v] = plane, a, b
                    total += 1
                    floor = floor_under(p)
                    if floor is None or index.holds(p):
                        continue
                    if axis == 2 and sign < 0 and p[2] < floor + LOW_UNDERSIDE:
                        continue
                    hits += 1
                    where = where or tuple(p)
            if hits:
                found.append((massing.id, _SIDES[axis * 2 + (sign > 0)], hits, total, where))
    return found


def check_exposed_faces(blueprint) -> Report:
    """Z84: an error per undrawn face of a drawn box that the player can see."""
    report = Report()
    for mid, side, hits, total, (x, y, z) in open_undrawn_faces(blueprint):
        report.add(error(
            CODE,
            f"{mid}: its {side} face is undrawn (caulk) but {hits} of {total} "
            f"points just outside it are open room air, so the player looks "
            f"through the box there and whatever stands on it floats; give "
            f"that side a real material",
            mid, f"({x:.0f}, {y:.0f}, {z:.0f})"))
    return report
