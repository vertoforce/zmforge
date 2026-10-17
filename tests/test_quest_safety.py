"""Q1-Q7 (verify.quest_safety): each check breaks on a defect Workshop players
commonly report and passes what the quest and boss generators write."""

from __future__ import annotations

import pytest

from zmforge.script import quest as q
from zmforge.script.bosses import (
    BOSS_TTK,
    GUN_TIER_DPS,
    Boss,
    BossHealth,
    boss_script,
    boss_strings,
    gun_tier,
)
from zmforge.verify.quest_safety import check_quest_safety, wall_weapons_in_map

BOSS = Boss(key="examiner", name="THE EXAMINER", spawn_at=(0.0, 0.0, 0.0),
            arrives="It arrives.", defeated="It is failed.",
            health=BossHealth(ttk=40.0))


def _fn(name, body, params=""):
    return f"function {name}({params})\n{{\n" + "\n".join("\t" + b for b in body) + "\n}\n"


def _render(script) -> str:
    return "\n".join(_fn(f.name, f.body, ", ".join(f.params)) for f in script.functions)


def _codes(report, level="ERROR"):
    return sorted(f.code for f in report if str(f).startswith(level))


def _quest(steps) -> q.Quest:
    return q.Quest(key="register", header="CARS: &&1 OF &&2", intro="Go.",
                   step_done="&&1 OF &&2", complete="Done.", idle="CURRENT TASK: wait",
                   steps=tuple(steps))


def _quest_gsc(steps) -> str:
    quest = _quest(steps)
    return _render(q.quest_script(quest, {r: r for r in q.quest_strings(quest)}))


TIMED = q.HitTargets(key="vision", task="t (&&1/&&2)", start="s", done="d",
                     targets=(q.Target(point=(0.0, 200.0, 60.0)),),
                     time_limit=20.0, timeout="Out of time.")
FORMS = q.CollectDeliver(
    key="forms", task="t (&&1/&&2)", start="s", done="d",
    items=(q.Item(point=(-150.0, -150.0, 0.0), picked="You took form A."),),
    deliver_at=(0.0, -200.0, 0.0), pickup_prompt="Hold ^3[{+activate}]^7 to take",
    deliver_prompt="Hold ^3[{+activate}]^7 to hand in", empty="Nothing.", dropped="Back.")
HOLD = q.StandInZone(key="queue", task="t (&&1/&&2 s)", start="s", done="d",
                     point=(0.0, 0.0, 0.0), seconds=30, reset_on_leave=True, left="Left.")
EVERY = q.EveryPlayerFlag(key="served", task="t (&&1/&&2)", start="s", done="d",
                          flag="zmf_ticket_served")
FIGHT = q.DefeatBoss(key="road", task="t (&&1%)", start="s", done="d", boss=BOSS,
                     arena=(100.0, 0.0, 0.0))


# -- the generators pass their own checks ----------------------------------
def test_every_generated_step_kind_passes_q1_to_q7():
    gsc = _quest_gsc([TIMED, FORMS, HOLD, EVERY, FIGHT])
    report = check_quest_safety(gsc, wall_weapons=set())
    assert _codes(report) == [], [str(f) for f in report]
    assert _codes(report, "WARNING") == []


def test_lockdown_holds_special_rounds_and_waits_to_start():
    gsc = _quest_gsc([q.HitTargets(**{**TIMED.__dict__, "lockdown": True}),
                      q.StandInZone(**{**HOLD.__dict__, "lockdown": True})])
    assert "function zmf_quest_holding(" in gsc
    assert "level.next_dog_round = level.round_number + 2;" in gsc
    assert "// hold: vision" in gsc and "// hold: queue" in gsc
    step = gsc.split("function zmf_quest_step_vision(")[1].split("\n}\n")[0]
    assert step.index('flag::get( "special_round" )') < step.index("zmf_q_state[ 0 ] = 1;")
    assert _codes(check_quest_safety(gsc)) == []


def test_lockdown_is_only_for_timed_hold_and_kill_steps():
    with pytest.raises(ValueError):
        q.SurviveRounds(key="w", task="t", start="s", done="d", rounds=2, lockdown=True)
    q.KillInZone(key="k", task="t", start="s", done="d", point=(0, 0, 0), count=3,
                 lockdown=True)


def test_a_carried_item_goes_back_when_its_carrier_goes_down():
    gsc = _quest_gsc([FORMS])
    item = gsc.split("function zmf_quest_item_forms(")[1].split("\n}\n")[0]
    assert "laststand::player_is_in_laststand()" in item.split("zmf_q_bag[ 0 ]++")[1]


def test_a_hold_pauses_for_a_downed_player_and_a_dog_round():
    gsc = _quest_gsc([HOLD])
    step = gsc.split("function zmf_quest_step_queue(")[1]
    assert "else if ( n_t > 0 && !b_down_in )" in step
    assert 'if ( level flag::get( "special_round" ) )' in step


# -- each check breaks on the defect ----------------------------------------
def test_q1_step_without_end_game_and_player_thread_without_disconnect():
    gsc = _fn("zmf_quest_step_x", ["while ( true )", "{", "\twait 1;", "}"])
    gsc += _fn("zmf_quest_watch", ['self waittill( "weapon_fired" );'])
    gsc += _fn("zmf_quest_attach", ['level endon( "end_game" );',
                                    "a_players[ i ] thread zmf_quest_watch();"])
    assert _codes(check_quest_safety(gsc)) == ["Q1", "Q1"]


def test_q1_player_from_a_trigger_used_after_a_wait():
    body = ['level endon( "end_game" );', 't waittill( "trigger", e_who );', "wait 5;",
            "e_who IPrintLnBold( &\"X\" );"]
    assert _codes(check_quest_safety(_fn("zmf_quest_step_x", body))) == ["Q1"]
    fixed = body[:3] + ["if ( isdefined( e_who ) )", "{", "\te_who IPrintLnBold( &\"X\" );", "}"]
    assert _codes(check_quest_safety(_fn("zmf_quest_step_x", fixed))) == []


def test_q2_item_thread_without_a_down_return():
    gsc = _quest_gsc([FORMS]).replace(
        ' || e_who laststand::player_is_in_laststand()', "")
    assert "Q2" in _codes(check_quest_safety(gsc))


def test_q3_countdown_without_a_pause_or_hold():
    gsc = _quest_gsc([TIMED]).replace('level flag::get( "special_round" )', "false")
    assert "Q3" in _codes(check_quest_safety(gsc))


def test_q4_hud_scope():
    bad = _fn("zmf_quest_hud", ["level.zmf_line = NewClientHudElem( e_p );"])
    bad += _fn("zmf_quest_hud2", ["e_p.zmf_line = NewHudElem();"])
    bad += _fn("zmf_quest_hud3", ["e_hud = NewClientHudElem( getplayers()[ 0 ] );"])
    assert _codes(check_quest_safety(bad)) == ["Q4", "Q4", "Q4"]
    ok = _fn("zmf_quest_hud", ["e_p.zmf_line = NewClientHudElem( e_p );"])
    ok += _fn("zmf_boss_mark", ["// level-wide HUD: a waypoint for everyone",
                                "self.m = NewHudElem();"])
    assert _codes(check_quest_safety(ok)) == []


def test_q5_counts_and_scaling_and_one_shot_movers():
    count = _fn("zmf_quest_step_all", [
        'level endon( "end_game" );', "a_players = getplayers();", "n = 0;",
        "if ( n >= a_players.size )", "{", "\treturn;", "}"])
    scale = _fn("zmf_boss_x_setup", ["n = 100 * ( getplayers().size - 1 );"])
    mover = _fn("zmf_arena_enter", ['t waittill( "trigger", e_who );',
                                    "e_who setorigin( ( 0, 0, 0 ) );", "t delete();"])
    codes = _codes(check_quest_safety(count + scale + mover))
    assert codes.count("Q5") == 3
    # EveryPlayerFlag counts the players present: clean.
    assert "Q5" not in _codes(check_quest_safety(_quest_gsc([EVERY])))


def test_q6_every_boss_declares_a_time_to_kill_and_eases_spawns():
    old = Boss(key="old", name="OLD", spawn_at=(0.0, 0.0, 0.0), arrives="a", defeated="d",
               health=BossHealth(base=3000), fight_zombie_limit=None)
    gsc = _render(boss_script(old, {r: r for r in boss_strings(old)}))
    assert _codes(check_quest_safety(gsc)) == ["Q6"]
    assert _codes(check_quest_safety(gsc), "WARNING") == []  # opted out on purpose
    gsc = _render(boss_script(BOSS, {r: r for r in boss_strings(BOSS)}))
    assert "self.zmf_boss_ttk = 40;" in gsc
    assert "level.zombie_ai_limit = 10;" in gsc
    assert "function zmf_boss_examiner_hold(ai)" in gsc
    assert _codes(check_quest_safety(gsc)) == []


def test_boss_health_follows_the_guns():
    h = BossHealth(ttk=40.0, per_extra_player=0.75, cap=None)
    assert gun_tier(2) == "opening" and gun_tier(8) == "early" and gun_tier(20) == "late"
    assert h.at(8, 1) == int(40 * GUN_TIER_DPS["early"])
    assert h.at(8, 4) == int(40 * GUN_TIER_DPS["early"] * 3.25)
    assert BossHealth(ttk=40.0, tier="middle").at(3, 1) == 40 * GUN_TIER_DPS["middle"]
    with pytest.raises(ValueError):
        BossHealth(ttk=40.0, base=100)
    with pytest.raises(ValueError):
        BossHealth(tier="early")


def test_the_gravedigger_calibration_and_a_cap_that_scales_with_players():
    """The design target: 100,000 solo at round 6, +75% a player,
    and a cap that never clips a full lobby."""
    h = BossHealth(ttk=BOSS_TTK, per_extra_player=0.75)
    assert [h.at(6, n) for n in (1, 4, 8)] == [100_000, 325_000, 625_000]
    capped = BossHealth(ttk=100.0, per_extra_player=0.75, cap=150_000)
    assert capped.at(6, 1) == 150_000 and capped.at(6, 4) == 487_500


def test_a_boss_runs_and_its_minions_armour_it():
    boss = Boss(key="gd", name="THE GRAVEDIGGER", spawn_at=(0.0, 0.0, 0.0), arrives="a",
                defeated="d", health=BossHealth(ttk=40.0), minions=4, armour=0.25)
    assert boss.speed == "run" and boss.hurt_speed is None
    gsc = _render(boss_script(boss, {r: r for r in boss_strings(boss)}))
    assert 'self.zmf_boss_speed = "run";' in gsc
    assert "sprint" not in gsc
    assert "self.actor_damage_func = &zmf_boss_gd_armour;" in gsc
    assert "return int( damage * 0.25 );" in gsc
    assert "level.zmf_boss_gd_adds++;" in gsc
    assert "BOSS_GD_EXPOSED" in boss_strings(boss)
    assert _codes(check_quest_safety(gsc)) == []
    with pytest.raises(ValueError):  # armour needs minions to drop it
        Boss(key="x", name="X", spawn_at=(0.0, 0.0, 0.0), arrives="a", defeated="d",
             health=BossHealth(ttk=40.0), armour=0.25)


def test_q7_luck():
    step = _fn("zmf_quest_step_x", ['level endon( "end_game" );',
                                    'level waittill( "zmf_rolled" );'])
    roll = _fn("zmf_roll", ["if ( randomint( 100 ) < 10 )", "{",
                            '\tlevel notify( "zmf_rolled" );', "}"])
    assert _codes(check_quest_safety(step + roll)) == ["Q7"]
    pity = roll.replace("if ( randomint( 100 ) < 10 )",
                        "if ( randomint( 100 ) < 10 || level.zmf_pity > 3 )")
    assert _codes(check_quest_safety(step + pity)) == []
    # A random wait is timing, not a gate.
    waits = _fn("zmf_roll", ["wait randomfloatrange( 5, 9 );", 'level notify( "zmf_rolled" );'])
    assert _codes(check_quest_safety(step + waits)) == []
    tele = _fn("zmf_tele", ["n = randomint( 3 );", "e_who setorigin( a_spots[ n ] );",
                            'level notify( "zmf_rolled" );'])
    assert _codes(check_quest_safety(step + tele)) == ["Q7"]
    drop = _fn("zmf_quest_step_y", ['level endon( "end_game" );',
                                    'level waittill( "powerup_grabbed" );'])
    assert _codes(check_quest_safety(drop)) == ["Q7"]
    gun = _fn("zmf_quest_step_z", ['level endon( "end_game" );',
                                   'w = getweapon( "ray_gun" );', 'w2 = getweapon( "smg_fastfire" );'])
    walls = wall_weapons_in_map('"model" "_prefabs/zm/zm_core/spawnable_weapon_smg_fastfire.map"')
    assert walls == {"smg_fastfire"}
    assert _codes(check_quest_safety(gun, wall_weapons=walls)) == ["Q7"]


def test_a_soul_box_passes_q1_to_q7():
    souls = q.SoulBox(key="feed", task="t (&&1/&&2)", start="s", done="d", lockdown=True,
                      vessels=(q.Vessel(point=(0.0, 0.0, 0.0), model="p7_zm_teddybear"),))
    report = check_quest_safety(_quest_gsc([souls, FIGHT]), wall_weapons=set())
    assert _codes(report) == [], [str(f) for f in report]
    assert _codes(report, "WARNING") == [], [str(f) for f in report]
