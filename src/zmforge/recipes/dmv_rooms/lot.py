"""zm_dmv dense pass: the lot room (key ``lot``).  See the package docstring.

Everyone drove here for a 9 AM appointment.  What the dense pass adds to the
car park, keeping the spawn, the drive aisle, the covered walk, the front
door, the risers and the starter pistol clear, and adding no lamp (the lot is
sunlit):

* **the line outside the door** -- a waiting-room chair somebody carried out
  and the luggage queued behind it on the footway north of the canopy, the
  ``lot_line`` quirk at its tail;
* **the parking meter** -- a meter head on each kerb bollard beside the
  accessible bays (``lot_meter``), and in the south accessible bay the
  cinder blocks a towed car left behind (``lot_permit``);
* **the staff bay** -- coned off with two more bollards;
* **the hot-dog cart** -- the vendor's pots, plates and stock round the cart
  already in the far row;
* **the planted bed** -- weeds through the kerb line and a landscaping job
  abandoned with the shovel still on the lawn;
* **the frontage** -- a second sandbag run under the south windows and a
  warning sign on the brick.
"""
from __future__ import annotations

from ._kit import Facing, Point, RoomContext, _floor, _mounted, _on, _top_of

#: The room's quirks (see :func:`zmforge.script.tricks.use_notices`).
NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "lot_permit": ("RESERVED PARKING: hold ^3[{+activate}]^7 to display permit", (
        "Permit expired. Renew inside.",
        "Renewal requires a valid permit.",
        "Your vehicle has been towed. (You do not have a vehicle.)",
    )),
    "lot_meter": ("PARKING: hold ^3[{+activate}]^7 to pay", (
        "Payment accepted. Time remaining: 0 minutes.",
        "This meter only accepts Form 27-B.",
        "Your ticket has been added to your file.",
    )),
    "lot_line": ("THE LINE STARTS HERE -- hold ^3[{+activate}]^7 to join the line", (
        "The line inside starts somewhere else.",
        "Are you in line? Everyone here is in line.",
    )),
}

PYLON = "p7_3arc_park_pylon"
#: The line's x on the footway: between the bench and the north planter.
LINE_DX = 68.0
#: Where the line's chair stands, then each bag behind it, going north.
LINE_YS = (140.0, 182.0, 218.0, 254.0, 292.0)
#: The kerb bollards the meter heads sit on (placed by the lived-in pass).
METER_YS = (-300.0, 300.0)
#: The accessible bay on the south side of the walk: the towed car's.
TOWED_Y = -264.0


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    wx, wt = ctx.walk_x0, ctx.walk_top
    return [
        ("lot_permit", Point(wx - 110.0, TOWED_Y, ctx.room.floor_z)),
        ("lot_meter", Point(wx + 22.0, METER_YS[0], wt)),
        ("lot_line", Point(wx + LINE_DX, LINE_YS[-1] + 60.0, wt)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the lot room."""
    inside = ctx.room.interior
    z = ctx.room.floor_z
    wx, wt = ctx.walk_x0, ctx.walk_top
    fx = inside.maxs.x

    # ---- the line outside the door -------------------------------------
    lx = wx + LINE_DX
    bags = ("p7_luggage_hardshell_handle_down_white", "p7_luggage_cloth_a_lg_green",
            "p7_luggage_cloth_a_lg_green", "p7_luggage_hardshell_handle_down_white")
    ctx.put(
        [_floor("p7_chair_waiting_room_01_blue", lx, LINE_YS[0], wt, 90.0, solid=False)]
        + [_floor(bag, lx + (-3.0, 4.0, -2.0, 3.0)[i], y, wt, (5.0, 350.0, 12.0, 355.0)[i],
                  solid=False)
           for i, (bag, y) in enumerate(zip(bags, LINE_YS[1:]))]
        + [
            _floor("p7_debris_trash_cup_coffee_02", lx + 16.0, LINE_YS[0] + 26.0, wt, 40.0,
                   solid=False),
            _floor("p7_debris_trash_drink_carrier_01", lx - 18.0, LINE_YS[2] + 14.0, wt,
                   15.0, solid=False),
        ],
        "dense_lot_line",
    )

    # ---- the meter heads on the kerb bollards, the towed car -----------
    pylon_top = _top_of(PYLON, wt)
    ctx.put([
        _on("p7_electrical_box_set2_meterhead01", wx + 8.0, METER_YS[0], pylon_top, 90.0),
        _on("p7_electrical_box_set2_meterhead02", wx + 8.0, METER_YS[1], pylon_top, 90.0),
        _floor("p7_cinder_block", wx - 70.0, TOWED_Y - 24.0, z, 90.0, solid=False),
        _floor("p7_cinder_block", wx - 150.0, TOWED_Y + 22.0, z, 85.0, solid=False),
    ], "dense_lot_meter")

    # ---- the staff bay, coned off --------------------------------------
    ctx.put([
        _floor(PYLON, wx - 202.0, y, z, 0.0) for y in (-492.0, -456.0)
    ], "dense_lot_staff_bay")

    # ---- the hot-dog cart's stock --------------------------------------
    cart = Point(-2420.0, 486.0, z)
    crate = "p7_crate_wood_01_short_open"
    ctx.put([
        _floor("p7_pot_metal_boiling_lg", cart.x - 50.0, cart.y + 70.0, z, 20.0, solid=False),
        _floor("p7_pan_metal_lid", cart.x - 26.0, cart.y + 82.0, z, 0.0, solid=False),
        _floor("p7_pan_metal_sauce", cart.x + 25.0, cart.y + 68.0, z, 140.0, solid=False),
        _floor("p7_debris_trash_paper_plate_01", cart.x - 28.0, cart.y - 38.0, z, 0.0,
               solid=False),
        _floor(crate, cart.x - 75.0, cart.y + 114.0, z, 10.0),
        _on("p7_food_fruit_banana_bunch", cart.x - 75.0, cart.y + 114.0,
            _top_of(crate, z), 40.0),
        _floor("p7_debris_trash_drink_carrier_01", cart.x + 90.0, cart.y - 16.0, z, 60.0,
               solid=False),
    ], "dense_lot_cart")

    # ---- the planted bed: weeds, and the landscaping job ---------------
    bed_edge = inside.mins.x + ctx.plan.landscape_depth
    ctx.put([
        _floor("p7_foliage_weed_cluster_lrg", bed_edge - 14.0, -620.0, wt, 90.0, solid=False),
        _floor("p7_foliage_weed_cluster_med", bed_edge - 12.0, 150.0, wt, 90.0, solid=False),
        _floor("p7_foliage_weed_cluster_lrg", bed_edge - 14.0, 560.0, wt, 90.0, solid=False),
        _floor("p7_tools_shovel", bed_edge - 90.0, -560.0, wt, 30.0, solid=False),
        _floor("p7_container_cardboard_box_01", bed_edge - 60.0, -630.0, wt, 12.0),
    ], "dense_lot_bed")

    # ---- the frontage: sandbags under the south windows, a sign --------
    bag = "p7_sandbag_02"
    bag_x = fx - 3.5 - 10.1
    ctx.put(
        [_floor(bag, bag_x, y, wt, 0.0, solid=False) for y in (-396.0, -432.0)]
        + [_on(bag, bag_x, -420.0, _top_of(bag, wt), 0.0)]
        + [_mounted("p7_signage_caution_warning_01", Point(fx - 3.0, -250.0, wt + 96.0),
                    Facing.WEST)],
        "dense_lot_frontage",
    )
    dress_density(ctx)


# --------------------------------------------------------------------------
# The density pass: far more props, so the lot reads as a DMV.
# Everything below is non-solid ground clutter unless it says otherwise, so
# the aisle, the walk, the bays and the risers stay as free as they were.
# --------------------------------------------------------------------------
import random as _random

#: The bays the cars left empty that the pass may use (far row, x span).
_FAR_X0, _FAR_X1 = -2528.0, -2312.0
_NEAR_X0, _NEAR_X1 = -2024.0, -1808.0
LEAVES = ("p7_3arc_park_leaves_grp_2", "p7_3arc_park_leaves_corner_1")
FORMS = ("p7_office_paper_sheet_01", "p7_office_paper_sheet_02", "p7_office_paper_sheet_12",
         "p7_office_paper_sheet_10", "p7_office_paper_sheet_03")
NEWS = ("p7_debris_newspaper_01", "p7_debris_newspaper_04", "p7_debris_newspaper_06",
        "p7_debris_newspaper_08", "p7_zm_debris_newspaper_german_04")
TRASH = ("p7_debris_trash_cup_coffee_02", "p7_debris_trash_cup_red_02",
         "p7_debris_trash_food_box_01", "p7_debris_trash_paper_02",
         "p7_debris_trash_paper_08", "p7_cleaning_paper_ball_brown",
         "p7_debris_trash_paper_plate_01")


def dress_density(ctx: RoomContext) -> None:
    """The density pass: leaves and blown forms everywhere, the
    driving-test course, the forms delivery, the wreck's debris, the bed's
    weeds, the walk's litter and the lot's own signage."""
    rng = _random.Random(4417)
    _leaves(ctx, rng)
    _blown_forms(ctx, rng)
    _driving_test(ctx)
    _forms_delivery(ctx)
    _wreck(ctx, rng)
    _bed_weeds(ctx, rng)
    _walk_litter(ctx, rng)
    _lot_signs(ctx)


def _leaves(ctx: RoomContext, rng) -> None:
    """Leaf drifts against the north and south walls, in the corners, round
    the hedges and in the empty bays."""
    inside, z, wt = ctx.room.interior, ctx.room.floor_z, ctx.walk_top
    n, s = inside.maxs.y - 18.0, inside.mins.y + 18.0
    items = []
    for x in (-2470.0, -2380.0, -2270.0, -2170.0, -2070.0, -1970.0, -1880.0):
        items.append(_floor(LEAVES[0], x + rng.uniform(-12, 12), n, z, rng.choice((0.0, 180.0)),
                            solid=False))
        items.append(_floor(LEAVES[0], x + rng.uniform(-12, 12), s, z, rng.choice((0.0, 180.0)),
                            solid=False))
    for cx, cy, zz in ((inside.mins.x + 12.0, inside.maxs.y - 12.0, wt),
                       (inside.mins.x + 12.0, inside.mins.y + 12.0, wt),
                       (_NEAR_X1 - 14.0, inside.maxs.y - 12.0, z),
                       (_NEAR_X1 - 14.0, inside.mins.y + 12.0, z)):
        items.append(_floor(LEAVES[1], cx, cy, zz, rng.uniform(0, 360), solid=False))
    # Round the hedges (x -2728, 53 x 60) on their east side, and the bays.
    for y in (-576.0, -192.0, 192.0, 576.0):
        items.append(_floor(LEAVES[0], -2680.0, y + rng.uniform(-10, 10), wt, 90.0,
                            solid=False))
    for x, y in ((-2470.0, -60.0), (-2360.0, -380.0), (-2470.0, 400.0), (-1900.0, 250.0),
                 (-1870.0, -470.0), (-2380.0, 620.0)):
        items.append(_floor(LEAVES[0], x, y, z, rng.uniform(0, 360), solid=False))
    ctx.put(items, "dense_lot_leaves")


def _blown_forms(ctx: RoomContext, rng) -> None:
    """Forms, newspapers and cups the wind carried out of the front door and
    across the drive aisle, kept off the spawn."""
    z = ctx.room.floor_z
    starts_y = (-48.0, 48.0)
    spots = [(-2280.0, -620.0), (-2250.0, -520.0), (-2060.0, -600.0), (-2100.0, -470.0),
             (-2230.0, -380.0), (-2050.0, -330.0), (-2270.0, -250.0), (-2080.0, -200.0),
             (-2240.0, -130.0), (-2060.0, -90.0), (-2070.0, 90.0), (-2250.0, 140.0),
             (-2090.0, 220.0), (-2270.0, 300.0), (-2050.0, 360.0), (-2230.0, 420.0),
             (-2100.0, 500.0), (-2280.0, 560.0), (-2060.0, 620.0), (-2180.0, 650.0),
             (-2160.0, -640.0), (-2150.0, 260.0)]
    items = []
    for i, (x, y) in enumerate(spots):
        assert not (abs(x + 2168.0) < 64.0 and starts_y[0] - 64 <= y <= starts_y[1] + 64)
        model = (FORMS, NEWS, TRASH)[i % 3][i % 5]
        items.append(_floor(model, x + rng.uniform(-10, 10), y + rng.uniform(-10, 10), z,
                            rng.uniform(0, 360), solid=False))
        if i % 2 == 0:
            items.append(_floor(rng.choice(FORMS), x + rng.uniform(18, 30),
                                y + rng.uniform(-24, 24), z, rng.uniform(0, 360), solid=False))
    ctx.put(items, "dense_lot_blown_forms")


def _driving_test(ctx: RoomContext) -> None:
    """The road test, abandoned mid-test in the two empty far-row bays: the
    examiner's clipboard sheets and coffee.  (No slalom of ``PYLON``s: the
    model is a grey kerb bollard, not a cone, and a zigzag of them reads as
    random posts in the bays.  The install has no traffic cone.)"""
    z = ctx.room.floor_z
    items = [
        _floor("p7_office_paper_stack_sml", -2360.0, -30.0, z, 15.0, solid=False),
        _floor("p7_office_paper_sheet_12", -2330.0, -80.0, z, 70.0, solid=False),
        _floor("p7_debris_trash_cup_coffee_02", -2350.0, -350.0, z, 0.0, solid=False),
    ]
    ctx.put(items, "dense_lot_driving_test")


def _forms_delivery(ctx: RoomContext) -> None:
    """A pallet of form boxes dropped in bay 19 and never carried in; two
    cartons stand solid on the pallet, the rest are small and loose."""
    z = ctx.room.floor_z
    pallet = "p7_pallet_wood_damaged"
    px, py = -2470.0, 378.0
    pt = _top_of(pallet, z)
    carton = "p7_container_cardboard_box_01"
    ct = _top_of(carton, pt)
    ctx.put([
        _floor(pallet, px, py, z, 0.0, solid=False),
        _on(carton, px - 10.0, py - 5.0, pt, 0.0)[:4] + (True,),
        _on(carton, px + 12.0, py + 8.0, pt, 90.0)[:4] + (True,),
        _on("p7_office_paper_stack_sml", px - 10.0, py - 5.0, ct, 10.0),
        _on("p7_box_copy_paper_sheet", px + 12.0, py + 8.0, ct, 40.0),
        _floor("p7_box_wood_01_sm", px + 50.0, py - 25.0, z, 80.0, solid=False),
        _floor("p7_box_wood_01_long", px + 60.0, py + 22.0, z, 5.0, solid=False),
        _floor("p7_office_paper_sheet_02", px + 88.0, py - 4.0, z, 200.0, solid=False),
        _floor("p7_office_paper_sheet_01", px + 100.0, py + 30.0, z, 120.0, solid=False),
    ], "dense_lot_forms_delivery")


def _wreck(ctx: RoomContext, rng) -> None:
    """The burnt-out car in bay 14: its debris spills into the aisle at its
    head, with its owner's luggage and the paperwork they were bringing."""
    z = ctx.room.floor_z
    head = -2290.0                                 # just past the bay's aisle end
    items = [
        _floor("p7_debris_wood_board_cluster_burn_01", head + 10.0, -150.0, z, 30.0,
               solid=False),
        _floor("p7_debris_wood_board_cluster_burn_03", head + 40.0, -190.0, z, 100.0,
               solid=False),
        _floor("p7_debris_concrete_rubble_sm_06", head, -120.0, z, 0.0, solid=False),
        _floor("p7_debris_concrete_rubble_sm_07", head + 30.0, -110.0, z, 60.0, solid=False),
        _floor("p7_debris_brick_chunk_01", head + 22.0, -170.0, z, 10.0, solid=False),
        _floor("p7_debris_brick_chunk_hlf_01", head + 8.0, -200.0, z, 80.0, solid=False),
        _floor("p7_book_vintage_open_01_burn", head + 60.0, -140.0, z, 200.0, solid=False),
        _floor("p7_debris_newspaper_corner_02", head + 50.0, -215.0, z, 90.0, solid=False),
        _floor("p7_luggage_cloth_a_lg_green", head + 70.0, -175.0, z, 75.0, solid=False),
        _floor("p7_office_paper_folder_blue", head + 85.0, -120.0, z, 30.0, solid=False),
    ]
    ctx.put(items, "dense_lot_wreck")


def _bed_weeds(ctx: RoomContext, rng) -> None:
    """The planted bed gone to seed: weeds along its kerb, tall grass and
    aloes round the hedges, and the landscaper's soil bags by his shovel."""
    wt = ctx.walk_top
    edge = ctx.room.interior.mins.x + ctx.plan.landscape_depth
    weeds = ("p7_foliage_weed_cluster_sml_a", "p7_foliage_weed_cluster_sml_b",
             "p7_foliage_weed_cluster_med")
    items = []
    for i, y in enumerate(range(-600, 640, 80)):
        items.append(_floor(weeds[i % 3], edge - 10.0 - rng.uniform(0, 8), y + rng.uniform(-15, 15),
                            wt, rng.uniform(0, 360), solid=False))
    for y in (-400.0, -40.0, 60.0, 440.0):
        items.append(_floor("p7_foliage_grass_tall_cluster_sml", edge - 60.0, y, wt,
                            rng.uniform(0, 360), solid=False))
    for x, y in ((-2760.0, -470.0), (-2760.0, -300.0), (-2760.0, 300.0), (-2760.0, 470.0)):
        items.append(_floor("p7_foliage_plant_aloe_small", x, y, wt, rng.uniform(0, 360),
                            solid=False))
    items += [
        _floor("p7_bag_plastic_soil", edge - 50.0, -600.0, wt, 80.0, solid=False),
        _floor("p7_bag_plastic_soil", edge - 50.0, -574.0, wt, 95.0, solid=False),
        _floor("p7_bag_plastic_soil", edge - 36.0, -520.0, wt, 60.0, solid=False),
        _floor("p7_foliage_palm_lipstick_sml", -2745.0, -100.0, wt, 0.0, solid=False),
        _floor("p7_foliage_palm_lipstick_sml", -2745.0, 100.0, wt, 90.0, solid=False),
    ]
    ctx.put(items, "dense_lot_bed_weeds")


def _walk_litter(ctx: RoomContext, rng) -> None:
    """The covered walk: what the line left on the benches and round the bins."""
    wt = ctx.walk_top
    bench = _top_of("p7_bench_modern_01", wt)
    items = [
        _on("p7_office_paper_folder_pink", -1784.0, -200.0, bench, 5.0),
        _on("p7_debris_trash_cup_coffee_02", -1772.0, -168.0, bench, 0.0),
        _on("p7_office_paper_sheet_12", -1780.0, 170.0, bench, 30.0),
        _on("p7_book_vintage_02", -1776.0, 212.0, bench, 85.0),
    ]
    for bx, by in ((-1660.0, -96.0), (-1660.0, 96.0)):
        for k in range(3):
            items.append(_floor(TRASH[(k + (by > 0) * 3) % len(TRASH)],
                                bx - 28.0 - rng.uniform(0, 12), by + (-22.0, 4.0, 26.0)[k], wt,
                                rng.uniform(0, 360), solid=False))
    for x, y in ((-1700.0, -300.0), (-1740.0, -520.0), (-1690.0, 520.0), (-1720.0, 620.0),
                 (-1770.0, -620.0), (-1700.0, 330.0)):
        items.append(_floor(rng.choice(FORMS), x, y, wt, rng.uniform(0, 360), solid=False))
    ctx.put(items, "dense_lot_walk_litter")


def _lot_signs(ctx: RoomContext) -> None:
    """The lot's own signage on its north and south walls: loading zone,
    no smoking, staff only by the staff bay's end, the caution signs the
    outbreak added."""
    inside = ctx.room.interior
    n, s = inside.maxs.y - 3.0, inside.mins.y + 3.0
    z = ctx.room.floor_z
    ctx.put([
        _mounted("p7_signage_loading_zone_02", Point(-2420.0, n, z + 70.0), Facing.SOUTH),
        _mounted("p7_zm_der_signage_garage", Point(-2168.0, n, z + 110.0), Facing.SOUTH),
        _mounted("p7_zm_der_signage_no_smoking", Point(-1916.0, n, z + 80.0), Facing.SOUTH),
        _mounted("p7_signage_caution_biohazard_01", Point(-2250.0, n, z + 84.0), Facing.SOUTH),
        _mounted("p7_zm_der_signage_employees_only", Point(-1916.0, s, z + 80.0), Facing.NORTH),
        _mounted("p7_zm_der_signage_garage", Point(-2168.0, s, z + 110.0), Facing.NORTH),
        _mounted("p7_signage_caution_warning_01", Point(-2420.0, s, z + 84.0), Facing.NORTH),
        _mounted("p7_zm_der_signage_hazard_04", Point(-2060.0, s, z + 84.0), Facing.NORTH),
    ], "dense_lot_signs")
