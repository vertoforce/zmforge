"""zm_dmv dense pass: the waiting room (key ``waiting``).  See the package docstring.

The room is already full of solids (ten chairs in the block, two wall rows,
two lines of stanchion posts, Quick Revive, the cooler), so almost everything
here is non-solid: what people brought for a long wait, left on the seats and
between the rows, tickets dropped along the stanchion lane, a wall of clocks
that do not agree, a magazine crate, a TV on the north wall, and a camp on
the south row where somebody slept waiting for their number.

Vignettes (ids ``dense_waiting_<name>``):

``seats``      what people brought, left on the seats
``between``    what they dropped between the two rows of the block
``camp``       the saved seat: a pillow, a blanket, a lamp, breakfast
``lane``       tickets and cups dropped along the stanchion lane
``clocks``     three more clocks on the west wall, none agreeing
``magazines``  the magazine crate on the west wall, reading on top
``tv``         the waiting-room TV on the north wall
``walls``      the wash-hands sign by the cooler, a suitcase by the north row
"""
from __future__ import annotations

from ...dressing import on_room_wall
from ._kit import (
    MODEL_BOX,
    Facing,
    Point,
    RoomContext,
    WAITING_SEAT_TOP,
    _floor,
    _mount_face,
    _mounted,
    _on,
    _top_of,
)

#: The waiting chair's seat centre sits this far forward of its origin.
_SEAT_FORWARD = 2.5

CHAIR = "p7_chair_waiting_room_01_blue"
CLOCK = "p7_clock_metal_wall_01_base"
TV = "p7_consumer_grade_monitor_wall_medium"
#: The wall TV hangs by its drawn box (``MODEL_BOX``, root bone taken out): its back is on its origin and its 3-unit body lies along its
#: own -y, which is the way the screen looks.  The catalogue box put the body
#: 36 to 39 units along +y, and hanging it by that buried the TV in the north
#: wall with its screen to the brick.  The origin goes this far off the face.
_TV_GAP = 0.5

NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "waiting_tv": (
        "TV: hold ^3[{+activate}]^7 to change the channel",
        (
            "DMV Channel: How To Wait, part 1 of 40.",
            "DMV Channel: How To Wait, part 1 of 40.",
            "The remote is at the service window.",
        ),
    ),
    "waiting_clocks": (
        "THE CLOCKS: hold ^3[{+activate}]^7 to check the time",
        (
            "9:02.",
            "9:02.",
            "It has been 9:02 for some time.",
        ),
    ),
    "waiting_saved_seat": (
        "SAVED SEAT: hold ^3[{+activate}]^7 to read the note",
        (
            "BACK IN 5 MIN. DO NOT TAKE.",
            "STILL BACK IN 5 MIN.",
            "IF YOU ARE READING THIS I LOST MY PLACE.",
        ),
    ),
}


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """In front of the TV, by the west-wall clocks, and in front of the camp
    on the south row (clear of Quick Revive, the suggestion box and 846)."""
    w_in, wz = ctx.room.interior, ctx.room.floor_z
    return [
        ("waiting_tv", Point(w_in.mins.x + 104.0, w_in.maxs.y - 94.0, wz)),
        ("waiting_clocks", Point(w_in.mins.x + 54.0, 140.0, wz)),
        ("waiting_saved_seat", Point(w_in.mins.x + 144.0, w_in.mins.y + 84.0, wz)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the waiting room."""
    w_in, wz = ctx.room.interior, ctx.room.floor_z
    seat = wz + WAITING_SEAT_TOP
    north_y = w_in.maxs.y - 16.0 - _SEAT_FORWARD     # north row faces south
    south_y = w_in.mins.y + 16.0 + _SEAT_FORWARD     # south row faces north

    # ---- seats: what people brought for a long wait ---------------------
    # The block faces east, so a seat is 2.5 east of its chair's origin.
    # (-866, 88) is customer 846's and stays his.
    ctx.put([
        _on("p7_book_vintage_open_01", -930.0 + _SEAT_FORWARD, -88.0, seat, 80.0),
        _on("p7_cup_coffee_mug", -930.0 + _SEAT_FORWARD, 0.0, seat, 35.0),
        _on("p7_office_paper_folder_blue", -866.0 + _SEAT_FORWARD, -44.0, seat, 20.0),
        _on("p7_food_fruit_banana_bunch", -1026.0, north_y, seat, 140.0),
        _on("p7_office_paper_folder_pink", -972.0, south_y, seat, 190.0),
    ], "dense_waiting_seats")

    # ---- between the two rows of the block ------------------------------
    gap_x = -898.0
    ctx.put([
        _floor("p7_debris_trash_drink_carrier_01", gap_x, -62.0, wz, 30.0, solid=False),
        _floor("p7_debris_trash_cup_coffee_02", gap_x + 3.0, 22.0, wz, 200.0, solid=False),
    ], "dense_waiting_between")

    # ---- the camp on the south row: the saved seat ----------------------
    ctx.put([
        _on("p7_bed_pillow_barrack", -1060.0, south_y, seat, 0.0),
        _on("p7_food_fruit_banana_bunch", -1016.0, south_y, seat, 60.0),
        _floor("p7_bed_sheet_barrack_02", -1036.0, w_in.mins.y + 58.0, wz, 8.0, solid=False),
        _floor("p7_zm_der2_light_hurricane_lamp", -994.0, w_in.mins.y + 12.0, wz, 30.0,
               solid=False),
        _floor("p7_bottle_glass_wine_01", -990.0, w_in.mins.y + 34.0, wz, 0.0, solid=False),
    ], "dense_waiting_camp")

    # ---- the stanchion lane: dropped tickets and cups -------------------
    lane_y = -202.0
    ctx.put([
        _floor("p7_office_paper_sheet_12", -1032.0, lane_y + 4.0, wz, 25.0, solid=False),
        _floor("p7_office_paper_sheet_12", -868.0, lane_y + 2.0, wz, 300.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", -824.0, lane_y + 8.0, wz, 0.0, solid=False),
    ], "dense_waiting_lane")

    # ---- the wall of clocks, carried on round to the west wall ----------
    west = w_in.mins.x + 3.0
    ctx.put([
        _mounted(CLOCK, Point(west, -150.0, wz + 128.0), Facing.EAST),
        _mounted(CLOCK, Point(west, 140.0, wz + 108.0), Facing.EAST),
        _mounted(CLOCK, Point(west, 370.0, wz + 146.0), Facing.EAST),
    ], "dense_waiting_clocks")

    # ---- the magazine crate on the west wall ----------------------------
    crate = "p7_crate_wood_01_short"
    cx, cy = w_in.mins.x + 16.5, 320.0
    top = _top_of(crate, wz)
    ctx.put([
        _floor(crate, cx, cy, wz, 0.0),
        _on("p7_book_office_med_brown", cx - 4.0, cy - 8.0, top, 0.0),
        _on("p7_book_office_sml_beige", cx - 4.0, cy - 4.0, top, 4.0),
        _on("p7_office_paper_sheet_02", cx + 5.0, cy + 6.0, top, 70.0),
    ], "dense_waiting_magazines")

    # ---- the TV on the north wall, over the north row -------------------
    ctx.put([
        (TV, Point(-1080.0, w_in.maxs.y - _TV_GAP - MODEL_BOX[TV][1][1], wz + 170.0),
         (Facing.SOUTH.world_yaw - _mount_face(TV)) % 360.0, 1.0, False),
    ], "dense_waiting_tv")

    # ---- walls and the north row's end ----------------------------------
    ctx.put([
        _mounted("p7_zm_der_signage_wash_hands", Point(west, -292.0, wz + 96.0), Facing.EAST),
        _floor("p7_luggage_hardshell_handle_down_white", -1152.0, w_in.maxs.y - 10.0, wz, 0.0),
    ], "dense_waiting_walls")

    dress_more(ctx)


# ==========================================================================
# Second density pass: more props, and more of them reading as a DMV.
# The helpers below are private to this module.
# ==========================================================================

from ._kit import _seated


_D2_LITTER = (
    "p7_office_paper_sheet_12", "p7_debris_trash_cup_coffee_02", "p7_office_paper_sheet_01",
    "p7_debris_trash_paper_02", "p7_debris_trash_cup_red_02", "p7_office_paper_sheet_10",
    "p7_debris_trash_food_box_01", "p7_box_copy_paper_sheet", "p7_debris_trash_paper_08",
    "p7_office_paper_sheet_03", "p7_cleaning_paper_ball_brown", "p7_debris_trash_paper_04",
    "p7_office_paper_sheet_08", "p7_debris_trash_paper_plate_01", "p7_cleaning_paper_towel",
    "p7_debris_trash_paper_10", "p7_office_paper_sheet_09", "p7_debris_newspaper_01",
)

#: What a long wait leaves on a seat, dealt round the rows in turn.
_D2_ON_SEAT = (
    "p7_office_paper_folder_blue", "p7_cup_coffee_mug", "p7_book_vintage_open_04",
    "p7_bottle_plastic_16oz_water", "p7_office_paper_sheet_01", "p7_debris_trash_food_box_01",
    "p7_office_paper_folder_pink", "p7_book_vintage_02", "p7_debris_trash_cup_coffee_02",
    "p7_office_paper_stack_sml", "p7_cleaning_paper_folded_wrapped", "p7_book_office_binder_open",
)

_D2_FORWARD = {Facing.EAST: (1.0, 0.0), Facing.WEST: (-1.0, 0.0),
               Facing.NORTH: (0.0, 1.0), Facing.SOUTH: (0.0, -1.0)}


def dress_more(ctx: RoomContext) -> None:
    """The second density pass: more rows of joined chairs (the room held
    three hundred on a Monday), what was left on every other seat, bags and
    coats, the walls papered with the rules, and the floor after it."""
    room = ctx.room
    w_in, wz = room.interior, room.floor_z
    seat = wz + WAITING_SEAT_TOP
    west, east = w_in.mins.x, w_in.maxs.x
    south, north = w_in.mins.y, w_in.maxs.y

    # ---- more chairs: (origin x, origin y, facing) -----------------------
    # A second block north of the first, same two columns, joined seats at
    # a 24 pitch; a row along the west wall between the door's band and
    # the crate; a short row on the east wall facing into the room.
    chairs: list[tuple[float, float, Facing]] = []
    chairs += [(x, y, Facing.EAST) for x in (-930.0, -866.0)
               for y in (196.0, 220.0, 244.0, 268.0, 292.0)]
    chairs += [(west + 13.0, y, Facing.EAST) for y in (104.0, 128.0, 152.0, 176.0, 200.0)]
    chairs += [(east - 13.0, y, Facing.WEST) for y in (288.0, 312.0, 336.0)]
    ctx.put([_seated(CHAIR, Point(x, y, wz), f) for x, y, f in chairs],
            "dense_waiting_more_chairs")

    # ---- on the seats: every other one, new rows and old ----------------
    old = [(-930.0, y, Facing.EAST) for y in (-44.0, 44.0)] + \
          [(-866.0, y, Facing.EAST) for y in (-88.0, 0.0)] + \
          [(x, north - 15.0, Facing.SOUTH) for x in (-982.0, -938.0)] + \
          [(-1016.0, south + 15.0, Facing.NORTH)]
    loaded = [c for i, c in enumerate(chairs) if i % 5 != 3] + old
    items = []
    for i, (x, y, f) in enumerate(loaded):
        fx, fy = _D2_FORWARD[f]
        model = _D2_ON_SEAT[i % len(_D2_ON_SEAT)]
        items.append(_on(model, x + fx * 3.0, y + fy * 3.0, seat, float((i * 47) % 360)))
    ctx.put(items, "dense_waiting_seat_clutter")

    # ---- bags and coats: set down by a seat and never picked up ----------
    ctx.put([
        _floor("p7_luggage_cloth_a_lg_green", -890.0, 330.0, wz, 80.0, solid=False),
        _floor("p7_luggage_hardshell_handle_down_white", -960.0, 176.0, wz, 15.0,
               solid=False),
        _floor("p7_debris_clothing_piles_01", west + 50.0, 150.0, wz, 30.0, solid=False),
        _floor("p7_debris_clothing_tshirts_02", -898.0, 250.0, wz, 120.0, solid=False),
        _floor("p7_debris_clothing_dress_01", east - 50.0, 300.0, wz, 200.0, solid=False),
        _floor("p7_clothes_womens_crumpled_01_shirt", -900.0, -30.0, wz, 10.0, solid=False),
        _floor("p7_bag_plastic_soil", -960.0, 60.0, wz, 45.0, solid=False),
        _floor("p7_luggage_cloth_a_lg_green", west + 60.0, -340.0, wz, 100.0, solid=False),
    ], "dense_waiting_bags")

    # ---- walls: rules, fees, hours, a notice board, a frame or two -------
    poster, frame = "p7_picture_frame_modern_01", "p7_picture_frame_modern_01"
    ctx.put([
        on_room_wall(poster, room, "w", -70.0, 80.0),
        on_room_wall(poster, room, "w", 100.0, 70.0),
        on_room_wall(poster, room, "w", 200.0, 70.0),
        on_room_wall(poster, room, "w", 420.0, 80.0),
        on_room_wall(frame, room, "w", -430.0, 76.0),
        on_room_wall(poster, room, "s", -940.0, 88.0),
        on_room_wall("p7_zm_der_signage_no_smoking", room, "s", -1060.0, 100.0),
        on_room_wall(poster, room, "s", -770.0, 80.0),
        on_room_wall(poster, room, "n", -1150.0, 90.0),
        on_room_wall(poster, room, "n", -920.0, 80.0),
        on_room_wall(frame, room, "e", -240.0, 70.0),
        on_room_wall(poster, room, "e", -400.0, 80.0),
        on_room_wall(poster, room, "e", 240.0, 70.0),
        on_room_wall(frame, room, "e", 420.0, 76.0),
        on_room_wall("p7_zm_der_signage_steps", room, "e", -110.0, 96.0),
    ], "dense_waiting_posters")

    # ---- a plant in the south-east corner, and the cooler's spill -------
    ctx.put([
        _floor("p7_3arc_lobby_plant", east - 24.0, -400.0, wz, 0.0),
        _floor("p7_foliage_plant_aloe_small", -800.0, north - 26.0, wz, 30.0, solid=False),
    ], "dense_waiting_plants")
    ctx.put([
        _floor(m, x, y, wz, yaw, solid=False)
        for m, x, y, yaw in (
            ("p7_debris_trash_cup_red_02", west + 30.0, -312.0, 0.0),
            ("p7_debris_trash_cup_red_02", west + 44.0, -300.0, 60.0),
            ("p7_debris_trash_cup_red_02", west + 36.0, -352.0, 120.0),
            ("p7_cleaning_paper_towel", west + 50.0, -326.0, 20.0),
            ("p7_cleaning_paper_brown", west + 64.0, -344.0, 80.0),
        )
    ], "dense_waiting_cooler")

    # ---- the floor --------------------------------------------------------
    revive = (-1170.0, south, -1070.0, south + 110.0)
    dress_more_reading(ctx)
    # In heaps, not confetti: the bins
    # overflowing, the corners drifted, forms dropped by the seats and
    # somebody's things left behind.  Same 90 pieces.
    from ._kit import litter_heaps, room_heaps
    rect = (west + 8.0, south + 8.0, east - 8.0, north - 8.0)
    ctx.put(litter_heaps(ctx, rect, 90, 7202, room_heaps(ctx, rect, 7202), keep_out=[revive]),
            "dense_waiting_litter")


def dress_more_reading(ctx: RoomContext) -> None:
    """The reading on both west-wall crates topped up, and the one who got
    bitten in the line: what is left of it by the stanchions."""
    wz = ctx.room.floor_z
    top = _top_of("p7_crate_wood_01_short", wz)
    ctx.put([
        _on("p7_book_vintage_01", -1160.0, 311.0, top, 0.0),
        _on("p7_book_vintage_open_01", -1174.0, 244.0, top, 10.0),
        _on("p7_cup_coffee_mug", -1158.0, 258.0, top, 80.0),
        _on("p7_book_vintage_02", -1160.0, 242.0, top, 90.0),
    ], "dense_waiting_reading")
    gx, gy = -990.0, -290.0
    ctx.put([
        _floor(model, gx + dx, gy + dy, wz, yaw, solid=False)
        for model, dx, dy, yaw in (
            ("p7_gib_chunk_flesh_02", 0.0, 0.0, 0.0), ("p7_gib_chunk_meat_01", 12.0, -8.0, 60.0),
            ("p7_gib_chunk_bone_03", -10.0, 6.0, 120.0), ("p7_gib_chunk_meat_03", 16.0, 12.0, 200.0),
            ("p7_gib_chunk_bone_01", -14.0, -12.0, 30.0),
            ("p7_debris_clothing_tshirts_01", 36.0, -20.0, 70.0),
        )
    ], "dense_waiting_bitten")
