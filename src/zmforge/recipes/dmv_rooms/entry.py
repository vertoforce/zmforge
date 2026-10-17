"""zm_dmv dense pass: the entry room (key ``entry``).  See the package docstring.

The lobby where everyone took a number and then found out what the number
meant: the ticket machine is the only thing in the building that still
works, so the whole room is dressed to point at it.  It stands in the middle
of the lobby facing the front door (:func:`ticket_kiosk_xy`); behind it a
kiosk panel and a sign over it make it read as a dispenser from the doorway, a
drift of dropped tickets lies round its base, and two short lines of
stanchion posts funnel the way in.  Nothing solid stands within
:data:`KIOSK_CLEAR` of its use trigger, and nothing at all solid between the
front door and it.

Vignettes (ids ``dense_entry_<name>``):

``take_a_number``  the dispenser: backdrop panel, wall sign, tickets on top
``tickets``        the drift of dropped paper tickets round its base
``stanchions``     two lines of posts funnelling from the door to it
``overflow``       the bin beside it, overflowing with screwed-up tickets
``now_serving``    the dark NOW SERVING screen on the east wall
``rack``           the publications rack: brochures on top, forms below
``self_service``   the self-service kiosk that never worked, and the repair
``cooler``         the broken cooler's spare bottle, cups and the mop-up
``ceiling``        the patch of ceiling that came down
``debris``         post-outbreak lobby litter
``walls``          a picture on the south wall
"""
from __future__ import annotations

from ..dmv import ticket_kiosk_xy, ticket_trigger_point
from ...dressing import on_room_wall
from ._kit import _mount_face
from ._kit import (
    Facing,
    Point,
    RoomContext,
    _belt_line,
    _floor,
    _mounted,
    _on,
    _top_of,
    shelf_boards,
)

#: No solid prop's footprint comes nearer the ticket trigger than this.
KIOSK_CLEAR = 64.0

KIOSK = "p7_water_cooler_digital_body"
PANEL = "p7_cai_sign_inteactive_kiosk"
POST = "p7_handrail_post_middle"
SCREEN = "p7_cai_monitor_wall_large"
RACK = "p7_shelf_metal_lab_01"

#: The paper a ticket drift is made of.
_SLIPS = (
    "p7_box_copy_paper_sheet", "p7_office_paper_sheet_12", "p7_office_paper_sheet_03",
    "p7_office_paper_sheet_10", "p7_box_copy_paper_sheet", "p7_office_paper_sheet_08",
    "p7_office_paper_sheet_09", "p7_office_paper_sheet_01",
)

NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "entry_self_service": (
        "SELF-SERVICE: hold ^3[{+activate}]^7 to skip the line",
        (
            "Please see an attendant.",
            # Not the service window: that one is open for the quest.
            "The attendant is on break.",
            "The attendant is still on break.",
            "Please take a number.",
        ),
    ),
    "entry_now_serving": (
        "NOW SERVING: hold ^3[{+activate}]^7 to check your number",
        (
            "NOW SERVING: 12.",
            "Your ticket is not 12.",
            "Estimated wait: 3 to 5 business years.",
        ),
    ),
    "entry_line": (
        "LINE STARTS HERE: hold ^3[{+activate}]^7 to join the line",
        (
            "You are now in line.",
            "Please take a number first.",
            "Numbers are not issued in the line. Nothing is issued in the line.",
        ),
    ),
}


def _screen_y(ctx: RoomContext) -> float:
    return 110.0


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """In front of the self-service kiosk and under the screen (both on the
    east wall, clear of the waiting-room door), and at the mouth of the
    stanchion lane (clear of the ticket trigger and Take-a-Number)."""
    e_in, ez = ctx.room.interior, ctx.room.floor_z
    return [
        ("entry_self_service", Point(e_in.maxs.x - 54.0, -190.0, ez)),
        ("entry_now_serving", Point(e_in.maxs.x - 74.0, _screen_y(ctx), ez)),
        ("entry_line", Point(e_in.mins.x + 84.0, 60.0, ez)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the entry lobby."""
    e_in, ez = ctx.room.interior, ctx.room.floor_z
    kx, ky = ticket_kiosk_xy(e_in)
    trig = ticket_trigger_point(e_in, ez)
    west, east = e_in.mins.x, e_in.maxs.x
    south, north = e_in.mins.y, e_in.maxs.y

    # ---- the dispenser --------------------------------------------------
    # A kiosk panel stands behind the machine, facing the door, so it reads
    # as a ticket station from the doorway; its near face is KIOSK_CLEAR+1
    # from the trigger (the panel is 12 deep).  A sign on the east wall
    # behind it, above the waiting-room door's head, and on the machine's top the
    # ticket roll and the last few tickets.
    panel_x = trig.x + KIOSK_CLEAR + 1.0 + 6.0
    top = _top_of(KIOSK, ez)
    sign = "p7_zm_der_storefront_signage_1"
    ctx.put([
        _floor(PANEL, panel_x, ky, ez, (Facing.WEST.world_yaw - _mount_face(PANEL)) % 360.0),
        # A storefront sign's box straddles its origin by 3 either way, so
        # the origin is held 3.1 off the wall; it hangs above the door head.
        _mounted(sign, Point(east - 3.1, ky, ez + 150.0), Facing.WEST),
        _on("p7_box_copy_paper_sheet", kx - 2.0, ky - 3.0, top, 10.0),
        _on("p7_box_copy_paper_sheet", kx + 2.0, ky + 4.0, top, 75.0),
        _on("p7_cup_coffee_mug", kx + 4.0, ky - 4.0, top, 200.0),
    ], "dense_entry_take_a_number")

    # ---- the drift of dropped tickets -----------------------------------
    # Fanned out on the door side where people stood, a few kicked on toward
    # the waiting room.  Paper: nothing here is solid.
    drift = [
        (-30.0, -14.0), (-38.0, 12.0), (-20.0, 22.0), (-52.0, -2.0), (-44.0, -30.0),
        (-64.0, 18.0), (-14.0, -28.0), (-70.0, -22.0), (-26.0, 40.0), (-82.0, 4.0),
        (30.0, 34.0), (60.0, 44.0), (96.0, 52.0), (-4.0, -40.0),
    ]
    ctx.put([
        _floor(_SLIPS[i % len(_SLIPS)], kx + dx, ky + dy, ez, float((i * 53) % 360),
               solid=False)
        for i, (dx, dy) in enumerate(drift)
    ], "dense_entry_tickets")

    # ---- the stanchion lane ---------------------------------------------
    # Two short lines of posts either side of the walk in, belted post to
    # post (bare poles do not read as a waiting line).  The lines are
    # straight because a belt is an axis-aligned brush.  The last post of
    # each is still more than KIOSK_CLEAR from the trigger and the straight
    # walk from the door to the trigger passes between them.  The lines run
    # the whole way from the door to the machine, because short stubs by
    # the door read as random posts that end short of anything; the south
    # line's last post stops just outside
    # KIOSK_CLEAR of the trigger (footprint to trigger).
    rows = [[(-1530.0, -116.0), (-1496.0, -116.0), (-1462.0, -116.0)],
            [(-1530.0, 36.0), (-1496.0, 36.0), (-1462.0, 36.0)]]
    ctx.put([_floor(POST, x, y, ez, 0.0) for row in rows for x, y in row],
            "dense_entry_stanchions")
    for index, row in enumerate(rows):
        _belt_line(ctx.bp, row, ez, f"entry_belt_{index}")

    # ---- the bin beside it, overflowing ---------------------------------
    bx, by = kx + 60.0, ky - 80.0
    ctx.put([
        _floor("p7_trashcan_metal_modern_glass", bx, by, ez, 15.0),
        _floor("p7_cleaning_paper_ball_brown", bx - 22.0, by + 6.0, ez, 0.0, solid=False),
        _floor("p7_cleaning_paper_ball_brown", bx - 10.0, by + 22.0, ez, 70.0, solid=False),
        _floor("p7_cleaning_paper_ball_brown", bx + 20.0, by + 14.0, ez, 140.0, solid=False),
        _floor("p7_cleaning_paper_ball_brown", bx + 4.0, by - 22.0, ez, 210.0, solid=False),
        _floor("p7_office_paper_sheet_09", bx - 24.0, by - 14.0, ez, 30.0, solid=False),
    ], "dense_entry_overflow")

    # ---- the NOW SERVING screen, dark, north of the waiting-room door ----
    ctx.put([
        _mounted(SCREEN, Point(east - 1.0, _screen_y(ctx), ez + 154.0), Facing.WEST),
    ], "dense_entry_now_serving")

    # ---- the publications rack (the first pass's shelf on the west wall) -
    # Its footprint is x -1575..-1543, y -196..-84; brochures on top, the
    # boxes they came in underneath, the forms it lost fanned toward the door.
    rx, ry = west + 24.0, -140.0
    rtop = shelf_boards(RACK, ez)[-1]  # the top board, under the posts
    ctx.put([
        _on("p7_office_paper_stack_sml", rx, ry - 36.0, rtop, 0.0),
        _on("p7_office_paper_stack_sml", rx + 1.0, ry - 8.0, rtop, 184.0),
        _on("p7_office_paper_folder_blue", rx - 2.0, ry + 18.0, rtop, 95.0),
        _on("p7_office_paper_folder_pink", rx + 2.0, ry + 20.0, rtop, 80.0),
        _on("p7_book_vintage_03", rx - 1.0, ry + 38.0, rtop, 90.0),
        _on("p7_book_vintage_05", rx + 1.0, ry + 38.0, _top_of("p7_book_vintage_03", rtop), 70.0),
        _floor("p7_container_cardboard_box_01", west + 16.0, -232.0, ez, 90.0),
        _floor("p7_box_copy_paper_sheet", west + 44.0, -120.0, ez, 20.0, solid=False),
        _floor("p7_office_paper_sheet_01", west + 50.0, -84.0, ez, 110.0, solid=False),
        _floor("p7_office_paper_sheet_10", west + 40.0, -46.0, ez, 250.0, solid=False),
        _floor("p7_office_paper_sheet_03", west + 30.0, -24.0, ez, 15.0, solid=False),
        _floor("p7_office_paper_folder_blue", west + 62.0, -32.0, ez, 160.0, solid=False),
        _floor("p7_office_paper_sheet_02", west + 18.0, -58.0, ez, 300.0, solid=False),
    ], "dense_entry_rack")

    # ---- the self-service kiosk that never worked -----------------------
    # Against the east wall south of the door, clear of the first pass's
    # picture above it; the caution sign on its face, the hazard sign
    # somebody put up after trying to fix it, and its manual on the floor.
    sx, sy = east - 7.0, -98.0
    ctx.put([
        # A dead wall screen, not a second kiosk panel: two panels of one
        # model read as two ticket machines.
        _mounted("p7_cai_monitor_wall_large", Point(east - 1.0, sy - 100.0, ez + 60.0),
                 Facing.WEST),
        _mounted("p7_signage_caution_warning_01", Point(east - 1.0, sy - 100.0, ez + 40.0),
                 Facing.WEST),
        _mounted("p7_zm_der_signage_hazard_03", Point(east - 1.0, -150.0, ez + 70.0),
                 Facing.WEST),
        _floor("p7_office_paper_stack_sml", east - 30.0, -150.0, ez, 70.0, solid=False),
        _floor("p7_office_paper_sheet_08", sx - 30.0, sy + 14.0, ez, 40.0, solid=False),
        _floor("p7_cleaning_paper_folded_wrapped", sx - 26.0, sy - 22.0, ez, 90.0,
               solid=False),
    ], "dense_entry_self_service")

    # ---- the broken cooler on the north wall (first pass: -1500, 274) ----
    ctx.put([
        _floor("p7_water_cooler_digital_bottle", west + 110.0, north - 12.0, ez, 30.0,
               solid=False),
        _floor("p7_debris_trash_cup_red_02", west + 70.0, north - 30.0, ez, 0.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", west + 98.0, north - 44.0, ez, 90.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", west + 120.0, north - 36.0, ez, 45.0, solid=False),
        _floor("p7_cleaning_paper_towel", west + 90.0, north - 22.0, ez, 20.0, solid=False),
        _floor("p7_cleaning_paper_brown", west + 76.0, north - 58.0, ez, 130.0, solid=False),
    ], "dense_entry_cooler")

    # ---- the patch of ceiling that came down -------------------------------
    lx, ly = west + 114.0, 150.0
    ctx.put([
        _floor("p7_debris_rockychunks_small_10", lx + 2.0, ly, ez, 30.0, solid=False),
        _floor("p7_debris_concrete_rubble_sm_06", lx - 6.0, ly + 8.0, ez, 0.0, solid=False),
        _floor("p7_debris_concrete_rubble_sm_07", lx + 12.0, ly - 10.0, ez, 60.0, solid=False),
        _floor("p7_debris_rockychunks_small_07", lx - 2.0, ly - 20.0, ez, 120.0, solid=False),
        _floor("p7_debris_concrete_rubble_sm_02", lx + 16.0, ly + 18.0, ez, 200.0,
               solid=False),
    ], "dense_entry_ceiling")

    # ---- post-outbreak lobby litter -------------------------------------
    ctx.put([
        _floor("p7_debris_newspaper_04", west + 60.0, 18.0, ez, 200.0, solid=False),
        _floor("p7_debris_newspaper_06", east - 90.0, 40.0, ez, 30.0, solid=False),
        _floor("p7_debris_trash_drink_carrier_01", east - 120.0, -20.0, ez, 15.0,
               solid=False),
        _floor("p7_debris_trash_paper_plate_01", -1340.0, 70.0, ez, 0.0, solid=False),
        _floor("p7_debris_trash_drink_carrier_01", -1440.0, 90.0, ez, 75.0, solid=False),
        _floor("p7_debris_clothing_tshirts_02", -1360.0, 200.0, ez, 40.0, solid=False),
        _floor("p7_debris_wood_board_splinter_01", west + 40.0, 40.0, ez, 20.0, solid=False),
        _floor("p7_debris_trash_cup_coffee_02", -1300.0, -40.0, ez, 0.0, solid=False),
        _floor("p7_debris_trash_paper_03", -1300.0, 240.0, ez, 90.0, solid=False),
        _floor("p7_cleaning_paper_ball_brown", -1296.0, 262.0, ez, 0.0, solid=False),
    ], "dense_entry_debris")

    # ---- walls ----------------------------------------------------------
    ctx.put([
        _mounted("p7_picture_frame_modern_01", Point(-1506.0, south + 1.5, ez + 128.0),
                 Facing.NORTH),
    ], "dense_entry_walls")

    dress_more(ctx)


# ==========================================================================
# Second density pass: more props, and more of them reading as a DMV.
# The helpers below are private to this module.
# ==========================================================================


#: Paper, cups and wrappers: what a lobby floor collects (all low-poly).
_D2_LITTER = (
    "p7_office_paper_sheet_01", "p7_debris_trash_cup_red_02", "p7_office_paper_sheet_10",
    "p7_debris_trash_paper_03", "p7_office_paper_sheet_12", "p7_debris_trash_cup_coffee_02",
    "p7_office_paper_sheet_02", "p7_debris_trash_paper_09", "p7_box_copy_paper_sheet",
    "p7_debris_trash_food_box_01", "p7_office_paper_sheet_08", "p7_cleaning_paper_brown",
    "p7_debris_trash_paper_05", "p7_office_paper_sheet_03", "p7_debris_trash_paper_plate_01",
    "p7_cleaning_paper_towel", "p7_debris_trash_paper_10", "p7_office_paper_sheet_09",
)


def dress_more(ctx: RoomContext) -> None:
    """The second density pass: the lobby's walls papered with the rules,
    a bench where people waited to take a number, what they left, the
    forms that came in boxes, the boards gathered for the doors, and the
    floor of a lobby three hundred people ran through."""
    room = ctx.room
    e_in, ez = room.interior, room.floor_z
    west, east = e_in.mins.x, e_in.maxs.x
    south, north = e_in.mins.y, e_in.maxs.y
    poster, frame = "p7_picture_frame_modern_01", "p7_picture_frame_modern_01"

    # ---- posters: rules, fees, hours, the forms list ---------------------
    ctx.put([
        on_room_wall("p7_cai_signage_plastic_exit", room, "w", 0.0, 104.0),
        on_room_wall(poster, room, "w", -180.0, 106.0),          # over the rack: FEES
        on_room_wall(poster, room, "w", -130.0, 106.0),          # over the rack: FORMS
        on_room_wall("p7_zm_der_signage_no_smoking", room, "w", -66.0, 58.0),
        on_room_wall("p7_zm_der2_bulletin_board", room, "w", 196.0, 48.0),
        on_room_wall(poster, room, "s", west + 24.0, 84.0),      # HOURS
        on_room_wall(poster, room, "s", -1500.0, 68.0),          # WHAT TO BRING
        on_room_wall(frame, room, "s", east - 26.0, 84.0),
        on_room_wall(poster, room, "n", -1474.0, 80.0),          # PLEASE HAVE YOUR ID READY
        on_room_wall(poster, room, "n", -1322.0, 80.0),
        on_room_wall(frame, room, "n", east - 30.0, 88.0),
        on_room_wall("p7_zm_der_signage_wash_hands", room, "n", -1400.0 + 70.0, 60.0),
    ], "dense_entry_posters")

    # ---- the bench by the NOW SERVING screen, and what was left on it -----
    bench = "p7_bench_modern_01"
    bx, by = east - 10.0, 190.0
    btop = _top_of(bench, ez)
    ctx.put([
        _floor(bench, bx, by, ez, 90.0),
        _on("p7_book_vintage_open_01", bx, by - 28.0, btop, 0.0),
        _on("p7_cup_coffee_mug", bx + 2.0, by - 12.0, btop, 60.0),
        _on("p7_office_paper_stack_sml", bx, by + 8.0, btop, 0.0),
        _on("p7_bottle_plastic_16oz_water", bx - 3.0, by + 24.0, btop, 0.0),
        _on("p7_debris_trash_food_box_01", bx, by + 32.0, btop, 20.0),
        _floor("p7_luggage_cloth_a_lg_green", bx - 6.0, 132.0, ez, 90.0, solid=False),
        _floor("p7_debris_trash_cup_coffee_02", bx - 22.0, by - 8.0, ez, 40.0, solid=False),
        _floor("p7_debris_newspaper_05", bx - 34.0, by + 20.0, ez, 80.0, solid=False),
    ], "dense_entry_bench")
    ctx.put([
        _floor("p7_3arc_lobby_plant", east - 24.0, north - 26.0, ez, 0.0),
        _floor("p7_luggage_hardshell_handle_down_white", -1325.0, north - 10.0, ez, 0.0,
               solid=False),
        _floor("p7_debris_clothing_tshirts_01", -1336.0, north - 44.0, ez, 30.0, solid=False),
    ], "dense_entry_corner")

    # ---- the forms: boxes of them in the south-west corner --------------
    # The first box stands at (west + 16, -232); another went on top and the
    # pads on that, and the ones nobody wanted are on the floor.
    box = "p7_container_cardboard_box_01"
    btop1 = _top_of(box, ez)
    btop2 = _top_of(box, btop1)
    ctx.put([
        _on(box, west + 16.0, -232.0, btop1, 90.0),
        _on("p7_office_paper_stack_sml", west + 12.0, -242.0, btop2, 10.0),
        _on("p7_office_paper_stack_sml", west + 16.0, -222.0, btop2, 100.0),
        _on("p7_office_paper_folder_blue", west + 12.0, -242.0, _top_of(
            "p7_office_paper_stack_sml", btop2), 60.0),
        _floor("p7_box_copy_paper_sheet", west + 44.0, -226.0, ez, 30.0, solid=False),
        _floor("p7_box_copy_paper_sheet", west + 50.0, -244.0, ez, 100.0, solid=False),
        _floor("p7_office_paper_stack_sml", west + 40.0, -262.0, ez, 200.0, solid=False),
    ], "dense_entry_forms")

    # ---- more brochures on the publications rack's top -------------------
    rx, rtop = west + 24.0, shelf_boards("p7_shelf_metal_lab_01", ez)[-1]
    ctx.put([
        _on("p7_book_vintage_01", rx, -196.0, rtop, 90.0),
        _on("p7_office_paper_sheet_03", rx, -169.0, rtop, 0.0),
        _on("p7_office_paper_sheet_09", rx + 1.0, -141.0, rtop, 90.0),
        _on("p7_book_vintage_06", rx - 1.0, -97.0, rtop, 90.0),
    ], "dense_entry_rack_top")

    # ---- boards somebody gathered to nail over the doors -----------------
    px, py = -1300.0, south + 26.0
    ctx.put([
        _floor("p7_debris_wood_board_cluster_01", px, py, ez, 0.0, solid=False),
        _floor("p7_debris_wood_board_cluster_04", px - 44.0, py - 4.0, ez, 90.0, solid=False),
        _floor("p7_debris_wood_board_splinter_02", px - 20.0, py + 26.0, ez, 10.0,
               solid=False),
        _floor("p7_debris_wood_board_splinter_01", px + 26.0, py + 22.0, ez, 70.0,
               solid=False),
        _floor("p7_debris_wood_board_cluster_03", -1246.0, -120.0, ez, 30.0, solid=False),
    ], "dense_entry_boards")

    # ---- somebody did not make it to the front door ----------------------
    gx, gy = -1520.0, -40.0 - 60.0
    ctx.put([
        _floor(model, gx + dx, gy + dy, ez, yaw, solid=False)
        for model, dx, dy, yaw in (
            ("p7_gib_chunk_flesh_01", 0.0, 0.0, 0.0), ("p7_gib_chunk_meat_02", 10.0, -6.0, 60.0),
            ("p7_gib_chunk_bone_01", -8.0, 8.0, 120.0), ("p7_gib_chunk_meat_03", 14.0, 10.0, 200.0),
            ("p7_gib_chunk_bone_03", -12.0, -10.0, 30.0),
            ("p7_debris_clothing_pants_01", 30.0, -30.0, 70.0),
        )
    ], "dense_entry_gore")

    # ---- the floor --------------------------------------------------------
    kx, ky = ticket_kiosk_xy(e_in)
    keep = [(kx - 40.0, ky - 40.0, kx + 30.0, ky + 40.0)]
    # In heaps, not confetti: tickets and
    # forms dropped beside the machine, the bins overflowing, and what the
    # door draft pushed into the corners.  Same 64 pieces.
    from ._kit import BIN_SPILL, DRIFT, DROPPED_FORMS, bins_in, corner_heaps, litter_heaps
    rect = (west + 8.0, south + 8.0, east - 8.0, north - 8.0)
    heaps = [(kx + 50.0, ky + 6.0, 16.0, 4.0, DROPPED_FORMS),
             (kx + 20.0, ky - 56.0, 14.0, 2.0, DROPPED_FORMS)]
    heaps += [(bx, by, 16.0, 2.0, BIN_SPILL) for bx, by in bins_in(ctx)]
    heaps += [(cx, cy, 16.0, 1.5, DRIFT) for cx, cy in corner_heaps(rect)]
    ctx.put(litter_heaps(ctx, rect, 64, 7101, heaps, keep_out=keep), "dense_entry_litter")
