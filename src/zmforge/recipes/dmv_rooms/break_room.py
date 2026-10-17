"""zm_dmv dense pass: the break room (key ``break``).  See the package docstring.

Staff went on break at 11:58 and never clocked back in.  The coffee is still
on, and Gary's party is still happening, in a sense.  What this pass adds:

* **the party table** -- napkins and a plate squeezed in round the donuts and
  the cake, a roast turkey on top of the fridge that nobody claims;
* **the kitchenette** -- the radio and another mug;
* **the time clock** -- a second wall clock by the door that disagrees with
  the room's, and the time cards dropped under it;
* **the safety board** -- a chalkboard on the west wall (DAYS WITHOUT AN
  INCIDENT: 0);
* **the breaker corner** -- hazard plates either side of the power switch,
  kept clear of its trigger;
* **the nap spot** -- a pillow on the floor between the chairs and the
  kitchenette;
* **the bin** -- overflowing, and the floor round it;
* three notices: the time clock, the radio and the safety board.
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
)

#: The room's use-trigger jokes (shape of :data:`zmforge.recipes.dmv.NOTICE_LINES`).
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "break_time_clock": ("TIME CLOCK: hold ^3[{+activate}]^7 to punch in", (
        "Punched in. Your break ended 212 days ago.",
        "Punched out. Overtime requires Form 27-B.",
        "GARY: clocked in 06/14. Not clocked out.",
        "Card jammed. Please see a manager.",
    )),
    "break_radio": ("RADIO: hold ^3[{+activate}]^7 to change station", (
        "...all branches remain open regular hours. Please remain in line...",
        "Smooth jazz.",
        "EMERGENCY BROADCAST: stay indoors. Take a number.",
        "Smooth jazz.",
    )),
    "break_safety_board": ("SAFETY BOARD: hold ^3[{+activate}]^7 to read", (
        "DAYS WITHOUT AN INCIDENT: 0",
        "PREVIOUS RECORD: 0",
        "REMINDER: THE BREAKER IS NOT A LIGHT SWITCH.",
    )),
}

#: The named story vignettes and the scatter id each one goes out under.
VIGNETTES: dict[str, str] = {
    "party_table": "dense_break_party_table",
    "fridge_top": "dense_break_fridge_top",
    "kitchenette": "dense_break_kitchenette",
    "time_clock": "dense_break_time_clock",
    "safety_board": "dense_break_safety_board",
    "breaker_corner": "dense_break_breaker_corner",
    "nap_spot": "dense_break_nap_spot",
    "water": "dense_break_water",
    "bin": "dense_break_bin",
    "walls": "dense_break_walls",
    "floor": "dense_break_floor",
}

_TABLE = "p7_cai_work_table_metal_03_white"
_FRIDGE = "p7_cai_fridge_metal_plant"
_CABINET = "p7_zm_der_cabinet_lab_bottom"


def dress(ctx: RoomContext) -> None:
    """Fill the break room."""
    room = ctx.room
    b_in = room.interior
    bz = room.floor_z
    # The existing pieces (``_furnish_lived_in`` / ``_furnish_character``).
    table_x, table_y = b_in.mins.x + 68.0, b_in.centre.y          # -316, 550 (dmv.py table_at)
    table_top = _top_of(_TABLE, bz)
    fridge_x, fridge_y = b_in.maxs.x - 13.0, 540.0
    fridge_top = _top_of(_FRIDGE, bz)
    # 16: on the wall (the box, y -16.5..15.5, half a unit into it) so it stops at the
    # power switch's approach lane (y <= 652) instead of reaching 1 unit in,
    # which took the counter and all on it (zmforge.blueprint.lanes).
    counter_y = b_in.maxs.y - 16.0                                  # 668
    counter_top = _top_of(_CABINET, bz)
    bin_x, bin_y = b_in.maxs.x - 44.0, 604.0

    # ---- the party table: what still fits round the cake ----------------
    ctx.put([
        _on("p7_cleaning_paper_folded_wrapped", table_x, table_y + 37.0, table_top, 90.0),
        _on("p7_debris_trash_paper_plate_01", table_x, table_y - 36.0, table_top, 0.0),
    ], VIGNETTES["party_table"])

    # ---- on top of the fridge: nobody's turkey, nobody's melon ----------
    ctx.put([
        # A kit prop, so solid like the cake: the kit ships its collmap (Z21).
        _centred("zmf_prop_roast_turkey", fridge_x, fridge_y + 12.0,
                 _rest_on("zmf_prop_roast_turkey", fridge_top), 90.0, solid=True),
        _on("p7_food_fruit_watermelon", fridge_x, fridge_y - 12.0, fridge_top, 0.0),
    ], VIGNETTES["fridge_top"])

    # ---- the kitchenette counter ----------------------------------------
    ctx.put([
        # The radio, at the counter's west end.
        _on("p7_electrical_box_set2_box06", b_in.mins.x + 6.0, counter_y + 4.0,
            counter_top, 90.0),
        # A mug nobody washed.
        _on("p7_cup_coffee_mug", -327.0, counter_y + 8.0, counter_top, 300.0),
    ], VIGNETTES["kitchenette"])

    # ---- the time clock, by the door ------------------------------------
    clock_x = -180.0
    ctx.put([
        # A second clock, showing a different time from the room's.
        _mounted("p7_clock_metal_wall_01_base",
                 Point(clock_x, b_in.mins.y + 3.0, bz + 120.0), Facing.NORTH),
        # The time cards, dropped under it.
        _floor("p7_office_paper_sheet_09", clock_x - 10.0, b_in.mins.y + 14.0, bz, 20.0,
               solid=False),
        _floor("p7_office_paper_sheet_09", clock_x + 8.0, b_in.mins.y + 22.0, bz, 105.0,
               solid=False),
        _floor("p7_office_paper_sheet_03", clock_x - 2.0, b_in.mins.y + 36.0, bz, 250.0,
               solid=False),
    ], VIGNETTES["time_clock"])

    # ---- the safety board, standing against the west wall ---------------
    ctx.put([
        # Its face looks +y at yaw 0; turned 270 it looks east into the room.
        _floor("p7_zm_der_chalkboard_vintage", b_in.mins.x + 14.0, 458.0, bz, 270.0),
    ], VIGNETTES["safety_board"])

    # ---- the breaker corner: plates either side of the switch -----------
    ctx.put([
        _mounted("p7_zm_der_signage_hazard_03",
                 Point(-300.0, b_in.maxs.y - 2.0, bz + 104.0), Facing.SOUTH),
        _mounted("p7_zm_der_signage_hazard_03",
                 Point(-200.0, b_in.maxs.y - 2.0, bz + 104.0), Facing.SOUTH),
    ], VIGNETTES["breaker_corner"])

    # ---- the nap spot: a pillow on the floor ----------------------------
    ctx.put([
        _floor("p7_bed_pillow_barrack", b_in.mins.x + 26.0, 618.0, bz, 90.0, solid=False),
        _floor("p7_debris_newspaper_01", b_in.mins.x + 70.0, 622.0, bz, 30.0, solid=False),
    ], VIGNETTES["nap_spot"])

    # ---- spare water jugs by the cooler ---------------------------------
    ctx.put([
        _floor("p7_water_cooler_digital_bottle", b_in.maxs.x - 10.0, 436.0, bz, 0.0),
        _floor("p7_water_cooler_digital_bottle", b_in.maxs.x - 10.0, 452.0, bz, 40.0),
    ], VIGNETTES["water"])

    # ---- the bin, overflowing -------------------------------------------
    ctx.put([
        _floor(model, bin_x + dx, bin_y + dy, bz, yaw, solid=False)
        for model, dx, dy, yaw in (
            ("p7_cleaning_paper_ball_brown", -24.0, -8.0, 0.0),
            ("p7_cleaning_paper_ball_brown", -20.0, 14.0, 80.0),
            ("p7_cleaning_paper_ball_brown", 4.0, -26.0, 160.0),
            ("p7_debris_trash_drink_carrier_01", -30.0, 30.0, 20.0),
            ("p7_debris_trash_cup_coffee_02", -40.0, -20.0, 60.0),
        )
    ], VIGNETTES["bin"])

    # ---- wall dressing ---------------------------------------------------
    ctx.put([
        # The CPR chart on the east wall, above the jugs.
        _mounted("p7_zm_der2_poster_anatomy_05",
                 Point(b_in.maxs.x - 0.5, 450.0, bz + 96.0), Facing.WEST),
        _mounted("p7_zm_der_signage_no_smoking",
                 Point(-305.0, b_in.mins.y + 2.0, bz + 80.0), Facing.NORTH),
        _mounted("p7_picture_frame_modern_01",
                 Point(-160.0, b_in.maxs.y - 2.0, bz + 100.0), Facing.SOUTH),
        # The blind over the nap spot, drawn.
        _mounted("p7_blinds_01_closed",
                 Point(b_in.mins.x + 2.0, 620.0, bz + 100.0), Facing.EAST),
    ], VIGNETTES["walls"])

    # ---- the floor: the party, afterwards -------------------------------
    ctx.put([
        _floor(model, x, y, bz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_trash_cup_coffee_02", -260.0, 500.0, 20.0),
            ("p7_debris_trash_cup_coffee_02", -330.0, 470.0, 140.0),
            ("p7_debris_trash_drink_carrier_01", -230.0, 540.0, 35.0),
            ("p7_debris_trash_cup_red_02", -250.0, 610.0, 0.0),
            ("p7_debris_trash_paper_plate_01", -330.0, 600.0, 0.0),
            ("p7_debris_newspaper_03", -200.0, 520.0, 120.0),
            ("p7_cleaning_paper_folded_wrapped", -270.0, 590.0, 45.0),
            ("p7_debris_trash_paper_08", -180.0, 480.0, 200.0),
            ("p7_debris_trash_paper_02", -225.0, 470.0, 70.0),
        )
    ], VIGNETTES["floor"])

    _break_dense2(ctx)


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """Where each of :data:`NOTICES` stands, on reachable floor, 80+ from
    every other use trigger (the switch, Deadshot through the wall, the
    fridge note)."""
    bz = ctx.room.floor_z
    return [
        ("break_time_clock", Point(-170.0, 458.0, bz)),
        ("break_radio", Point(-340.0, 620.0, bz)),
        ("break_safety_board", Point(-335.0, 455.0, bz)),
    ]


# ==========================================================================
# Dense pass 2: far more props, so the room reads as a DMV
# ==========================================================================
# A second counter with the sink, the supply boxes by the fridge, the
# party's leftovers on every surface and all over the floor, more notices.
# Solids only against a wall; every piece on the floor is flat.  Nothing
# within 48 of the breaker (test_the_power_switch_stays_clear).
from .records import _put_clear, _trail  # noqa: E402  (shared dense-pass helpers)

VIGNETTES.update({
    "sink_counter": "dense_break_sink_counter",
    "counter_gaps": "dense_break_counter_gaps",
    "supply_boxes": "dense_break_supply_boxes",
    "table_cups": "dense_break_table_cups",
    "left_behind": "dense_break_left_behind",
    "notices": "dense_break_notices",
    "leftovers": "dense_break_leftovers",
})

#: Floor litter for the break room: the party, afterwards.
_PARTY = ("p7_debris_trash_cup_coffee_02", "p7_debris_trash_paper_plate_01",
          "p7_debris_trash_cup_red_02", "p7_cleaning_paper_ball_brown",
          "p7_debris_trash_food_box_01", "p7_debris_trash_paper_03",
          "p7_debris_trash_drink_carrier_01", "p7_cleaning_paper_folded_wrapped",
          "p7_debris_trash_paper_08", "p7_office_paper_sheet_03",
          "p7_debris_trash_paper_plate_01", "p7_debris_trash_cup_coffee_02")


def _break_dense2(ctx: RoomContext) -> None:
    """The second dense pass: the break room, lived in."""
    b_in, bz = ctx.room.interior, ctx.room.floor_z
    x0, x1, y0, y1 = b_in.mins.x, b_in.maxs.x, b_in.mins.y, b_in.maxs.y
    counter_top = _top_of(_CABINET, bz)
    # The breaker, the riser, the door and the three notices stay walkable.
    keep_out = ((-250.0, 660.0, 50.0), (-250.0, 456.0, 30.0), (-250.0, 430.0, 40.0),
                (-170.0, 458.0, 22.0), (-340.0, 620.0, 22.0), (-335.0, 455.0, 22.0))

    # ---- the sink counter, east of the breaker ---------------------------
    # 80 from the switch centre to this cabinet's, doors looking south.
    sink_x, sink_y = x1 - 54.0, y1 - 16.0                          # -170, 668 (counter_y)
    mug = "p7_cup_coffee_mug"
    ctx.put([
        _floor(_CABINET, sink_x, sink_y, bz, 0.0),
        _centred("p7_sink_kitchen_stainless_modern_01_clean", sink_x - 2.0, y1 - 24.0,
                 _rest_on("p7_sink_kitchen_stainless_modern_01_clean", counter_top), 0.0,
                 scale=0.85),
        _on("p7_faucet_kitchen_stainless_modern_01_clean", sink_x - 2.0, y1 - 6.5,
            counter_top, 0.0),
        _on("p7_bottle_plastic_soap_orange_clean", sink_x + 24.0, y1 - 8.0, counter_top, 0.0),
        # Mugs upturned to dry, west of the sink (and 48 clear of the switch).
        _on(mug, sink_x - 27.0, y1 - 28.0, counter_top, 20.0),
        _on(mug, sink_x - 28.0, y1 - 18.0, counter_top, 100.0),
        _on(mug, sink_x - 26.0, y1 - 8.0, counter_top, 250.0),
        # The second coffee maker, the one that works, and the pan from lunch.
        _on("p7_coffee_maker_digital", sink_x + 44.0, y1 - 9.0, counter_top, 0.0),
        _on("p7_pan_metal_sauce", sink_x + 39.0, y1 - 25.0, counter_top, 200.0),
        _on("p7_pan_metal_lid", sink_x + 23.0, y1 - 26.0, counter_top, 0.0),
        _on("p7_debris_trash_paper_plate_01", sink_x + 23.0, y1 - 26.0,
            _top_of("p7_pan_metal_lid", counter_top), 0.0),
        _on("p7_debris_trash_food_box_01", sink_x + 24.0, y1 - 16.0, counter_top, 0.0),
    ], "dense_break_sink_counter")

    # ---- what still fits on the old counter (west of the breaker) --------
    ctx.put([
        _on("p7_debris_trash_food_box_01", -351.0, y1 - 8.0, counter_top, 10.0),
        _on("p7_bottle_plastic_soap_orange_clean", -318.0, y1 - 7.0, counter_top, 0.0),
        _on("p7_debris_trash_paper_plate_01", -305.0, y1 - 7.0, counter_top, 0.0),
    ], "dense_break_counter_gaps")

    # ---- supply boxes against the east wall, between the jugs and fridge -
    box = "p7_container_cardboard_box_01"
    bx, by = x1 - 14.5, 489.0
    box_top = _top_of(box, bz)
    two_top = _top_of(box, box_top)
    ctx.put([
        _floor(box, bx, by, bz, 90.0),
        _centred(box, bx, by, _rest_on(box, box_top), 87.0, solid=True),
        _on("p7_debris_trash_cup_coffee_02", bx - 6.0, by - 10.0, two_top, 0.0),
        _on("p7_debris_trash_cup_coffee_02", bx + 2.0, by - 12.0, two_top, 60.0),
        _on("p7_cleaning_paper_folded_wrapped", bx - 2.0, by + 6.0, two_top, 80.0),
        _on("p7_debris_trash_food_box_01", bx + 3.0, by + 15.0, two_top, 20.0),
    ], "dense_break_supply_boxes")

    # ---- the party table's east edge, and the fridge top -----------------
    table_top = _top_of(_TABLE, bz)
    ctx.put([
        _on("p7_debris_trash_cup_coffee_02", -307.0, 528.0, table_top, 0.0),  # table at -316 (dmv.py)
        _on("p7_debris_trash_cup_red_02", -307.0, 566.0, table_top, 0.0),
        _on("p7_debris_trash_food_box_01", x1 - 13.0, 538.5, _top_of(_FRIDGE, bz), 0.0),
    ], "dense_break_table_cups")

    # ---- left behind: a suitcase by the board, a bag --------------------
    ctx.put([
        _floor("p7_luggage_hardshell_handle_down_white", x0 + 9.0, 508.0, bz, 90.0),
        _floor("p7_bag_plastic_soil", -200.0, 474.0, bz, 30.0, solid=False),
    ], "dense_break_left_behind")

    # ---- notices: exit, a calendar, a hazard plate, a frame --------------
    ctx.put([
        _mounted("p7_cai_signage_plastic_exit", Point(-250.0, y0 + 1.3, bz + 126.0),
                 Facing.NORTH),
        _mounted("p7_picture_frame_modern_01", Point(-340.0, y1 - 1.0, bz + 96.0),
                 Facing.SOUTH),
        _mounted("p7_picture_frame_modern_01", Point(x0 + 1.0, 550.0, bz + 130.0), Facing.EAST),
        _mounted("p7_zm_der_signage_hazard_04", Point(x0 + 1.0, 440.0, bz + 100.0),
                 Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(x1 - 1.0, 489.0, bz + 96.0),
                 Facing.WEST),
        _mounted("p7_signage_caution_warning_01", Point(x1 - 1.0, 660.0, bz + 96.0),
                 Facing.WEST),
    ], "dense_break_notices")

    # ---- the leftovers, over the whole floor -----------------------------
    _put_clear(ctx, _trail(x0 + 20.0, y0 + 20.0, x1 - 20.0, y1 - 40.0, 64, 7, bz, _PARTY)
               + _trail(x0 + 30.0, y0 + 30.0, x1 - 30.0, y1 - 50.0, 48, 13, bz, _PARTY),
               "dense_break_leftovers", keep_out=keep_out)
