"""The play-structure checks of docs/map-design-method.md section 8
(``verify/design.py``, D1-D6) and the scene's cause and telling detail (S1).
Each check gets a map that trips it and one that does not, because a check
that has never fired is not evidence."""

from __future__ import annotations

from zmforge.blueprint.elements import Lamp, Room
from zmforge.dressing import declare_scene
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Point, Span
from zmforge.verify import check_blueprint
from zmforge.verify.design import (
    check_clean_fronts,
    check_lock_before_key,
    check_play_lighting,
    check_training_loops,
    points_to_core,
    training_rings,
)
from zmforge.verify.scenes import check_scenes

CABINET = "p7_zm_der_cabinet_lab_bottom"   # 108 x 32, taller than a step


def _map():
    bp = three_room_map("zm_design_probe")
    rooms = {r.id: r for r in bp.elements(Room)}
    return bp, rooms


def _without_play_lamps(bp):
    """The map as a recipe that forgot its buyables' lamps would leave it.

    ``Blueprint.light_rooms`` gives every unlit door and buyable a play lamp
    (:func:`zmforge.blueprint.autolamp.light_play`), so a
    generated map never has the gap D5 looks for; these tests take those
    lamps back out to show the check still finds one.
    """
    from zmforge.blueprint.elements import Lamp

    gone = [e for e in bp._elements if isinstance(e, Lamp) and e.id.endswith("_play_lamp")]
    assert gone, "no play lamps to remove: light_play changed"
    for lamp in gone:
        bp._elements.remove(lamp)
        bp._by_id.pop(lamp.id, None)
    return bp


def _pillar(bp, room, half=128.0):
    c = room.interior.centre
    bp.add_block(Span(Point(c.x - half, c.y - half, room.floor_z),
                      Point(c.x + half, c.y + half, room.floor_z + 128.0)),
                 "t7_concrete_wall_dark_01", id="probe_pillar")


# -- D1 training loop ------------------------------------------------------------
def test_an_open_arena_has_no_training_ring() -> None:
    bp, _ = _map()
    found = [f for f in check_training_loops(bp).warnings if f.element_id == "arena"]
    assert len(found) == 1 and "no closed ring" in found[0].message
    assert any(f.code == "D1" for f in check_blueprint(bp).warnings)
    assert not [f for f in check_blueprint(bp).errors if f.code == "D1"]


def test_a_pillar_with_wide_lanes_round_it_is_a_training_ring() -> None:
    bp, rooms = _map()
    _pillar(bp, rooms["arena_room"])
    rings = training_rings(bp)["arena"]
    assert rings and rings[0]["length"] >= 1000.0
    assert not [f for f in check_training_loops(bp).warnings if f.element_id == "arena"]


def test_a_block_that_leaves_narrow_lanes_is_not_a_ring() -> None:
    bp, rooms = _map()
    arena = rooms["arena_room"]
    # 864 wide: a 700 block leaves 82-unit lanes, under the 128 a ring needs.
    _pillar(bp, arena, half=350.0)
    assert [f for f in check_training_loops(bp).warnings if f.element_id == "arena"]


# -- D3 points to core -------------------------------------------------------------
def test_points_to_core_reports_the_cheapest_door_spend() -> None:
    bp, _ = _map()
    core = points_to_core(bp)
    assert core["juggernog"]["door_spend"] == 500
    assert core["juggernog"]["via"] == ["door_start_arena"]
    assert core["quick_revive"]["door_spend"] == 500
    assert core["power"]["door_spend"] == 2000
    assert core["first_box"]["zone"] in ("start", "arena", "vault")
    assert "no threshold" in core["note"]


# -- D4 lock before key ------------------------------------------------------------
def test_a_lock_deeper_than_its_first_key_warns() -> None:
    bp, _ = _map()
    bp.quest_locks = [{"label": "quest q step s desk", "lock": [1100.0, 0.0, 32.0],
                       "keys": [[300.0, 0.0, 32.0], [1000.0, 100.0, 32.0]]}]
    found = check_lock_before_key(bp).warnings
    assert len(found) == 1 and found[0].code == "D4"
    assert "zone vault" in found[0].message and "zone arena" in found[0].message
    assert any(f.code == "D4" for f in check_blueprint(bp).warnings)


def test_a_lock_seen_first_passes() -> None:
    bp, _ = _map()
    bp.quest_locks = [{"label": "quest q step s desk", "lock": [300.0, 0.0, 32.0],
                       "keys": [[1100.0, 0.0, 32.0]]}]
    assert check_lock_before_key(bp).warnings == []


def test_a_recipe_quest_records_its_locks() -> None:
    from zmforge.review.facts import build_blueprint

    bp, quests, _ = build_blueprint("dmv")
    locks = getattr(bp, "quest_locks", [])
    assert quests and locks
    assert all(len(lock["lock"]) == 3 and lock["keys"] for lock in locks)


# -- D5 light the play first ------------------------------------------------------
def test_an_unlit_buyable_warns() -> None:
    bp, _ = _map()
    _without_play_lamps(bp)
    found = [f for f in check_play_lighting(bp, rings={}).warnings
             if "no lamp within" in f.message]
    assert any("pack_a_punch" in f.message for f in found)


def test_a_buyable_lit_dimmer_than_filler_warns_and_lit_brighter_passes() -> None:
    bp, _ = _map()
    jugg = Point(48.0, -336.0, 16.0)
    for lamp in bp.elements(Lamp):
        if abs(lamp.position.x - jugg.x) < 192.0 and abs(lamp.position.y - jugg.y) < 192.0:
            lamp.stops = 10.0   # every lamp on it, dimmer than the fill beyond
    msgs = [f.message for f in check_play_lighting(bp, rings={}).warnings]
    assert any("dimmer than the filler" in m and "juggernog" in m for m in msgs)
    bp.place_light(Point(jugg.x, jugg.y + 40.0, 200.0), stops=20.0, id="probe_bright")
    msgs = [f.message for f in check_play_lighting(bp, rings={}).warnings]
    assert not any("dimmer than the filler" in m and "juggernog machine" in m for m in msgs)


def test_a_dark_training_ring_warns() -> None:
    bp, _ = _map()
    rings = {"far": [{"length": 2000.0, "centre": (9000.0, 9000.0), "floor": 16.0}]}
    msgs = [f.message for f in check_play_lighting(bp, rings=rings).warnings]
    assert any("training ring" in m for m in msgs)
    rings = {"far": [{"length": 2000.0, "centre": (320.0, 0.0), "floor": 16.0}]}
    msgs = [f.message for f in check_play_lighting(bp, rings=rings).warnings]
    assert not any("training ring" in m for m in msgs)


def test_a_dark_gap_on_the_way_to_a_buyable_warns_and_lamps_clear_it() -> None:
    bp, _ = _map()
    _without_play_lamps(bp)
    msgs = [f.message for f in check_play_lighting(bp, rings={}).warnings
            if "dark gap" in f.message]
    assert any("vault_room" in m for m in msgs)
    for n, x in enumerate(range(800, 1300, 150)):
        for m, y in enumerate((-160.0, 0.0, 160.0)):
            bp.place_light(Point(float(x), y, 200.0), id=f"probe_vault_{n}_{m}")
    msgs = [f.message for f in check_play_lighting(bp, rings={}).warnings
            if "dark gap" in f.message]
    assert not any("vault_room" in m for m in msgs)


# -- D6 clean fronts ---------------------------------------------------------------
def test_tall_dressing_in_front_of_a_perk_warns(past_the_lane_rule) -> None:
    bp, _ = _map()
    # Juggernog stands at (48, -336) facing north: its front runs north.
    bp.place_props([(CABINET, Point(48.0, -270.0, 16.0), 0.0, 1.0, False)], id="probe_front")
    found = [f for f in check_clean_fronts(bp).warnings if "juggernog" in f.message]
    assert len(found) == 1 and CABINET in found[0].message
    assert any(f.code == "D6" for f in check_blueprint(bp).warnings)


def test_dressing_beside_a_perk_passes() -> None:
    bp, _ = _map()
    bp.place_props([(CABINET, Point(300.0, 0.0, 16.0), 0.0, 1.0, False)], id="probe_front")
    assert not [f for f in check_clean_fronts(bp).warnings if "juggernog" in f.message]


# -- S1 cause and telling detail --------------------------------------------------
def test_a_missing_telling_detail_warns_and_a_placed_one_passes() -> None:
    bp, rooms = _map()
    arena = rooms["arena_room"]
    declare_scene(bp, arena, "The lab tech ran; the cabinet he emptied still stands open.",
                  cause="the tech fled the outbreak", tell="cabinet_lab")
    msgs = [f.message for f in check_scenes(bp).findings if f.code == "S1"]
    assert any("telling detail 'cabinet_lab'" in m and "tech fled" in m for m in msgs)
    bp.place_props([(CABINET, Point(300.0, 300.0, 16.0), 0.0)], id="probe_tell")
    msgs = [f.message for f in check_scenes(bp).findings if f.code == "S1"]
    assert not any("telling detail" in m for m in msgs)


def test_a_cause_without_a_tell_warns() -> None:
    bp, rooms = _map()
    scene = declare_scene(bp, rooms["arena_room"], "Something broke out.", cause="the vault")
    assert scene.cause == "the vault" and scene.tell is None
    msgs = [f.message for f in check_scenes(bp).findings if f.code == "S1"]
    assert any("names a cause" in m for m in msgs)
