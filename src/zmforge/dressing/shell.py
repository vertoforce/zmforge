"""Room shells: surface materials and holes cut in world coordinates.

Units are map units (inches).  These wrap :class:`RoomMaterials` and
:meth:`Blueprint.cut_opening` so a recipe says where a doorway is in the
world and the offset and sill each room's wall wants are derived for it.
"""

from __future__ import annotations

from ..blueprint.elements import RoomMaterials
from ..materials import Material
from ..solids.layout import Aperture
from ..spatial import Axis, Side

__all__ = ["room_skin", "wall_midpoint", "cut_hole", "link_rooms"]


def room_skin(wall: Material, floor: Material, ceiling: Material,
              **sides: Material) -> RoomMaterials:
    """A room's three surface families, with optional per-wall accents
    (``north=``, ``south=``, ``east=``, ``west=``).  One wall of a room is
    usually the wall the room is *about* (the bay wall, the chart wall, the
    wall of shelves), and a room whose four walls are one material has
    nothing to look at."""
    return RoomMaterials(wall=wall, floor=floor, ceiling=ceiling,
                         sides={Side[key.upper()]: value for key, value in sides.items()})


def wall_midpoint(room, side: Side) -> float:
    """The centre of the run *room*'s *side* wall covers, along the wall:
    what an :class:`Aperture` offset is measured from."""
    piece = room.shell.of_side(side)[0].box
    along = Axis.Y if side.axis is Axis.X else Axis.X
    return (piece.mins[along.index] + piece.maxs[along.index]) / 2.0


def cut_hole(bp, room, side: Side, *, centre: float, width: float, height: float,
             bottom_z: float):
    """Cut one hole *width* wide and *height* tall in *room*'s *side* wall,
    centred at world coordinate *centre* along the wall, its bottom at world
    height *bottom_z*.  Returns the :class:`Opening`.

    Sills are measured from each room's own floor, and a hole joining two
    rooms whose floors differ needs the same *world* height on both sides:
    taking ``bottom_z`` is the difference between a doorway and a step into
    a wall."""
    return bp.cut_opening(room, Aperture(
        side=side, width=width, height=height, sill=bottom_z - room.floor_z,
        offset=centre - wall_midpoint(room, side)))


def link_rooms(bp, near, near_side: Side, far, far_side: Side, *, centre: float,
               width: float, height: float, bottom_z: float):
    """Aligned holes through two walls that touch, one from each room (a
    doorway between *near* and *far*).  Returns both openings."""
    return (
        cut_hole(bp, near, near_side, centre=centre, width=width, height=height,
                 bottom_z=bottom_z),
        cut_hole(bp, far, far_side, centre=centre, width=width, height=height,
                 bottom_z=bottom_z),
    )
