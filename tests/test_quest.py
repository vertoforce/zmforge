"""The quest framework, the objective HUD, the buyable win and the mini-boss.

Read off a committed one-room map: the emitted server script carries each
piece's wiring, every line ships as a precached map string, the stock
symbol table resolves every call, and the commit's own checks pass.  None
of it is an observation of play (see :mod:`zmforge.script.quest`).
"""

from __future__ import annotations

import re

import pytest

from zmforge import Project
from zmforge.recipes.layouts import one_room_map
from zmforge.script import quest as q
from zmforge.script.bosses import Boss, BossHealth, boss_script, install_boss_rounds
from zmforge.script.gsc import scan
from zmforge.script.symbols import ENGINE_BUILTINS, lookup, unresolved

from conftest import seed_stock_weapon_table

NAME = "zm_qst"

BOSS = Boss(
    key="examiner", name="THE EXAMINER", spawn_at=(100.0, 0.0, 0.0), yaw=180.0,
    arrives="THE EXAMINER is here.", defeated="THE EXAMINER is down.",
    health=BossHealth(base=3000, per_round=400, per_extra_player=0.5),
    minions=3, points=500, powerup="full_ammo",
)


def _quest(**over) -> q.Quest:
    steps = (
        q.HitTargets(
            key="vision", task="CURRENT TASK: shoot E, F in order (&&1/&&2)",
            start="Read the chart.", done="Vision test passed.",
            advance="&&1 of &&2 letters", wrong="Wrong letter. Start again.",
            hint=q.Hint(point=(0.0, 100.0, 0.0), text="Shoot the letters in order."),
            targets=(q.Target(point=(0.0, 200.0, 60.0), cue="Letter E"),
                     q.Target(point=(20.0, 200.0, 60.0), cue="Letter F")),
            pulse_fx="powerup_grabbed_solo",
        ),
        q.HitTargets(
            key="photo", task="CURRENT TASK: knife the camera after the flash (&&1/&&2)",
            start="Smile.", done="Photo taken.", mode="melee", hits=3,
            targets=(q.Target(point=(-100.0, 0.0, 50.0), model="p7_zm_teddybear"),),
            flash=q.Flash(line="FLASH! Knife it now.", late="Wait for the flash."),
            unlock_round=3, waiting="CURRENT TASK: photo booth opens at round &&1",
        ),
        q.CollectDeliver(
            key="forms", task="CURRENT TASK: hand in forms (&&1/&&2)",
            start="Find the forms.", done="Forms filed.", advance="&&1 of &&2 filed",
            items=(q.Item(point=(-150.0, -150.0, 0.0), picked="You took form A."),
                   q.Item(point=(150.0, -150.0, 0.0), picked="You took form B.")),
            deliver_at=(0.0, -200.0, 0.0), pickup_prompt="Hold ^3[{+activate}]^7 to take the form",
            deliver_prompt="Hold ^3[{+activate}]^7 to hand in forms",
            empty="You have no forms.", dropped="A form blew back to where it was.",
        ),
        q.KillInZone(key="cull", task="CURRENT TASK: kill in the lobby (&&1/&&2)",
                     start="Clear the lobby.", done="Lobby clear.", advance="&&1 down",
                     point=(0.0, 0.0, 0.0), count=12, pulse_fx="powerup_on"),
        q.StandInZone(key="queue", task="CURRENT TASK: hold the queue (&&1/&&2 s)",
                      start="Stand in line.", done="Your turn.", point=(0.0, 0.0, 0.0),
                      seconds=30, reset_on_leave=True, left="You lost your place."),
        q.SurviveRounds(key="wait", task="CURRENT TASK: survive (&&1/&&2)",
                        start="Take a seat.", done="Called.", rounds=2),
        q.DefeatBoss(key="road", task="CURRENT TASK: fail THE EXAMINER (&&1% left)",
                     start="Road test.", done="You passed.", boss=BOSS,
                     arena=(100.0, 0.0, 0.0)),
    )
    fields = dict(
        key="register", header="CARS REGISTERED: &&1 OF &&2", intro="Register your cars.",
        step_done="CAR &&1 OF &&2 REGISTERED", complete="All cars registered.",
        idle="CURRENT TASK: wait for your appointment", steps=steps,
        exit=q.BuyableExit(
            origin=(-200.0, 150.0, 0.0),
            locked_prompt="EXIT - register all cars first",
            prompt="Hold ^3[{+activate}]^7 to Leave [Cost: &&1]",
            locked="Not yet.", poor="Leaving costs &&1.",
            task="CURRENT TASK: leave by the front door (&&1)",
            win_line="You are free to go.", win_title="YOU ARE FREE TO GO",
        ),
    )
    fields.update(over)
    return q.Quest(**fields)


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("quest")
    blueprint = one_room_map(NAME)
    q.install_quest(blueprint, _quest())
    seed_stock_weapon_table(root)
    project = Project.create(NAME, root, blueprint=blueprint)
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "strings": paths["localized_strings"].read_text(encoding="utf-8"),
        "zone": paths["manifest"].read_text(encoding="utf-8"),
    }


def _body(server: str, name: str) -> str:
    start = server.index(f"function {name}(")
    return server[start: server.index("\n}\n", start) + 2]


def test_the_commit_checks_pass_and_every_call_resolves(committed) -> None:
    assert committed["result"].report.errors == [], [str(e) for e in committed["result"].report.errors]
    source = scan(committed["server"])
    assert source.issues == []
    assert unresolved(source) == []


def test_every_new_call_carries_its_stock_evidence() -> None:
    for name in ("newclienthudelem", "settext", "fadeovertime", "destroy", "setmodel",
                 "playfx", "playfxontag", "geteye", "getweaponforwarddir", "bullettrace",
                 "distance2dsquared", "vectorscale", "abs", "int", "randomfloatrange"):
        assert re.search(r"\.gsc:\d+", ENGINE_BUILTINS[name]), name
    assert "_zm_score.gsc:655" in lookup("zm_score::can_player_purchase").evidence
    assert "_zm_spawner.gsc:2463" in lookup(
        "zm_spawner::register_zombie_death_event_callback").evidence
    assert "_zm_powerups.gsc:688" in lookup("zm_powerups::specific_powerup_drop").evidence


def test_every_line_ships_and_prompts_are_triggerstrings(committed) -> None:
    texts = q.quest_strings(_quest())
    for ref, (text, kind) in texts.items():
        asset = f"{NAME.upper()}_{ref}"
        assert f'#precache( "{kind}", "{asset}" );' in committed["server"], ref
        assert text in committed["strings"], ref
    assert texts["Q_REGISTER_FORMS_PICKUP_PROMPT"][1] == "triggerstring"
    assert texts["Q_REGISTER_EXIT_PROMPT"][1] == "triggerstring"


def test_the_quest_starts_after_the_intro_fade(committed) -> None:
    assert "level thread zmf_quest_init();" in committed["server"]
    init = _body(committed["server"], "zmf_quest_init")
    assert init.index('flag::wait_till( "initial_blackscreen_passed" )') < init.index(
        "level thread zmf_quest_step_vision();")
    assert "flag::init" not in init   # check Z3: see the quest docstring
    assert "level.zmf_quest_done = 0;" in init


def test_ordered_steps_wait_for_the_one_before(committed) -> None:
    photo = _body(committed["server"], "zmf_quest_step_photo")
    assert "while ( level.zmf_q_state[ 0 ] != 2 )" in photo
    assert "while ( level.round_number < 3 )" in photo
    vision = _body(committed["server"], "zmf_quest_step_vision")
    assert "zmf_quest_step_done" not in vision


def test_the_hud_is_persistent_top_left_text(committed) -> None:
    elem = _body(committed["server"], "zmf_quest_hud_elem")
    assert "NewClientHudElem( e_player );" in elem
    assert 'e_hud.horzAlign = "user_left";' in elem and 'e_hud.vertAlign = "user_top";' in elem
    draw = _body(committed["server"], "zmf_quest_hud_draw")
    assert (f'self.zmf_qh_head SetText( &"{NAME.upper()}_Q_REGISTER_HEADER", '
            "level.zmf_quest_count, level.zmf_quest_steps );") in draw
    assert "SetText( level.zmf_quest_task[ n ], level.zmf_q_n[ n ], level.zmf_q_of[ n ] );" in draw
    attach = _body(committed["server"], "zmf_quest_hud_attach")
    assert 'level waittill( "connected", player );' in attach
    assert "destroy();" in _body(committed["server"], "zmf_quest_hud_end")


def test_shooting_uses_the_aim_ray_and_a_trace(committed) -> None:
    aimed = _body(committed["server"], "zmf_quest_aimed_at")
    assert "BulletTrace( v_eye, a_pts[ j ], false, self );" in aimed
    assert "VectorDot( v_fwd, VectorNormalize( v_to ) );" in aimed
    watch = _body(committed["server"], "zmf_quest_aim_watch")
    assert 'self waittill( "weapon_fired" );' in watch
    assert 'self waittill( "weapon_melee" );' in watch


def test_an_ordered_wrong_hit_resets_and_cues_again(committed) -> None:
    vision = _body(committed["server"], "zmf_quest_step_vision")
    assert "if ( j != n_tgt )" in vision
    assert f'&"{NAME.upper()}_Q_REGISTER_VISION_WRONG"' in vision
    # at the start, after a reset, and in the next-target table
    assert vision.count(f'&"{NAME.upper()}_Q_REGISTER_VISION_CUE0"') == 3


def test_knifing_counts_only_inside_the_flash(committed) -> None:
    photo = _body(committed["server"], "zmf_quest_step_photo")
    assert '"zmf_q_hit_photo", "zmf_q_end_photo" );' in photo and ", 1, 72, " in photo
    assert "gettime() > level.zmf_q_open_photo" in photo
    flash = _body(committed["server"], "zmf_quest_flash_photo")
    assert "RandomFloatRange( 5, 9 )" in flash and "gettime() + 2000" in flash
    assert 'SetModel( "p7_zm_teddybear" )' in photo
    assert "xmodel,p7_zm_teddybear" in committed["zone"]


def test_items_are_carried_and_come_back_when_the_carrier_bleeds_out(committed) -> None:
    item = _body(committed["server"], "zmf_quest_item_forms")
    assert 'e_who.sessionstate == "spectator"' in item
    assert "e_who.zmf_q_bag[ 2 ]++;" in item and "e_who.zmf_q_bag[ 2 ]--;" in item
    desk = _body(committed["server"], "zmf_quest_desk_forms")
    assert "e_who.zmf_q_sent[ 2 ]++;" in desk
    assert f'&"{NAME.upper()}_Q_REGISTER_FORMS_EMPTY"' in desk


def test_kills_count_through_the_stock_death_callback(committed) -> None:
    step = _body(committed["server"], "zmf_quest_step_cull")
    assert "zm_spawner::register_zombie_death_event_callback( &zmf_quest_kill_cull );" in step
    kill = _body(committed["server"], "zmf_quest_kill_cull")
    assert "wait" not in kill
    assert "Distance2DSquared( self.origin, ( 0, 0, 0 ) ) > 90000" in kill


def test_standing_and_surviving(committed) -> None:
    stand = _body(committed["server"], "zmf_quest_step_queue")
    assert "n_t += 0.5;" in stand and "laststand::player_is_in_laststand()" in stand
    assert f'&"{NAME.upper()}_Q_REGISTER_QUEUE_LEFT"' in stand
    survive = _body(committed["server"], "zmf_quest_step_wait")
    assert 'level waittill( "end_of_round" );' in survive


def test_the_boss_is_a_tougher_glowing_zombie(committed) -> None:
    spawn = _body(committed["server"], "zmf_boss_examiner_spawn")
    assert "e_spawner.script_forcespawn = 1;" in spawn
    assert 'zombie_utility::spawn_zombie( e_spawner, "zmf_boss_examiner", s_at );' in spawn
    setup = _body(committed["server"], "zmf_boss_examiner_setup")
    assert setup.index("self.zombie_init_done") < setup.index("self.health = n_health;")
    assert "self.ignore_nuke = true;" in setup and "self.no_powerups = true;" in setup
    # red and on fire on head, chest and hips (principle P14), not one glow
    for tag in ("j_head", "j_spine4", "J_SpineLower"):
        assert f'PlayFXOnTag( level._effect[ "zmf_boss_aura" ], self, "{tag}" );' in setup
        assert f'PlayFXOnTag( level._effect[ "zmf_boss_fire" ], self, "{tag}" );' in setup
    death = _body(committed["server"], "zmf_boss_examiner_death")
    assert 'zm_powerups::specific_powerup_drop( "full_ammo", v_at );' in death
    assert "zm_score::add_to_player_score( 500 );" in death
    road = _body(committed["server"], "zmf_quest_step_road")
    assert 't_arena = spawn( "trigger_radius"' in road
    assert "n_pct = int( ( ai.health * 100 ) / ai.maxhealth );" in road


def test_the_exit_is_locked_then_sells_the_win(committed) -> None:
    exit_ = _body(committed["server"], "zmf_quest_exit")
    assert "if ( !level.zmf_quest_done )" in exit_
    assert "zm_score::can_player_purchase( 20000 )" in exit_
    assert "zm_score::minus_to_player_score( 20000 );" in exit_
    opened = _body(committed["server"], "zmf_quest_exit_open")
    assert f'SetHintString( &"{NAME.upper()}_Q_REGISTER_EXIT_PROMPT", 20000 );' in opened
    win = _body(committed["server"], "zmf_quest_win")
    assert win.index("level.custom_game_over_hud_elem = &zmf_quest_win_hud;") < win.index(
        'level notify( "end_game" );')
    hud = _body(committed["server"], "zmf_quest_win_hud")
    assert f'e_game_over SetText( &"{NAME.upper()}_Q_REGISTER_EXIT_WIN_TITLE" );' in hud


def test_bad_quests_are_refused() -> None:
    with pytest.raises(ValueError):
        q.param_count("only &&2")
    with pytest.raises(ValueError):
        q.HitTargets(key="x", task="t", start="s", done="d", targets=())
    with pytest.raises(ValueError):
        q.HitTargets(key="x", task="t", start="s", done="d", mode="kick",
                     targets=(q.Target(point=(0, 0, 0)),))
    with pytest.raises(ValueError):
        q.SurviveRounds(key="x", task="t", start="s", done="d", rounds=1, unlock_round=4)
    with pytest.raises(ValueError):
        _quest(steps=_quest().steps + (_quest().steps[0],))
    with pytest.raises(ValueError):
        Boss(key="Bad", name="n", spawn_at=(0, 0, 0), arrives="a", defeated="d")
    with pytest.raises(ValueError):
        Boss(key="b", name="n", spawn_at=(0, 0, 0), arrives="a", defeated="d", glow_fx="nope")
    # a start line may not ask for a parameter nobody passes
    bad = _quest(steps=(q.SurviveRounds(key="w", task="t", start="round &&1", done="d",
                                        rounds=1),))
    with pytest.raises(ValueError):
        q.quest_script(bad, {r: r for r in q.quest_strings(bad)})


def test_use_points_list_every_spawned_use_trigger() -> None:
    points = _quest().use_points()
    assert (0.0, -200.0, 0.0) in points and (-200.0, 150.0, 0.0) in points
    assert len(points) == 4


def test_boss_health_formula() -> None:
    health = BossHealth(base=3000, per_round=400, per_extra_player=0.5)
    # 3000 + 4000 + 35 * 1045 (stock round-10 zombie health)
    assert health.at(10, 1) == 43575
    assert health.at(10, 3) == 87150
    # Scaled by the players present (Q5), not getplayers().size (spectators).
    assert "n_present - 1" in health.expression()
    assert "getplayers" not in health.expression()


def test_a_boss_can_run_on_a_round_schedule(tmp_path) -> None:
    blueprint = one_room_map(NAME)
    install_boss_rounds(blueprint, BOSS, rounds=(8, 4))
    seed_stock_weapon_table(tmp_path)
    project = Project.create(NAME, tmp_path, blueprint=blueprint)
    result = project.commit()
    assert result.report.errors == []
    server = project.paths()["server_script"].read_text(encoding="utf-8")
    rounds = _body(server, "zmf_boss_examiner_rounds")
    assert "a_rounds[ 0 ] = 4;" in rounds and "a_rounds[ 1 ] = 8;" in rounds
    assert unresolved(scan(server)) == []
    assert boss_script(BOSS, {"BOSS_EXAMINER_ARRIVES": "A", "BOSS_EXAMINER_DEFEATED": "D"}).functions


def test_a_flash_countdown_needs_its_line_and_one_parameter() -> None:
    with pytest.raises(ValueError):
        q.Flash(line="FLASH", late="late", countdown=3)
    with pytest.raises(ValueError):
        q.Flash(line="FLASH", late="late", countdown=3, count_line="no number")
    with pytest.raises(ValueError):
        q.Flash(line="FLASH", late="late", count_fx="not_an_effect")
    f = q.Flash(line="FLASH", late="late")
    assert (f.countdown, f.early, f.screen) == (0, None, False)


def _timed_script(step) -> str:
    quest = _quest(steps=(step,))
    script = q.quest_script(quest, {r: r for r in q.quest_strings(quest)})
    return "\n".join(line for f in script.functions for line in (f.name, *f.body))


def test_a_time_limit_is_optional_and_only_on_hit_and_collect_steps() -> None:
    base = dict(key="x", task="t", start="s", done="d")
    target = (q.Target(point=(0, 0, 0)),)
    with pytest.raises(ValueError):  # no timeout line
        q.HitTargets(**base, targets=target, time_limit=10.0)
    with pytest.raises(ValueError):  # a timeout line with no limit
        q.HitTargets(**base, targets=target, timeout="Time's up.")
    with pytest.raises(ValueError):  # the timeout takes no parameters
        q.HitTargets(**base, targets=target, time_limit=10.0, timeout="up &&1")
    with pytest.raises(ValueError):
        q.HitTargets(**base, targets=target, time_limit=0.0, timeout="up")
    with pytest.raises(ValueError):  # the timer line needs the seconds as &&1
        q.HitTargets(**base, targets=target, time_limit=10.0, timeout="up", timer_line="hurry")
    with pytest.raises(ValueError):
        q.StandInZone(**base, point=(0, 0, 0), radius=64.0, seconds=10.0,
                      time_limit=10.0, timeout="up")
    # untimed steps emit no timer at all (the maps that predate it are unchanged)
    text = _timed_script(_quest().steps[0])
    assert "zmf_quest_timer_" not in text and "zmf_q_tout" not in text
    # nor any countdown text a review could read into the HUD
    untimed = _quest()
    assert all(s.timer_line is None for s in untimed.steps)
    assert not any(ref.endswith(("_TIMER", "_TIMEOUT")) for ref in q.quest_strings(untimed))
    with pytest.raises(ValueError):  # a timer line with no limit
        q.HitTargets(**base, targets=target, timer_line="left &&1")


def test_a_fractional_limit_counts_whole_seconds_after_the_first_tick() -> None:
    step = q.HitTargets(key="x", task="t", start="s", done="d", time_limit=2.5, timeout="up",
                        targets=(q.Target(point=(0, 0, 0)), q.Target(point=(9, 0, 0))))
    text = _timed_script(step)
    assert "for ( n = 3; n > 0; n-- )" in text and "wait 0.5;" in text


_CALL = re.compile(r"(?:\bthread\s+)?\b(zmf_quest_\w+)\(([^;]*)\);")


def _threads_under(fns, name: str, end: str, bound: bool, seen: set) -> list[tuple[str, bool]]:
    """Every script thread started (directly or through a plain call) from
    *name*: (function, whether ``str_end`` is bound to *end* in it)."""
    out = []
    for line in fns[name].body:
        for m in _CALL.finditer(line):
            callee, args = m.group(1), m.group(2)
            if callee not in fns or callee in seen:
                continue
            seen.add(callee)
            carries = f'"{end}"' in args or (bound and "str_end" in args)
            if re.search(rf"\bthread\s+{callee}\(", line):
                out.append((callee, carries))
            out += _threads_under(fns, callee, end, carries, seen)
    return out


#: Loops bound to an entity the step deletes before it ends, not to a notify.
_ENDS_WITH_ITS_ENTITY = {"zmf_quest_item_pulse"}


def _assert_every_step_thread_ends_with_its_step(quest: q.Quest) -> None:
    script = q.quest_script(quest, {r: r for r in q.quest_strings(quest)})
    fns = {f.name: f for f in script.functions}
    for step in quest.steps:
        end = f"zmf_q_end_{step.key}"
        body = list(fns[f"zmf_quest_step_{step.key}"].body)
        notify = body.index(f'level notify( "{end}" );')
        # a trigger the step hands to a watcher goes only after the watcher
        # has stopped
        handed = {m for line in body if "thread" in line for m in re.findall(r"\bt_\w+", line)}
        for j, line in enumerate(body):
            m = re.fullmatch(r"(t_\w+) delete\(\);", line.strip())
            if m and m.group(1) in handed:
                assert j > notify, (step.key, line)
        threads = _threads_under(fns, f"zmf_quest_step_{step.key}", end, False, set())
        for callee, carries in threads:
            if callee in _ENDS_WITH_ITS_ENTITY:
                continue
            own = f'level endon( "{end}" );' in fns[callee].body
            via = carries and "level endon( str_end );" in fns[callee].body
            assert own or via, f"{step.key}: {callee} outlives the step"


def test_every_thread_a_step_starts_ends_on_the_step_end() -> None:
    """P12: a finished step leaves no watcher, pulse, flash, timer or hint
    running, whatever the step type."""
    _assert_every_step_thread_ends_with_its_step(_quest())
    hint = q.Hint(point=(0.0, 0.0, 0.0), text="Look here.")
    target = (q.Target(point=(0.0, 0.0, 0.0)), q.Target(point=(9.0, 0.0, 0.0)))
    steps = (
        q.HitTargets(key="timed", task="t (&&1/&&2)", start="s", done="d", hint=hint,
                     targets=target, time_limit=20.0, timeout="up", wrong="no",
                     flash=q.Flash(line="GO", late="late", early="early", countdown=3,
                                   count_line="in &&1", screen=True)),
        q.CollectDeliver(key="bags", task="t (&&1/&&2)", start="s", done="d", hint=hint,
                         items=(q.Item(point=(1.0, 0.0, 0.0), picked="p"),),
                         deliver_at=(0.0, 0.0, 0.0), pickup_prompt="take", deliver_prompt="give",
                         empty="none", time_limit=30.0, timeout="up", pulse_fx="powerup_on"),
        q.SurviveRounds(key="rest", task="t (&&1/&&2)", start="s", done="d", hint=hint, rounds=1),
    )
    _assert_every_step_thread_ends_with_its_step(_quest(steps=steps))


def test_a_hint_is_owned_by_its_step_and_ends_with_it() -> None:
    hint = q.Hint(point=(0.0, 0.0, 0.0), text="Look here.")
    quest = _quest(steps=(q.SurviveRounds(key="rest", task="t (&&1/&&2)", start="s", done="d",
                                          hint=hint, rounds=1),))
    script = q.quest_script(quest, {r: r for r in q.quest_strings(quest)})
    fns = {f.name: f for f in script.functions}
    step = fns["zmf_quest_step_rest"].body
    assert "level thread zmf_quest_hint_rest( t_hint );" in step
    assert step.index('level notify( "zmf_q_end_rest" );') < step.index("t_hint delete();")
    assert 'level endon( "zmf_q_end_rest" );' in fns["zmf_quest_hint_rest"].body
    assert "t_hint delete();" not in fns["zmf_quest_hint_rest"].body


def test_a_plain_collect_counts_each_pickup_and_has_no_desk() -> None:
    """``deliver=False`` (Harvest Moon's golden corn): a
    pickup counts at once, there is no hand-in desk and no carry bag."""
    items = (q.Item(point=(1.0, 0.0, 0.0), picked="p"), q.Item(point=(9.0, 0.0, 0.0), picked="p"))
    step = q.CollectDeliver(key="corn", task="t (&&1/&&2)", start="s", done="d",
                            advance="a (&&1/&&2)", items=items, pickup_prompt="take", deliver=False)
    assert "deliver_prompt" not in step.lines() and "empty" not in step.lines()
    assert step.use_points() == [it.point for it in items]
    quest = _quest(steps=(step,))
    script = q.quest_script(quest, {r: r for r in q.quest_strings(quest)})
    fns = {f.name: f for f in script.functions}
    assert "zmf_quest_desk_corn" not in fns
    item = "\n".join(fns["zmf_quest_item_corn"].body)
    assert "zmf_q_bag" not in item
    assert item.index("t_item delete();") < item.index("zmf_quest_progress(")
    assert item.index("zmf_quest_progress(") < item.index('level notify( "zmf_q_filed_corn" );')
    body = "\n".join(fns["zmf_quest_step_corn"].body)
    assert "t_desk" not in body and 'level waittill( "zmf_q_filed_corn" );' in body
    _assert_every_step_thread_ends_with_its_step(quest)
    with pytest.raises(ValueError):
        q.CollectDeliver(key="corn", task="t", start="s", done="d", items=items,
                         pickup_prompt="take", deliver=False, deliver_at=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        q.CollectDeliver(key="corn", task="t", start="s", done="d", items=items,
                         pickup_prompt="take", deliver=False, time_limit=30.0, timeout="up")
    with pytest.raises(ValueError):
        q.CollectDeliver(key="corn", task="t", start="s", done="d", items=items, pickup_prompt="take")


# --------------------------------------------------------------------------
# Soul boxes (SoulBox / Vessel)
# --------------------------------------------------------------------------
def _souls(**over) -> q.SoulBox:
    fields = dict(
        key="feed", task="CURRENT TASK: feed them (&&1/&&2 souls)", start="Feed them.",
        done="Fed.", full="&&1 of &&2 full.",
        vessels=(q.Vessel(point=(0.0, 100.0, 0.0), model="p7_zm_teddybear", scale=2.0,
                          full_scale=3.0),
                 q.Vessel(point=(0.0, -100.0, 0.0), model="p7_zm_teddybear", rise=40.0)),
        souls=10, per_extra_player=4)
    fields.update(over)
    return q.SoulBox(**fields)


@pytest.fixture(scope="module")
def souls_committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("souls")
    blueprint = one_room_map(NAME)
    q.install_quest(blueprint, _quest(steps=(_souls(),), exit=None))
    seed_stock_weapon_table(root)
    project = Project.create(NAME, root, blueprint=blueprint)
    result = project.commit()
    paths = project.paths()
    return {"result": result, "server": paths["server_script"].read_text(encoding="utf-8"),
            "zone": paths["manifest"].read_text(encoding="utf-8")}


def test_a_soul_box_commits_and_every_call_resolves(souls_committed) -> None:
    assert souls_committed["result"].report.errors == [], [
        str(e) for e in souls_committed["result"].report.errors]
    source = scan(souls_committed["server"])
    assert source.issues == [] and unresolved(source) == []
    assert "xmodel,p7_zm_teddybear" in souls_committed["zone"]
    for name in ("moveto", "rotateto", "setscale", "distance", "isplayer", "playsound"):
        assert re.search(r"\.gsc:\d+|\.csc:\d+", ENGINE_BUILTINS[name]), name


def test_souls_scale_with_players_and_only_player_kills_count(souls_committed) -> None:
    server = souls_committed["server"]
    step = _body(server, "zmf_quest_step_feed")
    assert "level.zmf_q_need_feed = 10 + 4 * ( n_players - 1 );" in step
    assert "level.zmf_q_of[ 0 ] = level.zmf_q_need_feed * 2;" in step
    assert "zm_spawner::register_zombie_death_event_callback( &zmf_quest_soul_kill_feed );" in step
    # a death changes nothing: the need is only ever lowered, when a player leaves
    assert "if ( n_now < n_players && n_now > 0 )" in step
    kill = _body(server, "zmf_quest_soul_kill_feed")
    assert "wait" not in kill
    assert "if ( !isdefined( e_attacker ) || !isplayer( e_attacker ) )" in kill
    assert "level thread zmf_quest_soul_fly_feed( v_at + ( 0, 0, 40 ), n_best );" in kill
    # the nearest hungry vessel within the radius takes the soul
    assert "n_d = 160000;" in kill and "level.zmf_q_fill_feed[ n_best ]++;" in kill


def test_a_soul_flies_to_its_vessel_which_grows_rises_and_goes_dark_when_full(souls_committed) -> None:
    server = souls_committed["server"]
    fly = _body(server, "zmf_quest_soul_fly_feed")
    assert 'level endon( "end_game" );' in fly
    assert 'e_orb SetModel( "tag_origin" );' in fly
    assert 'PlayFXOnTag( level._effect[ "powerup_on_solo" ], e_orb, "tag_origin" );' in fly
    assert "e_orb MoveTo( v_to, n_t );" in fly and "e_orb delete();" in fly
    assert "e_box SetScale( 2 + 1 * n_f );" in fly
    assert "e_box MoveTo( ( 0, -100, -40 + 40 * n_f ), 0.3 );" in fly
    assert 'e_box playsound( "zmb_souls_end" );' in fly
    full = _body(server, "zmf_quest_soul_full_feed")
    assert "wait" not in full and "e_glow delete();" in full
    # the looping glow is only ever on a tag (glow.LOOPING_FX), never PlayFX
    assert 'PlayFX( level._effect[ "powerup_on' not in server
    step = _body(server, "zmf_quest_step_feed")
    assert 'e_box = spawn( "script_model", ( 0, -100, -40 ) );' in step
    assert step.index("wait 2.2;") < step.index('level notify( "zmf_q_end_feed" );')


def test_a_soul_box_is_gated_on_its_vessels_and_ends_its_threads() -> None:
    step = _souls()
    assert q.step_points(step) == [(0.0, 100.0, 0.0), (0.0, -100.0, 0.0)]
    assert step.total == 20 and "full" in step.lines()
    _assert_every_step_thread_ends_with_its_step(_quest(steps=(step,), exit=None))


def test_bad_soul_boxes_are_refused() -> None:
    with pytest.raises(ValueError):
        _souls(vessels=())
    with pytest.raises(ValueError):
        _souls(arrive_fx="powerup_on_solo")  # a looping effect played at a point
    with pytest.raises(ValueError):
        _souls(orb_fx="powerup_grabbed")  # a one-shot on a flying tag
    with pytest.raises(ValueError):
        _souls(vessels=(q.Vessel(point=(0.0, 0.0, 0.0)),))  # 'full' is for several vessels
    with pytest.raises(ValueError):
        q.Vessel(point=(0.0, 0.0, 0.0), rise=10.0)  # nothing to raise
    with pytest.raises(ValueError):
        _souls(souls=0)
