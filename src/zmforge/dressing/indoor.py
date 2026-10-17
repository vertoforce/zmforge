"""Indoor vignettes: the "what happened here" heaps of a lab, office, clinic or institution.

:mod:`.vignette` is the library of small composed stories; all sixteen of
its kinds are outdoor and farm (a picnic, a hay wagon, a scarecrow).  Indoor
rooms without them come out at a fraction of the stock density, with nothing
in them that says what happened: tidy furniture on a clean floor.  This
module adds the indoor kinds and the room-side
plumbing to lay them:

* :data:`INDOOR_KINDS` -- seven kinds, each a one-line story built from
  stock realistic models that link locally (measured boxes in
  ``recipes.props.MODEL_BOX``) and worn catalogued brushes: an overturned
  desk with its files spilled, collapsed shelving, a gurney pile-up, a
  barricade of chairs, a fallen ceiling panel with its cables, an abandoned
  evacuation, a flooded and sparking corner.
* :data:`THEMES` -- which kinds suit a ``lab``, ``office``, ``clinic`` or
  ``institution`` room.
* :class:`IndoorSpot` -- a :class:`~.vignette.Spot` that knows its ceiling,
  so a kind can hang cables or drop a ceiling panel from it.
* :class:`RoomPlacer` -- the rules of one roofed room: inside its walls,
  off every doorway's 96-unit approach lane, off barricade windows, off
  every interactive's keep-clear, off what already stands there, and off
  any keep-outs the recipe hands it.
* :func:`wall_spots` -- clear stretches along the room's walls a vignette
  of a given size fits.
* :func:`dress_indoor` -- choose and lay *count* vignettes of a theme.

All placement goes through :func:`zmforge.dressing.vignette.place_vignette`
(``library=INDOOR_KINDS``), so a vignette is all or nothing for its core
parts, exactly as outdoors.  No part carries text (P17).  Avoided on
purpose: ``p7_desk_metal_old_01`` (placeholder material; its ``_body`` is
fine), ``p7_foliage_grass_dry_03`` and the ``ar_cqb`` set.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Sequence

from ..materials import Material
from ..spatial import Bounds
from .fixtures import RAIL
from .vignette import (
    IRON,
    Block,
    Fx,
    Glow,
    Item,
    Kind,
    SimplePlacer,
    Slant,
    Spot,
    Vignette,
    _model_box,
    choose_kind,
    place_vignette,
)

__all__ = [
    "INDOOR_KINDS", "THEMES", "INDOOR_SETTLE", "IndoorSpot", "RoomPlacer",
    "wall_spots", "floor_spots", "dress_indoor", "door_lanes", "SHELF_STOCK", "packed_shelves",
    "load_surfaces", "STORES", "stacked_stores",
]

#: Worn, catalogued brush materials for the heaps.
STEEL = Material("t7_metal_panel_horizontal_painted", 64.0)
PANEL = Material("t7_plastic_panels_white", 64.0)
CEILING_TILE = Material("t7_plastic_ceiling_corrugated_panel", 48.0)
PAD = Material("t7_plaster_smooth_dirty_01", 32.0)
WET = Material("t7_concrete_bare_dark_01_wet", 64.0)
VOID = Material("t7_concrete_wall_dark_01", 64.0)
#: A cold, flickering-looking electrical light and a dim institutional one.
COLD = (0.62, 0.76, 1.0)
PALE = (0.85, 0.88, 0.95)

#: Floor litter that settles an indoor heap into the room (instead of the
#: outdoor weeds of :data:`~.vignette.SETTLE`): ``(model, (scale_lo, scale_hi))``.
INDOOR_SETTLE = (
    ("p7_debris_trash_paper_03", (1.0, 1.3)), ("p7_debris_trash_paper_05", (1.0, 1.3)),
    ("p7_office_paper_sheet_01", (1.0, 1.0)), ("p7_office_paper_sheet_09", (1.0, 1.0)),
    ("p7_office_paper_folder_blue", (1.0, 1.0)), ("p7_office_paper_folder_pink", (1.0, 1.0)),
    ("p7_debris_concrete_rubble_sm_06", (0.8, 1.2)), ("p7_debris_trash_cup_coffee_02", (1.0, 1.0)),
)

_PAPERS = ("p7_office_paper_sheet_01", "p7_office_paper_sheet_02", "p7_office_paper_sheet_03",
           "p7_office_paper_sheet_08", "p7_office_paper_sheet_09", "p7_office_paper_sheet_10",
           "p7_office_paper_sheet_12")
_BOOKS = ("p7_book_vintage_01", "p7_book_vintage_02", "p7_book_vintage_03", "p7_book_vintage_04",
          "p7_book_vintage_05", "p7_book_vintage_open_01", "p7_book_vintage_open_04")
_RUBBLE = ("p7_debris_concrete_rubble_sm_01", "p7_debris_concrete_rubble_sm_03",
           "p7_debris_concrete_rubble_sm_07", "p7_debris_concrete_rubble_sm_10",
           "p7_debris_concrete_rubble_sm_12")
_CHAIRS = ("p7_sgen_chair_dining_future", "p7_chair_wood_fancy_01", "p7_chair_waiting_room_01_blue",
           "p7_chair_lab_02")


@dataclass(frozen=True)
class IndoorSpot(Spot):
    """A :class:`~.vignette.Spot` in a roofed room.  ``u`` runs from the back
    line (``-back``: a wall face, or the far edge of a floor patch) into the
    room; *height* is floor to ceiling, for the kinds that hang things."""

    height: float = 320.0


def _j(rng: random.Random, amount: float = 4.0) -> float:
    return rng.uniform(-amount, amount)


def _scatter(rng, models, u0, u1, v0, v1, n, *, scale=(1.0, 1.0)) -> list[Item]:
    return [Item(models[k % len(models)], rng.uniform(u0, u1), rng.uniform(v0, v1),
                 rng.uniform(0, 360), rng.uniform(*scale), solid=False) for k in range(n)]


# ---------------------------------------------------------------------------
# The kinds.  ``w = -spot.back`` is the back line (the wall); every part
# stands out from it by at least its own half depth.
# ---------------------------------------------------------------------------
def _overturned_desk(rng, spot):
    w = -spot.back
    parts: list = [
        # The desk on its side as cover: its top stands on edge facing the
        # room, its two pedestals lie back toward the wall.
        Block(w + 40, -38, 0, w + 42, 38, 36, STEEL, "desk_top"),
        Block(w + 12, -38, 0, w + 40, -26, 30, STEEL, "desk_pedestal"),
        Block(w + 12, 26, 0, w + 40, 38, 30, STEEL, "desk_pedestal"),
        Item("p7_desk_metal_old_01_drawer_small_01", w + 58, -22, 20 + _j(rng, 25), solid=False, core=True),
        Item("p7_desk_metal_old_01_drawer_small_01", w + 64, 26, 160 + _j(rng, 25), solid=False),
        Item("p7_debris_paper_sheet_01", w + 70, -4, rng.uniform(0, 360), solid=False, core=True),
        Item("p7_file_cab_metal_02", w + 17, -64, 270, solid=True, core=True),
        Item("p7_file_cab_metal_02_drawer_02", w + 46, -62, 270 + _j(rng, 20), solid=False),
        Item("p7_chair_lab_01", w + 80, 50, rng.uniform(0, 360), solid=True),
        Item("p7_keyboard_metal_tech", w + 70, 58, 200 + _j(rng, 20), solid=False),
        Item("p7_book_office_binder_open", w + 60, 6, rng.uniform(0, 360), solid=False),
        Item("p7_office_paper_stack_sml", w + 90, -30, rng.uniform(0, 360), solid=False),
        Item("p7_cup_coffee_mug", w + 52, 44, rng.uniform(0, 360), solid=False),
    ]
    parts += _scatter(rng, _PAPERS, w + 48, w + 104, -56, 44, 7)
    parts += _scatter(rng, ("p7_office_paper_folder_blue", "p7_office_paper_folder_pink"),
                      w + 50, w + 100, -40, 40, 3)
    return parts


def _collapsed_shelving(rng, spot):
    w = -spot.back
    parts: list = [
        Item("p7_shelf_metal_lab_01", w + 18, -52, 90, solid=True, core=True),
        # The second unit came down off the wall and lies across the aisle.
        Slant((w + 96, 60, 0), (w + 6, 60, 78), 50, 1.5, STEEL, "fallen_shelf"),
        Block(w + 60, 14, 0, w + 64, 106, 2, STEEL, "shelf_board", core=False),
        Item("p7_books_office_row_01", w + 18, -76, 90, on=0, solid=False),
        Item("p7_box_wood_01_sm", w + 18, -36, 0, on=0, solid=False),
        Item("p7_container_cardboard_box_01", w + 100, 30, rng.uniform(0, 360), solid=True, core=True),
        Item("p7_container_cardboard_box_01", w + 84, -24, rng.uniform(0, 360), solid=True),
        Item("p7_box_wood_01_long", w + 112, 76, rng.uniform(0, 360), solid=False),
        Item("p7_grating_metal_01_panel", w + 104, -64, rng.uniform(0, 360), solid=False),
        Item("p7_debris_paper_sheet_01", w + 120, -10, rng.uniform(0, 360), solid=False),
        Item("p7_book_office_binder_open", w + 104, 64, rng.uniform(0, 360), solid=False),
    ]
    # from 76: a book at 70 lay 2% on the fallen board (Z44)
    parts += _scatter(rng, _BOOKS, w + 76, w + 128, -80, 100, 9)
    parts += _scatter(rng, _PAPERS, w + 60, w + 130, -90, 100, 5)
    return parts


def _gurney(u0: float, v0: float, name: str, *, length: float = 78.0, width: float = 26.0,
            top: float = 30.0) -> list:
    """A gurney from brushes: a frame, four legs on casters, a pad."""
    u1, v1 = u0 + width, v0 + length
    parts: list = [Block(u0, v0, top - 3, u1, v1, top, IRON, f"{name}_frame", floats=True)]
    for lu, lv in ((u0 + 2, v0 + 4), (u1 - 4, v0 + 4), (u0 + 2, v1 - 6), (u1 - 4, v1 - 6)):
        parts.append(Block(lu, lv, 0, lu + 2, lv + 2, top - 3, RAIL, f"{name}_leg", core=False))
        parts.append(Block(lu - 0.5, lv - 0.5, 0, lu + 2.5, lv + 2.5, 3, RAIL, f"{name}_caster",
                           core=False))
    parts.append(Block(u0 + 1, v0 + 2, top, u1 - 1, v1 - 2, top + 4, PAD, f"{name}_pad", floats=True))
    return parts


def _gurney_pileup(rng, spot):
    w = -spot.back
    parts: list = []
    parts += _gurney(w + 4, -104, "gurney_a")
    parts += _gurney(w + 38, -46, "gurney_b")
    n_pad_b = len(parts) - 1
    parts += [
        # The third one went over on its side.
        Slant((w + 104, 44, 0), (w + 76, 44, 30), 39, 1.5, IRON, "gurney_c"),
        Block(w + 106, 8, 0, w + 110, 80, 3, RAIL, "gurney_c_rail", core=False),
        Item("p7_bed_sheet_barrack_03", w + 51, -8, 90 + _j(rng, 10), 0.6, on=n_pad_b, solid=False),
        Item("p7_bed_pillow_barrack", w + 50, 22, 90 + _j(rng, 10), 0.8, on=n_pad_b, solid=False),
        Item("p7_bed_sheet_barrack_02", w + 92, -40, rng.uniform(0, 360), 0.6, solid=False, core=True),
        Item("p7_bed_pillow_barrack", w + 110, -86, rng.uniform(0, 360), 0.8, solid=False),
        Item("p7_tank_nitrogen_metal", w + 14, 70, 0, solid=True),
        # A drip stand: pole on a cross foot.
        Block(w + 66, 96, 2, w + 67.5, 97.5, 74, RAIL, "drip_pole", core=False),
        Block(w + 60, 90, 0, w + 73.5, 103.5, 2, RAIL, "drip_foot", core=False),
        Item("p7_bottle_plastic_16oz_water", w + 86, -70, rng.uniform(0, 360), solid=False),
        Item("p7_bottle_plastic_16oz_water", w + 124, 20, rng.uniform(0, 360), solid=False),
    ]
    parts += _scatter(rng, _PAPERS, w + 80, w + 130, -100, 80, 4)
    return parts


def _chair_barricade(rng, spot):
    w = -spot.back
    parts: list = [
        Item("p7_desk_metal_military_02", w + 22, 0, 90, solid=True, core=True),
        Item(_CHAIRS[0], w + 16, -26, rng.uniform(0, 360), on=0, solid=True),
        Item(_CHAIRS[1], w + 24, 20, rng.uniform(0, 360), on=0, solid=True),
        # A table top leant against the desk as a second wall.
        Slant((w + 80, -68, 0), (w + 44, -68, 40), 24, 1.0, PANEL, "table_top"),
        Item(_CHAIRS[2], w + 62, -24, rng.uniform(0, 360), solid=True, core=True),
        Item(_CHAIRS[0], w + 70, 34, rng.uniform(0, 360), solid=True),
        Item(_CHAIRS[3], w + 56, 70, rng.uniform(0, 360), solid=True),
        Item(_CHAIRS[1], w + 96, 4, rng.uniform(0, 360), solid=True),
        Item("p7_debris_wood_board_2x4x128", w + 104, -30, 80 + _j(rng, 20), 0.6, solid=False),
        Item("p7_debris_wood_board_cluster_02", w + 90, 60, rng.uniform(0, 360), solid=False),
        Item("p7_container_cardboard_box_01", w + 24, 70, rng.uniform(0, 360), solid=True),
        Item("p7_debris_trash_paper_03", w + 84, -50, rng.uniform(0, 360), solid=False),
    ]
    return parts


def _fallen_ceiling(rng, spot: IndoorSpot):
    w = -spot.back
    top = getattr(spot, "height", 320.0)
    parts: list = [
        # The panel broke as it fell: a short piece still hangs from the hole's
        # edge, the rest lies on the floor in two pieces (one whole 80-wide
        # slab floor to ceiling dominated every render).
        Slant((w + 58, 10, top * 0.55), (w + 36, 10, top), 22, 1.0, CEILING_TILE, "ceiling_panel"),
        Slant((w + 138, -6, 0), (w + 100, 0, 18), 22, 1.0, CEILING_TILE, "panel_piece", core=False),
        Block(w + 96, 28, 0, w + 128, 62, 1.5, CEILING_TILE, "panel_flat", core=False),
        # The hole it left: dark void where the panel was.
        Block(w + 20, -34, top - 1, w + 104, 54, top, VOID, "ceiling_hole", floats=True),
        # The dead fitting still hangs in the hole on its cables (on the floor
        # Z44 reads it as a ceiling fixture dealt onto the ground), off
        # the hanging piece's side (22 half-wide about v 10).
        Item("p7_light_fixture_led_ceiling_01_dmg", w + 62, -24, 90.0, solid=False,
             core=True, dz=top - 6.0),
        Item("p7_debris_plaster_rubble_med_01", w + 100, 40, rng.uniform(0, 360), solid=False),
        Item("p7_debris_plaster_rubble_med_03", w + 100, -40, rng.uniform(0, 360), solid=False),
        Item("p7_grating_metal_01_panel", w + 128, -56, rng.uniform(0, 360), 1.5, solid=False),
        Item("p7_grating_metal_01_panel", w + 30, -56, rng.uniform(0, 360), 1.5, solid=False),
        Glow(w + 60, 10, top - 30, COLD, 180.0),
    ]
    # Cut cables hanging out of the hole.
    for k, (cu, cv, drop) in enumerate(((w + 30, -20, 90), (w + 70, 40, 130), (w + 92, -26, 60))):
        parts.append(Block(cu, cv, top - drop, cu + 0.8, cv + 0.8, top, RAIL, f"cable_{k}", core=False,
                           floats=True))
    # rubble and paper off the broken pieces (a chip half on a piece is Z44)
    parts += _scatter(rng, _RUBBLE, w + 70, w + 140, -74, -38, 6, scale=(0.8, 1.2))
    parts += _scatter(rng, ("p7_debris_trash_paper_03", "p7_debris_trash_paper_05"),
                      w + 60, w + 90, 20, 70, 3)
    return parts


def _abandoned_evacuation(rng, spot):
    w = -spot.back
    parts: list = [
        Item("zmf_prop_hand_cart", w + 66, 6, 90 + _j(rng, 12), solid=True, core=True),
        Item("p7_container_cardboard_box_01", w + 66, -4, rng.uniform(0, 360), 0.9, on=0, solid=False),
        Item("p7_container_cardboard_box_01", w + 24, -66, 0, solid=True, core=True),
        Item("p7_container_cardboard_box_01", w + 24, -66, 12, 0.9, on=2, solid=True),
        Item("p7_crate_plastic_tech_01", w + 17, -10, 0, solid=True),
        Item("p7_box_wood_01_long", w + 17, -10, 0, on=4, solid=False),
        Item("p7_debris_clothing_piles_01", w + 108, 50, rng.uniform(0, 360), solid=False),
        Item("p7_debris_paper_sheet_01", w + 110, -40, rng.uniform(0, 360), solid=False),
        Item("p7_book_office_binder_open", w + 96, -6, rng.uniform(0, 360), solid=False),
        Item("p7_office_paper_stack_sml", w + 40, 40, rng.uniform(0, 360), solid=False),
        Item("p7_chair_lab_02", w + 30, 62, rng.uniform(0, 360), solid=True),
        Item("p7_bottle_plastic_16oz_water", w + 88, 30, rng.uniform(0, 360), solid=False),
        Item("p7_bottle_plastic_16oz_water", w + 92, 36, rng.uniform(0, 360), solid=False),
    ]
    parts += _scatter(rng, _PAPERS, w + 50, w + 130, -80, 80, 7)
    parts += _scatter(rng, ("p7_office_paper_folder_blue", "p7_office_paper_folder_pink"),
                      w + 70, w + 130, -60, 60, 3)
    return parts


def _flooded_corner(rng, spot):
    w = -spot.back

    def wet(u: float, v: float) -> float:
        """How far the water lifts a thing standing at (u, v)."""
        if w + 40 <= u <= w + 150 and 30 <= v <= 86:
            return 0.9
        return 0.6 if (w + 1 <= u <= w + 118 and -86 <= v <= 40) else 0.0

    parts: list = [
        # The water: two dark wet sheets at different depths, so the edge is ragged.
        Block(w + 1, -86, 0, w + 118, 40, 0.6, WET, "flood"),
        Block(w + 40, 30, 0, w + 150, 86, 0.9, WET, "flood_edge", core=False),
        # The burst riser: two lengths of pipe and an elbow at the wall.
        Item("p7_pipe_metal_hp_12_straight_64_bare", w + 12, -52, 0, dz=wet(w + 12, -52), solid=True,
             core=True),
        Item("p7_pipe_metal_hp_12_straight_64_bare", w + 12, -52, 0, on=2, solid=True),
        # v 62: at 52 it stood 21% on the water sheet (Z44)
        Item("p7_electrical_box_tall_red", w + 18, 62, 270, solid=True),
        # A cut cable from the box to the water, and the sparks off it.
        Slant((w + 60, 30, 1), (w + 36, 44, 60), 0.6, 0.6, RAIL, "cut_cable", core=False),
        Fx("embers", w + 48, 36, 8.0),
        Glow(w + 48, 36, 30.0, COLD, 150.0),
    ]
    loose = [("p7_barrel_metal_55gal_blue", w + 98, -60, 0.0, 1.0, True),
             ("p7_container_cardboard_box_01", w + 70, -20, rng.uniform(0, 360), 0.9, True),
             ("p7_debris_paper_sheet_01", w + 72, -40, rng.uniform(0, 360), 1.0, False)]
    # inside one sheet, clear of its edges (a paper across two depths is Z44)
    loose += [(_PAPERS[k], rng.uniform(w + 44, w + 106), rng.uniform(-74, 18), rng.uniform(0, 360), 1.0,
               False) for k in range(4)]
    parts += [Item(m, u, v, yaw, sc, dz=wet(u, v), solid=solid) for m, u, v, yaw, sc, solid in loose]
    return parts


INDOOR_KINDS: dict[str, Kind] = {k.name: k for k in (
    Kind("overturned_desk", "Someone tipped the desk over for cover; the files spilled out and "
         "nobody came back for them.", ("wall_face", "dead_end", "clearing_edge"), _overturned_desk,
         (150.0, 110.0), (60.0, 0.0, 20.0), large=True),
    Kind("collapsed_shelving", "A shelving unit came off the wall across the aisle and spilled a year "
         "of records over the floor.", ("wall_face", "dead_end", "clearing_edge"), _collapsed_shelving,
         (230.0, 135.0), (70.0, 20.0, 30.0), large=True),
    Kind("gurney_pileup", "The gurneys were rammed into a heap to hold the room; the sheets are "
         "still on them.", ("wall_face", "dead_end", "clearing_edge"), _gurney_pileup,
         (220.0, 132.0), (60.0, 0.0, 30.0), large=True),
    Kind("chair_barricade", "Every chair in the room was piled against the desk as a barricade, "
         "and it did not hold.", ("wall_face", "dead_end", "clearing_edge"), _chair_barricade,
         (190.0, 120.0), (50.0, 0.0, 40.0), large=True),
    Kind("fallen_ceiling", "A ceiling panel gave way and came down with its light and cables; "
         "the dust has not settled.", ("wall_face", "dead_end", "clearing_edge"), _fallen_ceiling,
         (170.0, 155.0), (80.0, 10.0, 80.0), large=True),
    Kind("abandoned_evacuation", "They packed to leave and never got the cart out: boxes taped, "
         "papers everywhere, a coat on the floor.", ("wall_face", "dead_end", "clearing_edge"),
         _abandoned_evacuation, (180.0, 140.0), (60.0, 0.0, 20.0), large=True),
    Kind("flooded_corner", "A pipe burst at the wall; the corner is flooded and a cut cable still "
         "spits sparks at the water.", ("wall_face", "dead_end", "clearing_edge"), _flooded_corner,
         (180.0, 155.0), (40.0, 40.0, 30.0), large=True),
)}

#: Which kinds suit which room theme (a recipe may pass its own list).
THEMES: dict[str, tuple[str, ...]] = {
    "lab": ("collapsed_shelving", "fallen_ceiling", "flooded_corner", "abandoned_evacuation",
            "overturned_desk"),
    "office": ("overturned_desk", "chair_barricade", "abandoned_evacuation", "collapsed_shelving",
               "fallen_ceiling"),
    "clinic": ("gurney_pileup", "fallen_ceiling", "flooded_corner", "abandoned_evacuation",
               "collapsed_shelving"),
    "institution": ("chair_barricade", "overturned_desk", "abandoned_evacuation", "fallen_ceiling",
                    "gurney_pileup", "collapsed_shelving", "flooded_corner"),
}


# ---------------------------------------------------------------------------
# The room's rules
# ---------------------------------------------------------------------------
#: How far into a room a doorway's approach lane runs, and how far past each
#: jamb (96-unit lanes; Z53's band is 48).
DOOR_LANE, DOOR_SIDE = 96.0, 16.0


def door_lanes(room, *, depth: float = DOOR_LANE, side: float = DOOR_SIDE) -> list[Bounds]:
    """A keep-out box per floor-level opening in *room*'s walls: the opening
    plus *side* past each jamb, *depth* into the room.  Openings with a sill
    over 48 (windows, observation slots) get a 48-deep band only."""
    b = room.interior
    out: list[Bounds] = []
    for ap, box in zip(room.apertures, room.aperture_boxes):
        d = depth if ap.sill <= 48.0 else 48.0
        z0, z1 = b.mins.z - 8.0, b.maxs.z
        if ap.side.axis.name == "X":
            y0, y1 = box.mins.y - side, box.maxs.y + side
            if ap.side.value[1] < 0:
                out.append(Bounds.between((b.mins.x - 1.0, y0, z0), (b.mins.x + d, y1, z1)))
            else:
                out.append(Bounds.between((b.maxs.x - d, y0, z0), (b.maxs.x + 1.0, y1, z1)))
        else:
            x0, x1 = box.mins.x - side, box.maxs.x + side
            if ap.side.value[1] < 0:
                out.append(Bounds.between((x0, b.mins.y - 1.0, z0), (x1, b.mins.y + d, z1)))
            else:
                out.append(Bounds.between((x0, b.maxs.y - d, z0), (x1, b.maxs.y + 1.0, z1)))
    return out


class RoomPlacer(SimplePlacer):
    """:class:`~.vignette.SimplePlacer` for one roofed room: also refuses parts
    outside the room's walls (less *margin*), in a doorway's approach lane
    (:func:`door_lanes`), in a barricade window's zone, and over anything
    already standing on the floor.  *zone* names the zone for owned lights."""

    def __init__(self, bp, room, keepouts: Sequence[Bounds] = (), *, margin: float = 1.0,
                 zone: str | None = None, lanes: bool = True):
        from .keepout import window_keepouts
        from .place import floor_footprints

        extra = list(keepouts)
        if lanes:
            extra += door_lanes(room)
        extra += window_keepouts(bp)
        super().__init__(bp, extra)
        self.room = room
        self.margin = margin
        self.zone = zone
        # What stands on the floor already; flat litter (under 6 units) may be
        # built over, the way a heap lands on the papers round it.
        self.standing = [(f.mins.x, f.mins.y, f.maxs.x, f.maxs.y) for f in floor_footprints(bp, room)
                         if f.maxs.z - room.floor_z > 6.0]
        self.reserved: list[tuple[float, float, float, float]] = []

    def zone_of(self, room) -> str | None:
        return self.zone

    def _inside(self, x0, y0, x1, y1) -> bool:
        b = self.room.interior
        m = self.margin
        return b.mins.x + m <= x0 and x1 <= b.maxs.x - m and b.mins.y + m <= y0 and y1 <= b.maxs.y - m

    def _free(self, x0, y0, x1, y1) -> bool:
        return not any(a < x1 and c > x0 and b < y1 and d > y0 for a, b, c, d in self.standing)

    def fits(self, room, model, x, y, surface, yaw, scale, solid) -> bool:
        from .place import turned_box

        if _model_box(model) is None:
            return False
        bx0, by0, bx1, by1 = turned_box(model, yaw)
        box = (x + bx0 * scale, y + by0 * scale, x + bx1 * scale, y + by1 * scale)
        return self._inside(*box) and self._free(*box) and self._clear(*box, surface)

    def fits_box(self, room, box) -> bool:
        xy = (box.mins.x, box.mins.y, box.maxs.x, box.maxs.y)
        return self._inside(*xy) and self._free(*xy) and self._clear(*xy, box.mins.z)

    def reserve(self, room, box) -> None:
        super().reserve(room, box)
        self.standing.append((box.mins.x, box.mins.y, box.maxs.x, box.maxs.y))
        self.reserved.append((box.mins.x, box.mins.y, box.maxs.x, box.maxs.y))


# ---------------------------------------------------------------------------
# Where, and how many
# ---------------------------------------------------------------------------
_WALLS = (("south", 90.0), ("north", 270.0), ("west", 0.0), ("east", 180.0))


def wall_spots(room, placer: RoomPlacer, *, width: float, depth: float, step: float = 48.0,
               walls: Sequence[str] = ("south", "north", "west", "east")) -> list[IndoorSpot]:
    """Every stretch along *room*'s walls where a *width* x *depth* patch is
    clear by *placer*'s rules, one per *step*, facing into the room."""
    b = room.interior
    f = room.floor_z
    h = b.maxs.z - f
    out: list[IndoorSpot] = []
    for name, yaw in _WALLS:
        if name not in walls:
            continue
        horizontal = name in ("south", "north")
        lo, hi = ((b.mins.x, b.maxs.x) if horizontal else (b.mins.y, b.maxs.y))
        t = lo + width / 2.0 + 2.0
        while t <= hi - width / 2.0 - 2.0:
            if name == "south":
                x, y, box = t, b.mins.y, (t - width / 2, b.mins.y, t + width / 2, b.mins.y + depth)
            elif name == "north":
                x, y, box = t, b.maxs.y, (t - width / 2, b.maxs.y - depth, t + width / 2, b.maxs.y)
            elif name == "west":
                x, y, box = b.mins.x, t, (b.mins.x, t - width / 2, b.mins.x + depth, t + width / 2)
            else:
                x, y, box = b.maxs.x, t, (b.maxs.x - depth, t - width / 2, b.maxs.x, t + width / 2)
            if placer.fits_box(room, Bounds.between((box[0] + 1.5, box[1] + 1.5, f),
                                                    (box[2] - 1.5, box[3] - 1.5, f + 8.0))):
                out.append(IndoorSpot(x, y, f, yaw, "wall_face", getattr(room, "id", "room"),
                                      width=width, back=0.0, reach=depth, height=h))
            t += step
    return out


def floor_spots(room, placer: RoomPlacer, *, width: float, depth: float, step: float = 32.0
                ) -> list[IndoorSpot]:
    """Clear *width* x *depth* patches anywhere on *room*'s floor (four
    facings each), for a heap out in the open when the walls are taken: a
    ``clearing_edge`` spot whose back line is the patch's far edge."""
    b = room.interior
    f = room.floor_z
    h = b.maxs.z - f
    out: list[IndoorSpot] = []
    rid = getattr(room, "id", "room")
    x = b.mins.x + step
    while x < b.maxs.x - step:
        y = b.mins.y + step
        while y < b.maxs.y - step:
            for yaw in (0.0, 90.0, 180.0, 270.0):
                spot = IndoorSpot(x, y, f, yaw, "clearing_edge", rid, width=width, back=0.0,
                                  reach=depth, height=h)
                if placer.fits_box(rid, Bounds.between(*_spot_box(spot))):
                    out.append(spot)
            y += step
        x += step
    return out


def dress_indoor(bp, room, placer: RoomPlacer, rng: random.Random, *, count: int,
                 theme: str | Sequence[str] = "institution", ident: str,
                 gap: float = 400.0, open_floor: bool = False) -> list[Vignette]:
    """Lay up to *count* indoor vignettes of *theme* (a :data:`THEMES` key or
    a list of kind names) along *room*'s walls, no two within *gap* of each
    other, each through *placer* (all or nothing for its core parts); with
    *open_floor*, out on the open floor too (:func:`floor_spots`) when the
    walls run out.  Call ``placer.flush()`` after.  Returns the placed records."""
    names = list(THEMES[theme] if isinstance(theme, str) else theme)
    library = {n: INDOOR_KINDS[n] for n in names}
    placed: list[Vignette] = []
    # Candidate spots fit the smallest kind; each kind then tries its own size.
    width = min(k.needs[0] for k in library.values())
    depth = min(k.needs[1] for k in library.values())
    spots = wall_spots(room, placer, width=width, depth=depth, step=24.0)
    rng.shuffle(spots)
    if open_floor:
        more = floor_spots(room, placer, width=width, depth=depth, step=24.0)
        rng.shuffle(more)
        spots += more
    for spot in spots:
        if len(placed) >= count:
            break
        if any(math.hypot(v.focus[0] - spot.x, v.focus[1] - spot.y) < gap for v in placed):
            continue
        # Re-check: an earlier vignette may have reserved this stretch.
        probe = Bounds.between(*_spot_box(spot))
        if not placer.fits_box(spot.room, probe):
            continue
        # every kind is a candidate here; each is then tried at its own size
        roomy = replace(spot, width=1e6, reach=1e6)
        for kind in choose_kind(rng, roomy, placed, gap=gap * 2, library=library):
            k = library[kind]
            s = IndoorSpot(spot.x, spot.y, spot.z, spot.yaw, spot.kind, spot.room,
                           width=k.needs[0], back=0.0, reach=k.needs[1], height=spot.height)
            made = place_vignette(bp, kind, s, rng, placer, ident=f"{ident}_{len(placed)}",
                                  library=library, settle_models=INDOOR_SETTLE, settle=(3, 6))
            if made is not None:
                placed.append(made)
                break
    return placed


def _spot_box(spot: Spot):
    pts = [spot.world(u, v) for u in (1.5, spot.reach - 1.5) for v in (-spot.width / 2 + 1.5,
                                                                      spot.width / 2 - 1.5)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), spot.z), (max(xs), max(ys), spot.z + 8.0)


# ---------------------------------------------------------------------------
# Packed shelving against the walls
# ---------------------------------------------------------------------------
#: What a room's shelves hold, per theme: ``((model, weight), ...)`` for
#: :func:`zmforge.dressing.interior.fill_board`.  Low things first (the lab
#: shelf's boards are 12 apart, so only books lying flat, pillows, pans and
#: small boxes fit it; the industrial shelf's 28-unit gaps take boxes and files).  No
#: litter-named models (``bottle``, ``paper``, ``cup_``): Z74 caps each at 40 a map.
SHELF_STOCK: dict[str, tuple[tuple[str, int], ...]] = {
    "office": (("p7_book_vintage_01", 3), ("p7_book_vintage_02", 3), ("p7_book_vintage_05", 3),
               ("p7_book_vintage_06", 2), ("p7_book_vintage_open_04", 1),
               ("p7_box_wood_wine_storage_tan", 2), ("p7_books_office_row_01", 3),
               ("p7_book_office_lrg_red", 2), ("p7_book_office_med_brown", 2),
               ("p7_book_office_sml_beige", 2), ("p7_file_cab_metal_02_drawer_02", 1),
               ("p7_desk_metal_old_01_drawer_small_01", 1), ("p7_box_wood_01_sm", 1)),
    "clinic": (("p7_bed_pillow_barrack", 3), ("p7_box_wood_wine_storage", 3),
               ("p7_pan_metal_sauce", 2), ("p7_pan_metal_lid", 2), ("p7_pot_metal_boiling_lg", 1),
               ("p7_book_vintage_03", 2), ("p7_zm_der_cabinet_lab_drawer", 1),
               ("p7_box_wood_01_sm", 1)),
    "lab": (("p7_box_wood_wine_storage", 2), ("p7_box_wood_01_sm", 2), ("p7_pot_metal_boiling_lg", 2),
            ("p7_pan_metal_sauce", 2), ("p7_book_vintage_04", 2), ("p7_book_vintage_02", 1),
            ("p7_electrical_box_set2_meterhead01", 1), ("p7_zm_der_cabinet_lab_drawer", 1)),
    "plant": (("p7_electrical_box_set2_meter05", 2), ("p7_electrical_box_set2_meter09", 2),
              ("p7_electrical_box_set2_meterhead01", 3), ("p7_electrical_box_set2_meterhead02", 3),
              ("p7_electrical_box_set_box_4", 2), ("p7_box_wood_01_sm", 3), ("p7_cinder_block", 2),
              ("p7_brick_dirty_01", 1), ("p7_pan_metal_lid", 1), ("p7_box_wood_wine_storage", 2)),
    "burnt": (("p7_book_vintage_01_burn", 3), ("p7_book_vintage_02_burn", 3),
              ("p7_book_vintage_05_burn", 2), ("p7_book_vintage_open_01_burn", 1),
              ("p7_book_vintage_03", 2), ("p7_box_wood_wine_storage_tan", 2),
              ("p7_books_office_row_01", 2), ("p7_book_office_med_brown", 1)),
}
#: Shelf units with measured boards (``recipes.props.SHELF_BOARDS``).
SHELF_UNITS = ("p7_shelf_metal_lab_01", "p7_shelf_industrial_vintage_96")


def packed_shelves(bp, room, placer: RoomPlacer, rng: random.Random, *, count: int,
                   stock: str | Sequence[tuple[str, int]] = "office", ident: str,
                   units: Sequence[str] = SHELF_UNITS, gap: float = 32.0,
                   walls: Sequence[str] = ("south", "north", "west", "east")) -> int:
    """Stand up to *count* shelf units along *room*'s walls where *placer*
    lets them (door lanes, windows, buys and keep-outs stay clear), backs to
    the wall and *gap* apart, each board packed end to end from *stock* (a
    :data:`SHELF_STOCK` key or a palette) in runs of like items, the way a
    store room's shelves are full rather than dotted.  A unit takes a
    keep-out, so later heaps keep off it.  Places the props through
    *placer* (call ``placer.flush()`` after); returns how many."""
    from ..recipes.props import shelf_boards
    from .interior import fill_board

    palette = SHELF_STOCK[stock] if isinstance(stock, str) else tuple(stock)
    rid = getattr(room, "id", "room")
    f = room.floor_z
    made, n = [], 0
    spots: list[tuple[IndoorSpot, str]] = []
    for unit in units:
        (lx, ly, _lz), (hx, hy, hz) = _model_box(unit)
        for spot in wall_spots(room, placer, width=hx - lx + 6.0, depth=hy - ly + 6.0, step=24.0,
                               walls=walls):
            spots.append((spot, unit))
    rng.shuffle(spots)
    last = None
    for spot, unit in spots:
        if len(made) >= count:
            break
        if last is not None and unit == last and any(u != last for _s, u in spots):
            # alternate the units, so two shelves in a room are not one stamp (Z74)
            if rng.random() < 0.7:
                continue
        (lx, ly, _lz), (hx, hy, hz) = _model_box(unit)
        w, d = hx - lx, hy - ly
        # the unit's long side (its x) runs along the wall, its back 2 off it
        yaw = (spot.yaw - 90.0) % 360.0
        a = math.radians(spot.yaw)
        cx = spot.x + math.cos(a) * (d / 2.0 + 2.0)
        cy = spot.y + math.sin(a) * (d / 2.0 + 2.0)
        along_x = round(yaw) % 180 == 0
        ex, ey = (w / 2.0, d / 2.0) if along_x else (d / 2.0, w / 2.0)
        if any(abs(cx - mx) < ex + mx_e + gap and abs(cy - my) < ey + my_e + gap
               for mx, my, mx_e, my_e in made):
            continue
        if not placer.fits_box(rid, Bounds.between((cx - ex, cy - ey, f), (cx + ex, cy + ey, f + 8.0))):
            continue
        # origin from the box centre (the models are near-centred, not exactly)
        mx0, my0 = (lx + hx) / 2.0, (ly + hy) / 2.0
        c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        ox, oy = cx - (mx0 * c - my0 * s_), cy - (mx0 * s_ + my0 * c)
        placer.put(rid, unit, ox, oy, f, yaw, 1.0, True)
        n += 1
        tops = shelf_boards(unit, f)
        # some of each shelf already taken, a different share per unit
        keep_share = rng.uniform(0.7, 0.95)
        plan = Bounds.between((cx - ex + (2.5 if along_x else 2.0), cy - ey + (2.0 if along_x else 2.5), 0.0),
                              (cx + ex - (2.5 if along_x else 2.0), cy + ey - (2.0 if along_x else 2.5), 1.0))
        for k, top in enumerate(tops):
            room_above = (tops[k + 1] - top - 1.5) if k + 1 < len(tops) else 24.0
            # the top board is its roof: things stand on it only if the room is tall enough
            if k + 1 == len(tops) and room.interior.maxs.z - top < 60.0:
                continue
            for p in fill_board(rng, palette, plan, top, max_height=room_above):
                if rng.random() > keep_share:
                    continue
                placer.put(rid, p.model, p.x, p.y, p.surface, p.yaw, p.scale, False)
                n += 1
        placer.reserve(rid, Bounds.between((cx - ex - 4, cy - ey - 4, f), (cx + ex + 4, cy + ey + 4, f + hz)))
        made.append((cx, cy, ex, ey))
        last = unit
    return n


#: Flat-topped furniture a room's things pile onto: model-name words, and
#: the words that rule a model out (a seat, a bed, a shelf's own boards).
SURFACE_WORDS = ("desk", "table", "cabinet", "counter", "crate", "file_cab", "locker", "dresser",
                 "workbench", "cart", "trunk", "box_wood", "container_cardboard")
NOT_SURFACE = ("chair", "bed", "shelf", "drawer", "door", "light", "sink", "stool", "bench_modern",
               "_lid", "sofa", "couch")


def load_surfaces(bp, room, rng: random.Random, *, stock: str | Sequence[tuple[str, int]] = "office",
                  ident: str, share: float = 0.7, low: float = 20.0, high: float = 60.0,
                  most: int | None = None) -> int:
    """Pile the tops of *room*'s flat furniture (desks, tables, cabinets,
    crates: :data:`SURFACE_WORDS`, top *low*-*high* over the floor, square
    to the room) with *stock* (a :data:`SHELF_STOCK` key or palette), packed
    in runs by :func:`~zmforge.dressing.interior.fill_board`, off whatever
    already stands on each top, *share* of the pieces kept so a top reads
    used rather than tiled.  A room placed a desk with a mug on it; a room
    left in a hurry has the desk buried.  Returns how many props it placed
    (up to *most*)."""
    from ..spatial import Point
    from .interior import fill_board
    from .place import _placed_props, turned_box

    palette = SHELF_STOCK[stock] if isinstance(stock, str) else tuple(stock)
    b, f = room.interior, room.floor_z
    placed = list(_placed_props(bp))
    inside = [(p, pl) for p, pl in placed
              if b.mins.x - 1 <= p.origin.x <= b.maxs.x + 1 and b.mins.y - 1 <= p.origin.y <= b.maxs.y + 1]
    items: list[tuple] = []
    for p, pl in inside:
        name = p.model.lower()
        if not pl.solid or not any(w in name for w in SURFACE_WORDS) or any(w in name for w in NOT_SURFACE):
            continue
        top = pl.z_high
        if not (f + low <= top <= f + high) or round(p.yaw) % 90 != 0 or pl.z_low > f + 4.0:
            continue
        x0, y0, x1, y1 = pl.footprint.bounds
        if min(x1 - x0, y1 - y0) < 14.0:
            continue
        # what already stands on this top (or hangs over it)
        taken = [q.footprint.bounds for _o, q in placed
                 if q is not pl and q.z_high > top + 0.5 and q.z_low < top + 40.0
                 and q.footprint.bounds[0] < x1 and q.footprint.bounds[2] > x0
                 and q.footprint.bounds[1] < y1 and q.footprint.bounds[3] > y0]
        plan = Bounds.between((x0 + 2.0, y0 + 2.0, 0.0), (x1 - 2.0, y1 - 2.0, 1.0))
        room_above = min(24.0, b.maxs.z - top - 4.0)
        for piece in fill_board(rng, palette, plan, top, max_height=room_above):
            bx0, by0, bx1, by1 = turned_box(piece.model, piece.yaw)
            fx0, fy0 = piece.x + bx0 * piece.scale, piece.y + by0 * piece.scale
            fx1, fy1 = piece.x + bx1 * piece.scale, piece.y + by1 * piece.scale
            if any(a < fx1 + 0.5 and c > fx0 - 0.5 and d < fy1 + 0.5 and e > fy0 - 0.5
                   for a, d, c, e in taken):
                continue
            if rng.random() > share:
                continue
            lo = _model_box(piece.model)[0]
            items.append((piece.model, Point(piece.x, piece.y, piece.surface - lo[2] * piece.scale),
                          piece.yaw, piece.scale, False))
            taken.append((fx0, fy0, fx1, fy1))
            if most is not None and len(items) >= most:
                break
        if most is not None and len(items) >= most:
            break
    for k in range(0, len(items), 40):
        bp.place_props(items[k:k + 40], id=f"{ident}_{k // 40}")
    return len(items)


#: Stacked stores: the crates and archive boxes a building being emptied
#: piles by the walls (``interior.stack_clump``'s base, tops and skirt).
STORES = {
    "base": (("p7_crate_wood_01_short", 3), ("p7_container_cardboard_box_01", 3), ("p7_crate_wood_01", 1),
             ("p7_zm_der_magic_box_fake_trunk", 1)),
    "tops": (("p7_box_wood_01_sm", 3), ("p7_box_wood_wine_storage_tan", 2), ("p7_book_vintage_05", 2),
             ("p7_books_office_row_01", 1)),
    "skirt": (("p7_box_wood_01_sm", 2), ("p7_book_vintage_01", 2), ("p7_box_wood_wine_storage", 1),
              ("p7_box_wood_01_long", 2)),
}


def stacked_stores(bp, room, placer: RoomPlacer, rng: random.Random, *, count: int, ident: str,
                   stores: dict = STORES, gap: float = 110.0, open_floor: bool = True) -> int:
    """Up to *count* heaps of stacked crates and boxes that climb
    (``interior.stack_clump``: a base, often a second on it, small things on
    top, a skirt round its foot), along the walls first and then, with
    *open_floor*, on clear floor, *gap* apart, each through *placer* (a base
    that does not fit drops the whole heap; a skirt piece that does not fit
    is left out).  Call ``placer.flush()`` after.  Returns props placed."""
    from .interior import stack_clump
    from .place import turned_box

    rid = getattr(room, "id", "room")
    f = room.floor_z
    spots = [(sp.x + math.cos(math.radians(sp.yaw)) * 36.0, sp.y + math.sin(math.radians(sp.yaw)) * 36.0)
             for sp in wall_spots(room, placer, width=72.0, depth=72.0, step=24.0)]
    rng.shuffle(spots)
    if open_floor:
        more = [(sp.x, sp.y) for sp in floor_spots(room, placer, width=72.0, depth=72.0, step=32.0)
                if sp.yaw == 0.0]
        rng.shuffle(more)
        spots += more
    done: list[tuple[float, float]] = []
    n = 0
    for x, y in spots:
        if len(done) >= count:
            break
        if any(math.hypot(x - a, y - b) < gap for a, b in done):
            continue
        pieces = stack_clump(rng, x, y, f, base=stores["base"], tops=stores["tops"],
                             skirt=stores["skirt"], second=0.6, on_top=(1, 2), skirt_n=(2, 4),
                             yaw=rng.choice((0.0, 90.0)) + rng.uniform(-8.0, 8.0))
        base = pieces[0]
        if not placer.fits(rid, base.model, base.x, base.y, base.surface, base.yaw, base.scale, True):
            continue
        keep = []
        for k, p in enumerate(pieces):
            on_floor = abs(p.surface - f) < 0.5
            if k == 0 or not on_floor:
                keep.append((p, k == 0 or (k == 1 and not on_floor and p.model in dict(stores["base"]))))
            elif placer.fits(rid, p.model, p.x, p.y, p.surface, p.yaw, p.scale, False):
                keep.append((p, False))
        for p, solid in keep:
            placer.put(rid, p.model, p.x, p.y, p.surface, p.yaw, p.scale, solid)
            n += 1
        bx0, by0, bx1, by1 = turned_box(base.model, base.yaw)
        placer.reserve(rid, Bounds.between((base.x + bx0 - 4, base.y + by0 - 4, f),
                                           (base.x + bx1 + 4, base.y + by1 + 4, f + 64.0)))
        done.append((x, y))
    return n
