"""zm_dmv dense pass: the windows room (key ``windows``).  See the package docstring.

The counter hall.  One service window in a partition wall, and the staff
side behind it still holds everyone's lunch and workday.  What this pass adds:

* **every clerk's place along the run** -- the staff work surface behind
  the partition carries each clerk's leftovers: bay 1's open binder, bay
  2's mug and pot, bay 3's lunch, bay 8's bottle hidden behind the manuals;
* **the service window** (bay 5) -- the one monitor on the run, a mug, and a
  form somebody left on the patron ledge;
* **the staff floor** -- paperwork on every desk, copy-paper boxes and a crate
  of binders between the desks, a pulled-out drawer and its spill, cabinet
  tops and file cabinets used as shelves;
* **the public floor** -- tickets nobody was called for at the foot of the
  run, the paper towels on a wet patch of floor, the chair
  somebody dragged up to the service window, and the organ-donor poster;
* three notices: the complaints box, the clerk's terminal and the lost and
  found.
"""
from __future__ import annotations

from ...dressing import on_room_wall, turned_box
from ._kit import (
    Facing,
    Point,
    RoomContext,
    _floor,
    _mounted,
    _on,
    _seated,
    _top_of,
    counter_run,
    bay_centres,
)

#: The room's use-trigger jokes (shape of :data:`zmforge.recipes.dmv.NOTICE_LINES`).
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "windows_complaints": ("COMPLAINTS: hold ^3[{+activate}]^7 to file a complaint", (
        "Complaint received. Estimated response: 45 minutes.",
        "Complaints about wait times are handled at the service window.",
        "Your complaint has been placed in the queue. You are number 2292.",
    )),
    "windows_terminal": ("CLERK'S TERMINAL: hold ^3[{+activate}]^7 to check status", (
        "SYSTEM DOWN. PLEASE WAIT.",
        "Loading... 3%",
        "Your appointment has been moved to 06/14. Of which year: not stated.",
        "ERROR: customer not found. Customer may be deceased.",
    )),
    "windows_lost_found": ("LOST AND FOUND: hold ^3[{+activate}]^7 to look", (
        "One glove. Left.",
        "Ticket 13. It was called 212 days ago.",
        "A set of car keys. The car is still in the lot.",
        "An arm. Please claim it at the service window.",
    )),
}

#: The named story vignettes and the scatter id each one goes out under.
VIGNETTES: dict[str, str] = {
    "clerk_places": "dense_windows_clerk_places",
    "service_window": "dense_windows_service_window",
    "staff_desks": "dense_windows_desks",
    "staff_floor": "dense_windows_staff_floor",
    "cabinet_tops": "dense_windows_cabinet_tops",
    "tickets": "dense_windows_tickets",
    "wet_floor": "dense_windows_wet_floor",
    "own_chair": "dense_windows_own_chair",
    "walls": "dense_windows_walls",
    "litter": "dense_windows_litter",
}

#: The four staff desks, one per pair of windows (from ``_furnish_lived_in``):
#: their centres' y, and the desk's own centre x.
_DESK_X = -362.0
_DESK_YS = (-300.0, -132.0, 36.0, 204.0)
_DESK = "p7_desk_metal_old_01_body"


def dress(ctx: RoomContext) -> None:
    """Fill the counter hall."""
    room = ctx.room
    win = room.interior
    fz = room.floor_z
    plan = ctx.plan
    face_x, back_x, _y0, run_y1 = counter_run(plan)
    ledge_x1 = face_x + plan.patron_ledge_depth
    surface_x = (ledge_x1 + back_x) / 2.0
    surface_top = fz + plan.staff_surface_height
    ledge_top = fz + plan.counter_height
    c = bay_centres(plan)
    desk_top = _top_of(_DESK, fz)

    # ---- every clerk's place along the run (the staff work surface) ----
    ctx.put([
        # Bay 1 (ADA): the binder left open at the page nobody reads.
        _on("p7_book_office_binder_open", surface_x, c[0] - 22.0, surface_top, 0.0),
        # Bay 2: three mugs and the pot, the coffee still on.
        _on("p7_cup_coffee_mug", surface_x - 5.0, c[1] - 30.0, surface_top, 20.0),
        _on("p7_coffee_maker_digital_pot", surface_x, c[1] + 22.0, surface_top, 90.0),
        # Bay 3: lunch, started and abandoned.
        _on("p7_food_fruit_banana_bunch", surface_x, c[2] - 18.0, surface_top, 30.0),
        _on("p7_debris_trash_drink_carrier_01", surface_x, c[2] - 34.0, surface_top, 15.0),
        # Bay 4: the carry-permit manuals, standing.
        _on("p7_book_office_lrg_red", surface_x, c[3] + 26.0, surface_top, 90.0),
        _on("p7_book_office_med_brown", surface_x, c[3] + 31.0, surface_top, 90.0),
        # Bay 7: the pink folder pile.
        _on("p7_office_paper_folder_pink", surface_x, c[6] - 22.0, surface_top, 80.0),
        # Bay 8: the bottle kept behind the manuals.
        _on("p7_books_office_row_01", surface_x - 6.0, c[7] - 18.0, surface_top, 180.0),
        _on("p7_bottle_glass_liquor_03", surface_x + 7.0, c[7] - 18.0, surface_top, 0.0),
    ], VIGNETTES["clerk_places"])

    # ---- the service window ------------------------------------------------
    ctx.put([
        # The one monitor on the run, turned to the clerk, not the customer.
        _on("p7_consumer_grade_monitor_medium", surface_x + 3.0, c[4] + 6.0,
            surface_top, 90.0),
        _on("p7_cup_coffee_mug", surface_x - 6.0, c[4] - 30.0, surface_top, 130.0),
        # The form somebody left on the patron ledge, filled in wrong.
        _on("p7_office_paper_sheet_01", (face_x + ledge_x1) / 2.0, c[4] - 14.0,
            ledge_top, 80.0),
    ], VIGNETTES["service_window"])

    # ---- the staff desks: paperwork on every one ------------------------
    desks: list[tuple] = []
    for n, y in enumerate(_DESK_YS):
        desks.append(_on("p7_office_paper_sheet_10", _DESK_X + 2.0, y - 11.0,
                         desk_top, 20.0 + 40.0 * n))
    ctx.put(desks, VIGNETTES["staff_desks"])

    # ---- the staff floor -------------------------------------------------
    box = "p7_container_cardboard_box_01"
    box_x = back_x + 22.0
    ctx.put([
        # Copy paper, delivered and never opened, between the first two desks.
        _floor(box, box_x, -242.0, fz, 0.0),
        _floor(box, box_x, -210.0, fz, 0.0),
        _on("p7_office_paper_stack_sml", box_x, -242.0, _top_of(box, fz), 12.0),
        # A drawer pulled out and dumped between desks two and three, and
        # what was in it.
        _floor("p7_file_cab_metal_02_drawer_02", back_x + 20.0, -70.0, fz, 80.0,
               solid=False),
        _floor("p7_office_paper_sheet_02", back_x + 42.0, -52.0, fz, 40.0, solid=False),
        # A crate of binders between desks three and four.
        _floor("p7_crate_plastic_tech_01", back_x + 18.0, 120.0, fz, 0.0),
        _on("p7_book_office_binder_open", back_x + 18.0, 108.0,
            _top_of("p7_crate_plastic_tech_01", fz), 0.0),
    ], VIGNETTES["staff_floor"])

    # ---- the cabinet tops against the east wall, used as shelves ---------
    cab_top = _top_of("p7_zm_der_cabinet_lab_bottom", fz)
    file_top = _top_of("p7_file_cab_metal_02", fz)
    cx = win.maxs.x - 16.0
    ctx.put([
        _on("p7_books_office_row_01", cx, -254.0, cab_top, 270.0),
        _on("p7_coffee_maker_digital_pot", cx, 166.0, cab_top, 270.0),
        _on("p7_office_paper_stack_sml", cx, 100.0, file_top, 90.0),
        _on("p7_books_office_row_01", cx, -120.0, file_top, 270.0),
    ], VIGNETTES["cabinet_tops"])

    # ---- the public floor: tickets nobody was called for ----------------
    ticket = "p7_office_paper_sheet_12"
    foot = face_x - 14.0
    ctx.put([
        _floor(ticket, foot, y, fz, yaw, solid=False)
        for y, yaw in ((c[4] - 26.0, 10.0), (c[4] + 34.0, 75.0), (c[2] + 10.0, 200.0))
    ], VIGNETTES["tickets"])

    # The wet floor: the towels that did not help.  (No ``p7_3arc_park_pylon``
    # as a "cone": it is a grey kerb bollard and reads as a lone random post
    # on the public floor in front of the counter.)
    wet_x, wet_y = -580.0, 150.0
    ctx.put([
        _floor("p7_cleaning_paper_towel", wet_x + 22.0, wet_y - 10.0, fz, 30.0, solid=False),
        _floor("p7_cleaning_paper_towel", wet_x - 6.0, wet_y + 8.0, fz, 115.0, solid=False),
    ], VIGNETTES["wet_floor"])

    # The chair somebody dragged up to the service window and waited in.
    ctx.put([
        _seated("p7_chair_waiting_room_01_blue",
                Point(face_x - 36.0, c[4] + 50.0, fz), Facing.EAST),
    ], VIGNETTES["own_chair"])

    # ---- wall dressing ---------------------------------------------------
    ctx.put([
        # Public side: the organ-donor poster, an anatomy chart, by the door.
        _mounted("p7_zm_der2_poster_anatomy_02",
                 Point(win.mins.x + 0.5, -150.0, fz + 100.0), Facing.EAST),
        # Staff side: the south wall's safety notices and the north wall's
        # staff board by the gate.
        _mounted("p7_zm_der2_poster_anatomy_04",
                 Point(-380.0, win.mins.y + 0.5, fz + 100.0), Facing.NORTH),
        _mounted("p7_zm_der2_bulletin_board",
                 Point(-360.0, win.maxs.y - 3.0, fz + 96.0), Facing.SOUTH),
        # A closed blind on the staff side's south wall, west of the boarded one: the window
        # back here, shut so nobody has to look at the car park.
        _mounted("p7_blinds_01_wide_closed",
                 Point(-310.0, win.mins.y + 2.0, fz + 110.0), Facing.NORTH),
    ], VIGNETTES["walls"])

    # ---- floor litter ----------------------------------------------------
    ctx.put([
        _floor(model, x, y, fz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_trash_cup_coffee_02", -540.0, 60.0, 30.0),
            ("p7_debris_trash_drink_carrier_01", -660.0, -250.0, 0.0),
            ("p7_debris_trash_paper_09", -220.0, 300.0, 60.0),
        )
    ], VIGNETTES["litter"])

    dress_more(ctx)


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """Where each of :data:`NOTICES` stands, on reachable floor, 80+ from
    every other use trigger."""
    fz = ctx.room.floor_z
    return [
        # West wall of the public floor, under the organ-donor poster.
        ("windows_complaints", Point(-640.0, -210.0, fz)),
        # Staff floor, behind the service window's desk.
        ("windows_terminal", Point(-280.0, 100.0, fz)),
        # Staff floor, by the lab cabinet the lost property is kept in.
        ("windows_lost_found", Point(-200.0, -220.0, fz)),
    ]


# ==========================================================================
# Second density pass: more props, and more of them reading as a DMV.
# The helpers below are private to this module.
# ==========================================================================
import math as _m2
import random as _r2

from ...blueprint.elements import PropScatter as _PropScatter2
from ...placement.relations import Placed as _Placed2
from ._kit import collision_box as _box2
from ._kit import SEAT_TOP


def _d2_solids3(ctx) -> list[tuple[float, float, float, float, float, float]]:
    """3-D boxes (x0, y0, x1, y1, z0, z1) of every prop in this room."""
    b = ctx.room.interior
    out = []
    for scatter in ctx.bp.elements(_PropScatter2):
        for p in scatter.props:
            box = _box2(p.model)
            if box is None:
                continue
            pl = _Placed2.from_model(p.model, box, (p.origin.x, p.origin.y, p.origin.z),
                                     p.yaw, p.scale, solid=p.solid)
            if not (b.mins.x - 4 <= pl.x <= b.maxs.x + 4 and b.mins.y - 4 <= pl.y <= b.maxs.y + 4):
                continue
            c, s = abs(_m2.cos(_m2.radians(pl.yaw))), abs(_m2.sin(_m2.radians(pl.yaw)))
            ex, ey = pl.hx * c + pl.hy * s, pl.hx * s + pl.hy * c
            out.append((pl.x - ex, pl.y - ey, pl.x + ex, pl.y + ey, pl.z_low, pl.z_high))
    return out


def _d2_fit_on(ctx, taken, items) -> list[tuple]:
    """Of *items* (``_on`` tuples), the ones whose box meets nothing already
    in *taken* (3-D boxes, extended as items are accepted) -- so a kit dealt
    onto a surface that already carries somebody's things steps round them."""
    out = []
    for item in items:
        model, pos, yaw, scale = item[0], item[1], item[2], item[3]
        x0, y0, x1, y1 = turned_box(model, yaw)
        (_a, _b, z0), (_c, _d, z1) = _box2(model)
        me = (pos.x + x0 * scale, pos.y + y0 * scale, pos.x + x1 * scale, pos.y + y1 * scale,
              pos.z + z0 * scale, pos.z + z1 * scale)
        if any(me[0] < o[2] - 0.5 and o[0] < me[2] - 0.5 and me[1] < o[3] - 0.5
               and o[1] < me[3] - 0.5 and me[4] < o[5] - 0.2 and o[4] < me[5] - 0.2
               for o in taken):
            continue
        taken.append(me)
        out.append(item)
    return out


def _d2_fit_first(ctx, taken, options) -> list[tuple]:
    """For each entry of *options* (a list of alternative ``_on`` tuples for
    one item), the first alternative that fits (:func:`_d2_fit_on`)."""
    out = []
    for alternatives in options:
        for item in alternatives:
            got = _d2_fit_on(ctx, taken, [item])
            if got:
                out += got
                break
    return out


def _d2_pack(ctx, taken, models, rect, top: float, n: int, seed: int) -> list[tuple]:
    """Up to *n* of *models* (cycled) set down on a surface at *top* inside
    *rect* (x0, y0, x1, y1), deterministically, each clear of what is there."""
    rng = _r2.Random(seed)
    out: list[tuple] = []
    tries = 0
    while len(out) < n and tries < n * 40:
        tries += 1
        model = models[len(out) % len(models)]
        yaw = float(rng.randrange(0, 360, 15))
        x0, y0, x1, y1 = turned_box(model, yaw)
        w, h = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        if rect[2] - rect[0] < 2 * w or rect[3] - rect[1] < 2 * h:
            continue
        x = rng.uniform(rect[0] + w, rect[2] - w)
        y = rng.uniform(rect[1] + h, rect[3] - h)
        out += _d2_fit_on(ctx, taken, [_on(model, x, y, top, yaw)])
    return out


_D2_LITTER = (
    "p7_office_paper_sheet_12", "p7_office_paper_sheet_01", "p7_debris_trash_cup_coffee_02",
    "p7_office_paper_sheet_10", "p7_box_copy_paper_sheet", "p7_debris_trash_paper_03",
    "p7_office_paper_sheet_02", "p7_office_paper_sheet_08", "p7_debris_trash_cup_red_02",
    "p7_office_paper_sheet_03", "p7_debris_trash_paper_09", "p7_office_paper_sheet_09",
    "p7_cleaning_paper_ball_brown", "p7_debris_trash_paper_05", "p7_office_paper_folder_blue",
)

VIGNETTES.update({
    "counter_kits": "dense_windows_counter_kits",
    "desk_work": "dense_windows_desk_work",
    "back_shelves": "dense_windows_back_shelves",
    "form_boxes": "dense_windows_form_boxes",
    "public_seats": "dense_windows_public_seats",
    "posters": "dense_windows_posters",
    "gore": "dense_windows_gore",
    "public_litter": "dense_windows_public_litter",
    "staff_litter": "dense_windows_staff_litter",
})


def dress_more(ctx: RoomContext) -> None:
    """The second density pass: every staffed window kitted out the way a
    branch window is (screen, keyboard, in-tray, signature pad, the forms),
    the desks behind worked on, the forms in boxes, a row of chairs on the
    public side, the rules on the walls, and the paper of a day that ended
    at 9:02 on both floors."""
    room = ctx.room
    win, fz = room.interior, room.floor_z
    plan = ctx.plan
    face_x, back_x, _y0, _y1 = counter_run(plan)
    ledge_x1 = face_x + plan.patron_ledge_depth
    surface_top = fz + plan.staff_surface_height
    ledge_top = fz + plan.counter_height
    c = bay_centres(plan)
    taken = _d2_solids3(ctx)

    # ---- the counter kit at every bay but 3 and 5 ------------------------
    # Bay 3 is the forms in-tray (a quest spot) and 5 the service window:
    # both stay as they are.
    kit: list[list[tuple]] = []
    tray = "p7_desk_metal_old_01_drawer_small_01"
    tray_top = _top_of(tray, surface_top)
    slide = (0.0, 12.0, -12.0, 24.0, -24.0, 32.0, -32.0)
    for n in (0, 1, 3, 5, 6, 7):
        y = c[n]
        kit.append([_on("p7_consumer_grade_monitor_medium", ledge_x1 + 4.0, y + d, surface_top,
                        90.0, scale=0.7) for d in slide])
        kit.append([_on("p7_keyboard_metal_tech", back_x - 7.0, y + d, surface_top, 90.0,
                        scale=0.5) for d in slide])
        kit.append([_on(tray, back_x - 12.0, y + d, surface_top, 0.0) for d in slide[::-1]])
        kit.append([_on("p7_cup_coffee_mug", back_x - 4.0, y + d, surface_top, 40.0 * n)
                    for d in (-36.0, 36.0, -18.0, 18.0, 0.0)])
        kit.append([_on("p7_office_paper_stack_sml", ledge_x1 + 9.0, y + d, surface_top, 5.0 * n)
                    for d in (-30.0, 30.0, -16.0, 16.0)])
        kit.append([_on("p7_office_paper_sheet_02", (face_x + ledge_x1) / 2.0, y + d, ledge_top,
                        90.0 + 11.0 * n) for d in (26.0, -26.0, 34.0)])
        if n in (1, 5, 7):
            kit.append([_on("p7_office_paper_folder_pink", (face_x + ledge_x1) / 2.0,
                            y + d, ledge_top, 0.0) for d in (-20.0, 10.0, -34.0)])
    placed = _d2_fit_first(ctx, taken, kit)
    # A sheet in each in-tray that went down.
    placed += _d2_fit_on(ctx, taken, [
        _on("p7_office_paper_sheet_10", item[1].x, item[1].y, tray_top - 5.0, 20.0)
        for item in list(placed) if item[0] == tray])
    ctx.put(placed, VIGNETTES["counter_kits"])

    # ---- the desks behind: a day's work on each -------------------------
    desk_top = _top_of(_DESK, fz)
    work: list[tuple] = []
    desk_things = ("p7_books_office_row_01", "p7_book_office_binder_open",
                   "p7_office_paper_sheet_01", "p7_bottle_plastic_16oz_water",
                   "p7_debris_trash_food_box_01", "p7_office_paper_folder_blue",
                   "p7_cup_coffee_mug", "p7_office_paper_sheet_08")
    for n, y in enumerate(_DESK_YS):
        work += _d2_pack(ctx, taken, desk_things[n % 2:] + desk_things[:n % 2],
                         (_DESK_X - 36.0, y - 16.0, _DESK_X + 36.0, y + 16.0), desk_top, 6,
                         7310 + n)
    ctx.put(work, VIGNETTES["desk_work"])

    # ---- the cabinet and file-cabinet tops on the east wall --------------
    cab_top = _top_of("p7_zm_der_cabinet_lab_bottom", fz)
    file_top = _top_of("p7_file_cab_metal_02", fz)
    cx = win.maxs.x - 16.0
    shelves = [
        _on("p7_office_paper_stack_sml", cx, 120.0, file_top, 0.0),
        _on("p7_office_paper_stack_sml", cx, 140.0, file_top, 90.0),
        _on("p7_book_office_binder_open", cx, -100.0, file_top, 0.0),
        _on("p7_office_paper_stack_sml", cx, -140.0, file_top, 180.0),
        _on("p7_books_office_row_01", cx, 244.0, cab_top, 270.0),
        _on("p7_office_paper_folder_blue", cx, 226.0, cab_top, 30.0),
        _on("p7_bottle_plastic_16oz_water", cx + 4.0, 196.0, cab_top, 0.0),
        _on("p7_office_paper_folder_pink", cx, -170.0, cab_top, 60.0),
        _on("p7_cup_coffee_mug", cx + 3.0, -210.0, cab_top, 30.0),
        _on("p7_book_office_lrg_red", cx, -242.0, cab_top, 0.0),
    ]
    ctx.put(_d2_fit_on(ctx, taken, shelves), VIGNETTES["back_shelves"])

    # ---- forms by the box, against the staff side's south wall -----------
    box = "p7_container_cardboard_box_01"
    bx, by = -322.0, win.mins.y + 16.0
    b1 = _top_of(box, fz)
    ctx.put([
        _floor(box, bx, by, fz, 0.0),
        _on(box, bx, by, b1, 0.0),
        _on("p7_office_paper_stack_sml", bx, by, _top_of(box, b1), 0.0),
        _floor(box, bx + 42.0, by, fz, 0.0, solid=False),
        _on("p7_office_paper_folder_blue", bx + 42.0, by, b1, 70.0),
        _floor("p7_box_copy_paper_sheet", bx + 20.0, by + 26.0, fz, 40.0, solid=False),
        _floor("p7_office_paper_stack_sml", bx - 30.0, by + 18.0, fz, 110.0, solid=False),
    ], VIGNETTES["form_boxes"])

    # ---- a row of chairs on the public side's west wall ------------------
    # Either side of the complaints box (y -210), clear of the door (y +-72).
    seats = [(win.mins.x + 13.0, y) for y in (-324.0, -300.0, -276.0, -252.0, -168.0, -144.0)]
    top = fz + SEAT_TOP[_D2_CHAIR]
    ctx.put([_seated(_D2_CHAIR, Point(x, y, fz), Facing.EAST) for x, y in seats]
            + [_on(m, x + 3.0, y, top, 30.0 * i) for i, (m, (x, y)) in enumerate(zip(
                ("p7_office_paper_folder_pink", "p7_cup_coffee_mug",
                 "p7_book_vintage_open_04", "p7_office_paper_sheet_01"),
                (seats[0], seats[2], seats[3], seats[5])))],
            VIGNETTES["public_seats"])

    # ---- walls: the rules, the fees, the hours ---------------------------
    poster, frame = "p7_picture_frame_modern_01", "p7_picture_frame_modern_01"
    ctx.put([
        on_room_wall(poster, room, "w", -290.0, 80.0),
        on_room_wall(poster, room, "w", 110.0, 80.0),
        on_room_wall(poster, room, "w", 280.0, 90.0),
        on_room_wall(poster, room, "s", -660.0, 90.0),
        on_room_wall(poster, room, "s", -510.0, 90.0),
        on_room_wall(frame, room, "s", -420.0, 76.0),
        on_room_wall(poster, room, "n", -410.0, 70.0),
        on_room_wall(poster, room, "e", 80.0, 90.0),
        on_room_wall("p7_zm_der_signage_no_smoking", room, "n", -330.0, 100.0),
    ], VIGNETTES["posters"])

    # ---- the clerk who went over the counter -----------------------------
    gx, gy = -520.0, 250.0
    ctx.put([
        _floor(model, gx + dx, gy + dy, fz, yaw, solid=False)
        for model, dx, dy, yaw in (
            ("p7_gib_chunk_flesh_01", 0.0, 0.0, 0.0), ("p7_gib_chunk_meat_02", 12.0, -8.0, 60.0),
            ("p7_gib_chunk_bone_03", -10.0, 6.0, 120.0), ("p7_gib_chunk_meat_03", 16.0, 12.0, 200.0),
            ("p7_gib_chunk_bone_01", -14.0, -12.0, 30.0),
            ("p7_debris_clothing_tshirts_02", 30.0, -24.0, 70.0),
        )
    ], VIGNETTES["gore"])

    # ---- both floors ------------------------------------------------------
    dress_more_floors(ctx)
    # Not inside the registration car: its clips' footprint is kept out
    # (four sheets of litter were strewn in it).
    from ...blueprint.elements import Massing as _Massing
    car = [m.authored.box for m in ctx.bp.elements(_Massing)
           if m.id.startswith("perk_registration_car_clip")]
    car_out = [(min(b.mins.x for b in car), min(b.mins.y for b in car),
                max(b.maxs.x for b in car), max(b.maxs.y for b in car))] if car else []
    # In heaps, not confetti.  Public side:
    # forms dropped at the counter's open window and drifted into the
    # corners; staff side: paper fallen round the desks.  Same 48 + 44.
    from ._kit import DRIFT, DROPPED_FORMS, corner_heaps, litter_heaps, room_heaps
    pub = (win.mins.x + 8.0, win.mins.y + 8.0, face_x - 4.0, win.maxs.y - 8.0)
    pub_heaps = room_heaps(ctx, pub, 7301)
    pub_heaps += [(face_x - 30.0, cy, 14.0, 1.0, DROPPED_FORMS) for cy in c[::3]]
    ctx.put(litter_heaps(ctx, pub, 48, 7301, pub_heaps, keep_out=car_out),
            VIGNETTES["public_litter"])
    staff = (back_x + 4.0, win.mins.y + 8.0, win.maxs.x - 8.0, win.maxs.y - 8.0)
    staff_heaps = [(cx, cy, 14.0, 1.0, DRIFT) for cx, cy in corner_heaps(staff, 20.0)]
    staff_heaps += [(back_x + 30.0, cy, 14.0, 1.5, DROPPED_FORMS) for cy in c[1::3]]
    ctx.put(litter_heaps(ctx, staff, 44, 7302, staff_heaps), VIGNETTES["staff_litter"])


_D2_CHAIR = "p7_chair_waiting_room_01_blue"


def dress_more_floors(ctx: RoomContext) -> None:
    """What would not fit on the desks, on the floor beside them, and the
    tickets nobody called, along the foot of the run (clear of bays 3
    and 5, the forms in-tray and the service window, where people stand)."""
    fz = ctx.room.floor_z
    face_x, _back_x, _y0, _y1 = counter_run(ctx.plan)
    c = bay_centres(ctx.plan)
    piles: list[tuple] = []
    for n, y in enumerate(_DESK_YS):
        piles += [
            _floor("p7_office_paper_stack_sml", _DESK_X - 20.0, y + 30.0, fz, 15.0 * n,
                   solid=False),
            _floor("p7_book_office_binder_open", _DESK_X + 4.0, y + 32.0, fz, 90.0 + 20.0 * n,
                   solid=False),
        ]
    ctx.put(piles, VIGNETTES["desk_piles"])
    ctx.put([
        _floor("p7_office_paper_sheet_12", face_x - 10.0 - 6.0 * (i % 2), c[n] + dy, fz,
               37.0 * i, solid=False)
        for i, (n, dy) in enumerate(((0, -18.0), (0, 20.0), (1, -24.0), (1, 12.0),
                                     (3, -20.0), (5, 22.0), (6, -14.0), (7, 16.0)))
    ], VIGNETTES["uncalled"])


VIGNETTES.update({"desk_piles": "dense_windows_desk_piles",
                  "uncalled": "dense_windows_uncalled"})
