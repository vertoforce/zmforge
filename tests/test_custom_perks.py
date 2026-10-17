"""Perks of our own: what a recipe writes, what the files say, and what Z50 refuses.

A perk the game does not have is five registration calls in the map's own
script, one ``script_struct`` and one line in the map's ``.str``
(:mod:`zmforge.script.perks`).  These pin all three against the lines of
``_zm_perks.gsc`` they were read out of, and pin the failures Z50 names.

**Nothing here is verified in game.**  Every assertion is a property of the
text a commit writes.  A perk that links is not a perk that works.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint.model import Blueprint
from zmforge.emit.mapfile import build_document
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.emit.strings import PROMPT_SHAPE, asset_name, render_str_file
from zmforge.errors import BlueprintError
from zmforge.mapsource import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import three_room_map
from zmforge.script import gsc, symbols
from zmforge.script.perks import (
    BOUND_ICON_SLOTS,
    COIN_RETURN,
    DIVE_TO_NUKE_ICON,
    STOCK_BOTTLES,
    TOMBSTONE_ICON,
    CustomPerk,
    IconSlot,
    move_speed,
    perk_script,
    points_each_round,
)
from zmforge.spatial import Facing, Point
from zmforge.verify import blueprint as check_blueprint
from zmforge.verify.files import check_gameplay

MAP_NAME = "zm_forge_gate"

#: Somewhere inside the fixture's arena, which is x -112..752, y -496..496.
SPOT = Point(-40.0, -400.0, 16.0)
ELSEWHERE = Point(500.0, -400.0, 16.0)


def _perk_map(perk: CustomPerk = COIN_RETURN, position: Point = SPOT) -> Blueprint:
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_custom_perk(perk, position, Facing.NORTH, id="own_perk")
    return blueprint


def _written(blueprint: Blueprint):
    """The three files as text, the way a commit writes them."""
    document = parse_map_text(render_map_text(build_document(blueprint)))
    return (
        document,
        render_server_script(blueprint.script),
        render_client_script(blueprint.script),
    )


def _findings(blueprint, *, script=None, client=None, document=None):
    written_document, server, written_client = _written(blueprint)
    report = check_gameplay(
        document if document is not None else written_document,
        server if script is None else script,
        client_script=written_client if client is None else client,
    )
    return [f for f in report.findings if f.code == "Z50"]


# ------------------------------------------------------------- the recipe side


def test_a_recipe_declares_a_perk_with_five_facts_and_an_effect() -> None:
    """The whole API surface, so a recipe writer can read it off one test."""
    perk = CustomPerk(
        slug="rinse_aid",
        name="RINSE AID",
        cost=2000,
        effect=points_each_round(50),
        bottle="zombie_perk_bottle_sleight",
        machine_model="p7_zm_vending_ads",
        icon=DIVE_TO_NUKE_ICON,
    )
    assert perk.specialty == "specialty_zmf_rinse_aid"
    assert perk.alias == "zmf_rinse_aid"
    assert perk.radiant_name == "zmf_vending_rinse_aid"
    assert perk.reference == "PERK_RINSE_AID"
    assert perk.bottle in STOCK_BOTTLES


def test_placing_one_is_the_same_call_a_stock_perk_gets() -> None:
    """It is a Machine, so every placement check already applies to it."""
    blueprint = _perk_map()
    machine = blueprint.find("own_perk")
    assert machine.perk.specialty == COIN_RETURN.specialty
    assert machine.perk.xmodel == COIN_RETURN.machine_model
    # No module: the perk's script is this map's own file, which is the whole
    # difference from a stock perk.
    assert machine.perk.module is None
    assert COIN_RETURN.specialty not in blueprint.script.perk_rotation


def test_a_map_without_one_is_the_map_it_always_was() -> None:
    plain = three_room_map(MAP_NAME)
    assert plain.custom_perks == []
    before = render_server_script(plain.script)
    assert "register_perk_basic_info" not in before
    assert "_custom_perks" not in before
    assert not plain.ships_localized_strings()


def test_two_machines_for_one_perk_are_one_registration() -> None:
    blueprint = _perk_map()
    blueprint.place_custom_perk(COIN_RETURN, ELSEWHERE, Facing.NORTH, id="second")
    _, server, _ = _written(blueprint)
    assert server.count("register_perk_basic_info") == 1
    assert len(blueprint.custom_perks) == 1


# ------------------------------------------------------------------ the script


def test_the_five_registrations_are_written_before_the_framework_entry() -> None:
    """``zm_perks::init`` runs inside the entry, so afterwards is too late."""
    _, server, _ = _written(_perk_map())
    call = "zmf_perk_coin_return_register();"
    assert call in server
    assert server.index(call) < server.index("zm_usermap::main()")
    for registration in (
        "register_perk_basic_info",
        "register_perk_precache_func",
        "register_perk_machine",
        "register_perk_threads",
        "register_perk_host_migration_params",
    ):
        assert f"zm_perks::{registration}(" in server


def test_the_registration_names_the_price_the_prompt_and_the_bottle() -> None:
    _, server, _ = _written(_perk_map())
    asset = asset_name(f"{MAP_NAME}.str", COIN_RETURN.reference)
    assert (
        f'zm_perks::register_perk_basic_info( "{COIN_RETURN.specialty}", '
        f'"{COIN_RETURN.alias}", {COIN_RETURN.cost}, &"{asset}", '
        f'GetWeapon( "{COIN_RETURN.bottle}" ) );' in server
    )


def test_the_precache_function_fills_in_what_the_framework_reads() -> None:
    """``level.machine_assets`` and ``level._effect``, both by name."""
    _, server, _ = _written(_perk_map())
    specialty = COIN_RETURN.specialty
    assert f'level.machine_assets[ "{specialty}" ] = SpawnStruct();' in server
    assert (
        f'level.machine_assets[ "{specialty}" ].weapon = '
        f'GetWeapon( "{COIN_RETURN.bottle}" );' in server
    )
    for field in ("off_model", "on_model"):
        assert (
            f'level.machine_assets[ "{specialty}" ].{field} = '
            f'"{COIN_RETURN.machine_model}";' in server
        )
    assert (
        f'level._effect[ "{COIN_RETURN.light_handle}" ] = "{COIN_RETURN.light_fx}";'
        in server
    )


def test_the_machine_setup_stamps_this_perks_own_names() -> None:
    """Not a stock name: ``_zm_perk_electric_cherry.gsc`` is what that costs."""
    _, server, _ = _written(_perk_map())
    assert f'perk_machine.targetname = "{COIN_RETURN.radiant_name}";' in server
    assert f'use_trigger.target = "{COIN_RETURN.radiant_name}";' in server
    # The jingle is named because _zm_audio.gsc:1607 reads it with no guard,
    # and it is silent because a usermap has no perk aliases.
    assert f'use_trigger.script_sound = "{COIN_RETURN.jingle}";' in server
    assert f'use_trigger.script_label = "{COIN_RETURN.sting}";' in server


def test_the_effect_is_the_one_the_recipe_asked_for() -> None:
    _, server, _ = _written(_perk_map())
    assert 'level waittill( "start_of_round" );' in server
    assert "self zm_score::add_to_player_score( 100 );" in server
    # The give thread ends on the notify the take function sends, which is the
    # framework's own contract for a perk that is lost or paused.
    assert f'self endon( "{COIN_RETURN.stop_notify}" );' in server
    assert f'self notify( "{COIN_RETURN.stop_notify}" );' in server


def test_a_different_dividend_is_a_different_number_and_nothing_else() -> None:
    perk = CustomPerk(
        slug="coin_return", name="COIN RETURN", cost=1500, effect=points_each_round(250)
    )
    _, server, _ = _written(_perk_map(perk))
    assert "self zm_score::add_to_player_score( 250 );" in server


def test_a_dividend_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError):
        points_each_round(0)


# ------------------------------------------------------------- the speed one


def _speed_perk(percent: float = 75.0) -> CustomPerk:
    return CustomPerk(
        slug="fast_lane",
        name="FAST LANE",
        cost=3000,
        effect=move_speed(percent),
        icon=DIVE_TO_NUKE_ICON,
    )


def test_speed_is_a_scale_on_base_movement_and_75_per_cent_is_1_75() -> None:
    """The only movement call the stock scripts make on a player.

    ``zm_usermap.gsc:336`` sets this player's scale to 1 on every spawn and
    ``_zm.gsc:4795`` sets 0.3 on a zombified one, so 1 is normal and 75%
    faster is 1.75.  This checks the text; how it plays is not measured.
    """
    _, server, _ = _written(_perk_map(_speed_perk()))
    assert "self SetMoveSpeedScale( 1.75 );" in server
    # and it goes back to what the spawn path itself writes when the perk does
    assert "self SetMoveSpeedScale( 1 );" in server


def test_the_speed_perk_re_applies_itself_after_a_spawn() -> None:
    """The spawn path resets the scale, so setting it once is not holding it.

    ``giveCustomCharacters`` (``zm_usermap.gsc:336``) runs from
    ``giveLoadoutLevelSpecific`` (``_globallogic_spawn.gsc:176-178``) and the
    notify below is sent at the end of the same ``spawnPlayer`` (``:464``).
    """
    _, server, _ = _written(_perk_map(_speed_perk()))
    give = server[server.index("function zmf_perk_fast_lane_give()") :]
    give = give[: give.index("\n}\n")]
    assert 'self waittill( "spawned_player" );' in give
    assert give.count("self SetMoveSpeedScale( 1.75 );") == 2


def test_a_different_percentage_is_a_different_scale_and_nothing_else() -> None:
    _, server, _ = _written(_perk_map(_speed_perk(50)))
    assert "self SetMoveSpeedScale( 1.5 );" in server


def test_a_speed_perk_that_makes_you_no_faster_is_refused() -> None:
    for percent in (0, -25):
        with pytest.raises(ValueError):
            move_speed(percent)


def test_the_speed_perk_borrows_no_module_and_no_stamin_up() -> None:
    """Stamin-Up's boost is engine-side off its own specialty, not a call.

    ``_zm_perk_staminup.gsc`` contains no movement call at all, so there is
    nothing there for a perk of ours to reuse; what this perk uses is the
    engine builtin, which needs no ``#using`` line.
    """
    effect = move_speed(75)
    assert effect.using == ()
    _, server, _ = _written(_perk_map(_speed_perk()))
    assert "staminup" not in server
    assert "specialty_staminup" not in server


def test_both_emitted_scripts_are_sound_and_every_call_resolves() -> None:
    """The one defence off Windows: a table of what really exists."""
    _, server, client = _written(_perk_map())
    for text in (server, client):
        source = gsc.scan(text)
        assert source.issues == []
        assert symbols.unresolved(source) == []


def test_the_script_carries_the_using_lines_its_own_text_needs() -> None:
    _, server, _ = _written(_perk_map())
    for module in (
        r"scripts\zm\_zm_perks",
        r"scripts\zm\_zm_score",
        r"scripts\shared\clientfield_shared",
    ):
        assert f"#using {module};" in server


def test_the_perk_adds_nothing_to_the_client_script_but_the_effect_handle() -> None:
    """No client half: this perk registers no clientfield on either side."""
    plain = render_client_script(three_room_map(MAP_NAME).script)
    _, _, client = _written(_perk_map())
    assert "register_perk" not in client
    assert "set_player_uimodel" not in client
    added = [line for line in client.splitlines() if line not in plain.splitlines()]
    assert added == [f'#precache( "client_fx", "{COIN_RETURN.light_fx}" );']


# -------------------------------------------------------------------- the icon


def test_the_icon_is_written_rather_than_registered() -> None:
    """A registered clientfield the two sides disagree about is a disconnect.

    This perk registers none, so the map registers exactly the clientfields it
    registered without it.  Whether the shipped widget draws an unregistered
    path is **unverified**; the failure if it does not is no icon.
    """
    _, server, client = _written(_perk_map())
    assert (
        f'self clientfield::set_player_uimodel( "{TOMBSTONE_ICON.path}", n_state );'
        in server
    )
    assert "clientfield::register" not in server
    assert "clientfield::register" not in client


def test_the_two_claimable_slots_are_the_two_nothing_owns() -> None:
    """Eleven keys are bound; nine belong to perks with a module."""
    for slot in (TOMBSTONE_ICON, DIVE_TO_NUKE_ICON):
        assert BOUND_ICON_SLOTS[slot.key] is None
    owned = {key for key, perk in BOUND_ICON_SLOTS.items() if perk is not None}
    assert len(BOUND_ICON_SLOTS) == 11
    assert len(owned) == 9


def test_a_perk_can_have_no_icon_at_all() -> None:
    perk = CustomPerk(
        slug="coin_return", name="COIN RETURN", cost=1500,
        effect=points_each_round(100), icon=None,
    )
    _, server, _ = _written(_perk_map(perk))
    assert "set_player_uimodel" not in server


# ------------------------------------------------------------------ the string


def test_the_prompt_is_shipped_precached_and_declared() -> None:
    """Three halves, and any one alone is a blank line on the machine."""
    blueprint = _perk_map()
    asset = asset_name(f"{MAP_NAME}.str", COIN_RETURN.reference)
    _, server, _ = _written(blueprint)
    assert f'#precache( "string", "{asset}" );' in server
    assert blueprint.ships_localized_strings()
    entry = next(
        s for s in blueprint.localized_strings() if s.reference == COIN_RETURN.reference
    )
    assert entry.english == PROMPT_SHAPE.replace("$NAME", "COIN RETURN")
    assert "COIN RETURN" in render_str_file(blueprint.localized_strings())
    assert ("localize", MAP_NAME) in [(a.prefix, a.name) for a in blueprint.assets]


def test_the_machine_light_is_precached_and_not_declared() -> None:
    """It is already in the level-common zone: a manifest line packs it twice."""
    blueprint = _perk_map()
    assert COIN_RETURN.light_fx in blueprint.script.precache_fx
    assert ("fx", COIN_RETURN.light_fx) not in [
        (a.prefix, a.name) for a in blueprint.assets
    ]
    _, server, client = _written(blueprint)
    assert f'#precache( "fx", "{COIN_RETURN.light_fx}" );' in server
    assert f'#precache( "client_fx", "{COIN_RETURN.light_fx}" );' in client


# ----------------------------------------------------------------- the machine


def test_the_machine_is_the_struct_the_framework_reads() -> None:
    """``_zm_perks.gsc:1419``: model and script_noteworthy on a struct."""
    document, _, _ = _written(_perk_map())
    structs = [
        e
        for e in document.entities_of("script_struct")
        if e.value("targetname") == "zm_perk_machine"
        and e.value("script_noteworthy") == COIN_RETURN.specialty
    ]
    assert len(structs) == 1
    assert structs[0].value("model") == COIN_RETURN.machine_model


# ---------------------------------------------------------------------- Z50


def test_z50_is_quiet_on_a_map_that_does_it_right() -> None:
    assert _findings(_perk_map()) == []
    assert [f for f in check_blueprint(_perk_map()).findings if f.code == "Z50"] == []


def test_z50_refuses_a_perk_with_no_bottle() -> None:
    """The defect worth naming twice: it charges and gives nothing."""
    blueprint = _perk_map()
    _, server, _ = _written(blueprint)
    hits = _findings(
        blueprint,
        script=server.replace(
            f'GetWeapon( "{COIN_RETURN.bottle}" ) );', "undefined );", 1
        ),
    )
    assert len(hits) == 1
    assert "no bottle" in hits[0].message


def test_the_model_refuses_a_perk_with_no_bottle_before_that() -> None:
    with pytest.raises(ValueError):
        CustomPerk(slug="x", name="X", cost=500, effect=points_each_round(10), bottle="")


def test_z50_refuses_a_perk_whose_script_the_map_never_carries() -> None:
    blueprint = _perk_map()
    _, server, _ = _written(blueprint)
    stripped = server[: server.index("function zmf_perk_coin_return_register")]
    hits = _findings(
        blueprint, script=stripped.replace("\tzmf_perk_coin_return_register();\n", "")
    )
    assert len(hits) == 1
    assert "never registers it" in hits[0].message


def test_z50_refuses_a_registration_main_never_calls() -> None:
    blueprint = _perk_map()
    _, server, _ = _written(blueprint)
    hits = _findings(
        blueprint, script=server.replace("\tzmf_perk_coin_return_register();\n", "")
    )
    assert len(hits) == 1
    assert "never calls it" in hits[0].message


def test_z50_refuses_a_registration_after_the_framework_entry() -> None:
    blueprint = _perk_map()
    _, server, _ = _written(blueprint)
    moved = server.replace("\tzmf_perk_coin_return_register();\n", "").replace(
        "\tzm_usermap::main();",
        "\tzm_usermap::main();\n\tzmf_perk_coin_return_register();",
    )
    hits = _findings(blueprint, script=moved)
    assert len(hits) == 1
    assert "too late" in hits[0].message


def test_z50_refuses_a_perk_with_no_machine_to_buy_it_from() -> None:
    blueprint = three_room_map(MAP_NAME)
    blueprint.declare_perk(COIN_RETURN)
    hits = _findings(blueprint)
    assert len(hits) == 1
    assert "no machine carrying that script_noteworthy" in hits[0].message
    model = [f for f in check_blueprint(blueprint).findings if f.code == "Z50"]
    assert len(model) == 1
    assert "places no machine for it" in model[0].message


def test_z50_refuses_an_unprecached_prompt() -> None:
    blueprint = _perk_map()
    asset = asset_name(f"{MAP_NAME}.str", COIN_RETURN.reference)
    _, server, _ = _written(blueprint)
    hits = _findings(
        blueprint, script=server.replace(f'#precache( "string", "{asset}" );\n', "")
    )
    assert len(hits) == 1
    assert "blank" in hits[0].message


def test_z50_refuses_a_machine_light_with_no_handle() -> None:
    """The one asset a custom perk names that Z17 cannot see."""
    blueprint = _perk_map()
    _, server, client = _written(blueprint)
    line = f'#precache( "client_fx", "{COIN_RETURN.light_fx}" );\n'
    hits = _findings(blueprint, client=client.replace(line, ""))
    assert len(hits) == 1
    assert "no handle" in hits[0].message


def test_the_model_refuses_two_perks_claiming_one_slot() -> None:
    blueprint = _perk_map()
    other = CustomPerk(
        slug="rinse_aid", name="RINSE AID", cost=1000, effect=points_each_round(50)
    )
    with pytest.raises(BlueprintError) as raised:
        blueprint.place_custom_perk(other, ELSEWHERE, Facing.NORTH, id="rinse")
    assert "tombstone" in str(raised.value)


def test_the_model_refuses_a_slug_a_stock_machine_already_answers_to() -> None:
    """Every finding this package prints names a machine by slug."""
    blueprint = three_room_map(MAP_NAME)
    with pytest.raises(BlueprintError):
        blueprint.declare_perk(
            CustomPerk(
                slug="juggernog", name="NOT JUGGERNOG", cost=500,
                effect=points_each_round(10),
            )
        )


def test_two_perks_on_the_two_free_slots_are_fine() -> None:
    blueprint = _perk_map()
    other = CustomPerk(
        slug="rinse_aid",
        name="RINSE AID",
        cost=1000,
        effect=points_each_round(50),
        icon=DIVE_TO_NUKE_ICON,
    )
    blueprint.place_custom_perk(other, ELSEWHERE, Facing.NORTH, id="rinse")
    assert _findings(blueprint) == []


def test_z50_refuses_a_slot_a_stock_perk_on_this_map_owns() -> None:
    """Juggernog is on the fixture, and its own module writes that path."""
    juggernog_slot = IconSlot(
        "juggernaut",
        "hudItems.perks.juggernaut",
        "specialty_juggernaut_zombies",
        "_zm_perks.gsh:11 PERK_CLIENTFIELD_JUGGERNAUT",
    )
    perk = CustomPerk(
        slug="coin_return",
        name="COIN RETURN",
        cost=1500,
        effect=points_each_round(100),
        icon=juggernog_slot,
    )
    blueprint = _perk_map(perk)
    hits = _findings(blueprint)
    assert len(hits) == 1
    assert "fight over one widget" in hits[0].message
    model = [f for f in check_blueprint(blueprint).findings if f.code == "Z50"]
    assert len(model) == 1


def test_z50_says_nothing_about_a_stock_only_map() -> None:
    assert _findings(three_room_map(MAP_NAME)) == []


def test_a_machine_nobody_can_reach_is_already_somebody_elses_job() -> None:
    """Trap four is not Z50's: a custom perk is a Machine, so Z25 and Z48 ask."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_custom_perk(
        COIN_RETURN, Point(300.0, -700.0, 16.0), Facing.NORTH, id="own_perk"
    )
    codes = {f.code for f in check_blueprint(blueprint).findings}
    assert {"Z25", "Z48"} <= codes


# --------------------------------------------------------------------- the perk


def test_the_shipped_perk_borrows_only_stock_names() -> None:
    """Everything it shows the player is on the level-common asset list."""
    from zmforge.script.perks import STOCK_MACHINE_LIGHTS, STOCK_MACHINE_MODELS

    perk = COIN_RETURN
    assert perk.bottle in STOCK_BOTTLES
    assert perk.machine_model in STOCK_MACHINE_MODELS
    assert perk.light_fx in STOCK_MACHINE_LIGHTS


def test_the_perk_script_is_the_same_text_every_time() -> None:
    """Regenerate, never patch: two builds of one perk are one file."""
    first = perk_script(COIN_RETURN, "ZM_X_PERK_COIN_RETURN")
    second = perk_script(COIN_RETURN, "ZM_X_PERK_COIN_RETURN")
    assert first == second


def test_a_machine_whose_front_is_not_south_turns_and_shifts_by_its_own_front() -> None:
    """FIGHT OR FLIGHT's fridge has its door on +x (``front_zero`` EAST): the
    placed yaw turns that door to the asked facing, and the use trigger moves
    along ``AnglesToForward``, not the vending machines' ``AnglesToRight``."""
    import dataclasses

    from zmforge.blueprint.catalogue import prefab_yaw

    fridge = dataclasses.replace(COIN_RETURN, machine_model="p7_cai_fridge_metal_plant",
                                 front_zero=Facing.EAST, trigger_shift=24.0)
    text = str(perk_script(fridge, "ZM_X_PERK_COIN_RETURN"))
    assert "AnglesToForward( perk_machine.angles ), 24 )" in text
    assert "AnglesToRight( perk_machine.angles )" not in text
    vending = dataclasses.replace(COIN_RETURN, trigger_shift=24.0)
    assert "AnglesToRight( perk_machine.angles ), 24 )" in str(perk_script(vending, "ZM_X_PERK_COIN_RETURN"))
    # door (+x) to the west: yaw 180
    assert prefab_yaw(Facing.WEST, fridge.front_zero) == 180.0
    blueprint = three_room_map(MAP_NAME)
    machine = blueprint.place_custom_perk(fridge, SPOT, Facing.WEST)
    assert machine.perk.front_zero == Facing.EAST


def test_the_icon_write_cannot_stop_the_perk_effect() -> None:
    """The HUD path is not a registered clientfield; if writing it errors at
    run time, only its own thread may end.  The give thread starts it and
    goes straight on to the effect; the take thread clears it last."""
    import re

    _, server, _ = _written(_perk_map())

    def body(name: str) -> str:
        start = server.index(f"function {name}(")
        return server[start: server.index("\n}", start)]

    give_name = re.search(r"function (\w+_give)\(", server).group(1)
    prefix = give_name[: -len("_give")]
    give, take, hud = body(f"{prefix}_give"), body(f"{prefix}_take"), body(f"{prefix}_hud")
    assert "set_player_uimodel" not in give and "set_player_uimodel" not in take
    assert f"self thread {prefix}_hud( 1 );" in give
    assert take.rstrip().endswith(f"self thread {prefix}_hud( 0 );")
    assert "set_player_uimodel" in hud and hud.index("wait 0.05;") < hud.index("set_player_uimodel")
