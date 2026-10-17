"""What every room module of the dense pass gets: one context and the
placement helpers of :mod:`zmforge.recipes.dmv`.

A room module is imported only from inside
:func:`zmforge.recipes.dmv.dmv_of_the_damned` (via :func:`furnish_dense`), by
which time :mod:`zmforge.recipes.dmv` is fully loaded, so importing its
helpers here is not circular.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ...blueprint.model import Blueprint
from ...spatial import Bounds, Facing, Point, Side  # noqa: F401  (re-exported)
from ... import dressing
from ...dressing import centred as _centred  # noqa: F401  (re-exported for the room modules)
from ...dressing import corner_heaps  # noqa: F401
from ...dressing import mounted as _mounted  # noqa: F401
from ...dressing import on_floor as _floor  # noqa: F401
from ...dressing import on_surface as _on  # noqa: F401
from ...dressing import rest_on as _rest_on  # noqa: F401
from ...dressing import seated as _seated  # noqa: F401
from ...dressing import top_of as _top_of  # noqa: F401
from ..dmv import (  # noqa: F401  (re-exported for the room modules)
    FIXTURE,
    DmvPlan,
    WAITING_SEAT_TOP,
    _belt_line,
    counter_run,
    queue_dead_end,
    queue_route,
    bay_centres,
)
from ..props import MODEL_BOX, SEAT_TOP, _mount_face, collision_box, shelf_boards  # noqa: F401


@dataclass
class RoomContext:
    """One room's share of the dense pass.

    *room* is the room element (``.interior`` bounds, ``.floor_z``,
    ``.aperture_boxes``); *rooms* holds all ten under the keys ``lot``,
    ``entry``, ``waiting``, ``windows``, ``eye``, ``photo``, ``break``,
    ``records``, ``queue``, ``office``, for reading a neighbour's geometry
    only.  ``walk_top``/``walk_x0`` are the lot footway's top and west edge.
    """

    bp: Blueprint
    plan: DmvPlan
    key: str
    room: object
    rooms: Mapping[str, object]
    walk_top: float
    walk_x0: float
    placed: int = field(default=0)

    def put(self, items: list[tuple], ident: str) -> None:
        """Place *items* (tuples from :func:`_on`, :func:`_floor`,
        :func:`_mounted`, :func:`_seated`, :func:`_centred`) as one scatter.
        *ident* must be unique map-wide; prefix it with ``dense_<key>_``."""
        if not items:
            return
        if not ident.startswith(f"dense_{self.key}_"):
            raise ValueError(f"{ident}: dense-pass ids start with dense_{self.key}_")
        self.bp.place_props(items, id=ident)
        self.placed += len(items)


# --------------------------------------------------------------------------
# Floor litter in heaps, not confetti
# --------------------------------------------------------------------------
# A lobby floor does not collect paper evenly.  It piles where something made
# people stop or drop things: round the bins (which overflowed), at the
# ticket machine (tickets and forms pulled and dropped), against the wall feet
# and in the corners (the door draft and the crowd pushed it there), and
# where somebody left their things.  Same piece count as the old even strew;
# only where the pieces lie changes.

import random as _cr

#: Overflow round a bin: cups, wrappers, food boxes.
BIN_SPILL = (
    "p7_debris_trash_cup_coffee_02", "p7_debris_trash_paper_03", "p7_debris_trash_cup_red_02",
    "p7_debris_trash_food_box_01", "p7_debris_trash_paper_09", "p7_debris_trash_drink_carrier_01",
    "p7_debris_trash_paper_plate_01", "p7_debris_trash_paper_05",
)
#: Dropped forms and tickets: sheets, a stack, a folder.
DROPPED_FORMS = (
    "p7_office_paper_sheet_01", "p7_office_paper_sheet_12", "p7_office_paper_sheet_02",
    "p7_office_paper_stack_sml", "p7_office_paper_sheet_08", "p7_office_paper_folder_pink",
    "p7_office_paper_sheet_03", "p7_office_paper_sheet_10",
)
#: What a draft pushes into a corner: loose paper of every kind.
DRIFT = (
    "p7_office_paper_sheet_09", "p7_debris_trash_paper_10", "p7_cleaning_paper_towel",
    "p7_office_paper_sheet_02", "p7_debris_newspaper_01", "p7_cleaning_paper_brown",
    "p7_office_paper_sheet_12", "p7_debris_trash_paper_05",
)
#: Somebody's things, left where they sat: a jacket, a shirt, a water bottle, a folder.
LEFT_BEHIND = (
    "p7_debris_clothing_tshirts_01", "p7_bottle_plastic_16oz_water", "p7_office_paper_folder_blue",
    "p7_debris_clothing_pants_01", "p7_debris_trash_cup_coffee_02",
)


def bins_in(ctx) -> list[tuple[float, float]]:
    """:func:`zmforge.dressing.bins_in` for this room."""
    return dressing.bins_in(ctx.bp, ctx.room)


def seats_in(ctx) -> list[tuple[float, float]]:
    """:func:`zmforge.dressing.seats_in` for this room."""
    return dressing.seats_in(ctx.bp, ctx.room)


def litter_heaps(ctx, rect, n: int, seed: int, heaps, *, keep_out=(),
                 margin: float = 2.0, solid_margin: float = 6.0) -> list[tuple]:
    """:func:`zmforge.dressing.litter_heaps` in this room."""
    return dressing.litter_heaps(ctx.bp, ctx.room, rect, n, seed, heaps, keep_out=keep_out,
                                 margin=margin, solid_margin=solid_margin)


def room_heaps(ctx, rect, seed: int) -> list[tuple]:
    """The usual heaps of a public room: every bin overflowing, the four
    corners drifted, forms dropped by two seats and somebody's things left
    on a third (seats picked by *seed*)."""
    heaps = [(bx, by, 16.0, 2.0, BIN_SPILL) for bx, by in bins_in(ctx)]
    heaps += [(cx, cy, 16.0, 1.5, DRIFT) for cx, cy in corner_heaps(rect)]
    seats = seats_in(ctx)
    if seats:
        rng = _cr.Random(seed)
        pick = rng.sample(seats, min(3, len(seats)))
        for i, (sx, sy) in enumerate(pick):
            if i < 2:
                heaps.append((sx + 24.0, sy + 24.0, 14.0, 1.5, DROPPED_FORMS))
            else:
                heaps.append((sx + 20.0, sy - 20.0, 10.0, 0.6, LEFT_BEHIND))
    return heaps
