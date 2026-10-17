"""Take a number: the kiosk, the calls to the window, and the serve.

Every test reads what is emitted -- the server script, the ``.str`` and the
zone -- because a machine nobody can find
raises the question whether the shipped files carry it.  The
design: tickets 1-10, a call a minute, three seconds to
reach the window, a reward for making it, a void ticket for missing it.
"""

from __future__ import annotations

import re

import pytest

from zmforge import Project
from zmforge.recipes.layouts import one_room_map
from zmforge.script.gsc import scan
from zmforge.script.symbols import unresolved
from zmforge.script.tricks import TICKET_SERVED_FLAG, TicketCalls, take_a_ticket
from zmforge.spatial import Point

from conftest import seed_stock_weapon_table

NAME = "zm_tkt"
LINES = {
    "TICKET_PROMPT": ("Hold ^3[{+activate}]^7 to TAKE A NUMBER", "triggerstring"),
    "TICKET_NUMBER": ("You are number ^3&&1^7.", "triggerstring"),
    "TICKET_YOURS": ("TICKET ^3&&1^7", "string"),
    "TICKET_EARLY": ("TICKET ^3&&1^7, windows open at round 5", "string"),
    "TICKET_WELCOME": ("Please TAKE A NUMBER.", "string"),
    "TICKET_MINE": ("TICKET &&1", "string"),
    "TICKET_MINE_EARLY": ("TICKET &&1 (round 5)", "string"),
    "TICKET_CALL": ("NOW SERVING NUMBER &&1 AT WINDOW 5", "string"),
    "TICKET_YOU": ("THAT'S YOU! Number &&1: get to WINDOW 5!", "string"),
    "TICKET_HUD_CALL": ("NOW SERVING &&1: &&2", "string"),
    "TICKET_HUD_YOU": ("YOU &&1: &&2", "string"),
    "TICKET_SERVED": ("Your paperwork has been processed.", "string"),
    "TICKET_SERVED_ALL": ("&&1 has been served.", "string"),
    "TICKET_MISSED": ("NUMBER &&1? ... It has been given to the next person.", "string"),
    "TICKET_NO_ONE": ("NUMBER &&1? ... No one? Next!", "string"),
    "TICKET_OPENED": ("WINDOW 5 IS NOW OPEN.", "string"),
}
WINDOW = (300.0, -40.0, 0.0)


def _calls(a, **kw) -> TicketCalls:
    return TicketCalls(
        window=WINDOW, call=a["TICKET_CALL"], you=a["TICKET_YOU"],
        hud_call=a["TICKET_HUD_CALL"], hud_you=a["TICKET_HUD_YOU"],
        served=a["TICKET_SERVED"], served_all=a["TICKET_SERVED_ALL"],
        missed=a["TICKET_MISSED"], no_one=a["TICKET_NO_ONE"], opened=a["TICKET_OPENED"],
        every=60.0, grace=3.0, start_round=5, **kw)


def _commit(tmp_path, *, calls: bool = True, extras: bool = True):
    blueprint = one_room_map(NAME)
    a = {ref: blueprint.add_map_string(ref, text, kind=kind)
         for ref, (text, kind) in LINES.items()}
    options = {}
    if extras:
        options = dict(yours_early=a["TICKET_EARLY"], welcome=a["TICKET_WELCOME"],
                       mine=a["TICKET_MINE"], mine_early=a["TICKET_MINE_EARLY"])
    blueprint.add_custom_logic(
        take_a_ticket(
            Point(-100.0, 40.0, 0.0),
            prompt=a["TICKET_PROMPT"], number=a["TICKET_NUMBER"], yours=a["TICKET_YOURS"],
            calls=_calls(a) if calls else None, **options,
        )
    )
    seed_stock_weapon_table(tmp_path)
    project = Project.create(NAME, tmp_path, blueprint=blueprint)
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8"),
        "zone": paths["manifest"].read_text(encoding="utf-8"),
    }


def _function(server: str, name: str) -> str:
    start = server.index(f"function {name}(")
    end = server.index("\n}\n", start)
    return server[start:end + 2]


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    return _commit(tmp_path_factory.mktemp("full"))


FUNCTIONS = ("zmf_take_a_ticket", "zmf_ticket_free", "zmf_ticket_welcome", "zmf_ticket_caller",
             "zmf_ticket_pick", "zmf_ticket_at_window", "zmf_ticket_countdown", "zmf_ticket_all",
             "zmf_ticket_hud_attach", "zmf_ticket_hud_player", "zmf_ticket_hud_end")


def test_it_commits_clean_and_every_call_is_stock(full) -> None:
    assert full["result"].report.errors == []
    source = scan(full["server"])
    assert source.issues == []
    assert unresolved(source) == []
    for name in FUNCTIONS:
        body = _function(full["server"], name)
        assert body.count("{") == body.count("}"), name
        assert body.count("(") == body.count(")"), name


def test_the_trigger_is_spawned_big_enough_and_on_the_floor(full) -> None:
    body = _function(full["server"], "zmf_take_a_ticket")
    # Radius 64, height 80: wider than a perk's 40 (_zm_perks.gsc:1513) so
    # the prompt shows from in front of the machine, not only against it.
    assert 't_ticket = spawn( "trigger_radius_use", ( -100, 40, 0 ), 0, 64, 80 );' in body
    for line in ("t_ticket TriggerIgnoreTeam();", "t_ticket SetVisibleToAll();",
                 't_ticket SetTeamForTrigger( "none" );',
                 't_ticket SetCursorHint( "HINT_NOICON" );'):
        assert line in body
    assert "level thread zmf_take_a_ticket();" in full["server"]


def test_every_line_is_a_localized_string_precached_and_shipped(full) -> None:
    server, strings, zone = full["server"], full["strings"], full["zone"]
    for ref, (text, kind) in LINES.items():
        asset = f"{NAME.upper()}_{ref}"
        assert f'#precache( "{kind}", "{asset}" );' in server, ref
        assert f"REFERENCE\t\t\t{ref}\n" in strings, ref
        assert f'LANG_ENGLISH\t\t"{text}"' in strings, ref
    assert f"localize,{NAME}" in zone
    # Nothing prints a literal: every hint and every print names an &"asset"
    # (or is the sayer's own str_line parameter).
    for call in re.findall(r"(?:SetHintString|IPrintLnBold|SetText)\( ([^;]*)\);", server):
        assert call.startswith('&"') or call.startswith("str_line"), call


def test_tickets_are_one_to_ten_one_per_player_never_shared(full) -> None:
    take = _function(full["server"], "zmf_take_a_ticket")
    free = _function(full["server"], "zmf_ticket_free")
    # Taking one replaces the one you had: a single field per player.
    assert "e_who.zmf_my_ticket = zmf_ticket_free( e_who );" in take
    assert "for ( n = 1; n <= 10; n++ )" in free
    # Numbers another player holds are skipped; the taker's own is not.
    assert ("a_players[ i ] != e_who && isdefined( a_players[ i ].zmf_my_ticket ) "
            "&& a_players[ i ].zmf_my_ticket == n") in free
    assert "return a_free[ randomint( a_free.size ) ];" in free
    # Before the calls start the kiosk says when the windows open.
    asset = NAME.upper()
    assert f'e_who IPrintLnBold( &"{asset}_TICKET_EARLY", e_who.zmf_my_ticket );' in take
    assert f'e_who IPrintLnBold( &"{asset}_TICKET_YOURS", e_who.zmf_my_ticket );' in take
    assert "level.zmf_ticket_open = 0;" in take


def test_numbers_are_called_every_minute_from_round_five(full) -> None:
    body = _function(full["server"], "zmf_ticket_caller")
    assert "while ( level.round_number < 5 )" in body
    assert body.index("while ( level.round_number < 5 )") < body.index("level.zmf_ticket_open = 1;")
    # Every minute, every 30 s with more than four unserved holders (one a
    # minute would keep eight players waiting at least eight minutes).
    assert "\tn_wait = 60;" in body
    assert "\tif ( zmf_ticket_holders() > 4 )" in body
    assert "\t\tn_wait = 30;" in body
    assert "\twait n_wait;" in body
    assert "n_call = zmf_ticket_pick();" in body
    pick = _function(full["server"], "zmf_ticket_pick")
    # Mostly the longest-waiting unserved holder's number; otherwise any of 1-10.
    assert f"!isdefined( e_p.{TICKET_SERVED_FLAG} )" in pick
    assert "if ( n_best == 0 || n_t < n_since )" in pick
    assert "if ( n_best > 0 && randomint( 100 ) < 75 )" in pick
    assert "return randomintrange( 1, 11 );" in pick
    assert "\tif ( n_call == 0 )" in body
    take = _function(full["server"], "zmf_take_a_ticket")
    assert "e_who.zmf_ticket_time = gettime();" in take


def test_dmv_calls_only_held_numbers_longest_waiting_first() -> None:
    """A call names a number someone holds, never a random one.  At 100 the pick never invents a number, and returns 0 (no
    call) when nobody holds an unserved ticket."""
    from zmforge.recipes.dmv import TICKET_HELD_CHANCE

    assert TICKET_HELD_CHANCE == 100
    a = {ref: ref for ref in LINES}
    script = take_a_ticket(Point(-100.0, 40.0, 0.0), prompt="P", number="N", yours="Y",
                           calls=_calls(a, held_chance=100))
    pick = next(f for f in script.functions if f.name == "zmf_ticket_pick")
    body = "\n".join(pick.body)
    assert "randomint" not in body
    assert body.rstrip().endswith("return n_best;")


def test_the_holder_has_three_seconds_to_stand_at_the_window(full) -> None:
    body = _function(full["server"], "zmf_ticket_caller")
    assert "n_end = gettime() + 3000;" in body
    assert "while ( gettime() < n_end )" in body
    assert ("e_called.zmf_my_ticket == n_call && e_called zmf_ticket_at_window()") in body
    at = _function(full["server"], "zmf_ticket_at_window")
    assert "laststand::player_is_in_laststand()" in at
    assert "Distance2DSquared( self.origin, ( 300, -40, 0 ) ) > 9216" in at
    # The window pulses while the call is open, so it is findable.
    assert 'PlayFX( level._effect[ "powerup_grabbed" ], ( 300, -40, 0 ) );' in body


def test_served_pays_and_missed_voids_the_ticket(full) -> None:
    body = _function(full["server"], "zmf_ticket_caller")
    asset = NAME.upper()
    served = body[body.index("\tif ( b_served )"):body.index("\telse if ( isdefined( e_called ) )")]
    assert f"e_called.{TICKET_SERVED_FLAG} = 1;" in served
    assert "e_called zm_score::add_to_player_score( 1000 );" in served
    assert "zm_powerups::specific_powerup_drop( a_pow[ randomint( a_pow.size ) ], e_called.origin );" in served
    assert "e_called.zmf_my_ticket = undefined;" in served
    assert f'e_called IPrintLnBold( &"{asset}_TICKET_SERVED" );' in served
    assert f'a_players[ i ] IPrintLnBold( &"{asset}_TICKET_SERVED_ALL", e_called );' in served
    assert 'level notify( "zmf_ticket_served", e_called );' in served
    missed = body[body.index("\telse if ( isdefined( e_called ) )"):]
    assert "e_called.zmf_my_ticket = undefined;" in missed
    assert f'zmf_ticket_all( &"{asset}_TICKET_MISSED", n_call, undefined );' in missed
    assert f'zmf_ticket_all( &"{asset}_TICKET_NO_ONE", n_call, undefined );' in missed
    for name in ("double_points", "insta_kill", "full_ammo"):
        assert f'"{name}";' in body


def test_the_call_is_on_everyones_screen_and_the_holder_is_told(full) -> None:
    body = _function(full["server"], "zmf_ticket_caller")
    asset = NAME.upper()
    assert f'zmf_ticket_all( &"{asset}_TICKET_CALL", n_call, undefined );' in body
    assert f'e_called IPrintLnBold( &"{asset}_TICKET_YOU", n_call );' in body
    assert "level thread zmf_ticket_countdown( n_call, e_called );" in body
    count = _function(full["server"], "zmf_ticket_countdown")
    assert "for ( n = 3; n > 0; n-- )" in count
    assert f'e_p.zmf_tk_call SetText( &"{asset}_TICKET_HUD_YOU", n_call, n );' in count
    assert f'e_p.zmf_tk_call SetText( &"{asset}_TICKET_HUD_CALL", n_call, n );' in count
    assert 'level endon( "zmf_ticket_call_over" );' in count
    # Gags hold their lines until the call is over.
    assert "level.zmf_gag_hush = gettime() + 7000;" in body
    hud = _function(full["server"], "zmf_ticket_hud_player")
    assert "self.zmf_tk_mine.y = 62;" in hud and 'self.zmf_tk_call.horzAlign = "user_center";' in hud


def test_players_are_told_to_take_a_number_once_each(full) -> None:
    body = _function(full["server"], "zmf_ticket_welcome")
    assert 't_near = spawn( "trigger_radius", ( -100, 40, 0 ), 0, 160, 80 );' in body
    assert "isdefined( e_who.zmf_ticket_welcomed )" in body
    assert f'e_who IPrintLnBold( &"{NAME.upper()}_TICKET_WELCOME" );' in body


def test_the_extras_are_off_unless_asked_for(tmp_path) -> None:
    server = _commit(tmp_path, calls=False, extras=False)["server"]
    assert "function zmf_take_a_ticket()" in server
    for name in ("zmf_ticket_welcome", "zmf_ticket_caller", "zmf_ticket_hud_attach"):
        assert f"function {name}(" not in server
    assert "level.zmf_ticket_open = 1;" in _function(server, "zmf_take_a_ticket")


def test_bad_calls_are_refused() -> None:
    a = {ref: ref for ref in LINES}
    with pytest.raises(ValueError):
        _calls(a, powerups=())
    with pytest.raises(ValueError):
        TicketCalls(window=WINDOW, call="a", you="b", hud_call="c", hud_you="d", served="e",
                    served_all="f", missed="g", no_one="h", every=3.0, grace=3.0)
    with pytest.raises(ValueError):
        _calls(a, powerups=("raygun",))


# --------------------------------------------------------------------------
# zm_dmv as the recipe builds it
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def dmv(dmv_committed):
    return {**dmv_committed, "zone": dmv_committed["manifest"]}


def test_dmv_ships_the_ticket_machine(dmv) -> None:
    server, strings = dmv["server"], dmv["strings"]
    assert "level thread zmf_take_a_ticket();" in server
    body = _function(server, "zmf_take_a_ticket")
    spawn = re.search(r'spawn\( "trigger_radius_use", \(([^)]*)\), 0, (\S+), (\S+) \);', body)
    assert spawn is not None
    assert float(spawn.group(2)) >= 64.0 and float(spawn.group(3)) >= 72.0
    for ref in ("TICKET_PROMPT", "TICKET_NUMBER", "TICKET_CALL", "TICKET_YOU", "TICKET_MISSED",
                "TICKET_NO_ONE", "TICKET_SERVED", "TICKET_SERVED_ALL", "TICKET_HUD_YOU"):
        assert f"REFERENCE\t\t\t{ref}\n" in strings
        assert f'"ZM_DMV_{ref}"' in server
    assert "localize,zm_dmv" in dmv["zone"]
    for asset in re.findall(r'&"(ZM_DMV_TICKET_[A-Z0-9_]+)"', server):
        assert re.search(rf'#precache\( "(?:string|triggerstring)", "{asset}" \);', server), asset
        assert f"REFERENCE\t\t\t{asset[len('ZM_DMV_'):]}\n" in strings, asset


def test_the_kiosk_never_touches_its_trigger_after_the_calls_close(tmp_path) -> None:
    """The DMV closes the kiosk (``stop_when``) and deletes its trigger while
    the kiosk loop may be in its reset wait, so the loop must never call
    SetHintString / waittill on a deleted entity.  The close notifies the
    loop off, stops taking presses, and only then deletes; the loop also
    re-checks after its wait."""
    blueprint = one_room_map(NAME)
    a = {ref: blueprint.add_map_string(ref, text, kind=kind)
         for ref, (text, kind) in LINES.items()}
    blueprint.add_custom_logic(take_a_ticket(
        Point(-100.0, 40.0, 0.0), prompt=a["TICKET_PROMPT"], number=a["TICKET_NUMBER"],
        yours=a["TICKET_YOURS"], calls=_calls(a, stop_when="level.round_number > 9")))
    seed_stock_weapon_table(tmp_path)
    project = Project.create(NAME, tmp_path, blueprint=blueprint)
    result = project.commit()
    assert result.ok, [str(f) for f in result.report.errors]
    server = project.paths()["server_script"].read_text(encoding="utf-8")
    kiosk = _function(server, "zmf_take_a_ticket")
    assert 'level endon( "zmf_ticket_closed" );' in kiosk
    after_wait = kiosk[kiosk.rindex("wait "):]
    assert after_wait.index("!isdefined( t_ticket )") < after_wait.index("SetHintString")
    caller = _function(server, "zmf_ticket_caller")
    close = caller[caller.index("level.zmf_ticket_closed = 1;"):]
    order = [close.index(s) for s in ('level notify( "zmf_ticket_closed" );',
                                      "TriggerEnable( false );", "delete();")]
    assert order == sorted(order)
    assert not unresolved(scan(server))
