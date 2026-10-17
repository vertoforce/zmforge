"""Z60: the per-prop rules in ``props/notes.json`` (``verify/prop_rules.py``).

Each rule type gets a map that breaks it and one that keeps it, because a
check that has never fired is not evidence.  The rules come from the real
notes file wherever it has one; ``max_per_room``, ``not_in`` and a
``clearance_front`` on a model with a measured box are patched in, since no
notes entry uses them on such a model yet."""

from __future__ import annotations

import pytest

from zmforge.blueprint.elements import Room
from zmforge.props import notes
from zmforge.recipes.layouts import three_room_map
from zmforge.recipes.props import MODEL_BOX
from zmforge.spatial import Bounds, Point
from zmforge.verify import check_blueprint
from zmforge.verify.prop_rules import check_prop_rules

CHAIR = "p7_chair_lab_01"                  # front -y (seat method)
CHAIR_UNKNOWN = "p7_chair_lab_02"          # front unknown: skipped
DESK = "p7_desk_metal_military_02"         # 90 x 37 x 36
MONITOR = "p7_consumer_grade_monitor_medium"
SIGN = "p7_signage_caution_warning_01"     # front -y (back_plane), a wall sign
SCREEN = "p7_cai_monitor_wall_large"       # wall screen, 40-200 up
SINK = "p7_sink_kitchen_stainless_modern_01_clean"
PIPE = "p7_pipe_metal_hp_12_straight_64_bare"
CABINET = "p7_zm_der_cabinet_lab_bottom"   # solid, 108 x 32
TOILET = "zmf_prop_toilet"
PLATE = "t7_metal_plate_01"


def _map():
    bp = three_room_map("zm_rules_probe")
    room = next(r for r in bp.elements(Room) if r.id == "arena_room")
    return bp, room


def _rule(bp, rule: str) -> list[str]:
    return [f for f in (str(x) for x in check_prop_rules(bp).warnings) if f"]: {rule}: " in f]


@pytest.fixture
def patch_rules(monkeypatch):
    """Add rules to named models on top of the real notes file."""
    real = notes.rules_for

    def apply(extra: dict[str, dict]) -> None:
        def patched(model: str) -> dict:
            out = dict(real(model))
            out.update(extra.get(model, {}))
            return out

        monkeypatch.setattr(notes, "rules_for", patched)

    return apply


# -- the notes file ----------------------------------------------------------
def test_rules_merge_categories_under_the_model_and_null_drops_one() -> None:
    assert notes.rules_for(SIGN)["mount"] == {"on": "wall"}          # category poster_or_wall_sign
    assert notes.rules_for(SIGN)["front"] == "-y"                    # its own, measured
    exit_sign = notes.rules_for("p7_cai_signage_plastic_exit")
    assert "mount" not in exit_sign and "faces" not in exit_sign     # two-sided: dropped by null
    assert notes.front_of(CHAIR) == -90.0
    assert notes.front_of(CHAIR_UNKNOWN) is None
    assert notes.front_of("p7_zm_vending_jugg") == -90.0             # category, stock perk prefabs


def test_every_rules_block_uses_known_keys_and_every_front_says_how() -> None:
    import json

    data = json.loads(notes.NOTES_PATH.read_text())
    blocks = [(k, e.get("rules", {})) for k, e in data["models"].items()]
    blocks += [(k, e.get("rules", {})) for k, e in data["categories"].items()]
    for key, rules in blocks:
        assert set(rules) <= set(notes.RULE_KEYS), (key, set(rules) - set(notes.RULE_KEYS))
        if "front" in rules:
            assert rules["front"] in ("+x", "-x", "+y", "-y", "unknown"), key
            assert rules.get("front_how"), f"{key}: a front with no record of how it was measured"


def test_the_measured_seat_fronts_agree_with_model_front() -> None:
    from zmforge.recipes.props import MODEL_FRONT

    for model, degrees in MODEL_FRONT.items():
        assert notes.front_of(model) == degrees, model


# -- faces: a chair and its desk ---------------------------------------------
def _desk_and_chair(chair: str, yaw: float):
    bp, room = _map()
    f = room.floor_z
    bp.place_props([(DESK, Point(300.0, 0.0, f), 0.0, 1.0, True),
                    (chair, Point(300.0, 40.0, f), yaw, 1.0, True)], id="probe_office")
    return bp


def test_a_chair_with_its_back_to_the_desk_warns() -> None:
    found = _rule(_desk_and_chair(CHAIR, 180.0), "faces")
    assert len(found) == 1 and "turns its back on" in found[0], found


def test_a_chair_facing_the_desk_does_not() -> None:
    assert _rule(_desk_and_chair(CHAIR, 0.0), "faces") == []


def test_a_chair_whose_front_is_unknown_is_not_judged() -> None:
    assert _rule(_desk_and_chair(CHAIR_UNKNOWN, 180.0), "faces") == []


# -- faces: room -------------------------------------------------------------
def _wall_sign(yaw: float):
    bp, room = _map()
    wall = room.interior.maxs.y
    bp.place_props([(SIGN, Point(300.0, wall, room.floor_z + 90.0), yaw, 1.0, False)], id="probe_sign")
    return bp


def test_a_sign_facing_its_wall_warns() -> None:
    found = _rule(_wall_sign(180.0), "faces")
    assert len(found) == 1 and "faces the wall" in found[0], found


def test_a_sign_facing_the_room_does_not() -> None:
    assert _rule(_wall_sign(0.0), "faces") == []


# -- mount -------------------------------------------------------------------
def test_a_wall_sign_in_mid_air_warns_and_on_the_wall_does_not() -> None:
    bp, room = _map()
    bp.place_props([(SIGN, Point(300.0, 0.0, room.floor_z + 90.0), 0.0, 1.0, False)], id="probe_sign")
    found = _rule(bp, "mount")
    assert len(found) == 1 and "free of any wall" in found[0], found
    assert _rule(_wall_sign(0.0), "mount") == []


def test_a_wall_screen_above_its_band_warns_and_at_eye_height_does_not() -> None:
    for up, trips in ((300.0, True), (100.0, False)):
        bp, room = _map()
        bp.place_props([(SCREEN, Point(300.0, room.interior.maxs.y, room.floor_z + up), 0.0, 1.0, False)],
                       id="probe_screen")
        found = _rule(bp, "mount")
        assert bool(found) is trips, (up, found)
        if trips:
            assert "outside 40-200" in found[0]


# -- faced_by: a desk monitor and its seat -----------------------------------
def _monitor(chair_yaw: float | None):
    bp, room = _map()
    f = room.floor_z
    top = f + MODEL_BOX[DESK][1][2]
    items = [(DESK, Point(300.0, 0.0, f), 0.0, 1.0, True),
             (MONITOR, Point(300.0, 0.0, top), 0.0, 1.0, False)]
    if chair_yaw is not None:
        items.append((CHAIR, Point(300.0, 40.0, f), chair_yaw, 1.0, True))
    bp.place_props(items, id="probe_desk")
    return bp


def test_a_desk_monitor_with_no_seat_warns() -> None:
    found = _rule(_monitor(None), "faced_by")
    assert len(found) == 1 and "no seat within" in found[0], found


def test_a_desk_monitor_whose_seat_looks_away_warns() -> None:
    found = _rule(_monitor(180.0), "faced_by")
    assert len(found) == 1 and "no seat faces it" in found[0], found


def test_a_desk_monitor_with_a_seat_facing_it_does_not() -> None:
    assert _rule(_monitor(0.0), "faced_by") == []


# -- clearance_front ---------------------------------------------------------
def test_a_machine_with_something_in_front_warns_and_a_clear_one_does_not(patch_rules, past_the_lane_rule) -> None:
    patch_rules({CABINET: {"front": "-y", "front_how": "test", "clearance_front": 32}})
    for blocked in (True, False):
        bp, room = _map()
        f = room.floor_z
        items = [(CABINET, Point(300.0, 400.0, f), 0.0, 1.0, True)]
        if blocked:
            items.append((DESK, Point(300.0, 360.0, f), 0.0, 1.0, True))
        bp.place_props(items, id="probe_machine")
        found = [x for x in _rule(bp, "clearance_front") if CABINET in x]
        assert bool(found) is blocked, found


# -- needs_near: a sink and its legs -----------------------------------------
def test_a_sink_with_nothing_under_it_warns_and_on_legs_does_not() -> None:
    for legs in (False, True):
        bp, room = _map()
        wall, f = room.interior.maxs.y, room.floor_z
        bp.place_props([(SINK, Point(300.0, wall, f + 36.0), 0.0, 1.0, False)], id="probe_sink")
        if legs:
            under = f + 36.0 + MODEL_BOX[SINK][0][2]
            bp.add_block(Bounds.between((280.0, wall - 24.0, f), (320.0, wall - 2.0, under)), PLATE,
                         id="probe_sink_legs")
        found = _rule(bp, "needs_near")
        assert bool(found) is not legs, found
        if found:
            assert "legs or a counter" in found[0]


# -- connects: a pipe run ----------------------------------------------------
def test_a_pipe_run_in_mid_air_warns_and_one_from_the_floor_does_not() -> None:
    for up, trips in ((100.0, True), (0.0, False)):
        bp, room = _map()
        f = room.floor_z
        bp.place_props([(PIPE, Point(300.0, 0.0, f + up), 0.0, 1.0, False),
                        (PIPE, Point(300.0, 0.0, f + up + 64.0), 0.0, 1.0, False)], id="probe_pipes")
        found = _rule(bp, "connects")
        assert bool(found) is trips, (up, found)
        if trips:
            assert "a run of 2 piece(s)" in found[0]


# -- max_per_room and not_in -------------------------------------------------
def _toilets(n: int):
    bp, room = _map()
    bp.place_props([(TOILET, Point(100.0 + 60.0 * i, 0.0, room.floor_z), 0.0, 1.0, True) for i in range(n)],
                   id="probe_toilets")
    return bp


def test_max_per_room(patch_rules) -> None:
    patch_rules({TOILET: {"max_per_room": 1}})
    found = _rule(_toilets(2), "max_per_room")
    assert len(found) == 1 and "2 in one room, at most 1" in found[0], found
    assert _rule(_toilets(1), "max_per_room") == []


def test_not_in(patch_rules) -> None:
    patch_rules({TOILET: {"not_in": ["arena"]}})
    found = _rule(_toilets(1), "not_in")
    assert len(found) == 1 and "arena_room" in found[0], found
    patch_rules({TOILET: {"not_in": ["kitchen"]}})
    assert _rule(_toilets(1), "not_in") == []


# -- assembly: the scarecrow's parts -----------------------------------------
def test_scarecrow_parts_apart_warn_and_together_do_not() -> None:
    for apart, trips in ((60.0, True), (0.0, False)):
        bp, room = _map()
        f = room.floor_z
        bp.add_block(Bounds.between((296.0, -4.0, f), (304.0, 4.0, f + 90.0)), PLATE, id="probe_scarecrow_pole")
        bp.add_block(Bounds.between((270.0 + apart, -2.0, f + 60.0), (330.0 + apart, 2.0, f + 64.0)), PLATE,
                     id="probe_scarecrow_arms")
        found = _rule(bp, "assembly")
        assert bool(found) is trips, (apart, found)
        if trips:
            assert "probe_scarecrow_arms" in found[0]


# -- the check as a whole ----------------------------------------------------
def test_z60_is_a_warning_in_check_blueprint() -> None:
    bp = _desk_and_chair(CHAIR, 180.0)
    report = check_blueprint(bp)
    assert any(f.code == "Z60" for f in report.warnings)
    assert not [f for f in report.errors if f.code == "Z60"]
