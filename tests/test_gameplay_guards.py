"""Gameplay guards: each test builds the shape its guard rejects, and the
shape it accepts."""

from __future__ import annotations

from zmforge.script import tricks
from zmforge.script.bosses import Boss, BossHealth, boss_script, boss_strings
from zmforge.script.quest import EveryPlayerFlag, with_use_key
from zmforge.script.zonegate import initial_zones
from zmforge.verify.gameplay import check_gameplay_script, check_prompt_strings

EDGES = [("lot", "entry", "enter_entry"), ("entry", "waiting", "enter_waiting"),
         ("hall", "entry", "always_on")]


def _codes(report):
    return sorted(f.code for f in report)


def _fn(name, body, params=""):
    return f"function {name}({params})\n{{\n" + "\n".join("\t" + b for b in body) + "\n}\n"


def _script(zones, edges=EDGES, functions=""):
    lines = ["function main()", "{", "\tinit_zones = [];"]
    lines += [f'\tinit_zones[{i}] = "{z}";' for i, z in enumerate(zones)]
    lines += ["}", "function zone_hook()", "{",
              '\tlevel flag::init( "always_on" );', '\tlevel flag::set( "always_on" );']
    lines += [f'\tzm_zonemgr::add_adjacent_zone( "{a}", "{b}", "{f}" );' for a, b, f in edges]
    lines += ["}", ""]
    return "\n".join(lines) + functions


def test_initial_zones_lists_start_open_and_sealed_zones_only():
    zones = ["lot", "entry", "waiting", "hall", "corridor_1"]
    assert initial_zones(zones, "lot", EDGES) == ["lot", "corridor_1"]
    # An always_on neighbour of the start is open at load anyway.
    assert initial_zones(zones, "entry", EDGES) == ["entry", "hall", "corridor_1"]


def test_z67_fails_a_door_gated_zone_in_init_zones():
    assert "Z67" in _codes(check_gameplay_script(_script(["lot", "entry", "waiting"])))
    assert "Z67" not in _codes(check_gameplay_script(_script(["lot", "corridor_1"])))


def test_z68_fire_handler_must_cool_down_and_pay_last():
    watch = _fn("w", ['w_trap = getweapon( "smg_versatile" );',
                      'self waittill( "weapon_fired", w_fired );', "self thread h();"])
    bad = _fn("h", ["self zm_score::add_to_player_score( 150 );", "if ( x )", "{",
                    "\treturn;", "}"])
    assert _codes(check_gameplay_script(_script(["lot"], functions=watch + bad))) == ["Z68", "Z68"]
    good = tricks.job_creation_on_fire(origin=(0, 0, 0))
    text = "".join(_fn(f.name, f.body) for f in good.functions)
    assert "Z68" not in _codes(check_gameplay_script(_script(["lot"], functions=text)))


def test_z69_grenades_are_watched_on_grenade_fire():
    bad = _fn("w", ['w_trap = getweapon( "frag_grenade" );',
                    'self waittill( "weapon_fired", w_fired );', "self thread h();"])
    assert "Z69" in _codes(check_gameplay_script(_script(["lot"], functions=bad)))
    assert tricks.fire_wait_line("frag_grenade").startswith('self waittill( "grenade_fire"')
    assert "weapon_fired" in tricks.fire_wait_line("smg_versatile")


def test_z70_and_z71_spawn_delay_and_moves():
    stale = _fn("s", ['n_was = level.zombie_vars[ "zombie_spawn_delay" ];',
                      'zm_utility::set_zombie_var( "zombie_spawn_delay", n_was, 1 );'])
    move = _fn("m", ["wait 0.4;", "self setorigin( ( 0, 0, 0 ) );"])
    codes = _codes(check_gameplay_script(_script(["lot"], functions=stale + move)))
    assert codes == ["Z70", "Z71"]
    fixed = tricks.relocation_on_fire(arrival=(0, 0, 0))
    spike = tricks.spawn_spike_on_flag("enter_x")
    text = "".join(_fn(f.name, f.body) for f in (*fixed.functions, *spike.functions))
    assert not _codes(check_gameplay_script(_script(["lot"], functions=text)))


def test_z72_prompts_name_the_use_key():
    bad = 'REFERENCE\t\tQ_EXIT_LOCKED_PROMPT\nLANG_ENGLISH\t\t"It is locked"\n'
    assert _codes(check_prompt_strings(bad)) == ["Z72"]
    assert "[{+activate}]" in with_use_key("It is locked")


def test_z73_boss_is_guarded_and_capped():
    boss = Boss(key="b", name="B", spawn_at=(0.0, 0.0, 0.0), arrives="a", defeated="d",
                health=BossHealth(base=12500, per_round=1750, zombie_multiple=175))
    assets = {ref: ref for ref in boss_strings(boss)}
    text = "".join(_fn(f.name, f.body) for f in boss_script(boss, assets).functions)
    assert not _codes(check_gameplay_script(_script(["lot"], functions=text)))
    assert "if ( n_health > 250000 )" in text
    assert boss.health.at(8, 8) == 250_000
    stripped = text.replace("self.zmf_no_instakill = true;", "")
    assert "Z73" in _codes(check_gameplay_script(_script(["lot"], functions=stripped)))


def test_every_player_step_clears_its_flag_and_counts_only_players_present():
    step = EveryPlayerFlag(key="n", task="&&1 of &&2", start="s", done="d", flag="zmf_served")
    body = "\n".join(step.body(0, lambda role: (f"REF_{role.upper()}", 1)))
    assert "a_players[ j ].zmf_served = undefined;" in body
    assert 'sessionstate == "playing"' in body
    assert '&"REF_MISSING", a_players[ j ]' in body


# --------------------------------------------------------------------------
# Z79: few flavour broadcasts (P13, P17; the cemetery's 15)
# --------------------------------------------------------------------------
def _written(*customs):
    from zmforge.script.custom import merge

    script = merge(*customs) if customs else None
    return "".join(_fn(f.name, f.body, ", ".join(f.params))
                   for f in (script.functions if script else ()))


def test_flavour_broadcasts_over_the_limit_warn():
    from zmforge.script import gags
    from zmforge.verify.gameplay import FLAVOUR_BROADCAST_LIMIT, flavour_broadcasts

    script = _written(
        gags.player_reactions(rooms={"gate": "S_GATE", "shed": "S_SHED"},
                              idle=("hills", 25.0, "S_IDLE")),
        gags.round_announcer([["S_PA_0", "S_PA_1"], ["S_PA_2"]]),
        gags.random_announcements(["S_R_0"]))
    assert flavour_broadcasts(script) == {"zone-entry": 2, "round-end PA": 3, "random PA": 1}
    report = check_gameplay_script(_script(["lot"]) + script)
    assert _codes(report) == ["Z79"]
    assert f"over {FLAVOUR_BROADCAST_LIMIT}" in next(iter(report)).message


def test_replies_to_players_and_a_couple_of_lines_pass():
    from zmforge.script import gags

    script = _written(
        gags.player_reactions(downed="S_DOWN", pap="S_PAP", idle=("hills", 25.0, "S_IDLE")),
        gags.box_reactions(used="S_BOX", moved="S_MOVED"),
        gags.power_on_announcement("S_POWER"),
        gags.round_announcer([["S_PA_0", "S_PA_1"]]))
    assert _codes(check_gameplay_script(_script(["lot"]) + script)) == []


def test_announcer_helpers_take_nothing_and_add_nothing():
    from zmforge.script import gags

    for empty in (gags.round_announcer([]), gags.round_announcer([[], []]),
                  gags.random_announcements([]), gags.power_on_announcement(None)):
        assert empty.empty
