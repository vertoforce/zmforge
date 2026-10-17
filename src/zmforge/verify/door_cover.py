"""Z81: a closed door fills its opening, and the opening is a way through.

Measured on zm_corn_maze: the patch gate out of the spawn yard is
256 wide by 176 tall, and the stock one-piece leaf hung in it at modelscale 1
is 120 by 102 (``catalogue.DOOR_LEAF_SIZE``).  The door's collision is
invisible clip, so the closed door showed a small door in the middle of a big
hole, 68 units open at each jamb and 74 over the top (it read as too small for
its opening).  :attr:`Door.leaves` now scales and tiles the leaf
to the opening; this holds that for every recipe.

For every door:

* the leaves, closed, cover the opening across its width and up its height
  (error): a gap is a hole into the next zone you can see and shoot through;
* a framed door's leaves are no taller than the opening (warning): the spare
  goes into the wall at the jambs, but over the head of an unroofed wall it
  shows (a free-standing stair gate grows upwards on purpose);
* the opening is at least the player's hull wide (30) and tall (72), the
  stock values in :mod:`zmforge.verify.model` (error): a door nobody fits
  through is not a door.  ``W2`` covers room doorways' width; this covers
  every door box, stair gates included, and the height.
"""

from __future__ import annotations

from .report import Report, error, warning

__all__ = ["CODE", "check_door_cover"]

CODE = "Z81"

#: Rounding slack, in world units: the modelscale is written to 4 places.
TOLERANCE = 0.5


def check_door_cover(bp) -> Report:
    """``Z81`` over a blueprint."""
    from ..blueprint.catalogue import DOOR_LEAF_SIZE
    from ..spatial import Axis
    from .model import PLAYER_HULL_HEIGHT, PLAYER_HULL_WIDTH
    from ..blueprint.elements import Door

    report = Report()
    for door in bp.elements(Door):
        box = door.box
        axis = door.across_axis
        width, height = box.extent(axis), box.extent(Axis.Z)
        if width < PLAYER_HULL_WIDTH or height < PLAYER_HULL_HEIGHT:
            report.add(error(
                CODE,
                f"door {door.id}'s opening is {width:g} wide by {height:g} tall, under the "
                f"player's {PLAYER_HULL_WIDTH:g} x {PLAYER_HULL_HEIGHT:g} hull: nobody walks "
                "through it once it is bought", door.id))
        if not door.model:
            report.add(error(
                CODE,
                f"door {door.id} has no leaf model: closed, it is an invisible clip wall "
                "across an open hole", door.id))
            continue
        if door.model not in DOOR_LEAF_SIZE:
            report.add(error(
                CODE,
                f"door {door.id}'s leaf {door.model!r} has no measured face in "
                "catalogue.DOOR_LEAF_SIZE, so it cannot be sized to its opening", door.id))
            continue
        lo, hi, bottom, top = door.leaf_cover()
        gaps = {
            "at one jamb": lo - box.mins[axis.index],
            "at the other jamb": box.maxs[axis.index] - hi,
            "under the leaf": bottom - box.mins.z,
            "over the leaf": box.maxs.z - top,
        }
        open_ = {where: gap for where, gap in gaps.items() if gap > TOLERANCE}
        if open_:
            spelled = ", ".join(f"{gap:g} {where}" for where, gap in open_.items())
            report.add(error(
                CODE,
                f"door {door.id} closed leaves its {width:g} x {height:g} opening open "
                f"({spelled}): a hole behind invisible clip", door.id))
        if door.framed and top - box.maxs.z > TOLERANCE:
            report.add(warning(
                CODE,
                f"door {door.id}'s leaf stands {top - box.maxs.z:g} above its opening, "
                "which shows over an unroofed wall", door.id))
    return report
