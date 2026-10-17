"""Visual-defect checks every map gets (``verify/looks.py``,
the hollow half of ``Z54``) and the shared dressing helpers behind them
(``zmforge.dressing``).  Each check gets a map that breaks it and one that
does not, because a check that has never fired is not evidence."""

from __future__ import annotations

import random

from zmforge.blueprint.elements import Massing, Room, Window
from zmforge.dressing import drift_points, fit_within, hang_bar, hanging_sign, no_repeat, window_keepouts
from zmforge.lettering import brush_text
from zmforge.recipes.layouts import three_room_map
from zmforge.recipes.props import MODEL_BOX
from zmforge.spatial import Bounds, Facing, Point
from zmforge.verify import check_blueprint
from zmforge.verify.looks import (
    check_floor_lettering,
    check_needs,
    check_reads_badly,
    check_window_approaches,
)
from zmforge.verify.walls import check_props_inside_walls

CRATE = "p7_zm_der_cabinet_lab_bottom"   # solid, 108 x 32
BOOKS = "p7_books_office_row_01"          # hollow shelf clutter, 12 x 12


def _map():
    bp = three_room_map("zm_looks_probe")
    room = next(r for r in bp.elements(Room) if r.id == "arena_room")
    return bp, room


# -- Z56 -------------------------------------------------------------------
def test_flat_floor_lettering_warns() -> None:
    bp, room = _map()
    brush_text(bp, "EAT ME", at=Point(0.0, 0.0, room.floor_z + 1.0), facing=Facing.NORTH,
               flat=True, ident="probe_floor_words")
    found = [f for f in check_floor_lettering(bp).warnings if f.code == "Z56"]
    assert len(found) == 1, [str(f) for f in found]
    assert "EAT ME" in str(found[0]) and "arena_room" in str(found[0])
    assert any(f.code == "Z56" for f in check_blueprint(bp).warnings)
    assert not [f for f in check_blueprint(bp).errors if f.code == "Z56"]


def test_a_hanging_sign_does_not() -> None:
    bp, room = _map()
    ids = hanging_sign(bp, "probe_hung", 0.0, 0.0, floor=room.floor_z,
                       ceiling=room.interior.maxs.z, lines=(("EAT ME", 3.0), ("NOW", 2.0)),
                       faces=(Facing.NORTH, Facing.SOUTH))
    assert ids and check_floor_lettering(bp).warnings == []
    board = next(e for e in bp.elements(Massing) if e.id == "probe_hung_board")
    assert board.authored.box.mins.z == room.floor_z + 100.0
    rods = [e for e in bp.elements(Massing) if e.id.startswith("probe_hung_rod_")]
    assert len(rods) == 2
    assert all(r.authored.box.maxs.z == room.interior.maxs.z for r in rods)


# -- Z57 -------------------------------------------------------------------
def _window(bp):
    win = next(iter(bp.elements(Window)))
    room = next(r for r in bp.elements(Room) if r.id == win.room_id)
    return win, room


def test_a_solid_in_front_of_a_barricade_window_warns() -> None:
    bp, _ = _map()
    win, room = _window(bp)
    o = win.barricade_origin
    inward = 1.0 if o.y < 0 else -1.0     # the fixture's windows are on N/S walls
    bp.place_props([(CRATE, Point(o.x, o.y + inward * 40.0, room.floor_z), 0.0, 1.0, True)],
                   id="probe_by_window")
    found = [f for f in check_window_approaches(bp).warnings if f.code == "Z57"]
    assert len(found) == 1 and win.id in str(found[0])
    assert not [f for f in check_blueprint(bp).errors if f.code == "Z57"]


def test_the_same_solid_across_the_room_does_not() -> None:
    bp, _ = _map()
    win, room = _window(bp)
    o = win.barricade_origin
    inward = 1.0 if o.y < 0 else -1.0
    bp.place_props([(CRATE, Point(o.x, o.y + inward * 140.0, room.floor_z), 0.0, 1.0, True)],
                   id="probe_off_window")
    assert check_window_approaches(bp).warnings == []


def test_window_keepouts_are_the_z57_zone_and_keep_a_placer_clear() -> None:
    bp, _ = _map()
    win, room = _window(bp)
    boxes = window_keepouts(bp)
    assert len(boxes) == len(list(bp.elements(Window)))
    o = win.barricade_origin
    inward = 1.0 if o.y < 0 else -1.0
    near = Point(o.x, o.y + inward * 40.0, room.floor_z + 8.0)
    assert any(b.mins.x <= near.x <= b.maxs.x and b.mins.y <= near.y <= b.maxs.y
               and b.mins.z <= near.z <= b.maxs.z for b in boxes)
    wide = window_keepouts(bp, approach=90.0, side=42.0, height=260.0)
    assert all(w.maxs.z - w.mins.z == 270.0 for w in wide)
    assert all((w.maxs.x - w.mins.x) * (w.maxs.y - w.mins.y) > (b.maxs.x - b.mins.x) * (b.maxs.y - b.mins.y)
               for w, b in zip(wide, boxes))


# -- Z58 -------------------------------------------------------------------
def test_a_deny_listed_model_warns_once_with_its_count() -> None:
    bp, room = _map()
    pic = "p7_3arc_lobby_picture_41x29"
    bp.place_props([(pic, Point(0.0, 0.0, room.floor_z + 80.0), 0.0, 1.0, False),
                    (pic, Point(40.0, 0.0, room.floor_z + 80.0), 0.0, 1.0, False)], id="probe_pics")
    found = check_reads_badly(bp).warnings
    assert len(found) == 1 and "2 time(s)" in str(found[0]) and "dark" in str(found[0])


def test_a_model_measured_to_draw_wrong_warns_from_the_notes() -> None:
    """Z58 reads props/notes.json too: a measured ``editor_invisible`` model
    warns; a ``review_only`` dark one (not independently checked) does not."""
    bp, room = _map()
    shirt, curved = "p7_clothes_hanging_01_tshirt", "p7_monitor_curved_military"
    bp.place_props([(shirt, Point(0.0, 0.0, room.floor_z + 90.0), 0.0, 1.0, False),
                    (curved, Point(60.0, 0.0, room.floor_z + 60.0), 0.0, 1.0, False)],
                   id="probe_notes")
    found = [str(f) for f in check_reads_badly(bp).warnings]
    assert len(found) == 1 and shirt in found[0] and "does not draw at all" in found[0], found
    assert "use build the clothes from brushes" in found[0]


def test_a_deny_listed_model_warns_once_even_with_a_note() -> None:
    bp, room = _map()
    pic = "p7_3arc_lobby_picture_41x29"          # on READS_BADLY and noted dark
    bp.place_props([(pic, Point(0.0, 0.0, room.floor_z + 80.0), 0.0, 1.0, False)], id="probe_pic")
    found = check_reads_badly(bp).warnings
    assert len(found) == 1 and "settled" in str(found[0])


# -- Z59 -------------------------------------------------------------------
DRAPE = "p7_cloth_drape_01_beige"      # category "curtain" by pattern: needs a rail
MONITOR = "p7_consumer_grade_monitor_medium"   # its own note: needs a desk


def test_a_curtain_with_no_rail_warns() -> None:
    bp, room = _map()
    bp.place_props([(DRAPE, Point(0.0, 0.0, room.floor_z + 10.0), 0.0, 1.0, False),
                    (DRAPE, Point(0.0, 100.0, room.floor_z + 10.0), 0.0, 1.0, False)],
                   id="probe_drapes")
    found = [f for f in check_needs(bp).warnings if f.code == "Z59"]
    assert len(found) == 1 and "2 time(s)" in str(found[0]) and "rail" in str(found[0])
    assert any(f.code == "Z59" for f in check_blueprint(bp).warnings)
    assert not [f for f in check_blueprint(bp).errors if f.code == "Z59"]


def test_a_curtain_under_hang_bar_does_not() -> None:
    bp, room = _map()
    z = room.floor_z + 10.0
    bp.place_props([(DRAPE, Point(0.0, 0.0, z), 0.0, 1.0, False)], id="probe_drapes")
    top = z + MODEL_BOX[DRAPE][1][2]
    hang_bar(bp, "probe_rail", (-60.0, 0.0), (60.0, 0.0), top + 1.5, ceiling=room.interior.maxs.z)
    assert check_needs(bp).warnings == []


def test_a_monitor_on_the_floor_warns_and_on_a_desk_does_not() -> None:
    bp, room = _map()
    bp.place_props([(MONITOR, Point(0.0, 0.0, room.floor_z), 0.0, 1.0, False)], id="probe_tv")
    found = [str(f) for f in check_needs(bp).warnings]
    assert len(found) == 1 and "desk" in found[0], found
    assert "chair_facing" not in found[0]          # not judged: a chair's front is unknown

    bp2, room2 = _map()
    top = room2.floor_z + 30.0
    bp2.add_block(Bounds.between((-40.0, -20.0, room2.floor_z), (40.0, 20.0, top)), "t7_metal_plate_01",
                  id="probe_desk")
    bp2.place_props([(MONITOR, Point(0.0, 0.0, top), 0.0, 1.0, False)], id="probe_tv")
    assert check_needs(bp2).warnings == []


# -- Z54, hollow half ------------------------------------------------------
def test_shelf_clutter_through_the_wall_warns_and_fit_within_fixes_it() -> None:
    bp, room = _map()
    box = room.interior
    shelf = Bounds.between((box.mins.x, 0.0, room.floor_z + 60.0),
                           (box.mins.x + 18.0, 40.0, room.floor_z + 61.0))
    # Put at the shelf's middle, turned so its 12-unit side runs into the wall.
    x, y = box.mins.x + 2.0, 20.0
    bp.place_props([(BOOKS, Point(x, y, shelf.maxs.z), 0.0, 1.0, False)], id="probe_shelf")
    found = [f for f in check_props_inside_walls(bp).warnings if f.code == "Z54"]
    assert len(found) == 1, [str(f) for f in check_props_inside_walls(bp)]
    assert check_props_inside_walls(bp).errors == []

    bp2, room2 = _map()
    fit = fit_within(BOOKS, x, y, 0.0, shelf)
    assert fit is not None
    bp2.place_props([(BOOKS, Point(fit[0], fit[1], shelf.maxs.z), fit[2], 1.0, False)],
                    id="probe_shelf")
    assert check_props_inside_walls(bp2).warnings == []


def test_floor_litter_by_the_wall_is_not_asked() -> None:
    bp, room = _map()
    box = room.interior
    bp.place_props([(BOOKS, Point(box.mins.x + 2.0, 0.0, room.floor_z), 0.0, 1.0, False)],
                   id="probe_litter")
    assert check_props_inside_walls(bp).warnings == []


# -- the shared helpers ----------------------------------------------------
def test_fit_within_turns_or_refuses() -> None:
    lo, hi = MODEL_BOX[CRATE]
    narrow = Bounds.between((0.0, 0.0, 0.0), (40.0, 200.0, 1.0))
    fit = fit_within(CRATE, 20.0, 100.0, 0.0, narrow)
    assert fit is not None and round(fit[2]) % 180 == 90       # turned to run along y
    tiny = Bounds.between((0.0, 0.0, 0.0), (20.0, 20.0, 1.0))
    assert fit_within(CRATE, 10.0, 10.0, 0.0, tiny) is None


def test_hang_bar_has_a_rod_to_the_ceiling_at_each_end() -> None:
    bp, room = _map()
    ceiling = room.interior.maxs.z
    hang_bar(bp, "probe_rail", (0.0, 0.0), (100.0, 0.0), 150.0, ceiling=ceiling)
    ids = {e.id: e for e in bp.elements(Massing) if e.id.startswith("probe_rail")}
    assert set(ids) == {"probe_rail_bar", "probe_rail_rod_0", "probe_rail_rod_1"}
    assert ids["probe_rail_rod_0"].authored.box.maxs.z == ceiling


def test_drift_points_gather_in_their_drifts() -> None:
    drifts = ((0.0, 0.0, 10.0, 10.0, 3), (500.0, 500.0, 10.0, 10.0, 1))
    pts = drift_points(random.Random(1), drifts, 40)
    assert len(pts) == 40
    assert all(abs(x) <= 10 and abs(y) <= 10 or abs(x - 500) <= 10 and abs(y - 500) <= 10
               for x, y in pts)
    near_first = sum(1 for x, _ in pts if abs(x) <= 10)
    assert near_first == 30                     # weight 3 of 4
    assert drift_points(random.Random(1), drifts, 5, lambda x, y: x > 400) and all(
        x > 400 for x, _ in drift_points(random.Random(1), drifts, 5, lambda x, y: x > 400))


def test_no_repeat_never_repeats_a_kind_twice_running() -> None:
    picks = no_repeat(("box", "twin", "bare"), 200, random.Random(3))
    assert len(picks) == 200 and set(picks) == {"box", "twin", "bare"}
    assert all(a != b for a, b in zip(picks, picks[1:]))
    assert no_repeat(("only",), 3, random.Random(0)) == ["only", "only", "only"]
