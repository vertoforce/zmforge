"""zm_dmv's ending (:mod:`zmforge.recipes.dmv_quest`): four registrations,
THE EXAMINER, and the 20,000-point front door.

Placement is measured against the built blueprint (the same rules the
notices live under in ``tests/test_dmv.py``); wiring is read off the
committed server script.  Nothing here is an observation of play.
"""

from __future__ import annotations

import re

import math

import pytest

from zmforge import Project
from zmforge.blueprint.elements import (
    Door, Machine, MysteryBox, PowerSwitch, Room, WallWeapon, Window,
)
from zmforge.recipes import dmv_of_the_damned
from zmforge.recipes.dmv import all_notices, lot_walk, ticket_trigger_point, FIXTURE
from zmforge.recipes.dmv_quest import (
    FORMS_BAY, EXIT_PRICE, FORMS_TIME_LIMIT, PHOTO_TIME_LIMIT, UNLOCK_ROUNDS,
    VISION_TIME_LIMIT, register_quest, use_points,
)
from zmforge.script import quest as q
from zmforge.script.gsc import scan
from zmforge.script.symbols import unresolved
from zmforge.verify.reachability import flood_from_spawn

from conftest import seed_stock_weapon_table

MAP_NAME = "zm_dmv"
ROOM_IDS = {"lot": "lot_room", "entry": "entry_room", "waiting": "waiting_room",
            "windows": "windows_room", "eye": "eye_exam_room", "photo": "photo_room",
            "break": "break_room", "records": "records_room", "queue": "queue_room",
            "office": "office_room"}


def _wired(bp) -> bool:
    return any(ref == "Q_REGISTER_HEADER" for ref in bp.map_strings)


def _build():
    """The DMV with its quest: the recipe's own wiring once it has it, the
    same call made here until then."""
    bp = dmv_of_the_damned(MAP_NAME)
    rooms = {key: bp.find(rid) for key, rid in ROOM_IDS.items()}
    quest = register_quest(FIXTURE, rooms, walk_top=lot_walk(FIXTURE, rooms["lot"])[0])
    if not _wired(bp):
        q.install_quest(bp, quest)
    return bp, rooms, quest


@pytest.fixture(scope="module")
def built():
    return _build()


@pytest.fixture(scope="module")
def committed(tmp_path_factory, built):
    bp, _rooms, _quest = built
    root = tmp_path_factory.mktemp("dmv_quest")
    seed_stock_weapon_table(root)
    project = Project.create(MAP_NAME, root, blueprint=bp)
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8"),
        "manifest": paths["manifest"].read_text(encoding="utf-8"),
    }


def _body(server: str, name: str) -> str:
    start = server.index(f"function {name}(")
    return server[start: server.index("\n}\n", start) + 2]


def test_the_map_commits_clean_with_its_quest(committed) -> None:
    assert committed["result"].report.errors == [], [
        str(e) for e in committed["result"].report.errors]
    source = scan(committed["server"])
    assert source.issues == []
    assert unresolved(source) == []
    assert "level thread zmf_quest_init();" in committed["server"]


def test_four_registrations_in_order_at_four_times(built, committed) -> None:
    _bp, _rooms, quest = built
    assert [s.key for s in quest.steps] == ["vision", "photo", "written", "number", "road"]
    assert [type(s).__name__ for s in quest.steps] == [
        "HitTargets", "HitTargets", "CollectDeliver", "EveryPlayerFlag", "DefeatBoss"]
    # The Examiner is still the last stamp before the exit.
    assert quest.steps[-1].key == "road" and quest.exit is not None
    # Every step after the first two tells a player where to go.
    assert all(s.hint is not None for s in quest.steps[2:])
    assert [s.unlock_round for s in quest.steps] == list(UNLOCK_ROUNDS)
    assert quest.steps[0].mode == "shoot" and quest.steps[0].ordered
    assert quest.steps[1].mode == "melee" and quest.steps[1].flash is not None
    server = committed["server"]
    for prev, key in enumerate(("photo", "written", "number", "road")):
        assert f"while ( level.zmf_q_state[ {prev} ] != 2 )" in _body(server, f"zmf_quest_step_{key}")


def test_every_line_ships(built, committed) -> None:
    _bp, _rooms, quest = built
    for ref, (text, kind) in q.quest_strings(quest).items():
        assert f'#precache( "{kind}", "ZM_DMV_{ref}" );' in committed["server"], ref
        assert text in committed["strings"], ref
    assert "xmodel,p7_office_paper_folder_blue" in committed["manifest"]


def test_the_exit_sells_the_win_for_twenty_thousand(committed) -> None:
    exit_ = _body(committed["server"], "zmf_quest_exit")
    assert f"zm_score::can_player_purchase( {EXIT_PRICE} )" in exit_
    assert EXIT_PRICE == 20000
    assert "YOU ARE FREE TO GO" in committed["strings"]
    assert "You are free to go. Please drive safely." in committed["strings"]
    assert "level.custom_game_over_hud_elem = &zmf_quest_win_hud;" in committed["server"]


def test_the_examiner_waits_in_the_back_office(built, committed) -> None:
    _bp, rooms, quest = built
    road = quest.steps[4]
    office = rooms["office"].interior
    for x, y, _z in (road.boss.spawn_at, road.arena):
        assert office.holds_flat(x, y)
    assert road.boss.name == "THE EXAMINER"
    assert "zmf_boss_examiner_spawn" in committed["server"]


def test_targets_sit_on_the_props_they_name(built) -> None:
    _bp, rooms, quest = built
    eye = rooms["eye"].interior
    rows = [t.point for t in quest.steps[0].targets]
    assert all(eye.holds_flat(x, y) for x, y, _ in rows)
    cam = quest.steps[1].targets[0].point
    assert rooms["photo"].interior.holds_flat(cam[0], cam[1])


def test_vision_targets_are_the_drawn_letters_e_f_p(built) -> None:
    """Each Vision Test spot is the centre of the chart letter it names, just
    in front of the letter's face, with a radius of half the letter's height;
    the letters shrink top down; decoys share rows 2 and 3."""
    from zmforge.blueprint.elements import Massing
    from zmforge.recipes.dmv_rooms.eye import VISION_LETTERS, chart_letters

    bp, rooms, quest = built
    eye = rooms["eye"]
    letters = chart_letters(eye.interior, eye.floor_z)
    targets = quest.steps[0].targets
    assert "".join(
        next(l.char for l in letters if (l.row, l.col) == rc) for rc in VISION_LETTERS
    ) == "EFP"
    heights = []
    for target, rc in zip(targets, VISION_LETTERS, strict=True):
        letter = next(l for l in letters if (l.row, l.col) == rc)
        x, y, z = target.point
        assert letter.x0 < x < letter.x1 and letter.z0 < z < letter.z1
        assert abs(x - (letter.x0 + letter.x1) / 2) < 1e-6
        assert abs(z - (letter.z0 + letter.z1) / 2) < 1e-6
        assert 0.0 < letter.face_y - y <= 1.0       # just in front of the ink
        assert target.radius == pytest.approx(letter.height / 2.0)
        heights.append(letter.height)
        # the ink is really there: one of the placed brushes covers the
        # letter's middle column at the target's height band
        ids = {m.id for m in bp.elements(Massing)}
        assert any(i.startswith(f"eye_chart_{rc[0]}_{rc[1]}_{letter.char.lower()}_") for i in ids)
    assert heights == sorted(heights, reverse=True) and heights[-1] <= 10.0
    # decoys: row 2 has a P beside the F, row 3 has three other letters
    assert [l.char for l in letters if l.row == 1] == ["F", "P"]
    row3 = [l.char for l in letters if l.row == 2]
    assert row3.count("P") == 1 and len(row3) >= 4
    # no target's circle reaches a neighbouring letter's centre
    for target in targets:
        for l in letters:
            c = l.centre
            if c == target.point:
                continue
            assert sum((a - b) ** 2 for a, b in zip(c, target.point)) > target.radius ** 2


def test_the_vision_lines_reach_everyone(built, committed) -> None:
    """The start line and each next-letter cue go to every player through
    the quest's own sayer, not the rate-limited gag sayer or a radius."""
    _bp, _rooms, quest = built
    server = committed["server"]
    body = server[server.index("function zmf_quest_step_vision("):]
    body = body[: body.index("zmf_quest_finish")]
    assert body.count("zmf_quest_all_0(") >= 4       # start + three cues
    assert "zmf_gag_say" not in body


def test_no_quest_trigger_stands_where_a_purchase_is_made(built) -> None:
    """The notice rule from tests/test_dmv.py: every use trigger the quest
    spawns is 80 units from every purchase, door, barrier, notice, the
    ticket machine and each other, in a room, on floor the spawn reaches."""
    bp, rooms, quest = built
    others = [(e.id, e.position) for cls in (Machine, WallWeapon, PowerSwitch, MysteryBox)
              for e in bp.elements(cls)]
    others += [(w.id, w.barricade_origin) for w in bp.elements(Window)]
    others += [(d.id, d.box.centre) for d in bp.elements(Door)]
    entry = rooms["entry"]
    others.append(("ticket", ticket_trigger_point(entry.interior, entry.floor_z)))
    _lines, spots = all_notices(FIXTURE, rooms)
    others += [(f"notice:{key}", point) for key, point in spots]
    flood = flood_from_spawn(bp)
    points = use_points(quest)
    assert len(points) == 5
    for point in points:
        near = min((math.hypot(point.x - o.x, point.y - o.y), name) for name, o in others)
        assert near[0] >= 80.0, (point, near)
        inside = [r.id for r in bp.elements(Room) if r.interior.holds_flat(point.x, point.y)]
        assert len(inside) == 1, (point, inside)
        assert flood.under(point.x, point.y, point.z + 4.0, only_reached=True) is not None, point
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            assert math.hypot(a.x - b.x, a.y - b.y) >= 80.0, (a, b)


def test_the_forms_go_in_the_tray_two_bays_from_the_window(built) -> None:
    from zmforge.recipes.dmv import bay_centres, window_opening

    _bp, _rooms, quest = built
    desk = quest.steps[2].deliver_at
    assert desk[1] == bay_centres(FIXTURE)[FORMS_BAY - 1]
    y0, y1 = window_opening(FIXTURE)
    assert not y0 <= desk[1] <= y1
    assert quest.steps[2].deliver_prompt.startswith("FORMS IN-TRAY")


def test_called_holder_must_be_at_the_one_window_within_three_seconds(built, committed) -> None:
    """The DMV's core mechanic, kept when the hall went to one window: when your number is called you have 3 seconds to stand at
    the (single) service window to be served."""
    from zmforge.recipes.dmv import (TICKET_GRACE_SECONDS, TICKET_WINDOW_RADIUS,
                                     counter_run, ticket_window_point, window_y)

    _bp, rooms, _quest = built
    assert TICKET_GRACE_SECONDS == 3.0
    point = ticket_window_point(FIXTURE, rooms)
    assert point.y == window_y(FIXTURE)
    assert point.x == counter_run(FIXTURE)[0] - 60.0
    server = committed["server"]
    caller = _body(server, "zmf_ticket_caller")
    assert "n_end = gettime() + 3000;" in caller
    assert "e_called zmf_ticket_at_window()" in caller
    at = _body(server, "zmf_ticket_at_window")
    win = f"( {point.x:g}, {point.y:g}, {point.z:g} )"
    assert f"Distance2DSquared( self.origin, {win} ) > {TICKET_WINDOW_RADIUS ** 2:g}" in at


# -- Take a Number: every player served at the window ----------------------
def test_take_a_number_opens_with_the_calls_and_needs_everyone(built, committed) -> None:
    from zmforge.recipes.dmv import TICKET_OPEN_ROUND, TICKET_GRACE_SECONDS
    from zmforge.script.tricks import TICKET_SERVED_FLAG

    _bp, _rooms, quest = built
    step = next(s for s in quest.steps if s.key == "number")
    assert step.unlock_round == TICKET_OPEN_ROUND == 5
    assert step.flag == TICKET_SERVED_FLAG
    assert "no number, no service" in step.hint.text
    assert "Served: &&1 of &&2" in step.task
    assert f"within {TICKET_GRACE_SECONDS:g} s" in step.task
    body = _body(committed["server"], "zmf_quest_step_number")
    # Opens at round 5, after the Written Test.
    assert "while ( level.round_number < 5 )" in body
    assert "while ( level.zmf_q_state[ 2 ] != 2 )" in body
    # Counts everyone present every half second: late joiners raise the
    # total, a player who left drops out, a downed one still counts.
    assert "a_players = getplayers();" in body
    assert f"if ( isdefined( a_players[ j ].{TICKET_SERVED_FLAG} ) )" in body
    assert "level.zmf_q_of[ 3 ] = a_players.size;" in body
    assert "if ( a_players.size > 0 && n >= a_players.size )" in body
    assert "laststand" not in body
    # The ticket window sets the same flag the step counts.
    assert f"e_called.{TICKET_SERVED_FLAG} = 1;" in _body(committed["server"], "zmf_ticket_caller")


def test_the_waiting_line_says_the_windows_open_at_round_five(built, committed) -> None:
    _bp, _rooms, quest = built
    step = next(s for s in quest.steps if s.key == "number")
    assert "opens at round &&1" in step.waiting
    assert "Take a Number" in step.waiting


# ---- Photo ID: a flash every player in the booth can see -------------------
def _photo(quest):
    return next(s for s in quest.steps if s.key == "photo")


def test_photo_id_opens_after_the_vision_test_at_its_round_and_tells_everyone(
        built, committed) -> None:
    """It cannot start before the Vision Test is passed and its round has
    come; then the start line goes to every player (not a radius), and the
    flash loop only starts after that line."""
    _bp, _rooms, quest = built
    keys = [s.key for s in quest.steps]
    vision = keys.index("vision")
    body = _body(committed["server"], "zmf_quest_step_photo")
    gate = body.index(f"while ( level.zmf_q_state[ {vision} ] != 2 )")
    rnd = body.index(f"while ( level.round_number < {UNLOCK_ROUNDS[keys.index('photo')]} )")
    start = body.index('zmf_quest_all_0( &"ZM_DMV_Q_REGISTER_PHOTO_START" );')
    loop = body.index("level thread zmf_quest_flash_photo( a_pts[ 0 ] );")
    assert gate < rnd < start < loop
    every = _body(committed["server"], "zmf_quest_all_0")
    assert "getplayers()" in every and "Distance" not in every


def test_the_countdown_and_flash_reach_everyone_in_the_booth_and_skip_the_gag_limiter(
        built, committed) -> None:
    from zmforge.recipes.dmv_quest import PHOTO_HEARD

    _bp, rooms, quest = built
    photo = _photo(quest)
    assert photo.flash.heard == PHOTO_HEARD
    cam = photo.targets[0].point
    p_in = rooms["photo"].interior
    corners = [(x, y) for x in (p_in.mins.x, p_in.maxs.x) for y in (p_in.mins.y, p_in.maxs.y)]
    assert max(math.hypot(x - cam[0], y - cam[1]) for x, y in corners) < PHOTO_HEARD
    # the welcome's whole circle is inside the flash's
    h = photo.hint
    assert math.hypot(h.point[0] - cam[0], h.point[1] - cam[1]) + h.radius < PHOTO_HEARD
    server = committed["server"]
    flash = _body(server, "zmf_quest_flash_photo")
    hud = _body(server, "zmf_quest_flash_hud_photo")
    heard = f"DistanceSquared( a_players[ i ].origin, v_at ) < {PHOTO_HEARD * PHOTO_HEARD:g}"
    assert heard in flash and heard in hud
    assert 'zmf_quest_flash_hud_photo( v_at, &"ZM_DMV_Q_REGISTER_PHOTO_COUNT", n );' in flash
    assert 'zmf_quest_flash_hud_photo( v_at, &"ZM_DMV_Q_REGISTER_PHOTO_FLASH", 0 );' in flash
    assert "NewClientHudElem( e_p );" in hud and "SetText( str_line, n );" in hud
    for body in (flash, hud):
        assert "zmf_gag_say" not in body
    # a white flash on each nearby player, never a level-wide one
    assert 'a_players[ i ] thread lui::screen_flash(' in flash
    assert "level thread lui" not in flash and "level lui::" not in flash
    assert 'PlayFX( level._effect[ "powerup_grabbed_solo" ], v_at );' in flash
    # the countdown is off every screen when the step ends
    assert "zmf_quest_flash_hide_photo();" in _body(server, "zmf_quest_step_photo")


def test_the_photo_window_is_one_named_constant(built, committed) -> None:
    from zmforge.recipes.dmv_quest import PHOTO_COUNTDOWN, PHOTO_WINDOW_SECONDS

    _bp, _rooms, quest = built
    assert PHOTO_WINDOW_SECONDS == 3.0
    assert _photo(quest).flash.open == PHOTO_WINDOW_SECONDS
    flash = _body(committed["server"], "zmf_quest_flash_photo")
    assert f"gettime() + {int(PHOTO_WINDOW_SECONDS * 1000)};" in flash
    assert f"for ( n = {PHOTO_COUNTDOWN}; n > 0; n-- )" in flash


def test_too_early_and_too_late_are_told_apart(committed) -> None:
    body = _body(committed["server"], "zmf_quest_step_photo")
    late = body.index('e_who IPrintLnBold( &"ZM_DMV_Q_REGISTER_PHOTO_LATE" );')
    early = body.index('e_who IPrintLnBold( &"ZM_DMV_Q_REGISTER_PHOTO_EARLY" );')
    assert body.rindex("level.zmf_q_phase_photo == 3", 0, late) < late < early
    # a second swing at the same flash says nothing (the advance line has)
    assert "level.zmf_q_phase_photo == 4" in body
    assert 'zmf_quest_all_2( &"ZM_DMV_Q_REGISTER_PHOTO_ADVANCE", n_done, 3 );' in body


def test_photo_id_says_what_to_do_everywhere_it_is_met(built, committed) -> None:
    lines, spots = all_notices(FIXTURE, built[1])
    assert lines["photo"][0].startswith("PHOTO ID: hold ^3[{+activate}]^7")
    cam = _photo(built[2]).targets[0].point
    sign = dict(spots)["photo"]
    assert math.hypot(sign.x - cam[0], sign.y - cam[1]) < 72.0
    strings = committed["strings"]
    for text in ("PHOTO ID: say cheese... &&1", "^3*FLASH*^7 KNIFE THE CAMERA NOW!",
                 "Too early. Wait for the FLASH.", "Too late. Wait for the next flash.",
                 "PHOTO &&1 OF &&2 TAKEN! Wait for the next flash.",
                 "WELCOME TO THE PHOTO BOOTH.",
                 "PHOTO ID: hold ^3[{+activate}]^7 for help"):
        assert text in strings, text


def test_the_letter_cues_come_only_after_a_wrong_hit(committed) -> None:
    """The letters are the puzzle: no NEXT LETTER line up
    front or after a right hit, only after the WRONG LETTER line."""
    body = _body(committed["server"], "zmf_quest_step_vision")
    start = body.index('zmf_quest_all_0( &"ZM_DMV_Q_REGISTER_VISION_START" );')
    watch = body.index("level thread zmf_quest_aim_attach(")
    wrong = body.index('IPrintLnBold( &"ZM_DMV_Q_REGISTER_VISION_WRONG" );')
    cues = [m.start() for m in re.finditer(r"VISION_CUE\d", body)]
    assert start < watch < wrong
    assert cues and all(c > wrong for c in cues)
    assert f"wait {q.CUE_GAP:g};" not in body[:watch]


TIMED = (("vision", 0, VISION_TIME_LIMIT), ("photo", 1, PHOTO_TIME_LIMIT),
         ("written", 2, FORMS_TIME_LIMIT))


def test_the_skill_steps_are_timed_and_the_rest_are_not(built, committed) -> None:
    _bp, _rooms, quest = built
    limits = {s.key: s.time_limit for s in quest.steps}
    assert limits == {"vision": 15.0, "photo": 60.0, "written": 180.0,
                      "number": None, "road": None}
    server = committed["server"]
    for key, _i, limit in TIMED:
        timer = _body(server, f"zmf_quest_timer_{key}")
        assert f"for ( n = {int(limit)}; n > 0; n-- )" in timer
        assert f"zmf_quest_timer_hud_{key}( n );" in timer
        assert f"level.zmf_q_tout_{key} = 1;" in timer
        hud = _body(server, f"zmf_quest_timer_hud_{key}")
        assert f"zmf_quest_hud_elem( e_p, {q.TIMER_Y}," in hud
        assert f'SetText( &"ZM_DMV_Q_REGISTER_{key.upper()}_TIMER", n );' in hud
        for role in ("TIMER", "TIMEOUT"):
            ref = f"ZM_DMV_Q_REGISTER_{key.upper()}_{role}"
            assert f'#precache( "string", "{ref}" );' in server, ref
        assert f"zmf_quest_timer_hide_{key}();" in _body(server, f"zmf_quest_step_{key}")
    assert "TIME'S UP! The examiner sighs." in committed["strings"]
    for key in ("number", "road"):
        assert f"zmf_quest_timer_{key}" not in server
    for body in (server,):
        assert body.count("{") == body.count("}")


def test_out_of_time_zeroes_the_hit_steps_and_they_start_again(committed) -> None:
    server = committed["server"]
    for key, i, _limit in TIMED[:2]:
        step = _body(server, f"zmf_quest_step_{key}")
        reset = step.index(f"if ( level.zmf_q_tout_{key} )")
        # checked before anything reads the (absent) hitter
        assert reset < step.index("if ( !isdefined( e_who ) )")
        branch = step[reset: step.index("continue;", reset)]
        for line in ("n_done = 0;", "n_tgt = 0;", "n_hit = 0;", f"level.zmf_q_next_{key} = 0;",
                     f"level.zmf_q_hits_{key}[ j ] = 0;", f"zmf_quest_progress( {i}, 0 );",
                     f'zmf_quest_all_0( &"ZM_DMV_Q_REGISTER_{key.upper()}_TIMEOUT" );'):
            assert line in branch, (key, line)
        # the clock starts at the first progress, once
        assert step.count(f"level thread zmf_quest_timer_{key}();") == 1
        assert step.index(f"level thread zmf_quest_timer_{key}();") > step.index("n_done++;")
    # a wrong letter starts the attempt over, clock included
    vision = _body(server, "zmf_quest_step_vision")
    assert 'level notify( "zmf_q_tstop_vision" );' in vision


def test_out_of_time_puts_every_form_back_and_empties_every_bag(committed) -> None:
    server = committed["server"]
    step = _body(server, "zmf_quest_step_written")
    assert "if ( level.zmf_q_tout_written && level.zmf_q_n[ 2 ] < 3 )" in step
    assert "zmf_quest_reset_written();" in step
    reset = _body(server, "zmf_quest_reset_written")
    for line in ('level notify( "zmf_q_reset_written" );', "level.zmf_q_it_written[ j ] delete();",
                 "level.zmf_q_im_written[ j ] delete();", "a_players[ j ].zmf_q_bag[ 2 ] = 0;",
                 "zmf_quest_progress( 2, 0 );",
                 'zmf_quest_all_0( &"ZM_DMV_Q_REGISTER_WRITTEN_TIMEOUT" );'):
        assert line in reset, line
    # the items come back last, once the old ones are gone
    assert reset.rstrip().endswith("zmf_quest_items_written();\n}")
    assert _body(server, "zmf_quest_items_written").count("level thread zmf_quest_item_written(") == 3
    item = _body(server, "zmf_quest_item_written")
    assert 'level endon( "zmf_q_reset_written" );' in item
    assert "level.zmf_q_it_written[ n_item ] = t_item;" in item
    assert item.index("level thread zmf_quest_timer_written();") > item.index("zmf_q_bag[ 2 ]++;")


def test_the_photo_countdown_holds_the_gags(committed) -> None:
    flash = _body(committed["server"], "zmf_quest_flash_photo")
    assert "level.zmf_gag_hush = gettime() + " in flash
