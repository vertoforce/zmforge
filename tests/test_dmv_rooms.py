"""zm_dmv dense pass, room by room: density, vignettes, quirks and what each
room must keep clear.

The first half runs the same checks over every room module in
:data:`zmforge.recipes.dmv_rooms.ROOM_MODULES` (density band, every vignette
placed and inside its room, every notice hung in its own room).  The second
half is each room's own vignette rules and jokes.

What every notice shares -- 80 units from every purchase, barrier, the
ticket machine and every other notice, on reached floor, shipping its own
words -- is pinned once for the whole map in ``tests/test_dmv.py``
(``test_no_notice_stands_where_a_purchase_is_made``,
``test_every_notice_is_hung_and_says_its_own_words``), which reads the
committed server script and so covers every room module's notices too.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest

from zmforge.blueprint.elements import Lamp, PlayerStart, PropScatter, Room
from zmforge.placement.geometry import Poly2
from zmforge.placement.relations import Placed
from zmforge.recipes import dmv_of_the_damned
from zmforge.recipes.dmv import (
    FIXTURE, LOT_CARS, NOTICE_LINES, all_notices, counter_run, parking_bays, queue_dead_end,
    queue_route, ticket_kiosk_xy, ticket_trigger_point,
)
from zmforge.recipes.dmv_rooms import ROOM_MODULES
from zmforge.recipes.dmv_rooms import break_room, entry, eye, lot, office, photo, queue, records
from zmforge.recipes.dmv_rooms import waiting, windows
from zmforge.recipes.props import _mount_face, collision_box
from zmforge.spatial import Point


@dataclass(frozen=True)
class RoomSpec:
    key: str
    room_id: str
    module: object
    props: tuple[int, int | None]          # density band (low, high or None)
    max_solids: int | None = None          # the pass adds clutter, not obstacles
    floors: dict[str, int] = field(default_factory=dict)   # vignette -> least props


# Floors are the least each vignette carries; solid caps are the room's base
# solids plus what the density pass deliberately adds.  Each band is about
# the room's count -5%/+10%; records and office include the shelf-board fill
# (props.SHELF_BOARDS).
ROOMS = {
    spec.key: spec for spec in (
        # 25 solids before, four added (bollards, crate, carton); cars excluded.
        RoomSpec("lot", "lot_room", lot, (230, 270), 31,
                 {"line": 7, "meter": 4, "staff_bay": 2, "cart": 7, "bed": 5, "frontage": 4}),
        # 21 props (10 solid) before the dense pass.
        RoomSpec("entry", "entry_room", entry, (190, 225), 20,
                 {"take_a_number": 5, "tickets": 12, "stanchions": 6, "overflow": 5,
                  "now_serving": 1, "rack": 12, "self_service": 6, "cooler": 6,
                  "ceiling": 5, "debris": 10, "walls": 1}),
        # 41 solids before; two added, both against a wall.
        RoomSpec("waiting", "waiting_room", waiting, (250, 290), 59,
                 {"seats": 5, "between": 2, "camp": 5, "lane": 3, "clocks": 3,
                  "magazines": 4, "tv": 1, "walls": 2}),
        RoomSpec("windows", "windows_room", windows, (265, 310)),
        # Four solids before; one added, the lenses carton.
        RoomSpec("eye", "eye_exam_room", eye, (110, 135), 6,
                 {"station": 4, "line": 3, "lenses": 7, "walls": 5, "chart_rubble": 4,
                  "litter": 14}),
        RoomSpec("photo", "photo_room", photo, (100, 130), None,
                 {"cart": 5, "lollipops": 5, "samples": 1, "exit": 1, "rejects": 8,
                  "boxes": 2, "floor": 10, "walls": 4}),
        RoomSpec("break", "break_room", break_room, (135, 160)),
        # 22 solids before; eight added against a wall, plus the kit teddy.
        RoomSpec("records", "records_room", records, (415, 480), 34,
                 {"cabinet_tops": 8, "shelf_tops": 6, "filing": 2, "request": 6, "camp": 7,
                  "unclaimed": 5, "speed_corner": 3, "latrine": 3, "stacks": 3, "walls": 4,
                  "floor": 3}),
        # 9 solids before; three on the north wall, plus the kit lollipop on the bench.
        # Posts: along every rail, belted, not one per free end.
        RoomSpec("queue", "queue_room", queue, (240, 280), 16,
                 {"rail_tops": 11, "posts": 36, "bench": 5, "bin": 4,
                  "camper": 5, "south": 4, "screen": 1, "west": 2, "litter": 10}),
        RoomSpec("office", "office_room", office, (270, 315)),
    )
}
ROOM_IDS = {key: spec.room_id for key, spec in ROOMS.items()}


@pytest.fixture(scope="module")
def built():
    return dmv_of_the_damned("zm_dmv")


@pytest.fixture(scope="module")
def spots(built):
    """``(lines, [(key, point), ...])`` for every notice on the map."""
    return all_notices(FIXTURE, {key: built.find(rid) for key, rid in ROOM_IDS.items()})


def _footprint(prop) -> Placed:
    return Placed.from_model(prop.model, collision_box(prop.model),
                             (prop.origin.x, prop.origin.y, prop.origin.z),
                             prop.yaw, prop.scale, solid=prop.solid, ident=prop.id)


def _home(built, prop) -> list[str]:
    """Every room whose interior (4 units of slack) holds the prop's centre."""
    p = _footprint(prop)
    return [room.id for room in built.elements(Room)
            if room.interior.mins.x - 4.0 <= p.x <= room.interior.maxs.x + 4.0
            and room.interior.mins.y - 4.0 <= p.y <= room.interior.maxs.y + 4.0]


def _room_props(built, room_id: str) -> list:
    return [prop for scatter in built.elements(PropScatter) for prop in scatter.props
            if room_id in _home(built, prop)]


def _vignettes(spec: RoomSpec) -> dict[str, str]:
    """Vignette name -> scatter id: the module's own table where it has one."""
    return getattr(spec.module, "VIGNETTES", None) or {
        name: f"dense_{spec.key}_{name}" for name in spec.floors}


# --------------------------------------------------------------------------
# Every room
# --------------------------------------------------------------------------
def test_every_room_module_is_covered() -> None:
    assert set(ROOMS) == set(ROOM_MODULES)


@pytest.mark.parametrize("key", list(ROOMS))
def test_the_room_is_full_to_its_density_target_but_not_of_obstacles(built, key) -> None:
    spec = ROOMS[key]
    props = _room_props(built, spec.room_id)
    low, high = spec.props
    assert low <= len(props), len(props)
    assert high is None or len(props) <= high, len(props)
    if spec.max_solids is not None:
        # The parked cars (lot_cars) are solid on top of the cap
        # and paid for their place under the 100 cap with the litter they replaced.
        cars = {id(p) for p in built.find("lot_cars").props} if key == "lot" else set()
        solids = sum(bool(p.solid) for p in props if id(p) not in cars)
        assert solids <= spec.max_solids, solids


@pytest.mark.parametrize("key", list(ROOMS))
def test_every_vignette_is_placed_and_stays_in_the_room(built, key) -> None:
    spec = ROOMS[key]
    for name, ident in _vignettes(spec).items():
        assert ident.startswith(f"dense_{key}_"), name
        props = built.find(ident).props
        assert len(props) >= spec.floors.get(name, 1), name
        for prop in props:
            assert _home(built, prop) == [spec.room_id], (name, prop.model)


@pytest.mark.parametrize("key", list(ROOMS))
def test_the_room_s_notices_hang_in_the_room(built, spots, key) -> None:
    spec = ROOMS[key]
    _lines, where = spots
    mine = {k: p for k, p in where if k in spec.module.NOTICES}
    assert set(mine) == set(spec.module.NOTICES)
    assert 2 <= len(mine) <= (5 if key == "queue" else 4)
    room = built.find(spec.room_id).interior
    for name, point in mine.items():
        assert room.holds_flat(point.x, point.y), name


def test_the_jokes_that_were_asked_for() -> None:
    """Each room's key joke lines, pinned so a rewrite keeps them."""
    def said(module):
        return {k: " / ".join((p,) + r) for k, (p, r) in module.NOTICES.items()}

    assert "(You do not have a vehicle.)" in " ".join(lot.NOTICES["lot_permit"][1])
    assert "Form 27-B" in " ".join(lot.NOTICES["lot_meter"][1])
    assert "attendant" in entry.NOTICES["entry_self_service"][1][0]
    assert "take a number" in " ".join(entry.NOTICES["entry_line"][1]).lower()
    assert "9:02" in " ".join(waiting.NOTICES["waiting_clocks"][1])
    assert "BACK IN 5 MIN" in waiting.NOTICES["waiting_saved_seat"][1][0]
    assert "COMPLAINTS" in said(windows)["windows_complaints"]
    assert "SYSTEM DOWN" in said(windows)["windows_terminal"]
    assert "LOST AND FOUND" in said(windows)["windows_lost_found"]
    assert "Further back." in eye.NOTICES["eye_line"][1]
    assert eye.NOTICES["eye_lenses"][1][-1] == "Thank you. Your answer was wrong."
    assert "Gary" in " ".join(photo.NOTICES["photo_samples"][1])
    assert "not an exit" in photo.NOTICES["photo_exit"][1][0]
    assert "GARY" in said(break_room)["break_time_clock"]
    assert "Take a number." in said(break_room)["break_radio"]
    assert "DAYS WITHOUT AN INCIDENT: 0" in said(break_room)["break_safety_board"]
    assert "customer 846" in " ".join(records.NOTICES["records_request"][1])
    assert records.NOTICES["records_occupied"][0].startswith("OCCUPIED -- hold")
    assert "45 MINUTES" in NOTICE_LINES["queue_wait"][0]
    assert "50 MINUTES" in queue.NOTICES["queue_wait_50"][0]
    assert "3 HOURS" in queue.NOTICES["queue_wait_3h"][0]
    assert queue.NOTICES["queue_next"][0].startswith("YOU ARE NEXT -- hold")
    assert "NOW SERVING: 12." in queue.NOTICES["queue_next"][1]
    assert "back of the line" in " ".join(queue.NOTICES["queue_express"][1])
    assert "RING FOR SERVICE" in said(office)["office_service_bell"]
    assert "Gary." in said(office)["office_employee_month"]
    assert "The manager is in a meeting." in said(office)["office_survey"]


def _added(built, key: str):
    """Every prop the dense pass adds to one room, with its vignette name."""
    for name, ident in _vignettes(ROOMS[key]).items():
        for prop in built.find(ident).props:
            yield name, prop


# --------------------------------------------------------------------------
# The lot, and its parked cars (so the bays are not left empty)
# --------------------------------------------------------------------------
def test_the_spawn_the_aisle_the_walk_and_the_pistol_stay_clear(built) -> None:
    """Nothing solid the pass adds stands in the drive aisle, under the
    covered walk, or within 120 of the starter pistol or a riser."""
    plan = FIXTURE
    walk_x0 = plan.lot.maxs.x - plan.wall - plan.walk_depth
    aisle = (walk_x0 - plan.stall_depth - plan.drive_aisle, walk_x0 - plan.stall_depth)
    pistol = built.find("lot_wallbuy").position
    risers = [built.find(f"lot_riser_{i}").position for i in range(3)]
    for _name, prop in _added(built, "lot"):
        if not prop.solid:
            continue
        p = _footprint(prop)
        assert not aisle[0] <= p.x <= aisle[1], prop.model
        assert not (p.x >= walk_x0 and abs(p.y) <= plan.canopy_width / 2.0 + 24.0), prop.model
        for at in [pistol, *risers]:
            assert math.hypot(p.x - at.x, p.y - at.y) >= 120.0, prop.model


def test_the_staff_bay_is_coned_inside_a_bay(built) -> None:
    near = [b for b in parking_bays(FIXTURE) if b[0] == "standard"]
    for prop in built.find("dense_lot_staff_bay").props:
        p = _footprint(prop)
        assert any(x0 <= p.x <= x1 and y0 <= p.y <= y1 for _k, x0, x1, y0, y1 in near)


def test_the_lot_stays_sunlit_with_no_lamp(built) -> None:
    lot_in = built.find("lot_room").interior
    assert not [lamp for lamp in built.elements(Lamp)
                if lot_in.holds(lamp.position, tolerance=-1e-9)]


def _box(prop):
    return _footprint(prop).footprint.bounds


def test_the_lot_has_cars_in_it(built) -> None:
    """Twelve or more solid cars, at least three models, every one with a
    measured box and a GDT declaration, and one of them the burnt-out wreck."""
    from zmforge.blueprint.installed import load_ledger

    cars = built.find("lot_cars").props
    assert len(cars) >= 12
    assert all(car.solid and car.model.startswith("veh_t7_") for car in cars)
    assert all(collision_box(car.model) is not None for car in cars)
    assert len({car.model for car in cars}) >= 3
    assert "veh_t7_city_car_static_dead" in {car.model for car in cars}
    ledger = load_ledger()
    if ledger is not None:
        assert {car.model for car in cars} <= ledger.xmodels_declared


def test_every_car_is_parked_in_its_bay(built) -> None:
    """Each car's footprint is inside its bay's row (never the drive aisle,
    the walk or the planted bed), centred on the bay, and only an askew one
    crosses a bay line, and then by less than a quarter of a bay."""
    bays = parking_bays(FIXTURE)
    cars = built.find("lot_cars").props
    assert len(cars) == len(LOT_CARS)
    for car, (index, model, _yaw) in zip(cars, LOT_CARS):
        kind, x0, x1, y0, y1 = bays[index]
        assert kind in ("standard", "accessible") and car.model == model
        p = _footprint(car)
        assert p.x == pytest.approx((x0 + x1) / 2.0) and p.y == pytest.approx((y0 + y1) / 2.0)
        bx0, by0, bx1, by1 = _box(car)
        assert x0 <= bx0 and bx1 <= x1, (car.model, index)
        slack = (y1 - y0) / 4.0
        assert y0 - slack <= by0 and by1 <= y1 + slack, (car.model, index)
    assert len({index for index, _m, _y in LOT_CARS}) == len(LOT_CARS)


def test_the_cars_keep_the_spawn_the_aisles_and_the_risers_clear(built) -> None:
    """No car in an access aisle, the towed or staff bay, near the pistol or
    a riser, over a player's start or on top of another solid prop."""
    bays = parking_bays(FIXTURE)
    used = {index for index, _m, _y in LOT_CARS}
    kept = {i for i, bay in enumerate(bays) if bay[0] == "aisle"}
    staff = next(i for i, b in enumerate(bays)
                 if b[0] == "standard" and b[3] <= -492.0 <= b[4] and b[1] > -2100.0)
    towed = next(i for i, b in enumerate(bays)
                 if b[0] == "accessible" and b[3] <= lot.TOWED_Y <= b[4])
    assert not used & (kept | {staff, towed})
    cars = built.find("lot_cars").props
    pistol = built.find("lot_wallbuy").position
    risers = [built.find(f"lot_riser_{i}").position for i in range(3)]
    starts = [point for start in built.elements(PlayerStart) for point in start.slot_positions()]
    assert starts
    others = [p for p in _room_props(built, "lot_room")
              if p.solid and not p.model.startswith("veh_")]
    for car in cars:
        bx0, by0, bx1, by1 = _box(car)
        c = _footprint(car)
        assert math.hypot(c.x - pistol.x, c.y - pistol.y) >= 120.0
        for at in risers:
            assert math.hypot(c.x - at.x, c.y - at.y) >= 120.0
        for at in starts:
            assert not (bx0 - 32.0 <= at.x <= bx1 + 32.0 and by0 - 32.0 <= at.y <= by1 + 32.0)
        for other in others:
            ox0, oy0, ox1, oy1 = _box(other)
            assert ox1 <= bx0 or bx1 <= ox0 or oy1 <= by0 or by1 <= oy0, (car.id, other.model)
    for a in cars:
        for b in cars:
            if a is b:
                continue
            ax0, ay0, ax1, ay1 = _box(a)
            cx0, cy0, cx1, cy1 = _box(b)
            assert ax1 <= cx0 or cx1 <= ax0 or ay1 <= cy0 or cy1 <= ay0


# --------------------------------------------------------------------------
# The entry lobby: the ticket machine must be easy to find, so the pass is
# pinned not to bury it.
# --------------------------------------------------------------------------
PAPER = ("p7_office_paper_sheet_", "p7_box_copy_paper_sheet")


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _poly_to_point(poly: Poly2, x: float, y: float) -> float:
    pts = poly.points
    return min(_seg_dist(x, y, *pts[i], *pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def _inside(poly: Poly2, x: float, y: float) -> bool:
    pts = poly.points
    signs = [(b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
             for a, b in zip(pts, pts[1:] + pts[:1])]
    return all(v >= 0 for v in signs) or all(v <= 0 for v in signs)


def _poly_to_segment(poly: Poly2, a: tuple, b: tuple) -> float:
    """Distance between a convex footprint and a segment, sampled every 2
    units along the segment (0 where the segment runs through it)."""
    steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 2.0))
    best = math.inf
    for i in range(steps + 1):
        x = a[0] + (b[0] - a[0]) * i / steps
        y = a[1] + (b[1] - a[1]) * i / steps
        best = min(best, 0.0 if _inside(poly, x, y) else _poly_to_point(poly, x, y))
    return best


def _solids_but_the_kiosk(built) -> list:
    return [p for p in _room_props(built, "entry_room")
            if p.solid and not (p.model == entry.KIOSK and p.id.startswith("entry_props"))]


def test_nothing_solid_crowds_the_ticket_trigger(built) -> None:
    room = built.find("entry_room")
    trig = ticket_trigger_point(room.interior, room.floor_z)
    for prop in _solids_but_the_kiosk(built):
        d = _poly_to_point(_footprint(prop).footprint, trig.x, trig.y)
        assert d >= entry.KIOSK_CLEAR, (prop.id, prop.model, d)


def test_the_walk_from_the_front_door_to_the_ticket_is_clear(built) -> None:
    room = built.find("entry_room")
    trig = ticket_trigger_point(room.interior, room.floor_z)
    door = (room.interior.mins.x, 0.0)
    for prop in _solids_but_the_kiosk(built):
        d = _poly_to_segment(_footprint(prop).footprint, door, (trig.x, trig.y))
        assert d >= 20.0, (prop.id, prop.model, d)


def test_the_dispenser_reads_as_take_a_number(built) -> None:
    room = built.find("entry_room")
    kx, ky = ticket_kiosk_xy(room.interior)
    trig = ticket_trigger_point(room.interior, room.floor_z)
    dressing = built.find("dense_entry_take_a_number").props
    panels = [p for p in dressing if p.model == entry.PANEL]
    assert len(panels) == 1 and panels[0].solid
    panel = panels[0]
    # Behind the machine (door side is west), square to it, facing the door.
    assert panel.origin.x > kx and abs(panel.origin.y - ky) < 1.0
    assert (panel.yaw + _mount_face(panel.model)) % 360.0 == pytest.approx(180.0)
    # Tickets on the machine's top.
    assert sum(p.model == "p7_box_copy_paper_sheet" for p in dressing) >= 2
    # A drift of paper tickets at its feet, none of it solid.
    drift = built.find("dense_entry_tickets").props
    near = [p for p in drift if p.model.startswith(PAPER) and not p.solid
            and math.hypot(p.origin.x - kx, p.origin.y - ky) <= 110.0]
    assert len(near) >= 12
    assert not any(p.solid for p in drift)
    # The stanchion lane: posts on both sides of the door-to-ticket walk.
    posts = built.find("dense_entry_stanchions").props
    assert all(p.model == entry.POST for p in posts)
    assert any(p.origin.y > 0.0 for p in posts) and any(p.origin.y < trig.y for p in posts)


def test_no_entry_notice_shadows_a_bought_door(built, spots) -> None:
    """The lobby's two bought doors carry prompts a notice would shadow (the
    map-wide notice rule does not list doors)."""
    room = built.find("entry_room").interior
    doors = [Point(room.mins.x, 0.0, 0.0), Point(room.maxs.x, 0.0, 0.0)]
    for key, point in spots[1]:
        if key in entry.NOTICES:
            assert min(math.hypot(point.x - d.x, point.y - d.y) for d in doors) >= 80.0, key


# --------------------------------------------------------------------------
# The waiting room
# --------------------------------------------------------------------------
def test_the_dense_clutter_leaves_quick_revive_and_the_lane_free(built) -> None:
    """Nothing solid the pass adds stands in front of Quick Revive or in the
    block of chairs, the stanchion lane, or the east door's approach."""
    revive = built.find("perk_quick_revive").position
    for _name, prop in _added(built, "waiting"):
        if not prop.solid:
            continue
        p = _footprint(prop)
        assert math.hypot(p.x - revive.x, p.y - revive.y) >= 120.0, prop.model
        assert not (-1080.0 <= p.x <= -716.0 and -240.0 <= p.y <= 120.0), prop.model


# --------------------------------------------------------------------------
# The counter hall (windows)
# --------------------------------------------------------------------------
def test_the_counter_clutter_stays_on_the_counter(built) -> None:
    """Everything on the two tiers of the run sits inside the run's footprint."""
    face_x, back_x, y0, y1 = counter_run(FIXTURE)
    for ident in (windows.VIGNETTES["clerk_places"], windows.VIGNETTES["service_window"]):
        for prop in built.find(ident).props:
            assert not prop.solid, prop.model
            assert face_x <= prop.origin.x <= back_x + 4.0 or prop.model.startswith(
                "p7_consumer_grade_monitor"), (prop.model, prop.origin)
            assert y0 <= prop.origin.y <= y1, (prop.model, prop.origin)


# --------------------------------------------------------------------------
# The eye exam
# --------------------------------------------------------------------------
def test_the_chart_deadshot_and_the_shotgun_stay_readable_and_reachable(built) -> None:
    """Nothing the pass adds is solid within 90 of Deadshot or the shotgun
    buy, nothing at all stands in the 64 in front of either, and nothing is
    mounted over the chart."""
    deadshot = built.find("perk_deadshot").position
    shotgun = built.find("eye_wallbuy").position
    board = built.find("eye_chart").authored.box
    for name, prop in _added(built, "eye"):
        p = _footprint(prop)
        if prop.solid:
            for at in (deadshot, shotgun):
                assert math.hypot(p.x - at.x, p.y - at.y) >= 90.0, prop.model
        # the strip in front of the perk (west of it) and the buy (east of it)
        assert not (deadshot.x - 64.0 <= p.x <= deadshot.x and abs(p.y - deadshot.y) <= 30.0), prop.model
        assert not (shotgun.x <= p.x <= shotgun.x + 64.0 and abs(p.y - shotgun.y) <= 30.0), prop.model
        if name == "walls" and abs(p.y - board.maxs.y) <= 8.0:
            reach = max(p.hx, p.hy)
            assert (p.x + reach <= board.mins.x or p.x - reach >= board.maxs.x
                    or p.z_high <= board.mins.z or p.z_low >= board.maxs.z), prop.model


def test_the_stand_here_line_is_three_sheets_on_the_floor(built) -> None:
    room = built.find("eye_exam_room")
    line = built.find("dense_eye_line").props
    assert len(line) == 3 and not any(prop.solid for prop in line)
    assert len({round(prop.origin.y, 3) for prop in line}) == 1
    bottoms = {round(prop.origin.z + collision_box(prop.model)[0][2], 3) for prop in line}
    assert bottoms == {round(room.floor_z, 3)}


# --------------------------------------------------------------------------
# The photo booth
# --------------------------------------------------------------------------
def _pad(built):
    room = built.find("photo_room")
    return room.interior.centre.x, room.interior.mins.y + 72.0


def test_the_pad_the_arrival_and_the_riser_stay_empty(built) -> None:
    """The teleporter fires in 40 of the pad and lands 56 north of it; the
    riser is 32 south.  Nothing the pass adds stands in any of them."""
    px, py = _pad(built)
    riser = built.find("photo_riser").position
    keep = [(px, py, 56.0), (px, py + 56.0, 40.0), (riser.x, riser.y, 40.0)]
    floor_z = built.find("photo_room").floor_z
    for _name, prop in _added(built, "photo"):
        p = _footprint(prop)
        if prop.origin.z - floor_z > 80.0:
            continue            # on a wall, over head height
        for x, y, r in keep:
            assert math.hypot(p.x - x, p.y - y) >= r, (prop.model, p.x, p.y)


def test_no_photo_notice_stands_on_the_pad(built, spots) -> None:
    px, py = _pad(built)
    for key, point in spots[1]:
        if key in photo.NOTICES:
            assert math.hypot(point.x - px, point.y - py) >= 48.0, key


# --------------------------------------------------------------------------
# The break room
# --------------------------------------------------------------------------
def test_the_power_switch_stays_clear(built) -> None:
    """Nothing this pass adds stands within 48 of the switch, and nothing it
    adds near the switch is solid."""
    switch = built.find("break_power").position
    for _name, prop in _added(built, "break"):
        placed = _footprint(prop)
        d = math.hypot(placed.x - switch.x, placed.y - switch.y)
        assert d >= 48.0 or (d >= 40.0 and placed.z_low > switch.z + 60.0), (prop.model, d)


# --------------------------------------------------------------------------
# The records room
# --------------------------------------------------------------------------
def test_the_dense_solids_leave_the_machines_and_the_walk_free(built) -> None:
    """Nothing solid the pass adds stands in front of Speed Cola (south of
    it) or the box (north of it), or on the door-to-door walk down the
    middle of the room."""
    cola = built.find("perk_speed_cola").position
    box = built.find("records_box").position
    for _name, prop in _added(built, "records"):
        if not prop.solid:
            continue
        p = _footprint(prop)
        assert not (abs(p.x - cola.x) < 60.0 + p.hx and cola.y - 120.0 < p.y < cola.y), prop.model
        assert not (abs(p.x - box.x) < 60.0 + p.hx and box.y < p.y < box.y + 120.0), prop.model
        assert not -60.0 <= p.y <= 60.0, prop.model


# --------------------------------------------------------------------------
# The queue
# --------------------------------------------------------------------------
def test_the_dense_solids_stay_out_of_the_lanes_and_off_the_rails(built) -> None:
    """Every solid the pass adds stands against the north wall of the last
    lane, north of its walking line, west of the office door, and far from
    every rail (no step up to a rail top) and from the Pack-a-Punch.  The
    one solid up on a rail (the kit lollipop) is not floor-standing and is
    skipped."""
    room = built.find("queue_room").interior
    walk_y = queue_route(FIXTURE)[-1].y
    pap = built.find("queue_pap").position
    for _name, prop in _added(built, "queue"):
        if not prop.solid:
            continue
        p = _footprint(prop)
        if p.z_low > room.mins.z + 1.0:
            continue
        assert p.y - p.hy >= walk_y + 60.0, prop.model
        assert p.y + p.hy <= room.maxs.y, prop.model
        assert p.x + p.hx < 1140.0, prop.model
        assert math.hypot(p.x - pap.x, p.y - pap.y) >= 200.0, prop.model


def test_the_wait_estimate_rises_along_the_line(spots) -> None:
    """45 minutes at the door, 50 at the first turn, 3 hours at the second,
    and YOU ARE NEXT / NOW SERVING: 12 in sight of the Pack-a-Punch: each
    estimate stands further along the route than the one before."""
    mine = {key: point for key, point in spots[1] if key in queue.NOTICES}
    route = queue_route(FIXTURE)
    order = ("queue_wait_50", "queue_wait_3h", "queue_next")
    legs = [min(range(len(route)), key=lambda i: math.hypot(mine[k].x - route[i].x,
                                                            mine[k].y - route[i].y))
            for k in order]
    assert legs == sorted(legs) and len(set(legs)) == 3, legs


def test_the_express_lane_sends_you_to_the_back_of_the_line(built) -> None:
    """A second short hop, in the dead end, whose arrival is the queue's own
    entry; its notice is read before the pad, and the route never crosses it."""
    pad, arrival = queue.express_lane(FIXTURE)
    assert arrival == queue_route(FIXTURE)[0]
    dead = queue_dead_end(FIXTURE)
    assert pad.y == dead[-1].y and dead[-1].x < pad.x < dead[-2].x
    # nowhere on the real route comes within the pad's reach (radius 40)
    route = queue_route(FIXTURE)
    for a, b in zip(route, route[1:]):
        for t in range(0, 101):
            x = a.x + (b.x - a.x) * t / 100.0
            y = a.y + (b.y - a.y) * t / 100.0
            assert math.hypot(x - pad.x, y - pad.y) > 80.0
    names = [f.name for f in built.script.custom.functions]
    assert any(name.endswith("_express") for name in names), names


# --------------------------------------------------------------------------
# The back office
# --------------------------------------------------------------------------
def test_the_arena_floor_stays_open(built) -> None:
    """Every solid this pass adds is behind the counter or within 48 of a
    wall; out on the fighting floor there is only flat litter."""
    room = built.find("office_room")
    b_in = room.interior
    counter_north = b_in.maxs.y - FIXTURE.booth_depth
    for _name, prop in _added(built, "office"):
        placed = _footprint(prop)
        if prop.solid:
            wall = min(placed.x - b_in.mins.x, b_in.maxs.x - placed.x,
                       placed.y - b_in.mins.y, b_in.maxs.y - placed.y)
            assert placed.y > counter_north or wall <= 48.0, (prop.model, placed.x, placed.y)
        elif placed.z_low <= room.floor_z + 1.0 and placed.y < counter_north - 16.0:
            assert placed.z_high - placed.z_low <= 12.0, prop.model


def test_stamin_up_and_the_stapler_stay_clear(built) -> None:
    """Nothing this pass adds is solid within 96 of Stamin-Up or the stapler."""
    for target in ("perk_stamin_up", "office_wallbuy"):
        at = built.find(target).position
        for _name, prop in _added(built, "office"):
            placed = _footprint(prop)
            d = math.hypot(placed.x - at.x, placed.y - at.y)
            assert not prop.solid or d >= 96.0, (target, prop.model, d)
