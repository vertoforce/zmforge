"""P22: the gamble machine (``script/gamble.py``, ``dressing/gamble.py``,
check ``Z87``): 2,000 for a 1 in 4 chance at 10,000, once per player per round,
at the farthest walk from the spawn."""

from __future__ import annotations

import re

import pytest

from zmforge import Project
from zmforge.dressing.gamble import (SignatureGamble, place_gamble_machine,
                                     walking_distances)
from zmforge.recipes.layouts import three_room_map
from zmforge.script import gamble
from zmforge.script.gsc import scan
from zmforge.script.symbols import unresolved
from zmforge.spatial import Facing, Point
from zmforge.verify.gamble import check_gamble_script
from zmforge.verify.report import Report

from conftest import seed_stock_weapon_table


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("gamble")
    seed_stock_weapon_table(root)
    bp = three_room_map("zm_gamble")
    project = Project.create("zm_gamble", root, blueprint=bp)
    result = project.commit(force=True, loading_screen=False)
    server = project.paths()["server_script"].read_text()
    return bp, result, server


def _body(server: str) -> str:
    start = server.index("function zmf_gamble(")
    return server[start:server.index("\n}\n", start)]


def test_the_default_odds_cost_and_prize() -> None:
    assert (gamble.COST, gamble.PRIZE, gamble.WINS, gamble.OUT_OF) == (2000, 10000, 1, 4)
    assert gamble.PER_ROUND == 1


def test_the_prompt_says_the_deal(committed) -> None:
    bp, _result, _server = committed
    assert bp.map_strings["ZMF_GAMBLE_PROMPT"] == (
        "Hold ^3[{+activate}]^7 to gamble 2,000 for a 1 in 4 chance at 10,000")


def test_the_script_checks_then_charges_then_draws_exact_odds(committed) -> None:
    _bp, _result, server = committed
    body = _body(server)
    check = body.index("zm_score::can_player_purchase( 2000 )")
    charge = body.index("zm_score::minus_to_player_score( 2000 )")
    draw = body.index("RandomInt( 4 ) < 1")
    pay = body.index("zm_score::add_to_player_score( 10000 )")
    # Affordability first (no negative points), then the charge, then the
    # uniform draw over 0..3 (exactly 1 in 4), then the prize.
    assert check < charge < draw < pay
    assert body.count("minus_to_player_score") == 1
    assert body.count("add_to_player_score") == 1
    # No wait between the checks and the payment: presses cannot interleave.
    after = body[body.index('waittill( "trigger"') + len('waittill( "trigger"'):draw]
    assert not re.search(r"\bwait\b", after)


def test_once_per_player_per_round(committed) -> None:
    body = _body(committed[2])
    limit = body.index("e_who.zmf_gamble_plays >= 1")
    assert "e_who.zmf_gamble_round != level.round_number" in body
    assert limit < body.index("minus_to_player_score")
    assert "e_who.zmf_gamble_plays = e_who.zmf_gamble_plays + 1;" in body


def test_lines_go_to_the_player_and_the_win_feed_to_the_rest(committed) -> None:
    body = _body(committed[2])
    assert "IPrintLnBold" in body
    assert not re.search(r"^\s*IPrintLnBold", body, re.M)  # never a global bold line
    assert "a_players[ i ] != e_who" in body


def test_the_script_scans_clean(committed) -> None:
    source = scan(committed[2])
    assert source.issues == []
    assert unresolved(source) == []


def test_commit_places_one_machine_with_no_errors(committed) -> None:
    bp, result, server = committed
    assert bp.gamble_machine is not None
    assert bp.gamble_machine.room_id == "vault_room"
    assert not [f for f in result.report.errors if f.code == "Z87"]
    report = Report()
    check_gamble_script(server, report)
    assert not report.errors and not report.warnings


def test_it_goes_to_the_farthest_walk() -> None:
    bp = three_room_map("zm_gamble_far")
    walk = walking_distances(bp)
    placed = place_gamble_machine(bp)
    far = max(walk.dist.values())
    # The stand is within a room's width of the farthest floor there is.
    assert placed.walk is not None and placed.walk > 0.6 * far


def test_placing_twice_adds_nothing() -> None:
    bp = three_room_map("zm_gamble_twice")
    first = place_gamble_machine(bp)
    n = len(bp.elements())
    assert place_gamble_machine(bp) is first and len(bp.elements()) == n


def test_a_recipe_can_opt_out_or_pin_and_retune() -> None:
    bp = three_room_map("zm_gamble_off")
    bp.signature_gamble = False
    assert place_gamble_machine(bp) is None and bp.gamble_failure == "opted out"
    bp = three_room_map("zm_gamble_pin")
    bp.signature_gamble = SignatureGamble(per_round=2, name="JACKPOT")
    placed = place_gamble_machine(bp)
    body = next(f for f in bp.script.custom.functions if f.name == "zmf_gamble").body
    assert any("zmf_gamble_plays >= 2" in line for line in body)
    assert placed is not None
    with pytest.raises(ValueError):
        gamble.gamble_script(Point(0, 0, 0), gamble.GambleLines("a", "b", "c", "d", "e"),
                             wins=4, out_of=4)


def test_the_files_check_refuses_a_charge_without_a_check() -> None:
    report = Report()
    check_gamble_script("function zmf_gamble()\n{\n\te zm_score::minus_to_player_score( 2000 );"
                        "\n\tif ( RandomInt( 4 ) < 1 )\n\t{\n\t}\n}\n", report)
    assert [f.code for f in report.errors] == ["Z87"]


def test_the_custom_model_faces_the_room() -> None:
    from zmforge.blueprint.elements import PropScatter

    bp = three_room_map("zm_gamble_atm")
    bp.signature_gamble = SignatureGamble(model="zmf_prop_gamble_atm")
    placed = place_gamble_machine(bp)
    prop = next(p for s in bp.elements(PropScatter) if s.id == "gamble_machine"
                for p in s.props)
    # The model's front is -Y at yaw 0 (props/atm.py); turned by yaw it must
    # point the way the machine faces.
    import math
    front = (math.sin(math.radians(prop.yaw)), -math.cos(math.radians(prop.yaw)))
    step = placed.facing.step
    assert abs(front[0] - step.x) < 1e-6 and abs(front[1] - step.y) < 1e-6
    assert not [m for m in bp.elements() if m.id.startswith("gamble_sign")]
