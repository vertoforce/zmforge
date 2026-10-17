"""Der Wunderfizz: what a map has to emit, and what Z49 refuses.

The machine that sells a random perk is not a perk and does not go through
the perk-machine mechanism.  It is one zbarrier entity the stock script finds
by ``targetname`` and drives by piece index, plus a rotation the map has to
fill in itself.  These pin the entity and both script halves against the
lines of ``_zm_perk_random.{gsc,csc,gsh}`` they were read out of.

**Nothing here is verified in game.**  Every assertion is a property of the
text a commit writes.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint import catalogue as fixed
from zmforge.blueprint.elements import Wunderfizz
from zmforge.blueprint.script_plan import ScriptPlan
from zmforge.emit.mapfile import build_document
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.mapsource import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import three_room_map
from zmforge.spatial import Facing, Point
from zmforge.verify.files import check_gameplay

MAP_NAME = "zm_forge_gate"


#: What ``three_room_map`` already places, in the order it places them --
#: which is therefore the rotation a Wunderfizz on that fixture inherits.
FIXTURE_ROTATION = [
    "specialty_armorvest",
    "specialty_fastreload",
    "specialty_quickrevive",
    "specialty_doubletap2",
]


def _fizz_map(**kwargs):
    """The fixture with one Wunderfizz beside its four perks."""
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    blueprint.place_wunderfizz(
        Point(300.0, -700.0, arena.floor_z), Facing.NORTH, id="fizz", **kwargs
    )
    return blueprint


def _written(blueprint):
    """The three files as text, the way a commit writes them."""
    document = parse_map_text(render_map_text(build_document(blueprint)))
    return (
        document,
        render_server_script(blueprint.script),
        render_client_script(blueprint.script),
    )


# ---------------------------------------------------------------- the entity


def test_the_machine_is_an_entity_the_stock_script_can_find() -> None:
    """``_zm_perk_random.gsc:91`` GetEntArray( "perk_random_machine", ... )."""
    document, _, _ = _written(_fizz_map())
    machines = [
        e for e in document.entities if e.value("targetname") == "perk_random_machine"
    ]
    assert len(machines) == 1
    assert machines[0].classname == "zbarrier_zmcore_packapunch"
    # Not a struct.  The perk machines are; this one is not, and the whole
    # reason it needed its own emitter is that the two are different.
    assert machines[0].classname != "script_struct"
    assert machines[0].value("zm_perk_machine") is None


def test_the_first_machine_is_the_one_the_script_starts_on() -> None:
    """``init_starting_perk_random_machine_location`` needs exactly one."""
    blueprint = _fizz_map()
    arena = blueprint.find("arena_room")
    blueprint.place_wunderfizz(
        Point(420.0, -700.0, arena.floor_z), Facing.NORTH, id="fizz_two"
    )
    document, _, _ = _written(blueprint)
    machines = [
        e for e in document.entities if e.value("targetname") == "perk_random_machine"
    ]
    marked = [
        e
        for e in machines
        if "start_perk_random_machine" in (e.value("script_noteworthy") or "")
    ]
    assert len(machines) == 2
    assert len(marked) == 1


def test_the_machine_carries_the_six_boards_the_script_drives() -> None:
    """``_zm_perk_random.gsh:26-31`` names piece indices 0 through 5."""
    document, _, _ = _written(_fizz_map())
    machine = next(
        e for e in document.entities if e.value("targetname") == "perk_random_machine"
    )
    assert machine.value("zbarriernumboards") == "6"
    models = [machine.value(f"zbarrierboardmodel{n}") for n in range(1, 7)]
    assert models == list(fixed.WUNDERFIZZ_PIECES)
    # The three body pieces are the model the mod tools install actually ships, and
    # process_perk_random_machine_state shows one of them in every state.
    assert models[1:4] == ["p7_zm_vending_wonder"] * 3
    # Blank rather than absent: left out, each piece inherits an animation
    # from the borrowed pack-a-punch definition.
    for n in range(1, 7):
        assert machine.value(f"zbarrierboardanim{n}") == ""
        assert machine.value(f"zbarriertearanim{n}") == ""


def test_placing_one_declares_no_asset_and_ships_no_file() -> None:
    """Everything it needs is already in ``zm_levelcommon.csv``.

    So placing one adds no manifest line, and the link needs no new file.
    """
    plain = three_room_map(MAP_NAME)
    fizz = _fizz_map()
    assert [a.line for a in fizz.assets] == [a.line for a in plain.assets]


# --------------------------------------------------------------- the scripts


def test_both_scripts_name_the_module() -> None:
    """The ``.csc`` registers the clientfields the ``.gsc`` sets."""
    _, server, client = _written(_fizz_map())
    using = "#using scripts\\zm\\_zm_perk_random;"
    assert using in server
    assert using in client


def test_a_map_without_one_is_the_script_it_always_was() -> None:
    before = render_server_script(three_room_map(MAP_NAME).script)
    assert "_zm_perk_random" not in before
    assert "include_perk_in_random_rotation" not in before


def test_the_rotation_is_the_perks_on_the_map() -> None:
    _, server, _ = _written(_fizz_map())
    calls = [
        line.strip()
        for line in server.splitlines()
        if "include_perk_in_random_rotation" in line
    ]
    assert calls == [
        f'zm_perk_random::include_perk_in_random_rotation( "{specialty}" );'
        for specialty in FIXTURE_ROTATION
    ]
    # The pack-a-punch is on that fixture too and is not a perk, so it has
    # no specialty string and cannot be in the rotation.
    assert not any("pack" in call for call in calls)


def test_the_rotation_is_registered_after_the_framework_entry() -> None:
    """Treyarch's own page puts them under ``usermaps::main();``."""
    _, server, _ = _written(_fizz_map())
    assert server.index("zm_usermap::main()") < server.index(
        "include_perk_in_random_rotation"
    )


def test_a_perk_placed_after_the_machine_still_joins_the_rotation() -> None:
    """The two calls are order-independent; the plan collects both ways."""
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    blueprint.place_wunderfizz(
        Point(300.0, -700.0, arena.floor_z), Facing.NORTH, id="fizz"
    )
    blueprint.place_perk(
        "deadshot", Point(-380.0, -700.0, arena.floor_z), Facing.NORTH, id="late"
    )
    assert "specialty_deadshot" in render_server_script(blueprint.script)


def test_a_recipe_can_name_the_rotation_itself() -> None:
    """Slugs and specialty strings both work, and the map's perks lose."""
    _, server, _ = _written(_fizz_map(rotation=("quick_revive", "specialty_armorvest")))
    calls = [
        line.strip()
        for line in server.splitlines()
        if "include_perk_in_random_rotation" in line
    ]
    assert calls == [
        'zm_perk_random::include_perk_in_random_rotation( "specialty_quickrevive" );',
        'zm_perk_random::include_perk_in_random_rotation( "specialty_armorvest" );',
    ]


def test_a_machine_that_is_not_a_perk_cannot_be_in_the_rotation() -> None:
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    with pytest.raises(ValueError):
        blueprint.place_wunderfizz(
            Point(300.0, -700.0, arena.floor_z),
            Facing.NORTH,
            rotation=("pack_a_punch",),
            id="fizz",
        )


def test_every_placeable_perk_has_the_specialty_string_the_game_uses() -> None:
    """``_zm_perks.gsh:31-43``, against the modules that register them."""
    by_slug = {perk.slug: perk.specialty for perk in fixed.PERKS}
    assert by_slug["juggernog"] == "specialty_armorvest"
    assert by_slug["speed_cola"] == "specialty_fastreload"
    assert by_slug["mule_kick"] == "specialty_additionalprimaryweapon"
    # The two machines that are not perks stay out of it.
    assert by_slug["pack_a_punch"] is None
    assert by_slug["gobblegum"] is None


# ------------------------------------------------------------------- the check


def test_z49_is_quiet_on_a_map_that_does_it_right() -> None:
    document, server, client = _written(_fizz_map())
    report = check_gameplay(document, server, client_script=client)
    assert [f for f in report.findings if f.code == "Z49"] == []


def test_the_check_reads_past_a_commented_out_call() -> None:
    """``strip_noise`` blanks comments; the name comes from the original."""
    document, server, client = _written(_fizz_map())
    server = server.replace(
        'zm_perk_random::include_perk_in_random_rotation( "specialty_armorvest" );',
        '// zm_perk_random::include_perk_in_random_rotation( "specialty_armorvest" );',
    )
    report = check_gameplay(document, server, client_script=client)
    assert [f for f in report.findings if f.code == "Z49"] == []


def test_z49_refuses_a_machine_with_nothing_to_give() -> None:
    """The defect worth naming: a Wunderfizz with an empty rotation."""
    document, server, client = _written(_fizz_map(rotation=()))
    report = check_gameplay(document, server, client_script=client)
    hits = [f for f in report.errors if f.code == "Z49"]
    assert len(hits) == 1
    assert "no perk to give" in hits[0].message


def test_z49_refuses_a_map_with_no_starting_machine() -> None:
    blueprint = _fizz_map()
    blueprint.find("fizz").starting = False
    document, server, client = _written(blueprint)
    report = check_gameplay(document, server, client_script=client)
    hits = [f for f in report.errors if f.code == "Z49"]
    assert len(hits) == 1
    assert "start_perk_random_machine" in hits[0].message


def test_z49_refuses_a_rotation_whose_module_the_script_lacks() -> None:
    """``level.machine_assets`` is only ever written by a perk module."""
    blueprint = _fizz_map()
    blueprint.script.wunderfizz_rotation = ["specialty_staminup"]
    document, server, client = _written(blueprint)
    report = check_gameplay(document, server, client_script=client)
    hits = [f for f in report.errors if f.code == "Z49"]
    assert len(hits) == 1
    assert "_zm_perk_staminup" in hits[0].message


def test_z49_refuses_a_machine_the_client_script_does_not_know_about() -> None:
    document, server, client = _written(_fizz_map())
    client = client.replace("#using scripts\\zm\\_zm_perk_random;\n", "")
    report = check_gameplay(document, server, client_script=client)
    hits = [f for f in report.errors if f.code == "Z49"]
    assert len(hits) == 1
    assert "client script" in hits[0].message


def test_z49_refuses_a_machine_with_too_few_boards() -> None:
    text = render_map_text(build_document(_fizz_map()))
    text = text.replace('"zbarriernumboards" "6"', '"zbarriernumboards" "3"')
    blueprint = _fizz_map()
    report = check_gameplay(
        parse_map_text(text),
        render_server_script(blueprint.script),
        client_script=render_client_script(blueprint.script),
    )
    hits = [f for f in report.errors if f.code == "Z49"]
    assert len(hits) == 1
    assert "zbarriernumboards" in hits[0].message


def test_z49_warns_when_a_rotation_is_registered_with_no_machine() -> None:
    blueprint = three_room_map(MAP_NAME)
    plan = blueprint.script
    document = parse_map_text(render_map_text(build_document(blueprint)))
    plan.wunderfizz = True
    plan.perk_rotation = ["specialty_armorvest"]
    plan.perk_modules = ["scripts\\zm\\_zm_perk_juggernaut"]
    report = check_gameplay(
        document, render_server_script(plan), client_script=render_client_script(plan)
    )
    hits = [f for f in report.warnings if f.code == "Z49"]
    assert len(hits) == 1


def test_the_plan_dedupes_and_keeps_order() -> None:
    plan = ScriptPlan(map_name="zm_demo")
    plan.perk_rotation = ["specialty_armorvest", "specialty_staminup", "specialty_armorvest"]
    assert plan.rotation() == ["specialty_armorvest", "specialty_staminup"]
    plan.wunderfizz_rotation = []
    assert plan.rotation() == []


def test_the_element_is_not_a_machine() -> None:
    """The two mechanisms share nothing, so neither do the types."""
    from zmforge.blueprint.elements import Machine

    assert not issubclass(Wunderfizz, Machine)


# ------------------------------------------------------------- reach (Z42)
def _fizz_inside_a_machine():
    """The fixture with a Wunderfizz moved into a perk machine's body.

    The placement methods refuse this now that the machine has a body, so,
    like ``test_interactive_reach._planted_overlap``, it is planted by moving
    the element after it went in: the road ``Z42`` exists for.
    """
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    jug = blueprint.place_perk(
        "juggernog", Point(300.0, 200.0, arena.floor_z), Facing.NORTH, id="jug"
    )
    fizz = blueprint.place_wunderfizz(
        Point(300.0, -700.0, arena.floor_z), Facing.NORTH, id="fizz"
    )
    fizz.position = Point(jug.position.x + 10.0, jug.position.y, jug.position.z)
    return blueprint


def test_z42_catches_a_wunderfizz_inside_another_item() -> None:
    from zmforge.verify import check_blueprint

    report = check_blueprint(_fizz_inside_a_machine())
    found = [f for f in report.errors if f.code == "Z42"]
    assert len(found) == 1, [str(f) for f in report.errors]
    assert "fizz" in found[0].message and "jug" in found[0].message
    assert "drawn through each other" in found[0].message


def test_placing_a_wunderfizz_inside_another_item_is_refused() -> None:
    from zmforge.errors import InteractiveBlocked

    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    jug = blueprint.place_perk(
        "juggernog", Point(300.0, 200.0, arena.floor_z), Facing.NORTH, id="jug"
    )
    with pytest.raises(InteractiveBlocked):
        blueprint.place_wunderfizz(jug.position, Facing.NORTH, id="fizz")


def test_z42_is_quiet_on_a_wunderfizz_with_room_around_it() -> None:
    from zmforge.verify import check_blueprint

    report = check_blueprint(_fizz_map())
    assert [f for f in report.findings if f.code == "Z42"] == []


def test_the_wunderfizz_has_a_body() -> None:
    from zmforge.blueprint import reach

    keep = reach.keep_of(_fizz_map().find("fizz"))
    assert keep is not None and keep.standing
    assert keep.body.size.x == 2 * reach.BODIES["wunderfizz"].half_width
