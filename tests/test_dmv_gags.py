"""The DMV's on-screen gags, read off the committed server script.

Every gag is pinned four ways: the hook it waits on (a stock notify or hook,
see :mod:`zmforge.script.gags`), the print call that puts its line on
screen, the precache plus the ``.str`` entry that ship the words, and the
rate limit that stops it spamming.  Nothing here is an observation of play.
"""

from __future__ import annotations

import re

import pytest

from zmforge.recipes.dmv import (
    GAG_LINES, GAG_SAY_GAP, NOTICE_LINES,
    TICKET_LINES,
)
from zmforge.script import gags
from zmforge.script.gsc import scan
from zmforge.script.symbols import ENGINE_BUILTINS, lookup, unresolved


MAP_NAME = "zm_dmv"


@pytest.fixture(scope="module")
def committed(dmv_committed):
    return dmv_committed


def _body(server: str, name: str) -> str:
    start = server.index(f"function {name}(")
    return server[start: server.index("\n}\n", start) + 2]


def _ref(key: str) -> str:
    return f"ZM_DMV_GAG_{key.upper()}"


def _shipped(committed, key: str) -> None:
    """Precached as a string, and its words are in the map's .str."""
    ref = _ref(key)
    assert f'#precache( "string", "{ref}" );' in committed["server"], key
    assert f"REFERENCE\t\t\tGAG_{key.upper()}\n" in committed["strings"], key
    assert GAG_LINES[key] in committed["strings"], key


def _says(body: str, gag: str, key: str, mode: int, cooldown: float) -> None:
    """One call to the rate-limited sayer, with its gag key and cooldown."""
    call = re.search(
        rf'zmf_gag_say(?:_all)?\( "{re.escape(gag)}", &"{_ref(key)}", (\d+), {mode}\b', body)
    assert call, (gag, key, body[:400])
    assert int(call.group(1)) == int(round(cooldown * 1000)), (gag, call.group(1))


# --------------------------------------------------------------------------
# The sayer and its rate limits
# --------------------------------------------------------------------------
def test_the_sayer_limits_per_player_and_per_gag(committed) -> None:
    body = _body(committed["server"], "zmf_gag_say")
    # per player per gag: a cooldown clock keyed by the gag's name
    assert "self.zmf_gag_next[ str_gag ] = n_now + n_cooldown;" in body
    assert "n_now < self.zmf_gag_next[ str_gag ]" in body
    # per player: one slot clock for the centre of the screen, a gap, a backlog cap
    assert f"self.zmf_gag_slot = self.zmf_gag_slot + {int(GAG_SAY_GAP * 1000)};" in body
    assert f"if ( self.zmf_gag_slot - n_now > {int(gags.SAY_BACKLOG * 1000)} )" in body
    # the three ways a line is said
    assert "self IPrintLnBold( str_line, param );" in body
    assert "self IPrintLn( str_line, param );" in body
    assert "self thread zm_equipment::show_hint_text( str_line, 4 );" in body
    everyone = _body(committed["server"], "zmf_gag_say_all")
    assert "level.zmf_gag_next[ str_gag ] = n_now + n_cooldown;" in everyone
    assert "a_players = getplayers();" in everyone
    assert "#using scripts\\zm\\_zm_equipment;" in committed["server"]


def test_every_call_the_gags_make_is_one_the_checker_knows(committed) -> None:
    """Every print and helper is in the symbol table with its evidence, and
    the whole committed script resolves."""
    for builtin in ("iprintlnbold", "iprintln", "gettime", "getplayers",
                    "randomint", "randomintrange", "distancesquared"):
        assert builtin in ENGINE_BUILTINS, builtin
    assert "_zm_gametype.gsc:815" in ENGINE_BUILTINS["iprintln"]
    assert lookup("zm_zonemgr::get_player_zone").evidence.startswith(
        "share/raw/scripts/zm/_zm_zonemgr.gsc:89")
    assert "_zm_equipment.gsc:587" in lookup("zm_equipment::show_hint_text").evidence
    source = scan(committed["server"])
    assert source.issues == []
    assert unresolved(source) == []


def test_every_gag_line_is_shipped(committed) -> None:
    for key in GAG_LINES:
        _shipped(committed, key)
        assert f'&"{_ref(key)}"' in committed["server"], key


# --------------------------------------------------------------------------
# Event reactions
# --------------------------------------------------------------------------
def test_going_down_suspends_your_license(committed) -> None:
    body = _body(committed["server"], "zmf_gag_on_downed")
    assert 'self waittill( "player_downed" );' in body
    _says(body, "downed", "downed", gags.SAY_BOLD, gags.COOLDOWNS["downed"])
    _says(body, "downed_feed", "downed_feed", gags.SAY_FEED, gags.COOLDOWNS["downed_feed"])
    assert "SUSPENDED" in GAG_LINES["downed"]
    bled = _body(committed["server"], "zmf_gag_on_bled_out")
    assert 'self waittill( "bled_out" );' in bled
    _says(bled, "bled_out_feed", "bled_out_feed", gags.SAY_FEED, gags.COOLDOWNS["bled_out_feed"])


def test_a_revive_reinstates_and_charges_the_fee(committed) -> None:
    body = _body(committed["server"], "zmf_gag_on_revived")
    assert 'self waittill( "player_revived", e_reviver );' in body
    assert "self zm_score::minus_to_player_score( 25 );" in body
    assert "self.score >= 25" in body
    _says(body, "revived", "revived", gags.SAY_BOLD, gags.COOLDOWNS["revived"])
    _says(body, "revived", "revived_broke", gags.SAY_BOLD, gags.COOLDOWNS["revived"])
    _says(body, "reviver", "reviver", gags.SAY_FEED, gags.COOLDOWNS["reviver"])
    assert "$25" in GAG_LINES["revived"] and "reinstated" in GAG_LINES["revived"]


def test_the_registration_perk_says_you_may_drive(committed) -> None:
    body = _body(committed["server"], "zmf_gag_on_perk")
    assert 'self waittill( "perk_bought", str_perk );' in body
    assert 'str_perk == "specialty_zmf_vehicle_registration"' in body
    assert 'str_perk == "specialty_zmf_take_a_number"' in body
    _says(body, "perk_0", "perk_registration", gags.SAY_BOLD, gags.COOLDOWNS["perk"])
    _says(body, "perk_1", "perk_ticket", gags.SAY_BOLD, gags.COOLDOWNS["perk"])
    assert GAG_LINES["perk_registration"] == (
        "Vehicle registration fee paid. You may now drive (run).")


def test_pack_a_punch_upgrades_your_paperwork(committed) -> None:
    body = _body(committed["server"], "zmf_gag_on_pap")
    assert 'self waittill( "pap_taken" );' in body
    _says(body, "pap", "pap", gags.SAY_BOLD, gags.COOLDOWNS["pap"])
    assert "paperwork has been" in GAG_LINES["pap"]


def test_the_box_asks_you_to_take_a_number(committed) -> None:
    server = committed["server"]
    assert "level._magic_box_used_VO = &zmf_gag_on_box;" in server
    _says(_body(server, "zmf_gag_on_box"), "box", "box", gags.SAY_BOLD, gags.COOLDOWNS["box"])
    moved = _body(server, "zmf_gag_box_moved")
    assert 'level waittill( "weapon_fly_away_start" );' in moved
    _says(moved, "box_moved", "box_moved", gags.SAY_BOLD, gags.COOLDOWNS["box_moved"])
    assert "Please take a number." in GAG_LINES["box"]


def test_the_power_coming_on_is_announced(committed) -> None:
    body = _body(committed["server"], "zmf_gag_power_on")
    assert 'level flag::wait_till( "power_on" );' in body
    _says(body, "power", "power", gags.SAY_BOLD, 0)


# --------------------------------------------------------------------------
# Rooms
# --------------------------------------------------------------------------
def test_no_room_sign_in_lines(committed) -> None:
    """P13/P17: no zone-entry flavour lines; the room
    signs and props say where you are."""
    assert not [key for key in GAG_LINES if key.startswith("room_")]
    assert "level.zmf_gag_rooms[ \"" not in committed["server"]


def test_waiting_still_is_noticed_as_hud_text(committed) -> None:
    body = _body(committed["server"], "zmf_gag_rooms")
    assert 'str_zone == "waiting"' in body
    _says(body, "idle", "idle", gags.SAY_HINT, gags.COOLDOWNS["idle"])


def test_every_player_gets_the_watchers_now_and_on_join(committed) -> None:
    server = committed["server"]
    assert server.count("level thread zmf_gag_attach();") == 1
    attach = _body(server, "zmf_gag_attach")
    assert 'level waittill( "connected", player );' in attach
    player = _body(server, "zmf_gag_player")
    for watcher in ("zmf_gag_on_downed", "zmf_gag_on_bled_out", "zmf_gag_on_revived",
                    "zmf_gag_on_perk", "zmf_gag_on_pap", "zmf_gag_on_hop_express",
                    "zmf_gag_on_hop_booth", "zmf_gag_rooms"):
        assert f"self thread {watcher}();" in player, watcher


# --------------------------------------------------------------------------
# The two hops, said out loud
# --------------------------------------------------------------------------
@pytest.mark.parametrize("suffix, key, feed", [("_express", "express", "express_feed"),
                                               ("_booth", "booth", None)])
def test_a_hop_says_what_it_did(committed, suffix, key, feed) -> None:
    server = committed["server"]
    move = _body(server, f"zmf_teleport_player{suffix}")
    assert f'self notify( "zmf_hopped{suffix}" );' in move
    assert move.index("self setorigin(") < move.index("zmf_hopped")
    body = _body(server, f"zmf_gag_on_hop{suffix}")
    assert f'self waittill( "zmf_hopped{suffix}" );' in body
    _says(body, f"hop{suffix}", key, gags.SAY_BOLD, gags.COOLDOWNS["hop"])
    if feed:
        _says(body, f"hop{suffix}_feed", feed, gags.SAY_FEED, gags.COOLDOWNS["hop_feed"])
    assert "back of the line" in GAG_LINES["express"]
    assert "FLASH" in GAG_LINES["booth"]


# --------------------------------------------------------------------------
# The PA
# --------------------------------------------------------------------------
def test_no_round_end_pa_flavour(committed) -> None:
    """P13/P17: the round-end PA jokes are gone; the only
    PA voice is the ticket window's calls, and no gag line calls a number."""
    server = committed["server"]
    assert not [key for key in GAG_LINES if key.startswith("pa_")]
    assert "function zmf_gag_announcer(" not in server
    assert "function zmf_ticket_now_serving(" not in server
    assert not [key for key, line in GAG_LINES.items() if "NOW SERVING NUMBER" in line]


def test_gag_lines_wait_for_quest_lines_and_ticket_calls(committed) -> None:
    body = _body(committed["server"], "zmf_gag_say")
    hush = "if ( isdefined( level.zmf_gag_hush ) && self.zmf_gag_slot < level.zmf_gag_hush )"
    assert hush in body
    assert "if ( isdefined( self.zmf_gag_hush ) && self.zmf_gag_slot < self.zmf_gag_hush )" in body
    # The hush moves the slot before the backlog check, so a gag due inside a
    # call is dropped rather than stacked on it.
    assert body.index(hush) < body.index("if ( self.zmf_gag_slot - n_now > ")
    assert "level.zmf_gag_hush = gettime() + " in _body(committed["server"], "zmf_quest_all_0")
    assert "level.zmf_gag_hush = gettime() + " in _body(committed["server"], "zmf_ticket_caller")


def test_no_random_pa_lines_and_hints_wait_out_a_ticket_call(committed) -> None:
    """The random mid-round PA gag is gone (it read as spam on top
    of the ticket calls); what else prints
    on its own holds back while a call is live."""
    assert not [key for key in GAG_LINES if key.startswith("pa_random")]
    assert "function zmf_gag_pa_random" not in committed["server"]
    hint = _body(committed["server"], "zmf_quest_hint_number")
    assert "if ( isdefined( level.zmf_gag_hush ) && gettime() < level.zmf_gag_hush )" in hint
    assert hint.index("level.zmf_gag_hush") < hint.index("IPrintLnBold")
    for step in ("photo", "vision"):
        body = _body(committed["server"], f"zmf_quest_step_{step}")
        assert "while ( isdefined( level.zmf_ticket_calling ) && level.zmf_ticket_calling )" in body


# --------------------------------------------------------------------------
# Notices: every prompt says there is something to press, every reply is
# centre screen and rate-limited per player
# --------------------------------------------------------------------------
def test_notice_replies_are_centre_screen_and_rate_limited(committed) -> None:
    body = _body(committed["server"], "zmf_notice")
    assert "e_who IPrintLnBold( a_lines[ n_line ] );" in body
    assert "n_now < e_who.zmf_notice_next" in body
    assert "e_who.zmf_notice_next = n_now + 1500;" in body
    assert body.index("zmf_notice_next = n_now") < body.index("IPrintLnBold")


def test_the_ticket_board_is_still_the_ticket_machine_s(committed) -> None:
    """The gags hook the ticket machine; they do not repeat its lines."""
    for key, line in GAG_LINES.items():
        assert line not in TICKET_LINES.values(), key


def test_every_notice_prompt_names_the_use_key() -> None:
    """A notice nobody knows to press is a joke nobody reads (every gag
    must be clear), so every prompt says to hold use."""
    from zmforge.recipes.dmv_rooms import dense_notice_lines

    lines = {**NOTICE_LINES, **dense_notice_lines()}
    bare = [key for key, (prompt, _replies) in lines.items() if "[{+activate}]" not in prompt]
    assert bare == []


def test_a_room_sign_in_is_only_marked_seen_when_it_will_be_said(committed) -> None:
    """A sign-in is marked seen only when it will be said: one dropped by the
    backlog rule would be lost for good, so it waits for a poll where the
    centre of the screen is free."""
    server = committed["server"]
    # zm_dmv has no room lines (P13), so no room table and no sign-in is
    # emitted at all (G7); the rule itself is tested on
    # the gag module directly.
    assert "level.zmf_gag_rooms = [];" not in server
    reactions = gags.player_reactions(rooms={"lobby": "hello"})
    rooms = next(f for f in reactions.functions if f.name == "zmf_gag_rooms")
    watcher = "\n".join(rooms.body)
    assert "self.zmf_gag_seen = [];" in watcher
    assert "isdefined( level.zmf_gag_rooms[ str_zone ] ) && self zmf_gag_can_say() )" in watcher
    # Only room sign-ins call it, so zm_dmv no longer ships it (pruned).
    assert "function zmf_gag_can_say(" not in server
    can = "\n".join(next(f for f in gags.gag_say().functions
                         if f.name == "zmf_gag_can_say").body)
    assert "level.zmf_gag_hush" in can and "self.zmf_gag_slot" in can
    assert f"return n_slot - n_now <= {int(gags.SAY_BACKLOG * 1000)};" in can
    init = _body(server, "zmf_quest_init")
    assert init.index("zmf_quest_all_0(") < init.index("wait 4;") < init.index(
        "level thread zmf_quest_step_vision();")


def test_ticket_calls_stop_once_take_a_number_is_done(committed) -> None:
    """The calls stop once that task is over (P12).  The check sits before any call line, the loop breaks, and the
    kiosk trigger is deleted; the index is the number step's own."""
    from zmforge.recipes.dmv import TICKET_QUEST_STEP

    body = _body(committed["server"], "zmf_ticket_caller")
    stop = f"level.zmf_q_state[ {TICKET_QUEST_STEP} ] == 2 )"
    assert stop in body
    assert body.index(stop) < body.index("n_call = zmf_ticket_pick();")
    tail = body[body.index("level.zmf_ticket_closed = 1;"):]
    assert "IPrintLnBold" not in tail and "zmf_ticket_all(" not in tail
    assert "level.zmf_ticket_kiosk delete();" in tail
    # The step's hint dies with the step: either it checks the step's state,
    # or it ends on the step's own end notify (the shared P12 rule).
    hint = _body(committed["server"], "zmf_quest_hint_number")
    assert (f"level.zmf_q_state[ {TICKET_QUEST_STEP} ]" in hint
            or 'level endon( "zmf_q_end_number" );' in hint)
    assert 'level notify( "zmf_q_end_number" );' in committed["server"]
