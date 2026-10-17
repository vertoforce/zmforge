"""Z54: no solid prop's measured footprint reaches past its room's inner wall face.

Measured on zm_dmv: the records room's six lab cabinets, its four
shelves, the two cabinets behind the service counter and the back office's two
cabinets were all placed turned with their long side into the wall, so each
one ran 24 to 37 units past the inner wall face -- into the wall slab, or
through it.  No check asked: Z44 compares props with props, Z53 only looks at
doorways, and the placer takes an origin at its word.  A prop reaching into a
wall is a model drawn through the brush (and, if the wall is thin enough, out
the far side into the next room or the void), and it is almost always the
sign of a prop turned the wrong way.

The rule: a solid prop whose footprint centre stands in a room, on that room's
floor, keeps every corner of its turned footprint inside the room's interior
to within :data:`TOLERANCE`.  Hollow props are not asked (a sheet of paper
under a skirting board is not a defect), and neither are wall and ceiling
fixtures, which are *meant* to sit on the wall plane.  A model deliberately
built into a wall goes in :data:`THROUGH_WALL` with the reason, so the
exemption is written down rather than silent.

Hollow props standing on something (a shelf, a desk, a dresser top) get a
**warning** past :data:`HOLLOW_TOLERANCE`: on zm_corn_maze, shelf items put
at the shelf's middle stood 5-11 units into the barn walls, and a box on a
dresser 3 units into the farmhouse wall, which a render showed poking out.  Floor litter is not asked.  Placers keep surface
items inside their surface with :func:`zmforge.dressing.fit_within`.
"""

from __future__ import annotations

from .report import Report, error, warning

__all__ = ["TOLERANCE", "HOLLOW_TOLERANCE", "THROUGH_WALL", "check_props_inside_walls"]

#: How far past the inner wall face a corner may reach: rounding, not design.
TOLERANCE = 1.0

#: ``model -> reason`` for solid floor models that are placed through a wall
#: on purpose.  Empty: nothing in any recipe needs it.
THROUGH_WALL: dict[str, str] = {}

#: How far above a room's floor a prop's underside may start and still be
#: judged against that room's walls (a prop on a desk or a counter is still
#: in the room; one hung high on a gantry belongs to whatever holds it).
FLOOR_BAND = 64.0

#: How far a hollow prop resting on a surface may reach past the inner wall
#: face before it is a warning: a model's measured box carries a unit or two
#: of rounding, and 3 is under anything the renders showed.
HOLLOW_TOLERANCE = 3.0

#: A hollow prop whose underside is at least this far over its room's floor
#: is resting on something (surface clutter), not lying on the floor.
ON_SURFACE = 4.0

#: The top of the band a hollow prop is judged in: the highest shelf board
#: a recipe dresses (a tall shelf's top board is about 150 up).
SHELF_BAND = 160.0


def check_props_inside_walls(blueprint) -> Report:
    """Z54: an error per solid prop that reaches past its room's walls, and
    a warning per hollow prop resting on a surface that does."""
    from ..blueprint.elements import PropScatter, Room
    from ..placement.relations import Placed
    from ..props.origins import drawn_box
    from ..recipes.props import MOUNT_FLOOR, collision_box, mount_kind

    report = Report()
    rooms = list(blueprint.elements(Room))
    if not rooms:
        return report
    for scatter in blueprint.elements(PropScatter):
        for prop in scatter.props:
            if prop.model in THROUGH_WALL:
                continue
            if mount_kind(prop.model) != MOUNT_FLOOR:
                continue
            measured = drawn_box(prop.model, collision_box(prop.model))
            if measured is None:
                continue
            placed = Placed.from_model(
                prop.model, measured, (prop.origin.x, prop.origin.y, prop.origin.z),
                prop.yaw, prop.scale, solid=prop.solid, ident=prop.id,
            )
            home = None
            for room in rooms:
                box = room.interior
                if not (box.mins.x <= placed.x <= box.maxs.x
                        and box.mins.y <= placed.y <= box.maxs.y):
                    continue
                band = FLOOR_BAND if prop.solid else SHELF_BAND
                if not (room.floor_z - TOLERANCE <= placed.z_low
                        <= room.floor_z + band):
                    continue
                home = room
                break
            if home is None:
                continue
            box = home.interior
            reach = max(
                max(box.mins.x - x, x - box.maxs.x, box.mins.y - y, y - box.maxs.y)
                for x, y in placed.footprint.points
            )
            if not prop.solid:
                if placed.z_low >= home.floor_z + ON_SURFACE and reach > HOLLOW_TOLERANCE:
                    report.add(
                        warning(
                            "Z54",
                            f"{prop.model} ({prop.id or scatter.id}) at "
                            f"{prop.origin.x:g} {prop.origin.y:g} {prop.origin.z:g} reaches "
                            f"{reach:.1f} units past the inner wall of {home.id} from the "
                            "surface it stands on; keep it on its surface "
                            "(zmforge.dressing.fit_within)",
                        )
                    )
                continue
            if reach > TOLERANCE:
                report.add(
                    error(
                        "Z54",
                        f"{prop.model} ({prop.id or scatter.id}) at "
                        f"{prop.origin.x:g} {prop.origin.y:g} reaches {reach:.1f} "
                        f"units past the inner wall of {home.id}; turn it to run "
                        "along the wall or move it off",
                    )
                )
    return report
