"""zm_dmv dense pass: the back office (key ``office``).  See the package docstring.

The operator's lair.  Everything in here is filed, stamped, pending, and
staring back through the glass; the arena floor is where the paperwork ends
up.  What this pass adds, solids against the walls and behind the counter,
only flat litter on the floor players fight on:

* **the operator's desk** -- more paper, and two file drawers pulled out and
  dumped on the booth floor;
* **the back shelves** -- a second shelf in the booth's east corner, boxes
  stacked beside it, and whatever fits on top of both;
* **the counter** -- the RING FOR SERVICE button, stacks, forms and a binder
  on the public side of the glass, closed blinds on one pane, and an OFFICE
  plate over the slot;
* **the filing wall** -- the tops of the west cabinets, and three Employee of
  the Month frames over the notice board (all Gary);
* **the manager's couch** -- by the door, with the manager's clothes;
* **the satisfaction kiosk** -- on the east wall, south of the stapler;
* **the east wall** -- a bench with somebody's suitcase, a caution sign;
* **the paper storm** -- forms, sheets and newspapers across the arena floor,
  thickest along the walls and the counter face, and the cups;
* three notices: the service bell, Employee of the Month, the kiosk.
"""
from __future__ import annotations

from ._kit import (
    Facing,
    Point,
    RoomContext,
    _centred,
    _floor,
    _mounted,
    _on,
    _rest_on,
    _top_of,
    shelf_boards,
)

#: The room's use-trigger jokes (shape of :data:`zmforge.recipes.dmv.NOTICE_LINES`).
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "office_service_bell": ("RING FOR SERVICE: hold ^3[{+activate}]^7", (
        "You rang. Please wait.",
        "You rang again. Your request has moved to the back of the queue.",
        "The operator is aware of you.",
    )),
    "office_employee_month": ("EMPLOYEE OF THE MONTH: hold ^3[{+activate}]^7 to read", (
        "JANUARY: Gary.",
        "FEBRUARY: Gary.",
        "MARCH TO PRESENT: position closed.",
    )),
    "office_survey": ("HOW WAS YOUR VISIT? hold ^3[{+activate}]^7 to rate", (
        "You rated your visit 1 star. Thank you.",
        "Your rating has been rounded down.",
        "Ratings are reviewed by the manager. The manager is in a meeting.",
    )),
}

#: The named story vignettes and the scatter id each one goes out under.
VIGNETTES: dict[str, str] = {
    "operator_desk": "dense_office_operator_desk",
    "back_shelves": "dense_office_back_shelves",
    "counter": "dense_office_counter",
    "glass": "dense_office_glass",
    "filing_wall": "dense_office_filing_wall",
    "employee_of_the_month": "dense_office_employee_of_the_month",
    "manager_couch": "dense_office_manager_couch",
    "survey_kiosk": "dense_office_survey_kiosk",
    "east_wall": "dense_office_east_wall",
    "paper_storm": "dense_office_paper_storm",
    "cups": "dense_office_cups",
}

_DESK = "p7_desk_metal_old_01_body"
_SHELF = "p7_shelf_industrial_vintage_96"
_CABINET = "p7_zm_der_cabinet_lab_bottom"
_BOX = "p7_container_cardboard_box_01"
_BELL = "p7_elevator_call_box"


def dress(ctx: RoomContext) -> None:
    """Fill the back office."""
    room = ctx.room
    b_in = room.interior                     # x 896..1464, y 484..1152
    z = room.floor_z
    plan = ctx.plan
    counter_north = b_in.maxs.y - plan.booth_depth        # 1056
    counter_south = counter_north - 16.0                  # 1040
    counter_y = counter_north - 8.0
    counter_top = z + plan.counter_height
    desk_x, desk_y = b_in.centre.x - 120.0, counter_north + 40.0   # 1060, 1096
    desk_top = _top_of(_DESK, z)
    x0, x1, y0, y1 = b_in.mins.x, b_in.maxs.x, b_in.mins.y, b_in.maxs.y

    # ---- the operator's desk: more paper, and the drawers dumped --------
    ctx.put([
        _on("p7_office_paper_folder_blue", desk_x - 10.0, desk_y + 30.0, desk_top, 70.0),
        _on("p7_office_paper_stack_sml", desk_x - 6.0, desk_y - 10.0, desk_top, 350.0),
        _on("p7_book_office_med_brown", desk_x + 12.0, desk_y + 32.0, desk_top, 0.0),
        _floor("p7_file_cab_metal_02_drawer_02", 1172.0, 1098.0, z, 200.0, solid=False),
        _floor("p7_file_cab_metal_02_drawer_02", 1206.0, 1090.0, z, 160.0, solid=False),
        # A hanging lamp over the desk: the only lit desk in the building.
        _centred("p7_light_hanging_modern_02", desk_x, desk_y + 4.0, b_in.maxs.z, 0.0),
    ], VIGNETTES["operator_desk"])

    # ---- the back shelves: a second shelf, and the boxes ----------------
    shelf_x, shelf_y = x1 - 64.0, y1 - 18.0                         # 1400, 1134
    shelf_top = shelf_boards(_SHELF, z)[-1]  # the top board, under the frame
    old_shelf_x = x0 + 52.0
    box_x, box_y = x1 - 20.0, counter_north + 26.0                  # 1444, 1082
    box_top = _top_of(_BOX, z)
    ctx.put([
        _floor(_SHELF, shelf_x, shelf_y, z, 0.0),
        _on(_BOX, shelf_x - 26.0, shelf_y, shelf_top, 0.0),
        _on("p7_books_office_row_01", shelf_x + 18.0, shelf_y - 2.0, shelf_top, 0.0),
        _on("p7_book_office_lrg_red", shelf_x + 34.0, shelf_y, shelf_top, 0.0),
        _on("p7_books_office_row_01", old_shelf_x - 30.0, y1 - 18.0, shelf_top, 0.0),
        _on("p7_book_office_binder_open", old_shelf_x + 20.0, y1 - 18.0, shelf_top, 10.0),
        # Two boxes stacked against the east wall inside the booth.
        _floor(_BOX, box_x, box_y, z, 90.0),
        _centred(_BOX, box_x, box_y, _rest_on(_BOX, box_top), 95.0, solid=True),
        _on("p7_office_paper_stack_sml", box_x, box_y, _top_of(_BOX, box_top), 20.0),
    ], VIGNETTES["back_shelves"])

    # ---- the counter: the public side of the glass ----------------------
    ctx.put([
        # RING FOR SERVICE, looking out through the slot.
        _on(_BELL, 1168.0, counter_y - 2.0, counter_top, 0.0),
        _on("p7_office_paper_stack_sml", 1270.0, counter_y, counter_top, 280.0),
        _on("p7_book_office_binder_open", 1235.0, counter_y, counter_top, 90.0),
        _on("p7_office_paper_sheet_01", 960.0, counter_y - 2.0, counter_top, 20.0),
        _on("p7_office_paper_sheet_03", 1030.0, counter_y + 1.0, counter_top, 70.0),
        _on("p7_cup_coffee_mug", 1290.0, counter_y, counter_top, 200.0),
    ], VIGNETTES["counter"])

    # ---- the glass: blinds down, and a plate over the slot --------------
    glass_z = counter_top + plan.service_slot                           # 94
    ctx.put([
        _mounted("p7_blinds_01_closed", Point(930.0, counter_south - 2.0, glass_z + 52.0),
                 Facing.SOUTH),
        _mounted("p7_zm_der_signage_office_maxis",
                 Point(desk_x, counter_south - 1.0, glass_z + 20.0), Facing.SOUTH),
    ], VIGNETTES["glass"])

    # ---- the filing wall: on top of the west cabinets --------------------
    cab_top = _top_of(_CABINET, z)
    cab_x = x0 + 16.0
    ctx.put([
        _on("p7_books_office_row_01", cab_x, 815.0, cab_top, 90.0),
        _on("p7_office_paper_stack_sml", cab_x, 846.0, cab_top, 60.0),
        _on("p7_book_office_binder_open", cab_x, 958.0, cab_top, 0.0),
        _on(_BOX, cab_x, 996.0, cab_top, 90.0),
    ], VIGNETTES["filing_wall"])

    # ---- Employee of the Month: three frames over the notice board -------
    ctx.put([
        _mounted("p7_picture_frame_modern_01", Point(x0 + 1.0, y, z + 124.0), Facing.EAST)
        for y in (872.0, 909.0, 946.0)
    ], VIGNETTES["employee_of_the_month"])

    # ---- the manager's couch, by the door --------------------------------
    couch_x = 1310.0
    ctx.put([
        # Backrest on the model's +y (mesh measured: the plan
        # centroid of its top quarter sits 5.4 to +y, the lab chair's does
        # the same and its MODEL_FRONT is -90), so it looks -y at yaw 0 and
        # yaw 180 puts its back on the south wall, facing into the room.
        _floor("p7_couch_modern_leather", couch_x, y0 + 24.0, z, 180.0),
        _floor("p7_cai_apt_couch_cushion_sml", couch_x - 40.0, y0 + 66.0, z, 30.0,
               solid=False),
        _floor("p7_debris_clothing_piles_01", couch_x + 20.0, y0 + 80.0, z, 80.0, solid=False),
        _floor("p7_debris_clothing_tshirts_01", couch_x + 60.0, y0 + 64.0, z, 200.0,
               solid=False),
        # NOW SERVING, over the door, for whoever is still on the couch.
        _mounted("p7_cai_monitor_wall_large", Point(1180.0, y0 + 0.5, z + 170.0),
                 Facing.NORTH),
    ], VIGNETTES["manager_couch"])

    # ---- the satisfaction kiosk, south of the stapler -------------------
    ctx.put([
        _floor("p7_cai_sign_inteactive_kiosk", x1 - 7.0, y0 + 46.0, z, 90.0),
    ], VIGNETTES["survey_kiosk"])

    # ---- the east wall: a bench, a suitcase, a sign ----------------------
    bench_y = counter_south - 42.0                                    # 998
    ctx.put([
        _floor("p7_bench_modern_01", x1 - 10.0, bench_y, z, 90.0),
        _on("p7_luggage_hardshell_handle_down_white", x1 - 10.0, bench_y + 18.0,
            _top_of("p7_bench_modern_01", z), 90.0),
        _mounted("p7_signage_caution_warning_01", Point(x1 - 1.0, bench_y, z + 104.0),
                 Facing.WEST),
        _floor("p7_cleaning_paper_ball_brown", 1418.0, 918.0, z, 0.0, solid=False),
        _floor("p7_cleaning_paper_ball_brown", 1422.0, 954.0, z, 70.0, solid=False),
        # The broken cooler by Stamin-Up: somebody tried.
        _floor("p7_water_cooler_digital_body_dmg", x0 + 10.0, 585.0, z, 0.0),
    ], VIGNETTES["east_wall"])

    # ---- the paper storm: edge-heavy, thin in the middle -----------------
    ctx.put([
        _floor(model, x, y, z, yaw, solid=False)
        for model, x, y, yaw in (
            # along the west wall
            ("p7_office_paper_sheet_02", 960.0, 600.0, 15.0),
            ("p7_debris_newspaper_05", 990.0, 780.0, 100.0),
            ("p7_office_paper_sheet_09", 950.0, 1010.0, 200.0),
            ("p7_office_paper_sheet_03", 1000.0, 880.0, 60.0),
            # along the east wall
            ("p7_office_paper_sheet_10", 1400.0, 620.0, 30.0),
            ("p7_debris_newspaper_01", 1410.0, 830.0, 250.0),
            ("p7_office_paper_sheet_08", 1390.0, 985.0, 120.0),
            ("p7_debris_paper_sheet_01", 1350.0, 720.0, 10.0),
            # the counter face, where the forms were handed back
            ("p7_office_paper_sheet_12", 1000.0, 1022.0, 80.0),
            ("p7_zm_debris_newspaper_german_01", 1090.0, 1012.0, 35.0),
            ("p7_office_paper_sheet_03", 1160.0, 1026.0, 170.0),
            ("p7_office_paper_sheet_09", 1222.0, 1008.0, 300.0),
            ("p7_debris_newspaper_04", 1280.0, 1016.0, 140.0),
            # the south end, by the door
            ("p7_debris_newspaper_06", 1180.0, 570.0, 45.0),
            ("p7_office_paper_sheet_08", 1330.0, 590.0, 220.0),
            # the middle, thin
            ("p7_debris_newspaper_03", 1250.0, 690.0, 75.0),
            ("p7_debris_paper_sheet_01", 1300.0, 650.0, 190.0),
        )
    ], VIGNETTES["paper_storm"])

    # ---- the cups, in front of the counter ------------------------------
    ctx.put([
        _floor(model, x, y, z, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_trash_cup_coffee_02", 1040.0, 998.0, 20.0),
            ("p7_debris_trash_cup_coffee_02", 1132.0, 986.0, 140.0),
            ("p7_debris_trash_cup_red_02", 1192.0, 978.0, 0.0),
            ("p7_debris_trash_drink_carrier_01", 1080.0, 966.0, 15.0),
        )
    ], VIGNETTES["cups"])

    _office_dense2(ctx)
    _office_shelf_boards(ctx)


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """Where each of :data:`NOTICES` stands, on reachable arena floor, 80+
    from Stamin-Up, the stapler, the manager's notice and each other."""
    z = ctx.room.floor_z
    return [
        ("office_service_bell", Point(1168.0, 996.0, z)),
        ("office_employee_month", Point(975.0, 909.0, z)),
        ("office_survey", Point(1390.0, 580.0, z)),
    ]


# ==========================================================================
# Dense pass 2: far more props, so the room reads as a DMV
# ==========================================================================
# A second clerk's desk in the booth, the booth's shelves and corners full,
# the counter covered in forms, filing cabinets on the south and east
# walls, the manager's bedding, notices on every wall and a far heavier
# paper storm.  The booth is walked (the gap at its east end is the way in),
# so its north wall takes the furniture and the 60 in front of it stays
# open; out on the arena every solid is against a wall and every piece on
# the floor is 12 high at most (test_the_arena_floor_stays_open).
from ._kit import _seated  # noqa: E402
from .records import _book_row, _FLAT, _put_clear, _trail  # noqa: E402  (shared helpers)

VIGNETTES.update({
    "clerk_desk": "dense_office_clerk_desk",
    "booth_shelves": "dense_office_booth_shelves",
    "booth_files": "dense_office_booth_files",
    "booth_litter": "dense_office_booth_litter",
    "counter_forms": "dense_office_counter_forms",
    "filing_rows": "dense_office_filing_rows",
    "south_cabinets": "dense_office_south_cabinets",
    "east_cabinets": "dense_office_east_cabinets",
    "bench_top": "dense_office_bench_top",
    "manager_bed": "dense_office_manager_bed",
    "wall_notices": "dense_office_wall_notices",
    "arena_litter": "dense_office_arena_litter",
})

_FILE_CAB = "p7_file_cab_metal_02"
_STACK = "p7_office_paper_stack_sml"


def _office_dense2(ctx: RoomContext) -> None:
    """The second dense pass: the back office, buried in paper."""
    b_in, z = ctx.room.interior, ctx.room.floor_z
    x0, x1, y0, y1 = b_in.mins.x, b_in.maxs.x, b_in.mins.y, b_in.maxs.y
    plan = ctx.plan
    counter_north = y1 - plan.booth_depth                              # 1056
    counter_south = counter_north - 16.0                               # 1040
    counter_top = z + plan.counter_height                              # 58
    desk_top = _top_of(_DESK, z)
    shelf_top = shelf_boards(_SHELF, z)[-1]  # the top board, under the frame
    box_top = _top_of(_BOX, z)
    fc_top = _top_of(_FILE_CAB, z)
    # Use spots and risers the litter keeps off.
    keep_out = ((960.0, 684.0, 60.0), (1420.0, 684.0, 60.0), (1168.0, 996.0, 30.0),
                (975.0, 909.0, 30.0), (1390.0, 580.0, 30.0), (952.0, 532.0, 30.0),
                (1408.0, 532.0, 30.0), (1180.0, 500.0, 40.0))

    # ---- a second clerk's desk against the booth's north wall ------------
    # The chair is tucked under it and not solid: the booth's only walk runs
    # between it and the counter.
    cdx, cdy = 1310.0, y1 - 18.0                                       # 1310, 1134
    ctx.put([
        _floor(_DESK, cdx, cdy, z, 180.0),
        _seated("p7_chair_lab_01", Point(cdx - 4.0, cdy - 30.0, _rest_on("p7_chair_lab_01", z)),
                Facing.NORTH, solid=False),
        _on("p7_consumer_grade_monitor_medium", cdx, cdy + 12.0, desk_top, 180.0),
        _on("p7_keyboard_metal_tech", cdx - 4.0, cdy - 5.0, desk_top, 180.0, scale=0.8),
        _on("p7_office_paper_folder_blue", cdx - 25.0, cdy + 2.0, desk_top, 0.0),
        _on("p7_cup_coffee_mug", cdx + 28.0, cdy, desk_top, 150.0),
        _on("p7_debris_trash_cup_coffee_02", cdx + 30.0, cdy - 10.0, desk_top, 0.0),
    ], "dense_office_clerk_desk")

    # ---- the booth shelves: boxed on top, boxed underneath ---------------
    shelves: list[tuple] = [
        _on(_BOX, 942.0, y1 - 18.0, shelf_top, 0.0, scale=0.85),
        _on(_STACK, 942.0, y1 - 18.0, _top_of(_BOX, shelf_top) - 25.4 * 0.15, 80.0),
        _on(_BOX, 1374.0, y1 - 18.0, box_top - z + shelf_top, 2.0),
        _on(_STACK, 1370.0, y1 - 18.0, _top_of(_BOX, box_top - z + shelf_top), 95.0),
    ]
    for bx in (915.0, 950.0, 1370.0, 1405.0):
        shelves.append(_on(_BOX, bx, y1 - 18.0, z, 0.0, scale=0.75))
    shelves += [_on(_STACK, 982.0, y1 - 18.0, z, 90.0), _on(_STACK, 1437.0, y1 - 18.0, z, 90.0)]
    ctx.put(shelves, "dense_office_booth_shelves")

    # ---- the booth's dead west end: two cabinets and the overflow --------
    # (the operator's desk closes it off, so none of this is on a walk)
    ctx.put([
        _floor(_FILE_CAB, 1010.0, y1 - 14.75, z, 0.0),
        _floor(_FILE_CAB, 1030.0, y1 - 14.75, z, 0.0),
        _on("p7_books_office_row_01", 1010.0, y1 - 12.0, fc_top, 0.0),
        _on(_STACK, 1030.0, y1 - 16.0, fc_top, 90.0),
        _on("p7_office_paper_folder_pink", 1030.0, y1 - 16.0, _top_of(_STACK, fc_top), 30.0),
        _floor("p7_file_cab_metal_02_drawer_02", 1020.0, counter_north + 36.0, z, 10.0,
               solid=False),
        _floor(_BOX, 925.0, counter_north + 26.0, z, 0.0, solid=False),
        _centred(_BOX, 925.0, counter_north + 26.0, _rest_on(_BOX, box_top), 6.0),
        _on(_STACK, 922.0, counter_north + 26.0, _top_of(_BOX, box_top), 10.0),
        _floor(_BOX, 972.0, counter_north + 24.0, z, 20.0, solid=False),
    ], "dense_office_booth_files")
    _put_clear(ctx, _trail(904.0, counter_north + 6.0, 1440.0, y1 - 8.0, 44, 23, z),
               "dense_office_booth_litter")

    # ---- the counter: forms, binders, pens in a mug ----------------------
    _put_clear(ctx, [
        _on(model, x, counter_south + 8.0, counter_top, yaw)
        for model, x, yaw in (
            (_STACK, 912.0, 90.0), ("p7_book_office_binder_open", 940.0, 90.0),
            ("p7_books_office_row_01", 976.0, 0.0), ("p7_office_paper_sheet_08", 1012.0, 30.0),
            (_STACK, 1054.0, 90.0), ("p7_office_paper_folder_blue", 1080.0, 10.0),
            ("p7_cup_coffee_mug", 1100.0, 60.0), ("p7_office_paper_sheet_10", 1138.0, 80.0),
            ("p7_office_paper_folder_pink", 1184.0, 350.0), ("p7_books_office_row_01", 1214.0, 0.0),
            ("p7_office_paper_sheet_12", 1250.0, 45.0), (_STACK, 1284.0, 90.0),
        )
    ], "dense_office_counter_forms")

    # ---- the west cabinet run: every gap on top --------------------------
    cab_x = x0 + 16.0
    cab_top = _top_of(_CABINET, z)
    box_on_cab = _top_of(_BOX, cab_top)
    rows = _book_row(cab_x, 861.0, cab_top, 5) + _book_row(cab_x, 914.0, cab_top, 6)
    rows += [
        _on(_STACK, cab_x, 888.0, cab_top, 0.0),
        _on("p7_books_office_row_01", cab_x, 905.0, cab_top, 0.0),
        _on("p7_office_paper_folder_blue", cab_x, 938.0, cab_top, 90.0),
        _on(_BOX, cab_x, 996.0, box_on_cab, 92.0),
        _on(_STACK, cab_x, 996.0, _top_of(_BOX, box_on_cab), 5.0),
    ]
    ctx.put(rows, "dense_office_filing_rows")

    # ---- filing cabinets on the south wall, west of the waiting chairs ---
    ctx.put([
        _floor(_FILE_CAB, 995.0, y0 + 15.25, z, 180.0),
        _floor(_FILE_CAB, 1015.0, y0 + 15.25, z, 180.0),
        _on("p7_books_office_row_01", 995.0, y0 + 12.0, fc_top, 0.0),
        _on(_STACK, 1015.0, y0 + 16.0, fc_top, 90.0),
        _on("p7_office_paper_folder_blue", 1015.0, y0 + 16.0, _top_of(_STACK, fc_top), 300.0),
    ], "dense_office_south_cabinets")

    # ---- and three on the east wall, north of the stapler's reach --------
    ctx.put([
        _floor(_FILE_CAB, x1 - 14.75, y, z, 270.0) for y in (810.0, 830.0, 850.0)
    ] + [
        _on("p7_books_office_row_01", x1 - 12.0, 806.0, fc_top, 90.0),
        _on(_STACK, x1 - 16.0, 830.0, fc_top, 0.0),
        _on("p7_book_office_binder_open", x1 - 16.0, 850.0, fc_top, 90.0),
        _on("p7_office_paper_folder_pink", x1 - 16.0, 830.0, _top_of(_STACK, fc_top), 60.0),
    ], "dense_office_east_cabinets")

    # ---- the bench: forms somebody was filling in ------------------------
    bench_top = _top_of("p7_bench_modern_01", z)
    ctx.put([
        _on(_STACK, x1 - 10.0, 975.0, bench_top, 90.0),
        _on("p7_office_paper_folder_blue", x1 - 10.0, 992.0, bench_top, 90.0),
    ], "dense_office_bench_top")

    # ---- the manager's bed: a pillow by the couch, and his supper -------
    ctx.put([
        _floor("p7_bed_pillow_barrack", 1290.0, 600.0, z, 10.0, solid=False),
        _floor("p7_cup_coffee_mug", 1250.0, 600.0, z, 30.0, solid=False),
        _floor("p7_bottle_plastic_16oz_water", 1240.0, 540.0, z, 0.0, solid=False),
        _floor("p7_book_vintage_open_04", 1360.0, 600.0, z, 25.0, solid=False),
    ], "dense_office_manager_bed")

    # ---- notices on every wall -------------------------------------------
    ctx.put([
        _mounted("p7_cai_signage_plastic_exit", Point(1180.0, y0 + 1.3, z + 126.0),
                 Facing.NORTH),
        _mounted("p7_zm_der2_bulletin_board", Point(1060.0, y0 + 3.0, z + 94.0), Facing.NORTH),
        _mounted("p7_clock_metal_wall_01_base", Point(1290.0, y0 + 3.0, z + 116.0),
                 Facing.NORTH),
        _mounted("p7_signage_caution_warning_01", Point(1420.0, y0 + 1.0, z + 94.0),
                 Facing.NORTH),
        _mounted("p7_zm_der2_poster_anatomy_01", Point(x0 + 0.5, 612.0, z + 96.0), Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(x0 + 1.0, 522.0, z + 94.0), Facing.EAST),
        _mounted("p7_zm_der_signage_hazard_04", Point(x0 + 1.0, 764.0, z + 96.0), Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(x0 + 1.0, 1000.0, z + 116.0), Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(x1 - 1.0, 608.0, z + 104.0), Facing.WEST),
        _mounted("p7_zm_der2_bulletin_board", Point(x1 - 3.0, 760.0, z + 94.0), Facing.WEST),
        _mounted("p7_clock_metal_wall_01_base", Point(x1 - 3.0, 910.0, z + 116.0), Facing.WEST),
        _mounted("p7_blinds_01_closed", Point(1275.0, counter_south - 2.0,
                                              counter_top + plan.service_slot + 52.0),
                 Facing.SOUTH),
    ], "dense_office_wall_notices")

    # ---- the paper storm, the rest of it ---------------------------------
    _put_clear(ctx, _trail(x0 + 30.0, y0 + 30.0, x1 - 30.0, counter_south - 10.0, 90, 17, z,
                           _FLAT + ("p7_debris_trash_cup_coffee_02", "p7_debris_newspaper_05",
                                    "p7_debris_trash_cup_red_02", "p7_zm_debris_newspaper_german_03")),
               "dense_office_arena_litter", keep_out=keep_out)


# --------------------------------------------------------------------------
# Inside the two booth shelving units
# --------------------------------------------------------------------------
# Both vintage units along the booth's back wall had things on their tops and
# nothing on the two boards below (the layout check only knew the tops until
# props.SHELF_BOARDS).  Each board has 28 under the next one, room for the
# archive cartons as well as the files.  Vignette ``dense_office_shelf_boards``.
from .records import _fill_board, _put_on_boards, _shelf_levels  # noqa: E402


def _office_shelf_boards(ctx: RoomContext) -> None:
    """Cartons, files and binders on the inner boards of both booth shelves."""
    b_in, z = ctx.room.interior, ctx.room.floor_z
    x0, x1, y1 = b_in.mins.x, b_in.maxs.x, b_in.maxs.y
    items: list[tuple] = []
    for n, cx in enumerate((x0 + 52.0, x1 - 64.0)):
        for k, (top, room) in enumerate(_shelf_levels(_SHELF, z)):
            items += _fill_board(y1 - 18.0, cx - 46.0, cx + 46.0, top, room,
                                 11 + 5 * n + k, axis="x", empty=0.1)
    _put_on_boards(ctx, items, "dense_office_shelf_boards")
