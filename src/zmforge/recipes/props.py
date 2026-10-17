"""Set dressing: the half of a room that is models rather than geometry.

A generated room used to be a textured box with four cover blocks in it, and
it read as a test level because that is what it was.  This module is the
other half: several hundred stock models per floor, placed by rule rather
than one call at a time, so a room's dressing is a paragraph of data instead
of two hundred lines of coordinates.

**Where the names come from.**  Every model name in :data:`PALETTE` is in the
union of ``xmodels_declared`` and ``misc_model_ok`` in
``blueprint/installed_assets.json`` -- the ledger of what the mod tools
install actually resolves, measured in that install -- and the size and
triangle count beside it are measured from each model's converted geometry
in the same install.  Neither is a guess and neither is a shipped map
source: a shipped map source is not proof an asset exists
(``zombie_sign_please_wait``, :mod:`zmforge.blueprint.installed`).  Check
``Z13`` re-checks every name against the ledger at generate time.

One theme is the exception, and it is an exception of provenance rather than of
rigour: ``zmforge_kit`` holds the models **this project builds itself**
from public-domain packs (:mod:`zmforge.props.library`).  The install has never
seen them, so no ledger can vouch for them; what vouches for them is that the
same repository converts the mesh, cuts the bullet mesh and the collmap from
it, and registers the asset, and that ``Z21`` refuses a placement whose
collision disagrees with the library.

**What is solid and what is not.**  Set dressing used to be walk-through by
construction: every model went out as a ``misc_model`` carrying
``no_collmap "1"``, so the player crossed a room straight through its
furniture.  Now :func:`is_solid` decides, from each model's own measured size,
whether it stops the player -- a filing cabinet does, a sheet of paper does
not -- and a solid one goes out with ``use_collmap "1"`` and a collmap to
bake.  :data:`SOLID_OVERRIDE` is where judgement overrules the measurement by
name, and ``solid=`` on a :class:`One`, :class:`Row` or :class:`Fill`
overrules both for one placement.

**So a badly placed model is no longer merely ugly.**  Collision can block a
doorway, narrow a corridor below what the navmesh generator will lay, or seal
a route, which is why every solid piece is fitted inside its room by its
circumscribed radius before it is kept, and why the check suite is worth
re-running after any change here.

**The bar.**  A shipped Treyarch interior of about 600 x 810 units --
``zm_giant_warehouse_office.map``, counted recursively through its own nested
prefabs -- holds 1,101 ``misc_model`` entities, i.e. roughly 2,300 per
million square units, and ``zm_giant`` as a whole averages about 700 per
million.  Most of that is architectural trim rather than furniture.  The
dressing aims at the whole-map figure rather than the single-room one, because
the triangle ceiling is shared: ``MAX_MAP_TRIANGLES`` is 3,072,000, and
:func:`triangle_budget` adds the palette up so the number is known before the
compiler counts it rather than after.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import chain
from typing import Mapping, Sequence

from ..blueprint.catalogue import ROUTE_MODELS, ROUTE_WORDS, is_route_model
from ..blueprint.model import Blueprint
from ..placement.geometry import Poly2, convex_hull
from ..placement.relations import (
    HangsFrom,
    MountKind,
    NoOverlap,
    OnWall,
    Placed,
    Wall,
    mount_kind_of_box,
    walls_of_rect,
)
from ..placement.scatter import KeepClear, Negatives
from ..props.origins import drawn_boxes
from ..solids.halfspace import plane_through
from ..spatial import Point

__all__ = [
    "MAX_MAP_TRIANGLES",
    "PALETTE",
    "MODEL_BOX",
    "CATALOGUE_BOX",
    "SEAT_TOP",
    "SHELF_BOARDS",
    "shelf_boards",
    "PLAN_BOX",
    "is_solid",
    "SOLID_OVERRIDE",
    "KIT",
    "KIT_SOLID",
    "is_route_model",
    "is_panel_model",
    "is_strewable",
    "is_rubble",
    "LITTER_FAMILIES",
    "is_litter",
    "mount_kind",
    "MOUNT_FLOOR",
    "MOUNT_WALL",
    "MOUNT_CEILING",
    "ROUTE_MODELS",
    "ROUTE_WORDS",
    "Row",
    "Fill",
    "One",
    "Scene",
    "furnish",
    "triangle_budget",
]


#: The compiler's own ceiling, as it prints it: ``MAX_MAP_TRIANGLES (3072000)
#: exceeded``.  Reported in community threads
#: that hit it; nothing in ``verify/`` holds a map-wide bound, so a recipe
#: that dresses heavily has to hold its own.
MAX_MAP_TRIANGLES = 3_072_000


# --------------------------------------------------------------------------
# The palette
# --------------------------------------------------------------------------
#: Theme -> models, each ``(name, (dx, dy, dz), triangles)``.
#:
#: Sizes are the model's own bounding box in game units with its origin at
#: its local zero, so ``dz`` is how tall a thing standing on the floor is and
#: the two horizontal numbers are its footprint.  They are here so a scene can
#: be written against real sizes: a shelf 113 units long wants a 113-unit
#: gap, and a mug is 4 units and can go on a desk.
PALETTE: Mapping[str, tuple[tuple[str, tuple[float, float, float], int], ...]] = {
    "lobby_reception": (
        ("p7_bench_modern_01", (80, 18, 24), 696),
        ("p7_chair_waiting_room_01_blue", (22.3, 26.2, 34.9), 2306),
        ("p7_chair_wood_fancy_01", (20.4, 24.9, 38.8), 2256),
        ("p7_desk_metal_old_01_body", (74.6, 36, 34), 3950),
        ("p7_3arc_lobby_plant", (46.9, 45.9, 37.2), 1704),
        ("p7_3arc_park_pylon", (12, 12, 30), 1088),
        ("p7_luggage_hardshell_handle_down_white", (21.5, 11.8, 39.2), 3337),
        ("p7_luggage_cloth_a_lg_green", (22.3, 16.4, 33), 2952),
    ),
    "queue_signage": (
        ("p7_signage_caution_biohazard_01", (28, 0.3, 28), 140),
        ("p7_signage_caution_exit", (28, 0.2, 7), 140),
        ("p7_signage_loading_zone_01", (28, 0.2, 18), 140),
        ("p7_zm_der_signage_employees_only", (10, 0.7, 5), 300),
        ("p7_zm_der_signage_no_smoking", (10, 0.7, 5), 300),
        ("p7_zm_der2_bulletin_board", (61.9, 2.2, 36.2), 1106),
        ("p7_clock_metal_wall_01_base", (32, 5.8, 32), 1708),
        ("p7_picture_frame_modern_01", (28.5, 1, 34.5), 26),
    ),
    "records_archive": (
        ("p7_shelf_metal_lab_01", (113.3, 31.5, 97), 2585),
        ("p7_shelf_industrial_vintage_96", (99.5, 34.1, 85.7), 9284),
        ("p7_zm_der_cabinet_lab_bottom", (108, 32, 36), 1462),
        ("p7_zm_der_cabinet_lab_top", (91, 18, 39), 1342),
        ("p7_books_office_row_01", (11.8, 12.1, 14), 1114),
        ("p7_book_vintage_open_01", (11.3, 19.8, 2.1), 645),
        ("p7_crate_wood_01", (60.5, 30.7, 31), 384),
        ("p7_cai_stacking_cargo_crate", (64, 64, 48.2), 3897),
        ("p7_zm_der_teleporter_mf_ladder", (29.9, 6.4, 50.7), 1056),
        ("p7_office_paper_stack_sml", (15.7, 19.4, 5.3), 76),
    ),
    "bunk_room": (
        ("p7_bunkbed", (64.5, 96.1, 110.2), 5466),
        ("p7_bunkbed_cubicle", (64.5, 96.1, 110.2), 2702),
        ("p7_bed_mattress_barrack", (47, 85.7, 6.3), 2448),
        ("p7_bed_mattress_barrack_made_v2", (50.3, 93.3, 9.1), 1906),
        ("p7_bed_pillow_barrack", (35.4, 20.5, 6.9), 1121),
        ("p7_bed_sheet_barrack_02", (49.9, 59.3, 8.7), 1625),
        ("p7_global_chainlink_fence_metal_base", (9.9, 9.9, 10), 430),
        ("p7_global_chainlink_fence_rail_end", (9.1, 4.1, 3.1), 722),
    ),
    "tall_hall": (
        ("p7_rebar_column_128", (12.6, 12.7, 129.9), 5248),
        ("p7_zm_der_teleporter_mf_int_column", (22.2, 17.3, 140.5), 3822),
        ("p7_cai_planter_rectangle", (144, 68.1, 60.5), 1584),
        ("p7_pallet_metal_military_01", (132.1, 70.1, 12), 2766),
        ("p7_cai_stacking_cargo_crate", (64, 64, 48.2), 3897),
        ("p7_grating_metal_01_panel", (16, 32, 1), 1272),
        ("p7_cai_staircase_01", (109, 191.5, 131.5), 1236),
        ("p7_light_chandelier_hologram", (73.9, 72.6, 18.7), 3180),
        ("p7_light_hanging_modern_02", (59.6, 60.9, 32.6), 904),
        ("p7_pallet_wood_damaged", (48, 40.2, 5.1), 1094),
    ),
    "cafeteria": (
        ("p7_cai_work_table_metal_03_white", (21.2, 81.1, 36), 3328),
        ("p7_sgen_chair_dining_future", (35.3, 26.9, 41.1), 792),
        ("p7_cup_coffee_mug", (4.4, 2.9, 3.5), 762),
        ("p7_debris_trash_paper_plate_01", (9.3, 9.3, 0.3), 284),
        ("p7_bottle_glass_wine_01", (3.2, 3.2, 12.7), 1124),
        ("p7_food_fruit_banana_bunch", (9.8, 10.6, 5), 3264),
        ("p7_food_fruit_watermelon", (10.9, 10.9, 12.6), 1456),
        ("p7_water_cooler_digital_body", (17.7, 15.3, 49.2), 1570),
        ("p7_cai_fridge_metal_plant", (24, 48, 84), 1102),
    ),
    "kitchen": (
        ("p7_kitchen_cabinets_modern", (168, 166, 112), 2169),
        ("p7_sink_kitchen_stainless_modern_01_clean", (44.6, 26.2, 11), 256),
        ("p7_cai_fridge_metal_plant", (24.3, 48, 84.1), 1102),
        ("p7_pan_metal_sauce", (16.1, 11.2, 6), 1160),
        ("p7_pan_metal_lid", (10.2, 10.2, 1.7), 728),
        ("p7_pot_metal_boiling_lg", (14.8, 12.4, 10), 2328),
        ("p7_crate_wood_01", (60.5, 30.7, 31), 384),
        ("p7_coffee_maker_digital_pot", (10.6, 7.6, 7.3), 5150),
    ),
    "machinery": (
        ("p7_pipe_metal_hp_12_straight_64_bare", (18, 18, 64), 700),
        ("p7_pipe_metal_hp_12_elbow_90_bare", (25, 18, 25), 924),
        ("p7_pipe_metal_hp_12_valve_01_bare", (36.5, 19.7, 32), 3744),
        ("p7_pipe_metal_water_valve", (4.3, 5, 8), 2452),
        ("p7_tank_nitrogen_metal", (18, 18, 50.6), 1574),
        ("p7_generator_large_01_housing_rusted", (171.3, 179.3, 89.7), 6268),
        ("p7_zm_der_generator_01", (88, 78, 73), 5634),
        ("p7_electrical_box_tall_red", (42.1, 17.2, 77), 3409),
        ("p7_electrical_box_set2_box02", (16.8, 11.4, 30.9), 1098),
        ("p7_conduit_metal_2_straight_64", (2, 2, 64), 96),
        ("p7_barrel_metal_55gal_blue", (23.6, 23.6, 34.6), 1628),
    ),
    "storeroom": (
        ("p7_shelf_metal_lab_01", (113.3, 31.5, 97), 2585),
        ("p7_zm_der_cabinet_lab_top", (91, 18, 39), 1342),
        ("p7_container_cardboard_box_01", (38.5, 27.6, 25.3), 1044),
        ("p7_crate_wood_01_short", (30.9, 30.1, 31), 384),
        ("p7_crate_plastic_tech_01", (29.2, 62.9, 26), 4618),
        ("p7_zm_der_teleporter_mf_ladder", (29.9, 6.4, 50.7), 1056),
        ("p7_office_paper_stack_sml", (15.7, 19.4, 5.3), 76),
        ("p7_books_office_row_01", (11.8, 12.1, 14), 1114),
    ),
    "meeting_room": (
        ("p7_cai_table_hydroponic_01", (191.5, 29, 49), 4416),
        ("p7_chair_wood_fancy_01", (20.4, 24.9, 38.8), 2256),
        ("p7_zm_der_chalkboard_vintage", (76.1, 26, 72), 1548),
        ("p7_cup_coffee_mug", (4.4, 2.9, 3.5), 762),
        ("p7_office_paper_folder_blue", (13, 10.1, 0.2), 114),
        ("p7_book_office_binder_open", (14, 26, 1.3), 628),
        ("p7_water_cooler_digital_body", (17.7, 15.3, 49.2), 1570),
        ("p7_clock_metal_wall_01_base", (32, 5.8, 32), 1708),
    ),
    "offices": (
        ("p7_desk_metal_military_02", (90, 37, 36), 6556),
        ("p7_desk_metal_old_01_body", (74.6, 36, 34), 3950),
        ("p7_chair_lab_01", (35.5, 33.8, 58.6), 3886),
        ("p7_consumer_grade_monitor_medium", (61.5, 6.6, 31.3), 2804),
        ("p7_keyboard_metal_tech", (48, 8.8, 11.9), 604),
        ("p7_zm_der2_light_hurricane_lamp", (12.8, 11.5, 26.5), 2732),
        ("p7_trashcan_metal_modern_glass", (33, 33, 48.3), 2804),
        ("p7_foliage_plant_aloe_small", (28.8, 31.9, 15.8), 1482),
        ("p7_desk_metal_old_01_drawer_small_01", (15.5, 18.9, 7.1), 278),
        ("p7_office_paper_stack_sml", (15.7, 19.4, 5.3), 76),
    ),
    "yard_outdoor": (
        ("p7_foliage_grass_tall_cluster_med", (68, 111, 60.5), 356),
        ("p7_foliage_weed_cluster_lrg", (16.9, 5.1, 6.8), 744),
        ("p7_foliage_tree_acacia_bush", (82.2, 64, 45.4), 2332),
        ("p7_foliage_hedge_box_48_48_36", (53, 59.7, 43.3), 2400),
        ("p7_foliage_palm_lipstick_sml", (57.5, 54.1, 49.6), 1148),
        ("p7_rock_sing_park_06", (85.6, 60.6, 31.3), 744),
        ("p7_cai_planter_square", (42, 50.1, 44.5), 1172),
        ("p7_sandbag_02", (20, 35.5, 9.7), 1276),
        ("p7_bench_modern_01", (80, 18, 24), 696),
        ("p7_pallet_wood_damaged", (48, 40.2, 5.1), 1094),
        ("p7_wheel_barrow_street_vendor", (34.4, 70, 39.2), 4646),
        ("p7_tools_shovel", (11.6, 59.4, 8.5), 718),
    ),
    "utility_tunnel": (
        ("p7_pipe_metal_hp_4_straight_32_bare", (6, 6, 32), 464),
        ("p7_conduit_metal_2_straight_32", (2, 2, 32), 96),
        ("p7_light_fixture_led_wall_01", (9.4, 64, 15), 1328),
        ("p7_grating_metal_01_panel", (16, 32, 1), 1272),
        ("p7_duct_metal_circular_straight_32", (32, 33.1, 33.1), 896),
        ("p7_pipe_metal_water_valve", (4.3, 5, 8), 2452),
        ("p7_debris_rockychunks_small_08", (15, 15.1, 12.3), 48),
    ),
    "rooftop": (
        ("p7_ac_unit_large", (79.2, 53.5, 38), 4313),
        ("p7_ac_unit_wall_mount_01", (36.2, 24.8, 25.2), 982),
        ("p7_duct_metal_circular_vent", (2.4, 33.1, 33.1), 1396),
        ("p6_antenna_rooftop", (42.1, 48.6, 130.5), 476),
        ("p7_cell_antenna_roof", (53.4, 53.4, 182), 7850),
        ("p7_sandbag_02", (20, 35.5, 9.7), 1276),
        ("p7_street_manhole_cover_cairo_01", (34.4, 34.5, 0.9), 252),
    ),
    "clutter_small": (
        ("p7_debris_newspaper_01", (40.4, 35.4, 2.3), 235),
        ("p7_debris_newspaper_04", (27.2, 37.5, 1.4), 1006),
        ("p7_debris_trash_paper_02", (6.4, 9.3, 2.2), 228),
        ("p7_debris_trash_paper_08", (9.8, 7.8, 1.8), 248),
        ("p7_bottle_glass_liquor_01", (5.1, 3.3, 12.3), 262),
        ("p7_bottle_glass_liquor_03", (3.4, 3.4, 12.5), 416),
        ("p7_debris_trash_cup_coffee_02", (4.2, 6.2, 3.2), 178),
        ("p7_debris_trash_cup_red_02", (4.3, 4.3, 1), 96),
        ("p7_debris_rockychunks_small_05", (23.8, 11.4, 7.1), 50),
        ("p7_debris_rockychunks_small_10", (14.7, 12.5, 7.4), 32),
        ("p7_cleaning_paper_folded_wrapped", (3.5, 9.9, 6.5), 490),
        ("p7_debris_trash_paper_plate_01", (9.3, 9.3, 0.3), 284),
    ),
    "rubble_debris": (
        ("p7_debris_concrete_rubble_med_01_no_metal", (61.6, 42.7, 30.7), 1628),
        ("p7_debris_concrete_rubble_sm_02", (10.2, 11.4, 14.1), 188),
        ("p7_debris_concrete_rubble_pile_02", (107.6, 70.7, 37.7), 7177),
        ("p7_debris_brick_chunk_01", (4.1, 3.9, 2.4), 264),
        ("p7_debris_brick_single_01", (8, 4, 2.4), 216),
        ("p7_brick_dirty_breakout_05", (27.4, 28.3, 59.9), 1874),
        ("p7_debris_plaster_rubble_med_01", (1, 23.9, 22.2), 1300),
        ("p7_debris_plaster_rubble_med_02", (1, 20.9, 31.8), 2440),
        ("p7_debris_wood_board_splinter_01", (18.1, 15, 1.6), 240),
        ("p7_debris_wood_board_cluster_01", (40.6, 41, 4.1), 766),
    ),
    # The one theme in here that is not Treyarch's.  The models this project
    # converts itself from public-domain packs (:mod:`zmforge.props.library`
    # names the pack, the file and the licence for each, and
    # the prop install step builds and registers them).  Sizes and triangle
    # counts are measured off the converted mesh, not off the install's
    # catalogue, because the install has never seen these.
    #
    # **Deal these out by hand, never by Row or Fill.**  Six props is a kit,
    # not a palette: strewn at random they read as six jokes dropped on the
    # floor.  Every one is
    # placed by a :class:`One` in the scene for the room it belongs in, on a
    # surface the recipe's own brushwork owns.
    "zmforge_kit": (
        ("zmf_prop_donut", (7.8, 9, 3), 360),
        ("zmf_prop_birthday_cake", (14, 14, 8), 1146),
        ("zmf_prop_lollipop", (1.8, 8.9, 18), 216),
        ("zmf_prop_roast_turkey", (15, 10.9, 6), 544),
        ("zmf_prop_teddy_bear", (17.3, 11, 20), 268),
        ("zmf_prop_toilet", (18.3, 28, 26.5), 440),
        # Halloween set (Kenney Graveyard, Nature and Car kits,
        # all CC0).  Appended, never inserted, so KIT indices stay put.
        ("zmf_prop_pumpkin", (16, 16, 13.6), 696),
        ("zmf_prop_jack_o_lantern", (16, 16, 13.6), 972),
        ("zmf_prop_jack_o_lantern_tall", (16.3, 16.3, 18), 920),
        ("zmf_prop_hay_bale", (40, 26.5, 23.4), 3956),  # generated bale
        ("zmf_prop_gravestone_round", (26.6, 14.8, 34), 356),
        ("zmf_prop_gravestone_cross", (23.6, 17.3, 48), 444),
        ("zmf_prop_gravestone_broken", (26, 20, 17.4), 268),
        ("zmf_prop_wooden_cross", (32.1, 32.1, 78), 252),
        ("zmf_prop_fence_wood", (64, 11.8, 39.7), 864),
        ("zmf_prop_fence_iron", (64, 7, 56.2), 752),
        ("zmf_prop_corn_stalk", (33.9, 33.9, 96), 412),  # generated
        ("zmf_prop_corn_stalk_thin", (21.9, 21.9, 90), 338),  # generated
        ("zmf_prop_tractor", (91.4, 150, 109.2), 2044),
        ("zmf_prop_hay_bale_stack", (40, 28.4, 25), 4220),  # generated bale
        ("zmf_prop_hand_cart", (40, 60, 24), 832),
        # Poly Haven CC0 photoscans, decimated on import.
        ("zmf_prop_dead_log", (120, 10.9, 11.4), 11999),
        ("zmf_prop_tree_stump", (56.3, 62.9, 22.7), 9999),
        ("zmf_prop_wooden_crate", (20.9, 46, 18.3), 5176),
        # Generated dead trees (props/dead_tree.py) (second pass).
        ("zmf_prop_dead_tree_a", (226, 226, 300), 1543),
        ("zmf_prop_dead_tree_b", (190, 190, 270), 1315),
        ("zmf_prop_dead_tree_c", (218, 218, 330), 1481),
        ("zmf_prop_dead_tree_d", (260, 260, 400), 1625),
        ("zmf_prop_dead_tree_e", (284, 284, 440), 1899),
        ("zmf_prop_gamble_atm", (44, 36, 90.9), 9206),  # generated cash machine
    ),
}

#: Index of each kit prop in the ``zmforge_kit`` theme, so a scene names the
#: prop rather than a number.  :class:`One` addresses a theme by position, and
#: ``One("zmforge_kit", 5, ...)`` says nothing about what is being placed.
KIT = {name: index for index, (name, _size, _tris) in enumerate(PALETTE["zmforge_kit"])}


#: Each model's own bounding box in its local frame, ``(mins, maxs)``,
#: measured from each model's converted geometry in the mod tools install.  It is the source of both :data:`PLAN_BOX` (where a
#: model's geometry sits relative to its origin) and the collision box
#: generated for a solid prop, so the two can never disagree.
#:
#: **A stock model's origin is not its centre.**  Measured across this
#: palette: 51 of the 129 models carry their geometry off to one
#: side of the origin, and some of them a long way -- the bounding box of
#: ``p7_duct_metal_circular_vent`` sits 217 units from its origin, and
#: ``p7_cai_watertank_body`` is a quarter-tank authored into the corner of a
#: 132 x 132 footprint.  Placing by origin therefore draws the model
#: somewhere other than where the scene asked for it, and an inset computed
#: as half the footprint is wrong by the same amount.
#:
#: That is not a cosmetic bug.  A 132-unit tank placed 14 units off a
#: 16-unit wall reached 187 units from its origin, straight
#: through the wall and into the void, and ``cod2map64`` answered
#: ``******* leaked *******`` and wrote a leakfile whose trace ended on that
#: model's exact x and y.  Bisecting 24 scenes to 1, 8 items to 2 and 12
#: models to 1 found it; the map compiled clean the moment it was placed by
#: its centre instead.
#: One model is deliberately absent from :data:`PALETTE` and kept here, so
#: that nobody re-adds it: ``p7_cai_watertank_body`` **leaks the map**.  Alone,
#: on open floor in the middle of a sealed room, 190 units from the nearest
#: wall, ``cod2map64`` answers ``******* leaked *******`` and writes a leakfile
#: whose trace ends on that model's own x and y; the same map without it
#: compiles exit 0 with no banner.  It is not a placement problem -- it was
#: tried at five positions and at two heights, and the only clean one was on
#: a staircase with 48 more units of solid under it, which says its collision
#: reaches below an origin its visible bounding box starts at.  It is a
#: quarter-tank (the install's own file is ``..._body_quarter_LOD0``), so the
#: part is probably meant to be assembled four to a tank on a base rather than
#: stood on a floor by itself.  Twelve other boiler models do the same job.
#: Two further models are absent for a duller reason: ``p6_bar_beer_glass``
#: and ``p7_wires_electrical_rubber_02`` are declared by the mod tools but their
#: ``model_export`` folders are missing from the tools tree this palette was
#: checked against, and the linker will not pack a model whose binary it
#: cannot open.  In a tools tree that has them, they can go back.
#: The raw catalogue boxes, in each model's authored scene frame.  Recipes and
#: checks read :data:`MODEL_BOX`, which is this table moved into the frame the
#: engine draws the model in (see :mod:`zmforge.props.origins`).
CATALOGUE_BOX: Mapping[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "p6_antenna_rooftop": ((-14.616, -24.316, 0.0), (27.5, 24.316, 130.5)),
    "p6_bar_beer_glass": ((-1.995, -2.001, 0.0), (1.995, 1.995, 7.0)),
    "p7_3arc_lobby_plant": ((-25.27, -22.954, -0.0), (21.585, 22.974, 37.179)),
    "p7_3arc_park_pylon": ((-6.0, -6.0, 0.0), (6.0, 6.0, 30.0)),
    "p7_ac_unit_large": ((-39.25, -31.504, 0.027), (39.994, 21.951, 38.034)),
    "p7_ac_unit_wall_mount_01": ((-18.078, -24.799, -12.75), (18.076, 0.008, 12.482)),
    "p7_barrel_metal_55gal_blue": ((-11.788, -11.832, 0.0), (11.788, 11.788, 34.618)),
    "p7_bed_mattress_barrack": ((-23.628, -42.728, -3.364), (23.392, 42.935, 2.937)),
    "p7_bed_mattress_barrack_made_v2": ((-25.183, -46.821, 0.599), (25.081, 46.472, 9.695)),
    "p7_bed_pillow_barrack": ((-18.475, -9.501, -2.804), (16.937, 11.025, 4.112)),
    "p7_bed_sheet_barrack_02": ((-24.228, -15.093, -4.469), (25.674, 44.194, 4.266)),
    "p7_bench_modern_01": ((-40.0, -9.016, -0.0), (40.0, 9.016, 24.0)),
    "p7_book_office_binder_open": ((-6.999, -12.979, 0.014), (6.999, 12.979, 1.333)),
    "p7_book_vintage_open_01": ((-5.649, -9.884, 0.0), (5.649, 9.884, 2.129)),
    "p7_books_office_row_01": ((-5.859, -6.039, 0.0), (5.921, 6.033, 14.016)),
    "p7_bottle_glass_liquor_01": ((-2.535, -1.654, 0.046), (2.535, 1.654, 12.323)),
    "p7_bottle_glass_liquor_03": ((-1.694, -1.694, -0.0), (1.694, 1.694, 12.517)),
    "p7_bottle_glass_wine_01": ((-1.575, -1.575, 0.0), (1.575, 1.575, 12.665)),
    "p7_brick_dirty_breakout_05": ((-25.895, -1.855, 0.0), (1.494, 26.441, 59.897)),
    "p7_bunkbed": ((-64.544, -0.0, 0.016), (0.0, 96.122, 110.211)),
    "p7_bunkbed_cubicle": ((-64.544, -0.0, 0.016), (0.0, 96.122, 110.211)),
    "p7_cai_fridge_metal_plant": ((-0.0, -24.0, -0.085), (24.324, 24.0, 84.0)),
    "p7_cai_planter_rectangle": ((-72.0, -34.125, 0.0), (72.0, 34.0, 60.5)),
    "p7_cai_planter_square": ((-21.0, -25.125, -0.0), (21.0, 25.0, 44.5)),
    "p7_cai_stacking_cargo_crate": ((-32.01, -32.0, 0.0), (32.01, 32.0, 48.208)),
    "p7_cai_staircase_01": ((-54.5, -0.75, 0.0), (54.5, 190.75, 131.5)),
    "p7_cai_table_hydroponic_01": ((-1.007, -29.0, 0.0), (190.5, 0.0, 49.0)),
    "p7_cai_watertank_body": ((-0.0, -132.0, -0.0), (132.0, -0.0, 254.0)),
    "p7_cai_work_table_metal_03_white": ((-10.634, -40.609, 0.01), (10.58, 40.528, 36.024)),
    "p7_cell_antenna_roof": ((-26.705, -26.705, 0.0), (26.705, 26.705, 181.995)),
    "p7_chair_lab_01": ((-17.771, -18.367, -0.034), (17.771, 15.392, 58.536)),
    "p7_chair_waiting_room_01_blue": ((-11.131, -12.579, -0.0), (11.131, 13.584, 34.865)),
    "p7_chair_wood_fancy_01": ((-10.2, -12.982, -0.0), (10.2, 11.939, 38.814)),
    "p7_cleaning_paper_folded_wrapped": ((-1.672, -4.871, -0.0), (1.803, 5.079, 6.486)),
    "p7_clock_metal_wall_01_base": ((-16.0, -3.759, -16.0), (16.0, 2.0, 16.0)),
    "p7_coffee_maker_digital_pot": ((-4.113, -3.798, -0.0), (6.448, 3.798, 7.282)),
    "p7_conduit_metal_2_straight_32": ((-1.0, -1.0, 0.0), (1.0, 1.0, 32.0)),
    "p7_conduit_metal_2_straight_64": ((-1.0, -1.0, 0.0), (1.0, 1.0, 64.0)),
    "p7_consumer_grade_monitor_medium": ((-164.708, 36.87, -0.0), (-103.17, 43.438, 31.3)),
    "p7_container_cardboard_box_01": ((-21.47, -10.585, 0.088), (17.052, 17.01, 25.383)),
    "p7_crate_plastic_tech_01": ((-14.839, -31.394, 0.036), (14.394, 31.5, 26.0)),
    "p7_crate_wood_01": ((-30.268, -15.358, 0.15), (30.268, 15.358, 31.18)),
    "p7_crate_wood_01_short": ((-15.437, -15.044, 0.15), (15.437, 15.044, 31.18)),
    "p7_cup_coffee_mug": ((-1.431, -1.456, 0.0), (2.969, 1.447, 3.468)),
    "p7_debris_brick_chunk_01": ((7.714, -1.041, -1.191), (11.791, 2.883, 1.191)),
    "p7_debris_brick_single_01": ((-27.239, -1.483, -1.19), (-19.242, 2.517, 1.19)),
    "p7_debris_concrete_rubble_med_01_no_metal": ((-35.231, -21.774, -15.368), (26.344, 20.956, 15.368)),
    "p7_debris_concrete_rubble_pile_02": ((-54.394, -66.133, -2.527), (53.245, 4.551, 35.2)),
    "p7_debris_concrete_rubble_sm_02": ((-5.106, -5.715, -7.043), (5.106, 5.715, 7.043)),
    "p7_debris_newspaper_01": ((-19.86, -16.124, -0.045), (20.49, 19.279, 2.245)),
    "p7_debris_newspaper_04": ((-18.077, -17.078, -0.031), (9.154, 20.465, 1.351)),
    "p7_debris_plaster_rubble_med_01": ((-0.483, -40.665, -11.097), (0.483, -16.746, 11.097)),
    "p7_debris_plaster_rubble_med_02": ((-0.483, -10.443, -15.918), (0.483, 10.443, 15.918)),
    "p7_debris_rockychunks_small_05": ((-11.92, -5.722, -3.546), (11.92, 5.722, 3.546)),
    "p7_debris_rockychunks_small_08": ((-7.49, -7.529, -6.165), (7.49, 7.529, 6.165)),
    "p7_debris_rockychunks_small_10": ((-7.352, -6.272, -3.685), (7.352, 6.272, 3.685)),
    "p7_debris_trash_cup_coffee_02": ((-2.106, -3.099, 0.026), (2.106, 3.099, 3.255)),
    "p7_debris_trash_cup_red_02": ((-2.129, -2.171, -0.004), (2.129, 2.171, 1.044)),
    "p7_debris_trash_paper_02": ((-3.202, -4.636, -0.045), (3.202, 4.636, 2.16)),
    "p7_debris_trash_paper_08": ((-4.913, -3.896, -0.076), (4.913, 3.896, 1.73)),
    "p7_debris_trash_paper_plate_01": ((-4.634, -4.634, 0.068), (4.634, 4.634, 0.41)),
    "p7_debris_wood_board_cluster_01": ((-20.308, -20.519, -2.05), (20.308, 20.519, 2.05)),
    "p7_debris_wood_board_splinter_01": ((-9.012, -5.144, -0.792), (9.134, 9.872, 0.823)),
    "p7_desk_metal_military_02": ((-45.0, -19.0, 0.0), (45.0, 18.0, 36.0)),
    "p7_desk_metal_old_01_body": ((-37.317, -18.0, 0.0), (37.317, 18.0, 34.0)),
    "p7_desk_metal_old_01_drawer_small_01": ((-7.757, -1.545, 0.0), (7.757, 17.321, 7.126)),
    "p7_duct_metal_circular_straight_32": ((-32.0, 133.435, -16.565), (0.0, 166.565, 16.565)),
    "p7_duct_metal_circular_vent": ((-1.0, -216.565, -16.565), (1.362, -183.435, 16.565)),
    "p7_electrical_box_set2_box02": ((-8.177, -11.38, -0.872), (8.615, 0.0, 30.035)),
    "p7_electrical_box_tall_red": ((-21.052, -0.0, -0.0), (21.052, 17.209, 77.002)),
    "p7_foliage_grass_tall_cluster_med": ((-32.262, -60.987, -1.845), (35.742, 50.058, 58.686)),
    "p7_foliage_hedge_box_48_48_36": ((-27.097, -29.269, -2.994), (25.883, 30.384, 40.322)),
    "p7_foliage_palm_lipstick_sml": ((-27.168, -24.578, -4.713), (30.305, 29.482, 44.844)),
    "p7_foliage_plant_aloe_small": ((-15.271, -14.771, -0.0), (13.521, 17.158, 15.848)),
    "p7_foliage_tree_acacia_bush": ((-39.47, -33.156, -1.437), (42.7, 30.842, 43.941)),
    "p7_foliage_weed_cluster_lrg": ((-8.427, -2.528, -0.68), (8.427, 2.528, 6.129)),
    "p7_food_fruit_banana_bunch": ((-4.907, -5.315, 0.0), (4.907, 5.315, 5.03)),
    "p7_food_fruit_watermelon": ((-5.483, -5.387, -0.0), (5.429, 5.498, 12.612)),
    "p7_generator_large_01_housing_rusted": ((-85.657, -89.674, -0.064), (85.657, 89.674, 89.674)),
    "p7_global_chainlink_fence_metal_base": ((-4.938, -4.938, -0.885), (4.938, 4.938, 9.092)),
    "p7_global_chainlink_fence_rail_end": ((-7.213, -2.023, -1.634), (1.917, 2.041, 1.494)),
    "p7_grating_metal_01_panel": ((-8.0, -16.0, 0.0), (8.0, 16.0, 1.0)),
    "p7_keyboard_metal_tech": ((-23.899, 0.0, -0.0), (24.101, 8.781, 11.886)),
    "p7_kitchen_cabinets_modern": ((0.0, -0.0, 0.0), (168.0, 166.0, 112.0)),
    "p7_light_chandelier_hologram": ((-36.941, -36.317, -18.657), (36.941, 36.317, 0.015)),
    "p7_light_fixture_led_wall_01": ((-0.003, -32.0, -7.5), (9.373, 32.001, 7.5)),
    "p7_light_hanging_modern_02": ((-29.002, -29.638, -32.582), (30.645, 31.31, -0.0)),
    "p7_luggage_cloth_a_lg_green": ((-11.865, -9.619, -0.178), (10.402, 6.773, 32.842)),
    "p7_luggage_hardshell_handle_down_white": ((-10.657, -7.087, 0.042), (10.797, 4.709, 39.202)),
    "p7_office_paper_folder_blue": ((-6.479, -5.045, 0.022), (6.499, 5.07, 0.199)),
    "p7_office_paper_stack_sml": ((-7.968, -10.153, -0.0), (7.776, 9.286, 5.338)),
    "p7_pallet_metal_military_01": ((-66.055, -35.055, -0.0), (66.055, 35.055, 12.0)),
    "p7_pallet_wood_damaged": ((-24.0, -20.088, -0.0), (24.0, 20.088, 5.122)),
    "p7_pan_metal_lid": ((-5.123, -5.123, 0.0), (5.123, 5.123, 1.734)),
    "p7_pan_metal_sauce": ((-8.055, -5.588, -0.0), (8.055, 5.588, 5.97)),
    "p7_picture_frame_modern_01": ((-14.25, -1.0, -17.25), (14.25, 0.0, 17.25)),
    "p7_pipe_metal_hp_12_elbow_90_bare": ((-9.0, -9.0, 0.0), (16.0, 9.0, 25.0)),
    "p7_pipe_metal_hp_12_straight_64_bare": ((-9.0, -9.0, 0.0), (9.0, 9.0, 64.0)),
    "p7_pipe_metal_hp_12_valve_01_bare": ((-27.497, -9.879, 0.0), (9.0, 9.812, 32.0)),
    "p7_pipe_metal_hp_4_straight_32_bare": ((-3.0, -3.0, -0.0), (3.0, 3.0, 32.0)),
    "p7_pipe_metal_water_valve": ((-2.157, -92.5, -1.835), (2.157, -87.5, 6.213)),
    "p7_pot_metal_boiling_lg": ((-7.42, -6.198, 0.0), (7.42, 6.198, 10.0)),
    "p7_rebar_column_128": ((-6.361, -6.398, -65.01), (6.259, 6.319, 64.916)),
    "p7_rock_sing_park_06": ((-44.02, -34.49, -17.651), (41.571, 26.09, 13.643)),
    "p7_sandbag_02": ((-9.955, -15.681, 0.041), (10.089, 19.782, 9.778)),
    "p7_sgen_chair_dining_future": ((-19.899, -13.45, -0.039), (15.362, 13.45, 41.088)),
    "p7_shelf_industrial_vintage_96": ((-49.769, -16.359, -0.0), (49.769, 17.722, 85.713)),
    "p7_shelf_metal_lab_01": ((-55.694, -16.784, 0.433), (57.603, 14.702, 97.472)),
    "p7_signage_caution_biohazard_01": ((-14.0, -0.25, -14.0), (14.0, 0.0, 14.0)),
    "p7_signage_caution_exit": ((-14.0, -0.25, -3.5), (14.0, 0.0, 3.5)),
    "p7_signage_loading_zone_01": ((-14.0, -0.25, -9.0), (14.0, 0.0, 9.0)),
    "p7_sink_kitchen_stainless_modern_01_clean": ((-22.321, -25.4, -11.746), (22.321, 0.771, -0.775)),
    "p7_street_manhole_cover_cairo_01": ((-17.147, -17.281, -0.347), (17.264, 17.178, 0.601)),
    "p7_tank_nitrogen_metal": ((-8.997, -8.997, -0.002), (8.997, 8.997, 50.626)),
    "p7_tools_shovel": ((-5.798, -31.991, -4.219), (5.798, 27.454, 4.283)),
    "p7_trashcan_metal_modern_glass": ((-16.5, -16.5, -0.0), (16.5, 16.5, 48.25)),
    "p7_water_cooler_digital_body": ((-8.805, -7.651, -0.0), (8.858, 7.651, 49.236)),
    "p7_wheel_barrow_street_vendor": ((-17.184, -34.342, -0.029), (17.184, 35.706, 39.126)),
    "p7_wires_electrical_rubber_02": ((-8.154, -0.084, -35.117), (6.96, 64.0, 3.821)),
    "p7_zm_der2_bulletin_board": ((-31.067, 0.001, -18.079), (30.832, 2.229, 18.079)),
    "p7_zm_der2_light_hurricane_lamp": ((-6.3, -5.755, 0.0), (6.531, 5.748, 26.459)),
    "p7_zm_der_cabinet_lab_bottom": ((-54.0, -16.5, -0.0), (54.0, 15.5, 36.0)),
    "p7_zm_der_cabinet_lab_top": ((-45.5, -9.0, -0.0), (45.5, 9.0, 39.0)),
    "p7_zm_der_chalkboard_vintage": ((-38.072, -12.985, -0.003), (38.072, 12.985, 72.007)),
    "p7_zm_der_generator_01": ((-44.0, -39.0, -0.0), (44.0, 39.0, 73.0)),
    "p7_zm_der_signage_employees_only": ((-5.0, -0.655, -2.504), (5.0, 0.0, 2.504)),
    "p7_zm_der_signage_no_smoking": ((-5.0, -0.655, -2.504), (5.0, 0.0, 2.504)),
    "p7_zm_der_teleporter_mf_int_column": ((-11.105, 62.655, 2.148), (11.105, 79.925, 142.647)),
    "p7_zm_der_teleporter_mf_ladder": ((-14.951, -83.372, 122.052), (14.951, -77.009, 172.73)),
    # ------------------------------------------------------------------
    # Office dressing for zm_dmv.  Read off the same
    # converted-asset catalogue as the rows above (the ``bbox`` of each model's xmodel_bin), and each one checked on the
    # way in: declared in a GDT (``installed_assets.json``
    # ``xmodels_declared``) and carrying a ``_LOD0.XMODEL_BIN`` in the tools
    # tree's ``model_export``, which is what the link packs from.  Which
    # way the file cabinet's drawers look was read off its mesh (drawer faces
    # on -y at yaw 0; the catalogue's glb winding is flipped, so the net
    # normal reads +y).
    "p7_3arc_lobby_picture_41x29": ((-20.5, -1.0, -14.75), (20.5, 0.0, 14.745)),
    "p7_3arc_park_doormat": ((-17.5, -11.5, 0.0), (17.5, 11.5, 0.075)),
    "p7_cai_planter_square_lrg": ((-36.0, -34.125, 0.0), (36.0, 34.0, 36.5)),
    "p7_cleaning_paper_towel": ((-4.716, -4.091, -0.034), (4.328, 4.087, 0.283)),
    "p7_coffee_maker_digital": ((-7.834, -4.894, 0.0), (7.834, 4.894, 17.46)),
    "p7_file_cab_metal_02": ((-9.014, -15.547, 0.0), (9.014, 14.0, 65.0)),
    "p7_foliage_plant_aloe_medium": ((-31.837, -31.115, -0.017), (28.197, 29.474, 47.057)),
    "p7_foliage_plant_aloe_pruned": ((-19.088, -21.887, -0.001), (15.676, 18.421, 29.538)),
    "p7_handrail_post_middle": ((-2.006, -2.816, 0.0), (2.006, 2.825, 36.016)),
    "p7_office_paper_folder_pink": ((-6.479, -5.045, 0.022), (6.499, 5.07, 0.199)),
    "p7_office_paper_sheet_01": ((-4.952, -7.861, -0.282), (5.05, 7.955, 1.323)),
    "p7_water_cooler_digital_bottle": ((-7.046, -7.082, -0.001), (7.057, 7.097, 25.463)),
    "p7_zm_der_signage_wash_hands": ((-3.39, -0.659, -3.39), (3.39, 0.0, 3.39)),
    # ------------------------------------------------------------------
    # zm_dmv's character pass (after-the-outbreak dressing), added
    # and measured the same way as the block above: the catalogue
    # ``bbox``, a GDT declaration, and a ``_LOD0.XMODEL_BIN`` present in the
    # tools tree's ``model_export``.  Three names that passed the first
    # two tests failed the third and are left out for it: the sandbag stacks
    # ``p7_sandbag_stack_44_end`` / ``_middle`` and ``p7_bottle_glass_liquor_02``
    # have only lower LODs there.  The civilian cars need their stock
    # ``model_export`` folders too (see :data:`zmforge.recipes.dmv.LOT_CARS`).
    "p7_anim_zm_barricade_board_01": ((-51.734, -1.01, -4.212), (52.02, 1.031, 4.199)),
    "p7_anim_zm_barricade_board_03": ((-53.535, -1.001, -4.228), (54.246, 1.0, 4.076)),
    "p7_anim_zm_barricade_board_05": ((-52.009, -1.001, -4.0), (52.152, 1.0, 4.0)),
    "p7_book_office_lrg_red": ((-5.85, -1.454, 0.011), (5.85, 1.454, 13.985)),
    "p7_book_office_med_brown": ((-5.85, -0.952, 0.011), (5.85, 0.982, 13.985)),
    "p7_cleaning_paper_ball_brown": ((-2.235, -2.652, 0.007), (2.237, 2.653, 2.952)),
    "p7_crate_wood_01_short_open": ((-15.437, -15.044, 0.15), (15.437, 15.044, 30.055)),
    "p7_debris_newspaper_02": ((-21.05, -20.696, 0.181), (20.875, 22.287, 1.578)),
    "p7_debris_newspaper_03": ((-18.348, -19.994, 0.018), (18.567, 19.26, 4.891)),
    "p7_debris_newspaper_06": ((-15.192, -13.169, 0.103), (24.773, 12.765, 4.891)),
    "p7_debris_newspaper_08": ((-16.874, -16.224, 0.103), (24.391, 16.54, 4.891)),
    "p7_debris_trash_drink_carrier_01": ((-5.106, -5.113, -0.097), (5.106, 5.113, 2.107)),
    "p7_debris_trash_food_box_01": ((-4.9, -4.554, 0.035), (4.9, 4.554, 1.331)),
    "p7_file_cab_metal_02_drawer_02": ((-8.0, -2.039, -0.572), (8.0, 18.0, 13.428)),
    "p7_gib_chunk_bone_01": ((-0.989, -1.294, -2.739), (0.944, 0.835, 2.099)),
    "p7_gib_chunk_bone_03": ((-0.994, -1.716, -1.61), (1.665, 2.805, 1.502)),
    "p7_gib_chunk_flesh_01": ((-2.614, -0.757, -2.589), (2.365, 0.757, 3.404)),
    "p7_gib_chunk_meat_01": ((-1.376, -3.606, -3.972), (1.233, 3.742, 4.774)),
    "p7_gib_chunk_meat_02": ((-1.8, -3.831, -3.114), (2.205, 3.844, 2.367)),
    "p7_office_paper_sheet_02": ((-4.944, -7.859, 0.005), (5.05, 7.955, 1.712)),
    "p7_office_paper_sheet_12": ((-6.982, -6.99, -0.398), (6.982, 6.99, 0.398)),
    "p7_water_cooler_digital_body_dmg": ((-8.805, -7.651, 0.0), (8.861, 8.074, 49.677)),
    "p7_zm_der2_poster_anatomy_01": ((-0.074, -18.952, -33.144), (4.234, 18.952, 35.131)),
    "p7_zm_der2_poster_anatomy_04": ((0.0, -14.536, -15.796), (2.916, 14.891, 15.796)),
    # ------------------------------------------------------------------
    # The map's own kit.  These six are not Treyarch's: they are converted
    # here from public-domain packs by :mod:`zmforge.props.build`
    # (:mod:`zmforge.props.library` says which pack and under which licence),
    # so their boxes are not read off the install's catalogue -- they are the
    # bounding box of the converted mesh, ``bounds_of(to_game_space(obj))``,
    # which is the same call the kit build uses to cut each prop's bullet mesh
    # and its collmap. the collmap in
    # ``share\raw\collmaps`` is written from the box here by both the kit's
    # converter and the commit (``props.collision.kit_collmap_document``), so
    # the two write the same bytes; before, they differed in GUIDs and in
    # rounding (9.17 against 9.16997729 on ``zmf_prop_toilet``).  ``tests/test_props.py`` re-measures
    # every one of the six from the cached archives and holds them to a
    # thousandth of a unit.
    #
    # Unlike half the stock palette these are centred on x and y and sit on
    # z = 0 (``to_game_space`` centres and floors them), so the plan centre is
    # (0, 0) and :func:`_placed_origin` is a no-op on them.  That is worth
    # writing down rather than leaving to be rediscovered: it is *measured*
    # here, so a scene that says where a kit prop should be gets it there, and
    # ``plan_half_extent`` insets by the real footprint instead of falling back
    # to the palette's size.
    "zmf_prop_donut": ((-3.897, -4.5, 0.0), (3.897, 4.5, 3.021)),
    "zmf_prop_birthday_cake": ((-7.0, -7.0, 0.0), (7.0, 7.0, 7.968)),
    "zmf_prop_lollipop": ((-0.913, -4.444, 0.0), (0.913, 4.444, 18.0)),
    "zmf_prop_roast_turkey": ((-7.5, -5.448, 0.0), (7.5, 5.448, 6.048)),
    "zmf_prop_teddy_bear": ((-8.66, -5.5, 0.0), (8.66, 5.5, 20.0)),
    "zmf_prop_toilet": ((-9.17, -14.0, 0.0), (9.17, 14.0, 26.462)),
    # Halloween set, measured the same way (tests/test_props.py).
    "zmf_prop_pumpkin": ((-8.0, -8.0, 0.0), (8.0, 8.0, 13.612)),
    "zmf_prop_jack_o_lantern": ((-8.0, -8.0, 0.0), (8.0, 8.0, 13.612)),
    "zmf_prop_jack_o_lantern_tall": ((-8.145, -8.145, 0.0), (8.145, 8.145, 18.0)),
    "zmf_prop_hay_bale": ((-20.0, -13.253, 0.0), (20.0, 13.253, 23.35)),
    "zmf_prop_gravestone_round": ((-13.304, -7.391, 0.0), (13.304, 7.391, 34.0)),
    "zmf_prop_gravestone_cross": ((-11.803, -8.656, 0.0), (11.803, 8.656, 48.0)),
    "zmf_prop_gravestone_broken": ((-13.0, -10.0, 0.0), (13.0, 10.0, 17.422)),
    "zmf_prop_wooden_cross": ((-16.051, -16.051, 0.0), (16.051, 16.051, 78.0)),
    "zmf_prop_fence_wood": ((-32.0, -5.888, 0.0), (32.0, 5.888, 39.688)),
    "zmf_prop_fence_iron": ((-32.0, -3.52, 0.0), (32.0, 3.52, 56.25)),
    "zmf_prop_corn_stalk": ((-16.956, -16.956, 0.0), (16.956, 16.956, 96.0)),
    "zmf_prop_corn_stalk_thin": ((-10.951, -10.951, 0.0), (10.951, 10.951, 90.0)),
    "zmf_prop_tractor": ((-45.72, -75.0, 0.0), (45.72, 75.0, 109.154)),
    "zmf_prop_hay_bale_stack": ((-20.0, -14.217, 0.0), (20.0, 14.217, 25.048)),
    "zmf_prop_hand_cart": ((-19.993, -30.0, 0.0), (19.993, 30.0, 23.978)),
    # Poly Haven photoscans: measured after the quadric cut
    # (props/build.game_mesh), which leaves the lowest point a hair off 0.
    "zmf_prop_dead_log": ((-59.926, -5.442, 0.010), (59.961, 5.455, 11.384)),
    "zmf_prop_tree_stump": ((-28.159, -31.426, 0.026), (28.180, 31.443, 22.695)),
    "zmf_prop_dead_tree_a": ((-113.0, -113.0, 0.0), (113.0, 113.0, 300.0)),
    "zmf_prop_dead_tree_b": ((-95.0, -95.0, 0.0), (95.0, 95.0, 270.0)),
    "zmf_prop_dead_tree_c": ((-109.0, -109.0, 0.0), (109.0, 109.0, 330.0)),
    "zmf_prop_dead_tree_d": ((-130.0, -130.0, 0.0), (130.0, 130.0, 400.0)),
    "zmf_prop_dead_tree_e": ((-142.0, -142.0, 0.0), (142.0, 142.0, 440.0)),
    # The gamble machine (props/atm.py): the anchor plate is the footprint, the
    # security dome on the topper the top; its front faces -Y.
    "zmf_prop_gamble_atm": ((-22.0, -18.0, 0.0), (22.0, 18.0, 90.9)),
    "zmf_prop_wooden_crate": ((-10.434, -23.0, 0.0), (10.434, 23.0, 18.298)),
    # ------------------------------------------------------------------
    # zm_dmv dense pass: every model in the converted-asset catalogue that
    # is GDT-declared and has its ``_lod0.xmodel_bin`` in the tools
    # tree's ``model_export``.  Boxes are the catalogue ``bbox`` verbatim.
    "p6_anim_zm_barricade_board_01_upgrade": ((-52.157, -1.301, -4.376), (52.249, 1.339, 4.41)),
    "p6_anim_zm_barricade_board_02_upgrade": ((-54.55, -1.273, -4.516), (54.145, 1.125, 4.376)),
    "p6_anim_zm_barricade_board_03_upgrade": ((-54.55, -1.25, -4.376), (54.145, 1.273, 4.516)),
    "p6_anim_zm_barricade_board_04_upgrade": ((-52.157, -1.339, -4.41), (52.249, 1.301, 4.376)),
    "p6_anim_zm_barricade_board_05_upgrade": ((-52.157, -1.301, -4.376), (52.249, 1.339, 4.41)),
    "p6_anim_zm_barricade_board_06_upgrade": ((-52.157, -1.339, -4.41), (52.249, 1.301, 4.376)),
    "p7_3arc_park_leaves_corner_1": ((-1.239, -12.693, -1.628), (15.708, 2.419, 8.904)),
    "p7_3arc_park_leaves_grp_2": ((-13.37, -17.401, -0.026), (24.213, 14.316, 3.157)),
    "p7_anim_zm_barricade_board_02": ((-54.011, -1.0, -4.259), (53.937, 1.001, 4.299)),
    "p7_anim_zm_barricade_board_04": ((-51.734, -1.031, -4.006), (52.02, 1.01, 4.405)),
    "p7_anim_zm_barricade_board_06": ((-51.993, -1.0, -4.004), (52.261, 1.001, 4.0)),
    "p7_bed_sheet_barrack_03": ((-27.671, -31.073, -4.038), (21.418, 16.563, 6.079)),
    "p7_book_office_sml_beige": ((-5.849, -0.548, 0.011), (5.873, 0.494, 13.949)),
    "p7_book_vintage_01": ((-5.649, -4.622, 0.0), (5.649, 4.622, 2.256)),
    "p7_book_vintage_01_burn": ((-5.649, -4.622, 0.0), (5.649, 4.622, 2.256)),
    "p7_book_vintage_02": ((-5.649, -4.622, 0.0), (5.649, 4.622, 2.261)),
    "p7_book_vintage_02_burn": ((-5.649, -4.622, 0.0), (5.649, 4.622, 2.261)),
    "p7_book_vintage_03": ((-5.341, -4.002, -0.01), (5.341, 4.002, 1.913)),
    "p7_book_vintage_03_burn": ((-5.341, -4.002, -0.01), (5.341, 4.002, 1.913)),
    "p7_book_vintage_04": ((-5.719, -4.603, -0.014), (5.719, 4.603, 1.875)),
    "p7_book_vintage_04_burn": ((-5.719, -4.603, -0.014), (5.719, 4.603, 1.875)),
    "p7_book_vintage_05": ((-5.686, -4.649, -0.03), (5.686, 4.649, 3.17)),
    "p7_book_vintage_05_burn": ((-5.686, -4.649, -0.03), (5.686, 4.649, 3.17)),
    "p7_book_vintage_06": ((-5.582, -4.609, 0.0), (5.582, 4.609, 2.248)),
    "p7_book_vintage_06_burn": ((-5.582, -4.609, 0.0), (5.582, 4.609, 2.248)),
    "p7_book_vintage_open_01_burn": ((-5.649, -9.884, 0.0), (5.649, 9.884, 2.129)),
    "p7_book_vintage_open_02_burn": ((-5.649, -9.886, -0.004), (5.649, 9.886, 2.123)),
    "p7_book_vintage_open_03_burn": ((-5.344, -8.561, -0.003), (5.344, 8.561, 2.134)),
    "p7_book_vintage_open_04": ((-5.719, -9.803, 0.0), (5.719, 9.803, 1.858)),
    "p7_book_vintage_open_04_burn": ((-5.719, -9.803, 0.0), (5.719, 9.803, 1.858)),
    "p7_brick_dirty_01": ((-2.855, -5.822, -1.95), (2.806, 6.076, 2.002)),
    "p7_brick_dirty_02": ((-2.752, -5.753, -1.956), (2.753, 5.848, 2.11)),
    "p7_brick_dirty_03": ((-2.565, -3.801, -1.901), (2.527, 3.75, 1.929)),
    "p7_brick_dirty_04": ((-2.647, -3.68, -1.867), (2.616, 3.67, 1.869)),
    "p7_brick_dirty_breakout_01": ((-7.794, -30.0, -0.154), (1.269, 30.0, 44.0)),
    "p7_brick_dirty_breakout_02": ((-8.748, -30.0, -0.154), (1.258, 30.0, 64.0)),
    "p7_brick_dirty_breakout_03": ((-4.841, -32.0, -0.002), (4.358, 32.0, 43.972)),
    "p7_brick_dirty_breakout_04": ((-5.016, -32.0, -0.002), (3.924, 32.0, 64.0)),
    "p7_brick_dirty_breakout_06": ((-4.878, -29.383, 15.901), (1.06, 17.566, 52.049)),
    "p7_brick_dirty_breakout_07": ((-3.958, -24.0, -0.086), (1.359, 4.161, 15.777)),
    "p7_brick_dirty_breakout_08": ((-1.185, -24.0, -0.018), (3.654, 4.513, 15.777)),
    "p7_brick_dirty_breakout_09": ((-3.477, -32.0, 0.0), (1.417, 4.513, 15.98)),
    "p7_brick_dirty_breakout_10": ((-1.31, -32.0, 0.0), (3.782, 2.769, 16.004)),
    "p7_brick_dirty_breakout_11": ((-25.895, -1.064, -0.089), (0.853, 26.441, 59.897)),
    "p7_cai_planter_corner": ((-28.0, -29.313, 0.0), (28.125, 29.125, 41.5)),
    "p7_cai_planter_rectangle_sml": ((-47.0, -24.625, 0.0), (47.0, 24.5, 46.0)),
    "p7_cinder_block": ((-8.609, -3.097, -4.006), (7.552, 3.137, 4.006)),
    "p7_cleaning_paper_brown": ((-7.868, -6.225, 0.004), (7.917, 5.975, 0.793)),
    "p7_consumer_grade_monitor_wall_medium": ((-30.769, 36.151, -13.65), (30.769, 39.177, 13.65)),
    "p7_crate_plastic_tech_02": ((-5.0, -31.394, -0.775), (5.0, 31.394, 31.402)),
    "p7_crate_wood_01_short_open_lid": ((-15.35, -15.007, 29.352), (15.35, 15.007, 31.18)),
    "p7_debris_brick_chunk_02": ((1.521, -1.134, -1.191), (3.816, 2.83, 1.191)),
    "p7_debris_brick_chunk_03": ((-7.365, -0.579, -1.191), (-2.533, 2.399, 1.191)),
    "p7_debris_brick_chunk_04": ((25.262, -0.249, -1.191), (28.172, 1.758, 1.191)),
    "p7_debris_brick_chunk_hlf_01": ((15.086, -1.272, -1.191), (20.822, 2.719, 1.191)),
    "p7_debris_brick_chunk_hlf_02": ((-15.662, -1.193, -1.191), (-10.679, 2.807, 1.191)),
    "p7_debris_concrete_rubble_med_03_no_metal": ((-22.213, -20.434, -12.684), (24.383, 21.431, 17.655)),
    "p7_debris_concrete_rubble_med_06_no_metal": ((-20.063, -18.022, -14.82), (20.063, 11.961, 14.82)),
    "p7_debris_concrete_rubble_sm_00": ((-7.807, -5.986, -6.249), (7.807, 5.986, 6.249)),
    "p7_debris_concrete_rubble_sm_01": ((-7.149, -10.254, -9.685), (7.149, 10.254, 9.685)),
    "p7_debris_concrete_rubble_sm_03": ((-6.114, -10.626, -8.682), (6.114, 10.626, 8.682)),
    "p7_debris_concrete_rubble_sm_06": ((-3.943, -4.081, -3.36), (3.943, 4.081, 3.36)),
    "p7_debris_concrete_rubble_sm_07": ((-5.775, -5.057, -4.625), (5.775, 5.057, 4.625)),
    "p7_debris_concrete_rubble_sm_08": ((-8.488, -4.599, -9.094), (8.488, 4.599, 9.094)),
    "p7_debris_concrete_rubble_sm_10": ((-7.299, -11.251, -9.254), (7.299, 11.251, 9.254)),
    "p7_debris_concrete_rubble_sm_11": ((-8.283, -6.104, -7.587), (8.283, 6.104, 7.587)),
    "p7_debris_concrete_rubble_sm_12": ((-8.076, -9.471, -7.888), (8.076, 9.471, 7.888)),
    "p7_debris_concrete_rubble_sm_13": ((-8.398, -6.292, -7.666), (8.398, 6.292, 7.666)),
    "p7_debris_concrete_rubble_sm_14": ((-6.896, -6.992, -6.771), (6.896, 6.992, 6.771)),
    "p7_debris_concrete_rubble_sm_15": ((-4.911, -8.529, -7.948), (4.911, 8.529, 7.948)),
    "p7_debris_concrete_rubble_sm_16": ((-7.093, -7.755, -8.322), (7.093, 7.755, 8.322)),
    "p7_debris_newspaper_05": ((-18.077, -17.341, -0.043), (11.693, 21.666, 1.678)),
    "p7_debris_newspaper_corner_02": ((39.931, 72.424, -0.365), (51.999, 116.447, 9.673)),
    "p7_debris_plaster_rubble_med_03": ((-0.483, 22.929, -12.192), (0.483, 44.564, 12.192)),
    "p7_debris_rockychunks_small_01": ((-17.514, -24.803, -6.726), (17.514, 24.803, 6.726)),
    "p7_debris_rockychunks_small_07": ((-7.965, -6.128, -2.39), (8.086, 5.996, 1.831)),
    "p7_debris_rockychunks_small_09": ((-8.514, -5.356, -7.795), (8.514, 5.356, 7.795)),
    "p7_debris_rockychunks_small_11": ((-15.7, -23.603, -2.766), (15.7, 23.603, 2.766)),
    "p7_debris_rockychunks_small_12": ((-10.572, -11.494, -12.874), (10.572, 11.494, 12.874)),
    "p7_debris_trash_paper_03": ((-5.011, -4.186, 0.011), (5.011, 4.186, 1.471)),
    "p7_debris_trash_paper_04": ((-2.297, -3.556, 0.013), (2.176, 3.506, 1.002)),
    "p7_debris_trash_paper_05": ((-2.314, -3.313, -0.001), (2.314, 3.313, 1.193)),
    "p7_debris_trash_paper_09": ((-3.605, -5.285, 0.006), (3.605, 5.285, 1.447)),
    "p7_debris_trash_paper_10": ((-4.563, -3.804, -0.028), (4.563, 3.804, 0.998)),
    "p7_debris_wood_board_2pc_2x4x128_lt": ((-35.034, -2.003, -0.982), (36.729, 2.003, 0.982)),
    "p7_debris_wood_board_2pc_2x4x128_lt_burn": ((-35.034, -2.003, -0.982), (36.729, 2.003, 0.982)),
    "p7_debris_wood_board_2pc_2x4x128_rt": ((-22.632, -2.003, -1.0), (18.017, 2.003, 1.0)),
    "p7_debris_wood_board_2pc_2x4x128_rt_burn": ((-22.632, -2.003, -1.0), (18.017, 2.003, 1.0)),
    "p7_debris_wood_board_2pc_2x8x128_lt": ((-41.756, -4.109, -1.049), (42.345, 4.109, 1.034)),
    "p7_debris_wood_board_2pc_2x8x128_rt": ((-28.333, -4.094, -1.049), (23.247, 4.109, 1.034)),
    "p7_debris_wood_board_2pc_2x8x128_rt_burn": ((-28.333, -4.094, -1.049), (23.247, 4.109, 1.034)),
    "p7_debris_wood_board_2pc_4x4x128_lt": ((-36.38, -1.935, -2.0), (37.697, 1.935, 2.0)),
    "p7_debris_wood_board_2pc_4x4x128_lt_burn": ((-36.38, -1.935, -2.0), (37.697, 1.935, 2.0)),
    "p7_debris_wood_board_2pc_4x4x128_rt": ((-24.145, -1.974, -2.0), (20.482, 1.974, 2.0)),
    "p7_debris_wood_board_2pc_4x4x128_rt_burn": ((-24.145, -1.974, -2.0), (20.482, 1.974, 2.0)),
    "p7_debris_wood_board_2x4x128": ((-63.999, -2.071, -1.0), (63.999, 2.071, 1.0)),
    "p7_debris_wood_board_cluster_02": ((-1.821, -26.885, -2.07), (39.75, 26.582, 2.131)),
    "p7_debris_wood_board_cluster_03": ((-19.811, -20.273, -2.109), (18.343, 22.606, 2.094)),
    "p7_debris_wood_board_cluster_04": ((-29.927, -8.641, -2.02), (10.286, 35.681, 2.02)),
    "p7_debris_wood_board_cluster_burn_01": ((-20.308, -20.519, -2.05), (20.308, 20.519, 2.05)),
    "p7_debris_wood_board_cluster_burn_02": ((-1.821, -26.885, -2.07), (39.75, 26.582, 2.131)),
    "p7_debris_wood_board_cluster_burn_03": ((-19.811, -20.273, -2.109), (18.343, 22.606, 2.094)),
    "p7_debris_wood_board_cluster_burn_04": ((-29.927, -8.641, -2.02), (10.286, 35.681, 2.02)),
    "p7_debris_wood_board_splinter_02": ((-14.45, -2.869, -0.77), (13.709, 2.744, 0.749)),
    "p7_debris_wood_board_splinter_03": ((-10.726, -1.443, -0.724), (10.799, 1.664, 0.762)),
    "p7_desk_metal_military_03_tablet": ((-3.564, -6.033, -0.01), (3.564, 6.004, 0.305)),
    "p7_desk_metal_old_01": ((-36.0, -19.612, 0.0), (36.0, 18.0, 34.0)),
    "p7_electrical_box_set2_box03": ((-7.188, -7.019, 0.0), (6.846, 0.0, 21.374)),
    "p7_electrical_box_set2_box05": ((-7.836, -8.184, 0.0), (7.836, 0.0, 31.26)),
    "p7_electrical_box_set2_box06": ((-8.11, -8.081, 0.0), (8.11, 0.0, 16.329)),
    "p7_electrical_box_set2_box07": ((-9.095, -7.633, -3.245), (9.095, 0.0, 25.558)),
    "p7_electrical_box_set2_meter05": ((0.0, -6.424, -3.79), (11.054, 0.0, 9.6)),
    "p7_electrical_box_set2_meter06": ((0.0, -6.401, -3.801), (11.054, 0.0, 9.6)),
    "p7_electrical_box_set2_meter07": ((-0.342, -6.424, -3.738), (10.515, 0.0, 22.471)),
    "p7_electrical_box_set2_meter08": ((-0.342, -6.401, -3.796), (10.515, 0.0, 15.15)),
    "p7_electrical_box_set2_meter09": ((-4.159, -4.752, 0.0), (3.817, 0.0, 14.02)),
    "p7_electrical_box_set2_meter10": ((-4.159, -4.623, 0.0), (3.817, 0.0, 14.02)),
    "p7_electrical_box_set2_meterhead01": ((-3.928, -4.775, -3.922), (3.928, 0.022, 3.933)),
    "p7_electrical_box_set2_meterhead02": ((-3.676, -4.458, -3.676), (3.689, 0.05, 3.689)),
    "p7_faucet_kitchen_stainless_modern_01_clean": ((-16.821, -11.631, -0.073), (19.301, 1.408, 15.09)),
    "p7_file_cab_metal_02_shell": ((-9.014, -14.0, 0.0), (9.014, 14.0, 65.0)),
    "p7_foliage_grass_02": ((-80.772, -80.772, 0.0), (87.995, 87.995, 44.967)),
    "p7_foliage_grass_tall_cluster_sml": ((-19.384, -18.673, -0.363), (23.88, 21.354, 34.011)),
    "p7_foliage_grass_tall_single_lrg": ((-22.479, -22.143, -0.033), (25.319, 29.514, 99.404)),
    "p7_foliage_grass_tall_single_sml": ((-18.467, -27.815, -0.033), (17.231, 30.251, 56.782)),
    "p7_foliage_plant_aloe_large": ((-62.438, -53.651, -0.004), (44.358, 61.217, 72.493)),
    "p7_foliage_weed_cluster_med": ((-3.892, -2.496, -0.318), (3.892, 2.496, 5.968)),
    "p7_foliage_weed_cluster_sml_a": ((-2.694, -2.446, -0.301), (2.694, 2.446, 6.561)),
    "p7_foliage_weed_cluster_sml_b": ((-2.532, -1.715, -0.158), (1.595, 2.666, 5.408)),
    "p7_food_fruit_melon": ((-3.247, -3.224, 0.0), (3.232, 3.22, 5.807)),
    "p7_food_fruit_pineapple": ((-4.105, -3.981, 0.0), (4.327, 4.021, 15.765)),
    "p7_gib_chunk_bone_02": ((-1.091, -1.444, -1.243), (1.744, 1.881, 0.81)),
    "p7_gib_chunk_flesh_02": ((-0.867, -3.042, -1.664), (0.549, 2.281, 2.894)),
    "p7_gib_chunk_flesh_03": ((-2.272, -0.911, -2.474), (1.616, 0.911, 2.128)),
    "p7_gib_chunk_meat_03": ((-1.656, -3.553, -3.206), (1.486, 3.23, 4.007)),
    "p7_grating_metal_01_support_32x16": ((-16.0, -8.039, -2.0), (16.0, 8.019, 0.0)),
    "p7_handrail_joint_corner": ((-2.821, -2.801, -1.416), (1.016, 1.035, 1.416)),
    "p7_handrail_joint_end": ((-1.016, -0.965, -1.433), (1.016, 2.821, 1.433)),
    "p7_handrail_joint_middle": ((-1.016, -2.816, -1.423), (1.016, 2.825, 1.423)),
    "p7_handrail_post_corner": ((-2.821, -2.798, 0.0), (2.006, 2.006, 36.015)),
    "p7_handrail_post_end": ((-2.006, -2.006, 0.0), (2.006, 2.84, 35.937)),
    "p7_light_fixture_led_ceiling_01": ((-10.0, -30.297, -4.709), (10.0, 30.297, 0.06)),
    "p7_light_fixture_led_ceiling_01_dmg": ((-10.0, -30.297, -4.709), (10.0, 30.297, 0.06)),
    "p7_light_fixture_led_utility": ((-0.01, -2.15, -6.905), (4.95, 2.15, 2.45)),
    "p7_office_paper_sheet_03": ((-5.769, -4.714, -1.616), (5.769, 4.714, 1.616)),
    "p7_office_paper_sheet_08": ((-7.853, -6.918, -1.387), (7.853, 6.918, 1.387)),
    "p7_office_paper_sheet_09": ((-4.599, -5.688, -2.04), (4.599, 5.688, 2.04)),
    "p7_office_paper_sheet_10": ((-6.227, -5.707, -0.335), (6.227, 5.707, 0.335)),
    "p7_rebar_patch_64x64_01": ((-30.65, -3.439, -32.233), (32.624, 3.439, 32.233)),
    "p7_rebar_patch_64x64_02": ((-32.341, -3.179, -26.37), (30.362, 3.398, 26.37)),
    "p7_rebar_straight_32_01": ((-16.618, -1.163, -10.827), (17.869, 1.121, 10.497)),
    "p7_rebar_straight_32_02": ((-16.618, -4.077, -10.803), (17.869, 1.872, 9.816)),
    "p7_signage_caution_warning_01": ((-14.0, -0.25, -14.0), (14.0, 0.0, 14.0)),
    "p7_signage_loading_zone_02": ((-9.0, -0.91, -14.0), (9.0, 0.0, 14.0)),
    "p7_zm_der2_barrel_metal_55gal_lid": ((-11.913, -12.622, -1.077), (11.913, 11.913, 1.199)),
    "p7_zm_der2_brick_dirty_breakout_05_wet": ((-25.895, -1.855, 0.0), (1.494, 26.441, 59.897)),
    "p7_zm_der2_electrical_box_set2_box04": ((-6.602, -10.523, -0.7), (6.412, 0.0, 24.497)),
    "p7_zm_der2_poster_anatomy_02": ((0.0, -24.19, -16.537), (7.615, 24.248, 16.552)),
    "p7_zm_der2_poster_anatomy_03": ((-0.206, -19.358, -8.076), (2.471, 18.952, 8.078)),
    "p7_zm_der2_poster_anatomy_05": ((-0.002, -14.83, -10.867), (4.96, 14.827, 10.867)),
    "p7_zm_der2_poster_anatomy_06": ((-0.204, -9.406, -10.517), (3.101, 9.426, 10.826)),
    "p7_zm_der2_poster_anatomy_07": ((-0.006, -9.446, -16.171), (2.814, 9.419, 16.163)),
    "p7_zm_der2_signage_hazard_01": ((-7.453, -0.665, -6.797), (7.782, -0.015, 6.797)),
    "p7_zm_der2_vending_packapunch_sign_wait": ((0.0, 0.0, 0.0), (20.44, 0.253, 21.564)),
    "p7_zm_der_cabinet_lab_door_left": ((-0.389, -2.087, -29.0), (15.5, 0.048, 0.0)),
    "p7_zm_der_cabinet_lab_door_right": ((-15.5, -2.087, -29.0), (0.389, 0.048, 0.0)),
    "p7_zm_der_cabinet_lab_drawer": ((-12.0, -2.087, -8.663), (12.0, 26.0, 1.0)),
    "p7_zm_der_handrail_joint_corner": ((-2.821, -2.801, -1.416), (1.016, 1.035, 1.416)),
    "p7_zm_der_handrail_joint_end": ((-1.016, -0.965, -1.433), (1.016, 2.821, 1.433)),
    "p7_zm_der_handrail_joint_end_45": ((-1.016, -0.965, -1.617), (1.016, 2.733, 1.433)),
    "p7_zm_der_handrail_joint_middle": ((-1.016, -2.816, -1.423), (1.016, 2.825, 1.423)),
    "p7_zm_der_handrail_joint_middle_45": ((-1.016, -3.268, -2.639), (1.016, 2.975, 2.543)),
    "p7_zm_der_handrail_post_corner": ((-2.821, -2.798, 0.0), (2.006, 2.006, 36.015)),
    "p7_zm_der_handrail_post_end": ((-2.006, -2.006, 0.0), (2.006, 2.84, 35.937)),
    "p7_zm_der_handrail_post_middle": ((-2.006, -2.816, 0.0), (2.006, 2.825, 36.016)),
    "p7_zm_der_magic_box": ((-47.315, -12.5, -0.007), (47.315, 13.844, 19.448)),
    "p7_zm_der_magic_box_fake": ((-10.106, 5.452, 13.925), (2.865, 16.254, 27.988)),
    "p7_zm_der_magic_box_fake_trunk": ((-15.35, -7.855, -0.328), (15.35, 8.126, 14.828)),
    "p7_zm_der_pswitch_body": ((-19.825, -12.171, 0.0), (19.811, 5.001, 95.544)),
    "p7_zm_der_pswitch_handle": ((-9.212, -2.224, -1.034), (9.212, 2.215, 24.164)),
    "p7_zm_der_signage_caution": ((-3.143, -0.362, -1.084), (3.143, -0.004, 1.084)),
    "p7_zm_der_signage_circus_child": ((-7.138, -0.651, -5.268), (7.138, 0.004, 5.268)),
    "p7_zm_der_signage_hazard_03": ((-7.453, -0.665, -6.797), (7.782, -0.015, 6.797)),
    "p7_zm_der_signage_hazard_04": ((-7.453, -0.665, -6.797), (7.782, -0.015, 6.797)),
    "p7_zm_der_signage_hazard_05": ((-7.453, -0.665, -6.797), (7.782, -0.015, 6.797)),
    "p7_zm_der_signage_hazard_06": ((-7.453, -0.665, -6.797), (7.782, -0.015, 6.797)),
    "p7_zm_der_signage_hazmat_suit": ((-3.39, -0.659, -3.39), (3.39, 0.0, 3.39)),
    "p7_zm_teddybear": ((-9.066, -6.026, -14.169), (9.163, 5.997, 13.906)),
    "p7_zm_vending_packapunch": ((-42.765, -26.494, 0.0), (42.765, 21.625, 86.44)),
    "p7_zm_vending_packapunch_on": ((-42.765, -26.494, 0.0), (42.765, 21.625, 86.44)),
    "p7_zm_vending_packapunch_sign_wait": ((0.0, 0.0, 0.0), (20.44, 0.253, 21.564)),
    "p7_zm_vending_packapunch_weapon": ((-2.0, -2.0, -2.0), (2.0, 2.0, 2.0)),
    # ------------------------------------------------------------------
    # zm_dmv models that use the stock ``model_export`` folders of the mod
    # tools: 152 models that are GDT-declared and catalogued, and need the 75
    # images their GDT materials name from other folders as well (999 files
    # in all).  Same three checks as the dmv blocks above: the
    # catalogue ``bbox``, a GDT declaration (``installed_assets.json``
    # ``xmodels_declared``), and the GDT's binary present in the tools
    # tree's ``model_export``.  All 152 now pass; five are left out because
    # their boxes read as flat panels (``is_panel_model``) and would trip the
    # pinned panel list: ``p7_light_lab_center_frame``,
    # ``p7_rug_cloth_modern_128x256_01``, ``p7_zm_debris_newspaper_german_05``,
    # ``veh_t7_civ_truck_semi_flatbed`` and ``veh_t7_civ_truck_semi_trailer``.
    "p7_bag_plastic_soil": ((-12.337, -7.031, -1.863), (12.337, 6.949, 2.364)),
    "p7_blinds_01_closed": ((-19.806, -2.137, -48.631), (19.88, 1.457, 36.209)),
    "p7_blinds_01_open": ((-19.924, -2.137, -36.147), (19.956, 1.457, 36.209)),
    "p7_blinds_01_wide_closed": ((-40.086, -2.289, -36.147), (39.086, 1.253, 36.209)),
    "p7_blinds_01_wide_open": ((-40.086, -2.289, -36.147), (39.086, 1.473, 36.209)),
    "p7_blinds_01_wide_raised": ((-40.086, -2.289, -24.374), (39.086, 1.617, 36.209)),
    "p7_blinds_cloth_01": ((-20.724, -3.929, -35.768), (20.712, 0.929, 37.522)),
    "p7_blinds_cloth_02": ((-20.724, -3.929, -48.332), (20.712, 0.929, 37.522)),
    "p7_blinds_cloth_03": ((-39.593, -3.929, -35.768), (39.618, 0.929, 37.522)),
    "p7_blinds_cloth_03_raised": ((-39.593, -3.929, 22.702), (39.618, 0.929, 37.522)),
    "p7_bottle_plastic_16oz_water": ((-1.214, -1.213, -0.009), (1.214, 1.214, 7.523)),
    "p7_bottle_plastic_soap_orange_clean": ((-1.95, -1.95, 0.019), (1.95, 1.95, 7.801)),
    "p7_box_copy_paper_sheet": ((-3.949, -5.633, -0.377), (3.949, 5.633, 0.021)),
    "p7_box_wood_01_long": ((-7.832, -21.917, 0.079), (7.107, 21.917, 13.048)),
    "p7_box_wood_01_sm": ((-7.819, -11.049, 0.079), (7.102, 11.049, 13.042)),
    "p7_box_wood_wine_storage": ((-9.0, -12.0, 0.0), (9.0, 12.0, 8.503)),
    "p7_box_wood_wine_storage_tan": ((-9.0, -12.0, 0.0), (9.0, 12.0, 8.503)),
    "p7_cai_apt_couch_cushion_lrg": ((-16.758, -11.757, -6.709), (16.759, 12.987, 6.345)),
    "p7_cai_apt_couch_cushion_sml": ((-11.492, -9.838, -4.655), (11.479, 11.019, 4.292)),
    "p7_cai_apt_couch_ottoman": ((-15.759, -15.903, 0.54), (15.765, 15.941, 19.4)),
    "p7_cai_hotel_deco_box_01": ((-6.0, -33.0, -33.0), (1.0, 33.154, 33.0)),
    "p7_cai_light_garden": ((-8.0, -8.0, 0.0), (8.0, 8.0, 9.655)),
    "p7_cai_lotus_light_door_01": ((0.011, -24.777, -1.26), (8.604, 24.777, 1.26)),
    "p7_cai_monitor_wall_large": ((-61.538, -6.131, -26.001), (61.538, -0.0, 26.001)),
    "p7_cai_sign_billboard_02_bolt_plate": ((-4.349, -5.993, -3.229), (4.349, 6.526, 2.411)),
    "p7_cai_sign_billboard_02_wire": ((-14.18, -1.177, -3.137), (14.18, 1.177, 3.137)),
    "p7_cai_sign_info_wall": ((-8.394, -65.394, -0.0), (8.394, 65.394, 114.0)),
    "p7_cai_sign_inteactive_kiosk": ((-29.0, -6.0, 0.0), (29.0, 6.0, 120.0)),
    "p7_cai_signage_plastic_exit": ((-8.516, -1.278, -9.752), (8.516, 1.278, 6.0)),
    "p7_chair_lab_02": ((-17.771, -18.367, -0.034), (17.771, 15.392, 51.861)),
    "p7_chemistry_kit_large_bottle": ((-5.709, -5.709, 0.0), (5.709, 5.709, 19.882)),
    "p7_chemistry_kit_measuring_bottle": ((-4.028, -4.028, -0.0), (4.028, 4.028, 28.81)),
    "p7_cloth_drape_01_beige": ((-48.752, -10.938, -0.113), (48.752, 5.651, 83.642)),
    "p7_cloth_drape_02_beige": ((55.013, -9.351, -0.445), (116.851, 5.655, 83.146)),
    "p7_clothes_hanging_01_dress": ((-3.105, -10.076, -58.495), (3.105, 10.076, 0.953)),
    "p7_clothes_hanging_01_hanger": ((-0.13, -10.274, -7.252), (0.13, 10.274, 1.171)),
    "p7_clothes_hanging_01_pants": ((-1.855, -9.873, -56.217), (1.855, 9.873, 1.151)),
    "p7_clothes_hanging_01_shirt": ((-2.25, -7.144, -26.664), (2.25, 7.144, -4.054)),
    "p7_clothes_hanging_01_suit": ((-2.553, -10.974, -31.92), (2.553, 10.974, -1.211)),
    "p7_clothes_hanging_01_tshirt": ((-3.569, -12.304, -35.091), (3.569, 12.304, -4.082)),
    "p7_clothes_hanging_02_clothesline_tank_landed": ((-5.299, -7.322, -0.315), (5.299, 7.322, 1.74)),
    "p7_clothes_hanging_02_clothesline_tshirt_landed": ((-11.625, -11.225, -0.244), (11.625, 11.225, 4.104)),
    "p7_clothes_womens_crumpled_01_shirt": ((-11.672, -18.578, -0.01), (11.805, 18.611, 1.405)),
    "p7_clothes_womens_crumpled_02_pants": ((-14.517, -6.571, -0.0), (17.274, 8.518, 3.652)),
    "p7_clothes_womens_crumpled_02_skirt": ((-22.517, -11.524, 0.0), (21.682, 14.084, 4.409)),
    "p7_computer_mobile_military_open": ((-11.339, -1.746, 0.023), (11.241, 34.685, 61.107)),
    "p7_container_bottle_wine_01": ((-2.017, -1.986, 0.017), (2.017, 1.986, 14.113)),
    "p7_corrugated_sheet_metal_rust_01": ((-48.034, -0.644, -48.0), (48.034, 0.644, 48.0)),
    "p7_corrugated_sheet_metal_rust_02": ((-22.241, -0.639, -48.0), (22.241, 0.639, 48.0)),
    "p7_corrugated_sheet_metal_rust_03": ((-11.946, -0.639, -48.0), (11.946, 0.639, 48.0)),
    "p7_corrugated_sheet_metal_rust_04": ((-22.241, -0.639, -24.008), (22.241, 0.639, 24.008)),
    "p7_couch_cloth_modern_01": ((-19.45, -46.717, -0.003), (19.489, 53.698, 29.769)),
    "p7_couch_modern_leather": ((-64.324, -21.327, -0.031), (64.324, 23.89, 41.184)),
    "p7_debris_clothing_dress_01": ((-11.781, -13.309, 0.0), (14.841, 13.816, 3.535)),
    "p7_debris_clothing_pants_01": ((-18.817, -19.541, -0.0), (18.783, 19.616, 4.55)),
    "p7_debris_clothing_piles_01": ((-15.384, -30.011, -0.0), (16.493, 17.189, 10.344)),
    "p7_debris_clothing_tshirts_01": ((-11.625, -11.423, -0.0), (11.577, 11.43, 4.417)),
    "p7_debris_clothing_tshirts_02": ((-13.572, -12.467, -0.024), (13.582, 12.466, 2.539)),
    "p7_debris_paper_sheet_01": ((-29.81, -22.642, 0.136), (29.97, 24.011, 4.545)),
    "p7_decanter_glass_bottle": ((-1.75, -1.75, 0.0), (1.75, 1.75, 10.25)),
    "p7_desk_lab_sterilizer_cabinet": ((-48.0, -36.608, 0.0), (48.0, 36.608, 46.0)),
    "p7_electrical_box_set_box_4": ((-9.803, -8.177, -0.532), (9.803, -0.0, 12.614)),
    "p7_elevator_call_box": ((-2.983, -3.009, -5.0), (3.017, 0.232, 5.0)),
    "p7_foliage_plant_meskel_1_yellow": ((-13.773, -11.639, -0.033), (14.409, 11.459, 31.889)),
    "p7_foliage_plant_meskel_3_noflower": ((-5.071, -4.593, -0.004), (5.086, 4.595, 11.298)),
    "p7_light_metal_circle_pole": ((-55.203, -55.203, 0.0), (55.203, 64.223, 373.467)),
    "p7_light_metal_modern_floor_01": ((-12.522, -9.939, 0.0), (62.405, 9.939, 66.841)),
    "p7_light_metal_recessed_led": ((-4.753, -4.753, -0.245), (4.753, 4.753, 3.59)),
    "p7_light_path_metal_small": ((-4.005, -3.469, 0.0), (4.005, -0.068, 9.435)),
    "p7_light_track_led_01_track_128_white": ((-2.0, -64.0, -2.0), (2.0, 64.0, 0.0)),
    "p7_light_track_led_01_track_64_white": ((-2.0, -32.0, -2.0), (2.0, 32.0, 0.0)),
    "p7_light_track_led_01_white": ((-4.25, -4.091, -11.591), (7.5, 4.091, 0.0)),
    "p7_light_wall_runner_led": ((-3.0, -0.75, -2.25), (3.0, 0.75, 2.25)),
    "p7_lightswitch_metal_m_sensor": ((-2.15, 0.0, -2.0), (2.15, 0.395, 2.0)),
    "p7_make_shift_drape_cloth_03": ((-17.021, -12.813, -33.278), (17.021, 12.813, 33.278)),
    "p7_medical_arm_light": ((-9.913, -5.66, -19.229), (7.158, 5.667, 0.118)),
    "p7_monitor_arm_mount_military": ((-1.636, -1.327, -1.322), (1.637, 4.363, 1.331)),
    "p7_monitor_arm_pole_a_military": ((-1.187, -18.427, -0.516), (1.179, -6.47, 11.846)),
    "p7_monitor_curved_military": ((-29.755, -4.939, -15.888), (29.799, 0.94, 15.866)),
    "p7_monitor_curved_military_decal_circle": ((-11.292, -7.14, -5.706), (4.786, -6.836, 9.867)),
    "p7_sign_aerofarm_01": ((-115.357, -4.28, -0.683), (115.357, -0.673, 58.244)),
    "p7_sign_aerofarm_02": ((-160.0, -5.0, 0.0), (328.0, 5.0, 176.0)),
    "p7_sign_metal_screen_large": ((-240.001, -0.0, -0.001), (168.195, 236.078, 158.945)),
    "p7_sin_cell_phone_antenna": ((-41.495, -9.018, -61.58), (17.617, 18.806, 77.787)),
    "p7_sin_cell_phone_antenna_track": ((-45.519, -2.217, -4.886), (45.519, 2.217, 4.886)),
    "p7_zm_debris_newspaper_german_01": ((-21.05, -20.696, 0.181), (20.875, 22.287, 1.578)),
    "p7_zm_debris_newspaper_german_02": ((-18.348, -19.994, 0.018), (18.567, 19.26, 4.891)),
    "p7_zm_debris_newspaper_german_03": ((-18.077, -17.078, -0.031), (9.154, 20.465, 1.351)),
    "p7_zm_debris_newspaper_german_04": ((-15.192, -13.169, 0.103), (24.773, 12.765, 4.891)),
    "p7_zm_debris_newspaper_german_06": ((-16.874, -16.224, 0.103), (24.391, 16.54, 4.891)),
    "p7_zm_der2_signage_armory": ((-65.493, -2.072, -38.611), (65.167, -0.0, 53.796)),
    "p7_zm_der_conduit_box_metal": ((-15.0, -24.0, -15.0), (15.0, -0.0, 15.0)),
    "p7_zm_der_light_bulb_glass_cover": ((16.336, -2.022, -0.0), (20.38, 2.022, 7.011)),
    "p7_zm_der_light_bulb_small": ((-37.625, -1.164, 0.0), (-35.296, 1.164, 4.99)),
    "p7_zm_der_light_cage_01": ((-32.662, -11.914, -2.735), (-8.834, 11.914, -0.0)),
    "p7_zm_der_light_cage_02": ((0.887, -2.745, 0.0), (6.38, 2.745, 7.707)),
    "p7_zm_der_light_shade": ((-12.101, -12.101, -11.0), (12.101, 12.101, -0.0)),
    "p7_zm_der_light_socket": ((53.178, -2.947, 0.0), (59.071, 2.947, 2.911)),
    "p7_zm_der_light_socket_02": ((45.797, -1.861, 0.0), (49.519, 1.861, 2.079)),
    "p7_zm_der_light_spot_base_plate": ((-28.748, -4.648, -4.15), (-21.248, 4.648, -0.0)),
    "p7_zm_der_light_spot_frame": ((-15.568, -1.513, -21.817), (10.806, 1.513, -0.0)),
    "p7_zm_der_light_spot_housing": ((18.108, -10.108, -12.263), (42.634, 15.413, 13.706)),
    "p7_zm_der_light_vacuum_tube": ((-5.5, -6.772, 0.0), (5.5, 6.772, 24.403)),
    "p7_zm_der_light_wall_mount": ((74.933, -2.443, -7.037), (106.956, 2.443, 7.037)),
    "p7_zm_der_signage_animal_lab": ((-21.809, -0.897, -4.125), (21.809, 0.0, 4.125)),
    "p7_zm_der_signage_garage": ((-17.149, -0.897, -4.125), (17.149, 0.0, 4.125)),
    "p7_zm_der_signage_office_maxis": ((-17.149, -0.897, -4.125), (17.149, 0.0, 4.125)),
    "p7_zm_der_signage_steps": ((-12.75, -0.846, -9.0), (12.75, 0.0, 9.0)),
    "p7_zm_der_storefront_signage_1": ((-75.992, -3.054, -0.319), (75.822, 2.943, 40.822)),
    "p7_zm_der_storefront_signage_2": ((-75.992, -3.054, -0.319), (75.822, 2.943, 40.822)),
    "p7_zm_der_storefront_signage_4": ((-75.992, -3.054, -0.319), (75.822, 2.943, 40.822)),
    "p7_zm_der_switch_box": ((-32.0, -16.604, 0.0), (32.0, 0.0, 106.0)),
    "p7_zm_der_switch_box_door_right": ((-33.75, -0.354, 0.5), (0.354, 2.252, 104.0)),
    "p7_zm_der_trap_control_box": ((-0.0, -8.0, -19.59), (9.984, 11.249, 7.993)),
    "radiant_omni_light": ((-2.301, -2.301, -4.984), (2.301, 2.301, 2.301)),
    "radiant_omni_light_build": ((-2.301, -2.301, -4.984), (2.301, 2.301, 2.301)),
    "radiant_spot_light": ((-2.365, -2.365, -2.05), (2.365, 2.365, 2.049)),
    "radiant_spot_light_build": ((-2.365, -2.365, -2.05), (2.365, 2.365, 2.049)),
    "veh_t7_city_car_static_dead": ((-64.725, -35.912, -0.469), (65.52, 36.461, 58.93)),
    "veh_t7_civ_car_compact": ((-67.205, -34.483, -0.342), (65.727, 34.483, 61.847)),
    "veh_t7_civ_city_car_dest_attach": ((-64.848, -35.214, 7.982), (65.221, 35.214, 62.732)),
    "veh_t7_civ_city_car_destructible": ((-64.453, -36.708, -0.539), (66.015, 36.708, 65.696)),
    "veh_t7_civ_city_car_vista": ((-63.38, -34.926, 0.0), (64.938, 34.926, 63.538)),
    "veh_t7_civ_citycar_spwn_antenna": ((-37.679, -0.342, 62.172), (-35.861, 0.342, 65.696)),
    "veh_t7_civ_citycar_spwn_grill": ((61.07, -12.621, 20.889), (66.015, 12.621, 30.989)),
    "veh_t7_civ_citycar_spwn_mirror_int": ((14.35, -4.596, 53.881), (16.796, 4.532, 59.005)),
    "veh_t7_civ_citycar_spwn_mirror_l": ((20.735, 28.264, 37.918), (26.728, 36.708, 44.109)),
    "veh_t7_civ_citycar_spwn_mirror_r": ((20.735, -36.708, 37.918), (26.728, -28.264, 44.109)),
    "veh_t7_civ_citycar_spwn_skirt_l": ((-29.845, 27.159, 7.982), (30.615, 35.05, 23.592)),
    "veh_t7_civ_citycar_spwn_skirt_r": ((-29.845, -35.05, 7.982), (30.615, -27.159, 23.592)),
    "veh_t7_civ_citycar_spwn_visor_l": ((9.758, 5.683, 54.386), (12.524, 20.13, 58.194)),
    "veh_t7_civ_citycar_spwn_visor_r": ((5.684, -20.37, 57.049), (10.233, -5.918, 58.432)),
    "veh_t7_civ_forklift_modular_attachment_cab": ((-44.67, -24.362, 23.923), (21.493, 24.362, 89.385)),
    "veh_t7_civ_forklift_modular_attachment_forklift": ((24.046, -19.237, 0.374), (96.419, 19.237, 91.598)),
    "veh_t7_civ_forklift_modular_decals_base": ((-62.96, -24.086, 15.091), (6.288, 24.086, 48.501)),
    "veh_t7_civ_forklift_modular_decals_forks": ((29.921, -15.885, 28.628), (39.67, 15.885, 74.213)),
    "veh_t7_civ_forklift_modular_manned_forklift": ((-62.96, -25.185, -0.15), (30.24, 25.185, 49.489)),
    "veh_t7_civ_gt": ((-92.756, -44.916, 0.089), (111.013, 44.639, 56.041)),
    "veh_t7_civ_license_plate_cairo": ((0.136, -6.102, -4.429), (0.466, 6.244, 2.172)),
    "veh_t7_civ_license_plate_mount_short": ((-0.397, -5.907, -3.88), (0.324, 5.907, 2.041)),
    "veh_t7_civ_license_plate_zurich": ((0.098, -10.032, -2.53), (0.439, 9.916, 2.134)),
    "veh_t7_civ_truck_semi_cab_trailer": ((-66.332, -65.687, -1.0), (202.422, 65.687, 166.914)),
    "veh_t7_mil_lsv": ((-127.628, -63.372, 15.496), (124.04, 63.372, 110.184)),
    "veh_t7_mil_lsv_engine": ((40.99, -33.849, 56.981), (116.091, 33.849, 81.622)),
    "veh_t7_mil_lsv_ext_parts": ((-58.569, -33.065, 85.121), (37.713, 33.065, 119.995)),
    "veh_t7_mil_macv_wheel_attach": ((90.294, 51.253, -0.618), (142.603, 74.548, 51.69)),
    "veh_t7_tu1_train_boxcar": ((-224.556, -76.609, -0.223), (224.556, 76.544, 176.23)),
}

#: ``name -> (low, high)`` in the model's **drawn** frame: :data:`CATALOGUE_BOX`
#: with each moved root bone taken out (44 models: the duct kit,
#: the DER light fixtures, the consumer-grade monitor, the beige drape, city
#: car parts).  A box that is not the raw catalogue box passes through, so a
#: hand-cut box is never corrected twice.
MODEL_BOX: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = drawn_boxes(CATALOGUE_BOX)


#: ``name -> height of the seat above the model's own base``, for the seats
#: something is set down on.  A box's top is a chair's backrest, not where
#: a thing left on the chair rests, so the layout check (``Z44``) would call
#: anything on a seat a floater.  Measured, not estimated: the highest
#: vertex of the model's converted LOD0 mesh (``*_lod0.glb``)
#: within 6 units of its centre line and between y -10 and +5 of its own
#: frame, i.e. the middle of the cushion, clear of the arms and the back.
#: ``p7_chair_waiting_room_01_blue``: 18.845 of a 34.865 box.
SEAT_TOP: Mapping[str, float] = {
    "p7_chair_waiting_room_01_blue": 18.845,
}


#: ``name -> the tops of its boards, in the model's own frame``, lowest
#: first, for the shelving units things are set down *inside*.  A box's top
#: is only the top shelf, so without these the layout check (``Z44``) calls
#: anything on an inner board a floater, and the placer could only use the
#: top.  Measured, not estimated: the upward-facing triangles of the LOD0
#: mesh (the converted ``*_lod0.glb``), summed by height, one band
#: per board (each 2,600 to 3,050 square units, nothing else over 300).
#: Both sit inside :data:`MODEL_BOX`: the lab shelf's box runs
#: 0.433 to 97.472 (its posts stand 1.7 over the top board), the vintage
#: one's 0 to 85.713 (its frame stands 5.8 over its top board: a thing set
#: on its box top floats over the board, so set it on the last board).  Use
#: :func:`shelf_boards` for world heights.
SHELF_BOARDS: Mapping[str, tuple[float, ...]] = {
    "p7_shelf_metal_lab_01": (10.85, 23.35, 34.77, 47.57, 59.87, 71.84, 83.41, 95.78),
    "p7_shelf_industrial_vintage_96": (23.44, 51.91, 79.94),
}


def shelf_boards(model: str, base_z: float) -> tuple[float, ...]:
    """World heights of *model*'s board tops once its box's underside rests
    on *base_z* (what :func:`zmforge.dressing.on_floor` does); empty for a
    model with no boards measured."""
    boards, box = SHELF_BOARDS.get(model), MODEL_BOX.get(model)
    if not boards or box is None:
        return ()
    return tuple(round(base_z + board - box[0][2], 3) for board in boards)


#: ``name -> (centre x, centre y, radius about that centre)``, the plan
#: projection of :data:`MODEL_BOX`.  Derived rather than typed out twice: the
#: radius is the **circumscribed** one, ``hypot(dx, dy) / 2``, because these
#: are placed at an arbitrary yaw and a box turned forty-five degrees needs
#: its diagonal, not its side.
PLAN_BOX: Mapping[str, tuple[float, float, float]] = {
    name: (
        round((low[0] + high[0]) / 2.0, 1),
        round((low[1] + high[1]) / 2.0, 1),
        round(math.hypot(high[0] - low[0], high[1] - low[1]) / 2.0, 1),
    )
    for name, (low, high) in MODEL_BOX.items()
}


# --------------------------------------------------------------------------
# What is solid, and what a player walks through
# --------------------------------------------------------------------------
# HOW A STOCK MODEL IS MADE SOLID, measured on the mod tools install, not
# assumed.  ``cod2map64`` reads ``use_collmap "1"`` on a ``misc_model`` and
# bakes the brush collmap named after that model in ``share\raw\collmaps``
# into the static BSP.  Three things were measured on a sealed one-room probe
# holding 25 copies of one model, compiled four ways:
#
#   * no key at all         BSP 26,060  navmesh 6,678   walk-through
#   * ``no_collmap "1"``    BSP 26,484  navmesh 6,678   walk-through
#   * ``bake_collision "1"``BSP 26,584  navmesh 6,678   walk-through
#   * ``use_collmap "1"``   BSP 31,176  navmesh 7,315   SOLID
#
# The navmesh moving is the proof it is collision and not bytes: the zombies'
# path grid now routes around the crates.  Two further measurements settle how
# the collmap is found, because the answer decides whether this can work at
# all for Treyarch's models:
#
#   * ``p7_shelf_metal_lab_01`` with ``use_collmap "1"`` grew the BSP by 28
#     bytes and did not move the navmesh -- nothing was baked.  It ships no
#     ``share\raw\collmaps\p7_shelf_metal_lab_01.map``.
#   * Copying any collmap to that filename made the same map bake it: BSP
#     26,636 -> 31,304, navmesh 6,678 -> 7,315.
#
# So the lookup is **by filename, at compile time**, not through the model's
# GDT and not through its bullet-collision model.  Only 26 of this palette's
# 123 models ship a stock collmap, so the rest need one generated -- a box
# around the model's own measured bounding volume, which is exactly the shape
# Treyarch's own prop collmaps are (``zmforge.props.collision``).  A generated
# box also cannot repeat ``p7_cai_watertank_body``'s trick of reaching below
# the visible mesh and leaking the map, because it *is* the visible mesh's
# box.

#: A prop is solid when it is tall enough to stop the player, **however thin
#: it is**, or low and broad enough to be a thing he steps onto.  Both numbers
#: are about the player, not about the art.
#:
#: THE THINNESS TEST WAS WRONG, measured on a test map.  The
#: rule used to demand 20 units of height *and* 14 units through the thin
#: plan axis, and the second half let two whole families of prop through as
#: ghosts.  Nineteen 12 x 12 x 30 concrete bollards, a row of pillars a
#: player runs straight through, failed it on 12 units of thickness, and a
#: thing 30 units tall is not a sheet however narrow it is: a bollard, a
#: lattice mast, a column and a ladder are all narrow and all stop you.
#:
#: THE HEIGHT TEST WAS ALSO WRONG, from the same build.  Twenty 132 x 70 x 12
#: metal military pallets, flat things that read as crates, are
#: only 12 units tall and failed the 20.  A pallet is not something you walk
#: through, it is something you step onto, and the engine's own step height
#: says the player can.  So a low thing with a broad footprint is solid too.
#:
#: What stays walk-through is decided by name, not by size
#: (:data:`SOLID_OVERRIDE`): foliage, bedding, paper, cloth and hanging
#: lights.  Litter that stops the player is what makes a room unpleasant to
#: cross, so a sheet of paper (13 x 10 x 0.2) and a newspaper (40 x 35 x 2.3)
#: fail both tests on their own and a coffee mug fails them on height.
SOLID_MIN_HEIGHT = 20.0

#: A prop shorter than :data:`SOLID_MIN_HEIGHT` is still solid when it is at
#: least this tall and this broad: something the player steps onto rather than
#: over.  A pallet, a planter and a low crate are all this shape.
STEP_ON_MIN_HEIGHT = 8.0

#: and the smaller of its two horizontal sides must be at least this for the
#: step-on test.  Below it there is nothing to stand on.
STEP_ON_MIN_FOOTPRINT = 30.0

#: A floor prop shorter than this is walk-through by default, however broad.
#: Pumpkins and low gravestones baked as step-on
#: solids are what players trip on -- a lip the player's step-up climbs with a
#: jolt, in the middle of a run.  18 is the player's own step; anything under
#: it is walked over, and a collmap on it only adds the bump.
SMALL_PROP_HEIGHT = 18.0

#: Where judgement beats the measurement, by name, with the reason.  This is
#: the hook a recipe reaches for when a particular model is wrong: a scene can
#: also override one placement at a time with ``solid=`` on :class:`One`,
#: :class:`Row` or :class:`Fill`.
SOLID_OVERRIDE: Mapping[str, bool] = {
    # Leaves and stalks.  Big enough to pass the rule, and stopping dead in a
    # hedge is worse than walking through one.
    "p7_foliage_grass_tall_cluster_med": False,
    "p7_foliage_tree_acacia_bush": False,
    "p7_foliage_palm_lipstick_sml": False,
    "p7_foliage_hedge_box_48_48_36": False,
    "p7_foliage_weed_cluster_lrg": False,
    "p7_foliage_plant_aloe_small": False,
    # Overhead.  These sit on the floor only when a scene stands everything
    # on the ground; solid, they would be knee-high walls.
    "p7_light_chandelier_hologram": False,
    "p7_light_hanging_modern_02": False,
    "p7_light_fixture_led_wall_01": False,
    # Bedding.  Flat enough to fail the rule anyway; named so nobody re-adds
    # it on a whim, because a mattress you cannot cross blocks a cell.
    "p7_bed_mattress_barrack": False,
    "p7_bed_mattress_barrack_made_v2": False,
    "p7_bed_sheet_barrack_02": False,
    # Narrow but far too tall to walk through: a 130-unit column.  The height
    # test alone now covers it; kept because the judgement is right and a
    # future change to the numbers should not quietly reverse it.
    "p7_rebar_column_128": True,
    # Lattice masts.  The size rule makes these solid and the generated
    # collmap is a box, and a 42 x 48 box around a mast that is mostly air is
    # a lie the player walks into.  Solid, two of them in a room
    # reached by one doorway leave the compiled navmesh with no surface a
    # zombie can path to in that room.  Walk-through, with every other solid
    # prop unchanged, H1 is clean.
    "p6_antenna_rooftop": False,
    "p7_cell_antenna_roof": False,
}


def _kit_solidity() -> Mapping[str, bool]:
    """``name -> solid`` for the props this project converts itself.

    Read off :mod:`zmforge.props.library` rather than decided again here.  That
    library is where each kit prop's ``solid`` flag is authored, it is what the
    kit build reads when it decides whether to cut a bullet mesh and a collmap
    at all, and it is what check ``Z21`` reads when it calls a placed entity
    that disagrees with it an **error**.  A second opinion in this module would
    therefore not be a difference of judgement, it would be a build that fails.

    Imported at module scope because ``zmforge.props.library`` is plain
    dataclasses with no dependencies of its own -- the heavy half of that
    package (``build``, and Pillow behind it) is reached through
    ``zmforge.props``, and ``zmforge.texture`` imports lazily, so this costs a
    bare install nothing.
    """
    from ..props.library import PROPS as KIT_PROPS

    return {entry.name: entry.solid for entry in KIT_PROPS}


KIT_SOLID: Mapping[str, bool] = _kit_solidity()


def is_solid(name: str) -> bool:
    """Whether this model should stop the player, by rule then by name.

    Two ways to qualify: tall enough to stop him, however thin, or low and
    broad enough to be something he steps onto.
    """
    if name in KIT_SOLID:
        return KIT_SOLID[name]
    # Nothing mounted off the floor stops the player.  A clock on a wall and
    # a chandelier on a ceiling are out of his way by construction, and a
    # collision box hanging in the air at head height is the shape that cuts
    # a navmesh in half (:func:`mount_kind`, and the three hanging lights
    # :data:`SOLID_OVERRIDE` already named by hand before the kinds existed).
    if mount_kind(name) != MOUNT_FLOOR:
        return False
    if name in SOLID_OVERRIDE:
        return SOLID_OVERRIDE[name]
    box = MODEL_BOX.get(name)
    if box is None:
        return False
    (x0, y0, z0), (x1, y1, z1) = box
    height = z1 - z0
    if height >= SOLID_MIN_HEIGHT:
        return True
    if height < SMALL_PROP_HEIGHT:
        return False  # stepped over; a collmap is only a bump to trip on
    return (height >= STEP_ON_MIN_HEIGHT
            and min(x1 - x0, y1 - y0) >= STEP_ON_MIN_FOOTPRINT)


#: Kit props whose collision is not their whole box: a tree blocks at its
#: trunk, not across its crown (a crown-wide box would wall off the ground
#: under the branches).  Local frame, like ``MODEL_BOX``: the generated dead
#: trees' trunk is on the origin, 6% of the height to a side (the bark's
#: radius is 11% at the foot, about 7% a quarter of the way up), up to 25% of
#: the height (the plumb part of the trunk, below the limbs,
#: ``props/dead_tree.py``).  ``props/collision.kit_box`` cuts the collmap and
#: the bullet mesh from this, and the reach checks read it as the part of the
#: prop that stands in a player's way.  Added.
KIT_COLLISION_BOX: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "zmf_prop_dead_tree_a": ((-18.0, -18.0, 0.0), (18.0, 18.0, 75.0)),
    "zmf_prop_dead_tree_b": ((-16.2, -16.2, 0.0), (16.2, 16.2, 67.5)),
    "zmf_prop_dead_tree_c": ((-19.8, -19.8, 0.0), (19.8, 19.8, 82.5)),
    "zmf_prop_dead_tree_d": ((-24.0, -24.0, 0.0), (24.0, 24.0, 100.0)),
    "zmf_prop_dead_tree_e": ((-26.4, -26.4, 0.0), (26.4, 26.4, 110.0)),
    # The gamble machine blocks at its cabinet (hood, deck and cash lip in front,
    # the conduit behind) up to the topper; the anchor plate's 0.5-unit rim and
    # the dome camera stay outside it.
    "zmf_prop_gamble_atm": ((-20.5, -17.6, 0.0), (20.5, 17.4, 88.6)),
}


def collision_box(name: str) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """The box a solid prop's collmap is cut from: the model's own bounding
    box, or its :data:`KIT_COLLISION_BOX` entry (a tree's trunk)."""
    return KIT_COLLISION_BOX.get(name) or MODEL_BOX.get(name)


# --------------------------------------------------------------------------
# Which way a thing faces
# --------------------------------------------------------------------------
# A room where every object points north reads as generated, and a room where
# every object points somewhere different reads as a skip full of furniture.
# Three rules, in the order a person furnishing a room would apply them:
#
#   1. A row is a row.  Shelves down an aisle and cabinets along a wall line
#      up, and they should: only the last few degrees wander, so the line
#      survives and the stamped-out look does not.
#   2. Anything solid strewn over a floor is furniture, so it is squared up --
#      against the nearest wall when it is near one, to the nearest quarter
#      turn when it is not -- and then nudged off true.
#   3. Anything the player walks through is loose, so it turns freely.  A
#      dropped newspaper has no correct heading.
#
# And a seat faces the nearest work surface, which is rule 2 with the target
# changed.

#: How far a row's own yaw may wander from the line it is on, in degrees.
#: Enough to read as placed by hand, far too little to break the line: at 5
#: degrees the end of a 113-unit shelf moves 5 units.
ROW_WANDER = 5.0

#: and how far a squared-up piece of loose furniture may wander.  Larger,
#: because nothing depends on it lining up with its neighbour.
FILL_WANDER = 12.0

#: How close to a wall a prop has to be for the wall to decide its heading.
#: Measured against this palette: the deepest piece of furniture in it is 96
#: units through, so anything inside this band is plausibly against the wall.
WALL_REACH = 72.0

#: How far a seat will look for something to face.
SEAT_REACH = 132.0

#: The clear floor a free-standing run of solid props has to leave between
#: its pieces.  N2's measured navmesh corridor width is 31 units, so 40 is
#: that plus a margin.  Without it a row of 42-to-79-unit machines spaced 32
#: units apart is not a row, it is a fence: measured on the compiled navmesh,
#: two such rows across a room can cut tens of thousands of square units of
#: floor off from every zombie spawn.  A row **against a wall** is exempt, because a
#: continuous bank of shelving along a wall blocks nothing.
ROW_GAP = 40.0

#: WHERE THINGS GO, measured rather than reasoned.  Five shipped ``zm_giant``
#: interior prefabs, 3,927 ``misc_model`` entities, read with
#: each model's centre taken from its own converted bounding box rather than
#: its origin:
#:
#:   prefab                       <=16u  <=32u  <=48u  median  parallel/perp/other
#:   zm_giant_warehouse_office     84%    94%    98%      2      41 / 33 / 25
#:   zm_giant_warehouse            76%    85%    91%      7      36 / 37 / 27
#:   zm_giant_mainframe_area       73%    85%    92%      4      41 / 22 / 37
#:   zoneb_pack_a_punch_area       89%    97%    99%      2      61 / 23 / 16
#:   zm_giant_hotel                92%    99%   100%      3      41 / 33 / 26
#:
#: (distance from the model's centre to the nearest vertical brush face, and,
#: for the ones within 48 units of one, how its longer plan side lies against
#: that face).  Two things fall out and neither was obvious.  **Their props
#: live against the brushwork**: three quarters to nine tenths of every model
#: in a room is within 16 units of a wall, a pillar or a ledge, and the middle
#: of the floor is empty.  And **the heading is a mix, not a rule**: parallel
#: is the plurality at 36-61%, perpendicular is a solid 22-37%, and a
#: deliberate 16-37% sits at neither.
#:
#: The same measurement on a generated interior before this rule: median 25 units, 32%
#: within 16, and 36 / 29 / 35.  The headings were already in their range; the
#: distances were not, which is why the rooms read as things standing about in
#: the open rather than a room somebody furnished.
EDGE_SHARE = 0.75

#: How deep the band along a fill's own edge is, in units.  A 48-unit band
#: holds the deepest piece of furniture in this palette with its back on the
#: wall.
EDGE_BAND = 48.0

#: Their nearest-neighbour distances, same five prefabs: median 5 to 10 units,
#: 87% to 99% of models within 32 units of another, and 15% to 23% of them
#: standing on another model's top face.  A generated interior already measures 7, 83%
#: and 25%, so nothing here tries to change the clustering.
CLUSTERED_WITHIN_32 = (0.87, 0.99)

#: Which way a model faces in its own local frame, in degrees, measured from
#: the converted mesh rather than guessed: the backrest's plan centroid above
#: 70% of the model's height against the seat's between 30% and 55% of it.
#: The separation is 5 to 15 units on one axis and under 0.1 on the other for
#: every entry, so none of these is a close call.  Aiming a seat without this
#: is how ten of eleven wall buys once shipped facing their own walls (Z23).
MODEL_FRONT: Mapping[str, float] = {
    "p7_chair_lab_01": -90.0,
    "p7_chair_wood_fancy_01": -90.0,
    "p7_chair_waiting_room_01_blue": -90.0,
    "p7_sgen_chair_dining_future": 0.0,
}


def _is_surface(name: str) -> bool:
    """A table, desk or counter: the thing a seat is pulled up to."""
    box = MODEL_BOX.get(name)
    if box is None:
        return False
    (x0, y0, z0), (x1, y1, z1) = box
    height, long_side = z1 - z0, max(x1 - x0, y1 - y0)
    return 24.0 <= height <= 56.0 and long_side >= 48.0


def _wander(tag: str, salt: int, degrees: float) -> float:
    return (_hash(tag, salt) - 0.5) * 2.0 * degrees


def _long_axis_yaw(name: str, along: str) -> float:
    """The yaw that lays this model's longer plan side along ``along``."""
    box = MODEL_BOX.get(name)
    if box is None:
        return 0.0
    (x0, y0, _z0), (x1, y1, _z1) = box
    local_long_is_x = (x1 - x0) >= (y1 - y0)
    want_x = along == "x"
    return 0.0 if local_long_is_x == want_x else 90.0


def _nearest_wall(rooms, point: Point) -> tuple[str, float] | None:
    """``(axis the wall runs along, distance)`` for the closest room wall."""
    for _room_id, inside in rooms:
        if not inside.holds_flat(point.x, point.y):
            continue
        if not (inside.mins.z - 8.0 <= point.z <= inside.maxs.z + 160.0):
            continue
        gaps = (
            ("y", point.x - inside.mins.x),  # the west wall runs along y
            ("y", inside.maxs.x - point.x),
            ("x", point.y - inside.mins.y),  # the south wall runs along x
            ("x", inside.maxs.y - point.y),
        )
        return min(gaps, key=lambda g: g[1])
    return None


def triangle_budget(scenes: Sequence["Scene"] = ()) -> tuple[int, int]:
    """``(distinct models, triangles if each were placed once)``.

    The second number is not the map's triangle count -- a model placed
    forty times is forty times its own triangles -- so :func:`furnish`
    reports the real total.  This is the cheaper sanity check: a palette
    whose *unique* models already run to six figures is one heavy model away
    from trouble.
    """
    seen: dict[str, int] = {}
    for models in PALETTE.values():
        for name, _size, tris in models:
            seen[name] = int(tris)
    return len(seen), sum(seen.values())


def _tris(name: str) -> int:
    for models in PALETTE.values():
        for entry, _size, tris in models:
            if entry == name:
                return tris
    return 0


# --------------------------------------------------------------------------
# What a model *is*, which a scatter rule has no way of knowing
# --------------------------------------------------------------------------
# The vocabulary lives in :mod:`zmforge.blueprint.catalogue` beside the rest of
# what this package knows about stock models, so that
# :func:`zmforge.verify.playtest.check_route_props` can use it without a
# recipe import.  Re-exported here because a scene author reads this module.
#
# WHAT THIS GUARDS.  ``p7_cai_staircase_01`` -- 109 x 191.5 x 131.5, the
# largest model in the palette -- sits in the ``tall_hall`` theme between a
# pallet and a chandelier.  :class:`Row` deals a theme out by index and
# :class:`Fill` draws from it at random, so a scene can put one on any floor
# of a tall room.  It climbs 131.5 units, so in a room whose floors are
# further apart than that it arrives at nothing from any position, and one
# dealt near a balcony edge can hang part of its footprint over open air.
# Every other check passes such a map, because the only check that asks
# whether stairs work (``Z19``) asks it of *brushwork*, and
# because ``Z25`` floods the map for things that are **stranded**: a
# staircase that goes nowhere strands nobody, so a useless one is invisible
# to a reachability argument by construction.
#: A FLAT PANEL IS NOT CLUTTER.  Measured off :data:`MODEL_BOX` rather than
#: named, because the names do not say it: ``p7_pallet_metal_military_01`` is
#: a 132 x 70 x 12 framed metal sheet that reads on screen as a corrugated
#: panel, and the two barrack mattresses are the same shape.  A model counts
#: as a panel when both its plan sides are big and the thinnest of its three
#: dimensions is a quarter or less of its longest.  On this palette that is
#: exactly those three models; the next thing down the list is a concrete
#: rubble pile at 0.35 and a planter at 0.42, so none of it is a close call.
#:
#: WHAT THIS GUARDS, measured on a test map.
#: Eight copies of that pallet were dealt out of a hall's theme by
#: :class:`Fill`, and they landed on and across its lower
#: flight and its landing at the free yaws a fill hands out, overlapping each
#: other, which reads as junk on the stairs.  A sheet has no
#: pose a scatter rule can put it in: laid flat in the open it is a slab in
#: the middle of the floor, and tipped at a fill's yaw over a stair it is a
#: ramp to nowhere.  Strewing is the wrong verb for the shape, so a panel is
#: not strewn -- :func:`_model` steps past it exactly as it steps past a
#: route model, and a scene that wants one says so with :class:`One`.
PANEL_MIN_SHORT_SIDE = 40.0

#: and its longer plan side has to reach this, so a floor tile is not a panel.
PANEL_MIN_LONG_SIDE = 64.0

#: Thinnest dimension over longest, at or under which the model is a sheet.
PANEL_THIN_SHARE = 0.25


def is_panel_model(name: str) -> bool:
    """Whether this model is a large flat sheet rather than an object."""
    box = MODEL_BOX.get(name)
    if box is None:
        return False
    (x0, y0, z0), (x1, y1, z1) = box
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    if min(dx, dy) < PANEL_MIN_SHORT_SIDE or max(dx, dy) < PANEL_MIN_LONG_SIDE:
        return False
    return min(dx, dy, dz) <= PANEL_THIN_SHARE * max(dx, dy, dz)


# --------------------------------------------------------------------------
# What a model hangs on: floor, wall or ceiling
# --------------------------------------------------------------------------
# WHAT THIS GUARDS, measured on a built map: 105 props were wall or ceiling fixtures dealt onto the floor --
# clocks, caution signs, notice boards and picture frames standing in the
# tile with half their body under it, eight LED wall fixtures, fifteen duct
# sections and six sinks, and sixteen chandeliers and hanging lights that
# were *entirely* below the floor and therefore invisible.  The placer had no
# idea: a scene says "a row of signage along this wall" and the row put each
# sign down as though it were a chair.
#
# HOW THE KIND IS DECIDED, and why the obvious rule is wrong.  The obvious
# rule -- "a z-centred or z-negative box is not floor-standing" -- fails on
# this palette, measured: 24 models carry a box centred on their own origin
# and every one of them stands on a floor.  Rubble, rock, brick, plaster,
# board splinters, both barrack mattresses, the pillow, the sheet, the
# shovel, the chainlink rail and the 130-unit rebar column are all authored
# about their middle (``z0 / height`` is -0.50 for all of them, exactly as it
# is for a wall clock).  A box tells you the origin is not at the bottom; it
# does not tell you what the origin is *for*.
#
# So: **a box wholly below its own origin hangs from something** -- nothing
# stands on a floor with its entire body under the point it is placed at --
# and that is decided by measurement.  Everything else that is mounted is
# decided by **family name**, which is the only thing that separates a
# 32 x 5.8 x 32 wall clock from a 24 x 11 x 14 lump of concrete.  The floor
# case needs no rule at all, because it is what is left.
#: ``mount_kind`` for a model whose geometry hangs below its own origin.
MOUNT_CEILING = "ceiling"

#: for one that mounts on a vertical surface at a sill height.
MOUNT_WALL = "wall"

#: and for everything the player could trip over.
MOUNT_FLOOR = "floor"

#: Name fragments of the families that hang from a ceiling.  Both are lights
#: whose box is wholly below the origin, so the measurement agrees with the
#: name and :func:`mount_kind` would reach the same answer without them;
#: they are written out because the agreement is the point.
CEILING_FAMILIES = ("light_chandelier", "light_hanging")

#: Name fragments of the families that mount on a wall.  One line per family,
#: with what its box looks like, because a box alone cannot tell these from
#: rubble:
#:
#:   ``signage``            z-centred, 0.2 to 0.7 units through
#:   ``clock_metal_wall``   z-centred, 32 x 32 face, 5.8 through
#:   ``picture_frame``      z-centred, 1 unit through
#:   ``bulletin_board``     z-centred, 2.2 through, body on +y
#:   ``light_fixture_led``  z-centred, 9.4 through, body on +x
#:   ``light_cage_02``      5.5 through on +x, box from the origin up: a caged
#:                          bulkhead (a test map's track lamps)
#:   ``wall_mount``         the air-conditioner's own name says so
#:   ``duct_metal``         z-centred round duct, runs along a wall or a soffit
#:   ``sink_``              wholly below the origin: a basin hung off a wall
#:   ``teleporter_mf_ladder``  box starts 122 units *above* the origin, so on
#:                             a floor it hovers; it is a ladder up a wall
#:   ``barricade_board``    z-centred plank, 2 through: nailed over a window
#:   ``poster_anatomy``     z-centred, 3 to 4 through, body on +x
WALL_FAMILIES = (
    "signage",
    "clock_metal_wall",
    "picture_frame",
    "lobby_picture",
    "bulletin_board",
    "light_fixture_led",
    "light_cage_02",
    "wall_mount",
    "duct_metal",
    "sink_",
    "teleporter_mf_ladder",
    "barricade_board",
    "poster_anatomy",
)


def mount_kind(name: str) -> str:
    """Whether this model stands on a floor, hangs on a wall or on a ceiling.

    One of :data:`MOUNT_FLOOR`, :data:`MOUNT_WALL`, :data:`MOUNT_CEILING`.
    A model nothing knows about is floor-standing, which is the safe answer:
    it is placed the way everything was placed before this existed.

    The measurement is
    :func:`zmforge.placement.relations.mount_kind_of_box`, so the rule that
    chooses a mounting and the rule ``Z44`` judges one by are one function.
    The two name lists stay in front of it as hints rather than as the rule,
    for the reason that function's own docstring gives: over this palette the
    box settles *ceiling* outright and narrows *wall* to fifteen candidates,
    five of which -- a rebar column, a shovel, a cable coil and two pieces of
    plaster rubble -- are z-centred objects rather than fixtures, so
    :data:`WALL_FAMILIES` is what tells those apart.  Checked over all 152
    names this module knows: the swap changes no answer.
    """
    if any(word in name for word in CEILING_FAMILIES):
        return MOUNT_CEILING
    if any(word in name for word in WALL_FAMILIES):
        return MOUNT_WALL
    kind = mount_kind_of_box(MODEL_BOX.get(name))
    return MOUNT_CEILING if kind is MountKind.CEILING else MOUNT_FLOOR


def _mount_face(name: str) -> float:
    """Which way a mounted model looks, in its own local frame, in degrees.

    Measured off the box rather than named: a fixture is authored with its
    back on the plane its origin sits in, so its body lies wholly to one side
    of that origin along its **thin plan axis**, and the side the body is on
    is the side it faces.  Every wall family in this palette agrees: the
    signs, the clock and the frame carry their body on -y and look south at
    yaw 0; the bulletin board carries its on +y and looks north; the LED
    fixture's is on +x.
    """
    box = MODEL_BOX.get(name)
    if box is None:
        return -90.0
    (x0, y0, _z0), (x1, y1, _z1) = box
    if (x1 - x0) <= (y1 - y0):
        return 0.0 if (x0 + x1) >= 0.0 else 180.0
    return 90.0 if (y0 + y1) >= 0.0 else -90.0


#: How far above its room's floor a wall fixture's own box bottom goes.  One
#: number for every family, and the model's own z-range does the rest
#: (:func:`_mounted_place` emits ``floor + WALL_SILL - z0``), which is the
#: plan-centre correction of :func:`_placed_origin` applied to the third
#: axis.  At 48 a 32-unit clock reads 48 to 80 and a 36-unit notice board 48
#: to 84, which is head height for a 60-unit player, and the map's wall
#: pictures hang at 134 to 154 above their floors, so nothing here can cover
#: one.
WALL_SILL = 48.0

#: A mounted fixture never hangs lower than this above the floor under it,
#: whatever its sill works out at after the ceiling clamp.
WALL_SILL_MIN = 16.0

#: How much clear air a wall or ceiling fixture leaves under the ceiling.
CEILING_CLEAR = 4.0


def is_strewable(name: str) -> bool:
    """Whether a :class:`Row` or a :class:`Fill` may deal this model out.

    A route model is an instruction and a panel is a sheet; neither is an
    object a scatter rule can put down anywhere and have it read right.
    """
    return not is_route_model(name) and not is_panel_model(name)


@lru_cache(maxsize=None)
def _unlinkable(name: str) -> bool:
    """Whether the install ledger says *name* will not link with the
    tools (``xmodels_unlinkable``: a missing ``.xmodel_bin``, a missing or
    placeholder image, or a TIFF layout the linker cannot read).  Check
    ``Z13`` refuses such a model, so a palette pick skips it the way a strewn
    pick skips a panel: ``p7_rebar_column_128`` in ``tall_hall`` stopped
    a test map link on its 16-bit grey+alpha cap image.
   No ledger, nothing skipped."""
    from ..blueprint.installed import judge_misc_model

    ledger = _install_ledger()
    return ledger is not None and judge_misc_model(name, ledger) == "unlinkable"


@lru_cache(maxsize=1)
def _install_ledger():
    from ..blueprint.installed import load_ledger

    return load_ledger()


def _model(
    theme: str, index: int, *, strewn: bool = False
) -> tuple[str, tuple[float, float, float], int]:
    """One entry of a theme, wrapping the index so a scene cannot run off the end.

    ``strewn`` is what :class:`Row` and :class:`Fill` pass.  It advances past
    any entry :func:`is_strewable` rejects, so the index a scene was written
    against still means "start here" and the placement still happens -- it
    just happens with the next model in the theme that is an object rather
    than an instruction.  Skipping rather than dropping keeps a scene's model
    count, and therefore its look, what the scene wrote.

    A theme of nothing but routes and panels is an authoring mistake and says
    so, rather than looping forever.
    """
    models = PALETTE.get(theme)
    if not models:
        raise KeyError(f"no models in palette theme {theme!r}")
    for offset in range(len(models)):
        entry = models[(index + offset) % len(models)]
        if _unlinkable(entry[0]):
            continue
        if not strewn or is_strewable(entry[0]):
            return entry
    if not strewn:
        raise ValueError(
            f"palette theme {theme!r} holds no model the linker can build "
            f"({', '.join(entry[0] for entry in models)}; installed_assets.json "
            "xmodels_unlinkable)"
        )
    raise ValueError(
        f"palette theme {theme!r} holds nothing a scatter rule may place -- "
        f"every entry is a route model or a flat panel "
        f"({', '.join(entry[0] for entry in models)}); a Row or a Fill has "
        "nothing it may place, so the scene wants One() instead"
    )


# --------------------------------------------------------------------------
# The three placement rules
# --------------------------------------------------------------------------
#: How many points a :class:`Fill` may draw for each piece it wants.  It used
#: to be six, which was enough when the only reason to refuse a point was a
#: scene's own ``avoid`` list.  It is not enough now that a fill also draws
#: again for a staircase, a doorway, a walking lane and a large prop already
#: standing there: measured on a test map, six attempts
#: left the map 506 models short of what its scenes asked for, and the rooms
#: that lost them were the small ones, where a doorway circle takes a real
#: share of the floor.  Raising it cannot move a piece that was already
#: placed -- each attempt is a separate hash of the scene and the attempt
#: number, and the loop stops the moment the fill has its count.
FILL_ATTEMPTS = 24

#: A scene's own floor height, by name, resolved by :func:`furnish`.
SCENE_LEVEL = "@scene"


@dataclass(frozen=True, slots=True)
class One:
    """One model, exactly there, at exactly that yaw."""

    theme: str
    index: int
    x: float
    y: float
    z: str | float
    yaw: float = 0.0
    scale: float = 1.0
    #: ``None`` lets :func:`is_solid` decide from the model's own size.
    solid: bool | None = None


@dataclass(frozen=True, slots=True)
class Row:
    """``count`` copies evenly spaced between two points.

    A row is what most dressing actually is: shelves down an aisle, chairs
    along a table, pipes along a wall, bollards along a path.  ``spread``
    cycles through a theme rather than repeating one model, because a row of
    identical objects is the thing that makes a generated room look generated.
    """

    theme: str
    x0: float
    y0: float
    x1: float
    y1: float
    count: int
    #: ``SCENE_LEVEL`` means "the floor of the room this scene dresses",
    #: which is what most of a room's dressing stands on and is therefore
    #: the default; a name or a number overrides it for the pieces that sit
    #: on a balcony or a gallery inside the same room.
    z: str | float = SCENE_LEVEL
    yaw: float = 0.0
    first: int = 0
    spread: int = 1
    yaw_step: float = 0.0
    scale: float = 1.0
    on_terrain: bool = False
    #: How far each piece may wander off the row's own heading, in degrees.
    #: The line survives it; the stamped-out look does not.  A row that has
    #: to be dead straight -- machinery bolted to a wall, a run of pipe --
    #: sets it to zero.
    vary: float = ROW_WANDER
    #: ``None`` lets :func:`is_solid` decide from each model's own size.
    solid: bool | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    """``count`` models strewn over a box, deterministically.

    The jitter is a hash of the scene's own name and the index, so the same
    map always comes out the same, and no two rooms get the same pattern.
    ``avoid`` is a list of ``(x0, y0, x1, y1)`` rectangles nothing lands in:
    doorways, stair wells, and the square in front of anything with a use
    prompt.  They are read as
    :class:`~zmforge.placement.scatter.KeepClear` polygons like every other
    keep-out in this module; see :func:`_avoid_zones`.
    """

    theme: str
    x0: float
    y0: float
    x1: float
    y1: float
    count: int
    z: str | float = SCENE_LEVEL
    avoid: tuple[tuple[float, float, float, float], ...] = ()
    scale: float = 1.0
    #: Which entries of the theme this fill may use, by index.  Empty is all
    #: of them.  It exists for the triangle budget: a fill of two hundred
    #: pieces of clutter has to draw from the cheap end of a theme, and a
    #: theme is ordered by what it is, not by what it costs.
    pick: tuple[int, ...] = ()
    #: Stand each model on the terrain under it rather than at a fixed
    #: height.  Outdoors the floor is a heightfield, so a fixed z either
    #: buries the model or floats it.
    on_terrain: bool = False
    #: ``None`` lets :func:`is_solid` decide from each model's own size.
    solid: bool | None = None
    #: What share of this fill's pieces are drawn into the band along its own
    #: edge rather than anywhere in the box.  Defaults to :data:`EDGE_SHARE`,
    #: which is measured off the shipped maps; a fill that is meant to be a
    #: pile in the middle of a room sets it to zero.
    edge: float | None = None


_CLUTTER_SMALL_MODELS = frozenset(name for name, _size, _tris in PALETTE["clutter_small"])

#: Themes that only a broken room may draw on.  One entry: every model in
#: ``rubble_debris`` is a piece of the building lying where the building
#: broke.  See :attr:`Scene.ruined`.
RUINED_THEMES = frozenset({"rubble_debris"})

#: and the same question asked of one model, because the theme test is not
#: enough on its own: ``clutter_small`` is the litter theme every room draws
#: on and two of its twelve entries are rocky chunks, which is where 71 of
#: the 232 pieces of masonry in finished rooms came from after the themes
#: were keyed.  Broken building, by name; dropped paper, cups, bottles and
#: food wrappers are not in here and go on being strewn everywhere, because
#: people drop those in finished rooms.
RUBBLE_FAMILIES = (
    "debris_concrete",
    "debris_brick",
    "brick_dirty",
    "debris_plaster",
    "debris_wood_board",
    "debris_rockychunks",
    "rubble",
)


def is_rubble(name: str) -> bool:
    """Is this model a piece of a broken building?"""
    return any(word in name for word in RUBBLE_FAMILIES)


#: Floor litter by name: what people drop (paper, folders, cups, bottles,
#: wrappers) and what a building sheds (every ``debris_`` model).  Together
#: with the ``clutter_small`` palette theme this is the one definition of
#: litter; the review caps how much of it counts toward a room's density
#: floor (P2: litter is seasoning, not the meal).  A model
#: only counts as litter where it lies on the floor: the same folder on a
#: desk is surface clutter.
LITTER_FAMILIES = (
    "debris_",
    "office_paper_sheet",
    "office_paper_folder",
    "paper_stack",
    "cleaning_paper",
    "book_office_binder_open",
    "cup_coffee",
    "bottle_plastic",
    "bottle_glass",
)


def is_litter(name: str) -> bool:
    """Is this model the kind of thing that lies around as floor litter?"""
    return (name in _CLUTTER_SMALL_MODELS
            or any(word in name for word in LITTER_FAMILIES))


@dataclass(frozen=True, slots=True)
class Scene:
    """Everything that dresses one room, and the floor it stands on."""

    room: str
    items: tuple[One | Row | Fill, ...] = field(default_factory=tuple)
    level: str = "ground"
    #: IS THIS ROOM BROKEN?  Set on any room where the building itself is
    #: meant to read as industrial or wrecked: a yard, a basement, a gutted
    #: shop.  A scene without it gets **no** :data:`
    #: RUINED_THEMES` dressing at all: no concrete rubble, no broken brick,
    #: no plaster, no splintered board.
    #:
    #: WHY: ``Fill("rubble_debris", ...)`` written into every room's scene as
    #: general-purpose clutter strews masonry debris through finished
    #: interiors, 20 to 50 pieces a room.  A smashed breeze block on an
    #: office's parquet is not clutter, it reads as a bug: the room
    #: around it is intact, so something has to have broken it and nothing
    #: did.  Litter (``clutter_small``) is not affected and still goes
    #: everywhere; people drop paper in finished rooms.
    ruined: bool = False
    #: KEEP THIS ROOM EXACTLY AS IT IS.  A scene marked this way is placed by
    #: the original rules: the zones nothing may stand in, the panel screen and the
    #: interpenetration rule are all skipped for it, and a prop of its that
    #: would block a doorway loses its collision the old way rather than being
    #: moved or dropped, because moving it would change the room.
    #:
    #: Use it sparingly.  It is for a room laid out by hand as a deliberate
    #: set piece, a gag that works because it happens once; generalised into
    #: a rule it is just a placer that repeats itself.  Such a room is pinned
    #: by name, with a test that its props do not move.
    keep_as_is: bool = False


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------
def _hash(text: str, salt: int) -> float:
    """A repeatable number in ``[0, 1)`` from a string and an integer.

    ``hash()`` is salted per process, so it cannot be used: the same map has
    to come out of the same blueprint every time, which is the whole reason
    this package seeds its GUIDs rather than generating them.
    """
    value = 2166136261
    for char in f"{text}:{salt}":
        value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
    return value / 4294967296.0


@lru_cache(maxsize=None)
def _avoid_zones(boxes: tuple[tuple[float, float, float, float], ...]) -> Negatives:
    """A :class:`Fill`'s hand-written ``avoid`` rectangles, as negative shapes.

    The last zone in this module that was not one.  Every other keep-out --
    the doorway lane, the flight, the spawn, the buy apron, the picture -- is
    already a :class:`~zmforge.placement.scatter.KeepClear` polygon read
    through :func:`_no_prop_zone`, and these were a list of four numbers the
    fill loop interpreted itself.  They are the same kind of thing, so they
    are now the same object, and the fill loop has no zone code left in it.

    Cached on the rectangles, because a :class:`Fill` asks this once per
    attempt and there are at most a few dozen distinct lists in the map.

    **The test is still the drawn point, not the footprint.**  That is
    deliberate and it is the only honest swap: a footprint test is strictly
    stricter, it would refuse props these rectangles have never refused, and
    the rectangles were drawn by hand around what the author could see -- a
    machine, a stair well -- with the point test in force.  Widening them to
    footprints is a change of layout to argue on its own evidence, not a
    consequence of moving the zone into the shared vocabulary.
    """
    return Negatives.of(
        KeepClear.rect("avoid", x0, y0, x1, y1) for x0, y0, x1, y1 in boxes
    )


def _height(z: str | float, levels: Mapping[str, float], scene: str) -> float:
    if not isinstance(z, str):
        return float(z)
    return float(levels[scene if z == SCENE_LEVEL else z])


#: Plan bucket for the solid index :func:`_solid_index` builds.
_BUCKET = 256.0

#: How far above a scene's own floor a surface may be and still be the thing
#: a prop stands on.  A counter is 48 tall and a desk 32, so a mug placed at
#: floor height ends up on the desk; a balcony 272 units up does not answer
#: for the floor beneath it.
SURFACE_REACH = 80.0

#: How far below a block top :func:`Blueprint.ground_under` has to be asked
#: before it stops answering with that block.  It allows a surface up to
#: ``STEP_TOLERANCE`` (8) above the hint, so anything less than that plus a
#: unit gets the block back.
STEP_DOWN = 9.0


def _solid_index(bp: Blueprint):
    """Every world solid's half-spaces, bucketed by plan position.

    The test is the one :meth:`Blueprint.light_rooms` uses for lamps -- a
    point is inside a convex solid when it is on the inner side of all of its
    faces -- and the bucket is only there to keep it from being quadratic.
    """
    grid: dict[tuple[int, int], list[list]] = defaultdict(list)
    for solid in bp.world_solids():
        faces = [plane_through(*face.points) for face in solid.faces]
        xs = [point.x for face in solid.faces for point in face.points]
        ys = [point.y for face in solid.faces for point in face.points]
        for gx in range(math.floor(min(xs) / _BUCKET), math.floor(max(xs) / _BUCKET) + 1):
            for gy in range(math.floor(min(ys) / _BUCKET), math.floor(max(ys) / _BUCKET) + 1):
                grid[(gx, gy)].append(faces)
    return grid


def _in_solid(grid, point: Point) -> bool:
    key = (math.floor(point.x / _BUCKET), math.floor(point.y / _BUCKET))
    for faces in grid.get(key, ()):
        if min(face.depth_at(point) for face in faces) > 1e-6:
            return True
    return False


def _room_interiors(bp: Blueprint) -> tuple[tuple[str, "Span"], ...]:
    """Every room's inside, which is the box a prop standing in it must fit."""
    from ..blueprint.elements import Room

    return tuple((room.id, room.interior) for room in bp.elements(Room))


def _placed_origin(name: str, centre: Point, yaw: float, scale: float) -> Point:
    """The origin to emit so the model's own centre lands on ``centre``.

    A scene says where a thing should *be*; the ``.map`` says where its origin
    is, and for half this palette those are not the same point
    (:data:`PLAN_BOX`).  The offset turns with the model, counter-clockwise in
    plan, which is the rotation ``cod2map64`` and the engine both apply
    (``zmforge.blueprint.catalogue``, "Orientation").
    """
    cx, cy, _radius = PLAN_BOX.get(name, (0.0, 0.0, 0.0))
    if cx == 0.0 and cy == 0.0:
        return centre
    angle = math.radians(yaw)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    ox = (cx * cos_a - cy * sin_a) * scale
    oy = (cx * sin_a + cy * cos_a) * scale
    return Point(centre.x - ox, centre.y - oy, centre.z)


def plan_half_extent(name: str, size, yaw: float, scale: float) -> tuple[float, float]:
    """Half the width and depth of the model's plan box *at this yaw*.

    Turning a box turns its footprint, and the axis-aligned box around the
    turned one is ``(dx|cos| + dy|sin|) / 2`` by ``(dx|sin| + dy|cos|) / 2``.
    That is exact, which the circumscribed radius this used to inset by was
    not: a 113 x 31 shelf laid along a wall was held 58.8 units off it by its
    own diagonal, when its back is 15.8 units from its centre.  Measured on
    five shipped ``zm_giant`` interiors, Treyarch's props sit a
    median 2 to 7 units from the nearest vertical brush face and 73% to 92% of
    them are within 16 units of one; ours sat at a median of 25, and this is
    most of the difference.
    """
    box = MODEL_BOX.get(name)
    if box is None:
        dx, dy = float(size[0]), float(size[1])
    else:
        (x0, y0, _z0), (x1, y1, _z1) = box
        dx, dy = x1 - x0, y1 - y0
    angle = math.radians(yaw)
    cos_a, sin_a = abs(math.cos(angle)), abs(math.sin(angle))
    scale = max(float(scale), 0.0)
    return ((dx * cos_a + dy * sin_a) / 2.0 * scale,
            (dx * sin_a + dy * cos_a) / 2.0 * scale)


def _fit_inside(rooms, point: Point, size, scale: float, name: str = "",
                yaw: float = 0.0, *, hug: float = 0.0) -> Point | None:
    """``point`` moved so the model at it fits inside its room, or ``None``.

    WHY THIS IS NOT COSMETIC.  A model is placed by its origin and drawn
    around it, so a row of machinery set fourteen units off a wall puts
    anything wider than twenty-eight units *into* that wall -- and anything
    wider than the wall is thick comes out the other side, in the void.
    Measured: wall rows holding a 171 x 179 generator and a 132 x 132 water
    tank, set fourteen units off a sixteen-unit wall, make ``cod2map64``
    answer ``******* leaked *******`` and write a leakfile.  Bisecting puts
    the leak on exactly the models whose radius reaches past the wall's outer
    face; the same row restricted to a two-unit conduit compiles clean.

    ``hug`` then pulls the piece the rest of the way in, so its back is
    against the wall rather than hanging a foot off it, which is what the
    shipped maps do (see :func:`plan_half_extent`).
    """
    hx, hy = plan_half_extent(name, size, yaw, scale)
    if hx <= 0.0 and hy <= 0.0:
        return point
    for _room_id, inside in rooms:
        if not inside.holds_flat(point.x, point.y):
            continue
        if not (inside.mins.z - 8.0 <= point.z <= inside.maxs.z + 8.0):
            continue
        low_x, high_x = inside.mins.x + hx, inside.maxs.x - hx
        low_y, high_y = inside.mins.y + hy, inside.maxs.y - hy
        if low_x > high_x or low_y > high_y:
            return None  # the room is smaller than the thing
        x = min(max(point.x, low_x), high_x)
        y = min(max(point.y, low_y), high_y)
        if hug > 0.0:
            x, y = _hug(inside, x, y, hx, hy, hug)
        return Point(x, y, point.z)
    return point


def _hug(inside, x: float, y: float, hx: float, hy: float,
         allowance: float) -> tuple[float, float]:
    """Slide a piece the last few units so its back touches the nearest wall."""
    gaps = (
        ("x", x - hx - inside.mins.x, inside.mins.x + hx),
        ("x", inside.maxs.x - hx - x, inside.maxs.x - hx),
        ("y", y - hy - inside.mins.y, inside.mins.y + hy),
        ("y", inside.maxs.y - hy - y, inside.maxs.y - hy),
    )
    axis, gap, target = min(gaps, key=lambda g: g[1])
    if gap > allowance:
        return x, y
    return (target, y) if axis == "x" else (x, target)


def _squared_yaw(name: str, where: Point, free: float, rooms,
                 surfaces: Sequence[tuple[str, Point]], tag: str) -> float:
    """The heading for one solid prop that a :class:`Fill` sited at random.

    A seat is aimed at the nearest work surface, using that model's own
    measured front (:data:`MODEL_FRONT`) so it is pulled up to the desk rather
    than turning its back on it.  Everything else is squared up: laid along
    the nearest wall when it is inside :data:`WALL_REACH` of one, and turned
    to the nearest quarter otherwise.  Both then wander, because a room of
    furniture at exact right angles is the thing that reads as generated.
    """
    front = MODEL_FRONT.get(name)
    if front is not None and surfaces:
        best: tuple[float, Point] | None = None
        for _other, at in surfaces:
            gap = math.hypot(at.x - where.x, at.y - where.y)
            if gap <= 1e-6 or gap > SEAT_REACH:
                continue
            if best is None or gap < best[0]:
                best = (gap, at)
        if best is not None:
            bearing = math.degrees(math.atan2(best[1].y - where.y, best[1].x - where.x))
            return round((bearing - front + _wander(tag, 7, FILL_WANDER)) % 360.0, 1)
    wall = _nearest_wall(rooms, where)
    if wall is not None and wall[1] <= WALL_REACH:
        yaw = _long_axis_yaw(name, wall[0])
        # Either way round is against the wall; which one is a coin the map
        # always flips the same way.
        yaw += 180.0 if _hash(tag, 11) < 0.5 else 0.0
    else:
        yaw = round(free / 90.0) * 90.0
    return round((yaw + _wander(tag, 13, FILL_WANDER)) % 360.0, 1)


def _against_wall(rooms, points: Sequence[Point]) -> bool:
    """Is every piece of this row inside :data:`WALL_REACH` of a room wall?"""
    if not points:
        return True
    for point in points:
        wall = _nearest_wall(rooms, point)
        if wall is None or wall[1] > WALL_REACH:
            return False
    return True


def _thin_a_fence(rows: list[list], rooms, *, free: bool = True) -> list[list]:
    """Turn a free-standing run of solid props into one with gaps in it.

    Walks the row in order and takes out any piece that would close the gap to
    the previous solid one below :data:`ROW_GAP`.  **Takes it out, rather than
    taking its collision away**: a row of machinery the player walks through
    reads as objects blocking doors with no collision, and
    a gap in a row is a row with a gap in it.  A room pinned with
    ``keep_as_is`` is the exception and keeps the old behaviour, because the
    whole point of pinning it is that nothing in it moves.
    """
    if len(rows) < 2:
        return rows
    first, last = rows[0][1], rows[-1][1]
    dx, dy = last.x - first.x, last.y - first.y
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return rows
    ux, uy = dx / length, dy / length
    if _against_wall(rooms, [row[1] for row in rows]):
        return rows
    reach = -1e9
    thinned: list[list] = []
    for row in rows:
        if not row[5]:
            thinned.append(row)
            continue
        name, point, yaw, scale = row[0], row[1], row[2], row[3]
        hx, hy = plan_half_extent(name, row[4], yaw, scale)
        half = abs(ux) * hx + abs(uy) * hy
        at = (point.x - first.x) * ux + (point.y - first.y) * uy
        if at - half < reach + ROW_GAP:
            if not free:
                row[5] = False
                thinned.append(row)
            continue
        reach = at + half
        thinned.append(row)
    return thinned


def _edge_point(item: "Fill", tag: str, attempt: int) -> tuple[float, float]:
    """A point in the band along one of the fill box's four edges.

    Which edge is a hash, so the same map always draws the same room, and the
    depth into the band is a second hash rather than zero, so a run of pieces
    is a line of things against a wall instead of a line ruled on the floor.
    """
    span_x, span_y = item.x1 - item.x0, item.y1 - item.y0
    band = min(EDGE_BAND, max(span_x, span_y) / 3.0)
    along = _hash(tag, attempt * 3)
    # Squared, so the band is a wall people put things against rather than a
    # 48-unit-wide stripe with things spread evenly over it.
    into = band * _hash(tag, attempt * 3 + 1) ** 2
    side = int(_hash(tag, attempt * 17 + 3) * 4) % 4
    if side == 0:
        return item.x0 + span_x * along, item.y0 + into
    if side == 1:
        return item.x0 + span_x * along, item.y1 - into
    if side == 2:
        return item.x0 + into, item.y0 + span_y * along
    return item.x1 - into, item.y0 + span_y * along


# --------------------------------------------------------------------------
# Where no prop may stand
# --------------------------------------------------------------------------
# THE RULE, AND WHY IT CHANGED.  These zones -- the circle round a doorway, a
# barricade landing or a rise struct, the lane from a doorway to the middle of
# its room, and a flight of stairs with its two landings -- began as places a
# prop's **collision** was taken away.  Each one answers a measured
# defect, not a precaution.  Built with collision and no keep-clear, a
# compiled navmesh loses a barricade landing or a rise struct outright, and a
# room with exactly one doorway is cut off from every spawn, nearly all of its
# floor, once a wall row puts a large solid prop across its mouth.
#
# Taking the collision off was the wrong repair: objects then block doors
# without stopping anyone.  Measured on a test map: 911 of its 2,200
# props stood inside one of these zones and **not one of them was solid**;
# 214 were models the size rule of the day called solid and were
# de-solidified purely for standing there.
# A crate standing in a doorway that the player runs through is worse than
# either a crate that stops him or no crate at all, because it tells him the
# map is broken.
#
# So the zones are now **placement** exclusions: a prop is not put there in
# the first place, and nothing is ever de-solidified for where it landed.  A
# :class:`Fill` that draws into one draws again, which is why the rooms keep
# their counts; a :class:`Row` or a :class:`One` aimed into one loses that
# piece, which is the scene saying something the map cannot have.
#: How far from a barricade landing or a rise struct no prop stands.
ENTRY_KEEP_CLEAR = 96.0


def _entry_points(bp: Blueprint) -> tuple[tuple[float, float, float], ...]:
    """Barricade landings and rise structs, as points.

    NOT DOORWAYS, and that is a change made with a measurement.  A doorway is
    covered by its own lane (:func:`_lanes`), which is the shape the thing
    actually needs: 72 units wide, from the opening to the middle of the room.
    A 96-unit *circle* on top of it was the right belt-and-braces while these
    zones only took a prop's collision away, and it is far too much floor now
    that they decide where a prop may stand at all.  Measured with the
    circle: seven corridors and closets
    came out with **no props at all**, 138 models between them, because a
    corridor is narrower than 192 units and a circle that wide over each of its
    two doorways is the whole corridor.  A room stripped bare is not a better
    map than a room with a crate beside the door.

    A barricade landing and a rise struct keep their circle: neither has a
    lane, because neither is an opening the room's own geometry knows about,
    and what arrives there is a zombie climbing in with nowhere else to go.
    """
    cached = getattr(bp, "_zmf_entry_points", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import Spawn, Window

    points: list[tuple[float, float, float]] = []
    for window in bp.elements(Window):
        at = window.barricade_origin
        if at is not None:
            points.append((at.x, at.y, at.z))
    for spawn in bp.elements(Spawn):
        at = spawn.position
        if at is not None:
            points.append((at.x, at.y, at.z))
    found = tuple(points)
    try:
        bp._zmf_entry_points = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


#: Half the width of the lane kept clear of collision between a doorway and
#: the middle of the room it opens into.  The player hull is 30 units and the
#: navmesh generator's corridor width is 31 (W2, N2), so a 72-unit lane is
#: those plus room to walk rather than scrape.
#:
#: WHY A LANE AND NOT A CIRCLE.  Clearing a circle round each doorway is not
#: enough, measured on the compiled navmesh: with the doorway itself clear, a
#: room is still cut off from every spawn when a fill runs as a strip down
#: the approach and its solid pieces (a rubble pile is solid by the size
#: rule) close the approach far from the doorway instead of at it.  What has to stay open is the whole way through, not
#: the threshold.
LANE_HALF_WIDTH = 36.0


def _lanes(bp: Blueprint) -> tuple[tuple[float, float, float, float, float], ...]:
    """Doorway-to-room-centre lanes, as ``(x0, y0, x1, y1, floor z)``.

    Every aperture joined to the middle of its own room is enough to keep a
    room connected: if each door reaches the centre, each door reaches every
    other door.
    """
    cached = getattr(bp, "_zmf_lanes", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import Room

    lanes: list[tuple[float, float, float, float, float]] = []
    for room in bp.elements(Room):
        inside = room.interior
        mid_x = (inside.mins.x + inside.maxs.x) / 2.0
        mid_y = (inside.mins.y + inside.maxs.y) / 2.0
        for box in room.aperture_boxes:
            at = box.centre
            lanes.append((at.x, at.y, mid_x, mid_y, room.floor_z))
    found = tuple(lanes)
    try:
        bp._zmf_lanes = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


def _lane_hits_box(x0: float, y0: float, x1: float, y1: float,
                   cx: float, cy: float, hx: float, hy: float) -> bool:
    """Does the lane run through this prop's plan box?

    Walked in 8-unit steps and tested against the box grown by
    :data:`LANE_HALF_WIDTH`, which is the box test and not a circle test: a
    113-unit shelf lying *along* a lane is beside it, and measuring from its
    centre to the line with its longest half-extent called that a blockage and
    took the collision off 193 props, a third of everything the size rule had
    made solid.
    """
    dx, dy = x1 - x0, y1 - y0
    steps = max(2, int(math.hypot(dx, dy) / 8.0) + 1)
    wide_x, wide_y = hx + LANE_HALF_WIDTH, hy + LANE_HALF_WIDTH
    for step in range(steps + 1):
        at = step / steps
        px, py = x0 + dx * at, y0 + dy * at
        if abs(px - cx) <= wide_x and abs(py - cy) <= wide_y:
            return True
    return False


#: How far past the foot and the head of a flight no prop stands.  Same number
#: as :data:`ENTRY_KEEP_CLEAR` and for the same reason: the floor a player
#: arrives on at the top of a flight, and the floor he turns on at the bottom,
#: are places the play goes through exactly as a doorway is.  Nothing is
#: needed *beside* a flight, because the test below is the prop's own plan box
#: against the flight's own footprint, so a box that overhangs a tread already
#: fails it.
STAIR_LANDING = 96.0

#: How far above the top of a flight the exclusion still holds: enough to
#: catch a prop standing on the landing at the head, not enough to reach a
#: gallery two storeys over the same patch of plan.
STAIR_HEAD_ROOM = 96.0


def _stair_zones(bp: Blueprint) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Every flight of stairs as ``(x0, y0, x1, y1, z low, z high)``.

    The footprint is the flight's own solids, which is exact -- a recipe builds
    its staircases out of brushwork
    (:meth:`~zmforge.blueprint.model.Blueprint.add_steps`) and keeps the call
    that made each one -- grown by :data:`STAIR_LANDING` at the foot and at
    the head, along the axis the flight climbs and no other.

    WHAT THIS GUARDS, measured on one map before it existed: 78
    props stood on its four flights, on their landings or within 48 units of a
    foot or a head.  33 of them were on one lower flight, 8 of those
    the 132 x 70 metal pallet, which reads as junk on the stairs.  Nothing in the placer knew a staircase
    was there: a flight is world brushwork, and a scene's fill box is a
    rectangle drawn over the room's floor, so a fill whose box covers a flight
    puts clutter up the treads as readily as on the floor.
    """
    cached = getattr(bp, "_zmf_stair_zones", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import Massing

    zones: list[tuple[float, float, float, float, float, float]] = []
    for massing in bp.elements(Massing):
        authored = massing.authored
        if authored is None or authored.form != "steps":
            continue
        box = massing.bounds
        x0, y0 = box.mins.x, box.mins.y
        x1, y1 = box.maxs.x, box.maxs.y
        toward = authored.toward
        along_x = toward is None or abs(toward.step.x) >= abs(toward.step.y)
        if along_x:
            x0, x1 = x0 - STAIR_LANDING, x1 + STAIR_LANDING
        else:
            y0, y1 = y0 - STAIR_LANDING, y1 + STAIR_LANDING
        zones.append((x0, y0, x1, y1, box.mins.z, box.maxs.z))
    found = tuple(zones)
    try:
        bp._zmf_stair_zones = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


#: How far from a player's own spawn slot no prop stands.  Same number as
#: :data:`ENTRY_KEEP_CLEAR`, and for a stronger reason: a zombie's landing is
#: somewhere the play goes through, and this is where the player *is* at
#: round one with nothing in his hands.  Without it a wall
#: row can run straight through the spawn slots, so the first thing the game
#: shows is a prop a few units from the camera, and more props stand on the
#: straight line from a slot to the first door, the wall buy or a window.
SPAWN_KEEP_CLEAR = 96.0

#: How tall a prop has to be before it counts as standing in a spawn's way.
#: Below this it is litter on the floor and the player looks straight over
#: it; at this height it is in the sightline of a standing player.
SPAWN_SIGHTLINE = 24.0


def _spawn_zones(bp: Blueprint):
    """``(slot points, spawn-to-exit lanes)`` for the players' own start.

    The slots are :meth:`PlayerStart.slot_positions`, the map's own answer to
    where each player stands, rather than the single start point: a
    four-player set is 96 units across, so a circle round the middle of it
    misses the outside two.

    The lanes are the doorway lanes' shape, aimed at everything a player
    walks to in his first ten seconds: every aperture of the room he starts
    in, every barricade in it, and every interactive item in it.  They are
    kept clear exactly as a doorway lane is -- 72 units wide, from the slot
    to the thing -- so what the player sees when the round starts is the way
    out and what he can buy, not the back of a filing cabinet.
    """
    cached = getattr(bp, "_zmf_spawn_zones", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import (
        Machine,
        MysteryBox,
        PlayerStart,
        PowerSwitch,
        Room,
        WallWeapon,
        Window,
    )

    slots: list[tuple[float, float, float]] = []
    for start in bp.elements(PlayerStart):
        for point in start.slot_positions():
            slots.append((point.x, point.y, point.z))
    targets: list[tuple[float, float, float]] = []
    # Only what is in the room the players start in.  A lane to a door three
    # rooms away is a line drawn through walls, and clearing it would take
    # the dressing out of rooms the player cannot even see from the spawn.
    here = [
        room for room in bp.elements(Room)
        if any(room.interior.holds_flat(x, y)
               and room.interior.mins.z - 8.0 <= z <= room.interior.maxs.z + 8.0
               for x, y, z in slots)
    ]
    for room in here:
        for box in room.aperture_boxes:
            at = box.centre
            targets.append((at.x, at.y, room.floor_z))

    def _in_here(x: float, y: float, z: float) -> bool:
        return any(
            room.interior.holds_flat(x, y)
            and room.interior.mins.z - 8.0 <= z <= room.interior.maxs.z + 160.0
            for room in here
        )

    for window in bp.elements(Window):
        at = window.barricade_origin
        if at is not None and _in_here(at.x, at.y, at.z):
            targets.append((at.x, at.y, at.z))
    for kind in (Machine, MysteryBox, PowerSwitch, WallWeapon):
        for item in bp.elements(kind):
            at = getattr(item, "position", None)
            if at is not None and _in_here(at.x, at.y, at.z):
                targets.append((at.x, at.y, at.z))
    lanes: list[tuple[float, float, float, float, float]] = []
    for sx, sy, sz in slots:
        for tx, ty, tz in targets:
            if abs(tz - sz) > 96.0:
                continue
            lanes.append((sx, sy, tx, ty, sz))
    found = (tuple(slots), tuple(lanes))
    try:
        bp._zmf_spawn_zones = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


#: How tall a prop has to be before it counts as standing in front of a
#: buyable item.  A dropped newspaper in front of Quick Revive is a dropped
#: newspaper; a bench is the reason the perk cannot be bought.  8 units is
#: the height below which a model is litter.
INTERACTIVE_MIN_HEIGHT = 8.0

#: How far in front of and behind a door leaf a prop tall enough to hide it
#: may not stand.  **Both faces**, which is the half that was missing: a
#: shelving unit on the far side of a door hides it from the room the player
#: is walking into just as well as one on this side hides it from the room he
#: is leaving.  48 is the depth a player crosses standing up to a door.
DOOR_FACE_CLEAR = 48.0

#: and how tall a prop has to be to hide a door rather than sit under it.
DOOR_HIDING_HEIGHT = 24.0


def _interactive_zones(bp: Blueprint) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Every buyable item's own body and the standing room in front of it.

    Six numbers a box, the shape :func:`_stair_zones` already returns.  The
    volumes are not invented here: they are
    :meth:`Blueprint.interactive_keep_clear`'s, derived by
    :mod:`zmforge.blueprint.reach` from the stock prefabs themselves, and the
    same ones the blueprint refuses a clashing *placement* with.  One
    definition, two users, so a prop cannot be allowed to stand where a
    second perk machine would be refused.

    **Doors are taken back out**, and that is measured rather than tidy.  A
    door's keep-clear is its leaf plus 96 units of standing room on each face
    and 32 to each side, which is right for another machine and far too much
    for a prop: in a 96-unit corridor with five doors opening off
    580 units of it, those five aprons are 720 units of a 580-unit room
    and every piece of dressing in it is inside one.  What a prop must not do
    to a door is hide it, which is :func:`_door_faces` -- 48 units on both
    faces of the leaf -- and block the way through it, which is the doorway
    lane :func:`_lanes` has always kept clear.
    """
    cached = getattr(bp, "_zmf_interactive_zones", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import Door
    from ..blueprint.reach import keep_of, keeps_of, zone_rectangles

    door_keeps = [keep_of(door) for door in bp.elements(Door)]
    doors = set(zone_rectangles([k for k in door_keeps if k is not None]))
    shared = getattr(bp, "interactive_keep_clear", None)
    if callable(shared):
        every = tuple(tuple(float(value) for value in zone) for zone in shared())
    else:
        every = zone_rectangles(keeps_of(bp.elements()))
    found = tuple(zone for zone in every if zone not in doors)
    try:
        bp._zmf_interactive_zones = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


def _art_faces(bp: Blueprint) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """The floor in front of every picture on a wall.

    The map draws its pictures on 2-unit panels set into the wall face
    (its recipe's poster slots), so a picture is a thin world solid and
    nothing else in the map is one.  Anything standing in front of one hides
    it: measured, a generator over a safety
    notice and a rooftop antenna over a poster.  The zone is the
    panel's own rectangle grown :data:`ART_CLEAR` on its thin axis, which
    reaches into the wall on one side, where nothing stands anyway.
    """
    cached = getattr(bp, "_zmf_art_faces", None)
    if cached is not None:
        return cached
    faces: list[tuple[float, float, float, float, float, float]] = []
    for boxes in _solid_rects(bp).values():
        for x0, y0, x1, y1, z0, z1 in boxes:
            if (x1 - x0) <= ART_PANEL_THICKNESS:
                faces.append((x0 - ART_CLEAR, y0, x1 + ART_CLEAR, y1, z0, z1))
            elif (y1 - y0) <= ART_PANEL_THICKNESS:
                faces.append((x0, y0 - ART_CLEAR, x1, y1 + ART_CLEAR, z0, z1))
    found = tuple(sorted(set(faces)))
    try:
        bp._zmf_art_faces = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


def _crowds_an_item(bp: Blueprint, where: Point, half: tuple[float, float],
                    low: float, high: float) -> bool:
    """Is this prop in a buyable item's way, or over one of the pictures?

    Asked of a floor prop and of a wall fixture alike: a sign hung on the
    chalk of a wall buy hides it exactly as a filing cabinet in front of it
    would, and 9 of them were, measured on the first build of this rule.
    """
    zones = _keep_clear(bp)
    foot = Poly2.rect(where.x - half[0], where.y - half[1],
                      where.x + half[0], where.y + half[1])
    return bool(
        zones["interactive"].blocks(foot, z_low=low, z_high=high)
        or zones["art"].blocks(foot, z_low=low, z_high=high)
    )


#: How thin a world solid has to be, through its plan, to be one of the map's
#: own picture panels rather than a wall, a pier or a plinth.  The panels are
#: 2 units; the next thinnest solid measured was a 16-unit wall.
ART_PANEL_THICKNESS = 4.0

#: and how much floor in front of a picture stays empty: a prop within 32
#: units in front of a picture covers it.
ART_CLEAR = 32.0

#: How far under an interactive item's own origin its keep-clear volume
#: starts, from :data:`zmforge.blueprint.reach.BASE_SLACK`.  Repeated as a
#: number rather than imported because it is only used to turn that volume's
#: floor back into the item's own origin.
BASE_SLACK = 8.0


def _door_faces(bp: Blueprint) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Each door leaf grown :data:`DOOR_FACE_CLEAR` along the way through it."""
    cached = getattr(bp, "_zmf_door_faces", None)
    if cached is not None:
        return cached
    from ..blueprint.elements import Door
    from ..spatial import Axis

    faces: list[tuple[float, float, float, float, float, float]] = []
    for door in bp.elements(Door):
        box = door.box
        if box is None:
            continue
        grown = box.grown_on(door.through_axis, DOOR_FACE_CLEAR)
        faces.append((grown.mins.x, grown.mins.y, grown.maxs.x, grown.maxs.y,
                      grown.mins.z, grown.maxs.z))
    found = tuple(faces)
    try:
        bp._zmf_door_faces = found  # type: ignore[attr-defined]
    except Exception:
        pass
    return found


def _box_hits(zones, x: float, y: float, hx: float, hy: float,
              low: float, high: float, rise: float = 0.0) -> bool:
    """Does a prop's plan box stand in one of these boxes and rise into it?

    ``rise`` is how far above a zone's own floor the prop's top has to reach
    before it counts.  A dropped paper plate on a counter is inside a wall
    buy's apron and is not in anybody's way; a notice board on the same wall
    is.
    """
    for x0, y0, x1, y1, z0, z1 in zones:
        if high < z0 + rise or low >= z1:
            continue
        if x + hx > x0 and x - hx < x1 and y + hy > y0 and y - hy < y1:
            return True
    return False


# --------------------------------------------------------------------------
# The zones nothing stands in, as negative shapes
# --------------------------------------------------------------------------
#: How many sides a keep-out circle is drawn with, and the factor that pushes
#: its corners out onto the circle rather than inside it.
#: :meth:`~zmforge.placement.scatter.KeepClear.disc` inscribes, which would
#: make every spawn and landing circle slightly *smaller* than the rule says;
#: a keep-out that under-covers is the one failure mode that matters here, so
#: the radius handed over is the circumscribing one.  At 64 sides that is
#: 0.12% -- a tenth of a unit on a 96-unit circle.
ZONE_SIDES = 64
ZONE_CIRCUMSCRIBE = 1.0 / math.cos(math.pi / ZONE_SIDES)

#: How far apart in z two things have to be before a keep-out on one storey
#: stops speaking about the other.  Half a storey, sized against storeys 272
#: and 288 units apart and a tallest prop of 179.
ZONE_STOREY = 96.0

#: The skin a zone whose hand-written test was **closed** is grown by.
#: :meth:`~zmforge.placement.scatter.KeepClear.blocks` asks for shared area,
#: so a footprint whose edge lies exactly on a zone's edge is clear of it,
#: where ``x + hx >= x0`` said it was in it.  A hundredth of a unit is under
#: the .map writer's own rounding and restores the closed reading: measured,
#: it is the difference between a pipe elbow on a
#: flight and off it, and nothing else moves.
ZONE_TOUCH = 0.01

#: How tall a prop standing in a buyable item's keep-clear volume has to be
#: before a **pinned** room is allowed to move it out.  The same 24 units as
#: :data:`DOOR_HIDING_HEIGHT`, because it is the same judgement: a prop that
#: can hide a door leaf is a prop that can stand between a player and a buy,
#: and one that cannot is scenery the player walks over.  Measured against
#: what stood in one wall buy's rectangle, the cut
#: lands in open air: the things that block are five 41-unit dining chairs, a
#: 49-unit water cooler and an 84-unit fridge; the things that do not are a
#: 12.6-unit watermelon, two 5-unit banana bunches, two 5-unit signs lying
#: flat and a 0.3-unit paper plate.  Nothing in this palette sits between 13
#: and 41, so the number is not balanced on a knife edge.
ITEM_BLOCKS_HEIGHT = DOOR_HIDING_HEIGHT


def _lane_zone(reason: str, x0: float, y0: float, x1: float, y1: float,
               z: float, half_width: float) -> KeepClear:
    """A walked route as one negative shape: the segment swept by a square.

    The hand-written test walked the segment in 8-unit steps and asked
    whether each step was inside the prop's box grown by ``half_width``.
    That is the Minkowski sum of the segment with a ``2 * half_width``
    square, and a convex hull of the square at both ends *is* that sum, so
    this is the same test with the sampling taken out of it.
    """
    corners = [
        (x + dx, y + dy)
        for x, y in ((x0, y0), (x1, y1))
        for dx in (-half_width, half_width)
        for dy in (-half_width, half_width)
    ]
    return KeepClear(
        Poly2.of(convex_hull(corners)), reason,
        z - ZONE_STOREY, z + ZONE_STOREY,
    )


def _keep_clear(bp: Blueprint) -> Mapping[str, Negatives]:
    """Every zone nothing may stand in, by reason, as negative shapes.

    One :class:`~zmforge.placement.scatter.Negatives` per reason, because the
    reasons are not all asked of every prop: a landing and a lane are about a
    body getting through and a model that is walk-through wherever it stands
    may sit in one, a spawn is asked of anything solid *or* tall, and a
    staircase is asked of everything.  :func:`_no_prop_zone` is the order
    they are asked in; this is what they are.

    Built once per blueprint and cached on it, like the builders it reads.
    """
    cached = getattr(bp, "_zmf_keep_clear", None)
    if cached is not None:
        return cached
    groups = {
        "stairs": Negatives.of(
            KeepClear.rect("stairs", x0 - ZONE_TOUCH, y0 - ZONE_TOUCH,
                           x1 + ZONE_TOUCH, y1 + ZONE_TOUCH,
                           z_low=z0 - 16.0, z_high=z1 + STAIR_HEAD_ROOM)
            for x0, y0, x1, y1, z0, z1 in _stair_zones(bp)
        ),
        "door": Negatives.of(
            KeepClear.rect("door", x0, y0, x1, y1,
                           z_low=z0 + DOOR_HIDING_HEIGHT, z_high=z1)
            for x0, y0, x1, y1, z0, z1 in _door_faces(bp)
        ),
        # The same leaves with no rise, which is what a *fixture* is asked:
        # a sign whose own height overlaps the opening's is over the opening,
        # however low the opening starts.
        "doorway": Negatives.of(
            KeepClear.rect("doorway", x0, y0, x1, y1, z_low=z0, z_high=z1)
            for x0, y0, x1, y1, z0, z1 in _door_faces(bp)
        ),
        "interactive": Negatives.of(
            KeepClear.rect("interactive", x0, y0, x1, y1,
                           z_low=z0 + INTERACTIVE_MIN_HEIGHT + BASE_SLACK,
                           z_high=z1)
            for x0, y0, x1, y1, z0, z1 in _interactive_zones(bp)
        ),
        # No rise on the pictures: any overlap at all hides part of one, and
        # a prop too short to reach a panel that hangs at head height is
        # already out on the vertical test.
        "art": Negatives.of(
            KeepClear.rect("art", x0, y0, x1, y1, z_low=z0, z_high=z1)
            for x0, y0, x1, y1, z0, z1 in _art_faces(bp)
        ),
        "landing": Negatives.of(
            KeepClear.disc("landing", x, y, ENTRY_KEEP_CLEAR * ZONE_CIRCUMSCRIBE,
                           segments=ZONE_SIDES,
                           z_low=z - ZONE_STOREY, z_high=z + ZONE_STOREY)
            for x, y, z in _entry_points(bp)
        ),
        "lane": Negatives.of(
            _lane_zone("lane", x0, y0, x1, y1, z, LANE_HALF_WIDTH + ZONE_TOUCH)
            for x0, y0, x1, y1, z in _lanes(bp)
        ),
    }
    # The floor in and either side of every doorway, which is verify's Z53
    # zone exactly: the placer refuses what the check would report.
    from ..verify.doorways import STEP as _DOOR_STEP, doorway_zones

    groups["approach"] = Negatives.of(
        KeepClear.rect("approach", x0, y0, x1, y1,
                       z_low=floor + _DOOR_STEP, z_high=floor + 96.0)
        for _room, (x0, y0, x1, y1), floor in doorway_zones(bp)
    )
    slots, lanes = _spawn_zones(bp)
    groups["spawn"] = Negatives.of(
        KeepClear.disc("spawn", x, y, SPAWN_KEEP_CLEAR * ZONE_CIRCUMSCRIBE,
                       segments=ZONE_SIDES,
                       z_low=z - ZONE_STOREY, z_high=z + ZONE_STOREY)
        for x, y, z in slots
    )
    groups["spawn lane"] = Negatives.of(
        _lane_zone("spawn lane", x0, y0, x1, y1, z,
                    LANE_HALF_WIDTH + ZONE_TOUCH)
        for x0, y0, x1, y1, z in lanes
    )
    try:
        bp._zmf_keep_clear = groups  # type: ignore[attr-defined]
    except Exception:
        pass
    return groups


def _no_prop_zone(bp: Blueprint, where: Point, half: tuple[float, float],
                  *, stairs: bool = True, solid: bool = True,
                  span: tuple[float, float] | None = None) -> str | None:
    """Why nothing may stand here, or ``None``.

    The reasons, in the order they are asked: ``stairs`` (a flight, its foot
    or its head), ``spawn`` and ``spawn lane`` (the players' own start and
    the way out of it), ``interactive`` (a buyable item's standing room, or
    one of the map's pictures), ``door`` (either face of a leaf), ``landing``
    (a barricade or a rise struct) and ``lane`` (a doorway to the middle of
    its room).

    The test is the prop's own plan box at its own yaw, not its centre: a
    132-unit pallet whose centre is beside a flight still has half of itself
    over the treads.

    The zones themselves are
    :class:`~zmforge.placement.scatter.KeepClear` polygons grouped by reason
    (:func:`_keep_clear`); this function is the order they are asked in and
    which props each one is asked of, and it has no geometry of its own.
    A spawn and a barricade landing are asked of the prop's **centre**, the
    rest of its footprint, which is the split the hand-written rules already
    made.

    ``span`` is the prop's own bottom and top in world z, which is how tall
    it is: a dropped newspaper in front of a wall buy is a dropped newspaper
    and a notice board on the same wall is a blocked buy, and the zone tests
    that care about that read it from here.

    ``solid`` is the prop's solidity **as a model**, which is the only thing
    solidity is ever decided by here.  A landing and a lane are about a body
    getting through, so a model that is walk-through wherever it stands -- a
    cup, a sheet of paper, a bush -- may stand in one; there is nothing there
    to get through.  A 96-unit closet with a zombie
    riser in the middle of the floor is common, and refusing every model in
    one leaves it completely bare.  A staircase is not like that: junk on the stairs is
    the first thing a player notices, and litter reads as junk just as well as a
    crate does, so nothing at all stands on a flight.
    """
    zones = _keep_clear(bp)
    foot = Poly2.rect(where.x - half[0], where.y - half[1],
                      where.x + half[0], where.y + half[1])
    here = (where.x, where.y)
    if stairs and zones["stairs"].blocks(foot, z_low=where.z, z_high=where.z):
        return "stairs"
    low, high = span if span is not None else (where.z, where.z)
    tall = (high - low) >= SPAWN_SIGHTLINE
    if solid or tall:
        if zones["spawn"].blocks(here, z_low=where.z, z_high=where.z):
            return "spawn"
        if zones["spawn lane"].blocks(foot, z_low=where.z, z_high=where.z):
            return "spawn lane"
    if _crowds_an_item(bp, where, half, low, high):
        return "interactive"
    if zones["door"].blocks(foot, z_low=low, z_high=high):
        return "door"
    if not solid:
        return None
    if zones["landing"].blocks(here, z_low=where.z, z_high=where.z):
        return "landing"
    if zones["lane"].blocks(foot, z_low=where.z, z_high=where.z):
        return "lane"
    if zones["approach"].blocks(foot, z_low=low, z_high=high):
        return "approach"
    return None


# --------------------------------------------------------------------------
# Not inside the brushwork, and not hanging off the edge of it
# --------------------------------------------------------------------------
#: How far a prop's own box may reach into a world solid before it counts as
#: being *in* it rather than against it.  Two units, the same allowance the shipped
#: maps need: Treyarch's props sit a median 2 to 7 units from the nearest
#: vertical brush face (:data:`EDGE_SHARE`), which means touching.
SOLID_POKE = 2.0

#: A solid whose top is no further than this above a prop's own base is the
#: thing the prop is standing on, not something it has walked into.  The
#: engine's step height is the reason for the number: anything this close is
#: under the prop's feet.
SOLID_STAND_ON = 8.0

#: How many times a placement is pushed out of the brushwork before it is
#: given up on.  Each push is the smallest translation that clears the worst
#: solid, and clearing one can put a corner into another, so it iterates --
#: but a prop that needs four is in a place with no room for it.
SOLID_PUSHES = 4


def _solid_rects(bp: Blueprint):
    """Every world solid the blueprint knows, as plan boxes bucketed in plan.

    ``(x0, y0, x1, y1, z0, z1)`` per solid, which is exact for this
    generator: a room shell, a block, a plinth, a column and a step are all
    :func:`~zmforge.solids.forms.block` calls, so the hull of a solid's face
    points is the solid.

    **Terrain is not in here, and that is deliberate.** The heightfield is
    emitted as a column per cell and those columns are the ground: a prop on
    a slope always overlaps the column uphill of it, which is what standing
    on a hill looks like, not a prop inside a wall.  The sky shell is out for
    the same reason -- it is not something a room has in it.
    """
    cached = getattr(bp, "_zmf_solid_rects", None)
    if cached is not None:
        return cached
    grid: dict[tuple[int, int], list[tuple[float, float, float, float, float, float]]] = defaultdict(list)
    for solid in bp.world_solids():
        note = getattr(solid, "note", "") or ""
        if note.startswith("terrain") or note == "sky shell":
            continue
        xs = [point.x for face in solid.faces for point in face.points]
        ys = [point.y for face in solid.faces for point in face.points]
        zs = [point.z for face in solid.faces for point in face.points]
        box = (min(xs), min(ys), max(xs), max(ys), min(zs), max(zs))
        for gx in range(math.floor(box[0] / _BUCKET), math.floor(box[2] / _BUCKET) + 1):
            for gy in range(math.floor(box[1] / _BUCKET), math.floor(box[3] / _BUCKET) + 1):
                grid[(gx, gy)].append(box)
    try:
        bp._zmf_solid_rects = grid  # type: ignore[attr-defined]
    except Exception:
        pass
    return grid


def _solids_near(grid, x: float, y: float, hx: float, hy: float):
    seen: set[int] = set()
    for gx in range(math.floor((x - hx) / _BUCKET), math.floor((x + hx) / _BUCKET) + 1):
        for gy in range(math.floor((y - hy) / _BUCKET), math.floor((y + hy) / _BUCKET) + 1):
            for box in grid.get((gx, gy), ()):
                if id(box) in seen:
                    continue
                seen.add(id(box))
                yield box


#: How close a keep-clear rectangle's edge has to be to a room wall before
#: that edge counts as being *on* it.  One unit: the volumes are derived from
#: the prefabs and land on the wall face exactly, so this is a rounding
#: allowance rather than a search.
ITEM_WALL_TOUCH = 1.0


def _item_open_side(bp: Blueprint, where: Point,
                    x0: float, y0: float, x1: float, y1: float) -> str | None:
    """Which way out of this rectangle leads away from the item's own wall.

    A wall buy's keep-clear volume has the wall it is mounted on as one of
    its four edges and open floor at the other three, so the way out that
    reads as "step back from the buy" is the one opposite that edge.  It
    matters because the *nearest* way out of a 112 by 96 rectangle is usually
    sideways, and sideways collapses a row of chairs into a stack at each end
    of the rectangle while the room is supposed to read as a room full of
    chairs.

    ``None`` when the rectangle is against no wall, or against more than one
    -- an item in a corner has no single "back" -- and the caller falls back
    to the shortest way out.
    """
    room = _room_at(bp, where)
    if room is None:
        return None
    inside = room.interior
    against = [
        side for side, touching in (
            ("+x", abs(x0 - inside.mins.x) <= ITEM_WALL_TOUCH),
            ("-x", abs(x1 - inside.maxs.x) <= ITEM_WALL_TOUCH),
            ("+y", abs(y0 - inside.mins.y) <= ITEM_WALL_TOUCH),
            ("-y", abs(y1 - inside.maxs.y) <= ITEM_WALL_TOUCH),
        ) if touching
    ]
    return against[0] if len(against) == 1 else None


def _clear_of_items(bp: Blueprint, rooms, where: Point, name: str, size,
                    yaw: float, scale: float,
                    low: float, high: float) -> Point:
    """``where`` slid back off any buyable item, if it is tall enough to matter.

    THE ONE RULE A PINNED ROOM STILL OBEYS.  ``Scene.keep_as_is`` exists so a
    pinned room keeps its look, and every other rule in this module
    is switched off in one (``free`` is ``not scene.keep_as_is``).  This one
    is not, because the thing it protects is not a matter of taste: a wall
    buy with the room's dressing standing on its chalk is a weapon the player
    cannot buy, and an unusable buy is a broken map rather than an ugly one.
    Without this rule, a pinned room's props can stand inside a wall buy's
    keep-clear volume.

    It is deliberately the *smallest* rule that makes the buy usable, because
    the room's look is deliberate and every prop moved changes it.  Two things keep it small:

    :data:`ITEM_BLOCKS_HEIGHT`
        only a prop tall enough to stand between a player and the buy is
        moved.  Chairs, a water cooler and a fridge are; fruit, signs lying
        flat and paper plates are floor clutter a player walks
        over, and they stay exactly where they were;

    :func:`_item_open_side`
        the move is **away from the item's own wall**, not the shortest way
        out.  Sideways is usually nearer and it collapses a row of five
        chairs into two stacks at the ends of the rectangle; backwards keeps
        the row a row, which is the whole reason the room reads as a room
        full of chairs.  Shortest is the fallback for a rectangle with no
        single wall behind it.

    Unlike :func:`_clear_of_solids` this **never refuses**: a pinned room may
    have its dressing moved, but nothing in one is allowed to disappear, so a
    prop with nowhere to go comes back unmoved and :func:`_no_prop_zone` is
    still not asked about it.  The move is the smallest of the four ways out
    of the rectangle that both leaves the volume and survives being re-fitted
    in the room, which is why it is not simply the nearest edge: the nearest
    edge of a buy on a wall is the wall.
    """
    zones = _interactive_zones(bp)
    if not zones:
        return where
    if (high - low) <= ITEM_BLOCKS_HEIGHT:
        return where  # floor clutter: walked over, not walked into
    rise = INTERACTIVE_MIN_HEIGHT + BASE_SLACK
    hx, hy = plan_half_extent(name, size, yaw, scale)
    start = where
    # The room the prop is pinned in.  A push may not leave it: the shortest
    # way out of a buy's rectangle is often straight through the wall behind
    # it, and :func:`_fit_inside` will happily answer with a neighbouring
    # room -- measured, that put a water cooler 24
    # units outside its room.
    home = _room_at(bp, start)
    for _push in range(SOLID_PUSHES):
        hit = []
        for x0, y0, x1, y1, z0, z1 in zones:
            if high < z0 + rise or low >= z1:
                continue
            shared_x = min(where.x + hx, x1) - max(where.x - hx, x0)
            shared_y = min(where.y + hy, y1) - max(where.y - hy, y0)
            if shared_x <= 0.0 or shared_y <= 0.0:
                continue
            hit.append((min(shared_x, shared_y), x0, y0, x1, y1))
        if not hit:
            return where
        # Deepest first, but a zone with no way out of it does not end the
        # search: a sign flat against the wall is in the buy's rectangle and
        # in a second volume that has the wall on three sides, and taking
        # only the worst one meant giving up without ever trying the buy's.
        hit.sort(key=lambda entry: -entry[0])
        best = None
        for _depth, x0, y0, x1, y1 in hit:
            away = _item_open_side(bp, where, x0, y0, x1, y1)
            # The label is the direction the prop *travels*: out through the
            # rectangle's high-x edge is a move in +x.
            for side, out in (
                ("+x", Point(x1 + hx, where.y, where.z)),
                ("-x", Point(x0 - hx, where.y, where.z)),
                ("+y", Point(where.x, y1 + hy, where.z)),
                ("-y", Point(where.x, y0 - hy, where.z)),
            ):
                fitted = _fit_inside(rooms, out, size, scale, name, yaw)
                if fitted is None:
                    continue
                # The nearest way out of a wall buy's rectangle is the wall
                # it is mounted on, and :func:`_fit_inside` does not stop
                # that: the rectangle's own south edge can *be* the
                # room's south wall face, so the chair pushed "out" ends up in the
                # brushwork.  Settling the candidate against the brushwork
                # is what answers that, and it is a settle rather than a
                # refusal because the way *back* from a buy often lands on
                # the room's own furniture: bench tables can stand
                # 44 units into the step-back, and refusing on that sent
                # every chair sideways into a stack instead.
                settled = _clear_of_solids(bp, rooms, fitted, name, size, yaw,
                                           scale, low, high)
                if settled is None:
                    continue
                fitted = settled
                if home is not None and not home.interior.holds_flat(fitted.x, fitted.y):
                    continue
                if (min(fitted.x + hx, x1) - max(fitted.x - hx, x0) > 0.0
                        and min(fitted.y + hy, y1) - max(fitted.y - hy, y0) > 0.0):
                    continue
                # The way out of the item's own face wins outright; among
                # the rest, the shortest.
                moved = math.hypot(fitted.x - start.x, fitted.y - start.y)
                rank = (0 if side == away else 1, moved)
                if best is None or rank < best[0]:
                    best = (rank, fitted)
            if best is not None:
                break
        if best is None:
            return start  # nowhere to go; a pinned prop is never dropped
        where = best[1]
    return where


def _clear_of_solids(bp: Blueprint, rooms, where: Point, name: str, size,
                     yaw: float, scale: float,
                     low: float, high: float,
                     extra: Sequence[tuple[float, float, float, float,
                                           float, float]] = ()) -> Point | None:
    """``where`` slid out of any brushwork its own box reaches into, or ``None``.

    WHY THE ROOM'S OWN WALLS ARE NOT ENOUGH, measured on one map:
    105 props stood with more than two units of themselves inside a world
    solid, and only a handful of those were the room's outer wall.  The rest
    were the things standing *in* the room, which :func:`_fit_inside` has
    never heard of -- a desk 16 units into a plinth, newspapers in a
    column, a plant through a service counter -- because a room in this
    package is a box and fitting a prop means fitting it in that box.

    The push is the smallest translation on x or y that clears the worst
    solid, re-fitted in the room afterwards so it cannot be pushed through a
    wall, and repeated because clearing one solid can put a corner in the
    next.  A prop that still overlaps after :data:`SOLID_PUSHES` has nowhere
    to go and is refused rather than shipped inside the brushwork.

    ``extra`` is a second list of boxes to be slid out of, in the same
    ``(x0, y0, x1, y1, z0, z1)`` shape as the brushwork.  It is how a prop
    that has landed in *another prop* is moved rather than dropped
    (:meth:`_Crowd.boxes_near`): a thing standing in the room is a thing to
    step round whether the map calls it a brush or a model, and the move a
    dresser makes is the same one either way.
    """
    grid = _solid_rects(bp)
    hx, hy = plan_half_extent(name, size, yaw, scale)
    for _push in range(SOLID_PUSHES):
        worst = None
        for x0, y0, x1, y1, z0, z1 in chain(
            _solids_near(grid, where.x, where.y, hx, hy), extra
        ):
            if z1 <= low + SOLID_STAND_ON or z0 >= high - SOLID_POKE:
                continue
            if min(high, z1) - max(low, z0) <= SOLID_POKE:
                continue
            shared_x = min(where.x + hx, x1) - max(where.x - hx, x0)
            shared_y = min(where.y + hy, y1) - max(where.y - hy, y0)
            if shared_x <= SOLID_POKE or shared_y <= SOLID_POKE:
                continue
            depth = min(shared_x, shared_y)
            if worst is None or depth > worst[0]:
                worst = (depth, x0, y0, x1, y1)
        if worst is None:
            return where
        _depth, x0, y0, x1, y1 = worst
        outs = (
            (abs(x1 + hx - where.x), Point(x1 + hx, where.y, where.z)),
            (abs(where.x - (x0 - hx)), Point(x0 - hx, where.y, where.z)),
            (abs(y1 + hy - where.y), Point(where.x, y1 + hy, where.z)),
            (abs(where.y - (y0 - hy)), Point(where.x, y0 - hy, where.z)),
        )
        moved = min(outs, key=lambda out: out[0])[1]
        fitted = _fit_inside(rooms, moved, size, scale, name, yaw)
        if fitted is None:
            return None
        if abs(fitted.x - where.x) < 1e-6 and abs(fitted.y - where.y) < 1e-6:
            return None  # the room pushed it straight back in
        where = fitted
    return None


def _block_rect(bp: Blueprint, hit, x: float, y: float) -> tuple[float, float, float, float] | None:
    """The plan rectangle of the block top under ``(x, y)``, or ``None``.

    ``None`` means the surface is a room floor or terrain, which a prop
    cannot hang off the edge of.
    """
    if not hit.found or not hit.source.startswith("platform "):
        return None
    from ..blueprint.elements import Massing

    for massing in bp.elements(Massing):
        if massing.id != hit.element_id:
            continue
        for solid in massing.solids:
            xs = [point.x for face in solid.faces for point in face.points]
            ys = [point.y for face in solid.faces for point in face.points]
            zs = [point.z for face in solid.faces for point in face.points]
            if abs(max(zs) - hit.z) > 0.5:
                continue
            if min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys):
                return (min(xs), min(ys), max(xs), max(ys))
    return None


def _fit_on_block(rect, where: Point, name: str, size, yaw: float,
                  scale: float) -> Point | None:
    """``where`` slid so the prop's footprint is inside the block it stands on.

    ``None`` when the prop is bigger than the block, which means it is not
    standing on it at all: it has two corners or fewer over the thing it
    rests on, as a 90-unit desk on a 40-deep counter does.  A prop that does
    not fit the block belongs on the floor beside it, so the caller drops it
    down rather than leaving it hanging in the air.
    """
    x0, y0, x1, y1 = rect
    hx, hy = plan_half_extent(name, size, yaw, scale)
    low_x, high_x = x0 + hx, x1 - hx
    low_y, high_y = y0 + hy, y1 - hy
    if low_x > high_x or low_y > high_y:
        return None
    return Point(min(max(where.x, low_x), high_x),
                 min(max(where.y, low_y), high_y), where.z)


def _room_at(bp: Blueprint, where: Point):
    """The room whose inside holds this point, or ``None``."""
    from ..blueprint.elements import Room

    for room in bp.elements(Room):
        inside = room.interior
        if not inside.holds_flat(where.x, where.y):
            continue
        if inside.mins.z - 8.0 <= where.z <= inside.maxs.z + 8.0:
            return room
    return None


#: How much of a mounted fixture may be inside the brushwork it is mounted
#: on.  Nothing: a fixture is placed flush against a face by construction, so
#: any overlap at all means it is on the wrong face -- a fin in a narrow
#: corridor, a plinth, or one of the map's own 2-unit picture panels, which is
#: how a notice board came to be hung over a framed picture.
MOUNT_POKE = 0.01

#: The rule a wall fixture has to satisfy where it is put, and the same
#: object ``Z44`` judges a built one by (:mod:`zmforge.placement.audit`).
#: ``sill_low`` is this module's own :data:`WALL_SILL_MIN`; the upper sill is
#: the relation's own 154, which is the top of where wall pictures hang,
#: and cannot bind here, because the placer aims every fixture at
#: :data:`WALL_SILL` (48) and the ceiling clamp only ever lowers it.
#: ``StableAgainst``'s end test comes with it: a fixture may not hang past
#: the end of the face it is mounted on, which the hand-written rule did not
#: ask and which is what keeps a 60-unit light off a 48-unit tunnel fin.
MOUNTED = OnWall(sill_low=WALL_SILL_MIN)

#: The ceiling counterpart.  The clearance is this module's
#: :data:`CEILING_CLEAR`, so the relation is satisfied by construction and is
#: here as the statement of what "hung" means rather than as a filter.
HUNG = HangsFrom(clearance=CEILING_CLEAR)


def _as_placed(name: str, where: Point, yaw: float, scale: float) -> Placed:
    """This placement as a :class:`zmforge.placement.relations.Placed`.

    ``where`` is the model's plan centre and its resting z, which is what
    every rule in this module passes about and what ``Placed`` holds; the
    emitted origin is :func:`_placed_origin`'s job and the two differ for
    half this palette.  The half extents handed over are the model's **own**,
    not :func:`plan_half_extent`'s turned ones, because ``Placed`` turns them
    itself -- handing over turned ones would turn them twice.
    """
    box = MODEL_BOX.get(name)
    (x0, y0, z0), (x1, y1, z1) = box if box is not None else ((0.0,) * 3, (0.0,) * 3)
    return Placed(
        name=name,
        x=where.x,
        y=where.y,
        hx=(x1 - x0) * scale / 2.0,
        hy=(y1 - y0) * scale / 2.0,
        yaw=yaw,
        z_low=where.z + z0 * scale,
        z_high=where.z + z1 * scale,
    )


def _mount_planes(bp: Blueprint, room, where: Point, low: float, high: float
                  ) -> tuple[Wall, ...]:
    """Every face a fixture at this height could be mounted flat against.

    :class:`zmforge.placement.relations.Wall` per face, nearest first: the
    room's four walls (:func:`~zmforge.placement.relations.walls_of_rect`),
    and then every world solid beside the point that is tall enough to cover
    the fixture's whole band -- a fin in a corridor, a pier, a chimney
    breast.  Measured: one corridor's interior is 144 units across
    and its two fin banks narrow it to 48, so "the nearest wall of the room"
    is 24 units of solid brushwork away and 35 ducts and wall lights were
    mounted inside it.

    A solid's four faces carry the solid's own run as the wall's ``low`` and
    ``high``, and the **room's** floor and ceiling, because the sill a
    fixture on a fin hangs at is measured from the floor the player stands
    on, not from the bottom of the fin.
    """
    inside = room.interior
    faces: list[Wall] = list(walls_of_rect(
        room.id, inside.mins.x, inside.mins.y, inside.maxs.x, inside.maxs.y,
        room.floor_z, inside.maxs.z,
    ))
    for x0, y0, x1, y1, z0, z1 in _solids_near(
        _solid_rects(bp), where.x, where.y, WALL_REACH, WALL_REACH
    ):
        if z0 > low + MOUNT_POKE or z1 < high - MOUNT_POKE:
            continue  # not a surface this fixture could be flat against
        faces.extend((
            Wall(room.id, "x", x0, -1, y0, y1, room.floor_z, inside.maxs.z, "solid"),
            Wall(room.id, "x", x1, +1, y0, y1, room.floor_z, inside.maxs.z, "solid"),
            Wall(room.id, "y", y0, -1, x0, x1, room.floor_z, inside.maxs.z, "solid"),
            Wall(room.id, "y", y1, +1, x0, x1, room.floor_z, inside.maxs.z, "solid"),
        ))
    ranked = []
    for wall in faces:
        gap = abs((where.x if wall.axis == "x" else where.y) - wall.at)
        if gap <= WALL_REACH:
            ranked.append((gap, wall))
    ranked.sort(key=lambda entry: entry[0])
    return tuple(wall for _gap, wall in ranked)


def _mount_is_clear(bp: Blueprint, name: str, where: Point, size, yaw: float,
                    scale: float, low: float, high: float) -> bool:
    """Is a fixture here flush against the brushwork rather than inside it?"""
    hx, hy = plan_half_extent(name, size, yaw, scale)
    for x0, y0, x1, y1, z0, z1 in _solids_near(_solid_rects(bp), where.x, where.y, hx, hy):
        if min(high, z1) - max(low, z0) <= MOUNT_POKE:
            continue
        shared_x = min(where.x + hx, x1) - max(where.x - hx, x0)
        shared_y = min(where.y + hy, y1) - max(where.y - hy, y0)
        if shared_x > MOUNT_POKE and shared_y > MOUNT_POKE:
            return False
    return True


def _mounted_place(bp: Blueprint, name: str, where: Point, size, scale: float
                   ) -> tuple[Point, float] | None:
    """Where a wall or ceiling fixture actually goes, or ``None`` to refuse it.

    A wall kind is put flat against the nearest face it fits on -- a room
    wall or any solid beside it that covers its whole height -- turned so its
    own measured face (:func:`_mount_face`) looks away from that surface, and
    raised so its own box bottom is :data:`WALL_SILL` above the room's floor.
    A ceiling kind is hung from the ceiling, which is where its box already
    is: its geometry is entirely below its origin, so the origin goes on the
    ceiling plane and the model hangs the rest of the way down.

    Refused rather than moved a long way: a fixture aimed at the middle of a
    room, more than :data:`WALL_REACH` from anything to hang it on, is a scene
    asking for something the room cannot have, and putting it on the floor is
    what this rule exists to stop.  A ceiling kind in a room with no ceiling
    -- a yard -- is refused for the same reason.
    """
    room = _room_at(bp, where)
    if room is None:
        return None
    inside = room.interior
    floor = room.floor_z
    box = MODEL_BOX.get(name)
    if box is None:
        return None
    (_x0, _y0, z0), (_x1, _y1, z1) = box
    if mount_kind(name) == MOUNT_CEILING:
        if not room.roofed:
            return None
        rest = inside.maxs.z - CEILING_CLEAR - z1 * scale
        fitted = _fit_inside(((room.id, inside),),
                             Point(where.x, where.y, rest), size, scale, name, 0.0)
        if fitted is None:
            return None
        hung = Point(fitted.x, fitted.y, rest)
        if not HUNG.holds(_as_placed(name, hung, 0.0, scale), inside.maxs.z, room.id):
            return None
        if hung.z + z0 * scale < floor + WALL_SILL_MIN:
            return None  # the room is not tall enough to hang it in
        low, high = _vertical_span(name, rest, scale)
        if not _mount_is_clear(bp, name, hung, size, 0.0, scale, low, high):
            return None
        return hung, 0.0
    rest = floor + WALL_SILL - z0 * scale
    top = rest + z1 * scale
    if top > inside.maxs.z - CEILING_CLEAR:
        rest -= top - (inside.maxs.z - CEILING_CLEAR)
    low, high = _vertical_span(name, rest, scale)
    for wall in _mount_planes(bp, room, where, low, high):
        yaw = round((wall.facing_yaw - _mount_face(name)) % 360.0, 1)
        hx, hy = plan_half_extent(name, size, yaw, scale)
        if wall.axis == "x":
            x = wall.at + wall.inward * hx
            y = min(max(where.y, inside.mins.y + hy), inside.maxs.y - hy)
        else:
            y = wall.at + wall.inward * hy
            x = min(max(where.x, inside.mins.x + hx), inside.maxs.x - hx)
        at = Point(x, y, rest)
        if not inside.holds_flat(x, y):
            continue
        if not MOUNTED.holds(_as_placed(name, at, yaw, scale), wall):
            continue
        if _mount_is_clear(bp, name, at, size, yaw, scale, low, high):
            return at, yaw
    return None


# --------------------------------------------------------------------------
# Two large things in the same place
# --------------------------------------------------------------------------
#: A prop is **large** when *either* of its plan sides is over this.  Only a
#: prop small both ways is let alone: a cup half inside a bowl is a still
#: life, and the shipped maps are full of them.  A shelf 113 units long and 31
#: deep is not a still life, and asking about both sides never asked about
#: one: measured on one dense map, the both-sides gate judged 169 of its
#: props and the either-side gate 259, and every one of the 21
#: interpenetration warnings it still carried was a long thin shelf or
#: cabinet the narrow gate never asked about.
BIG_PROP_SIDE = 40.0

#: How much of the smaller of two large footprints may be shared before the
#: two are interpenetrating rather than touching, as a share of that
#: footprint.  Small on purpose.  Treyarch's own interiors have props touching
#: and stacked -- nearest-neighbour median 5 to 10 units and 15% to 23% of
#: models standing on another model's top face (measured on shipped interiors)
#: -- so touching is what a furnished room looks like and is allowed; two
#: solid boxes sharing a quarter of a floor at the same height is not.
OVERLAP_TOLERANCE = 0.05

#: Two props whose heights overlap by no more than this are stacked or set
#: down on one another, which is allowed.  Anything more is one model inside
#: the other.  The allowance is also capped at half the height of the shorter
#: of the two, because a flat absolute number is no test at all for flat
#: things: two 2.3-unit newspapers lying on the same patch of floor overlap by
#: 2.3, which would read as "stacked" and is in fact two newspapers drawn
#: through each other.
STACK_CLEARANCE = 4.0

#: The three numbers above as the one rule that states them, which is the
#: same object :mod:`zmforge.placement.audit` judges a built map with, so the
#: placer and the check can no longer drift apart.
#:
#: ``min_side`` is :data:`BIG_PROP_SIDE` and is the same gate
#: :meth:`_Crowd.is_large` applies when it decides what to keep: the rule is
#: skipped only for a prop small on both plan sides.  The two were once opposite
#: gates -- the crowd asked whether *both* sides were over
#: the number, so nothing long and thin was ever asked about -- and widening
#: the crowd's to this one is what took that map's prop-interpenetration
#: warnings from 21 to 0.  What it cost is measured in :func:`furnish`.
NO_OVERLAP = NoOverlap(tolerance=OVERLAP_TOLERANCE,
                       stack_allowance=STACK_CLEARANCE,
                       min_side=BIG_PROP_SIDE)


def _vertical_span(name: str, rest: float, scale: float) -> tuple[float, float]:
    """The bottom and top of this model as placed, in world z."""
    box = MODEL_BOX.get(name)
    if box is None:
        return (rest, rest)
    return (rest + box[0][2] * scale, rest + box[1][2] * scale)


def _model_floor(name: str) -> float:
    """How far this model's own box reaches below its origin, or 0.

    The third axis of the correction :func:`_placed_origin` makes in plan.
    Fourteen 130-unit rebar columns in a test map stood 65 units into
    the floor because they are authored about their own middle and were
    placed by their origin; so are the rubble chunks, the rocks, the barrack
    bedding and the shovel, all of which were drawn part-way into the tile.
    """
    box = MODEL_BOX.get(name)
    return 0.0 if box is None else box[0][2]


#: How much clear air a seat needs in front of it before the thing it is
#: looking at counts as a wall.  Measured against this palette: the deepest
#: seat in it is 34 units through, so 20 units of nothing in front of its
#: front face is a seat nobody could sit in.
SEAT_CLEAR = 20.0


def _seat_turned(bp: Blueprint, rooms, name: str, where: Point, yaw: float,
                 size, scale: float) -> float:
    """``yaw``, turned right round if this seat is facing a wall.

    :data:`MODEL_FRONT` has only ever been applied by :func:`_squared_yaw`,
    which is the rule for a piece a :class:`Fill` sited at random.  A
    :class:`Row` takes its heading from the line it is on, so a row of chairs
    down a wall faces whichever way the scene author happened to write, and
    measured on one map, eleven of them faced a wall 13 units
    away.  A row cannot aim each piece separately without ceasing to be a
    row, but it can turn one round: 180 degrees keeps the line and is always
    the other way off the wall.
    """
    front = MODEL_FRONT.get(name)
    if front is None:
        return yaw

    def blocked(at: float) -> bool:
        return (_faces_a_wall(rooms, name, where, at, front, size, scale)
                or _seat_blocked(bp, name, where, at, front, size, scale))

    if not blocked(yaw):
        return yaw
    turned = round((yaw + 180.0) % 360.0, 1)
    if blocked(turned):
        return yaw  # both ways are a wall; the room is the problem
    return turned


def _faces_a_wall(rooms, name: str, where: Point, yaw: float, front: float,
                  size, scale: float) -> bool:
    """Is there less than :data:`SEAT_CLEAR` of room in front of this seat?"""
    bearing = math.radians(yaw + front)
    hx, hy = plan_half_extent(name, size, yaw, scale)
    reach = abs(math.cos(bearing)) * hx + abs(math.sin(bearing)) * hy + SEAT_CLEAR
    ahead = (where.x + math.cos(bearing) * reach,
             where.y + math.sin(bearing) * reach)
    for _room_id, inside in rooms:
        if not inside.holds_flat(where.x, where.y):
            continue
        if not (inside.mins.z - 8.0 <= where.z <= inside.maxs.z + 8.0):
            continue
        return not inside.holds_flat(ahead[0], ahead[1])
    return False


def _seat_blocked(bp: Blueprint, name: str, where: Point, yaw: float,
                  front: float, size, scale: float) -> bool:
    """Is a seat's own front face up against brushwork rather than a room wall?

    A room in this package is a box, so the room test alone misses the things
    standing *in* the room -- the counter a chair was pulled up to the back of.
    """
    bearing = math.radians(yaw + front)
    hx, hy = plan_half_extent(name, size, yaw, scale)
    reach = abs(math.cos(bearing)) * hx + abs(math.sin(bearing)) * hy + SEAT_CLEAR
    ahead = Point(where.x + math.cos(bearing) * reach,
                  where.y + math.sin(bearing) * reach, where.z)
    for x0, y0, x1, y1, z0, z1 in _solids_near(_solid_rects(bp), ahead.x, ahead.y,
                                               0.0, 0.0):
        if z1 <= where.z + 8.0 or z0 >= where.z + 40.0:
            continue
        if x0 <= ahead.x <= x1 and y0 <= ahead.y <= y1:
            return True
    return False


class _Crowd:
    """The large props already placed, bucketed in plan so this is not quadratic.

    WHAT THIS GUARDS, measured on one dense map before it existed: of
    418 props with a plan footprint over 40 by 40, 728 pairs shared more than
    a quarter of the smaller footprint and 648 of those pairs were at the same
    height, which is two solid objects in the same place rather than one set
    down on the other.  It holds every prop :meth:`is_large` keeps --
    that is everything over :data:`BIG_PROP_SIDE` on *either* plan
    side, so the long thin shelves and cabinets the first version of this
    never looked at are in it too.

    A :class:`Fill` draws its points from a hash and knows nothing about what
    it has already put down, so in a busy room it draws the same corner twice.
    """

    __slots__ = ("_cells",)

    def __init__(self) -> None:
        self._cells: dict[tuple[int, int], list[Placed]] = defaultdict(list)

    @staticmethod
    def _keys(x: float, y: float, hx: float, hy: float):
        for i in range(int((x - hx) // _BUCKET), int((x + hx) // _BUCKET) + 1):
            for j in range(int((y - hy) // _BUCKET), int((y + hy) // _BUCKET) + 1):
                yield (i, j)

    @staticmethod
    def is_large(hx: float, hy: float) -> bool:
        return hx * 2.0 > BIG_PROP_SIDE or hy * 2.0 > BIG_PROP_SIDE

    @staticmethod
    def _box(x: float, y: float, hx: float, hy: float,
             low: float, high: float) -> Placed:
        """This prop as the rule reads it: a plan box and a height range.

        ``yaw=0`` is not a claim that the prop is unturned.  ``hx``/``hy``
        here are :func:`plan_half_extent`'s *already turned* half extents, so
        the box is the prop's turned bounding box and giving ``Placed`` the
        yaw as well would turn it a second time.
        """
        return Placed(name="", x=x, y=y, hx=hx, hy=hy, yaw=0.0,
                      z_low=low, z_high=high)

    def crowded(self, x: float, y: float, hx: float, hy: float,
                low: float, high: float) -> bool:
        """Would a large prop here interpenetrate one already placed?

        The gate is :meth:`is_large`, which is :data:`NO_OVERLAP`'s own
        ``min_side`` said at the call site so the bucketing can skip a small
        prop before it ever builds a box for it.
        """
        if not self.is_large(hx, hy):
            return False
        mine = self._box(x, y, hx, hy, low, high)
        seen: set[int] = set()
        for key in self._keys(x, y, hx, hy):
            for other in self._cells.get(key, ()):
                if id(other) in seen:
                    continue
                seen.add(id(other))
                if not NO_OVERLAP.holds(mine, other):
                    return True
        return False

    def boxes_near(self, x: float, y: float, hx: float, hy: float):
        """The placed props around here, as :func:`_clear_of_solids` boxes.

        The same ``(x0, y0, x1, y1, z0, z1)`` a world brush is read as, so a
        prop standing in another prop is moved by the move the placer already
        makes for a prop standing in brushwork.
        """
        seen: set[int] = set()
        out: list[tuple[float, float, float, float, float, float]] = []
        for key in self._keys(x, y, hx, hy):
            for other in self._cells.get(key, ()):
                if id(other) in seen:
                    continue
                seen.add(id(other))
                out.append((other.x - other.hx, other.y - other.hy,
                            other.x + other.hx, other.y + other.hy,
                            other.z_low, other.z_high))
        return out

    def add(self, x: float, y: float, hx: float, hy: float,
            low: float, high: float) -> None:
        if not self.is_large(hx, hy):
            return
        entry = self._box(x, y, hx, hy, low, high)
        for key in self._keys(x, y, hx, hy):
            self._cells[key].append(entry)


def _step_aside(bp: Blueprint, rooms, crowd: "_Crowd", name: str, where: Point,
                size, yaw: float, scale: float, low: float, high: float,
                solid: bool) -> Point | None:
    """``where`` slid off the props already standing there, or ``None``.

    What a dresser does when the piece will not go where it was meant to:
    stand it beside the thing it landed in rather than in it, and only when
    there is no such place put it back in the van.  The move is the shortest
    push out of the neighbour it is deepest inside, which is
    :func:`_clear_of_solids`, the same push the placer already makes for a
    prop that has landed in brushwork, handed the crowd's own boxes
    (:meth:`_Crowd.boxes_near`); the push repeats because clearing one
    neighbour can put a corner in the next, and the neighbours are looked up
    again each time because the prop has moved between the buckets.

    A moved prop is re-judged, not trusted: it has to be out of the crowd, in
    a place :func:`_no_prop_zone` allows (a doorway, a stair, a spawn, a
    barricade landing or a machine's standing room is not somewhere to step
    aside into) and somewhere it has actually moved to.  Anything else is
    ``None`` and the caller drops it, which is what the placer did with every
    crowded prop before this existed.
    """
    half = plan_half_extent(name, size, yaw, scale)
    spot = where
    for _push in range(SOLID_PUSHES):
        if not crowd.crowded(spot.x, spot.y, half[0], half[1], low, high):
            break
        moved = _clear_of_solids(
            bp, rooms, spot, name, size, yaw, scale, low, high,
            extra=crowd.boxes_near(spot.x, spot.y, half[0], half[1]),
        )
        if moved is None:
            return None
        spot = moved
    if spot is where:
        return None
    # It may not step into the next room.  A push big enough to clear a long
    # shelf is big enough to cross a 16-unit wall in one go, and a prop that
    # lands wholly the other side of one overlaps no brushwork at all, so
    # nothing else here would notice; :func:`_clear_of_items` keeps a pinned
    # prop in its room for the same reason.
    home = _room_at(bp, where)
    if home is not None and not home.interior.holds_flat(spot.x, spot.y):
        return None
    # A slide in plan is not a slide in Z.  The floor the prop was standing on
    # does not have to reach the place it stepped to -- a deck ends, a
    # yard's terrain falls away under it -- and a prop that steps off its own
    # floor hangs in the air, which is a worse fault than the one being fixed:
    # measured, three of the first 83 moves did that, one of them
    # 124 units up.  So the step is re-grounded the way the main loop grounds
    # a prop, it may not step up or down by more than the engine's step
    # (:data:`SOLID_STAND_ON`, so a stride across a yard's slope is a move
    # and a stride off a deck is not), and the height it is judged at is
    # the height it ends up at.
    floor = where.z + min(0.0, _model_floor(name) * scale)
    hit = bp.ground_under(spot.x, spot.y, below=floor + SURFACE_REACH)
    if not hit.found or abs(hit.z - floor) > SOLID_STAND_ON:
        return None
    spot = Point(spot.x, spot.y, hit.z - min(0.0, _model_floor(name) * scale))
    low, high = _vertical_span(name, spot.z, scale)
    if crowd.crowded(spot.x, spot.y, half[0], half[1], low, high):
        return None
    if _no_prop_zone(bp, spot, half, solid=solid, span=(low, high)) is not None:
        return None
    return spot


def _panel_may_lean(rooms, where: Point, taken: set[tuple[str, str]]) -> bool:
    """May a flat panel stand here?  Against a wall, and one to a wall.

    A sheet has no free-standing pose.  Leaning it on a wall is the only place
    it reads as a sheet somebody put down rather than as a slab dropped on the
    floor, and a second one on the same wall is a pile, which reads as junk.
    Both halves are refusals rather than moves: a panel
    that cannot lean is not placed.
    """
    segment = _wall_segment(rooms, where)
    if segment is None or segment in taken:
        return False
    wall = _nearest_wall(rooms, where)
    if wall is None or wall[1] > WALL_REACH:
        return False
    taken.add(segment)
    return True


def _wall_segment(rooms, point: Point) -> tuple[str, str] | None:
    """``(room id, which wall)`` for the wall nearest this point, or ``None``.

    A panel leans on one wall, and only one panel leans on it.  A room in this
    package is a box, so "a wall segment" is one of its four sides.
    """
    for room_id, inside in rooms:
        if not inside.holds_flat(point.x, point.y):
            continue
        if not (inside.mins.z - 8.0 <= point.z <= inside.maxs.z + 160.0):
            continue
        gaps = (
            ("west", point.x - inside.mins.x),
            ("east", inside.maxs.x - point.x),
            ("south", point.y - inside.mins.y),
            ("north", inside.maxs.y - point.y),
        )
        return (room_id, min(gaps, key=lambda g: g[1])[0])
    return None


#: The grid the pocket flood works on, in units.
POCKET_CELL = 16.0

#: How far each solid prop's plan box is grown before the flood runs.  The
#: navmesh generator's own corridor width is 31 units (N2), so a gap this
#: flood is allowed to squeeze through has to be at least that: without the
#: margin the flood walked through 16-unit gaps the compiler then refused to
#: lay surface in, and called a sealed corner open.
POCKET_MARGIN = 16.0


def _room_of(rooms, where: Point):
    """The room this point is in, keyed by storey as well as by name.

    A three-storey hall is one box three storeys tall, and the flood is a
    plan flood: rasterising its gallery and its floor into one grid would call
    the balcony rail a wall across the middle of the room.  Rounding the
    point's own height to the nearest 64 units separates the storeys.
    """
    for room_id, inside in rooms:
        if not inside.holds_flat(where.x, where.y):
            continue
        if inside.mins.z - 8.0 <= where.z <= inside.maxs.z + 8.0:
            return f"{room_id}@{round(where.z / 64.0)}", inside
    return None


def _dedupe(entries: list[list]) -> int:
    """Drop the second of any two identical props at the same spot.

    Two :class:`Row` s that share a corner deal the same model at the same
    coordinate, and the map then carries two copies of one chair drawn
    exactly through each other -- measured, eleven of them on one map.  Position
    and model, because the same model at the same place at a different yaw is
    the same defect.
    """
    seen: set[tuple[str, int, int, int]] = set()
    lost = 0
    for entry in entries:
        if not entry[6] or not entry[7]:
            continue  # a pinned room, or already taken out
        key = (entry[0], round(entry[1].x), round(entry[1].y), round(entry[1].z))
        if key in seen:
            entry[7] = False
            lost += 1
            continue
        seen.add(key)
    return lost


def _open_the_pockets(entries: list[list], rooms, bp: Blueprint) -> int:
    """Take the collision off whatever seals a piece of floor off.

    WHY A FLOOD AND NOT A SPACING RULE.  No spacing rule is right.
    Requiring a gap between every pair of solid props takes the collision off
    a bank of shelving against a wall, which blocks nothing; requiring it only
    where two banks meet removes most of a room's solid props and can still
    leave floor sealed, because one bank standing a little off a wall traps
    the strip behind it without making a corner at all.  The thing that actually has to hold is
    the thing ``H1`` measures on the compiled navmesh -- every piece of floor
    joined to a doorway -- so this measures the same thing on the same floor,
    before the compiler does, and opens whatever is shut.

    Per room: mark the cells a solid prop's plan box covers, flood the rest
    from that room's doorways, and for every stranded pocket **take out** the
    props around its edge.  Repeat until it floods.  Taking them out rather
    than taking their collision away is the same rule the doorway zones now
    follow: a prop the player walks through is a broken-looking map, so the
    repair for a prop in the wrong place is not to put it there.  A room
    pinned with ``keep_as_is`` is the exception and keeps its prop, ghosted,
    because nothing in a pinned room may move.
    """
    lost = 0
    by_room: dict[str, list[list]] = {}
    spans: dict[str, object] = {}
    for entry in entries:
        found = _room_of(rooms, entry[1])
        if found is None:
            continue
        room_id, inside = found
        by_room.setdefault(room_id, []).append(entry)
        spans[room_id] = inside
    doors: dict[str, list[tuple[float, float]]] = {}
    from ..blueprint.elements import Room, Spawn, Window

    for room in bp.elements(Room):
        key = f"{room.id}@{round(room.floor_z / 64.0)}"
        doors[key] = [(b.centre.x, b.centre.y) for b in room.aperture_boxes]
    for window in bp.elements(Window):
        at = window.barricade_origin
        if at is None:
            continue
        found = _room_of(rooms, at)
        if found is not None:
            doors.setdefault(found[0], []).append((at.x, at.y))
    for spawn in bp.elements(Spawn):
        at = spawn.position
        if at is None:
            continue
        found = _room_of(rooms, at)
        if found is not None:
            doors.setdefault(found[0], []).append((at.x, at.y))

    for room_id, here in by_room.items():
        inside = spans[room_id]
        x0, y0 = inside.mins.x, inside.mins.y  # type: ignore[attr-defined]
        nx = max(1, int((inside.maxs.x - x0) // POCKET_CELL))  # type: ignore[attr-defined]
        ny = max(1, int((inside.maxs.y - y0) // POCKET_CELL))  # type: ignore[attr-defined]
        if nx * ny > 40000:
            continue
        for _pass in range(6):
            boxes = []
            for entry in here:
                if not entry[4] or not entry[7]:
                    continue
                hx, hy = plan_half_extent(
                    entry[0], (0.0, 0.0, 0.0), entry[2], entry[3]
                )
                at = entry[1]
                boxes.append((entry,
                              at.x - hx - POCKET_MARGIN, at.y - hy - POCKET_MARGIN,
                              at.x + hx + POCKET_MARGIN, at.y + hy + POCKET_MARGIN))
            blocked = bytearray(nx * ny)
            for _entry, bx0, by0, bx1, by1 in boxes:
                for i in range(max(0, int((bx0 - x0) // POCKET_CELL)),
                               min(nx, int((bx1 - x0) // POCKET_CELL) + 1)):
                    for j in range(max(0, int((by0 - y0) // POCKET_CELL)),
                                   min(ny, int((by1 - y0) // POCKET_CELL) + 1)):
                        blocked[j * nx + i] = 1
            seeds = []
            for dx, dy in doors.get(room_id, ()):
                i = min(nx - 1, max(0, int((dx - x0) // POCKET_CELL)))
                j = min(ny - 1, max(0, int((dy - y0) // POCKET_CELL)))
                seeds.append(j * nx + i)
            if not seeds:
                seeds = [(ny // 2) * nx + nx // 2]
            seen = bytearray(nx * ny)
            stack = [s for s in seeds if not blocked[s]]
            if not stack:
                stack = [k for k in range(nx * ny) if not blocked[k]][:1]
            for s in stack:
                seen[s] = 1
            while stack:
                k = stack.pop()
                i, j = k % nx, k // nx
                for ai, aj in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
                    if 0 <= ai < nx and 0 <= aj < ny:
                        n = aj * nx + ai
                        if not seen[n] and not blocked[n]:
                            seen[n] = 1
                            stack.append(n)
            stranded = [k for k in range(nx * ny) if not blocked[k] and not seen[k]]
            if not stranded:
                break
            touch = set()
            for k in stranded:
                i, j = k % nx, k // nx
                cx = x0 + (i + 0.5) * POCKET_CELL
                cy = y0 + (j + 0.5) * POCKET_CELL
                for entry, bx0, by0, bx1, by1 in boxes:
                    if (bx0 - POCKET_CELL * 2 <= cx <= bx1 + POCKET_CELL * 2
                            and by0 - POCKET_CELL * 2 <= cy <= by1 + POCKET_CELL * 2):
                        touch.add(id(entry))
            if not touch:
                break
            for entry in here:
                if entry[4] and entry[7] and id(entry) in touch:
                    if entry[6]:
                        entry[7] = False   # not placed at all
                    else:
                        entry[4] = False   # a pinned room keeps it, walked through
                    lost += 1
    return lost


def furnish(
    bp: Blueprint, scenes: Sequence[Scene], **levels: float
) -> tuple[int, int, int, Counter[str]]:
    """Place every scene.

    Returns ``(models placed, triangles, dropped, refused)``.  ``dropped``
    counts the models that did not fit their room or landed inside world
    brushwork, which is a scene aimed wrong and is what the recipe refuses to
    ship on.  ``refused`` counts, by reason, the models a **placement rule**
    would not allow where they were asked for -- ``stairs``, ``doorway``,
    ``lane``, ``crowd``, ``panel`` -- which is the rule working, not a fault:
    a fill draws again and keeps its count, and a row or a one loses the piece
    it aimed into a staircase.  ``crowd moved`` is the one tally in it that is
    not a loss: a prop that landed in another prop and was slid off it by
    :func:`_step_aside` instead of being dropped.

    WHAT THE OVERLAP RULE COSTS, measured on one dense map by
    generating it with :meth:`_Crowd.is_large` narrowed back to its old
    both-sides gate and with :func:`_step_aside` switched off:

    ==============================  ==========  ===========
    ..                              both sides  either side
    ==============================  ==========  ===========
    models placed                        1,920        1,854
    props the rule looks at                169          259
    ``Z44`` prop-layout warnings            38           17
    of those, interpenetration              21            0
    props slid aside, not dropped            0           52
    ==============================  ==========  ===========

    (Props looked at, both counts on the map the wide gate produced; a pinned
    room is placed by neither and is left out.)

    The 66 models that went are 3% of the dressing, and 62 of the 66 are in
    one outdoor room: sandbags above all, 148 of them down to 84.  The fill deals
    those at a random yaw over ground that is already full, and a 20-by-35 bag
    turned 45 degrees measures 40.7 across, so it is the one model in this
    palette the wider gate catches by a hair.  No interior lost more than
    five.

    Every model is **stood on the surface under it and proved not to be
    inside a solid**, and that is not a nicety.  Placing two thousand models
    by rule hides them at scale: a scene aimed at a room's floor puts
    models inside the counters, tables, stacks and piers that stand on it.
    One early set of scenes put 570 of 2,811 models inside a world solid
    -- invisible, and passing every check, because no check covers props.
    So each one is snapped to :meth:`Blueprint.ground_under` (with ``below``,
    so a balcony does not answer for the floor beneath it, and a mug aimed at
    the floor ends up on the desk) and then tested against the world solids;
    anything still inside one is dropped rather than shipped invisible.

    The triangle figure is the sum of each placed model's own triangle count,
    so it is the number ``MAX_MAP_TRIANGLES`` (3,072,000) is spent against by
    the dressing alone -- world brushes and prefabs are on top of it.  It is
    returned rather than printed because the caller is the recipe, and the
    recipe is what has to refuse to build a map that will not compile.

    ``levels`` names the floor heights a scene refers to by name -- ``ground``,
    ``first``, ``second``, ``deck`` -- so a scene never repeats a
    coordinate the recipe already owns.  One ``place_props`` call per scene
    keeps the emitted entity ids grouped by room, which is what makes a
    misplaced prop findable in the written ``.map``.
    """
    from ..blueprint.elements import Prop

    grid = _solid_index(bp)
    rooms = _room_interiors(bp)
    crowd = _Crowd()
    panel_walls: set[tuple[str, str]] = set()
    total = 0
    triangles = 0
    dropped = 0
    refused: Counter[str] = Counter()
    every: list[list] = []
    scenes_kept: list[tuple] = []
    for scene in scenes:
        # A pinned room is placed by the original rules; see
        # :attr:`Scene.keep_as_is`.
        free = not scene.keep_as_is
        # (name, point, yaw, scale, size, solid, square, on_edge, row group)
        placed: list[tuple] = []
        draft = _Crowd()
        for order, item in enumerate(scene.items):
            tag = f"{scene.room}:{order}"
            if free and item.theme in RUINED_THEMES and not scene.ruined:
                # Broken masonry in a room nobody has broken.  See
                # :attr:`Scene.ruined`.
                refused["finished"] += getattr(item, "count", 1)
                continue
            if isinstance(item, One):
                name, size, tris = _model(item.theme, item.index)
                triangles += tris
                placed.append((
                    name, Point(item.x, item.y, _height(item.z, levels, scene.level)),
                    item.yaw, item.scale, size,
                    is_solid(name) if item.solid is None else item.solid,
                    False, False, None,
                ))
            elif isinstance(item, Row):
                z = _height(item.z, levels, scene.level)
                steps = max(item.count - 1, 1)
                run: list[list] = []
                for step in range(item.count):
                    ratio = step / steps if item.count > 1 else 0.0
                    name, size, tris = _model(
                        item.theme, item.first + step * item.spread, strewn=True
                    )
                    triangles += tris
                    x = item.x0 + (item.x1 - item.x0) * ratio
                    y = item.y0 + (item.y1 - item.y0) * ratio
                    at = bp.ground_under(x, y).z if item.on_terrain else z
                    yaw = item.yaw + item.yaw_step * step
                    yaw += _wander(tag, 1000 + step, item.vary)
                    run.append([
                        name, Point(x, y, at), round(yaw % 360.0, 1), item.scale, size,
                        is_solid(name) if item.solid is None else item.solid,
                        False, True, order,
                    ])
                # The thinning happens after fitting, not here: _fit_inside
                # slides a row up to 120 units toward its wall, and measured
                # on one map, 523 of 951 row props move more than
                # 8 units after being judged and 164 move more than the
                # 40-unit gap the thinner is enforcing.  Judging a row on the
                # coordinates it was authored at is judging the wrong row.
                placed.extend(tuple(row) for row in run)
            else:
                z = _height(item.z, levels, scene.level)
                span_x, span_y = item.x1 - item.x0, item.y1 - item.y0
                made = 0
                share = EDGE_SHARE if item.edge is None else item.edge
                for attempt in range(item.count * FILL_ATTEMPTS):
                    if made >= item.count:
                        break
                    on_edge = _hash(tag, attempt * 11 + 5) < share
                    if on_edge:
                        x, y = _edge_point(item, tag, attempt)
                    else:
                        x = item.x0 + span_x * _hash(tag, attempt * 3)
                        y = item.y0 + span_y * _hash(tag, attempt * 3 + 1)
                    if _avoid_zones(item.avoid).blocks((x, y)):
                        continue
                    roll = int(_hash(tag, attempt * 3 + 2) * 997)
                    index = item.pick[roll % len(item.pick)] if item.pick else roll
                    name, size, tris = _model(item.theme, index, strewn=True)
                    at = bp.ground_under(x, y).z if item.on_terrain else z
                    if free and not scene.ruined and is_rubble(name):
                        # Broken masonry in a room nobody has broken.
                        refused["finished"] += 1
                        continue
                    if free and mount_kind(name) != MOUNT_FLOOR:
                        # A fill strews a floor.  A clock, a duct or a
                        # chandelier has no pose on one, so the fill draws
                        # again rather than dealing it out (:func:`mount_kind`).
                        refused["fixture"] += 1
                        continue
                    if free:
                        # Draw again rather than place here.  This is what
                        # keeps a room's count when the zones take a corner of
                        # its floor away: the fill has attempts in hand, so it
                        # spends them somewhere the prop is allowed to be.
                        # The yaw is not decided yet, so the footprint here is
                        # the model's own box; the exact test runs below on the
                        # yaw the piece ends up with.
                        half = plan_half_extent(name, size, 0.0, item.scale)
                        here = Point(x, y, at)
                        zone = _no_prop_zone(
                            bp, here, half,
                            solid=is_solid(name) if item.solid is None else item.solid,
                        )
                        if zone is not None:
                            refused[zone] += 1
                            continue
                        low, high = _vertical_span(name, at, item.scale)
                        if (crowd.crowded(x, y, half[0], half[1], low, high)
                                or draft.crowded(x, y, half[0], half[1], low, high)):
                            refused["crowd"] += 1
                            continue
                        draft.add(x, y, half[0], half[1], low, high)
                    triangles += tris
                    solid = is_solid(name) if item.solid is None else item.solid
                    placed.append((
                        name, Point(round(x, 1), round(y, 1), at),
                        round(_hash(tag, attempt * 7) * 360.0, 1), item.scale, size,
                        solid,
                        # Furniture strewn over a floor is squared up against
                        # the room; litter keeps the free draw it was given.
                        solid,
                        # but everything drawn against an edge is slid the
                        # last few units so its back is on the wall.
                        on_edge,
                        None,
                    ))
                    made += 1
        # A piece has to know which way it is facing before it can be fitted,
        # because the box it takes up is the box *at that yaw* -- the shelf
        # that is 113 units long is 31 deep once it is laid along the wall.
        surfaces = [(row[0], row[1]) for row in placed if _is_surface(row[0])]
        aimed: list[tuple] = []
        for index, (name, point, yaw, scale, size, solid, square, on_edge,
                    group) in enumerate(placed):
            if square:
                yaw = _squared_yaw(name, point, yaw, rooms, surfaces,
                                   f"{scene.room}:{index}")
            aimed.append((name, point, yaw, scale, size, solid, square, on_edge, group))
        # Fit first, thin the rows on where the pieces actually landed, and
        # only then apply the rules that refuse a place outright.
        sited: list[list] = []
        for name, point, yaw, scale, size, solid, square, on_edge, group in aimed:
            # A wall clock and a chandelier are not furniture: neither is
            # fitted to a floor, stood on a surface or given collision.  They
            # go on the wall plane and the ceiling plane instead.
            if free and not scene.ruined and is_rubble(name):
                refused["finished"] += 1
                triangles -= _tris(name)
                continue
            if free and mount_kind(name) != MOUNT_FLOOR:
                hung = _mounted_place(bp, name, point, size, scale)
                if hung is None:
                    refused["fixture"] += 1
                    triangles -= _tris(name)
                    continue
                sited.append([name, hung[0], hung[1], scale, size, False,
                              None, False])
                continue
            allowance = (EDGE_BAND + WALL_REACH) if on_edge else (
                WALL_REACH if square else 0.0)
            fitted = _fit_inside(rooms, point, size, scale, name, yaw, hug=allowance)
            if fitted is None:
                dropped += 1
                triangles -= _tris(name)
                continue
            if not free and solid and _no_prop_zone(
                bp, fitted, plan_half_extent(name, size, yaw, scale), stairs=False
            ):
                solid = False
            hit = bp.ground_under(fitted.x, fitted.y, below=point.z + SURFACE_REACH)
            rest = hit.z if (hit.found and hit.z >= point.z - 8.0) else point.z
            if free:
                # Standing on a block means standing *on* it: a prop that
                # hangs off the block it landed on belongs on the floor
                # beside the block, not in the air over its edge.
                rect = _block_rect(bp, hit, fitted.x, fitted.y)
                if rect is not None:
                    on_block = _fit_on_block(rect, fitted, name, size, yaw, scale)
                    if on_block is None:
                        # Below the block, and below it by more than the step
                        # tolerance ``ground_under`` allows, or it answers
                        # with the same block again.
                        under = bp.ground_under(fitted.x, fitted.y,
                                                below=hit.z - STEP_DOWN)
                        rest = (under.z if under.found and under.z < hit.z - 0.5
                                else rest)
                    else:
                        fitted = on_block
            if _in_solid(grid, Point(fitted.x, fitted.y, rest + 6.0)):
                dropped += 1
                triangles -= _tris(name)
                continue
            # The z counterpart of the plan-centre correction: a model whose
            # own box starts below its origin is placed by that origin, so a
            # 130-unit rebar column authored about its middle arrived 65 units
            # short.  Emit it at the surface minus its own box bottom.
            if free:
                rest -= min(0.0, _model_floor(name) * scale)
            if free:
                low, high = _vertical_span(name, rest, scale)
                clear = _clear_of_solids(bp, rooms, Point(fitted.x, fitted.y, rest),
                                         name, size, yaw, scale, low, high)
                if clear is None:
                    refused["brushwork"] += 1
                    triangles -= _tris(name)
                    continue
                fitted = clear
            else:
                # A pinned room keeps its look, but not a buy nobody can use.
                low, high = _vertical_span(name, rest, scale)
                fitted = _clear_of_items(bp, rooms, Point(fitted.x, fitted.y, rest),
                                         name, size, yaw, scale, low, high)
            sited.append([name, Point(fitted.x, fitted.y, rest), yaw, scale,
                          size, solid, group, square])

        # A seat in a row is aimed like a seat in a fill: its own measured
        # front (:data:`MODEL_FRONT`) has to look into the room rather than
        # into the wall the row runs along.  Turning it right round is the
        # only move a row can make without breaking its own line.
        if free:
            for row in sited:
                row[2] = _seat_turned(bp, rooms, row[0], row[1], row[2],
                                      row[4], row[3])

        # A free-standing run of solid props with no gaps in it is a fence, on
        # the coordinates the pieces ended up at.
        runs: dict[int, list[list]] = defaultdict(list)
        for row in sited:
            if row[6] is not None:
                runs[row[6]].append(row)
        survives = {id(row) for row in sited if row[6] is None}
        for run in runs.values():
            for row in _thin_a_fence(run, rooms, free=free):
                survives.add(id(row))
        thinned = [row for row in sited if id(row) in survives]
        refused["fence"] += len(sited) - len(thinned)
        triangles -= sum(_tris(row[0]) for row in sited if id(row) not in survives)

        kept: list[list] = []
        for name, where, yaw, scale, size, solid, _group, square in thinned:
            half = plan_half_extent(name, size, yaw, scale)
            low, high = _vertical_span(name, where.z, scale)
            if free and mount_kind(name) != MOUNT_FLOOR:
                # On a wall or a ceiling: no *floor* rule has anything to say
                # about it, and it takes no floor away from the ones that do.
                # What still applies is what is on the wall beside it.
                if _crowds_an_item(bp, where, half, low, high):
                    refused["interactive"] += 1
                    triangles -= _tris(name)
                    continue
                # A doorway is a hole, so nothing refuses a sign hung across
                # one: it lands with no wall behind half of it (24 fixtures did on
                # a test map).  No rise here -- a fixture
                # whose own height overlaps the opening's is over the opening.
                if _keep_clear(bp)["doorway"].blocks(
                    Poly2.rect(where.x - half[0], where.y - half[1],
                               where.x + half[0], where.y + half[1]),
                    z_low=low, z_high=high,
                ):
                    refused["door"] += 1
                    triangles -= _tris(name)
                    continue
                kept.append([name, where, yaw, scale, False, square, free, True])
                continue
            if free:
                zone = _no_prop_zone(bp, where, half, solid=solid, span=(low, high))
                if zone is not None:
                    refused[zone] += 1
                    triangles -= _tris(name)
                    continue
                if crowd.crowded(where.x, where.y, half[0], half[1], low, high):
                    # Move it before dropping it: a piece that will not go
                    # where the scene said still belongs in the room.
                    aside = _step_aside(bp, rooms, crowd, name, where, size,
                                        yaw, scale, low, high, solid)
                    if aside is None:
                        refused["crowd"] += 1
                        triangles -= _tris(name)
                        continue
                    refused["crowd moved"] += 1
                    where = aside
                    # It stepped aside and may have stepped down a slope with
                    # it, so the height everything below judges it at is the
                    # height it is now at.
                    low, high = _vertical_span(name, where.z, scale)
                if is_panel_model(name) and not _panel_may_lean(
                    rooms, where, panel_walls
                ):
                    refused["panel"] += 1
                    triangles -= _tris(name)
                    continue
            crowd.add(where.x, where.y, half[0], half[1], low, high)
            kept.append([name, where, yaw, scale, solid, square, free, True])
        every.extend(kept)
        scenes_kept.append((scene, kept))
    refused["twin"] += _dedupe(every)
    refused["pocket"] += _open_the_pockets(every, rooms, bp)
    for scene, all_kept in scenes_kept:
        kept = [row for row in all_kept if row[7]]
        triangles -= sum(_tris(row[0]) for row in all_kept if not row[7])
        if kept:
            bp.place_props(
                [
                    Prop(
                        model=name,
                        origin=_placed_origin(name, where, yaw, scale),
                        yaw=yaw,
                        scale=scale,
                        solid=solid,
                        collision_box=collision_box(name) if solid else None,
                    )
                    for name, where, yaw, scale, solid, _square, _free, _alive in kept
                ],
                id=f"dressing_{scene.room}",
            )
            total += len(kept)
    return total, triangles, dropped, refused
