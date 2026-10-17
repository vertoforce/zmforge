"""zm_dmv dense pass: the queue room (key ``queue``).  See the package docstring.

The line is still moving, technically.  What people put down while they
waited is still on the rails, and the wait estimate gets worse the further
along it you get: 45 minutes at the door (``queue_wait`` in
:data:`zmforge.recipes.dmv.NOTICE_LINES`), 50 at the first turn, three hours
at the second, and "YOU ARE NEXT" in sight of the Pack-a-Punch.

The lanes are the gameplay, so nothing here stands in one.  Each rail is a
48-tall clip box (:func:`zmforge.recipes.dmv._rails`) and what a player sees
along its middle is a row of stanchion posts belted post to post
(bare poles do not read as a waiting line).  Cups ride the post tops, paperwork lies on the floor under the
belts (inside the rail's footprint, so off the lanes) or flat along the rail
faces, the solids go against the north wall of the wide last lane, west of
the Pack-a-Punch's apron, and nothing solid touches a rail (a step up to a
rail top would make the line hoppable).

Vignettes (ids ``dense_queue_<name>``):

``rail_tops``  paperwork dropped under the belts, mugs and bottles left on
               the post tops
``posts``      stanchion posts along every rail, at most 96 apart, belted
               (``queue_belt_<rail>_<n>``)
``bench``      a bench on the north wall with somebody's luggage and a
               lollipop
``bin``        a bin on the north wall, and the cups that missed it
``camper``     somebody camped in line against the last rail
``south``      the dead-end lane's wall: notice board, pictures, a clock
``screen``     a dead NOW SERVING screen above the Pack-a-Punch
``west``       a caution sign and a STEPS sign (there are no steps)
``litter``     flat litter along the rail faces
"""
from __future__ import annotations

from ...dressing import on_wall
from ._kit import (
    Facing,
    Point,
    RoomContext,
    _belt_line,
    _floor,
    _mounted,
    _on,
    _top_of,
    queue_dead_end,
    queue_route,
)

NOTICES: dict[str, tuple[str, tuple[str, ...]]] = {
    "queue_wait_50": ("ESTIMATED WAIT FROM THIS POINT: 50 MINUTES -- hold ^3[{+activate}]^7 to ask", (
        "The estimate has been revised.",
        "Thank you for your patience.",
    )),
    "queue_wait_3h": ("ESTIMATED WAIT FROM THIS POINT: 3 HOURS -- hold ^3[{+activate}]^7 to ask", (
        "Thank you for your continued patience.",
        "The estimate has been revised again.",
    )),
    "queue_next": ("YOU ARE NEXT -- hold ^3[{+activate}]^7 to check", (
        "Please wait to be called.",
        "NOW SERVING: 12.",
    )),
    "queue_express": ("EXPRESS LANE -- hold ^3[{+activate}]^7 to read the rules", (
        "Express customers are served from the back of the line.",
        "You have been moved to the back of the line.",
    )),
    "queue_documents": ("HAVE YOUR DOCUMENTS READY: hold ^3[{+activate}]^7 to check", (
        "Missing: proof of residence.",
        "Missing: proof of being alive.",
        "Please return to the back of the line.",
    )),
}


def _rails(ctx: RoomContext) -> list[tuple[float, float, float]]:
    """The four rails as ``(x0, x1, y_centre)``, south to north, from the
    route's lane centres: a rail sits half a lane north of each of the
    first four lanes' middles.  Rails 0 and 2 run from the west wall, 1 and
    3 to the east one, leaving the turn at the other end."""
    plan = ctx.plan
    q_in = ctx.room.interior
    route, dead = queue_route(plan), queue_dead_end(plan)
    mids = (dead[3].y, dead[1].y, route[0].y, route[2].y)
    y_off = plan.lane_width / 2.0 + plan.rail_thickness / 2.0
    out = []
    for index, mid in enumerate(mids):
        if index % 2 == 0:
            out.append((q_in.mins.x, q_in.maxs.x - plan.turn_width, mid + y_off))
        else:
            out.append((q_in.mins.x + plan.turn_width, q_in.maxs.x, mid + y_off))
    return out


#: Most room between two neighbouring stanchion posts on a rail.
POST_SPACING = 96.0
POST = "p7_handrail_post_middle"


def rail_posts(ctx: RoomContext) -> list[list[float]]:
    """Each rail's post x positions, west to east: one 6 off the wall the
    rail is fixed to, one 4 short of its free end at the turn, and the run
    between split evenly at most :data:`POST_SPACING` apart."""
    q_in = ctx.room.interior
    out = []
    for index, (x0, x1, _y) in enumerate(_rails(ctx)):
        a = x0 + (6.0 if index % 2 == 0 else 4.0)
        b = x1 - (4.0 if index % 2 == 0 else 6.0)
        assert q_in.mins.x <= a < b <= q_in.maxs.x
        n = max(1, int(-(-(b - a) // POST_SPACING)))
        out.append([a + (b - a) * k / n for k in range(n + 1)])
    return out


def _nearest(xs: list[float], x: float, taken: set[float]) -> float:
    """The post in *xs* nearest *x* that nothing stands on yet; claims it."""
    best = min((p for p in xs if p not in taken), key=lambda p: abs(p - x))
    taken.add(best)
    return best


def _clear_of(xs: list[float], x: float, gap: float = 12.0) -> float:
    """*x*, or *x* moved off the post it would sit on, *gap* clear of it."""
    for p in xs:
        if abs(x - p) < gap:
            return p + gap if x >= p else p - gap
    return x


def express_lane(plan) -> tuple[Point, Point]:
    """The Express Lane's ``(pad, arrival)``: a short-hop pad in the dead
    end's last leg, 142 east of where it stops, that sends whoever steps on
    it to the queue's own entry -- the back of the line.  It is in the dead
    end, so the walk to the Pack-a-Punch never crosses it."""
    route, dead = queue_route(plan), queue_dead_end(plan)
    end = dead[-1]
    return Point(end.x + 142.0, end.y, end.z), route[0]


def notice_spots(ctx: RoomContext) -> list[tuple[str, Point]]:
    """The two turns of the route (the estimate rises at each), the last
    lane short of the Pack-a-Punch, and the dead end's first turn."""
    qz = ctx.room.floor_z
    route, dead = queue_route(ctx.plan), queue_dead_end(ctx.plan)
    return [
        ("queue_wait_50", Point(route[1].x, route[1].y, qz)),
        ("queue_wait_3h", Point(route[3].x, route[3].y, qz)),
        ("queue_next", Point(route[5].x - 4.0, route[5].y - 12.0, qz)),
        ("queue_documents", Point(dead[2].x, dead[2].y, qz)),
        # Read on the way west, before the pad (90 short of it).
        ("queue_express", Point(express_lane(ctx.plan)[0].x + 90.0, dead[-1].y, qz)),
    ]


def dress(ctx: RoomContext) -> None:
    """Fill the queue room."""
    q_in, qz = ctx.room.interior, ctx.room.floor_z
    west, east = q_in.mins.x, q_in.maxs.x
    south, north = q_in.mins.y, q_in.maxs.y
    rails = _rails(ctx)
    half = ctx.plan.rail_thickness / 2.0
    ry = [y for _x0, _x1, y in rails]

    posts = rail_posts(ctx)
    post_top = _top_of(POST, qz)
    #: Posts something already stands on, per rail.
    taken: list[set[float]] = [set() for _ in rails]

    # ---- stanchion posts along every rail, belted post to post ----------
    ctx.put([
        _floor(POST, x, y, qz, 0.0, solid=False)
        for (_x0, _x1, y), xs in zip(rails, posts) for x in xs
    ], "dense_queue_posts")
    for index, ((_x0, _x1, y), xs) in enumerate(zip(rails, posts)):
        # The rail is the clip already: belts only.
        _belt_line(ctx.bp, [(x, y) for x in xs], qz, f"queue_belt_{index}",
                   clip_thickness=None)

    # (No WAIT signs on the posts: the model,
    # ``p7_zm_der2_vending_packapunch_sign_wait``, renders as a red pennant,
    # not a queue sign.  The wait is told by the notices at the turns.)

    # ---- what people put down while they waited -------------------------
    # Cups and bottles on the post tops; paper and the lollipop on the floor
    # under the belt, inside the rail's footprint (off the lanes).
    cups = ("p7_cup_coffee_mug", "p7_debris_trash_cup_coffee_02",
            "p7_bottle_plastic_16oz_water")
    tops = [
        _on(model, _nearest(posts[rail], x, taken[rail]), ry[rail], post_top, yaw)
        if model in cups else
        _floor(model, _clear_of(posts[rail], x), ry[rail], qz, yaw,
               solid=model.startswith("zmf_prop_"))
        for model, rail, x, yaw in (
            ("p7_office_paper_folder_pink", 0, 520.0, 0.0),
            ("p7_cup_coffee_mug", 0, 780.0, 30.0),
            ("p7_office_paper_folder_blue", 1, 680.0, 8.0),
            ("p7_debris_trash_cup_coffee_02", 1, 900.0, 0.0),
            ("p7_bottle_plastic_16oz_water", 1, 1100.0, 0.0),
            ("p7_book_office_binder_open", 2, 600.0, 90.0),
            ("p7_cup_coffee_mug", 2, 850.0, 200.0),
            ("p7_office_paper_folder_pink", 2, 1050.0, 355.0),
            ("p7_bottle_plastic_16oz_water", 3, 700.0, 0.0),
            ("p7_office_paper_folder_blue", 3, 950.0, 3.0),
            ("p7_debris_trash_cup_coffee_02", 3, 1180.0, 90.0),
        )
    ]
    ctx.put(tops, "dense_queue_rail_tops")

    # ---- a bench on the north wall, west end, with the luggage ----------
    bench = "p7_bench_modern_01"
    bx, by = 500.0, north - 11.0
    b_top = _top_of(bench, qz)
    ctx.put([
        _floor(bench, bx, by, qz, 0.0),
        _on("p7_luggage_cloth_a_lg_green", bx - 20.0, by, b_top, 0.0),
        _on("p7_office_paper_stack_sml", bx + 20.0, by, b_top, 90.0),
        # A zmf_prop_* kit model is placed solid (Z21 at commit), so the
        # lollipop is on the bench, where the solids stand, not in the line.
        _on("zmf_prop_lollipop", bx + 2.0, by, b_top, 0.0)[:4] + (True,),
        _floor("p7_luggage_hardshell_handle_down_white", bx + 53.0, north - 8.0, qz, 0.0),
    ], "dense_queue_bench")

    # ---- a bin on the north wall, between the cooler and the aloe -------
    ctx.put([
        _floor("p7_trashcan_metal_modern_glass", 975.0, north - 18.0, qz, 0.0),
        _floor("p7_debris_trash_cup_coffee_02", 950.0, north - 32.0, qz, 40.0, solid=False),
        _floor("p7_debris_trash_cup_coffee_02", 1000.0, north - 42.0, qz, 160.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", 985.0, north - 52.0, qz, 0.0, solid=False),
    ], "dense_queue_bin")

    # ---- somebody camped in line, against the last rail -----------------
    face = ry[3] + half
    ctx.put([
        _floor("p7_bed_sheet_barrack_02", 700.0, face + 26.0, qz, 90.0, solid=False),
        _floor("p7_bed_pillow_barrack", 748.0, face + 14.0, qz, 0.0, solid=False),
        _floor("p7_book_vintage_02", 660.0, face + 13.0, qz, 20.0, solid=False),
        _floor("p7_bottle_plastic_16oz_water", 690.0, face + 58.0, qz, 0.0, solid=False),
        _floor("p7_debris_trash_drink_carrier_01", 770.0, face + 38.0, qz, 30.0, solid=False),
    ], "dense_queue_camper")

    # ---- the dead-end lane's wall ---------------------------------------
    ctx.put([
        _mounted("p7_zm_der2_bulletin_board", Point(600.0, south + 3.0, qz + 96.0),
                 Facing.NORTH),
        _mounted("p7_clock_metal_wall_01_base", Point(880.0, south + 3.0, qz + 120.0),
                 Facing.NORTH),
        _mounted("p7_picture_frame_modern_01", Point(1000.0, south + 2.0, qz + 100.0),
                 Facing.NORTH),
        _mounted("p7_picture_frame_modern_01", Point(1100.0, south + 2.0, qz + 100.0),
                 Facing.NORTH),
    ], "dense_queue_south")

    # ---- a dead NOW SERVING screen over the Pack-a-Punch ----------------
    pap_y = queue_route(ctx.plan)[5].y
    ctx.put([
        # Hung by its measured box: _mounted put it 39 off the wall (the
        # model's body sits well off its origin).
        on_wall("p7_consumer_grade_monitor_wall_medium", Facing.WEST, pap_y, east, centre_z=qz + 140.0),
    ], "dense_queue_screen")

    # ---- the entry wall: caution, and STEPS where there are none --------
    ctx.put([
        _mounted("p7_zm_der_signage_steps", Point(west + 3.0, -56.0, qz + 104.0), Facing.EAST),
        _mounted("p7_signage_caution_warning_01", Point(west + 3.0, 62.0, qz + 104.0),
                 Facing.EAST),
    ], "dense_queue_west")

    # ---- flat litter along the rail faces -------------------------------
    ctx.put([
        _floor(model, x, ry[rail] + side * (half + 5.0), qz, yaw, solid=False)
        for model, rail, side, x, yaw in (
            ("p7_debris_trash_paper_03", 0, -1, 620.0, 10.0),
            ("p7_debris_trash_cup_red_02", 0, -1, 900.0, 0.0),
            ("p7_cleaning_paper_ball_brown", 0, 1, 700.0, 50.0),
            ("p7_debris_trash_paper_09", 0, 1, 1000.0, 90.0),
            ("p7_debris_trash_paper_05", 1, -1, 650.0, 30.0),
            ("p7_debris_trash_drink_carrier_01", 1, -1, 1050.0, 0.0),
            ("p7_office_paper_sheet_02", 1, 1, 800.0, 90.0),
            ("p7_debris_trash_paper_10", 2, -1, 750.0, 200.0),
            ("p7_debris_trash_drink_carrier_01", 2, 1, 950.0, 70.0),
            ("p7_debris_trash_cup_red_02", 3, -1, 620.0, 0.0),
        )
    ], "dense_queue_litter")
    _dress_hall(ctx)


# ==========================================================================
# The DMV hall pass (the hall needed far more props to read as a
# DMV): what a real queue hall has on its walls and rails and floor, mid
# outbreak.  Everything here is flat litter, post-top or under-belt clutter or wall
# dressing (none of it solid), except three pieces against the north wall
# of the last lane, where the lane test lets solids stand.
#
# Vignettes (ids ``dense_queue_<name>``):
#
# ``rail_clutter``  forms, cups, folders and books dropped under every belt
# ``lane_litter``   dropped tickets, forms and cups down every lane
# ``notices``       rules, fees and hours boards, pictures and signs, all walls
# ``banners``       the wayfinding banners high over the entry, the Pack-a-Punch
#                   wall and the north wall
# ``now_serving``   three more dead NOW SERVING screens
# ``north_wall``    a planter, an OUT OF ORDER self-service kiosk and a forms
#                   cabinet in the gaps of the north wall (the only solids)
# ``left_behind``   luggage, bags, clothes and two chairs dragged into
#                   the line to wait on
# ``benches``       two benches along the dead end's south wall, and their mess
# ``dead_end``      what happened to whoever reached the dead end first
# ``wet_floor``     the water cooler's spill and the towels on it
# ==========================================================================
import math as _math  # noqa: E402
import random as _random  # noqa: E402


#: Small enough to lie under a belt, inside the 16-wide rail: (model, yaw).
_RAIL_BITS = (
    ("p7_office_paper_sheet_02", 90.0),
    ("p7_debris_trash_cup_coffee_02", 20.0),
    ("p7_office_paper_folder_blue", 4.0),
    ("p7_book_vintage_03", 80.0),
    ("p7_office_paper_sheet_12", 12.0),
    ("p7_bottle_plastic_16oz_water", 0.0),
    ("p7_debris_trash_food_box_01", 30.0),
    ("p7_office_paper_folder_pink", 350.0),
    ("p7_cup_coffee_mug", 140.0),
    ("p7_office_paper_sheet_10", 60.0),
    ("p7_book_office_binder_open", 90.0),
    ("p7_cleaning_paper_ball_brown", 0.0),
    ("p7_debris_trash_drink_carrier_01", 15.0),
)

#: Floor litter: tickets, forms, cups and wrappers, in rough proportion.
_LITTER = (
    "p7_office_paper_sheet_10", "p7_office_paper_sheet_12", "p7_debris_trash_paper_04",
    "p7_office_paper_sheet_01", "p7_debris_trash_cup_coffee_02", "p7_office_paper_sheet_02",
    "p7_debris_trash_paper_05", "p7_cleaning_paper_ball_brown", "p7_box_copy_paper_sheet",
    "p7_office_paper_sheet_09", "p7_debris_trash_paper_02", "p7_debris_trash_cup_red_02",
    "p7_office_paper_sheet_08", "p7_debris_trash_paper_08", "p7_office_paper_folder_blue",
    "p7_debris_trash_paper_03", "p7_cleaning_paper_towel", "p7_office_paper_sheet_03",
    "p7_debris_trash_food_box_01", "p7_debris_trash_paper_09", "p7_office_paper_folder_pink",
    "p7_debris_trash_paper_10", "p7_debris_trash_paper_plate_01", "p7_debris_newspaper_01",
)


def _dress_hall(ctx: RoomContext) -> None:
    """The DMV hall pass (see the block comment above)."""
    q_in, qz = ctx.room.interior, ctx.room.floor_z
    west, east = q_in.mins.x, q_in.maxs.x
    south, north = q_in.mins.y, q_in.maxs.y
    rails = _rails(ctx)
    half = ctx.plan.rail_thickness / 2.0
    posts = rail_posts(ctx)

    # ---- under the belts: what else got dropped while people waited -------
    # On the floor along the rail's middle, inside its clip (off the lanes),
    # kept 24 clear of the first pass's paper there and 12 clear of every
    # post.  Every 116 along, not 58: the posts are the rail's props now.
    dropped = (
        (520.0,), (680.0,), (600.0, 1050.0), (950.0,),
    )
    bits = []
    k = 0
    for i, (x0, x1, y) in enumerate(rails):
        x = max(x0, west + 24.0) + 20.0 + 11.0 * i
        while x <= min(x1, east - 24.0) - 16.0:
            if (all(abs(x - t) >= 24.0 for t in dropped[i])
                    and all(abs(x - p) >= 12.0 for p in posts[i])):
                model, yaw = _RAIL_BITS[k % len(_RAIL_BITS)]
                bits.append(_floor(model, x, y + (-2.0, 2.0)[k % 2], qz,
                                   yaw + 7.0 * (k % 3), solid=False))
                k += 1
            x += 116.0
    ctx.put(bits, "dense_queue_rail_clutter")

    # ---- dropped tickets and forms down every lane ------------------------
    rng = _random.Random(20260923)
    keep_off = ((472.0, -272.0, 40.0), (472.0, 332.0, 40.0),     # the risers
                (590.0, -272.0, 44.0),                           # the express pad
                (1260.0, 332.0, 110.0),                          # the Pack-a-Punch
                (700.0, 240.0, 70.0))                            # the camper
    lanes = (  # x0, x1, y0, y1, how many
        (440.0, 1262.0, south + 26.0, rails[0][2] - half - 10.0, 12),
        (440.0, 1262.0, rails[0][2] + half + 10.0, rails[1][2] - half - 10.0, 11),
        (440.0, 1262.0, rails[1][2] + half + 10.0, rails[2][2] - half - 10.0, 13),
        (440.0, 1262.0, rails[2][2] + half + 10.0, rails[3][2] - half - 10.0, 11),
        (440.0, 1150.0, rails[3][2] + half + 10.0, north - 70.0, 13),
    )
    # In drifts, not spread like confetti: paper
    # piles up where people stood still -- at the turns, against the belts
    # at each end of a lane, and round the middle where the line stalled --
    # so each lane's share is split over two heaps, each a tight scatter
    # about 25 across.
    litter = []
    n = 0
    for index, (x0, x1, y0, y1, count) in enumerate(lanes):
        mid_y = (y0 + y1) / 2.0
        # Two heaps a lane (a first render with three read as still even).
        heaps = (
            (x0 + 50.0, y0 + 0.3 * (y1 - y0)) if index % 2 else
            (x0 + (x1 - x0) * 0.4, mid_y),
            (x1 - 60.0, y1 - 0.3 * (y1 - y0)),
        )
        placed = 0
        tries = 0
        while placed < count and tries < count * 20:
            tries += 1
            hx, hy = heaps[placed % len(heaps)]
            x = min(max(rng.gauss(hx, 12.0), x0), x1)
            y = min(max(rng.gauss(hy, 9.0), y0), y1)
            if any(_math.hypot(x - kx, y - ky) < r for kx, ky, r in keep_off):
                continue
            litter.append(_floor(_LITTER[n % len(_LITTER)], x, y, qz, rng.uniform(0.0, 360.0),
                                 solid=False))
            n += 1
            placed += 1
    ctx.put(litter, "dense_queue_lane_litter")

    # ---- rules, fees and hours: boards, pictures and signs on every wall --
    board, frame, pic = ("p7_zm_der2_bulletin_board", "p7_picture_frame_modern_01",
                         "p7_picture_frame_modern_01")
    walls = [
        # north wall, over the chairs, the cooler and the bin
        (board, Facing.SOUTH, 560.0, north, qz + 96.0),
        (frame, Facing.SOUTH, 615.0, north, qz + 102.0),
        (pic, Facing.SOUTH, 760.0, north, qz + 100.0),
        ("p7_signage_caution_warning_01", Facing.SOUTH, 830.0, north, qz + 100.0),
        (pic, Facing.SOUTH, 880.0, north, qz + 100.0),
        (frame, Facing.SOUTH, 940.0, north, qz + 102.0),
        ("p7_signage_loading_zone_02", Facing.SOUTH, 1000.0, north, qz + 102.0),
        ("p7_zm_der_signage_employees_only", Facing.SOUTH, 1112.0, north, qz + 108.0),
        # east wall: the turns and the Pack-a-Punch lane
        (frame, Facing.WEST, -236.0, east, qz + 102.0),
        ("p7_zm_der2_signage_hazard_01", Facing.WEST, -40.0, east, qz + 104.0),
        ("p7_signage_caution_warning_01", Facing.WEST, 40.0, east, qz + 100.0),
        (board, Facing.WEST, 136.0, east, qz + 96.0),
        (frame, Facing.WEST, 244.0, east, qz + 102.0),
        (pic, Facing.WEST, 420.0, east, qz + 100.0),
        # west wall: the entry and the west turns
        (pic, Facing.EAST, -302.0, west, qz + 100.0),
        (frame, Facing.EAST, -182.0, west, qz + 102.0),
        ("p7_zm_der_signage_no_smoking", Facing.EAST, -95.0, west, qz + 104.0),
        (frame, Facing.EAST, 182.0, west, qz + 102.0),
        (board, Facing.EAST, 262.0, west, qz + 96.0),
        ("p7_signage_caution_warning_01", Facing.EAST, 400.0, west, qz + 100.0),
        # south wall: the dead end
        (frame, Facing.NORTH, 462.0, south, qz + 102.0),
        ("p7_zm_der_signage_hazard_03", Facing.NORTH, 508.0, south, qz + 104.0),
        (pic, Facing.NORTH, 682.0, south, qz + 100.0),
        (frame, Facing.NORTH, 732.0, south, qz + 102.0),
        ("p7_signage_loading_zone_01", Facing.NORTH, 940.0, south, qz + 104.0),
        (frame, Facing.NORTH, 1210.0, south, qz + 150.0),
    ]
    ctx.put([on_wall(m, f, a, w, centre_z=z) for m, f, a, w, z in walls], "dense_queue_notices")

    # ---- wayfinding banners, high up -------------------------------------
    ctx.put([
        on_wall("p7_zm_der_storefront_signage_1", Facing.EAST, 0.0, west, centre_z=qz + 196.0),
        on_wall("p7_zm_der_storefront_signage_2", Facing.WEST, 0.0, east, centre_z=qz + 196.0),
        on_wall("p7_zm_der_storefront_signage_4", Facing.SOUTH, 820.0, north, centre_z=qz + 196.0),
    ], "dense_queue_banners")

    # ---- three more NOW SERVING screens, all dead -------------------------
    screen = "p7_consumer_grade_monitor_wall_medium"
    ctx.put([
        on_wall(screen, Facing.WEST, -136.0, east, centre_z=qz + 144.0),
        on_wall(screen, Facing.EAST, 300.0, west, centre_z=qz + 144.0),
        on_wall(screen, Facing.SOUTH, 1060.0, north, centre_z=qz + 144.0),
    ], "dense_queue_now_serving")

    # ---- the north wall's gaps: the only solids ---------------------------
    cab = "p7_file_cab_metal_02"
    cab_top = _top_of(cab, qz)
    ctx.put([
        _floor("p7_cai_planter_square", west + 22.0, north - 25.5, qz, 0.0),
        _floor("p7_cai_sign_inteactive_kiosk", 933.0, north - 29.5, qz, 90.0),
        # Between the chairs' bin and the next one: the gap by the north
        # door is inside the door band (dmv._clear_door_bands drops it).
        # Drawers look along the cabinet's own -y: yaw 0 turns them south.
        _floor(cab, 805.0, north - 15.5, qz, 0.0),
        _on("p7_office_paper_stack_sml", 805.0, north - 21.0, cab_top, 0.0),
        _on("p7_office_paper_folder_blue", 805.0, north - 10.0, cab_top, 80.0),
    ], "dense_queue_north_wall")

    # ---- what people dropped and left in the lanes ------------------------
    r1_south = rails[1][2] - half
    r2_north = rails[2][2] + half
    ctx.put([
        _floor("p7_luggage_hardshell_handle_down_white", 820.0, r1_south - 7.0, qz, 0.0,
               solid=False),
        _floor("p7_bag_plastic_soil", 846.0, r1_south - 9.0, qz, 12.0, solid=False),
        _floor("p7_luggage_cloth_a_lg_green", 980.0, r2_north + 9.0, qz, 0.0, solid=False),
        _floor("p7_debris_clothing_tshirts_01", 760.0, -34.0, qz, 40.0, solid=False),
        _floor("p7_debris_clothing_piles_01", 620.0, 160.0, qz, 100.0, solid=False),
        _floor("p7_bag_plastic_soil", 1040.0, 44.0, qz, 200.0, solid=False),
        _floor("p7_chair_waiting_room_01_blue", 620.0, 372.0, qz, 205.0, solid=False),
        _floor("p7_chair_waiting_room_01_blue", 850.0, 366.0, qz, 140.0, solid=False),
        _floor("p7_book_vintage_open_01", 1000.0, 362.0, qz, 30.0, solid=False),
        _floor("p7_debris_trash_food_box_01", 1030.0, 300.0, qz, 75.0, solid=False),
    ], "dense_queue_left_behind")

    # ---- two benches along the dead end's south wall ----------------------
    bench = "p7_bench_modern_01"
    b_top = _top_of(bench, qz)
    by = south + 9.5
    ctx.put([
        _floor(bench, 700.0, by, qz, 0.0, solid=False),
        _floor(bench, 950.0, by, qz, 0.0, solid=False),
        _on("p7_office_paper_stack_sml", 680.0, by, b_top, 80.0),
        _on("p7_cup_coffee_mug", 712.0, by + 2.0, b_top, 30.0),
        _on("p7_office_paper_folder_pink", 728.0, by - 1.0, b_top, 170.0),
        _on("p7_book_office_binder_open", 935.0, by, b_top, 90.0),
        _on("p7_debris_trash_cup_coffee_02", 962.0, by + 3.0, b_top, 0.0),
        _floor("p7_debris_newspaper_05", 955.0, by + 30.0, qz, 15.0, solid=False),
        _floor("p7_bottle_plastic_16oz_water", 745.0, by + 18.0, qz, 0.0, solid=False),
    ], "dense_queue_benches")

    # (No boards on the wall east of the south door: there is no opening
    # there, so they would be nailed over bare plaster.)

    # ---- the dead end: somebody reached it first --------------------------
    ctx.put([
        _floor("p7_debris_clothing_pants_01", 820.0, -262.0, qz, 60.0, solid=False),
        _floor("p7_gib_chunk_flesh_01", 846.0, -240.0, qz, 0.0, solid=False),
        _floor("p7_gib_chunk_meat_02", 800.0, -286.0, qz, 90.0, solid=False),
        _floor("p7_gib_chunk_bone_03", 858.0, -276.0, qz, 30.0, solid=False),
        _floor("p7_gib_chunk_meat_01", 790.0, -236.0, qz, 200.0, solid=False),
        _floor("p7_office_paper_folder_blue", 872.0, -252.0, qz, 140.0, solid=False),
        _floor("p7_debris_wood_board_cluster_02", 1080.0, -270.0, qz, 20.0, solid=False),
        _floor("p7_debris_brick_chunk_02", 1110.0, -250.0, qz, 0.0, solid=False),
    ], "dense_queue_dead_end")

    # ---- the water cooler's spill, mopped at --------------------------------
    # (No ``p7_3arc_park_pylon`` "cone" here: it is a grey kerb bollard and
    # reads as one more stray stanchion post.)
    ctx.put([
        _floor("p7_cleaning_paper_towel", 878.0, north - 40.0, qz, 140.0, solid=False),
        _floor("p7_cleaning_paper_towel", 902.0, north - 26.0, qz, 20.0, solid=False),
        _floor("p7_cleaning_paper_towel", 915.0, north - 44.0, qz, 80.0, solid=False),
        _floor("p7_debris_trash_cup_red_02", 890.0, north - 58.0, qz, 0.0, solid=False),
    ], "dense_queue_wet_floor")
