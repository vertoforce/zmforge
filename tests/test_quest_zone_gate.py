"""A quest step behind a door waits for its zone (P8, Z61).

zm_dmv's Vision Test started at game start, 15-second timer and all, while
the eye exam room was four doors in.  Read off a committed three-room map
(start, a door to the arena, a door to the vault): the step in the vault
waits for ``zm_zonemgr::zone_is_enabled( "vault" )`` before its start line,
the HUD says the find line meanwhile, and Z61 flags a step without its gate.
"""

from __future__ import annotations

import json

import pytest

from zmforge import Project
from zmforge.recipes.layouts import three_room_map
from zmforge.script import quest as q
from zmforge.script.zonegate import door_opened, open_at_start, step_gates, zone_at
from zmforge.verify.quest_gates import (check_quest_gates, check_quest_gates_blueprint,
                                        check_quest_gates_document)

from conftest import seed_stock_weapon_table

NAME = "zm_qgate"


def _quest() -> q.Quest:
    return q.Quest(
        key="gate", header="STAMPS: &&1 OF &&2", intro="Get your stamps.",
        step_done="STAMP &&1 OF &&2", complete="All stamped.", idle="CURRENT TASK: wait",
        steps=(
            # In the start zone: nothing to wait for.
            q.StandInZone(key="lobby", task="CURRENT TASK: stand (&&1/&&2 s)", start="Stand.",
                          done="Stood.", point=(-300.0, 0.0, 0.0), seconds=5),
            # Targets in the vault, two doors in, and a timer.
            q.HitTargets(key="vision", task="CURRENT TASK: shoot the E (&&1/&&2)",
                         start="Read the chart.", done="Read.",
                         find="CURRENT TASK: Find the Vision Test room",
                         targets=(q.Target(point=(1000.0, 200.0, 60.0)),),
                         time_limit=15.0, timeout="Time's up."),
            # Hint in the arena: gated on the arena, with the default line.
            q.SurviveRounds(key="wait", task="CURRENT TASK: survive (&&1/&&2)",
                            start="Wait.", done="Waited.", rounds=1,
                            hint=q.Hint(point=(300.0, 0.0, 0.0), text="Wait here.")),
        ),
    )


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("qgate")
    blueprint = three_room_map(NAME)
    q.install_quest(blueprint, _quest())
    seed_stock_weapon_table(root)
    project = Project.create(NAME, root, blueprint=blueprint)
    result = project.commit()
    paths = project.paths()
    return {
        "blueprint": blueprint,
        "result": result,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8"),
        "document": json.loads(paths["map"].with_name(f"{NAME}.blueprint.json")
                               .read_text(encoding="utf-8")),
    }


def _body(server: str, name: str) -> str:
    start = server.index(f"function {name}(")
    return server[start: server.index("\n}\n", start) + 2]


def test_the_commit_passes_its_checks(committed) -> None:
    assert committed["result"].ok, [str(f) for f in committed["result"].report]
    assert not [f for f in committed["result"].report if f.code == "Z61"]


def test_a_step_behind_a_door_waits_for_its_zone(committed) -> None:
    vision = _body(committed["server"], "zmf_quest_step_vision")
    gate = 'zm_zonemgr::zone_is_enabled( "vault" )'
    assert gate in vision
    # Before the step is live: its state, its start line, its timer.
    assert vision.index(gate) < vision.index("level.zmf_q_state[ 1 ] = 1;")
    assert vision.index(gate) < vision.index("zmf_quest_all_0(")
    assert "level.zmf_q_locked[ 1 ] = 1;" in vision
    assert "#using scripts\\zm\\_zm_zonemgr;" in committed["server"]


def test_a_step_in_the_start_zone_does_not_wait(committed) -> None:
    assert "zone_is_enabled" not in _body(committed["server"], "zmf_quest_step_lobby")


def test_the_hint_counts_and_the_hud_says_the_find_line(committed) -> None:
    assert 'zm_zonemgr::zone_is_enabled( "arena" )' in _body(committed["server"],
                                                             "zmf_quest_step_wait")
    draw = _body(committed["server"], "zmf_quest_hud_draw")
    assert "level.zmf_q_locked[ n ]" in draw
    assert "SetText( level.zmf_quest_find[ n ] );" in draw
    assert "Find the Vision Test room" in committed["strings"]
    assert q.FIND_LINE in committed["strings"]


def test_the_steps_are_recorded_with_their_gates(committed) -> None:
    gates = {s["label"]: s["gates"] for s in committed["blueprint"].quest_steps}
    assert gates == {"quest gate step lobby": [], "quest gate step vision": ["vault"],
                     "quest gate step wait": ["arena"]}
    assert committed["document"]["engine"]["quest_steps"] == committed["blueprint"].quest_steps
    assert not list(check_quest_gates_document(committed["document"]))


def test_z61_flags_a_step_without_its_gate(committed) -> None:
    doc = json.loads(json.dumps(committed["document"]))
    for step in doc["engine"]["quest_steps"]:
        step["gates"] = []
    found = [str(f) for f in check_quest_gates_document(doc)]
    assert len(found) == 2 and all("Z61" in f for f in found)
    assert any("'vault'" in f and "step vision" in f for f in found)

    bp = committed["blueprint"]
    saved = list(bp.quest_steps)
    try:
        bp.quest_steps[:] = [dict(s, gates=[]) for s in saved]
        assert len(list(check_quest_gates_blueprint(bp))) == 2
    finally:
        bp.quest_steps[:] = saved


def test_zone_reachability() -> None:
    edges = [("start", "hall", "always_on"), ("hall", "room", "enter_room"),
             ("room", "track", "enter_track")]
    assert open_at_start(["start"], edges) == {"start", "hall"}
    assert door_opened(["start"], edges, ["enter_room"]) == {"start", "hall", "room"}
    # The track opens by a script flag, not a door: warned, never auto-gated.
    boxes = [("start", 0, 100, 0, 100, 0, 128), ("room", 100, 200, 0, 100, 0, 128),
             ("track", 200, 300, 0, 100, 0, 128)]
    assert zone_at((150, 50, 0), boxes) == "room"
    assert zone_at((500, 50, 0), boxes) is None
    assert step_gates([(50, 50, 0), (150, 50, 0), (160, 50, 0)], boxes, {"room"}) == ("room",)
    steps = [{"label": "s", "points": [[250, 50, 0]], "gates": []}]
    found = [str(f) for f in check_quest_gates(boxes, {"room"}, {"track"}, steps)]
    assert len(found) == 1 and "no door opens" in found[0]
    assert not list(check_quest_gates(boxes, {"room"}, {"track"},
                                      [dict(steps[0], gates=["track"])]))


def test_stacked_zones_pick_by_height() -> None:
    boxes = [("down", 0, 100, 0, 100, 0, 128), ("up", 0, 100, 0, 100, 128, 256)]
    assert zone_at((50, 50, 200), boxes) == "up"
    assert zone_at((50, 50, 16), boxes) == "down"


def test_a_find_line_takes_no_parameters() -> None:
    with pytest.raises(ValueError, match="find line"):
        q.SurviveRounds(key="w", task="t", start="s", done="d", rounds=1, find="round &&1")
