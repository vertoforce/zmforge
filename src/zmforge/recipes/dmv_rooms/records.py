"""zm_dmv dense pass: the records room (key ``records``).  See the package docstring.

The secure store, where the paperwork survived and the survivor is losing.
Every flat top in the room carries files; the man living by the east shelves
has dug in; somebody at the old request desk is still pretending to look
things up.  The walk from the west door to the east one (``y`` -40 to 40)
stays open down the middle, as do Speed Cola's front (north), the box's
front (south) and the riser (north-centre).

Vignettes (ids ``dense_records_<name>``):

``cabinet_tops``  files, folders and copy paper along the west cabinets
``shelf_tops``    archive boxes stacked on the four east shelving units
``filing``        paper left on the two pairs of filing cabinets
``request``       the records-request desk in the south-west corner
``camp``          the survivor's camp, grown: bottles, a pot, a diary, sandbags
``unclaimed``     unclaimed property in the south-east corner, by the box
``speed_corner``  a bin by Speed Cola and the cups that missed it
``latrine``       a toilet behind a drape in the north-west corner
``stacks``        the aisle boxes, stacked a box higher
``walls``         signage, a notice board, a staff picture
``floor``         paper drifts where the aisle boxes are
"""
from __future__ import annotations

from ._kit import (
    Facing,
    Point,
    RoomContext,
    _floor,
    _mounted,
    _on,
    _rest_on,
    _seated,
    _top_of,
    shelf_boards,
)

NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "records_request": (
        "RECORDS REQUEST: hold ^3[{+activate}]^7 to request your file",
        (
            "Your file has been located.",
            "Your file has been misfiled under Z.",
            "Your file is currently in use by customer 846.",
        ),
    ),
    "records_unclaimed": (
        "UNCLAIMED PROPERTY: hold ^3[{+activate}]^7 to claim an item",
        (
            "Please describe the item.",
            "That item is not in our records.",
            "Unclaimed items are disposed of in the box. 950 points per viewing.",
        ),
    ),
    "records_occupied": (
        "OCCUPIED -- hold ^3[{+activate}]^7 to knock",
        (
            "Still occupied.",
            "Please take a number.",
        ),
    ),
}

CABINET = "p7_zm_der_cabinet_lab_bottom"
SHELF = "p7_shelf_metal_lab_01"
FILE_CAB = "p7_file_cab_metal_02"
BOX = "p7_container_cardboard_box_01"
DESK = "p7_desk_metal_old_01_body"
CRATE = "p7_crate_wood_01_short_open"


def _desk(ctx: RoomContext) -> tuple[float, float]:
    """The request desk's centre: its back on the south wall, just east of
    the south-west cabinet (whose east face is 32 off the west wall)."""
    r_in = ctx.room.interior
    return r_in.mins.x + 76.0, r_in.mins.y + 19.0


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """The request desk (in front of it, east of the chair), the unclaimed
    pile (north-west of it, clear of the box) and the latrine drape."""
    r_in, rz = ctx.room.interior, ctx.room.floor_z
    return [
        ("records_request", Point(r_in.mins.x + 129.0, r_in.mins.y + 64.0, rz)),
        ("records_unclaimed", Point(r_in.maxs.x - 114.0, r_in.mins.y + 74.0, rz)),
        ("records_occupied", Point(r_in.mins.x + 84.0, r_in.maxs.y - 84.0, rz)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the records room."""
    r_in, rz = ctx.room.interior, ctx.room.floor_z
    west, east = r_in.mins.x, r_in.maxs.x
    south, north = r_in.mins.y, r_in.maxs.y

    # ---- files along the west cabinets ----------------------------------
    # Six cabinets 108 long, centred on y = +-110, +-218, +-326; the
    # lived-in pass put one thing on the middle of each, so these go 36 to
    # either side of it.
    cab_x = west + 16.0
    cab_top = _top_of(CABINET, rz)
    ctx.put([
        _on(model, cab_x, y, cab_top, yaw)
        for model, y, yaw in (
            ("p7_office_paper_folder_pink", -290.0, 5.0),
            ("p7_books_office_row_01", -362.0, 90.0),
            ("p7_box_copy_paper_sheet", -254.0, 0.0),
            ("p7_office_paper_stack_sml", -190.0, 0.0),
            ("p7_box_copy_paper_sheet", 215.0, 10.0),
            ("p7_office_paper_folder_blue", 300.0, 350.0),
            ("p7_book_office_binder_open", 182.0, 8.0),
            ("p7_books_office_row_01", 254.0, 90.0),
        )
    ], "dense_records_cabinet_tops")

    # ---- archive boxes on top of the east shelving ----------------------
    shelf_top = shelf_boards(SHELF, rz)[-1]  # the top board, under the posts
    shelf_x = east - 17.0
    # No shelves either side of the east door (they would stand inside
    # the doorway's 48); their boxes are stacked a
    # second high on the two that are left.
    box_on_box = _top_of(BOX, shelf_top)
    ctx.put([
        _on(BOX, shelf_x, y + dy, top, 90.0 + tilt)
        for y, dy, tilt, top in (
            (-230.0, -28.0, 0.0, shelf_top), (-230.0, 28.0, 3.0, shelf_top),
            (-230.0, -28.0, 358.0, box_on_box),
            (230.0, 28.0, 0.0, box_on_box),
            (230.0, -28.0, 2.0, shelf_top), (230.0, 28.0, 0.0, shelf_top),
        )
    ], "dense_records_shelf_tops")

    # ---- paper on the two pairs of filing cabinets ----------------------
    fc_top = _top_of(FILE_CAB, rz)
    fc_x = east - 16.0
    ctx.put([
        # On one cabinet each, not on the one-unit seam between a pair: at
        # y 320 they float 65 over the floor.
        _on("p7_office_paper_stack_sml", fc_x, 310.0, fc_top, 5.0),
        _on("p7_book_office_binder_open", fc_x, -310.0, fc_top, 0.0),
    ], "dense_records_filing")

    # ---- the records-request desk, south-west ---------------------------
    dx, dy = _desk(ctx)
    d_top = _top_of(DESK, rz)
    ctx.put([
        _floor(DESK, dx, dy, rz, 0.0),
        # Monitor at the back of the desk, keyboard in front of it.
        _on("p7_consumer_grade_monitor_medium", dx, dy - 10.0, d_top, 180.0),
        _on("p7_keyboard_metal_tech", dx - 8.0, dy + 7.0, d_top, 0.0, scale=0.8),
        _on("p7_cup_coffee_mug", dx + 30.0, dy + 8.0, d_top, 200.0),
        _floor("p7_desk_metal_old_01_drawer_small_01", dx + 54.0, dy - 5.0, rz, 20.0,
               solid=False),
        _seated("p7_chair_lab_01", Point(dx - 12.0, dy + 42.0, _rest_on("p7_chair_lab_01", rz)),
                Facing.SOUTH),
    ], "dense_records_request")

    # ---- the camp by the east shelves, grown ----------------------------
    # The bed is at (east - 74, 110), its pillow north; the open crate at
    # (bed - 70, 150).
    bed_x, bed_y = east - 74.0, 110.0
    crate_x, crate_y = bed_x - 70.0, 150.0
    c_top = _top_of(CRATE, rz)
    ctx.put([
        # A low wall of sandbags across the bed's head.
        _floor("p7_sandbag_02", bed_x - 10.0, bed_y + 62.0, rz, 90.0, solid=False),
        # Water, on the crate he uses as a table.
        _on("p7_bottle_plastic_16oz_water", crate_x - 12.0, crate_y + 12.0, c_top, 0.0),
        _on("p7_bottle_plastic_16oz_water", crate_x + 12.0, crate_y + 12.0, c_top, 0.0),
        # Dinner, cold, beside it.
        _floor("p7_pot_metal_boiling_lg", crate_x - 30.0, crate_y, rz, 30.0, solid=False),
        # His diary, open by the bed.
        _floor("p7_book_vintage_open_01", bed_x - 38.0, bed_y + 30.0, rz, 5.0, solid=False),
        # Laundry.
        _floor("p7_debris_clothing_piles_01", crate_x - 35.0, bed_y - 10.0, rz, 0.0,
               solid=False),
        _floor("p7_food_fruit_banana_bunch", crate_x - 30.0, crate_y + 22.0, rz, 60.0,
               solid=False),
    ], "dense_records_camp")

    # ---- unclaimed property, south-east ---------------------------------
    ctx.put([
        _floor("p7_luggage_cloth_a_lg_green", east - 99.0, south + 12.0, rz, 0.0),
        _floor("p7_luggage_hardshell_handle_down_white", east - 74.0, south + 10.0, rz, 0.0),
        # zmf_prop_* kit models must be placed solid (Z21 at commit).
        _on("p7_zm_teddybear", east - 74.0, south + 10.0,
            _top_of("p7_luggage_hardshell_handle_down_white", rz), 350.0)[:4] + (True,),
        _floor(CRATE, east - 46.0, south + 18.0, rz, 0.0),
        _on("p7_book_office_binder_open", east - 46.0, south + 18.0, c_top, 15.0),
    ], "dense_records_unclaimed")

    # ---- Speed Cola's east side: the bin and the cups that missed -------
    ctx.put([
        _floor("p7_trashcan_metal_modern_glass", east - 44.0, north - 18.0, rz, 0.0),
        _floor("p7_debris_trash_cup_red_02", east - 54.0, north - 44.0, rz, 0.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", east - 70.0, north - 38.0, rz, 90.0, solid=False),
    ], "dense_records_speed_corner")

    # ---- the latrine, north-west: a toilet behind a drape ---------------
    ctx.put([
        _floor("zmf_prop_toilet", west + 54.0, north - 16.0, rz, 0.0),
        _floor("p7_make_shift_drape_cloth_03", west + 54.0, north - 54.0, rz, 0.0),
        _floor("p7_cleaning_paper_towel", west + 84.0, north - 12.0, rz, 20.0, solid=False),
    ], "dense_records_latrine")

    # ---- the aisle boxes, a box higher ----------------------------------
    # The archive pass's boxes stand at these origins (not footprint
    # centres) and yaws; a second box on the same origin and yaw sits
    # squarely on the first.
    box_top = _top_of(BOX, rz)
    box_z = _rest_on(BOX, box_top)
    ctx.put([
        (BOX, Point(26.0, -120.0, box_z), 0.0, 1.0, False),
        (BOX, Point(137.0, 149.0, box_z), 213.0, 1.0, False),
        (BOX, Point(78.0, -178.0, box_z), 66.0, 1.0, False),
    ], "dense_records_stacks")

    # ---- the walls ------------------------------------------------------
    ctx.put([
        _mounted("p7_zm_der_signage_employees_only", Point(west + 3.0, 48.0, rz + 100.0),
                 Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(west + 150.0, south + 2.0, rz + 110.0),
                 Facing.NORTH),
        _mounted("p7_zm_der2_bulletin_board", Point(west + 74.0, north - 3.0, rz + 96.0),
                 Facing.SOUTH),
        _mounted("p7_signage_caution_warning_01", Point(200.0, north - 3.0, rz + 100.0),
                 Facing.SOUTH),
    ], "dense_records_walls")

    # ---- paper drifts ---------------------------------------------------
    ctx.put([
        _floor(model, x, y, rz, yaw, solid=False)
        for model, x, y, yaw in (
            ("p7_debris_paper_sheet_01", 60.0, 250.0, 30.0),
            ("p7_office_paper_sheet_12", 150.0, 60.0, 80.0),
            ("p7_debris_newspaper_05", 230.0, -160.0, 115.0),
        )
    ], "dense_records_floor")

    # ---- the two cabinets that stood by the counter door ----------------
    # They crowded the doorway (16 units off the
    # jamb) and are gone; what was in them is on the floor where they stood,
    # all of it flat enough to walk through.
    ctx.put([
        _floor(model, west + dx, y, rz, yaw, solid=False)
        for model, dx, y, yaw in (
            ("p7_office_paper_stack_sml", 18.0, 104.0, 20.0),
            ("p7_book_office_binder_open", 30.0, 128.0, 300.0),
            ("p7_office_paper_folder_pink", 20.0, 150.0, 75.0),
            ("p7_office_paper_stack_sml", 18.0, -104.0, 340.0),
            ("p7_office_paper_folder_blue", 28.0, -130.0, 12.0),
            ("p7_book_office_binder_open", 22.0, -152.0, 95.0),
        )
    ], "dense_records_emptied")

    _records_dense2(ctx)
    _records_shelf_boards(ctx)


# ==========================================================================
# Dense pass 2: far more props, so the room reads as a DMV
# ==========================================================================
# The archive filled to the ceiling: every top in the room stacked, the
# shelves' floor level stuffed, two more filing cabinets, a supply stash,
# spills round every aisle box and a paper trail over the whole floor.
# Solids only against a wall; everything out on the floor is flat and walked
# through.  The helpers here are shared with the office and the break room.
#
# New vignettes (ids ``dense_records_<name>``): ``shelf_stacks``,
# ``under_shelves``, ``file_cabinets``, ``cabinet_rows``, ``west_floor``,
# ``request_kit``, ``aisle_spills``, ``camp_stash``, ``unclaimed_pile``,
# ``wall_dressing``, ``paper_trail``.
import math as _math

from ...blueprint.elements import PropScatter as _PropScatter
from ...placement.relations import Placed as _Placed
from ._kit import _centred, collision_box as _collision_box


def _aabb(item: tuple) -> tuple[float, float, float, float, float, float]:
    """World box ``(x0, y0, z0, x1, y1, z1)`` of a placement tuple."""
    model, at, yaw = item[0], item[1], item[2]
    scale = item[3] if len(item) > 3 else 1.0
    p = _Placed.from_model(model, _collision_box(model), (at.x, at.y, at.z), yaw, scale)
    c, s = abs(_math.cos(_math.radians(yaw))), abs(_math.sin(_math.radians(yaw)))
    ex, ey = c * p.hx + s * p.hy, s * p.hx + c * p.hy
    return (p.x - ex, p.y - ey, p.z_low, p.x + ex, p.y + ey, p.z_high)


def _hits(a, b, pad: float = 0.5) -> bool:
    return all(min(a[k + 3], b[k + 3]) - max(a[k], b[k]) > pad for k in range(3))


def _room_boxes(ctx: RoomContext) -> list:
    """The world box of every prop already standing in this room."""
    r_in = ctx.room.interior
    boxes = []
    for scatter in ctx.bp.elements(_PropScatter):
        for p in scatter.props:
            box = _aabb((p.model, p.origin, p.yaw, p.scale))
            cx, cy = (box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0
            if (r_in.mins.x - 4.0 <= cx <= r_in.maxs.x + 4.0
                    and r_in.mins.y - 4.0 <= cy <= r_in.maxs.y + 4.0):
                boxes.append(box)
    return boxes


def _put_clear(ctx: RoomContext, items: list[tuple], ident: str,
               keep_out: tuple[tuple[float, float, float], ...] = ()) -> None:
    """Place those of *items* that stay inside the room (8 off every wall),
    touch nothing already in it nor each other, and keep out of every
    ``(x, y, radius)`` in *keep_out*: litter that can never land in a desk,
    on a use spot or through a wall, whatever else moves."""
    r_in = ctx.room.interior
    taken = _room_boxes(ctx)
    kept = []
    for item in items:
        box = _aabb(item)
        cx, cy = (box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0
        if (box[0] < r_in.mins.x + 8.0 or box[1] < r_in.mins.y + 8.0
                or box[3] > r_in.maxs.x - 8.0 or box[4] > r_in.maxs.y - 8.0):
            continue
        if any(_math.hypot(cx - x, cy - y) < r for x, y, r in keep_out):
            continue
        if any(_hits(box, other) for other in taken):
            continue
        taken.append(box)
        kept.append(item)
    ctx.put(kept, ident)


def _book_row(x: float, y0: float, top: float, count: int, yaw: float = 0.0,
              step_axis: str = "y") -> list[tuple]:
    """*count* office books standing spine-out side by side from *y0* (or
    *x0*), each advanced by its own thickness."""
    books = ("p7_book_office_lrg_red", "p7_book_office_med_brown",
             "p7_book_office_sml_beige", "p7_book_office_med_brown")
    thick = {"p7_book_office_lrg_red": 3.0, "p7_book_office_med_brown": 2.0,
             "p7_book_office_sml_beige": 1.0}
    out, at = [], y0
    for i in range(count):
        model = books[i % len(books)]
        at += thick[model] / 2.0 + 0.3
        px, py = (x, at) if step_axis == "y" else (at, x)
        out.append(_on(model, px, py, top, yaw))
        at += thick[model] / 2.0 + 0.3
    return out


#: Paper that lies flat enough to walk through, for spills and trails.
_FLAT = ("p7_office_paper_sheet_01", "p7_office_paper_sheet_08", "p7_office_paper_folder_blue",
         "p7_office_paper_sheet_12", "p7_book_office_binder_open", "p7_office_paper_sheet_03",
         "p7_office_paper_folder_pink", "p7_office_paper_sheet_10", "p7_debris_trash_paper_03",
         "p7_office_paper_sheet_02", "p7_book_vintage_open_04", "p7_office_paper_stack_sml",
         "p7_debris_trash_paper_09", "p7_office_paper_sheet_09")


def _trail(x0: float, y0: float, x1: float, y1: float, count: int, seed: int,
           floor_z: float, models: tuple[str, ...] = _FLAT) -> list[tuple]:
    """*count* flat, walk-through pieces spread over a rectangle on a
    jittered grid (deterministic: the same map every build)."""
    cols = max(1, round(_math.sqrt(count * (x1 - x0) / max(1.0, y1 - y0))))
    rows = max(1, -(-count // cols))
    out = []
    for i in range(count):
        cx, cy = i % cols, i // cols
        h = (i * 7919 + seed * 104729) % 9973
        jx, jy = (h % 97) / 97.0, ((h // 97) % 89) / 89.0
        x = x0 + (cx + 0.15 + 0.7 * jx) * (x1 - x0) / cols
        y = y0 + (cy + 0.15 + 0.7 * jy) * (y1 - y0) / rows
        model = models[(i + seed) % len(models)]
        out.append(_floor(model, x, y, floor_z, float((h * 37) % 360), solid=False))
    return out


def _records_dense2(ctx: RoomContext) -> None:
    """The second dense pass: the archive, filled."""
    r_in, rz = ctx.room.interior, ctx.room.floor_z
    west, east = r_in.mins.x, r_in.maxs.x
    south, north = r_in.mins.y, r_in.maxs.y

    # ---- the east shelving, boxed to the lamps ---------------------------
    # Two columns of archive boxes on each unit (y +-28 off its centre); the
    # outer column is two high and the inner one, so both go up two more,
    # books stand in the gap between the columns and on the ends.
    shelf_top = shelf_boards(SHELF, rz)[-1]  # the top board, under the posts
    sx = east - 17.0
    lv = [shelf_top]
    for _ in range(4):
        lv.append(_top_of(BOX, lv[-1]))
    stacks: list[tuple] = []
    for sign in (-1.0, 1.0):
        ys = sign * 230.0
        outer, inner = ys + sign * 28.0, ys - sign * 28.0
        stacks += [
            _on(BOX, sx, outer, lv[2], 92.0), _on(BOX, sx, outer, lv[3], 88.0),
            _on(BOX, sx, inner, lv[1], 91.0), _on(BOX, sx, inner, lv[2], 87.0),
            _on("p7_office_paper_stack_sml", sx, outer, lv[4], 80.0 + sign * 10.0),
            _on("p7_books_office_row_01", sx - 4.0, inner - sign * 8.0, lv[3], 90.0),
            _on("p7_book_office_binder_open", sx, inner + sign * 10.0, lv[3], 90.0),
        ]
        stacks += _book_row(sx, ys - 7.5, shelf_top, 5)
        stacks += _book_row(sx, -286.2 if sign < 0 else 278.0, shelf_top, 3)
    ctx.put(stacks, "dense_records_shelf_stacks")

    # ---- under the shelves' bottom board: flat files, 9 high at most -----
    under: list[tuple] = []
    for ys in (-230.0, 230.0):
        for dy, model, yaw in ((-40.0, "p7_office_paper_stack_sml", 0.0),
                               (-14.0, "p7_box_wood_wine_storage", 0.0),
                               (13.0, "p7_book_office_binder_open", 90.0),
                               (40.0, "p7_office_paper_stack_sml", 180.0)):
            under.append(_floor(model, sx, ys + dy, rz, yaw, solid=False))
        under.append(_on("p7_office_paper_folder_blue", sx, ys - 40.0,
                         _top_of("p7_office_paper_stack_sml", rz), 10.0))
        under.append(_on("p7_book_vintage_05", sx - 2.0, ys + 13.0,
                         _top_of("p7_book_office_binder_open", rz), 80.0))
    ctx.put(under, "dense_records_under_shelves")

    # ---- two more filing cabinets in the south-east corner, and drawers --
    fc_top = _top_of(FILE_CAB, rz)
    fx = east - 16.0
    ctx.put([
        _floor(FILE_CAB, fx, -350.0, rz, 270.0),
        _floor(FILE_CAB, fx, -370.0, rz, 270.0),
        _on("p7_books_office_row_01", fx, -366.0, fc_top, 90.0),
        _on("p7_office_paper_stack_sml", fx, -350.0, fc_top, 85.0),
        _on("p7_office_paper_folder_pink", fx - 1.0, -350.0,
            _top_of("p7_office_paper_stack_sml", fc_top), 20.0),
        _on("p7_books_office_row_01", fx, 332.0, fc_top, 90.0),
        _on("p7_office_paper_folder_blue", fx, 310.0,
            _top_of("p7_office_paper_stack_sml", fc_top), 340.0),
        _on("p7_books_office_row_01", fx, -333.0, fc_top, 90.0),
        _on("p7_office_paper_stack_sml", fx, -310.0,
            _top_of("p7_book_office_binder_open", fc_top), 95.0),
        # Drawers yanked out and dumped in front of each pair.
        _floor("p7_file_cab_metal_02_drawer_02", east - 58.0, 326.0, rz, 75.0, solid=False),
        _floor("p7_file_cab_metal_02_drawer_02", east - 60.0, -326.0, rz, 105.0,
               solid=False),
        _floor("p7_office_paper_sheet_08", east - 80.0, 318.0, rz, 20.0, solid=False),
        _floor("p7_office_paper_folder_blue", east - 84.0, 300.0, rz, 130.0, solid=False),
        _floor("p7_office_paper_sheet_01", east - 40.0, -318.0, rz, 200.0, solid=False),
        _floor("p7_office_paper_folder_pink", east - 86.0, -318.0, rz, 60.0, solid=False),
        _floor("p7_book_office_binder_open", east - 62.0, -262.0, rz, 150.0, solid=False),
    ], "dense_records_file_cabinets")

    # ---- the west cabinet run: every gap on top filled --------------------
    cab_x = west + 16.0
    cab_top = _top_of(CABINET, rz)
    box_on_cab = _top_of(BOX, cab_top)
    rows: list[tuple] = []
    rows += _book_row(cab_x, -355.0, cab_top, 5)
    rows += _book_row(cab_x, 229.0, cab_top, 6)
    rows += _book_row(cab_x, -179.0, cab_top, 4)
    rows += [
        _on("p7_books_office_row_01", cab_x, -305.0, cab_top, 90.0),
        _on("p7_books_office_row_01", cab_x, -273.0, cab_top, 90.0),
        _on("p7_office_paper_stack_sml", cab_x, 272.0, cab_top, 5.0),
        _on("p7_books_office_row_01", cab_x, 288.0, cab_top, 90.0),
        _on("p7_books_office_row_01", cab_x, 356.0, cab_top, 90.0),
        _on("p7_office_paper_stack_sml", cab_x, 372.0, cab_top, 80.0),
        # The two boxes the lived-in pass left up there, a box higher.
        _on(BOX, cab_x + 2.0, 326.0, box_on_cab, 88.0),
        _on("p7_office_paper_stack_sml", cab_x + 2.0, 326.0, _top_of(BOX, box_on_cab), 15.0),
        _on("p7_book_office_binder_open", cab_x + 1.0, -218.0, box_on_cab, 2.0),
    ]
    ctx.put(rows, "dense_records_cabinet_rows")

    # ---- the floor either side of the west door, where two cabinets were --
    _put_clear(ctx, _trail(west + 10.0, 50.0, west + 50.0, 160.0, 7, 3, rz)
               + _trail(west + 10.0, -160.0, west + 50.0, -50.0, 7, 5, rz),
               "dense_records_west_floor")

    # ---- the request desk: the rest of the kit, and the forms it ran on --
    dx, dy = _desk(ctx)
    d_top = _top_of(DESK, rz)
    b_top = _top_of(BOX, rz)
    ctx.put([
        _on("p7_debris_trash_cup_coffee_02", dx + 33.0, dy - 8.0, d_top, 0.0),
        # Forms boxes against the south wall, east of the desk's drawer.
        _floor(BOX, west + 164.0, south + 16.0, rz, 0.0),
        _centred(BOX, west + 164.0, south + 16.0, _rest_on(BOX, b_top), 3.0, solid=True),
        _on("p7_office_paper_stack_sml", west + 154.0, south + 16.0, _top_of(BOX, b_top), 80.0),
        _on("p7_book_office_binder_open", west + 176.0, south + 16.0, _top_of(BOX, b_top), 5.0),
        _floor("p7_office_paper_stack_sml", west + 164.0, south + 50.0, rz, 30.0, solid=False),
    ], "dense_records_request_kit")

    # ---- the aisle boxes: what spilled out, and what is piled on them ----
    # The archive pass's four floor boxes, by origin and yaw.
    aisle = ((26.0, -120.0, 0.0), (137.0, 149.0, 213.0), (78.0, -178.0, 66.0),
             (189.0, 207.0, 279.0))
    box_z = _rest_on(BOX, b_top)
    tops = [(BOX, Point(189.0, 207.0, box_z), 279.0, 1.0, False)]
    two_high = _top_of(BOX, b_top)
    for (ox, oy, _yaw), model in zip(aisle[:3], ("p7_office_paper_stack_sml",
                                                 "p7_book_office_binder_open",
                                                 "p7_books_office_row_01")):
        tops.append(_centred(model, ox + 3.0, oy - 2.0, _rest_on(model, two_high), 30.0))
    ctx.put(tops, "dense_records_aisle_tops")
    spill: list[tuple] = []
    for i, (ox, oy, _yaw) in enumerate(aisle):
        spill += _trail(ox - 55.0, oy - 50.0, ox + 55.0, oy + 50.0, 7, 11 + i, rz)
    _put_clear(ctx, spill, "dense_records_aisle_spills", keep_out=_RECORDS_KEEP_OUT)

    # ---- the survivor's stash: boxes against the wall behind the bed -----
    # Clear of the east door's 48-unit band (dmv._clear_door_bands drops a
    # solid inside it), so the stack starts 90 north of the door's centre.
    stash_x = east - 20.0
    ctx.put([
        _floor(BOX, stash_x, 108.0, rz, 90.0),
        _floor(BOX, stash_x, 148.0, rz, 90.0),
        _centred(BOX, stash_x, 120.0, _rest_on(BOX, b_top), 92.0, solid=True),
        _on("p7_bottle_plastic_16oz_water", stash_x - 4.0, 120.0, _top_of(BOX, b_top), 0.0),
        _on("p7_bottle_plastic_16oz_water", stash_x + 3.0, 124.0, _top_of(BOX, b_top), 0.0),
        _on("p7_bottle_plastic_16oz_water", stash_x - 2.0, 130.0, _top_of(BOX, b_top), 0.0),
        _on("p7_zm_der2_light_hurricane_lamp", stash_x + 2.0, 138.0, _top_of(BOX, b_top), 0.0),
        _on("p7_food_fruit_melon", stash_x, 101.0, b_top, 0.0),
        _on("p7_book_vintage_01", stash_x + 2.0, 158.0, b_top, 20.0),
        _on("p7_book_vintage_03", stash_x + 2.0, 158.0, _top_of("p7_book_vintage_01", b_top),
            50.0),
        _floor("p7_debris_clothing_tshirts_02", 262.0, 92.0, rz, 40.0, solid=False),
        _floor("p7_cup_coffee_mug", 272.0, 118.0, rz, 120.0, solid=False),
        _floor("p7_pan_metal_lid", 222.0, 176.0, rz, 0.0, solid=False),
        _floor("p7_book_vintage_05", 258.0, 176.0, rz, 15.0, solid=False),
        _on("p7_cup_coffee_mug", 254.0, 142.0, _top_of(CRATE, rz), 40.0),
    ], "dense_records_camp_stash")

    # ---- unclaimed property: what fell off the pile ----------------------
    lug_top = _top_of("p7_luggage_cloth_a_lg_green", rz)
    ctx.put([
        _floor("p7_debris_clothing_dress_01", east - 94.0, south + 39.0, rz, 20.0, solid=False),
        _floor("p7_clothes_womens_crumpled_01_shirt", east - 126.0, south + 46.0, rz, 0.0,
               solid=False),
        _floor("p7_bag_plastic_soil", east - 122.0, south + 14.0, rz, 90.0, solid=False),
        _on("p7_debris_clothing_tshirts_01", east - 99.0, south + 16.0, lug_top, 10.0),
        _on("p7_office_paper_stack_sml", east - 46.0, south + 18.0,
            _top_of("p7_book_office_binder_open", _top_of(CRATE, rz)), 15.0),
    ], "dense_records_unclaimed_pile")

    # ---- the walls: exits, boards, frames, a clock -----------------------
    exit_sign = "p7_cai_signage_plastic_exit"
    ctx.put([
        _mounted(exit_sign, Point(west + 1.3, 0.0, rz + 126.0), Facing.EAST),
        _mounted(exit_sign, Point(east - 1.3, 0.0, rz + 126.0), Facing.WEST),
        _mounted(exit_sign, Point(110.0, north - 1.3, rz + 142.0), Facing.SOUTH),
        # West wall, over the cabinet run.
        _mounted("p7_picture_frame_modern_01", Point(west + 1.0, -335.0, rz + 92.0),
                 Facing.EAST),
        _mounted("p7_zm_der2_bulletin_board", Point(west + 3.0, -250.0, rz + 96.0),
                 Facing.EAST),
        _mounted("p7_picture_frame_modern_01", Point(west + 1.0, 200.0, rz + 100.0),
                 Facing.EAST),
        _mounted("p7_zm_der2_poster_anatomy_02", Point(west + 0.5, 250.0, rz + 96.0),
                 Facing.EAST),
        _mounted("p7_clock_metal_wall_01_base", Point(west + 3.0, 330.0, rz + 126.0),
                 Facing.EAST),
        # East wall, between the south shelves and the door, and over the bed.
        _mounted("p7_zm_der2_bulletin_board", Point(east - 3.0, -112.0, rz + 90.0),
                 Facing.WEST),
        _mounted("p7_signage_caution_warning_01", Point(east - 1.0, -62.0, rz + 86.0),
                 Facing.WEST),
        _mounted("p7_picture_frame_modern_01", Point(east - 1.0, 110.0, rz + 100.0),
                 Facing.WEST),
        # North and south walls.
        _mounted("p7_picture_frame_modern_01", Point(345.0, north - 1.0, rz + 96.0),
                 Facing.SOUTH),
        _mounted("p7_clock_metal_wall_01_base", Point(-8.0, south + 3.0, rz + 124.0),
                 Facing.NORTH),
        _mounted("p7_signage_caution_warning_01", Point(115.0, south + 1.0, rz + 94.0),
                 Facing.NORTH),
        _mounted("p7_picture_frame_modern_01", Point(320.0, south + 1.0, rz + 94.0),
                 Facing.NORTH),
    ], "dense_records_wall_dressing")

    # ---- the paper trail over the whole floor ----------------------------
    _put_clear(ctx, _trail(west + 50.0, south + 40.0, east - 50.0, north - 40.0, 48, 29, rz),
               "dense_records_paper_trail", keep_out=_RECORDS_KEEP_OUT)


#: Use spots the litter stays off: the box and Speed Cola fronts, the three
#: notices and the riser.
_RECORDS_KEEP_OUT = ((190.0, -300.0, 55.0), (270.0, 300.0, 55.0), (45.0, -320.0, 30.0),
                     (270.0, -310.0, 30.0), (0.0, 300.0, 30.0), (150.0, 336.0, 30.0))


# --------------------------------------------------------------------------
# Inside the shelving: the boards between the floor and the top
# --------------------------------------------------------------------------
# Until props.SHELF_BOARDS the layout check only knew a shelving unit's box
# top, so everything went on top and the boards in between stood empty.  The
# fillers below walk each inner board end to end and set down whatever fits
# under the board above it: archive boxes, paper stacks, piles of binders and
# folders, flat books.  All walk-through (clutter on a solid unit), and every
# piece is dropped if it would cut into a prop already there.  Shared with the
# office.  New vignette ids ``dense_<key>_shelf_boards``.

#: Room under the next board: a board is under 1 thick (the top faces of
#: each pair of stacked meshes are 0.69 apart) and a box wants a hand's gap.
_BOARD_ROOM = 1.5


def _board_groups(c: float, s: float, z: float, yaw: float, axis: str
                  ) -> dict[str, tuple[float, float, list[tuple]]]:
    """Everything one board spot can hold, keyed by kind: ``(width along the
    run, height, the pieces)`` with the group's run-wise centre at *s* and its
    depth-wise centre at *c*."""
    def at(model: str, top: float, turn: float = 0.0, ds: float = 0.0,
           dc: float = 0.0) -> tuple:
        x, y = (c + dc, s + ds) if axis == "y" else (s + ds, c + dc)
        return _on(model, x, y, top, (yaw + turn) % 360.0)

    stack, wine, binder = ("p7_office_paper_stack_sml", "p7_box_wood_wine_storage",
                           "p7_book_office_binder_open")
    b1 = _top_of(binder, z)
    b2 = _top_of(binder, b1)
    v1 = _top_of("p7_book_vintage_02", z)
    v2 = _top_of("p7_book_vintage_05", v1)
    return {
        "wine": (18.0, 8.7, [at(wine, z, 1.0),
                             at("p7_office_paper_folder_blue", _top_of(wine, z), 6.0)]),
        "wine_tan": (18.0, 8.5, [at("p7_box_wood_wine_storage_tan", z, 358.0)]),
        "paper": (15.7, 5.5, [at(stack, z, 2.0),
                              at("p7_office_paper_folder_pink", _top_of(stack, z), 350.0)]),
        "paper2": (15.7, 10.6, [at(stack, z, 0.0), at(stack, _top_of(stack, z), 4.0)]),
        # (not in _BOARD_ORDER: a blue-only group, for a shelf where a pink
        # folder would read as a quest item)
        "paper_blue": (15.7, 5.5, [at(stack, z, 358.0),
                                   at("p7_office_paper_folder_blue", _top_of(stack, z), 8.0)]),
        "binders": (14.0, 3.9, [at(binder, z, 0.0), at(binder, b1, 3.0),
                                at(binder, b2, 357.0)]),
        "books": (11.4, 7.4, [at("p7_book_vintage_02", z, 0.0),
                              at("p7_book_vintage_05", v1, 5.0),
                              at("p7_book_vintage_03", v2, 350.0)]),
        "sheets": (15.7, 3.2, [at("p7_office_paper_sheet_08", z, 0.0),
                               at("p7_box_copy_paper_sheet", _top_of("p7_office_paper_sheet_08",
                                                                     z), 90.0)]),
        "row": (12.1, 14.0, [at("p7_books_office_row_01", z, 0.0)]),
        "crate": (14.9, 13.0, [at("p7_box_wood_01_sm", z, 1.0)]),
        "carton": (38.5, 25.3, [at(BOX, z, 0.0)]),
        "carton_paper": (38.5, 25.3 + 5.3, [at(BOX, z, 358.0),
                                            at(stack, _top_of(BOX, z), 20.0)]),
    }


#: The order kinds are tried in along a board (rotated by the board's seed,
#: so no two boards read the same); a kind too tall for the gap is skipped.
_BOARD_ORDER = ("carton", "wine", "paper", "binders", "row", "books", "wine_tan",
                "carton_paper", "sheets", "paper2", "crate", "binders", "paper", "row")


def _fill_board(c: float, s0: float, s1: float, z: float, room: float, seed: int,
                axis: str = "y", empty: float = 0.0,
                order: tuple[str, ...] = _BOARD_ORDER) -> list[tuple]:
    """One board from *s0* to *s1* along *axis*, filled with the groups that
    fit under *room*.  *empty* is the share of spots left bare (a real shelf
    has gaps), picked deterministically from *seed*.  *order* is the kinds
    tried in turn (a subset of :func:`_board_groups`' keys)."""
    yaw = 90.0 if axis == "y" else 0.0
    out: list[tuple] = []
    at, i = s0, 0
    while True:
        kind = order[(seed * 5 + i) % len(order)]
        i += 1
        if i > 4 * len(order):
            break
        width, height, _pieces = _board_groups(c, 0.0, z, yaw, axis)[kind]
        if height > room - _BOARD_ROOM:
            continue
        if at + width + 1.0 > s1:
            if any(w + 1.0 <= s1 - at and h <= room - _BOARD_ROOM
                   for k, (w, h, _) in _board_groups(c, 0.0, z, yaw, axis).items()
                   if k in order):
                continue
            break
        h = (i * 7919 + seed * 104729) % 9973
        if (h % 100) / 100.0 >= empty:
            out += _board_groups(c, at + width / 2.0 + 0.5, z, yaw, axis)[kind][2]
        at += width + 1.0 + (h % 4)
    return out


def _put_on_boards(ctx: RoomContext, items: list[tuple], ident: str) -> None:
    """Place those of *items* that cut into no prop already in the room (the
    shelving units themselves excepted: these are inside them on purpose)
    and into none of each other."""
    from ..props import SHELF_BOARDS

    r_in = ctx.room.interior
    taken = []
    for scatter in ctx.bp.elements(_PropScatter):
        for p in scatter.props:
            if p.model in SHELF_BOARDS:
                continue
            box = _aabb((p.model, p.origin, p.yaw, p.scale))
            cx, cy = (box[0] + box[3]) / 2.0, (box[1] + box[4]) / 2.0
            if (r_in.mins.x - 4.0 <= cx <= r_in.maxs.x + 4.0
                    and r_in.mins.y - 4.0 <= cy <= r_in.maxs.y + 4.0):
                taken.append(box)
    kept = []
    for item in items:
        box = _aabb(item)
        if any(_hits(box, other) for other in taken):
            continue
        taken.append(box)
        kept.append(item)
    ctx.put(kept, ident)


def _shelf_levels(model: str, floor_z: float) -> list[tuple[float, float]]:
    """``(board top, room under the next board)`` for every inner board."""
    boards = shelf_boards(model, floor_z)
    return [(z, boards[k + 1] - z) for k, z in enumerate(boards[:-1])]


def _records_shelf_boards(ctx: RoomContext) -> None:
    """The two east shelving units, every inner board filled with files."""
    rz, east = ctx.room.floor_z, ctx.room.interior.maxs.x
    sx = east - 17.0
    items: list[tuple] = []
    for n, ys in enumerate((-230.0, 230.0)):
        for k, (z, room) in enumerate(_shelf_levels(SHELF, rz)):
            items += _fill_board(sx, ys - 51.0, ys + 51.0, z, room, 3 + 7 * n + k,
                                 empty=0.12)
    _put_on_boards(ctx, items, "dense_records_shelf_boards")
