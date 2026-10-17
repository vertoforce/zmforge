"""The custom-script seam and the GSC checker that guards it.

A script error in this game is fatal at run time, so every check here has a
negative test: a checker that has never fired is not evidence it works.
"""

from __future__ import annotations

import pytest

from zmforge.script import CustomFunction, CustomScript, Slot, merge, scan
from zmforge.script.symbols import STOCK_FUNCTIONS, lookup, unresolved


# --------------------------------------------------------------------------
# The checker over text
# --------------------------------------------------------------------------
def codes(issues):
    return sorted({issue.code for issue in issues})


def test_a_sound_script_raises_nothing():
    text = (
        "#using scripts\\shared\\flag_shared;\n"
        "\n"
        "function main()\n"
        "{\n"
        "\tlevel.x = 1;\n"
        '\tflag::init( "a" );\n'
        "\tlevel thread helper();\n"
        "}\n"
        "\n"
        "function helper()\n"
        "{\n"
        "\twait 1;\n"
        "}\n"
    )
    source = scan(text)
    assert source.issues == []
    assert unresolved(source) == []


def test_a_missing_semicolon_is_caught():
    text = "function main()\n{\n\tlevel.x = 1\n}\n"
    assert codes(scan(text).issues) == ["gsc_semicolon"]


def test_an_unclosed_brace_is_caught():
    text = "function main()\n{\n\tlevel.x = 1;\n"
    assert codes(scan(text).issues) == ["gsc_bracket"]


def test_a_mismatched_bracket_is_caught():
    text = "function main()\n{\n\tlevel.x = foo[0);\n}\n"
    assert "gsc_bracket" in codes(scan(text).issues)


def test_an_unterminated_string_is_caught():
    text = 'function main()\n{\n\tlevel.x = "open;\n}\n'
    assert "gsc_string" in codes(scan(text).issues)


def test_a_statement_outside_a_function_is_caught():
    text = "level.x = 1;\nfunction main()\n{\n\twait 1;\n}\n"
    assert "gsc_toplevel" in codes(scan(text).issues)


def test_two_functions_of_one_name_are_caught():
    text = (
        "function main()\n{\n\twait 1;\n}\n"
        "function main()\n{\n\twait 2;\n}\n"
    )
    assert "gsc_duplicate" in codes(scan(text).issues)


def test_braces_inside_strings_and_comments_do_not_count():
    text = (
        "function main()\n"
        "{\n"
        '\tlevel.x = "a{b";  // trailing } brace\n'
        "\t/* a block }\n"
        "\t   comment { */\n"
        "\twait 1;\n"
        "}\n"
    )
    assert scan(text).issues == []


# --------------------------------------------------------------------------
# The checker over references
# --------------------------------------------------------------------------
def test_a_call_to_nothing_is_caught():
    text = "function main()\n{\n\tlevel thread ghost();\n}\n"
    assert codes(unresolved(scan(text))) == ["gsc_undefined"]


def test_a_pointer_to_nothing_is_caught():
    text = "function main()\n{\n\tlevel.f = &ghost;\n}\n"
    assert codes(unresolved(scan(text))) == ["gsc_undefined"]


def test_an_unknown_namespaced_call_is_caught():
    text = "function main()\n{\n\tzm_nonsense::do_it();\n}\n"
    assert codes(unresolved(scan(text))) == ["gsc_unknown_symbol"]


def test_a_known_call_without_its_using_is_caught():
    text = 'function main()\n{\n\tflag::init( "a" );\n}\n'
    assert codes(unresolved(scan(text))) == ["gsc_missing_using"]


def test_a_namespace_a_caller_has_read_can_be_allowed_through():
    text = "function main()\n{\n\tzm_nonsense::do_it();\n}\n"
    assert unresolved(scan(text), known_namespaces={"zm_nonsense"}) == []


def test_every_symbol_table_entry_carries_its_evidence():
    for function in STOCK_FUNCTIONS:
        assert function.evidence.strip(), f"{function.call} has no evidence"
        assert lookup(function.call) is function


# --------------------------------------------------------------------------
# The seam
# --------------------------------------------------------------------------
def test_a_function_name_must_be_a_gsc_identifier():
    with pytest.raises(ValueError):
        CustomFunction("2bad", ("wait 1;",))


def test_an_empty_body_is_refused():
    with pytest.raises(ValueError):
        CustomFunction("empty", ())


def test_two_custom_functions_of_one_name_are_refused():
    with pytest.raises(ValueError):
        CustomScript(
            functions=(
                CustomFunction("same", ("wait 1;",)),
                CustomFunction("same", ("wait 2;",)),
            )
        )


def test_merge_dedupes_using_and_keeps_order():
    a = CustomScript(
        using=("scripts\\zm\\_zm_score",),
        functions=(CustomFunction("a", ("wait 1;",)),),
        statements=((Slot.AFTER_ENTRY, "level thread a();"),),
    )
    b = CustomScript(
        using=("scripts\\zm\\_zm_score", "scripts\\zm\\_zm_weapons"),
        functions=(CustomFunction("b", ("wait 2;",)),),
        statements=((Slot.AFTER_ENTRY, "level thread b();"),),
    )
    both = merge(a, b)
    assert both.using == ("scripts\\zm\\_zm_score", "scripts\\zm\\_zm_weapons")
    assert [f.name for f in both.functions] == ["a", "b"]
    assert both.in_slot(Slot.AFTER_ENTRY) == ("level thread a();", "level thread b();")


def test_there_is_no_slot_between_the_dog_setting_and_the_framework_entry():
    """Spec 4.12: that ordering is load-bearing, so no slot may split it."""
    assert {slot.value for slot in Slot} == {
        "before_entry",
        "after_entry",
        "zone_hook",
        "client_init",
    }


# --------------------------------------------------------------------------
# The seam, through the emitter
# --------------------------------------------------------------------------
from zmforge.blueprint.script_plan import ScriptPlan  # noqa: E402
from zmforge.emit.scripts import render_client_script, render_server_script  # noqa: E402
from zmforge.verify import check_script_soundness, check_server_script  # noqa: E402


def _plan(custom: CustomScript) -> ScriptPlan:
    return ScriptPlan(map_name="zm_x", zones=["start_zone"], custom=custom)


def a_demo_script() -> CustomScript:
    return CustomScript(
        using=("scripts\\shared\\flag_shared",),
        functions=(
            CustomFunction(
                "watch_something",
                ('level endon( "end_game" );', "wait 1;"),
                purpose="a demo",
            ),
        ),
        statements=(
            (Slot.AFTER_ENTRY, "level thread watch_something();"),
            (Slot.ZONE_HOOK, "level.demo = 1;"),
        ),
    )


def test_custom_logic_reaches_the_emitted_script():
    text = render_server_script(_plan(a_demo_script()))
    assert "function watch_something()" in text
    assert "\tlevel thread watch_something();" in text
    assert "\tlevel.demo = 1;" in text
    assert "// a demo" in text


def test_the_framework_ordering_survives_custom_logic():
    """Z10: nothing a caller supplies may split the dog setting from the entry."""
    text = render_server_script(_plan(a_demo_script()))
    lines = text.splitlines()
    dog = next(i for i, l in enumerate(lines) if "dog_rounds_allowed" in l)
    entry = next(i for i, l in enumerate(lines) if "zm_usermap::main()" in l)
    assert entry == dog + 1
    assert not check_server_script(text).errors


def test_an_emitted_script_with_custom_logic_passes_the_checker():
    text = render_server_script(_plan(a_demo_script()))
    assert not check_script_soundness(text, label="zm_x.gsc").errors


def test_custom_logic_calling_nothing_is_caught_before_a_build():
    bad = CustomScript(
        statements=((Slot.AFTER_ENTRY, "level thread never_defined();"),)
    )
    report = check_script_soundness(render_server_script(_plan(bad)), label="zm_x.gsc")
    assert [f.code for f in report.errors] == ["Z16"]


def test_custom_logic_with_a_missing_terminator_is_caught_before_a_build():
    bad = CustomScript(
        functions=(CustomFunction("broken", ("level.x = 1",)),),
        statements=((Slot.AFTER_ENTRY, "level thread broken();"),),
    )
    report = check_script_soundness(render_server_script(_plan(bad)), label="zm_x.gsc")
    assert [f.code for f in report.errors] == ["Z15"]


def test_a_dev_only_call_outside_a_devblock_is_caught_before_a_build():
    # Two bare PrintLn calls kill a map at load with "Dev only calls must be
    # wrapped in a devblock /#...#/".
    bad = CustomScript(
        functions=(CustomFunction("noisy", (
            'PrintLn( "x" );',
            "self Print3d( self.origin, \"x\" );",
            "/# PrintLn( \"fine\" ); #/",
            "// Line( a, b );",
            'IPrintLn( "fine" );',
        )),),
        statements=((Slot.AFTER_ENTRY, "level thread noisy();"),),
    )
    report = check_script_soundness(render_server_script(_plan(bad)), label="zm_x.gsc")
    z90 = [f.message for f in report.errors if f.code == "Z90"]
    assert len(z90) == 2, z90
    assert "PrintLn()" in z90[0] and "Print3d()" in z90[1]
    assert "Z15" not in {f.code for f in report.errors}  # the devblock line still parses


def test_dev_only_calls_ignore_devblocks_and_the_scripts_own_functions():
    from zmforge.script.gsc import dev_only_calls

    text = "\n".join((
        "function line( a ) { return a; }",
        "function f()",
        "{",
        "\tline( 1 );",
        "\t/#",
        "\tSphere( o, 8 );",
        "\t#/",
        "\tRecordPlayerStats( p, \"x\", 1 );",
        "\tAssert( 1 );",
        "\tRecordLine( a, b );",
        "}",
    ))
    assert dev_only_calls(text) == [(10, "RecordLine")]


def test_client_custom_logic_reaches_the_client_script():
    custom = CustomScript(
        functions=(
            CustomFunction(
                "client_thing", ("wait 1;",), client_side=True
            ),
        ),
        statements=((Slot.CLIENT_INIT, "level.client_demo = 1;"),),
    )
    text = render_client_script(_plan(custom))
    assert "function client_thing()" in text
    assert "\tlevel.client_demo = 1;" in text
    assert not check_script_soundness(text, label="zm_x.csc").errors


# --------------------------------------------------------------------------
# The mechanics library
# --------------------------------------------------------------------------
from zmforge.script import tricks  # noqa: E402


ALL_TRICKS = {
    "mega_blast": tricks.mega_blast_on_fire("shotgun_pump"),
    "mega_blast_radius": tricks.mega_blast_on_fire(cone_degrees=360.0),
    "perk_refuses": tricks.perk_pranks(refuse=["deadshot"]),
    "perk_takes_money": tricks.perk_pranks(takes_money=["juggernog"]),
    "rigged_box": tricks.rigged_mystery_box(origin=(100.0, 200.0, 32.0)),
    "rigged_box_everywhere": tricks.rigged_mystery_box(),
    "spawn_spike": tricks.spawn_spike_on_flag("vault_door"),
    "teleporter": tricks.short_hop_teleporter((512, 0, 32), (572, 0, 32)),
}


@pytest.mark.parametrize("name", sorted(ALL_TRICKS))
def test_each_trick_emits_a_sound_script(name):
    """A GSC error is fatal in game, so every mechanic is checked as text."""
    text = render_server_script(_plan(ALL_TRICKS[name]))
    assert not check_script_soundness(text, label="zm_x.gsc").errors


@pytest.mark.parametrize("name", sorted(ALL_TRICKS))
def test_no_trick_breaks_the_framework_ordering(name):
    text = render_server_script(_plan(ALL_TRICKS[name]))
    assert not check_server_script(text).errors


#: One of each mechanic, which is what a map would actually ask for.
COMBINED = merge(
    *(
        trick
        for name, trick in sorted(ALL_TRICKS.items())
        if name not in ("rigged_box_everywhere", "mega_blast_radius")
    )
)


def test_every_trick_together_is_still_a_sound_script():
    text = render_server_script(_plan(COMBINED))
    assert not check_script_soundness(text, label="zm_x.gsc").errors
    assert not check_server_script(text).errors


def test_the_logical_and_operator_is_not_read_as_a_function_pointer():
    """Regression: `a && b` made the checker report a pointer to `b`."""
    text = (
        "function main()\n"
        "{\n"
        "\tif ( isdefined( self.num_perks ) && self.num_perks > 0 )\n"
        "\t{\n"
        "\t\tself.num_perks--;\n"
        "\t}\n"
        "}\n"
    )
    assert unresolved(scan(text)) == []


def test_a_trick_only_calls_stock_functions_the_table_knows():
    """Z16 over every mechanic at once: nothing invented, nothing unimported."""
    text = render_server_script(_plan(COMBINED))
    assert [f.code for f in check_script_soundness(text, label="x").errors] == []


def test_every_map_has_no_perk_limit_set_after_the_framework_entry():
    """No perk limit on any map.  zm_perks::init assigns
    level.perk_purchase_limit = 4 (_zm_perks.gsc:43) inside zm_usermap::main,
    so the override comes after that call, on a map with no custom logic."""
    from zmforge.emit.scripts import NO_PERK_LIMIT
    from zmforge.verify.gameplay import check_perk_limit

    text = render_server_script(_plan(CustomScript()))
    entry = text.index("zm_usermap::main();")
    assert text.index(f"level.perk_purchase_limit = {NO_PERK_LIMIT};") > entry
    assert text.index(
        "level.get_player_perk_purchase_limit = &zmf_perk_purchase_limit;") > entry
    hook = text[text.index("function zmf_perk_purchase_limit()"):]
    assert f"return {NO_PERK_LIMIT};" in hook[: hook.index("\n}\n")]
    assert list(check_perk_limit(text)) == []
    assert [f.code for f in check_script_soundness(text, label="x").errors] == []


def test_z80_fails_a_script_that_keeps_the_stock_perk_limit():
    from zmforge.verify.gameplay import check_perk_limit

    text = render_server_script(_plan(CustomScript()))
    missing = "\n".join(line for line in text.splitlines()
                        if "perk_purchase_limit =" not in line)
    assert {f.code for f in check_perk_limit(missing)} == {"Z82"}
    early = text.replace("\tlevel.perk_purchase_limit = 99;\n", "").replace(
        "\tzm_usermap::main();\n", "\tlevel.perk_purchase_limit = 99;\n\tzm_usermap::main();\n")
    assert [f.code for f in check_perk_limit(early)] == ["Z82"]
    capped = text.replace("return 99;", "return 4;")
    assert [f.code for f in check_perk_limit(capped)] == ["Z82"]
    reset = text.replace("function zmf_perk_purchase_limit()",
                         "function other()\n{\n\tlevel.perk_purchase_limit = 4;\n}\n"
                         "function zmf_perk_purchase_limit()")
    assert [f.code for f in check_perk_limit(reset)] == ["Z82"]


def test_the_rigged_box_falls_back_when_its_weapon_is_absent():
    """The forced weapon may not be in a usermap's box list; degrade, not die."""
    text = render_server_script(_plan(tricks.rigged_mystery_box()))
    assert "if ( a_out.size == 0 )" in text
    assert "return a_keys;" in text


def test_the_refusing_machine_is_selected_by_its_specialty_string():
    text = render_server_script(_plan(tricks.perk_pranks(refuse=["deadshot"])))
    assert 'self.script_noteworthy == "specialty_deadshot"' in text


def test_two_rigged_boxes_are_refused_rather_than_silently_merged():
    """The forcing hook is one level variable, so two boxes cannot both own it."""
    with pytest.raises(ValueError):
        merge(tricks.rigged_mystery_box(), tricks.rigged_mystery_box(origin=(0, 0, 0)))


# --------------------------------------------------------------------------
# End to end: a map with every mechanic on it
# --------------------------------------------------------------------------
from zmforge import Project  # noqa: E402
from zmforge import verify as verify_module  # noqa: E402
from zmforge.recipes import prank_map  # noqa: E402


def test_a_prank_map_commits_with_no_errors(tmp_path):
    """The whole path: recipe, blueprint, commit, then every file check."""
    project = Project.create(
        "zm_forge_prank", tmp_path, blueprint=prank_map("zm_forge_prank")
    )
    result = project.commit()
    assert not result.report.errors, [str(f) for f in result.report.errors]
    report = verify_module.files(project)
    assert not report.errors, [str(f) for f in report.errors]


def test_the_prank_map_keeps_the_round_loop_wiring(tmp_path):
    """Fair-play rule: the mechanics must not displace the map's own logic."""
    project = Project.create(
        "zm_forge_prank2", tmp_path, blueprint=prank_map("zm_forge_prank2")
    )
    project.commit()
    script = project.paths()["server_script"].read_text(encoding="utf-8")
    assert "zm_usermap::main();" in script
    assert "zm_zonemgr::manage_zones( init_zones );" in script
    assert "level.zone_manager_init_func = &connect_zones;" in script


def test_prank_logic_attaches_to_a_layout_it_did_not_build():
    """The map owns its geometry; the mechanics arrive in one call."""
    from zmforge.recipes import FIXTURE, PrankPlan, add_prank_logic, three_room_map
    from zmforge.spatial import Point

    blueprint = three_room_map("zm_x")
    add_prank_logic(blueprint, PrankPlan(), pad=Point(1000.0, 0.0, 16.0))
    text = render_server_script(blueprint.script)
    assert not check_script_soundness(text, label="zm_x.gsc").errors
    assert not check_server_script(text).errors
    # The spike goes on the door the player just paid the most for.
    assert str(FIXTURE.vault_door_price) not in text  # the price is not in the script
    assert "zmf_spawn_spike" in text


def test_the_spawn_spike_picks_the_most_expensive_door():
    from zmforge.blueprint.elements import Door
    from zmforge.recipes import PrankPlan, add_prank_logic, three_room_map

    blueprint = three_room_map("zm_x")
    dearest = max(blueprint.elements(Door), key=lambda d: d.price)
    add_prank_logic(blueprint, PrankPlan())
    text = render_server_script(blueprint.script)
    assert f'level flag::wait_till( "{dearest.flag}" );' in text


def test_prank_logic_skips_what_a_layout_does_not_have():
    """A map with no box gets no rigged box rather than a call into nothing."""
    from zmforge.recipes import PrankPlan, add_prank_logic, one_room_map

    blueprint = one_room_map("zm_x")
    add_prank_logic(blueprint, PrankPlan())
    text = render_server_script(blueprint.script)
    assert "zmf_box_weights" not in text
    assert not check_script_soundness(text, label="zm_x.gsc").errors


# --------------------------------------------------------------------------
# The mega blast
# --------------------------------------------------------------------------
def _blast(**kwargs) -> str:
    return render_server_script(_plan(tricks.mega_blast_on_fire(**kwargs)))


def test_the_blast_kills_zombies_before_it_downs_the_shooter():
    text = _blast()
    kill = text.index("a_zombies[ i ] dodamage( a_zombies[ i ].health + 666")
    down = text.index("self dodamage( self.health + 100")
    assert kill < down


def test_the_blast_tests_a_cone_by_default():
    text = _blast()
    assert "anglestoforward( self getplayerangles() )" in text
    assert "vectordot( v_to, v_forward )" in text


def test_a_full_circle_blast_drops_the_cone_test():
    text = _blast(cone_degrees=360.0)
    assert "vectordot( v_to, v_forward )" not in text
    assert "anglestoforward" not in text
    assert "distancesquared( v_from, a_zombies[ i ].origin )" in text


def test_the_cone_threshold_is_the_cosine_of_the_half_angle():
    assert "< 0.5 )" in _blast(cone_degrees=120.0)  # cos 60 degrees
    assert "< 0.707107 )" in _blast(cone_degrees=90.0)  # cos 45 degrees


def test_the_blast_skips_protected_ai_as_the_nuke_does():
    text = _blast()
    assert "zm_utility::is_magic_bullet_shield_enabled( a_zombies[ i ] )" in text
    assert "marked_for_death" in text


def test_the_blast_uses_no_unregistered_client_field_or_effect():
    """Both are fatal in a usermap: the nuke registers them, a usermap does not."""
    text = _blast()
    assert "zm_nuked" not in text
    assert "playfx" not in text
    assert "level._effect" not in text


def test_a_blast_with_no_range_is_refused():
    with pytest.raises(ValueError):
        tricks.mega_blast_on_fire(range_units=0.0)


# --------------------------------------------------------------------------
# The cupboard full of zombies
# --------------------------------------------------------------------------
def _ambush(**kwargs) -> str:
    return render_server_script(
        _plan(tricks.closet_ambush("enter_closet", (120.0, 240.0, 16.0), **kwargs))
    )


def test_the_ambush_waits_for_its_own_door_and_spawns_a_fixed_number():
    text = _ambush(count=10)
    assert 'level flag::wait_till( "enter_closet" );' in text
    assert "for ( i = 0; i < 10; i++ )" in text
    assert "a_spots[ 9 ] = (" in text
    assert "a_spots[ 10 ] = (" not in text


def test_the_ambush_forces_the_spawner_before_it_asks_for_a_zombie():
    """spawn_zombie returns undefined without it, and the gag dies silently."""
    text = _ambush()
    assert text.index("e_spawner.script_forcespawn = 1;") < text.index(
        "zombie_utility::spawn_zombie( e_spawner"
    )


def test_the_ambush_survives_a_map_with_no_spawners():
    text = _ambush()
    assert (
        "if ( !isdefined( level.zombie_spawners ) || level.zombie_spawners.size < 1 )"
        in text
    )


def test_the_ambush_forces_sprint_the_stock_way():
    text = _ambush()
    assert 'self zombie_utility::set_zombie_run_cycle( "sprint" );' in text
    assert "self.zombie_move_speed_original = self.zombie_move_speed;" in text


def test_a_walking_ambush_defines_no_sprint_thread():
    text = _ambush(sprint=False)
    assert "zmf_closet_sprint" not in text


def test_an_empty_ambush_is_refused():
    with pytest.raises(ValueError):
        tricks.closet_ambush("f", (0, 0, 0), count=0)


def test_the_ambush_script_is_sound_and_keeps_the_ordering():
    text = _ambush()
    assert not check_script_soundness(text, label="zm_x.gsc").errors
    assert not check_server_script(text).errors


def test_naming_an_ambush_door_without_a_closet_is_an_error():
    from zmforge.recipes import PrankPlan, add_prank_logic, three_room_map

    with pytest.raises(ValueError):
        add_prank_logic(
            three_room_map("zm_x"), PrankPlan(), ambush_door="door_arena_vault"
        )


# --------------------------------------------------------------------------
# Declaring assets in the manifest
# --------------------------------------------------------------------------
def test_a_mechanic_can_declare_the_asset_it_needs():
    from zmforge.blueprint import Blueprint

    blueprint = Blueprint("zm_x")
    blueprint.add_custom_logic(CustomScript(assets=(("sound", "zm_x"),)))
    assert [ref.line for ref in blueprint.assets] == ["sound,zm_x"]


def test_an_invented_asset_prefix_is_refused():
    from zmforge.emit.manifest import AssetRef

    with pytest.raises(ValueError):
        AssetRef("shellshock", "explosion")


def test_an_asset_name_with_a_comma_is_refused():
    from zmforge.emit.manifest import AssetRef

    with pytest.raises(ValueError):
        AssetRef("sound", "one,two")


def test_declarations_reach_the_manifest_once_each():
    from zmforge.emit.manifest import AssetRef, render_manifest

    text = render_manifest(
        "zm_x", assets=[AssetRef("sound", "zm_x"), AssetRef("sound", "zm_x")]
    )
    assert text.count("sound,zm_x") == 1


def test_a_manifest_line_with_an_unknown_type_is_caught():
    from zmforge.verify import check_manifest

    required = (
        ">class,zm_mod_level\n>group,modtools\n"
        "col_map,maps/zm/zm_x.d3dbsp\ngfx_map,maps/zm/zm_x.d3dbsp\n"
        "scriptparsetree,scripts/zm/zm_x.gsc\nscriptparsetree,scripts/zm/zm_x.csc\n"
    )
    report = check_manifest(required + "shellshock,explosion\n", "zm_x")
    assert [f.code for f in report.errors] == ["Z17"]


# --------------------------------------------------------------------------
# The shooter's hearing
# --------------------------------------------------------------------------
def test_the_blast_deafens_the_shooter_with_the_stock_concussion_call():
    text = _blast()
    assert 'self shellshock( "explosion", 6, 0 );' in text


def test_the_hearing_goes_before_the_kills_and_before_the_fall():
    text = _blast()
    shock = text.index('self shellshock( "explosion"')
    kill = text.index("a_zombies[ i ] dodamage(")
    down = text.index("self dodamage( self.health + 100")
    assert shock < kill < down


def test_the_flash_and_the_deafen_land_on_the_shooter_only():
    """A trick gun's flash must land only on its shooter, not every player in the game.

    ``shellshock`` was never the broadcast -- it was always on ``self``.  The
    white flash was: ``lui::screen_flash`` called on ``level`` re-threads
    itself on every player in ``level.players``
    (``shared/lui_shared.gsc:434-439``, header ``"CallOn: player or level
    (for all players)"``), so one shooter blinded the lobby.  Both halves are
    now on the shooter.
    """
    text = _blast()
    assert 'self thread lui::screen_flash( 0.1, 0.4, 0.6, 0.8, "white" );' in text
    assert "level thread lui::screen_flash" not in text
    assert 'self shellshock( "explosion", 6, 0 );' in text
    # Nothing in the blast reaches for the other players.
    blast = text[text.index("function zmf_mega_blast()") :]
    blast = blast[: blast.index("\n}\n") + 2]
    for broadcast in ("getplayers(", "level.players", "level thread", "level notify"):
        assert broadcast not in blast, broadcast


def test_the_deafen_can_be_turned_off():
    assert "shellshock" not in _blast(deafen_asset=None)


def test_no_ringing_alias_is_invented():
    """Stock zombies wires up no ringing loop, so none is guessed."""
    text = _blast()
    assert "playloopsound" not in text


def test_a_supplied_ringing_alias_is_played_the_flashbang_way():
    text = _blast(ring_alias="zmf_ears_ringing", ring_seconds=5.0)
    assert 'e_snd = spawn( "script_origin", ( 0, 0, 1 ) );' in text
    assert "e_snd linkto( self );" in text
    assert 'e_snd playloopsound( "zmf_ears_ringing", 0.25 );' in text
    assert "e_snd stoploopsound( 0.5 );" in text
    assert "zmf_sound_follows" in text


def test_a_ringing_alias_can_declare_the_bank_that_carries_it():
    custom = tricks.mega_blast_on_fire(
        ring_alias="zmf_ears_ringing", ring_bank="zm_forge_prank"
    )
    assert custom.assets == (("sound", "zm_forge_prank"),)


def test_a_bank_with_nothing_played_from_it_is_refused():
    with pytest.raises(ValueError):
        tricks.mega_blast_on_fire(ring_bank="zm_forge_prank")


# --------------------------------------------------------------------------
# The seam against the scaffold it is woven into
# --------------------------------------------------------------------------
def test_a_using_the_scaffold_already_writes_is_written_once():
    """A caller naming a module the generated half already #usings.

    ``merge`` dedupes between mechanics; this is the same rule against the
    scaffold, on both scripts, including the usermap module that must stay
    last.
    """
    from collections import Counter

    custom = CustomScript(
        using=(
            "scripts\\shared\\flag_shared",  # in SHARED_MODULES
            "scripts\\zm\\_zm_utility",  # in ZOMBIE_MODULES
            "scripts\\zm\\zm_usermap",  # the last line of the scaffold
            "scripts\\zm\\_zm_perk_juggernaut",  # a placed perk's module
            "scripts\\shared\\laststand_shared",  # genuinely new
        ),
        client_using=("scripts\\shared\\util_shared", "scripts\\shared\\lui_shared"),
        functions=(CustomFunction("thing", ("wait 1;",)),),
        statements=((Slot.AFTER_ENTRY, "level thread thing();"),),
    )
    plan = _plan(custom)
    plan.perk_modules = ["scripts\\zm\\_zm_perk_juggernaut"]
    for text in (render_server_script(plan), render_client_script(plan)):
        usings = [line for line in text.splitlines() if line.startswith("#using")]
        repeated = [line for line, n in Counter(usings).items() if n > 1]
        assert repeated == [], repeated
        assert usings[-1] == "#using scripts\\zm\\zm_usermap;"
    server = render_server_script(plan)
    assert "#using scripts\\shared\\laststand_shared;" in server
    assert "#using scripts\\shared\\lui_shared;" in render_client_script(plan)


def test_both_scripts_carry_the_plans_perk_modules():
    """One list, two scripts, and the client one is not optional.

    Each perk ships a ``.csc`` beside its ``.gsc`` in the mod tools' raw
    scripts, and that half is what registers the perk's clientfields, HUD
    callbacks and machine effect (``_zm_perk_juggernaut.csc:20-30``).
    Treyarch's own map lists every perk module in both files
    (``zm_giant.gsc:30-38`` against ``zm_giant.csc:21-28``).  The in-game
    effect of the client half missing is unverified.
    """
    plan = _plan(CustomScript())
    plan.perk_modules = [
        "scripts\\zm\\_zm_perk_juggernaut",
        "scripts\\zm\\_zm_pack_a_punch",
        "scripts\\zm\\_zm_perk_juggernaut",  # placed twice, written once
    ]
    server = render_server_script(plan)
    client = render_client_script(plan)
    for text in (server, client):
        for module in plan.module_set():
            assert text.count(f"#using {module};") == 1
    assert plan.module_set() == [
        "scripts\\zm\\_zm_perk_juggernaut",
        "scripts\\zm\\_zm_pack_a_punch",
    ]


def test_a_function_defined_inside_a_function_is_caught():
    """The braces balance, so only the depth at the definition sees it.

    This is what a multi-line custom statement carrying its own ``function``
    produces; before the check it passed Z15 and Z16 and would have died in
    the compiler.
    """
    text = (
        "function main()\n"
        "{\n"
        "\tfoo_a();\n"
        "function sneaky() { wait 1; }\n"
        "\tfoo_b();\n"
        "}\n"
        "function foo_a()\n{\n\twait 1;\n}\n"
        "function foo_b()\n{\n\twait 1;\n}\n"
    )
    assert "gsc_nested" in codes(scan(text).issues)
    smuggled = CustomScript(
        functions=(CustomFunction("foo", ("wait 1;",)),),
        statements=(
            (Slot.AFTER_ENTRY, "foo();\nfunction sneaky() { wait 1; }\nfoo();"),
        ),
    )
    report = check_script_soundness(render_server_script(_plan(smuggled)), label="x")
    assert "Z15" in [f.code for f in report.errors]


def test_the_box_cannot_be_rigged_to_a_weapon_the_level_does_not_have() -> None:
    """A box weapon the install does not carry fails silently.

    ``shotgun_olympia`` is in neither the install's
    ``gamedata/weapons/zm/zm_levelcommon_weapons.csv`` nor any assetlist under
    ``zone_source/*/assetlist`` (measured), so the hook's ``a_out``
    comes back empty, it returns the candidate array untouched, and the box
    hands out random weapons with nothing to say about it.
    """
    with pytest.raises(KeyError, match="not in this level's weapon set"):
        tricks.rigged_mystery_box("shotgun_olympia")


def test_the_box_cannot_be_rigged_to_a_weapon_the_chest_will_not_offer() -> None:
    """``shotgun_pump`` is in the table but its ``in_box`` flag is FALSE."""
    with pytest.raises(KeyError, match="in_box flag is FALSE"):
        tricks.rigged_mystery_box("shotgun_pump")


# --------------------------------------------------------------------------
# The zone hook's flag order, and effects the map declares
# --------------------------------------------------------------------------
def test_the_zone_hook_initialises_its_flag_before_the_adjacency_calls() -> None:
    """The order the mod tools' own template and every shipped zone hook use.

    ``rex/templates/ZM Mod Level/usermaps/template/scripts/zm/template.gsc``
    has ``flag::init`` and ``flag::set`` in ``usermap_test_zone_init`` and no
    adjacency call; ``zm_castle_zones.gsc``, ``zm_tomb.gsc``,
    ``zm_theater.gsc``, ``zm_stalingrad_zones.gsc``, ``zm_island_zones.gsc``
    and ``zm_genesis_zones.gsc`` all have the two flag lines first and the
    ``add_adjacent_zone`` calls after.  ``add_adjacent_zone`` creates a flag
    nothing has defined, and ``flag::init`` writes a flag back to zero, so
    the other order re-initialises any flag the two share.
    """
    from zmforge.blueprint.script_plan import ZoneEdge

    plan = ScriptPlan(
        map_name="zm_x",
        zones=["start_zone", "hall_zone"],
        edges=[ZoneEdge("start_zone", "hall_zone", "enter_hall")],
    )
    text = render_server_script(plan)
    assert text.index('flag::init( "always_on" )') < text.index("add_adjacent_zone")
    assert text.index('flag::set( "always_on" )') < text.index("add_adjacent_zone")


def test_a_flag_initialised_after_an_adjacency_call_is_a_finding() -> None:
    """The negative half: the emitted order is checked, not assumed."""
    from zmforge.verify.files import check_server_script

    broken = (
        "function connect_zones()\n"
        "{\n"
        '\tzm_zonemgr::add_adjacent_zone( "a", "b", "enter_b" );\n'
        '\tlevel flag::init( "enter_b" );\n'
        '\tlevel flag::set( "enter_b" );\n'
        "}\n"
    )
    report = check_server_script(broken)
    assert "Z3" in [finding.code for finding in report.errors]


def test_a_declared_effect_is_precached_in_both_scripts() -> None:
    """An ``fx`` line packs the effect; the precache is what plays it.

    The mod tools' own raw sources carry both halves: ``zm_giant.gsc`` has
    ``#precache( "fx", ... )`` and ``zm_giant_fx.csc`` the same paths as
    ``#precache( "client_fx", ... )``.  The client spelling is the half the
    community says gets forgotten.
    """
    from zmforge.emit.scripts import render_client_script

    plan = ScriptPlan(
        map_name="zm_x",
        zones=["start_zone"],
        precache_fx=["dlc0/factory/fx_elec_trap_factory"],
    )
    assert (
        '#precache( "fx", "dlc0/factory/fx_elec_trap_factory" );'
        in render_server_script(plan)
    )
    assert (
        '#precache( "client_fx", "dlc0/factory/fx_elec_trap_factory" );'
        in render_client_script(plan)
    )


def test_declaring_an_fx_asset_is_all_it_takes() -> None:
    """The seam: one ``declare_asset`` call reaches the manifest and both scripts."""
    from zmforge.recipes import one_room_map

    blueprint = one_room_map("zm_x")
    blueprint.declare_asset("fx", "dlc0/factory/fx_elec_trap_factory")
    assert blueprint.script.precache_fx == ["dlc0/factory/fx_elec_trap_factory"]


def test_a_declared_effect_with_no_precache_is_a_finding() -> None:
    """The negative half of the manifest-and-scripts check."""
    from zmforge.verify.files import check_declarations

    report = check_declarations(
        "fx,dlc0/factory/fx_elec_trap_factory\n",
        "#using scripts\\zm\\zm_usermap;\nfunction main()\n{\n}\n",
        "#using scripts\\zm\\zm_usermap;\nfunction main()\n{\n}\n",
        "zm_x",
    )
    messages = [finding.message for finding in report.errors]
    assert len(messages) == 2, messages
    assert any("server script never precaches" in m for m in messages)
    assert any("client script never precaches" in m for m in messages)


def test_a_loose_script_with_no_using_line_is_a_finding() -> None:
    """A ``scriptparsetree`` line alone compiles the script and calls nothing.

    The third artefact the community's install steps require, the entity the
    script looks for by ``targetname``, cannot be checked here: only the
    script being installed knows the name.  It is on the manual list.
    """
    from zmforge.verify.files import check_declarations

    manifest = (
        "scriptparsetree,scripts/zm/zm_x.gsc\n"
        "scriptparsetree,scripts/zm/zm_x.csc\n"
        "scriptparsetree,scripts/zm/ugxmods_buyable_ending.gsc\n"
    )
    script = "#using scripts\\zm\\zm_usermap;\nfunction main()\n{\n}\n"
    report = check_declarations(manifest, script, script, "zm_x")
    assert [finding.code for finding in report.errors] == ["Z17"]
    assert "ugxmods_buyable_ending" in report.errors[0].message

    with_using = (
        "#using scripts\\zm\\ugxmods_buyable_ending;\n"
        "#using scripts\\zm\\zm_usermap;\nfunction main()\n{\n}\n"
    )
    assert check_declarations(manifest, with_using, script, "zm_x").ok
