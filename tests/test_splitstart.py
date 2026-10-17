"""The split start (:mod:`zmforge.script.splitstart`): sealed start hallways,
a first-press-wins button, and the round-R fallback.

Read off the rendered server script of a committed map: every call resolves
in the stock symbol table, the commit's checks pass, and the logic has the
shape the mechanic needs.  None of it is an observation of play.
"""

from __future__ import annotations

import pytest

from zmforge import Project
from zmforge.blueprint import Blueprint
from zmforge.blueprint.elements import PlayerStart, Zone
from zmforge.script import splitstart as ss
from zmforge.script.gsc import scan
from zmforge.script.symbols import unresolved
from zmforge.solids.layout import Aperture
from zmforge.spatial import Bounds, Facing, Point, Side
from zmforge.verify.reachability import check_reachability

from conftest import seed_stock_weapon_table

NAME = "zm_split"
FLOOR = 0.0


def _room(bp: Blueprint, zone: str, x: float, y: float, *, starting: bool = False,
          openings: tuple = ()):
    """One small room with its own zone, window, riser and light; sealed
    unless ``openings`` (sides) cut doorways."""
    bounds = Bounds.between((x - 160, y - 256, FLOOR), (x + 160, y + 256, 256))
    room = bp.add_room(bounds, wall=16.0, id=f"room_{zone}",
                       openings=[Aperture(side=side, width=80.0, height=96.0) for side in openings])
    z = bp.add_zone(zone, room, starting=starting)
    bp.add_window(z, room, Side.SOUTH, yard_depth=176.0, height=48.0, id=f"window_{zone}")
    bp.add_riser(z, Point(x, y + 200, room.floor_z), Facing.SOUTH, id=f"riser_{zone}")
    bp.place_light(Point(x, y, 200.0), zone_name=zone, id=f"light_{zone}")
    return room


def split_map(halls: int = 4, slots: int = 4, *, wing: bool = False,
              ) -> tuple[Blueprint, list[ss.Hallway], list[ss.HubPoint]]:
    """``halls`` hallways in a row, 800 apart, and a hub well north of them,
    none joined to any other.  ``wing`` adds a room east of the hub behind a
    bought door: reachable only through the teleport and then the door."""
    bp = Blueprint(NAME)
    hallways = []
    for n in range(halls):
        x = n * 800.0
        room = _room(bp, f"hall_{n + 1}", x, 0.0)
        hallways.append(ss.Hallway(
            zone=f"hall_{n + 1}", spawn=(x, -150.0, room.floor_z + 16.0),
            button=(x, 150.0, room.floor_z + 40.0), yaw=90.0))
    hub_room = _room(bp, "hub", 0.0, 1600.0, starting=True,
                     openings=(Side.EAST,) if wing else ())
    if wing:
        wing_room = _room(bp, "wing", 320.0, 1600.0, openings=(Side.WEST,))
        bp.add_door((bp.zone_named("hub"), bp.zone_named("wing")), wing_room.opening(0),
                    price=750, id="door_hub_wing")
    hub = [ss.HubPoint((dx, 1600.0, hub_room.floor_z + 16.0), 90.0) for dx in (-64.0, 0.0, 64.0)]
    bp.set_player_start(Point(*hub[0].origin), Facing.NORTH, slots=slots)
    bp.set_dog_rounds(False)
    bp.enclose(id="enclosure")
    bp.light_rooms()
    return bp, hallways, hub


def _script(halls: int = 8):
    hallways = [ss.Hallway(f"hall_{n + 1}", (n * 800.0, 0.0, 16.0), (n * 800.0, 100.0, 40.0), 90.0)
                for n in range(halls)]
    return ss.split_start_script(
        hallways=hallways, hub_zone="hub", hub=[ss.HubPoint((0.0, 1600.0, 16.0))],
        prompt_asset="P", won_asset="W", lost_asset="L", timeout_asset="T")


def _body(script, name: str) -> str:
    return "\n".join(next(f for f in script.functions if f.name == name).body)


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("split")
    bp, hallways, hub = split_map(wing=True)
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    seed_stock_weapon_table(root)
    project = Project.create(NAME, root, blueprint=bp)
    result = project.commit()
    return {
        "bp": bp, "hallways": hallways, "hub": hub, "result": result,
        "server": project.paths()["server_script"].read_text(encoding="utf-8"),
        "strings": project.paths()["localized_strings"].read_text(encoding="utf-8"),
    }


# -- the committed map ---------------------------------------------------------
def test_the_commit_passes_and_every_call_resolves(committed) -> None:
    report = committed["result"].report
    assert report.errors == [], [str(e) for e in report.errors]
    source = scan(committed["server"])
    assert source.issues == []
    assert unresolved(source) == []


def test_hallways_and_hub_are_declared_so_zone_checks_accept_them(committed) -> None:
    # Z3 warns on a zone no door reaches; Z25 errors on one no floor reaches.
    # Neither may fire for a hallway or the hub: the script enters them.
    report = committed["result"].report
    said = [str(f) for f in list(report.errors) + list(report.warnings)]
    for zone in [h.zone for h in committed["hallways"]] + ["hub"]:
        assert not any(f"{zone!r}" in line and ("Z3" in line or "Z25" in line) for line in said), zone
    assert check_reachability(committed["bp"]).errors == []


def test_rooms_past_the_hub_count_as_reached_through_the_teleport(committed) -> None:
    # The teleport is the edge into the hub; the wing behind the hub's door is
    # then reached the ordinary way, by Z3's door walk and Z25's flood.
    said = [str(f) for f in list(committed["result"].report.errors)
            + list(committed["result"].report.warnings)]
    assert not any("wing" in line and ("Z3" in line or "Z25" in line) for line in said)
    assert ss.hallway_links(committed["bp"], committed["hallways"], "wing") == []


def test_without_the_declaration_the_same_map_is_reported() -> None:
    # The declaration is what the checks accept, not a blind spot: the same
    # layout with the plain start is unreachable.
    bp, _, _ = split_map()
    codes = {f.code for f in check_reachability(bp).errors}
    assert "Z25" in codes


def test_no_walkable_route_links_any_two_hallways_or_the_hub(committed) -> None:
    assert ss.hallway_links(committed["bp"], committed["hallways"], "hub") == []


def test_hallway_links_does_see_a_joined_pair() -> None:
    # The isolation check can fail: a "hallway" whose spawn stands in another
    # hallway's room is reported as linked to it.
    bp, hallways, _ = split_map()
    stray = ss.Hallway(hallways[1].zone, (0.0, 100.0, 16.0), hallways[1].button)
    assert ss.hallway_links(bp, [hallways[0], stray], "hub") == [(hallways[1].zone, hallways[0].zone)]


def test_each_initial_spawn_sits_in_a_distinct_hallway(committed) -> None:
    bp = committed["bp"]
    (start,) = bp.elements(PlayerStart)
    volumes = {z.name: z.bounds for z in bp.elements(Zone)}
    homes = []
    for point in start.slot_positions():
        inside = [name for name, b in volumes.items()
                  if b.mins.x <= point.x <= b.maxs.x and b.mins.y <= point.y <= b.maxs.y]
        assert len(inside) == 1 and inside[0].startswith("hall_"), (point, inside)
        homes.append(inside[0])
    assert len(set(homes)) == len(homes) == start.slots
    # and the emitted structs are those points: one initial_spawn per slot
    assert committed["result"].report.errors == []


def test_eight_slots_get_eight_hallways() -> None:
    bp, hallways, hub = split_map(halls=8, slots=8)
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    (start,) = bp.elements(PlayerStart)
    assert start.slots == 8 and bp.script.lift_player_cap
    assert start.slot_positions() == [Point(*h.spawn) for h in hallways]


def test_fewer_hallways_than_slots_is_refused() -> None:
    bp, hallways, hub = split_map(halls=4, slots=4)
    with pytest.raises(ValueError, match="every slot needs a hallway"):
        ss.install_split_start(bp, hallways=hallways[:3], hub_zone="hub", hub=hub)


def test_installing_twice_is_refused() -> None:
    bp, hallways, hub = split_map()
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    with pytest.raises(ValueError):
        ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)


def test_the_strings_ship(committed) -> None:
    strings = committed["strings"]
    for ref in (ss.PROMPT_REF, ss.WON_REF, ss.LOST_REF, ss.TIMEOUT_REF):
        assert ref in strings
    assert "[{+activate}]" in strings and "5,000" in strings


# -- the rendered logic --------------------------------------------------------
def test_player_i_gets_hallway_i_and_no_two_share() -> None:
    script = _script(8)
    init = _body(script, "zmf_split_init")
    for n in range(8):
        assert f'level.zmf_split_halls[ {n} ] = s_hall;' in init
    assert f's_hall.zone = "hall_8";' in init
    claim = _body(script, "zmf_split_claim")
    assert "n_want = self.playernum;" in claim
    assert "self zmf_split_free( n_want )" in claim
    # a taken hallway falls through to the first free one, and the claim is recorded
    assert "for ( i = 0; !isdefined( n_hall ) && i < level.zmf_split_halls.size; i++ )" in claim
    assert "level.zmf_split_halls[ n_hall ].owner = self;" in claim
    assert "return !isdefined( e_owner ) || e_owner == self;" in _body(script, "zmf_split_free")
    spawned = _body(script, "zmf_split_on_spawned")
    assert "self SetOrigin( s_where.origin );" in spawned
    assert "self SetPlayerAngles( s_where.angles );" in spawned


def test_spawn_hooks_are_in_place_before_anyone_spawns() -> None:
    script = _script()
    init = _body(script, "zmf_split_init")
    assert "level.check_for_valid_spawn_near_team_callback = &zmf_split_spawn_point;" in init
    assert "callback::on_spawned( &zmf_split_on_spawned );" in init
    assert "wait" not in init
    assert script.in_slot(ss.Slot.AFTER_ENTRY) == ("zmf_split_init();",)
    where = _body(script, "zmf_split_where")
    assert where.index('"hallways"') < where.index("zmf_split_claim()") < where.index("zmf_split_hub_point()")


def test_button_first_press_wins_under_a_lock() -> None:
    script = _script()
    button = _body(script, "zmf_split_button")
    assert 'SetHintString( &"P" )' in button
    tail = button[button.index('waittill( "trigger", e_who );'):]
    # nothing yields between the press and the lock, so no second press can win
    assert "wait" not in tail.replace('waittill( "trigger", e_who );', "", 1)
    assert tail.index("player_is_in_laststand") < tail.index("zmf_split_lock()") \
        < tail.index("level thread zmf_split_finish( e_who );")
    lock = _body(script, "zmf_split_lock")
    assert lock == ('if ( level.zmf_split_phase != "hallways" )\n{\n\treturn false;\n}\n'
                    'level.zmf_split_phase = "hub";\nreturn true;')
    deadline = _body(script, "zmf_split_deadline")
    assert "zmf_split_lock()" in deadline  # the fallback takes the same lock


def test_press_pays_moves_the_presser_and_kills_the_rest_solo_safe() -> None:
    script = _script()
    finish = _body(script, "zmf_split_finish")
    won = finish[: finish.index("else")]
    assert "e_winner zm_score::add_to_player_score( 5000 );" in won
    assert won.index("e_winner zmf_split_to_hub();") < won.index("e_p zmf_split_kill();")
    # the presser is skipped, so in solo the loop kills nobody
    assert won.index("if ( e_p == e_winner )") < won.index("e_p zmf_split_kill();")
    kill = _body(script, "zmf_split_kill")
    assert kill.index('self.sessionstate == "spectator"') < kill.index("dodamage")
    assert "self.lives = 0;" in kill and "self dodamage( self.health + 1000, self.origin );" in kill
    assert kill.rstrip().endswith("self.bleedout_time = 0;")
    assert "if ( !self laststand::player_is_in_laststand() )" in kill


def test_the_dead_respawn_in_the_hub() -> None:
    script = _script()
    point = _body(script, "zmf_split_spawn_point")
    assert "s_where = e_revivee zmf_split_where();" in point
    assert "return s_where;" in point and "return s_where.origin;" in point
    finish = _body(script, "zmf_split_finish")
    # the phase is "hub" before finish runs (the lock), so every later spawn,
    # late join and between-round respawn asks zmf_split_where and gets the hub
    assert 'level.zmf_split_phase = "hub";' in _body(script, "zmf_split_lock")
    assert "zmf_split_close();" in finish


def test_round_fallback_zeroes_everyone_and_moves_all() -> None:
    script = _script()
    deadline = _body(script, "zmf_split_deadline")
    assert 'level waittill( "start_of_round" );' in deadline
    assert "if ( level.round_number < 5 )" in deadline
    assert "level thread zmf_split_finish( undefined );" in deadline
    finish = _body(script, "zmf_split_finish")
    timeout = finish[finish.index("else"):]
    assert "e_p.score = 0;" in timeout and 'e_p.pers[ "score" ] = 0;' in timeout
    assert "e_p zm_laststand::auto_revive( e_p );" in timeout
    assert "e_p zmf_split_to_hub();" in timeout
    assert 'IPrintLnBold( &"T" )' in timeout
    assert "add_to_player_score" not in timeout
    custom = ss.split_start_script(
        hallways=[ss.Hallway("a", (0, 0, 0), (0, 1, 0))], hub_zone="hub",
        hub=[ss.HubPoint((0, 0, 0))], prompt_asset="P", won_asset="W", lost_asset="L",
        timeout_asset="T", deadline_round=7, points=2500)
    assert "if ( level.round_number < 7 )" in _body(custom, "zmf_split_deadline")
    assert "add_to_player_score( 2500 )" in _body(custom, "zmf_split_finish")


def test_hallways_are_sealed_after() -> None:
    script = _script()
    close = _body(script, "zmf_split_close")
    assert "s_hall.trigger delete();" in close
    assert "level.zones[ s_hall.zone ].is_enabled = false;" in close
    assert "level.zones[ s_hall.zone ].is_spawning_allowed = false;" in close
    assert 'zm_zonemgr::enable_zone( "hub" );' in close
    assert "[[ level.create_spawner_list_func ]]( level.zone_keys );" in close
    assert close.index("level.zombie_total++;") < close.index("a_zombies[ i ] Kill();")
    finish = _body(script, "zmf_split_finish")
    # every button thread and the fallback end on this, after the close
    assert finish.index("zmf_split_close();") < finish.index('level notify( "zmf_split_sealed", e_winner );')
    for name in ("zmf_split_button", "zmf_split_deadline"):
        assert 'level endon( "zmf_split_sealed" );' in _body(script, name)


def test_bad_arguments_are_refused() -> None:
    h = ss.Hallway("a", (0, 0, 0), (0, 1, 0))
    common = dict(hub=[ss.HubPoint((0, 0, 0))], prompt_asset="P", won_asset="W",
                  lost_asset="L", timeout_asset="T")
    with pytest.raises(ValueError):
        ss.split_start_script(hallways=[], hub_zone="hub", **common)
    with pytest.raises(ValueError):
        ss.split_start_script(hallways=[h, h], hub_zone="hub", **common)
    with pytest.raises(ValueError):
        ss.split_start_script(hallways=[h], hub_zone="a", **common)
    with pytest.raises(ValueError):
        ss.split_start_script(hallways=[h], hub_zone="hub", deadline_round=1, **common)


def test_the_rendered_standalone_script_resolves() -> None:
    # every call the module can emit resolves, on its own
    script = _script(8)
    text = "\n".join(f"#using {m};" for m in script.using) + "\n" + "\n".join(
        f"{f.signature}\n{{\n" + "\n".join("\t" + line for line in f.body) + "\n}\n"
        for f in script.functions)
    source = scan(text)
    assert source.issues == []
    assert unresolved(source) == []


def test_the_outcome_is_announced_and_readable() -> None:
    script = _script()
    init = _body(script, "zmf_split_init")
    assert "level.zmf_split_resolved = false;" in init
    finish = _body(script, "zmf_split_finish")
    assert 'level.zmf_split_resolved_by = "round";' in finish
    assert 'level.zmf_split_resolved_by = "press";' in finish
    assert "level.zmf_split_winner = e_winner;" in finish
    tail = finish[finish.index("zmf_split_close();"):]
    assert tail.index("level.zmf_split_resolved = true;") \
        < tail.index('level notify( "zmf_opening_resolved", e_winner );') \
        < tail.index('level notify( "zmf_opening_accepted", e_winner );') \
        < tail.index('level notify( "zmf_split_sealed", e_winner );')
    # the accepted notify is for a press only
    guard = tail[: tail.index('level notify( "zmf_opening_accepted"')]
    assert "if ( isdefined( e_winner ) )" in guard
    custom = ss.split_start_script(
        hallways=[ss.Hallway("a", (0, 0, 0), (0, 1, 0))], hub_zone="hub",
        hub=[ss.HubPoint((0, 0, 0))], prompt_asset="P", won_asset="W", lost_asset="L",
        timeout_asset="T", won_notify="my_press", resolved_notify="my_done")
    body = _body(custom, "zmf_split_finish")
    assert 'level notify( "my_press", e_winner );' in body and 'level notify( "my_done", e_winner );' in body
    with pytest.raises(ValueError):
        ss.split_start_script(
            hallways=[ss.Hallway("a", (0, 0, 0), (0, 1, 0))], hub_zone="hub",
            hub=[ss.HubPoint((0, 0, 0))], prompt_asset="P", won_asset="W", lost_asset="L",
            timeout_asset="T", won_notify="bad name")


# -- the presser's name and the solo line ---------------------------------------
def test_defaults_render_as_before() -> None:
    finish = _body(_script(), "zmf_split_finish")
    assert '\te_winner IPrintLnBold( &"W" );' in finish
    assert 'e_p IPrintLnBold( &"L" );' in finish
    assert "a_players.size < 2" not in finish


def test_the_lost_line_can_name_the_presser() -> None:
    hallways = [ss.Hallway("a", (0, 0, 0), (0, 1, 0))]
    script = ss.split_start_script(
        hallways=hallways, hub_zone="hub", hub=[ss.HubPoint((0, 0, 0))],
        prompt_asset="P", won_asset="W", lost_asset="L", timeout_asset="T",
        lost_names_presser=True)
    finish = _body(script, "zmf_split_finish")
    # the player entity is the parameter (_globallogic_player.gsc:71 names a
    # player the same way)
    assert 'e_p IPrintLnBold( &"L", e_winner );' in finish


def test_a_solo_press_gets_its_own_won_line() -> None:
    hallways = [ss.Hallway("a", (0, 0, 0), (0, 1, 0))]
    script = ss.split_start_script(
        hallways=hallways, hub_zone="hub", hub=[ss.HubPoint((0, 0, 0))],
        prompt_asset="P", won_asset="W", lost_asset="L", timeout_asset="T",
        won_solo_asset="WS")
    finish = _body(script, "zmf_split_finish")
    won = finish[: finish.index("e_p zmf_split_kill();")]
    assert won.index("if ( a_players.size < 2 )") < won.index('IPrintLnBold( &"WS" );') \
        < won.index("else") < won.index('IPrintLnBold( &"W" );')


def test_install_ships_the_solo_line_and_names_the_presser(tmp_path) -> None:
    bp, hallways, hub = split_map()
    text = ss.SplitStartText(
        prompt="Press ^3[{+activate}]^7 to press", won="You pressed it.",
        lost="&&1 pressed the button. You wake up in the hub next round.",
        timeout="Nobody pressed.", won_solo="You pressed it. Nobody else was here.")
    script = ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub, text=text)
    finish = _body(script, "zmf_split_finish")
    assert ", e_winner );" in finish and "a_players.size < 2" in finish
    assert ss.WON_SOLO_REF in bp.map_strings
    bad = ss.SplitStartText(prompt=text.prompt, won="&&1 won", lost="x", timeout="y")
    bp2, hallways2, hub2 = split_map()
    with pytest.raises(ValueError):
        ss.install_split_start(bp2, hallways=hallways2, hub_zone="hub", hub=hub2, text=bad)


def test_the_buttons_are_listed_for_the_design_review() -> None:
    """The buttons are script-spawned, so the review's element walk cannot see
    them; install_split_start lists one per hallway with its prompt."""
    bp, hallways, hub = split_map(halls=8, slots=8)
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    buttons = [i for i in bp.review_interactives if i["id"].startswith("split_start_button_")]
    assert [b["zone"] for b in buttons] == [h.zone for h in hallways]
    for b, h in zip(buttons, hallways):
        assert b["kind"] == "use_trigger" and tuple(b["at"]) == tuple(map(float, h.button))
        assert "[{+activate}]" in b["prompt"]


# -- Z78: after the split, nobody respawns in a sealed hallway ---------------------
# Clearing the respawn callback at
# resolution sends the dead back to their hallways, because the stock pick finds
# no point on a zmforge map and falls back to the initial struct
# (_zm.gsc:3282, :3315; _zm_gametype.gsc:552).
def test_after_resolution_every_respawn_source_points_at_the_hub() -> None:
    script = _script()
    finish = _body(script, "zmf_split_finish")
    assert "check_for_valid_spawn_near_team_callback = undefined" not in "\n".join(
        line for f in script.functions for line in f.body)
    # the stock fallback (spectator_respawn) is re-pointed for everyone, before
    # anything is told the opening is over
    assert finish.index("zmf_split_close();") \
        < finish.index("a_players[ i ].spectator_respawn = zmf_split_hub_point();") \
        < finish.index("level.zmf_split_resolved = true;")
    spawned = _body(script, "zmf_split_on_spawned")
    assert ("if ( level.zmf_split_resolved && isdefined( self.zmf_split_placed ) "
            "&& !self zmf_split_in_hall() )") in spawned
    assert "self.spectator_respawn = s_where;" in spawned
    in_hall = _body(script, "zmf_split_in_hall")
    assert "self zm_zonemgr::entity_in_zone( str_zone, true )" in in_hall


def test_z78_passes_the_committed_split_map(committed) -> None:
    from zmforge.verify.sealed_start import sealed_zones

    assert sealed_zones(committed["server"]) == [h.zone for h in committed["hallways"]]
    # the commit runs check_gameplay, which runs Z78
    assert not [f for f in committed["result"].report.errors if f.code == "Z78"]


@pytest.mark.parametrize("breakage", [
    # clearing the callback at resolution
    ("\tlevel notify( \"zmf_opening_resolved\"",
     "\tlevel.check_for_valid_spawn_near_team_callback = undefined;\n\tlevel notify( \"zmf_opening_resolved\""),
    ("a_players[ i ].spectator_respawn = zmf_split_hub_point();", ""),
    ("level.zones[ s_hall.zone ].is_enabled = false;", ""),
    ("&& !self zmf_split_in_hall() )", ")"),
])
def test_z78_fails_a_script_that_leaves_a_way_back(committed, breakage) -> None:
    from zmforge.verify.sealed_start import check_sealed_start

    old, new = breakage
    assert old in committed["server"]
    broken = committed["server"].replace(old, new, 1)
    codes = [f.code for f in check_sealed_start(None, broken).errors]
    assert codes and set(codes) == {"Z78"}


def test_z78_fails_a_respawn_point_inside_a_sealed_hallway(committed, tmp_path) -> None:
    from zmforge.mapsource import parse_map_text
    from zmforge.verify.sealed_start import check_sealed_start

    bp, hallways, hub = split_map()
    ss.install_split_start(bp, hallways=hallways, hub_zone="hub", hub=hub)
    # Forget the seal, so the respawn groups (blueprint.respawn) reach the
    # hallways as they would for any other zone.
    bp.elements(PlayerStart)[0].sealed_zones = ()
    seed_stock_weapon_table(tmp_path)
    project = Project.create(NAME, tmp_path, blueprint=bp)
    project.commit()
    document = parse_map_text(project.paths()["map"].read_text(encoding="utf-8"))
    said = [str(f) for f in check_sealed_start(document, committed["server"]).errors]
    assert any("player_respawn_point" in line and "'hall_1'" in line for line in said), said


def test_z78_is_silent_without_a_sealed_start() -> None:
    from zmforge.verify.sealed_start import check_sealed_start

    assert check_sealed_start(None, "function main()\n{\n}\n").errors == []
