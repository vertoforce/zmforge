"""zm_dmv dense pass: the photo room (key ``photo``).  See the package docstring.

The camera kept flashing after everyone left, so the floor is covered in
rejected licence photos of nobody.  The booth's pad (the south-centre square
the ``short_hop_teleporter`` fires on, radius 40, and the arrival square 56
north of it) and the riser behind it stay empty; everything here is packed
into the walls and the corners.

Vignettes (ids ``dense_photo_<name>``):

``cart``       the photographer's table on the east wall: the camera, mug,
               paperwork
``lollipops``  the complimentary lollipop stand in the south-west corner
``samples``    the SAMPLE PHOTOS board on the west wall
``exit``       an EXIT sign on the south wall, where there is no door
``rejects``    the reject pile in the north-east corner, grown
``boxes``      a second box of blank photo stock on the first
``floor``      cups and paper along the base of every wall
``walls``      signage and two more sample frames
"""
from __future__ import annotations

from ...dressing import on_wall
from ._kit import Facing, Point, RoomContext, _centred, _floor, _mounted, _on, _top_of

NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "photo_lollipop": (
        "COMPLIMENTARY LOLLIPOP: hold ^3[{+activate}]^7 to take one",
        (
            "Lollipops are for customers who did not smile.",
            "You smiled. No lollipop.",
            "Please present proof of age at the service window. Take a number.",
        ),
    ),
    "photo_samples": (
        "SAMPLE PHOTOS: hold ^3[{+activate}]^7 to compare",
        (
            "Acceptable: neutral expression, eyes open.",
            "Unacceptable: also neutral expression, eyes open.",
            "Both photos are of Gary.",
        ),
    ),
    "photo_exit": (
        "EXIT: hold ^3[{+activate}]^7 to exit",
        (
            "This is not an exit.",
            "You are facing the wrong way.",
            "So is your photo.",
        ),
    ),
}


def _pad(ctx: RoomContext) -> Point:
    """The booth's pad, where dmv.py puts the teleporter."""
    p_in = ctx.room.interior
    return Point(p_in.centre.x, p_in.mins.y + 72.0, ctx.room.floor_z)


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """The lollipop stand (south-west), the samples board (west, in front of
    the chairs) and the false exit (south wall, east of the pad's radius)."""
    p_in, pz = ctx.room.interior, ctx.room.floor_z
    return [
        ("photo_lollipop", Point(p_in.mins.x + 54.0, p_in.mins.y + 49.0, pz)),
        ("photo_samples", Point(p_in.mins.x + 104.0, p_in.maxs.y - 84.0, pz)),
        ("photo_exit", Point(p_in.maxs.x - 84.0, p_in.mins.y + 44.0, pz)),
    ]


CAMERA = "p7_zm_der_light_spot_housing"
CAMERA_SCALE = 0.55


def camera_point(room) -> tuple[float, float, float]:
    """The middle of the camera on the photographer's table, in world units:
    where :func:`dress` stands it and where the Photo ID step's knife target
    is, so the two cannot drift apart."""
    p_in, pz = room.interior, room.floor_z
    top = _top_of("p7_cai_work_table_metal_03_white", pz)
    return (p_in.maxs.x - 12.0, -662.0, top + 7.0)


def dress(ctx: RoomContext) -> None:
    """Fill the photo room."""
    p_in, pz = ctx.room.interior, ctx.room.floor_z

    # ---- the photographer's table on the east wall ----------------------
    table = "p7_cai_work_table_metal_03_white"
    tx, ty = p_in.maxs.x - 12.0, -650.0
    t_top = _top_of(table, pz)
    ctx.put([
        _floor(table, tx, ty, pz, 0.0),
        # The camera: a spot housing is the one lens-on-a-body in the
        # measured palette, and at 0.55 it is a camera-sized can on the
        # table, lens (its +x end) turned west at the pad.  This is what the
        # Photo ID step knifes (it used to be a
        # keyboard's display, and the room had no camera at all).
        # Its box straddles its origin in Z (the checks read that as a
        # fitting on a plane), so the origin sits on the table top.
        _centred(CAMERA, *camera_point(ctx.room), 180.0, scale=CAMERA_SCALE),
        _on("p7_cup_coffee_mug", tx + 3.0, ty + 30.0, t_top, 200.0),
        _on("p7_office_paper_stack_sml", tx, ty - 30.0, t_top, 90.0),
        _on("p7_office_paper_folder_blue", tx - 1.0, ty + 16.0, t_top, 95.0),
    ], "dense_photo_cart")

    # ---- the lollipop stand, south-west corner --------------------------
    crate = "p7_crate_wood_01_short"
    lx, ly = p_in.mins.x + 17.0, p_in.mins.y + 17.0
    l_top = _top_of(crate, pz)
    ctx.put([
        _floor(crate, lx, ly, pz, 0.0),
        _on("p7_office_paper_sheet_01", lx + 2.0, ly, l_top, 10.0),
    ] + [
        # zmf_ props carry their own collision (Z21: a no_collmap one would
        # be a solid model the player walks through), so these stay solid.
        _floor("zmf_prop_lollipop", lx + dx, ly + dy, l_top, yaw)
        for dx, dy, yaw in ((-7.0, -6.0, 0.0), (-3.0, 6.0, 40.0), (7.0, 2.0, 100.0))
    ], "dense_photo_lollipops")

    # ---- the samples board on the west wall -----------------------------
    west = p_in.mins.x + 3.0
    ctx.put([
        _mounted("p7_zm_der2_bulletin_board", Point(west, -592.0, pz + 96.0), Facing.EAST),
    ], "dense_photo_samples")

    # ---- an EXIT sign on the south wall, over no door --------------------
    ctx.put([
        _mounted("p7_signage_caution_exit", Point(p_in.maxs.x - 84.0, p_in.mins.y + 3.0,
                                                  pz + 118.0), Facing.NORTH),
    ], "dense_photo_exit")

    # ---- the reject pile, north-east corner, grown ----------------------
    ex, ny = p_in.maxs.x, p_in.maxs.y
    ctx.put([
        _floor(model, ex - dx, ny - dy, pz, yaw, solid=False)
        for model, dx, dy, yaw in (
            ("p7_office_paper_sheet_02", 44.0, 52.0, 200.0),
            ("p7_office_paper_sheet_12", 68.0, 48.0, 145.0),
            ("p7_office_paper_sheet_03", 88.0, 40.0, 30.0),
            ("p7_office_paper_sheet_08", 58.0, 90.0, 260.0),
            ("p7_office_paper_sheet_12", 84.0, 84.0, 15.0),
            ("p7_office_paper_sheet_01", 102.0, 60.0, 300.0),
            ("p7_cleaning_paper_ball_brown", 30.0, 64.0, 0.0),
            ("p7_cleaning_paper_ball_brown", 94.0, 26.0, 120.0),
        )
    ], "dense_photo_rejects")

    # ---- a second box of photo stock on the first (north-west) ----------
    box = "p7_container_cardboard_box_01"
    bx, by = p_in.mins.x + 22.0, p_in.maxs.y - 24.0
    ctx.put([
        _on(box, bx, by, _top_of(box, pz), 95.0),
        _on("p7_office_paper_stack_sml", bx, by, _top_of(box, _top_of(box, pz)), 10.0),
    ], "dense_photo_boxes")

    # ---- cups and paper along the base of the walls ---------------------
    ctx.put([
        _floor(model, x, y, pz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_trash_cup_coffee_02", p_in.mins.x + 10.0, -700.0, 40.0),
            ("p7_debris_trash_cup_coffee_02", p_in.maxs.x - 30.0, -706.0, 250.0),
            ("p7_debris_trash_cup_coffee_02", -905.0, p_in.maxs.y - 40.0, 180.0),
            ("p7_debris_newspaper_05", -940.0, -690.0, 20.0),
            ("p7_debris_trash_paper_03", p_in.mins.x + 10.0, -670.0, 60.0),
            ("p7_debris_trash_cup_red_02", p_in.mins.x + 44.0, p_in.mins.y + 12.0, 0.0),
            ("p7_debris_trash_paper_04", -920.0, p_in.mins.y + 8.0, 10.0),
            ("p7_debris_trash_paper_05", p_in.maxs.x - 8.0, -596.0, 200.0),
            ("p7_debris_trash_paper_09", p_in.maxs.x - 60.0, p_in.mins.y + 8.0, 90.0),
            ("p7_debris_trash_paper_10", -770.0, p_in.maxs.y - 8.0, 330.0),
            ("p7_book_office_binder_open", -892.0, -655.0, 70.0),
        )
    ], "dense_photo_floor")

    # ---- signage and two more sample frames -----------------------------
    east = p_in.maxs.x - 3.0
    ctx.put([
        _mounted("p7_zm_der_signage_wash_hands", Point(east, -690.0, pz + 100.0), Facing.WEST),
        _mounted("p7_zm_der_signage_employees_only", Point(east, -766.0, pz + 104.0),
                 Facing.WEST),
        _mounted("p7_picture_frame_modern_01", Point(-950.0, p_in.mins.y + 2.0, pz + 110.0),
                 Facing.NORTH),
        _mounted("p7_picture_frame_modern_01", Point(-910.0, p_in.mins.y + 2.0, pz + 110.0),
                 Facing.NORTH),
    ], "dense_photo_walls")
    _dress_desk(ctx)


# ==========================================================================
# The DMV photo-desk pass (the room needed far more props to read as
# a DMV).  Nothing here goes near the camera, the pad, the arrival or the
# riser: the counter is on the west wall, the stock on the east wall either
# side of the photographer's table, the backdrop hangs over head height, and
# the litter keeps out of all three circles.  Three solids, all against a
# wall: the counter and two cartons of stock.
#
# Vignettes (ids ``dense_photo_<name>``):
#
# ``counter``      the licence counter on the west wall: a monitor, the
#                  terminal, a card printer, a card reader, blank card stock
# ``clerk``        the clerk's stool, pushed back from it
# ``backdrop``     the pull-down backdrop behind the pad
# ``sample_wall``  sample photos and the rules for them, round the walls
# ``stock``        two cartons of photo stock on the east wall
# ``cards``        rejected licence cards on every free bit of floor
# ``debris``       the boards and the mess of the outbreak
# ``reject_stacks`` rejected cards squared into stacks by the north-east pile
# ==========================================================================
import math as _math  # noqa: E402
import random as _random  # noqa: E402

from ._kit import _seated  # noqa: E402


_CARDS = (
    "p7_office_paper_sheet_10", "p7_office_paper_sheet_12", "p7_box_copy_paper_sheet",
    "p7_office_paper_sheet_10", "p7_cleaning_paper_ball_brown", "p7_office_paper_sheet_12",
    "p7_debris_trash_cup_coffee_02", "p7_office_paper_sheet_09", "p7_box_copy_paper_sheet",
    "p7_debris_trash_paper_04", "p7_office_paper_sheet_10", "p7_cleaning_paper_towel",
    "p7_office_paper_sheet_12", "p7_debris_trash_food_box_01", "p7_office_paper_sheet_03",
)


def _dress_desk(ctx: RoomContext) -> None:
    """The DMV photo-desk pass (see the block comment above)."""
    p_in, pz = ctx.room.interior, ctx.room.floor_z
    x0, x1, y0, y1 = p_in.mins.x, p_in.maxs.x, p_in.mins.y, p_in.maxs.y

    # ---- the licence counter on the west wall ------------------------------
    counter = "p7_zm_der_cabinet_lab_bottom"
    cx, cy = x0 + 16.5, -696.0
    top = _top_of(counter, pz)
    ctx.put([
        _floor(counter, cx, cy, pz, 90.0),
        # The monitor's screen looks along its own -y, so yaw 90 faces east.
        _on("p7_consumer_grade_monitor_medium", cx - 7.0, cy - 4.0, top, 90.0),
        _on("p7_keyboard_metal_tech", cx + 7.0, cy - 4.0, top, 270.0, scale=0.8),
        _on("p7_electrical_box_set2_box06", cx - 4.0, cy + 38.0, top, 90.0),     # card printer
        _on("p7_electrical_box_set2_meter09", cx + 9.0, cy + 38.0, top, 90.0),   # card reader
        _on("p7_office_paper_stack_sml", cx, cy - 45.0, top, 90.0),              # blank stock
        _on("p7_box_copy_paper_sheet", cx + 1.0, cy - 45.0,
            _top_of("p7_office_paper_stack_sml", top), 20.0),
        _on("p7_cup_coffee_mug", cx + 1.0, cy + 50.0, top, 60.0),
        _on("p7_office_paper_sheet_10", cx + 10.0, cy + 24.0, top, 35.0),
    ], "dense_photo_counter")

    # ---- the clerk's stool, pushed back ------------------------------------
    ctx.put([
        _seated("p7_sgen_chair_dining_future", Point(cx + 44.0, cy + 6.0, pz), Facing.WEST,
                solid=False),
    ], "dense_photo_clerk")

    # ---- the pull-down backdrop behind the pad, over head height -----------
    # Its origin stands over 80 up (the pad test skips what hangs that high),
    # and it stops a unit short of the EXIT sign and the south frames.
    ctx.put([
        on_wall("p7_blinds_cloth_03", Facing.NORTH, -855.0, y0, centre_z=pz + 100.0),
    ], "dense_photo_backdrop")

    # ---- sample photos and the rules for them ------------------------------
    frame, pic = "p7_picture_frame_modern_01", "p7_picture_frame_modern_01"
    ctx.put([on_wall(m, f, a, w, centre_z=z) for m, f, a, w, z in (
        (frame, Facing.EAST, -592.0, x0, pz + 134.0),
        (pic, Facing.EAST, -537.0, x0, pz + 100.0),
        (frame, Facing.WEST, -540.0, x1, pz + 94.0),
        (frame, Facing.WEST, -708.0, x1, pz + 134.0),
        ("p7_signage_loading_zone_02", Facing.WEST, -625.0, x1, pz + 94.0),
        (frame, Facing.SOUTH, -920.0, y1, pz + 94.0),
        (frame, Facing.SOUTH, -780.0, y1, pz + 94.0),
        (frame, Facing.NORTH, -745.0, y0, pz + 94.0),
        ("p7_zm_der2_signage_hazard_01", Facing.NORTH, -975.0, y0, pz + 140.0),
    )], "dense_photo_sample_wall")

    # ---- two cartons of photo stock on the east wall -----------------------
    box = "p7_container_cardboard_box_01"
    bx = x1 - 14.3
    b_top = _top_of(box, pz)
    ctx.put([
        _floor(box, bx, -712.0, pz, 90.0),
        _floor(box, bx, -580.0, pz, 90.0),
        _on("p7_office_paper_stack_sml", bx, -712.0, b_top, 10.0),
        _on("p7_box_copy_paper_sheet", bx - 2.0, -586.0, b_top, 80.0),
        _on("p7_office_paper_sheet_12", bx + 3.0, -574.0, b_top, 20.0),
    ], "dense_photo_stock")

    # ---- rejected licence cards on every free bit of floor -----------------
    pad_x, pad_y = _pad(ctx).x, _pad(ctx).y
    riser_y = y0 + 40.0
    circles = ((pad_x, pad_y, 66.0), (pad_x, pad_y + 56.0, 50.0), (pad_x, riser_y, 50.0))
    busy = [  # solids and what stands on the floor, (x0, y0, x1, y1)
        (x0, -752.0, x0 + 36.0, -640.0),          # the counter
        (x0, y0, x0 + 34.0, y0 + 34.0),           # the lollipop crate
        (-942.0, -656.0, -902.0, -566.0),         # the chairs
        (x0, y1 - 40.0, x0 + 40.0, y1),           # the boxes
        (x1 - 32.0, -735.0, x1, -552.0),          # stock, the table, stock
        (x1 - 36.0, y1 - 36.0, x1, y1),           # the bin
        (x1 - 68.0, y0, x1, y0 + 54.0),           # the aloe
        (-948.0, -716.0, -908.0, -680.0),         # the stool
    ]
    rng = _random.Random(7741)
    cards = []
    tries = 0
    while len(cards) < 24 and tries < 800:
        tries += 1
        x, y = rng.uniform(x0 + 14.0, x1 - 14.0), rng.uniform(y0 + 14.0, y1 - 14.0)
        if any(_math.hypot(x - a, y - b) < r for a, b, r in circles):
            continue
        if any(a <= x <= c and b <= y <= d for a, b, c, d in busy):
            continue
        cards.append(_floor(_CARDS[len(cards) % len(_CARDS)], x, y, pz,
                            rng.uniform(0.0, 360.0), solid=False))
    ctx.put(cards, "dense_photo_cards")

    # ---- the boards and the mess of the outbreak ---------------------------
    ctx.put([
        _floor("p7_debris_wood_board_cluster_01", -880.0, -586.0, pz, 25.0, solid=False),
        _floor("p7_debris_wood_board_splinter_01", -842.0, -566.0, pz, 80.0, solid=False),
        _floor("p7_debris_brick_chunk_hlf_02", -775.0, -640.0, pz, 0.0, solid=False),
        _floor("p7_debris_wood_board_2pc_2x4x128_rt", -770.0, -760.0, pz, 95.0, solid=False),
        _floor("p7_debris_trash_drink_carrier_01", -940.0, -735.0, pz, 40.0, solid=False),
    ], "dense_photo_debris")

    # ---- stacks of rejects, squared up and then abandoned by the pile ------
    stack = "p7_office_paper_stack_sml"
    ctx.put([
        _floor(stack, -785.0, -532.0, pz, 20.0, solid=False),
        _on("p7_office_paper_sheet_10", -787.0, -530.0, _top_of(stack, pz), 50.0),
        _floor(stack, -762.0, -575.0, pz, 70.0, solid=False),
        _floor(stack, -800.0, -625.0, pz, 115.0, solid=False),
        _on("p7_office_paper_sheet_12", -798.0, -627.0, _top_of(stack, pz), 5.0),
    ], "dense_photo_reject_stacks")
