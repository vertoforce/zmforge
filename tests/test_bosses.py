"""The fallback mini-boss: 35 of the round's zombies in health, and a sprinter
that stays a sprinter (:mod:`zmforge.script.bosses`)."""

from __future__ import annotations

import re

import pytest

from zmforge.script.bosses import (
    BOSS_GLOW_TAGS,
    BOSS_LOUD_FX,
    BOSS_MARKER,
    BOSS_OWN_FX,
    BOSS_RED_FX,
    BOSS_ZOMBIE_MULTIPLE,
    Boss,
    BossHealth,
    BossProp,
    boss_script,
    stock_zombie_health,
)
from zmforge.script.symbols import lookup

ASSETS = {"BOSS_B_ARRIVES": "A", "BOSS_B_DEFEATED": "D"}


def _boss(**over) -> Boss:
    return Boss(key="b", name="B", spawn_at=(0.0, 0.0, 0.0), arrives="a", defeated="d", **over)


def _body(script, name: str) -> list[str]:
    return list(next(f for f in script.functions if f.name == name).body)


def test_default_health_is_35_zombies_scaled_per_player() -> None:
    assert BOSS_ZOMBIE_MULTIPLE == 35.0
    health = BossHealth()
    assert health.zombie_multiple == BOSS_ZOMBIE_MULTIPLE
    assert health.expression() == (
        "int( ( int( 35 * level.zombie_health ) ) * ( 1 + 0.75 * ( n_present - 1 ) ) )")
    assert health.at(1, 1) == 35 * 150
    assert health.at(10, 1) == 35 * 1045
    assert health.at(10, 4) == int(35 * 1045 * 3.25)


def test_stock_zombie_health_matches_ai_calculate_health() -> None:
    # zombie_utility.gsc:1906-1929 with the _zm.gsc:1209-1211 zombie_vars
    assert [stock_zombie_health(r) for r in (1, 2, 9, 10, 11)] == [150, 250, 950, 1045, 1149]


def test_the_emitted_health_uses_the_constant_and_zombie_health() -> None:
    setup = _body(boss_script(_boss(), ASSETS), "zmf_boss_b_setup")
    line = next(s for s in setup if s.startswith("n_health = "))
    assert f"int( {BOSS_ZOMBIE_MULTIPLE:g} * level.zombie_health )" in line


def test_bad_health_is_refused() -> None:
    with pytest.raises(ValueError):
        BossHealth(zombie_multiple=-1)
    with pytest.raises(ValueError):
        BossHealth(base=0, per_round=0, zombie_multiple=0)


def test_the_boss_runs_and_stays_running() -> None:
    """Tanky bosses are slower, not faster: run, not sprint
    (a sprinting tank boss is too fast to fight)."""
    boss = _boss()
    assert (boss.speed, boss.hurt_speed) == ("run", None)
    script = boss_script(boss, ASSETS)
    setup = _body(script, "zmf_boss_b_setup")
    lock = 'self zombie_utility::set_zombie_run_cycle_override_value( "run" );'
    assert lock in setup
    assert setup.index("self.health = n_health;") < setup.index(lock)
    assert setup.index(lock) < setup.index("self thread zmf_boss_b_speed();")
    keep = "\n".join(_body(script, "zmf_boss_b_speed"))
    assert 'self endon( "death" );' in keep
    assert "zmf_boss_hurt" not in keep
    assert "self.zombie_move_speed != self.zmf_boss_speed" in keep
    assert keep.index("self.zombie_move_speed_override = undefined;") < keep.index(
        "set_zombie_run_cycle_override_value( self.zmf_boss_speed );")
    assert "wait 1;" in keep


def test_a_second_phase_speed_is_possible() -> None:
    script = boss_script(_boss(speed="walk", hurt_speed="run"), ASSETS)
    assert 'self.zmf_boss_speed = "walk";' in _body(script, "zmf_boss_b_setup")
    keep = "\n".join(_body(script, "zmf_boss_b_speed"))
    assert 'self.zmf_boss_speed = "run";' in keep
    assert "self.health < self.maxhealth * 0.5" in keep


def test_the_override_call_is_a_read_stock_function() -> None:
    entry = lookup("zombie_utility::set_zombie_run_cycle_override_value")
    assert entry is not None and "zombie_move_speed_override" in entry.evidence


# -- The look: a boss must be unmistakable at a glance (principle P14) ------

def test_the_boss_glows_red_on_head_chest_and_hips() -> None:
    script = boss_script(_boss(), ASSETS)
    spawn = "\n".join(_body(script, "zmf_boss_b_spawn"))
    # The red paths are registered under the boss's own names before it spawns.
    for name, path in BOSS_RED_FX.items():
        assert f'level._effect[ "{name}" ] = "{path}";' in spawn
    assert spawn.index("zmf_boss_aura") < spawn.index("spawn_zombie")
    setup = _body(script, "zmf_boss_b_setup")
    for tag in BOSS_GLOW_TAGS:
        assert f'PlayFXOnTag( level._effect[ "zmf_boss_aura" ], self, "{tag}" );' in setup
    assert {"j_head", "j_spine4"} <= {t.lower() for t in BOSS_GLOW_TAGS}
    assert any('PlayFX( level._effect[ "zmf_boss_burst" ]' in line for line in setup)


def test_the_boss_wears_its_prop_and_declares_the_model() -> None:
    prop = BossProp("zmf_prop_jack_o_lantern", offset=(4.0, 0.0, 54.0),
                    angles=(0.0, 90.0, 0.0), scale=1.6)
    script = boss_script(_boss(props=(prop,)), ASSETS)
    setup = "\n".join(_body(script, "zmf_boss_b_setup"))
    assert 'e_prop SetModel( "zmf_prop_jack_o_lantern" );' in setup
    assert "e_prop SetScale( 1.6 );" in setup
    # tag "auto": the nearest spine/head/back/hand bone at rest, never the feet
    assert prop.bone == "j_spine4"
    assert 'e_prop LinkTo( self, "j_spine4", ' in setup and '"tag_origin"' not in setup
    assert setup.index("e_prop NotSolid();") < setup.index("e_prop LinkTo(")
    # after the stock init, so the model goes on a zombie that exists
    assert setup.index("zombie_init_done") < setup.index("SetModel")
    assert ("xmodel", "zmf_prop_jack_o_lantern") in script.assets
    death = "\n".join(_body(script, "zmf_boss_b_death"))
    assert "self.zmf_boss_props[ i ] delete();" in death


def test_the_marker_floats_over_the_boss_and_goes_on_death() -> None:
    script = boss_script(_boss(), ASSETS)
    setup = "\n".join(_body(script, "zmf_boss_b_setup"))
    assert "self.zmf_boss_marker = NewHudElem();" in setup
    assert f'setShader( "{BOSS_MARKER}", 12, 12 );' in setup
    assert "self.zmf_boss_marker SetTargetEnt( self );" in setup
    death = _body(script, "zmf_boss_b_death")
    assert death[0].startswith('self waittill( "death"')
    destroy = death.index("\tself.zmf_boss_marker Destroy();")
    notify = next(i for i, line in enumerate(death) if "level notify" in line)
    assert destroy < notify
    plain = boss_script(_boss(marker=False), ASSETS)
    assert "NewHudElem" not in "\n".join(_body(plain, "zmf_boss_b_setup"))


def test_the_three_map_bosses_each_wear_a_declared_model() -> None:
    import json
    from pathlib import Path

    from zmforge.recipes import cemetery_quest, corn_maze_script, dmv_quest

    ledger = json.loads((Path(__file__).parent.parent / "src/zmforge/blueprint/"
                         "installed_assets.json").read_text())
    declared = set(ledger["xmodels_declared"])
    sources = {
        "dmv": Path(dmv_quest.__file__).read_text(),
        "corn": Path(corn_maze_script.__file__).read_text(),
        "cemetery": Path(cemetery_quest.__file__).read_text(),
    }
    for where, text in sources.items():
        assert "props=(" in text and "BossProp(" in text, where
    for where, text in sources.items():
        # a themed outfit: at least two props each (P14)
        assert text.count("BossProp(") >= 2, where
        for model in re.findall(r'BossProp\(\s*"([a-z0-9_]+)"', text):
            assert model in declared, (where, model)


def test_a_bad_prop_is_refused() -> None:
    with pytest.raises(ValueError):
        BossProp("not a model")
    with pytest.raises(ValueError):
        BossProp("zmf_prop_pumpkin", scale=9.0)


def test_the_red_effects_are_precached_by_the_map() -> None:
    from types import SimpleNamespace

    from zmforge.script.bosses import boss_fx_paths, precache_boss_fx

    bp = SimpleNamespace(script=SimpleNamespace(precache_fx=[]))
    precache_boss_fx(bp, _boss())
    precache_boss_fx(bp, _boss())
    assert bp.script.precache_fx == list(boss_fx_paths(_boss()))  # once each
    assert set(bp.script.precache_fx) == set(BOSS_OWN_FX.values())
    assert boss_fx_paths(_boss(glow_fx="powerup_on", pulse_fx=None, fire_fx=None, arrive_fx=None)) == ()


def test_the_boss_burns_for_its_whole_life_and_arrives_with_lightning() -> None:
    script = boss_script(_boss(), ASSETS)
    spawn = "\n".join(_body(script, "zmf_boss_b_spawn"))
    for name, path in BOSS_LOUD_FX.items():
        assert f'level._effect[ "{name}" ] = "{path}";' in spawn
    assert 'PlayFX( level._effect[ "zmf_boss_arrive" ],' in spawn
    setup = _body(script, "zmf_boss_b_setup")
    for tag in BOSS_GLOW_TAGS:
        assert f'PlayFXOnTag( level._effect[ "zmf_boss_fire" ], self, "{tag}" );' in setup
    # the burst repeats every second while it lives, not every two
    loop = setup[setup.index("while ( isalive( self ) )"):]
    assert "\twait 1;" in loop


def test_spawn_snap_lands_the_boss_and_its_minions_on_the_navmesh() -> None:
    """A boss that climbs off a prop (Harvest Moon's scarecrow) is snapped to
    the nearest navmesh point; without spawn_snap the spawn is as before."""
    plain = "\n".join(_body(boss_script(_boss(minions=2), ASSETS), "zmf_boss_b_spawn"))
    assert "GetClosestPointOnNavMesh" not in plain
    assert "v_at = ( 0, 0, 0 );" in plain and "s_at.origin = v_at;" in plain
    assert 'level notify( "zmf_boss_b_spawned" );' in plain
    script = boss_script(_boss(minions=2, spawn_snap=128.0), ASSETS)
    spawn = "\n".join(_body(script, "zmf_boss_b_spawn"))
    assert (spawn.index("v_nav = GetClosestPointOnNavMesh( v_at, 128 );")
            < spawn.index("s_at.origin = v_at;") < spawn.index("spawn_zombie("))
    assert "Earthquake( 0.35, 2, v_at, 1500 );" in spawn
    minions = "\n".join(_body(script, "zmf_boss_b_minions"))
    assert (minions.index("GetClosestPointOnNavMesh( v_spot, 128 )")
            < minions.index("s_spot.origin = v_spot;") < minions.index("spawn_zombie("))
    assert lookup("GetClosestPointOnNavMesh") is None  # an engine builtin, not a script function


# -- Only a player may kill a boss ---------------------------------------------

def test_only_a_player_can_kill_the_boss() -> None:
    """A boss can die with no attacker: the stock stuck failsafe
    (round_spawn_failsafe) kills any zombie that moved under 24 units in 30 s,
    with no attacker.  Every boss keeps it off and drops non-player kills."""
    script = boss_script(_boss(), ASSETS)
    spawn = _body(script, "zmf_boss_b_spawn")
    register = "\tzm::register_zombie_damage_override_callback( &zmf_boss_b_guard_damage );"
    made = 'ai = zombie_utility::spawn_zombie( e_spawner, "zmf_boss_b", s_at );'
    assert spawn.index(register) < spawn.index(made)
    assert spawn.index(made) < spawn.index("ai.zmf_boss_guard = true;")
    assert "ai.ignore_round_spawn_failsafe = true;" in spawn
    assert "self thread zmf_boss_b_guard();" in _body(script, "zmf_boss_b_setup")
    guard = "\n".join(_body(script, "zmf_boss_b_guard"))
    assert 'self endon( "death" );' in guard
    # refreshed well inside the failsafe's 8 s window (zombie_utility.gsc:1850-1854)
    assert "self.lastchunk_destroy_time = gettime();" in guard and "wait 1;" in guard
    assert 'level.zombie_vars[ "below_world_check" ]' in guard
    assert "self forceteleport( ( 0, 0, 0 )" in guard
    damage = next(f for f in script.functions if f.name == "zmf_boss_b_guard_damage")
    assert len(damage.params) == 13 and damage.params[:3] == ("willbekilled", "inflictor", "attacker")
    body = "\n".join(damage.body)
    assert "isplayer( attacker )" in body and "isplayer( attacker.owner )" in body
    assert "self.dont_die_on_me = ( willbekilled && !b_player );" in body
    assert r"scripts\zm\_zm" in script.using
    entry = lookup("zm::register_zombie_damage_override_callback")
    assert entry is not None and "dont_die_on_me" in entry.evidence


def test_a_prop_on_a_bone_is_placed_at_rest_and_linked_in_the_bone_frame() -> None:
    from zmforge.script.bosses import BOSS_BIND_POSE, _axes
    prop = BossProp("zmf_prop_jack_o_lantern", offset=(1.0, 0.0, 59.0),
                    angles=(0.0, 90.0, 0.0), scale=1.9, tag="j_head")
    (ox, oy, oz), angles = prop.link()
    at, axes = BOSS_BIND_POSE["j_head"]
    # Back in the boss frame, the linked offset lands on the rest placement...
    rest = [at[k] + ox * axes[0][k] + oy * axes[1][k] + oz * axes[2][k] for k in range(3)]
    assert rest == pytest.approx(prop.offset, abs=0.1)
    # ...and the prop's axes on the rest facing.
    world = [[sum(r[i] * axes[i][k] for i in range(3)) for k in range(3)] for r in _axes(angles)]
    assert world == [pytest.approx(list(v), abs=0.02) for v in _axes(prop.angles)]
    setup = "\n".join(_body(boss_script(_boss(props=(prop,)), ASSETS), "zmf_boss_b_setup"))
    assert 'e_prop LinkTo( self, "j_head", ' in setup
    with pytest.raises(ValueError):
        BossProp("zmf_prop_jack_o_lantern", tag="j_nope")


def test_headless_takes_the_head_off_the_stock_way_and_is_off_by_default() -> None:
    plain = "\n".join(_body(boss_script(_boss(), ASSETS), "zmf_boss_b_setup"))
    assert "Detach" not in plain and "no_gib" not in plain
    setup = "\n".join(_body(boss_script(_boss(headless=True), ASSETS), "zmf_boss_b_setup"))
    assert "self.no_gib = true;" in setup
    assert "self zombie_utility::zombie_eye_glow_stop();" in setup
    assert 'self Detach( self.head, "" );' in setup
    assert setup.index("zombie_init_done") < setup.index("Detach")


# -- The boss, its minions and its model arrive where they are put --

def test_the_boss_and_its_minions_arrive_where_they_are_put_and_never_rise_elsewhere() -> None:
    """A forceteleport right after spawn_zombie is undone by the stock spawn
    code (do_zombie_spawn after waittillframeend picks a random riser), so
    the arena goes in as spawn_zombie's spawn_point: a walk-in
    "spawn_location" that hunts at once ("find_flesh")."""
    from zmforge.script.symbols import lookup as _lookup
    script = boss_script(_boss(minions=3, spawn_snap=64.0), ASSETS)
    for name, var in (("zmf_boss_b_spawn", "s_at"), ("zmf_boss_b_minions", "s_spot")):
        body = "\n".join(_body(script, name))
        assert "forceteleport" not in body, name
        assert f'{var}.script_noteworthy = "spawn_location";' in body
        assert f'{var}.script_string = "find_flesh";' in body
        assert re.search(rf"spawn_zombie\( e_spawner, \"[a-z_]+\", {var} \)", body), name
    assert _lookup("zombie_utility::spawn_zombie") is not None


def test_the_guard_teleports_only_a_boss_that_fell_out_of_the_world() -> None:
    """The guard must never fight the AI: its one teleport sits under the
    below-world test, and nothing else in the boss script teleports, sets a
    goal or path mode, or loops faster than once a second."""
    boss = _boss(minions=2, armour=0.5, hurt_speed="sprint")
    script = boss_script(boss, _assets(boss))
    guard = _body(script, "zmf_boss_b_guard")
    tp = [i for i, line in enumerate(guard) if "forceteleport" in line]
    assert len(tp) == 1
    assert "below_world_check" in guard[tp[0] - 2]
    for f in script.functions:
        text = "\n".join(f.body)
        if f.name != "zmf_boss_b_guard":
            assert "forceteleport" not in text, f.name
        for call in ("SetGoal", "PathMode", "SetGoalPos", "SetGoalEntity"):
            assert call not in text, (f.name, call)
        for w in re.findall(r"\bwait ([0-9.]+);", text):
            assert float(w) >= 0.05, (f.name, w)
    for loop in ("zmf_boss_b_guard", "zmf_boss_b_speed"):
        assert "\twait 1;" in _body(script, loop)


def _assets(boss: Boss) -> dict[str, str]:
    from zmforge.script.bosses import boss_strings
    return {ref: ref for ref in boss_strings(boss)}


def _recipe_props() -> list[tuple[str, BossProp]]:
    """Every ``BossProp(...)`` written in any recipe, evaluated in its own
    module (so a new map's boss is checked without a line here)."""
    import ast
    import importlib
    import pkgutil
    from pathlib import Path

    import zmforge.recipes as recipes
    out = []
    for info in pkgutil.walk_packages(recipes.__path__, recipes.__name__ + "."):
        mod = importlib.import_module(info.name)
        src = getattr(mod, "__file__", None)
        if not src or "BossProp(" not in Path(src).read_text():
            continue
        for node in ast.walk(ast.parse(Path(src).read_text())):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("BossProp"):
                out.append((info.name, eval(ast.unparse(node), vars(mod))))
    return out


def test_every_boss_prop_is_a_declared_linkable_model_in_the_zone() -> None:
    """Every worn model, in every recipe, goes in the zone and is declared on
    the install and linkable (or one of ours).  Its materials are the
    linker's to resolve: the boss test map's link log has no missing
    image or material."""
    import json
    from pathlib import Path

    ledger = json.loads((Path(__file__).parent.parent / "src/zmforge/blueprint/"
                         "installed_assets.json").read_text())
    declared = set(ledger["xmodels_declared"]) | set(ledger.get("xmodels_local", ()))
    unlinkable = set(ledger["xmodels_unlinkable"])
    props = _recipe_props()
    where = {w.rsplit(".", 1)[1] for w, _ in props}
    assert {"corn_maze_script", "cemetery_quest", "dmv_quest"} <= where
    for w, prop in props:
        script = boss_script(_boss(props=(prop,)), ASSETS)
        assert ("xmodel", prop.model) in script.assets, (w, prop.model)
        if prop.model.startswith("zmf_"):
            continue
        assert prop.model in declared and prop.model not in unlinkable, (w, prop.model)


def test_a_flat_boss_prop_faces_out_from_the_body() -> None:
    """The Scarecrow's caution sign showed its grey metal back (yaw 270 put
    its face, local -y per props._mount_face, into the chest).  A thin
    prop off the spine must face away from it."""
    import math

    from zmforge.recipes.props import MODEL_BOX, _mount_face
    checked = 0
    for w, prop in _recipe_props():
        if True:
            box = MODEL_BOX.get(prop.model)
            if box is None or abs(prop.angles[0]) > 1 or abs(prop.angles[2]) > 1:
                continue
            (x0, y0, z0), (x1, y1, z1) = box
            thin = min(x1 - x0, y1 - y0)
            if thin > 0.2 * max(x1 - x0, y1 - y0, z1 - z0):
                continue
            out = math.hypot(prop.offset[0], prop.offset[1])
            if out < 4.0:
                continue
            face = math.radians(_mount_face(prop.model) + prop.angles[1])
            dot = (math.cos(face) * prop.offset[0] + math.sin(face) * prop.offset[1]) / out
            assert dot > 0.5, (w, prop.model, prop.angles)
            checked += 1
    # Every qualifying prop in every recipe present is checked above; how many
    # there are depends on which recipes are present, so only require that the
    # check saw at least one.
    assert checked >= 1, "no flat off-spine boss prop found in any recipe"
