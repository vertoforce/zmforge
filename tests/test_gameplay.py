"""Conformance checks Z1-Z14: does the committed map wire the game up?

These parse the files a commit wrote, never the model that wrote them.  Each
check gets a positive test on the three-room fixture and, where the check
exists to catch a specific defect, a negative test that breaks the map and
asserts the checker notices -- a check that has never fired is not evidence.

The fixture is spec appendix C: a configuration known to compile, link and
load in game.  Nothing here claims anything about how it plays; they are
properties of text.
"""

from __future__ import annotations

import re

import math

import pytest

from zmforge import Project
from dataclasses import replace

from zmforge.blueprint.elements import SEALED_OPENING, Lamp, PlayerStart, Window
from zmforge.errors import BlueprintError
from zmforge.blueprint.model import Blueprint
from zmforge.mapsource.writer import render_map_text
from zmforge.emit.mapfile import build_document
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.mapsource import parse_map_text
from zmforge.recipes import FIXTURE, one_room_map, three_room_map
from zmforge.solids.layout import Aperture
from zmforge.spatial import Bounds, Facing, Point, Side
from zmforge.verify.model import PLAYER_HULL_WIDTH, SINGLE_FILE_WIDTH
from zmforge.verify import (
    check_blueprint,
    check_client_script,
    check_gameplay,
    check_manifest,
    check_server_script,
)


MAP_NAME = "zm_forge_gate"


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    """The three-room fixture, written to a throwaway tools root."""
    root = tmp_path_factory.mktemp("tools_root")
    project = Project.create(MAP_NAME, root, blueprint=three_room_map(MAP_NAME))
    result = project.commit()
    paths = project.paths()
    return {
        "project": project,
        "result": result,
        "map_text": paths["map"].read_text(encoding="utf-8"),
        "document": parse_map_text(paths["map"].read_text(encoding="utf-8")),
        "server": paths["server_script"].read_text(encoding="utf-8"),
        "client": paths["client_script"].read_text(encoding="utf-8"),
        "manifest": paths["manifest"].read_text(encoding="utf-8"),
    }


def _structs(document, **match):
    out = []
    for entity in document.entities_of("script_struct"):
        if all(entity.value(key) == value for key, value in match.items()):
            out.append(entity)
    return out


def _origin(entity) -> Point:
    return Point(*(float(v) for v in entity.value("origin").split()))


# --------------------------------------------------------------------------
def test_the_fixture_commits_with_no_errors(committed) -> None:
    """The gate's step 1: commit, then zero errors from verify.files."""
    report = committed["result"].report
    assert report.errors == [], [str(f) for f in report.errors]


def test_the_only_warnings_are_the_wall_buy_depth(committed) -> None:
    """Every warning the fixture produces should be one we chose to keep.

    The wall-buy warnings are deliberate: spec 4.10 fixes the purchase point
    eight units *below* the floor surface as ``[played, not derived]``, and
    reproducing it is what makes the comparison against that build valid.

    ``Z23`` is deliberate in a different way: the fixture puts the
    pack-a-punch and the mystery box on a west wall, and every prefab family
    except the wall buys is still turned with the clockwise yaw
    ``prefab_yaw`` gives, which is 180 degrees from what ``cod2map64``'s
    counter-clockwise turn needs on that heading.  The warning is the record
    that the map ships with a known-bad rotation nobody has measured a
    correction for; see ``docs/playable-map-requirements.md``.

    ``L2`` is deliberate in a third way, and it is on every lamp rather than a
    chosen few: the generator emits neither documented light LOD key, and what
    the engine does with a lamp that has neither has not been measured, so the
    check warns rather than errors and the map ships as it is.  It will stay on
    this list until somebody measures the consequence.
    """
    from conftest import DESIGN_ADVISORIES

    codes = {f.code for f in committed["result"].report.warnings} - DESIGN_ADVISORIES
    assert codes <= {"W1", "Z23", "L2"}, [
        str(f) for f in committed["result"].report.warnings
    ]


# --------------------------------------------------------------------------
# Z1, Z2
# --------------------------------------------------------------------------
def test_z1_spawn_set_is_a_respawn_point_per_zone_and_four_slots(committed) -> None:
    """Item K1: ``info_player_start`` is not read on the zombies path at all.

    One ``player_respawn_point`` per zone, each targeting a group of four
    points, as shipped ``zm_giant.map`` (``_zm.gsc:3453`` reads the target;
    Z86)."""
    document = committed["document"]
    respawn = _structs(document, targetname="player_respawn_point")
    zones = {e.value("targetname") for e in document.entities_of("info_volume")
             if e.value("script_noteworthy") == "player_volume"}
    assert {e.value("script_noteworthy") for e in respawn} == zones
    for entity in respawn:
        group = _structs(document, targetname=entity.value("target"))
        assert [e.value("script_int") for e in group] == ["1", "2", "3", "4"]
    initial = _structs(
        document, targetname="initial_spawn_points", script_noteworthy="initial_spawn"
    )
    assert len(initial) == 4
    # script_int on an initial-spawn struct is the team side, not a slot
    # number; getfreespawnpoint deletes the ones set to 1 or 2.
    assert [e.value("script_int") for e in initial] == [None, None, None, None]
    # It stays on the respawn struct, where it is the ideal distance.
    assert {e.value("script_int") for e in respawn} == {"2000"}
    for entity in initial + respawn:
        assert "zclassic_start_room" in entity.value("script_string").split()
    origins = [_origin(e) for e in initial]
    for index, left in enumerate(origins):
        for right in origins[index + 1 :]:
            assert left.distance_to(right) >= 32.0


def test_z1_fires_when_an_initial_spawn_struct_carries_script_int(committed) -> None:
    """The defect: numbering the slots 1..4 throws one of them away.

    ``zm::getfreespawnpoint`` drops every spawn struct whose ``script_int``
    is the team side it is not dealing with, and in survival every player is
    on ``allies``, so slot 1 or slot 2 is deleted on a coin flip before any
    player is placed.
    """
    text = committed["map_text"].replace(
        '"script_noteworthy" "initial_spawn"',
        '"script_noteworthy" "initial_spawn"\n"script_int" "1"',
    )
    report = check_gameplay(parse_map_text(text), committed["server"])
    assert "Z1" in [f.code for f in report.errors]


def test_z2_script_never_renames_the_start_location(committed) -> None:
    """Item K2: ``zclassic_start_zone`` matches no struct and empties the set."""
    assert "level.default_start_location" not in committed["server"]
    assert check_server_script(committed["server"]).errors == []


def test_z2_fires_on_a_renamed_start_location() -> None:
    script = 'level.dog_rounds_allowed = 0;\nzm_usermap::main();\nlevel.default_start_location = "start_zone";\n'
    codes = [f.code for f in check_server_script(script).errors]
    assert "Z2" in codes


# --------------------------------------------------------------------------
# Z3, Z4, Z5, Z6
# --------------------------------------------------------------------------
def test_z3_zone_volumes_match_the_scripts_init_zones(committed) -> None:
    document, script = committed["document"], committed["server"]
    volumes = [
        e
        for e in document.entities_of("info_volume")
        if e.value("script_noteworthy") == "player_volume"
    ]
    listed = re.findall(r'init_zones\[(\d+)\] = "([^"]+)";', script)
    names = [name for _, name in sorted(listed, key=lambda i: int(i[0]))]
    # Only the zones open at load (G1): the start; the others are
    # registered by their door's add_adjacent_zone call.
    assert names == [FIXTURE.start_zone]
    joined = set(re.findall(r'add_adjacent_zone\( "([^"]+)", "([^"]+)"', script))
    registered = set(names) | {z for pair in joined for z in pair}
    assert {v.value("targetname") for v in volumes} == registered


def test_z3_fires_when_a_volume_names_a_zone_the_script_never_registers(
    committed,
) -> None:
    """A volume whose zone is in no init_zones and no add_adjacent_zone call.

    ``zone_is_enabled`` returns false for a name with no ``level.zones``
    entry (``_zm_zonemgr.gsc:65``), so the volume is not playable area and
    the player standing in it is killed outright rather than downed.  This is
    the naming-mismatch class of bug: the volume and the script disagree and
    nothing about the map looks wrong.
    """
    script = committed["server"]
    script = re.sub(r'[^\n]*add_adjacent_zone\([^\n]*"vault"[^\n]*\n', "", script)
    report = check_gameplay(committed["document"], script)
    named = [
        f
        for f in report.errors
        if f.code == "Z3" and "never registers" in f.message and "vault" in f.message
    ]
    assert len(named) == 1


def test_z3_fires_when_a_registered_zone_is_never_enabled(committed) -> None:
    """Registered by ``add_adjacent_zone``, reached by no flag from a live zone.

    ``add_adjacent_zone`` calls ``zone_init`` on both names and enables
    neither (``_zm_zonemgr.gsc:595``); only ``manage_zones`` on its
    ``init_zones`` array, and the adjacency chain from those, ever enable
    one.  A zone off that chain is registered, empty of players' rights, and
    lethal to stand in.
    """
    script = committed["server"]
    script = re.sub(
        r'[^\n]*add_adjacent_zone\(\s*"start"[^\n]*\n', "", script
    )
    report = check_gameplay(committed["document"], script)
    stranded = {
        name
        for name in ("arena", "vault")
        for f in report.errors
        if f.code == "Z3" and "never enabled" in f.message and repr(name) in f.message
    }
    assert stranded == {"arena", "vault"}


def test_z3_fires_when_a_registered_zone_has_no_volume(committed) -> None:
    """init_zones names a zone; no entity carries that targetname."""
    script = committed["server"].replace(
        'init_zones[0] = "start";', 'init_zones[0] = "start";\n\tinit_zones[1] = "vaultt";')
    report = check_gameplay(committed["document"], script)
    assert [
        f for f in report.errors if f.code == "Z3" and "no player_volume carries" in f.message
    ]


def test_z4_spawn_structs_belong_to_a_zone_and_sit_inside_it(committed) -> None:
    report = check_gameplay(committed["document"], committed["server"])
    assert [f for f in report.errors if f.code == "Z4"] == []
    interior = _structs(
        committed["document"], script_noteworthy="riser_location", script_string="find_flesh"
    )
    assert interior, "the arena and vault risers are interior spawns"


def test_z5_at_least_one_zombie_factory_exists(committed) -> None:
    """With none, the round starts, sets its flag and returns: no zombies."""
    factories = [
        e
        for e in committed["document"].entities
        if e.value("script_noteworthy") == "zombie_spawner"
    ]
    assert factories
    # The usermap aitype, not the level template's older factory one: it is the
    # only `aitype` line in share/zone_source/zm_levelcommon.zone (:51), so it
    # is already in the shipped zone every zombies usermap loads, and its
    # animation tables (zm_genesis_zombie.*) carry the jump, mantle, climb and
    # traverse_procedural moves that zm_factory_zombie.ai_am does not name.
    assert all(
        e.classname == "actor_spawner_zm_usermap_zombie" for e in factories
    )


def test_z5_the_older_factory_spawner_warns_but_is_not_an_error(committed) -> None:
    """Both aitypes ship; one is older.

    ``archetypes/archetypes.gdt`` holds exactly three ``aitype.gdf`` entries
    and two of them are zombies, so these are the only two classnames a
    zombie_spawner can carry.  The factory one links -- a linked map's
    ``zone_source/all/assetinfo/<map>.csv`` shows
    ``spawner_zm_factory_zombie|aitype`` as the parent of
    ``zm_zombie.ai_bt`` and 527 animations -- so Z5 warns rather than errors,
    and reserves the error for a classname that names no aitype at all.
    """
    text = committed["map_text"].replace(
        "actor_spawner_zm_usermap_zombie", "actor_spawner_zm_factory_zombie"
    )
    report = check_gameplay(parse_map_text(text), committed["server"])
    assert [f for f in report.errors if f.code == "Z5"] == []
    warned = [f for f in report.warnings if f.code == "Z5"]
    assert warned and "traversal" in warned[0].message


def test_z5_a_classname_that_names_no_aitype_is_an_error(committed) -> None:
    text = committed["map_text"].replace(
        "actor_spawner_zm_usermap_zombie", "actor_spawner_zm_made_up_zombie"
    )
    report = check_gameplay(parse_map_text(text), committed["server"])
    assert [f for f in report.errors if f.code == "Z5"]


def test_z6_spawn_structs_sit_on_the_floor(committed) -> None:
    """Item E1: 32 and 40 above the slab produced floating, stuck zombies."""
    for entity in committed["document"].entities_of("script_struct"):
        if entity.value("script_noteworthy") not in {
            "riser_location",
            "spawn_location",
            "faller_location",
        }:
            continue
        assert _origin(entity).z == pytest.approx(16.0)


def test_z6_a_floating_spawn_is_refused_at_add_time() -> None:
    from zmforge.errors import NotOnFloor

    blueprint = three_room_map("zm_forge_gate")
    zone = blueprint.zone_named("arena")
    with pytest.raises(NotOnFloor, match="from the surface"):
        blueprint.add_riser(zone, Point(0.0, -400.0, 48.0), Facing.NORTH)


# --------------------------------------------------------------------------
# Z7: doors
# --------------------------------------------------------------------------
def test_z7_each_door_has_a_trigger_a_leaf_and_a_matching_zone_edge(committed) -> None:
    document, script = committed["document"], committed["server"]
    triggers = [
        e
        for e in document.entities_of("trigger_use")
        if e.value("targetname") == "zombie_door"
    ]
    assert len(triggers) == 2
    for trigger in triggers:
        name = trigger.value("target")
        leaves = [
            e
            for e in document.entities_of("script_brushmodel")
            if e.value("targetname") == name
        ]
        models = [
            e
            for e in document.entities_of("script_model")
            if e.value("targetname") == name
        ]
        assert len(leaves) == 1 and len(models) == 1
        assert leaves[0].value("script_vector") == models[0].value("script_vector")
        assert int(trigger.value("zombie_cost")) > 0
        flag = trigger.value("script_flag")
        assert script.count(f'"{flag}" )') == 1
    prices = sorted(int(t.value("zombie_cost")) for t in triggers)
    assert prices == [FIXTURE.arena_door_price, FIXTURE.vault_door_price]


def test_z7_door_trigger_carries_an_explicit_origin_inside_its_brush(committed) -> None:
    """Item E12: brush entities default to 0 0 0 and the prompt measures from it."""
    from zmforge.verify.files import _brush_bounds

    for trigger in committed["document"].entities_of("trigger_use"):
        origin = _origin(trigger)
        assert origin.distance_to(Point(0, 0, 0)) > 0
        assert _brush_bounds(trigger).holds(origin, tolerance=1e-6)


# --------------------------------------------------------------------------
# Z30: the door navigation key
# --------------------------------------------------------------------------
def test_z30_every_door_part_carries_dynamicpath(committed) -> None:
    """Radiant's own entity database defaults DYNAMICPATH to false.

    ``bin\\t7.def.json`` declares it on ``script_brushmodel`` and on
    ``script_model`` with ``"value": "false"``, and stock ``zm_giant.map``
    carries ``"DYNAMICPATH" "1"`` on its barricade clip, its pack-door clip
    and its dog clips.  Without it a door builds, links and opens, and the AI
    paths through the opening are never rejoined.
    """
    document = committed["document"]
    names = {
        t.value("target")
        for t in document.entities_of("trigger_use")
        if t.value("targetname") == "zombie_door"
    }
    assert names
    parts = [
        e
        for kind in ("script_brushmodel", "script_model")
        for e in document.entities_of(kind)
        if e.value("targetname") in names
    ]
    assert len(parts) == 2 * len(names)
    assert all(part.value("DYNAMICPATH") == "1" for part in parts)


def test_z30_fires_when_a_door_part_loses_dynamicpath(committed) -> None:
    """Deep-copied, because ``committed`` is shared and a stripped key leaks."""
    import copy

    from zmforge.verify.files import check_gameplay

    script = committed["server"]
    document = copy.deepcopy(committed["document"])
    assert [f.code for f in check_gameplay(document, script).findings].count("Z30") == 0

    names = {
        t.value("target")
        for t in document.entities_of("trigger_use")
        if t.value("targetname") == "zombie_door"
    }
    victim = next(
        e
        for e in document.entities_of("script_brushmodel")
        if e.value("targetname") in names
    )
    victim.pairs = [pair for pair in victim.pairs if pair[0] != "DYNAMICPATH"]
    assert [f.code for f in check_gameplay(document, script).errors].count("Z30") == 1
    # and the shared fixture is untouched
    assert (
        [f.code for f in check_gameplay(committed["document"], script).findings].count(
            "Z30"
        )
        == 0
    )


# --------------------------------------------------------------------------
# Z8: barricades
# --------------------------------------------------------------------------
def test_z8_each_barricade_has_one_riser_96_units_out(committed) -> None:
    document = committed["document"]
    barricades = [
        e
        for e in document.entities_of("misc_prefab")
        if "barricade" in e.value("model")
    ]
    assert len(barricades) == 2
    for barricade in barricades:
        tag = barricade.value("script_string")
        risers = _structs(document, script_string=tag)
        assert len(risers) == 1
        assert _origin(barricade).distance_to(_origin(risers[0])) == pytest.approx(96.0)
        # The riser faces the barricade.  Its angles are a plain world heading,
        # not the barricade prefab's convention plus 180 -- the stock prefab's
        # own ``exterior_goal`` struct stands outside the window at +Y and
        # carries a world yaw of south, pointing back at the barricade
        # (spec appendix B, measured).  So check it against the
        # direction on the ground rather than against the prefab's yaw.
        toward = _origin(barricade) - _origin(risers[0])
        wanted = math.degrees(math.atan2(toward.y, toward.x)) % 360.0
        facing = float(risers[0].value("angles").split()[1]) % 360.0
        assert facing == pytest.approx(wanted)


def test_z8_a_barricade_may_be_paired_with_a_walk_in_spawn(committed) -> None:
    """The mode is free; Treyarch's own map mostly uses the other one.

    ``_zm_utility.gsc:220-290`` branches on the ``script_noteworthy`` token
    and nothing else about the struct changes, and
    ``map_source/_prefabs/zm/zm_giant/script/zm_giant_nodes.map`` pairs 44 of
    its 50 ``spawn_location`` structs with a ``receiver_set_*`` barricade tag
    against 8 ``riser_location`` structs.  A Z8 that collects
    ``riser_location`` alone reports "matches 0 riser structs" on the shipped
    majority pattern.
    """
    text = committed["map_text"].replace(
        '"script_noteworthy" "riser_location"', '"script_noteworthy" "spawn_location"'
    )
    report = check_gameplay(parse_map_text(text), committed["server"])
    assert [f for f in report.errors if f.code == "Z8"] == []


def test_z8_a_window_can_ask_for_the_walk_in_spawn() -> None:
    """The generator half: ``add_window(spawn_kind=...)`` reaches the file."""
    blueprint = Blueprint("zm_forge_walk")
    room = blueprint.add_room(
        Bounds.between((0, 0, 0), (512, 512, 256)), wall=16.0, id="start"
    )
    zone = blueprint.add_zone("start_room", room, starting=True)
    window = blueprint.add_window(zone, room, Side.WEST, spawn_kind="walk")
    assert blueprint.find(window.riser_id).marker == "spawn_location"

    default = Blueprint("zm_forge_rise")
    room = default.add_room(
        Bounds.between((0, 0, 0), (512, 512, 256)), wall=16.0, id="start"
    )
    zone = default.add_zone("start_room", room, starting=True)
    window = default.add_window(zone, room, Side.WEST)
    assert default.find(window.riser_id).marker == "riser_location"


def test_add_riser_refuses_a_mode_the_engine_does_not_dispatch_on() -> None:
    blueprint = Blueprint("zm_forge_mode")
    room = blueprint.add_room(
        Bounds.between((0, 0, 0), (512, 512, 256)), wall=16.0, id="start"
    )
    zone = blueprint.add_zone("start_room", room, starting=True)
    with pytest.raises(BlueprintError):
        blueprint.add_riser(zone, Point(256, 256, 16), kind="teleport")


def test_z8_fixture_barricades_match_the_played_coordinates(committed) -> None:
    """Appendix C put them at (-320, ±240, 16) with yaw 180 and 0."""
    placed = {
        (e.value("origin"), e.value("angles"))
        for e in committed["document"].entities_of("misc_prefab")
        if "barricade" in e.value("model")
    }
    assert placed == {("-320 -240 16", "0 180 0"), ("-320 240 16", "0 0 0")}


def test_z8_a_barricade_window_starts_at_the_floor() -> None:
    """The opening has to contain the prefab's traversal channel.

    The opposite rule, ``WINDOW_SILL == 48.0``, comes from spec 4.6's "waist height" and its inherited claim that a floor-level sill
    "makes zombies vault onto nothing".  At a 48 sill no zombie comes through
    the window, and the prefab's own brushes say why.  Measured in
    ``_prefabs/zm/zm_core/barricade_reciever_wood.map``, in prefab-local
    units with local z = 0 at the floor surface:

        clip / clip_player      X -48..50   Z 0..113
        traverse, nonColliding  X -25..25   Z 0.. 40
        clip_missile / clip_ai  X -32..32   Z 0.. 35

    The channel they climb through runs from the floor up 40 units.  A
    48-unit sill buries all of it in solid wall.

    The vault-onto-nothing worry is real and is answered elsewhere: the yard
    add_window digs has a floor at the room's own z, and Z8 refuses a riser
    that is not standing in one.
    """
    from zmforge.blueprint.model import (
        TRAVERSE_TOP,
        TRAVERSE_WIDTH,
        WINDOW_HEIGHT,
        WINDOW_SILL,
        WINDOW_WIDTH,
    )

    assert (WINDOW_SILL, WINDOW_WIDTH, WINDOW_HEIGHT) == (0.0, 96.0, 112.0)
    # The default hole contains the channel and fits inside the prefab's clip.
    assert WINDOW_WIDTH >= TRAVERSE_WIDTH and WINDOW_WIDTH <= 98.0
    assert WINDOW_SILL + WINDOW_HEIGHT >= TRAVERSE_TOP and WINDOW_HEIGHT <= 113.0

    blueprint = three_room_map("zm_forge_gate")
    room = blueprint.find("start_room")
    for window in blueprint.elements(Window):
        if window.room_id != room.id:
            continue
        aperture = room.apertures[window.aperture_index]
        box = room.aperture_boxes[window.aperture_index]
        assert aperture.sill == 0.0
        assert box.mins.z == room.floor_z
        assert box.maxs.z - room.floor_z >= TRAVERSE_TOP


def test_add_window_refuses_a_hole_above_the_traversal_channel() -> None:
    """The exact call that shipped the dead windows, now refused.

    ``height=48`` with the old 48-unit sill is what the recipe asked for, and
    it produced a barricade over a hole starting above the channel.
    """
    from zmforge.blueprint.model import traverse_is_blocked

    blueprint = three_room_map("zm_forge_gate")
    room = blueprint.find("start_room")
    with pytest.raises(BlueprintError) as raised:
        blueprint.add_window(
            "start", room, Side.EAST, 180.0, height=48.0, sill=48.0, id="dead"
        )
    assert "traversal brush" in str(raised.value)
    assert "cut_opening()" in str(raised.value)

    # Each way of burying the channel is named, not lumped together.
    assert "sill" in (traverse_is_blocked(96.0, 112.0, 48.0) or "")
    assert "tall" in (traverse_is_blocked(96.0, 32.0, 0.0) or "")
    assert "wide" in (traverse_is_blocked(40.0, 112.0, 0.0) or "")
    assert traverse_is_blocked(96.0, 112.0, 0.0) is None


def test_z8_fires_on_a_barricade_over_an_unreachable_hole() -> None:
    """A hand-built blueprint can still get there, so the checker says so."""
    blueprint = three_room_map("zm_forge_gate")
    window = blueprint.elements(Window)[0]
    room = blueprint.find(window.room_id)
    aperture = room.apertures[window.aperture_index]
    room.apertures[window.aperture_index] = replace(aperture, sill=48.0, height=48.0)
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z8"]
    assert [f.element_id for f in errors] == [window.id]
    assert "sill" in errors[0].message


def test_a_plain_hole_is_still_a_plain_hole() -> None:
    """cut_opening is the gap-to-see-through API and is not policed.

    A window means a working entry point; a hole that is only a hole is a
    different intent and keeps working, sill and all.
    """
    blueprint = three_room_map("zm_forge_gate")
    room = blueprint.find("start_room")
    before = len(blueprint.elements(Window))
    opening = blueprint.cut_opening(
        room, Aperture(side=Side.EAST, width=48.0, height=32.0, sill=64.0, offset=180.0)
    )
    assert room.apertures[opening.index].sill == 64.0
    assert len(blueprint.elements(Window)) == before  # no barricade, no riser


# --------------------------------------------------------------------------
# Z9, Z10, Z13, Z14
# --------------------------------------------------------------------------
def test_z9_every_placed_machine_has_its_module(committed) -> None:
    """A machine without its ``#using`` line has no logic at all."""
    from zmforge.blueprint.catalogue import PERKS

    models = {e.value("model") for e in committed["document"].entities_of("misc_prefab")}
    for perk in PERKS:
        if perk.prefab in models and perk.module:
            assert f"#using {perk.module};" in committed["server"]


def test_z9_fires_when_a_module_is_missing(committed) -> None:
    stripped = committed["server"].replace(
        "#using scripts\\zm\\_zm_pack_a_punch;\n", ""
    )
    report = check_gameplay(committed["document"], stripped)
    assert any(f.code == "Z9" for f in report.errors)


def _perk_modules_in(script: str) -> set[str]:
    from zmforge.blueprint.catalogue import PERKS

    return {
        perk.module
        for perk in PERKS
        if perk.module and f"#using {perk.module};" in script
    }


def test_z9_both_scripts_carry_the_same_perk_modules(committed) -> None:
    """The client half of a perk is not optional.

    Treyarch's own map names every perk module in both scripts
    (``zm_giant.gsc:30-38`` against ``zm_giant.csc:21-28``), and each of
    those modules has a ``.csc`` beside its ``.gsc`` in the mod tools' raw
    scripts: the client half is where the perk registers its clientfields,
    its HUD callbacks and its machine effect
    (``_zm_perk_juggernaut.csc:20-30``), so the generator must write them
    into the client script and not into the server script only.  What a
    missing client half looks like in game is unverified.
    """
    server = _perk_modules_in(committed["server"])
    assert server, "the fixture places no perk machines"
    assert _perk_modules_in(committed["client"]) == server


def test_z9_fires_when_the_client_script_is_missing_a_module(committed) -> None:
    stripped = committed["client"].replace(
        "#using scripts\\zm\\_zm_pack_a_punch;\n", ""
    )
    report = check_gameplay(
        committed["document"], committed["server"], client_script=stripped
    )
    assert any(
        f.code == "Z9" and "client script is missing" in f.message
        for f in report.errors
    )


def test_z9_fires_when_only_the_client_script_carries_a_module(committed) -> None:
    """The mismatch either way: it is the disagreement that is the bug."""
    stripped = committed["server"].replace(
        "#using scripts\\zm\\_zm_pack_a_punch;\n", ""
    )
    report = check_gameplay(
        committed["document"], stripped, client_script=committed["client"]
    )
    assert any(
        f.code == "Z9" and "the server script does not" in f.message
        for f in report.errors
    )


def test_z10_statement_order_in_main(committed) -> None:
    """Item E6: after the framework entry, the dog default has already applied."""
    script = committed["server"]
    dog = script.index("level.dog_rounds_allowed")
    entry = script.index("zm_usermap::main()")
    hook = script.index("level.zone_manager_init_func")
    first_zone = script.index("init_zones[0]")
    manage = script.index("zm_zonemgr::manage_zones")
    assert dog < entry < hook < first_zone < manage
    assert "level.dog_rounds_allowed = 0;" in script


def test_z10_fires_when_the_dog_flag_comes_too_late() -> None:
    script = (
        "zm_usermap::main();\n"
        "level.dog_rounds_allowed = 0;\n"
        "level.zone_manager_init_func = &connect_zones;\n"
        'init_zones[0] = "start";\n'
        "level thread zm_zonemgr::manage_zones( init_zones );\n"
    )
    assert any(f.code == "Z10" for f in check_server_script(script).errors)


def test_z11_lighting_and_visibility_entities(committed) -> None:
    document = committed["document"]
    assert len(document.entities_of("volume_sun")) == 1
    assert len(document.entities_of("umbra_volume")) == 1
    world = document.worldspawn
    sky = [
        solid
        for solid in world.solids
        if getattr(solid, "facets", None)
        and all(f.material == "sky" for f in solid.facets)
    ]
    assert len(sky) == 6
    lights = document.entities_of("light")
    assert len(lights) >= 3
    for light in lights:
        assert light.value("PRIMARY_TYPE") == "PRIMARY_OMNI"


def test_z12_every_material_is_catalogued_or_reported(committed) -> None:
    """A missing material still compiles (exit 0), so only the log ever says so."""
    from zmforge.materials import is_catalogued

    report = check_gameplay(committed["document"], committed["server"])
    assert [f for f in report.findings if f.code == "Z12"] == []

    names = set()
    for entity in committed["document"].entities:
        for solid in entity.solids:
            for facet in getattr(solid, "facets", ()):
                names.add(facet.material)
            if hasattr(solid, "grid"):
                names.add(solid.material)
    assert names
    assert all(is_catalogued(name) for name in names), sorted(
        n for n in names if not is_catalogued(n)
    )


def test_z12_strict_mode_turns_an_unknown_material_into_an_error(committed) -> None:
    report = check_gameplay(
        committed["document"], committed["server"], strict_materials=True
    )
    assert report.errors == []

    from zmforge.materials import Material
    from zmforge.verify.files import _check_face_materials
    from zmforge.verify.report import Report

    document = parse_map_text(committed["map_text"])
    document.worldspawn.solids[0].facets[0].material = "not_a_real_material"
    strict = Report()
    _check_face_materials(document, strict, True)
    assert any(f.code == "Z12" for f in strict.errors)


def test_z13_client_script_calls_the_framework_entry(committed) -> None:
    """Item E11: without it the join is dropped on a clientfield mismatch."""
    assert check_client_script(committed["client"]).errors == []
    assert "zm_usermap::main();" in committed["client"]


def test_z13_fires_on_an_empty_client_main() -> None:
    assert check_client_script("function main()\n{\n}\n").errors


def test_z14_manifest_carries_the_six_lines_the_linker_needs(committed) -> None:
    assert check_manifest(committed["manifest"], MAP_NAME).errors == []
    for entry in (
        ">class,zm_mod_level",
        ">group,modtools",
        f"col_map,maps/zm/{MAP_NAME}.d3dbsp",
        f"gfx_map,maps/zm/{MAP_NAME}.d3dbsp",
        f"scriptparsetree,scripts/zm/{MAP_NAME}.gsc",
        f"scriptparsetree,scripts/zm/{MAP_NAME}.csc",
    ):
        assert entry in committed["manifest"]


def test_z14_fires_on_a_manifest_missing_the_bsp(committed) -> None:
    assert check_manifest(">class,zm_mod_level\n", MAP_NAME).errors


# --------------------------------------------------------------------------
# Determinism and the commit contract
# --------------------------------------------------------------------------
def test_the_same_inputs_produce_the_same_bytes(tmp_path) -> None:
    """Ids seed the GUIDs, so a re-run is a no-op diff (spec 8.3)."""
    texts = []
    for index in range(2):
        root = tmp_path / f"run{index}"
        project = Project.create(MAP_NAME, root, blueprint=three_room_map(MAP_NAME))
        project.commit()
        texts.append(project.paths()["map"].read_text(encoding="utf-8"))
    assert texts[0] == texts[1]


def test_commit_refuses_to_write_a_model_with_errors(tmp_path) -> None:
    """A map that fails these checks costs a build plus a session to find out."""
    from zmforge.blueprint.model import Blueprint

    blueprint = Blueprint(MAP_NAME)
    project = Project.create(MAP_NAME, tmp_path, blueprint=blueprint)
    result = project.commit()
    assert not result.ok
    assert result.written == []
    assert not project.paths()["map"].exists()


def test_commit_leaves_a_hand_edited_file_alone(tmp_path) -> None:
    """Spec 5.3: the mapper's edits are not the generator's to discard."""
    project = Project.create(MAP_NAME, tmp_path, blueprint=three_room_map(MAP_NAME))
    project.commit()
    script_path = project.paths()["server_script"]
    script_path.write_text("// mine\n", encoding="utf-8")

    second = Project.create(
        MAP_NAME, tmp_path, blueprint=three_room_map(MAP_NAME), overwrite=True
    )
    result = second.commit()
    assert str(script_path) in result.skipped
    assert script_path.read_text(encoding="utf-8") == "// mine\n"
    assert any(f.code == "hand_edited" for f in result.report.warnings)


def test_map_name_must_be_a_legal_asset_name(tmp_path) -> None:
    from zmforge.errors import ForgeError

    with pytest.raises(ForgeError, match="zm_"):
        Project.create("Not A Map", tmp_path)


# --------------------------------------------------------------------------
# Sealed openings, rooms outside every zone, and machines off the floor
# --------------------------------------------------------------------------
def test_a_sealed_opening_is_a_pane_of_collision_in_the_hole() -> None:
    """The hole stays open to the eye; the pane stops the body."""
    blueprint = one_room_map("zm_forge_cell")
    room = blueprint.find("room")
    opening = blueprint.cut_opening(
        room, Aperture(side=Side.EAST, width=64.0, height=48.0, sill=40.0)
    )
    pane = blueprint.seal_opening(opening)

    assert pane.bounds == opening.box
    assert pane.solids[0].material_names == {"clip"}
    assert pane.note == SEALED_OPENING
    # A pane with no door in it is not a complaint.
    report = check_blueprint(blueprint)
    assert [f for f in report.findings if f.code == "Z7"] == []


def test_z32_refuses_the_hide_pieces_barricade_prefab() -> None:
    """That prefab has no full-height player clip, so the hole stays open."""
    from zmforge.blueprint.catalogue import BARRICADE_PREFAB_HIDE_DEBRIS

    blueprint = three_room_map(MAP_NAME)
    window = next(iter(blueprint.elements(Window)))
    assert check_blueprint(blueprint).codes().isdisjoint({"Z32"})

    object.__setattr__(window, "prefab", BARRICADE_PREFAB_HIDE_DEBRIS)
    report = check_blueprint(blueprint)
    assert [f.code for f in report.errors].count("Z32") == 1


def test_z31_warns_when_a_pane_is_filled_with_a_tool_material() -> None:
    """clip draws nothing, so the hole looks exactly like a broken one."""
    blueprint = three_room_map(MAP_NAME)
    opening = blueprint.find("arena_room").opening(1)
    pane = blueprint.seal_opening(opening)

    report = check_blueprint(blueprint)
    hits = [f for f in report.findings if f.code == "Z31"]
    assert [f.element_id for f in hits] == [pane.id]
    assert all(not f.is_error for f in hits)


def test_z31_is_quiet_when_the_pane_is_meant_to_be_seen() -> None:
    blueprint = three_room_map(MAP_NAME)
    opening = blueprint.find("arena_room").opening(1)
    blueprint.seal_opening(opening, material="t7_wood_planks_worn")

    report = check_blueprint(blueprint)
    assert [f for f in report.findings if f.code == "Z31"] == []


def test_z7_fires_on_a_door_hung_in_a_sealed_opening() -> None:
    """The pane does not move, so the money buys an animation and nothing else."""
    blueprint = three_room_map(MAP_NAME)
    opening = blueprint.find("arena_room").opening(1)
    blueprint.seal_opening(opening)
    blueprint.add_door(("arena", "vault"), opening, price=500, flag="enter_the_pane")

    report = check_blueprint(blueprint)
    assert [f.code for f in report.errors].count("Z7") == 1


def test_z3_warns_about_a_room_no_zone_volume_covers() -> None:
    """A room outside every zone never activates -- deliberate or not."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.add_room(
        Bounds.between((1400, -200, 0), (1700, 200, 256)), wall=16.0, id="sealed_room"
    )
    blueprint.place_light(Point(1550.0, 0.0, 200.0), id="sealed_light")

    report = check_blueprint(blueprint)
    hits = [f for f in report.findings if f.code == "Z3" and f.element_id == "sealed_room"]
    assert len(hits) == 1 and not hits[0].is_error
    # The zoned rooms of the fixture say nothing.
    assert len(
        [f for f in report.findings if f.code == "Z3" and f.element_id != "sealed_room"]
    ) == 0


# --------------------------------------------------------------------------
# Z18: playable-area coverage
# --------------------------------------------------------------------------
def _two_rooms_with_a_doorway(name: str = "zm_forge_gap"):
    """Two rooms sharing a wall, with a doorway cut through both sides of it."""
    blueprint = Blueprint(name)
    west = blueprint.add_room(
        Bounds.between((0, 0, 0), (512, 512, 256)), wall=16.0, id="west"
    )
    east = blueprint.add_room(
        Bounds.between((512, 0, 0), (1024, 512, 256)), wall=16.0, id="east"
    )
    blueprint.cut_opening(west, Aperture(side=Side.EAST, width=80.0, height=96.0))
    blueprint.cut_opening(east, Aperture(side=Side.WEST, width=80.0, height=96.0))
    return blueprint, west, east


def test_z18_finds_the_dead_band_two_interior_zone_volumes_leave() -> None:
    """The bug this check exists for, on the smallest map that has it.

    Volumes sized to the room interiors stop at the inside face of each wall,
    so the 32 units of wall the two rooms share -- and the doorway through it
    -- is in no volume.  The player is 30 units across, so in the middle of
    that band nothing is touched, ``in_enabled_playable_area`` is false and
    the monitor in ``_zm.gsc`` kills the player outright.
    """
    blueprint, west, east = _two_rooms_with_a_doorway()
    blueprint.add_zone("west", west.interior, starting=True)
    blueprint.add_zone("east", east.interior)

    hits = [f for f in check_blueprint(blueprint).findings if f.code == "Z18"]
    assert hits and all(f.is_error for f in hits)
    assert {f.element_id for f in hits} == {"west", "east"}
    assert "touches no player_volume" in hits[0].message
    # The band is the two wall thicknesses less the player's hull: 2 units
    # across the 80-unit doorway, on each room's side of the wall line.
    assert sum(float(re.search(r"has (\d+) square", f.message).group(1)) for f in hits) == 160


def test_z18_is_quiet_when_the_volumes_cover_the_walls() -> None:
    """What ``add_zone`` writes now: the room's outer box, walls included."""
    blueprint, west, east = _two_rooms_with_a_doorway()
    blueprint.add_zone("west", west, starting=True)
    blueprint.add_zone("east", east)
    assert [f for f in check_blueprint(blueprint).findings if f.code == "Z18"] == []


def test_a_zone_from_a_room_is_the_rooms_outer_box() -> None:
    blueprint, west, _east = _two_rooms_with_a_doorway()
    zone = blueprint.add_zone("west", west, starting=True)
    assert zone.bounds.as_tuples() == west.outer.as_tuples()


def test_z18_finds_a_walkable_slab_laid_in_the_gap() -> None:
    """``bridge_threshold`` in one map: a deck inside the wall band.

    A step between two rooms is a surface the map asks the player to stand
    on, and with interior-sized volumes it was entirely out of bounds.
    """
    blueprint, west, east = _two_rooms_with_a_doorway()
    blueprint.add_zone("west", west.interior, starting=True)
    blueprint.add_zone("east", east.interior)
    blueprint.add_slab(
        Bounds.between((480, 200, 0), (544, 320, 16)), 16.0, 16.0,
        "t7_concrete_trowelled", id="threshold_step",
    )
    hits = [
        f
        for f in check_blueprint(blueprint).findings
        if f.code == "Z18" and f.element_id == "threshold_step"
    ]
    assert len(hits) == 1 and hits[0].is_error


def test_z18_says_nothing_about_a_room_nobody_can_stand_in() -> None:
    """A room the map declares unreachable needs no volume over it."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.add_room(
        Bounds.between((1400, -200, 0), (1700, 200, 256)),
        wall=16.0,
        reachable=False,
        id="sealed_room",
    )
    blueprint.place_light(Point(1550.0, 0.0, 200.0), id="sealed_light")
    report = check_blueprint(blueprint)
    # Z46 excluded: it prints one warning per surface the map declares out of
    # reach, on purpose, so that a deliberate exception is a line in the
    # report rather than an absence of one. This room is exactly that.
    assert [
        f
        for f in report.findings
        if f.element_id == "sealed_room" and f.code != "Z46"
    ] == []


def test_z18_is_quiet_on_the_three_room_fixture() -> None:
    assert [
        f for f in check_blueprint(three_room_map(MAP_NAME)).findings if f.code == "Z18"
    ] == []


def test_z9_says_nothing_about_a_machine_on_a_platform_you_can_reach() -> None:
    """An upper floor is a floor: placing on one is not a complaint."""
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    top = arena.floor_z + 192.0
    blueprint.add_slab(
        Bounds.between((200, -200, 0), (400, 0, 16)),
        top,
        16.0,
        "t7_concrete_trowelled",
        id="mezzanine",
    )
    blueprint.place_perk(
        "stamin_up", Point(300.0, -100.0, top), Facing.SOUTH, id="upstairs_perk"
    )
    assert [f for f in check_blueprint(blueprint).findings if f.code == "Z9"] == []


def test_z9_warns_about_a_machine_on_a_platform_declared_unreachable() -> None:
    """The ledge with no way up is a decision, so the map declares it."""
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    top = arena.floor_z + 288.0
    blueprint.add_slab(
        Bounds.between((200, -200, 0), (400, 0, 16)),
        top,
        16.0,
        "t7_concrete_trowelled",
        reachable=False,
        id="ledge",
    )
    blueprint.place_perk(
        "stamin_up", Point(300.0, -100.0, top), Facing.SOUTH, id="ledge_perk"
    )

    hits = [
        f
        for f in check_blueprint(blueprint).findings
        if f.code == "Z9" and "no route onto it" in f.message
    ]
    assert len(hits) == 1
    assert hits[0].element_id == "ledge_perk" and not hits[0].is_error


def test_z9_warns_about_a_machine_over_no_floor_at_all() -> None:
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_perk(
        "deadshot", Point(6000.0, 6000.0, 16.0), Facing.SOUTH, id="void_perk"
    )
    hits = [f for f in check_blueprint(blueprint).findings if f.code == "Z9"]
    assert len(hits) == 1 and hits[0].element_id == "void_perk"
    assert "over no room, yard, terrain or platform" in hits[0].message


def test_a_spawn_can_stand_on_an_upper_floor() -> None:
    """Before platforms counted as ground, an upstairs riser was unplaceable."""
    blueprint = three_room_map(MAP_NAME)
    arena = blueprint.find("arena_room")
    top = arena.floor_z + 192.0
    blueprint.add_slab(
        Bounds.between((200, -400, 0), (600, 0, 16)),
        top,
        16.0,
        "t7_concrete_trowelled",
        id="upper_floor",
    )
    upstairs = blueprint.add_riser(
        "arena", Point(400.0, -200.0, top), Facing.NORTH, id="upstairs_riser"
    )
    assert upstairs.position.z == top
    # and the ground floor underneath still resolves to the room's own floor
    downstairs = blueprint.ground_under(400.0, -200.0, below=arena.floor_z)
    assert downstairs.z == arena.floor_z
    assert [f for f in check_blueprint(blueprint).findings if f.code == "Z6"] == []


def test_w2_rejects_a_doorway_narrower_than_the_player() -> None:
    blueprint = one_room_map("zm_forge_cell")
    room = blueprint.find("room")
    blueprint.cut_opening(room, Aperture(side=Side.EAST, width=24.0, height=96.0))
    report = check_blueprint(blueprint)
    assert [f.code for f in report.errors].count("W2") == 1


def test_w2_warns_about_a_single_file_doorway_and_a_niche() -> None:
    blueprint = one_room_map("zm_forge_cell")
    room = blueprint.find("room")
    blueprint.cut_opening(room, Aperture(side=Side.EAST, width=40.0, height=96.0))
    report = check_blueprint(blueprint)
    single_file = [f for f in report.findings if f.code == "W2"]
    assert len(single_file) == 1 and not single_file[0].is_error
    assert "single file at best" in single_file[0].message


def test_w2_is_quiet_at_the_width_we_call_the_minimum() -> None:
    blueprint = one_room_map("zm_forge_cell")
    room = blueprint.find("room")
    blueprint.cut_opening(
        room, Aperture(side=Side.EAST, width=SINGLE_FILE_WIDTH, height=96.0)
    )
    assert [f for f in check_blueprint(blueprint).findings if f.code == "W2"] == []


# --------------------------------------------------------------------------
# Z1, player slots
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def eight_player(tmp_path_factory):
    """The same fixture, asked for eight slots instead of four."""
    root = tmp_path_factory.mktemp("tools_root_8p")
    name = "zm_forge_eight"
    project = Project.create(
        name, root, blueprint=three_room_map(name, player_slots=8)
    )
    result = project.commit()
    paths = project.paths()
    return {
        "result": result,
        "map_text": paths["map"].read_text(encoding="utf-8"),
        "document": parse_map_text(paths["map"].read_text(encoding="utf-8")),
        "server": paths["server_script"].read_text(encoding="utf-8"),
    }


def test_z1_eight_slots_commit_with_no_errors(eight_player) -> None:
    assert eight_player["result"].report.errors == [], [
        str(f) for f in eight_player["result"].report.errors
    ]


def test_z1_eight_slots_emit_eight_distinct_initial_spawn_structs(eight_player) -> None:
    """What a higher-player mod reads: struct *n* is where player *n* lands.

    ``zm::getfreespawnpoint`` returns ``spawnpoints[ j ]`` where
    ``en_num == player.playernum``, and ``spawnpoints[ 0 ]`` when the index
    runs off the end, so slots short of the player count stack everyone past
    the fourth on one point.
    """
    initial = _structs(
        eight_player["document"],
        targetname="initial_spawn_points",
        script_noteworthy="initial_spawn",
    )
    assert len(initial) == 8
    assert [e.value("script_int") for e in initial] == [None] * 8
    origins = [_origin(e) for e in initial]
    assert len({(p.x, p.y, p.z) for p in origins}) == 8
    for index, left in enumerate(origins):
        for right in origins[index + 1 :]:
            assert left.distance_to(right) >= 32.0
    for entity in initial:
        assert "zclassic_start_room" in entity.value("script_string").split()


def test_z1_the_respawn_set_does_not_grow_with_the_slot_count(committed, eight_player) -> None:
    """One ``player_respawn_point`` per zone however many players; only its
    group grows, to a point per player (``blueprint.respawn.group_size``)."""
    four = _structs(committed["document"], targetname="player_respawn_point")
    eight = _structs(eight_player["document"], targetname="player_respawn_point")
    assert len(eight) == len(four)
    for entity in eight:
        assert len(_structs(eight_player["document"], targetname=entity.value("target"))) == 8


def test_z1_eight_slots_change_nothing_else_in_the_map(committed, eight_player) -> None:
    """Everything a four-player game reads is untouched by the extra slots.

    The two maps differ by their name, their GUIDs, four spawn structs and
    four more points in each zone's respawn group, and by nothing else, so a
    map built for eight is still the four-player map it would otherwise have
    been.
    """
    def shape(document):
        return [
            (e.classname, e.value("targetname"), e.value("script_noteworthy"))
            for e in document.entities
            if e.value("targetname") != "initial_spawn_points"
            and not (e.value("targetname") or "").endswith("_respawn_points")
        ]

    assert shape(eight_player["document"]) == shape(committed["document"])


def test_z1_four_slots_sit_exactly_where_they_did_before_the_option(committed) -> None:
    """The default is the known-good arrangement, not a re-derivation of it."""
    origins = sorted(
        _origin(e).y
        for e in _structs(
            committed["document"],
            targetname="initial_spawn_points",
            script_noteworthy="initial_spawn",
        )
    )
    assert origins == [-48.0, -16.0, 16.0, 48.0]


def test_z1_pinning_the_slot_count_fires_on_a_map_built_for_four(committed) -> None:
    report = check_gameplay(
        committed["document"], committed["server"], player_slots=8
    )
    assert "Z1" in [f.code for f in report.errors]
    assert (
        check_gameplay(
            committed["document"], committed["server"], player_slots=4
        ).errors
        == []
    )


def test_z51_the_extra_seats_register_their_fields_before_the_framework_entry(
    eight_player,
) -> None:
    """The map that crashed, and the line that crashed it.

    ``zm_dmv`` built for eight seats linked clean and the game refused it at
    load: *Attempt to register ClientField laststand_update4 post finalization
    of ClientField registration period failed*.  The
    entry yields -- ``zm_usermap::main()`` -> ``load::main()``
    (``zm/_load.gsc:77``) -> ``system::wait_till( "all" )`` (``:105``) -- and
    the engine closes the registration period while it waits
    (``callbacks_shared.gsc:539-546``), so every registration has to be above
    that call.  **Unverified in game:** what is measured is the crash, not the
    fix.
    """
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    for text in (render_server_script(plan), render_client_script(plan)):
        entry = text.index("zm_usermap::main();")
        assert "clientfield::register" in text
        assert text.rindex("clientfield::register") < entry
        # and the array bookkeeping is still on the far side of the entry,
        # because the entry is what assigns those arrays empty
        assert text.rindex('"laststand_update" + i;') > entry


def test_z51_is_quiet_on_the_map_it_was_written_for(eight_player) -> None:
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    report = check_gameplay(
        eight_player["document"],
        render_server_script(plan),
        client_script=render_client_script(plan),
        player_slots=8,
    )
    assert [f for f in report.errors if f.code == "Z51"] == []


def test_z51_refuses_a_registration_written_after_the_entry(eight_player) -> None:
    """One line moved below the entry call is the whole defect."""
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    server = render_server_script(plan).replace(
        "\tzm_usermap::main();",
        '\tzm_usermap::main();\n\tclientfield::register( "world", '
        '"zmf_probe", VERSION_SHIP, 1, "int" );',
        1,
    )
    report = check_gameplay(
        eight_player["document"],
        server,
        client_script=render_client_script(plan),
        player_slots=8,
    )
    assert "Z51" in [f.code for f in report.errors]


def test_z52_an_eight_seat_map_registers_the_same_fields_on_both_sides() -> None:
    """The disconnect this was written against, and the lists that fix it.

    ``zm_dmv`` built for eight seats was refused in a solo game with
    "Server Disconnected - Clientfield Mismatch": the
    server registered six ``clientuimodel`` score fields per extra seat and
    the client none.  Both lists are parsed out of the emitted text and have
    to be identical, entry for entry, loop bound included.
    """
    from zmforge.verify.files import clientfield_registrations

    plan = three_room_map("zm_forge_eight", player_slots=8).script
    server = clientfield_registrations(render_server_script(plan))
    client = clientfield_registrations(render_client_script(plan))
    assert server == client
    # one last-stand field and the six score fields, per extra seat
    assert len(server) == 7
    assert {entry[0] for entry in server} == {"for ( i = 4; i < 8; i++ )"}
    assert sum('"clientuimodel"' == entry[1] for entry in server) == 6


def test_z52_is_quiet_on_the_eight_seat_map(eight_player) -> None:
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    report = check_gameplay(
        eight_player["document"],
        render_server_script(plan),
        client_script=render_client_script(plan),
        player_slots=8,
    )
    assert [f for f in report.errors if f.code == "Z52"] == []


def test_z52_refuses_the_server_only_score_fields_that_disconnected_zm_dmv(
    eight_player,
) -> None:
    """The shipped defect: the client half of the score fields missing."""
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    client = "\n".join(
        line
        for line in render_client_script(plan).split("\n")
        if ".score_cf_" not in line
    )
    report = check_gameplay(
        eight_player["document"],
        render_server_script(plan),
        client_script=client,
        player_slots=8,
    )
    assert "Z52" in [f.code for f in report.errors]


@pytest.mark.parametrize(
    "old, new",
    [
        # a different bit count on one side
        ("GetMinBitCountForNum( 7 )", "GetMinBitCountForNum( 3 )"),
        # a different loop bound: the same text, two more fields
        ("i < 8;", "i < 10;"),
        # a different type
        ('.score_cf_damage", VERSION_SHIP, GetMinBitCountForNum( 7 ), "counter"',
         '.score_cf_damage", VERSION_SHIP, GetMinBitCountForNum( 7 ), "int"'),
    ],
)
def test_z52_refuses_a_one_sided_difference(eight_player, old, new) -> None:
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    client = render_client_script(plan)
    assert old in client
    report = check_gameplay(
        eight_player["document"],
        render_server_script(plan),
        client_script=client.replace(old, new),
        player_slots=8,
    )
    assert "Z52" in [f.code for f in report.errors]


def test_z52_refuses_a_reordered_pair(eight_player) -> None:
    """Same set, different order: the check compares lists, not sets."""
    plan = three_room_map("zm_forge_eight", player_slots=8).script
    client = render_client_script(plan)
    first = next(l for l in client.split("\n") if ".score_cf_damage" in l)
    second = next(l for l in client.split("\n") if ".score_cf_death_melee" in l)
    swapped = client.replace(first, "\0").replace(second, first).replace("\0", second)
    report = check_gameplay(
        eight_player["document"],
        render_server_script(plan),
        client_script=swapped,
        player_slots=8,
    )
    assert "Z52" in [f.code for f in report.errors]


def test_z1_fires_on_fewer_slots_than_a_stock_game_seats() -> None:
    blueprint = three_room_map("zm_forge_thin", player_slots=2)
    codes = [f.code for f in check_blueprint(blueprint).errors]
    assert "Z1" in codes


def test_z1_fires_when_a_slot_hangs_off_the_floor() -> None:
    """The check is per slot, so a wide set over a small room is caught."""
    blueprint = one_room_map("zm_forge_tight")
    start = blueprint.elements(PlayerStart)[0]
    blueprint.set_player_start(
        start.position, start.facing, spread=512.0, slots=8, id="wide_start"
    )
    messages = [str(f) for f in check_blueprint(blueprint).errors if f.code == "Z1"]
    assert any("not over any floor" in m for m in messages)


# --------------------------------------------------------------------------
# Z26, the framework's own player-count check
# --------------------------------------------------------------------------
_CAP_OFF = "level.player_too_many_players_check = false;"


def test_z26_eight_slots_turn_the_player_count_check_off(eight_player) -> None:
    """The structs are useless without it.

    ``_zm.gsc:7067 player_too_many_players_check`` takes ``max_players = 4``
    outside ``zgrief``/``zmeat`` and, above that, freezes the players and
    notifies ``end_game``.  ``_zm.gsc:1865`` threads it out of
    ``onPlayerSpawned``, so the fifth player to spawn ends the match.
    """
    assert _CAP_OFF in eight_player["server"]


def test_z26_the_statement_lands_after_the_framework_entry(eight_player) -> None:
    """Before the entry it is overwritten and the map is back to four.

    ``zm::init()`` assigns the variable ``true`` at ``_zm.gsc:252``, and the
    entry reaches it synchronously: ``zm_usermap::main()`` calls
    ``load::main()``, which calls ``zm::init()`` (``_load.gsc:79``).  The read
    is on spawn, so after the entry is the only window.
    """
    script = eight_player["server"]
    assert script.index("zm_usermap::main()") < script.index(_CAP_OFF)


def test_z26_a_four_slot_map_says_nothing_about_the_player_count(committed) -> None:
    assert "player_too_many_players_check" not in committed["server"]


def test_z26_fires_on_eight_structs_without_the_statement(eight_player) -> None:
    """The failure the emitter exists to prevent: structs, no statement."""
    stripped = eight_player["server"].replace(_CAP_OFF, "")
    codes = [f.code for f in check_gameplay(eight_player["document"], stripped).errors]
    assert "Z26" in codes


def test_z26_fires_when_the_statement_is_before_the_framework_entry(
    eight_player,
) -> None:
    script = eight_player["server"].replace(_CAP_OFF, "")
    script = script.replace(
        "\tzm_usermap::main();", f"\t{_CAP_OFF}\n\tzm_usermap::main();"
    )
    messages = [
        str(f) for f in check_gameplay(eight_player["document"], script).errors
        if f.code == "Z26"
    ]
    assert any("before the framework entry" in m for m in messages)


def test_z26_does_not_count_a_commented_out_statement(eight_player) -> None:
    script = eight_player["server"].replace(_CAP_OFF, f"// {_CAP_OFF}")
    codes = [f.code for f in check_gameplay(eight_player["document"], script).errors]
    assert "Z26" in codes


def test_z26_passes_a_map_built_for_eight_as_written(eight_player) -> None:
    report = check_gameplay(eight_player["document"], eight_player["server"])
    assert [f for f in report if f.code == "Z26"] == []


def test_z26_warns_on_the_statement_without_the_structs(committed) -> None:
    """A lifted cap and four slots stacks everyone past the fourth on one point."""
    script = committed["server"].replace(
        "\tzm_usermap::main();", f"\tzm_usermap::main();\n\t{_CAP_OFF}"
    )
    report = check_gameplay(committed["document"], script)
    assert report.errors == []
    assert "Z26" in [f.code for f in report]


# --------------------------------------------------------------------------
# Decorative prefabs
# --------------------------------------------------------------------------
#: A real stock prefab path, taken from ``tests/corpus/zm_giant.map``, that
#: this generator attaches no meaning to: nothing in ``verify`` looks for it,
#: so what it does to a map is exactly what ``place_prefab`` does and nothing
#: else.  Nobody has opened it either, so it is also the example of a model
#: whose front at yaw 0 is unknown: ``Z23`` warns about the guess the emitter
#: has to make for it, on every heading, until someone reads it on the install.
SCENERY_PREFAB = "_prefabs/zm/zm_giant/geo/trap_switch_01.map"
SCENERY_POSITION = Point(-256.0, 96.0, 16.0)
SCENERY_FACING = Facing.SOUTH
#: A stock prefab that *has* been read on the install, so the emitter knows its
#: front and nothing has to be guessed.  The mystery box's stand faces north at
#: yaw 0 (spec appendix B), which is not the majority heading, so a test that
#: uses it would fail if the per-model table were ignored.
MEASURED_SCENERY_PREFAB = "_prefabs/zm/zm_core/buyable_magic_box_start.map"


def _commit_three_rooms(root, *, prefab: bool, yaw: float | None = None):
    """The fixture map, with and without one decorative prefab in it."""
    blueprint = three_room_map(MAP_NAME)
    if prefab:
        blueprint.place_prefab(
            SCENERY_PREFAB, SCENERY_POSITION, SCENERY_FACING, yaw=yaw, id="scenery"
        )
    project = Project.create(MAP_NAME, root, blueprint=blueprint)
    result = project.commit()
    return blueprint, project, result


def test_a_placed_prefab_is_one_misc_prefab_at_the_prefab_yaw(tmp_path) -> None:
    """The generic form of ``place_perk``: model, origin, angles, no more."""
    from zmforge.blueprint.catalogue import UNMEASURED_PREFAB_FRONT_ZERO, prefab_yaw

    _, project, _ = _commit_three_rooms(tmp_path / "scenery", prefab=True)
    document = parse_map_text(project.paths()["map"].read_text(encoding="utf-8"))
    placed = [
        e
        for e in document.entities_of("misc_prefab")
        if e.value("model") == SCENERY_PREFAB
    ]
    assert len(placed) == 1
    assert _origin(placed[0]) == SCENERY_POSITION
    expected = prefab_yaw(SCENERY_FACING, UNMEASURED_PREFAB_FRONT_ZERO)
    assert placed[0].value("angles") == f"0 {expected:g} 0"
    # the same key set a perk machine's prefab entity carries, and no other
    machines = [
        e
        for e in document.entities_of("misc_prefab")
        if "vending" in (e.value("model") or "")
    ]
    assert machines, "the fixture places perk machines"
    assert [key for key, _ in placed[0].pairs] == [key for key, _ in machines[0].pairs]
    assert [key for key, _ in placed[0].pairs] == [
        "classname",
        "model",
        "origin",
        "angles",
    ]


def test_a_prefab_nobody_has_opened_warns_on_every_heading(tmp_path) -> None:
    """Z23: the emitter cannot know an unread prefab's front, and says so.

    ``trap_switch_01.map`` is not in ``PREFAB_FRONT_ZERO_BY_MODEL``, so the
    emitter falls back to ``UNMEASURED_PREFAB_FRONT_ZERO``, which is a named
    guess and not a measurement.  A warning rather than an error, because a
    guess that happens to be right is not a defect and the check cannot tell.
    """
    from zmforge import verify

    for heading in (Facing.EAST, Facing.SOUTH):
        blueprint = three_room_map(MAP_NAME)
        blueprint.place_prefab(
            SCENERY_PREFAB, SCENERY_POSITION, heading, id="scenery"
        )
        report = verify.blueprint(blueprint)
        mine = [f for f in report if f.element_id == "scenery"]
        assert [f.code for f in mine] == ["Z23"]
        assert not mine[0].is_error
        assert "nobody has opened" in mine[0].message


def test_a_prefab_that_has_been_read_takes_its_own_front_and_is_silent() -> None:
    """Z23: a measured model is turned counter-clockwise off *its* front.

    East is the heading that separates the three ways this could be wrong.
    The stand's front is north, so east needs yaw 270.  The clockwise turn off
    north gives 90, and the counter-clockwise turn off the majority south
    front gives 90 as well; only reading this model's own row gives 270.
    """
    from zmforge import verify

    blueprint = three_room_map(MAP_NAME)
    blueprint.place_prefab(
        MEASURED_SCENERY_PREFAB, SCENERY_POSITION, Facing.EAST, id="scenery"
    )
    document = build_document(blueprint)
    # The fixture places a mystery box of its own on the same stand model, so
    # pick this one out by where it stands.
    placed = [
        e
        for e in document.entities_of("misc_prefab")
        if e.value("model") == MEASURED_SCENERY_PREFAB
        and _origin(e) == SCENERY_POSITION
    ]
    assert [e.value("angles") for e in placed] == ["0 270 0"]
    assert [f.element_id for f in verify.blueprint(blueprint)].count("scenery") == 0


def test_a_prefab_can_carry_the_one_token_that_wires_it(tmp_path) -> None:
    """``script_string``, in the place ``add_window``'s barricade carries it.

    A barricade is a ``misc_prefab`` whose token is the link tag its riser
    carries, and that string is the whole of the wiring between the two.  With
    no field for it a barricade could be placed only through ``add_window``,
    which digs a yard and a riser of its own -- so a caller that already has the
    hole, the yard and the riser, such as a map document edited by hand,
    could not put the boards back at all.
    """
    from zmforge.blueprint.catalogue import BARRICADE_PREFAB

    blueprint = three_room_map(MAP_NAME)
    blueprint.place_prefab(BARRICADE_PREFAB, SCENERY_POSITION, Facing.NORTH,
                           script_string="a_window_link", id="boards")
    document = build_document(blueprint)
    # The fixture's own barricade windows use the same model, so pick this one
    # out by where it stands.
    placed = [e for e in document.entities_of("misc_prefab")
              if e.value("model") == BARRICADE_PREFAB
              and _origin(e) == SCENERY_POSITION]
    assert len(placed) == 1
    assert placed[0].value("script_string") == "a_window_link"
    # In `add_window`'s own key order, so a barricade written either way is the
    # same entity key for key.
    assert [key for key, _ in placed[0].pairs] == [
        "classname", "model", "script_string", "origin", "angles",
    ]
    # and a prefab with no token is the three-key entity it always was
    plain = three_room_map(MAP_NAME)
    plain.place_prefab(SCENERY_PREFAB, SCENERY_POSITION, Facing.NORTH, id="scenery")
    entity = [e for e in build_document(plain).entities_of("misc_prefab")
              if e.value("model") == SCENERY_PREFAB][0]
    assert [key for key, _ in entity.pairs] == [
        "classname", "model", "origin", "angles",
    ]


def test_a_raw_yaw_overrides_the_facing(tmp_path) -> None:
    """For a prefab whose zero heading the caller has established is not south."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_prefab(
        SCENERY_PREFAB, SCENERY_POSITION, Facing.EAST, yaw=45.0, id="scenery"
    )
    document = build_document(blueprint)
    placed = [
        e
        for e in document.entities_of("misc_prefab")
        if e.value("model") == SCENERY_PREFAB
    ]
    assert [e.value("angles") for e in placed] == ["0 45 0"]


def test_a_placed_prefab_adds_no_script_no_zone_and_no_finding(tmp_path) -> None:
    """Decorative means decorative: the map plays as it did without it."""
    plain_blueprint, plain_project, plain_result = _commit_three_rooms(
        tmp_path / "plain", prefab=False
    )
    # With a raw yaw: the caller has established this prefab's own zero
    # heading, nothing is guessed, and so nothing is reported either.
    blueprint, project, result = _commit_three_rooms(
        tmp_path / "scenery", prefab=True, yaw=0.0
    )

    assert blueprint.script.zones == plain_blueprint.script.zones
    assert blueprint.script.edges == plain_blueprint.script.edges
    assert blueprint.script.perk_modules == plain_blueprint.script.perk_modules
    for role in ("server_script", "client_script", "manifest"):
        assert project.paths()[role].read_text(encoding="utf-8") == plain_project.paths()[
            role
        ].read_text(encoding="utf-8")

    # verify.blueprint and verify.files, as the commit ran them
    assert [str(f) for f in result.report] == [str(f) for f in plain_result.report]
    from zmforge import verify

    assert [str(f) for f in verify.blueprint(blueprint)] == [
        str(f) for f in verify.blueprint(plain_blueprint)
    ]
    assert [str(f) for f in verify.files(project)] == [
        str(f) for f in verify.files(plain_project)
    ]


def test_committing_a_prefab_twice_writes_the_same_bytes(tmp_path) -> None:
    """Ids and GUIDs are derived, so a re-run is byte-identical."""
    _, project, _ = _commit_three_rooms(tmp_path / "once", prefab=True)
    first = project.paths()["map"].read_bytes()
    project.commit()
    assert project.paths()["map"].read_bytes() == first

    _, other, _ = _commit_three_rooms(tmp_path / "again", prefab=True)
    assert other.paths()["map"].read_bytes() == first


# --------------------------------------------------------------------------
# Z10, every assignment
# --------------------------------------------------------------------------
def test_z10_fires_when_the_dog_flag_is_reassigned_after_the_entry() -> None:
    """The generated assignment is in place; a second one after the entry is
    the one that matters, and the check used to stop at the first."""
    script = (
        "function main()\n{\n"
        "\tlevel.dog_rounds_allowed = 0;\n"
        "\tzm_usermap::main();\n"
        "\tlevel.dog_rounds_allowed = 1;\n"
        "\tlevel.zone_manager_init_func = &connect_zones;\n"
        '\tinit_zones[0] = "start";\n'
        "\tlevel thread zm_zonemgr::manage_zones( init_zones );\n}\n"
    )
    late = [f for f in check_server_script(script).errors if f.code == "Z10"]
    assert len(late) == 1
    assert "after the framework entry" in late[0].message


# --------------------------------------------------------------------------
# Spec 2.8 step 8: nothing placed sits inside a world brush
# --------------------------------------------------------------------------
def _pillar_around(blueprint, point: Point, *, height: float = 200.0, walkable=False, id="pillar"):
    return blueprint.add_block(
        Bounds.between(
            (point.x - 40.0, point.y - 70.0, 16.0),
            (point.x + 40.0, point.y + 70.0, height),
        ),
        "t7_concrete_wall_dark_01",
        walkable=walkable,
        id=id,
    )


def test_z1_fires_when_a_spawn_slot_is_inside_a_solid() -> None:
    """Floor under the slot is not enough: a pillar on that floor around it
    left every slot with floor beneath and a brush all round, and passed."""
    blueprint = three_room_map("zm_forge_gate")
    start = blueprint.elements(PlayerStart)[0]
    _pillar_around(blueprint, start.position)
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z1"]
    assert len(errors) == 4, [str(f) for f in errors]
    assert all("inside a world solid" in f.message for f in errors)


def test_z1_fires_for_a_walkable_counter_over_the_slots_too() -> None:
    """A low walkable block is a floor to ground_under and a brush to the
    player standing in it; the check reads it as the brush."""
    blueprint = three_room_map("zm_forge_gate")
    start = blueprint.elements(PlayerStart)[0]
    _pillar_around(blueprint, start.position, height=64.0, walkable=True, id="counter")
    assert any(
        f.code == "Z1" and "inside a world solid" in f.message
        for f in check_blueprint(blueprint).errors
    )


def test_z6_fires_when_a_spawn_struct_is_inside_a_solid() -> None:
    """A riser's origin is on the floor, so a pillar standing on that floor
    contains it only at its bottom face; the probe up the body sees it."""
    blueprint = three_room_map("zm_forge_gate")
    riser = blueprint.find("arena_riser_south")
    _pillar_around(blueprint, riser.position)
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z6"]
    assert [f.element_id for f in errors] == ["arena_riser_south"]


def test_z11_fires_when_a_light_is_inside_a_pier() -> None:
    """Spec 4.11 says a light inside the ceiling lights nothing; a pier is no
    different: a light 18 units into brickwork lights nothing either."""
    blueprint = three_room_map("zm_forge_gate")
    lamp = blueprint.find("start_light")
    blueprint.add_block(
        Bounds.between(
            (lamp.position.x - 24, lamp.position.y - 24, 16.0),
            (lamp.position.x + 24, lamp.position.y + 24, lamp.position.z + 20.0),
        ),
        "t7_concrete_wall_dark_01",
        id="pier",
    )
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z11"]
    assert [f.element_id for f in errors] == ["start_light"]


def test_the_fixture_has_nothing_inside_a_solid(committed) -> None:
    assert not any(
        "inside a world solid" in f.message for f in committed["result"].report.findings
    )


# ==========================================================================
# Z11, lighting intensity and coverage
#
# A large generated map can come out far too dark in game with nothing wrong
# in the bake or the ambient: if every lamp carries "stops" "4", the map is
# too dark, because stops is log2 of an intensity measured against the
# exposure the map's own sun/sky preset sets.  Under ssi default_day, ev 15,
# stops 4 is eleven stops -- 2048x -- under shipped practice.  These tests pin the rule and
# the numbers behind it; the measurements are in zmforge.lighting.
# ==========================================================================


def test_stops_is_log2_of_the_shipped_intensities() -> None:
    """The unit, pinned against the values in zm_giant_light.map.

    If this ever fails, the interpretation of the key is wrong and every
    other number in zmforge.lighting is wrong with it.
    """
    from zmforge.lighting import intensity_of

    for stops, intensity in (
        (3.32192809488736, 10.0),
        (4.64385618977472, 25.0),
        (5.64385618977472, 50.0),
        (6.64385618977473, 100.0),
        (7.96578428466209, 250.0),
        (9.96578428466209, 1000.0),
    ):
        assert abs(intensity_of(stops) - intensity) < 1e-6


def test_a_lamp_takes_its_brightness_from_the_maps_sky_preset() -> None:
    """A lamp that names no stops is emitted at the preset's ev.

    default_day is ev 15 and zm_factory is ev 5, and The Giant's lamps do sit
    around 5 while mp_sector's sit around 15, so the same recipe under a
    night preset has to come out ten stops dimmer without anyone editing a
    lamp.
    """
    from zmforge.lighting import SSI_EXPOSURE

    for preset, expected in (("default_day", 15.0), ("zm_factory", 5.0)):
        blueprint = Blueprint("zm_forge_exposure")
        blueprint.add_room(
            Bounds.between((0.0, 0.0, 0.0), (256.0, 256.0, 256.0)), id="box"
        )
        blueprint.enclose(sun_preset=preset, id="enclosure")
        lamp = blueprint.place_light(Point(128.0, 128.0, 160.0), id="lamp")
        assert SSI_EXPOSURE[preset] == expected
        assert blueprint.exposure == expected
        assert blueprint.stops_of(lamp) == expected


def test_the_brightness_knob_moves_every_lamp_and_nothing_else() -> None:
    """One number, in stops, so +1 is twice the light.

    It is the control a map author turns after judging a bake, which is why it
    has to change the light and not the map's logic.
    """
    from zmforge.emit.mapfile import build_document

    def lit(brightness: float):
        blueprint = three_room_map("zm_forge_gate")
        blueprint.brightness_stops = brightness
        document = build_document(blueprint)
        return document, [
            float(light.value("stops")) for light in document.entities_of("light")
        ]

    base_doc, base = lit(0.0)
    up_doc, up = lit(1.5)
    down_doc, down = lit(-2.0)

    assert base and len(base) == len(up) == len(down)
    assert all(abs((u - b) - 1.5) < 1e-9 for b, u in zip(base, up))
    assert all(abs((d - b) + 2.0) < 1e-9 for b, d in zip(base, down))

    # Nothing but the stops lines differ.
    def without_stops(document) -> list[str]:
        return [
            line
            for line in render_map_text(document).splitlines()
            if not line.startswith('"stops"')
        ]

    assert without_stops(base_doc) == without_stops(up_doc)
    assert without_stops(base_doc) == without_stops(down_doc)


def test_z11_fires_on_the_old_fixed_stops_of_4() -> None:
    """The exact bug, as a regression test.

    stops 4 under default_day draws a map black.  A checker
    that cannot say so is a checker that would let it through again.
    """
    blueprint = three_room_map("zm_forge_gate")
    blueprint.find("start_light").stops = 4.0
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z11"]
    assert [f.element_id for f in errors] == ["start_light"]
    assert "too dark" in errors[0].message
    assert "ev 15" in errors[0].message


def test_z11_fires_on_a_lamp_far_brighter_than_the_shipped_band() -> None:
    blueprint = three_room_map("zm_forge_gate")
    blueprint.find("start_light").stops = 28.0
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z11"]
    assert [f.element_id for f in errors] == ["start_light"]
    assert "too bright" in errors[0].message


def test_z11_accepts_the_whole_band_the_shipped_maps_occupy() -> None:
    """mp_sector runs ev 12.75 with lamps from stops 13 to 17, so a lamp
    between half a stop under its exposure and four and a half over it is
    shipped practice, not a finding."""
    from zmforge.lighting import SHIPPED_STOPS_OVER_EXPOSURE

    low, high = SHIPPED_STOPS_OVER_EXPOSURE
    for over in (low, 0.0, 2.0, high):
        blueprint = three_room_map("zm_forge_gate")
        for lamp in blueprint.elements(Lamp):
            lamp.stops = blueprint.exposure + over
        assert [f for f in check_blueprint(blueprint).errors if f.code == "Z11"] == []


def test_z11_fires_when_one_lamp_is_asked_to_light_a_hall() -> None:
    """A lamp per room was the old rule and it is not enough.

    The Giant carries one lamp per 226 x 226 units of footprint; this arena
    is 864 x 992 with four lamps in it, and stripping it back to one leaves
    most of the floor beyond any of them.
    """
    blueprint = three_room_map("zm_forge_gate")
    arena = blueprint.find("arena_room")
    keep = None
    for lamp in list(blueprint.elements(Lamp)):
        if not arena.interior.holds_flat(lamp.position.x, lamp.position.y):
            continue
        if keep is None:
            keep = lamp
        else:
            blueprint._elements.remove(lamp)
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z11"]
    assert [f.element_id for f in errors] == ["arena_room"]
    assert "light_rooms()" in errors[0].message


def test_light_rooms_covers_every_room_and_is_idempotent() -> None:
    """The fix for the rule above, and it has to be safe to call twice."""
    blueprint = three_room_map("zm_forge_gate")
    before = len(blueprint.elements(Lamp))
    again = blueprint.light_rooms()
    assert again == []  # the recipe already calls it
    assert len(blueprint.elements(Lamp)) == before
    assert [f for f in check_blueprint(blueprint).errors if f.code == "Z11"] == []


def test_light_rooms_never_buries_a_lamp_in_a_solid_or_a_ceiling() -> None:
    """Spec 4.11: a lamp inside a brush lights nothing.  The grid walks a
    room's whole interior, so it will land on piers and stairs."""
    blueprint = three_room_map("zm_forge_gate")
    report = check_blueprint(blueprint)
    assert [f for f in report.errors if f.code == "Z11"] == []
    assert not any("inside a world solid" in f.message for f in report.findings)


def test_the_brightness_knob_is_usable_in_both_directions() -> None:
    """A trim is not a lamp authored wrong, and must not be judged as one.

    The band check first looked at the emitted stops, offset included, so
    `generate --brightness -2` reported 128 errors and refused to write the
    map -- half the knob's range was unusable.  The band judges how each lamp
    is authored; the trim gets one warning for the whole map.
    """
    for trim in (-4.0, -2.0, -1.0, 1.0, 3.0, 6.0):
        blueprint = three_room_map("zm_forge_gate")
        blueprint.brightness_stops = trim
        report = check_blueprint(blueprint)
        assert [f for f in report.errors if f.code == "Z11"] == [], trim
        outside = not (-0.5 <= trim <= 4.5)
        notes = [f for f in report.warnings if f.code == "Z11"]
        assert bool(notes) is outside, (trim, [str(f) for f in notes])
        if outside:
            assert "it is a trim, not a fix" in notes[0].message

    # An authored lamp outside the band is still an error, trim or no trim.
    blueprint = three_room_map("zm_forge_gate")
    blueprint.brightness_stops = 11.0
    blueprint.find("start_light").stops = 4.0
    errors = [f for f in check_blueprint(blueprint).errors if f.code == "Z11"]
    assert [f.element_id for f in errors] == ["start_light"]


# --------------------------------------------------------------------------
# W3: a wall buy has to face the room, not the wall
# --------------------------------------------------------------------------
#: The arena's south wall: interior face at y = -496, wall body to the south
#: of it.  A buy mounted here has to face north.
#:
#: x = 160 and not 300: the fixture
#: puts a buy of its own at x = 320 on the same wall, and two buys 20 units
#: apart draw their chalk through each other.  The standing-room rule
#: (``blueprint/reach.py``, ``Z42``) refuses the second one, so this moved to
#: a clear stretch of the same wall.
WALL_BUY_ON_SOUTH_WALL = Point(160.0, -496.0, 8.0)


def _map_with_one_wall_buy(facing: Facing) -> Blueprint:
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_wall_weapon(
        "ar_standard", WALL_BUY_ON_SOUTH_WALL, facing, id="buy_under_test"
    )
    return blueprint


def test_a_wall_buy_faces_the_room_at_the_measured_yaw() -> None:
    """The stock prefab faces north at yaw 0, so facing north emits yaw 0.

    Measured on the install: the chalk mesh and the weapon struct sit on the
    prefab's ``y = 0`` plane and the mount brush behind it, and cod2map64
    turns the prefab counter-clockwise (see
    ``catalogue.wall_weapon_yaw``).  The old ``prefab_yaw(..., SOUTH)``
    emitted 180 here, which pointed the drawing into the brickwork.
    """
    from zmforge.blueprint.catalogue import wall_weapon_yaw

    expected = {Facing.NORTH: 0.0, Facing.EAST: 270.0, Facing.SOUTH: 180.0, Facing.WEST: 90.0}
    assert {face: wall_weapon_yaw(face) for face in expected} == expected

    document = build_document(_map_with_one_wall_buy(Facing.NORTH))
    placed = [
        e
        for e in document.entities_of("misc_prefab")
        if "spawnable_weapon_ar_standard" in (e.value("model") or "")
        and e.value("origin") == "160 -496 8"
    ]
    assert len(placed) == 1
    assert placed[0].value("angles") == "0 0 0"


def test_a_backwards_wall_buy_is_an_error() -> None:
    """A wall buy aimed into the wall is reported."""
    report = check_blueprint(_map_with_one_wall_buy(Facing.SOUTH))
    aimed_at_the_wall = [
        f
        for f in report.findings
        if f.code == "W3" and f.severity == "error" and f.element_id == "buy_under_test"
    ]
    assert len(aimed_at_the_wall) == 1
    assert "points into a world solid" in aimed_at_the_wall[0].message


def test_a_wall_buy_that_faces_the_room_passes() -> None:
    report = check_blueprint(_map_with_one_wall_buy(Facing.NORTH))
    assert [f for f in report.findings if f.code == "W3"] == []


def test_a_floating_wall_buy_is_flagged() -> None:
    """Nothing behind the mount: the prefab's bracket hangs in mid-air."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_wall_weapon(
        "ar_standard", Point(300.0, 0.0, 8.0), Facing.NORTH, id="buy_in_the_open"
    )
    report = check_blueprint(blueprint)
    floating = [
        f for f in report.findings if f.code == "W3" and f.element_id == "buy_in_the_open"
    ]
    assert len(floating) == 1
    assert "no wall behind it" in floating[0].message


# --------------------------------------------------------------------------
# Z9: a machine has its back to the wall it is against, not its side
# --------------------------------------------------------------------------
#: On the same south wall as the wall buy above -- interior face at y = -496 --
#: 24 units out into the room, which is where every machine in both shipped
#: recipes sits.  A machine here faces north; facing east or west stands it
#: broadside to the wall with 8 units of a 64-wide machine inside it.
MACHINE_ON_SOUTH_WALL = Point(160.0, -472.0, 16.0)


def _map_with_one_machine(facing: Facing, at: Point = MACHINE_ON_SOUTH_WALL) -> Blueprint:
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_perk("juggernog", at, facing, id="machine_under_test")
    return blueprint


def test_a_machine_broadside_to_its_wall_is_an_error() -> None:
    """A pack-a-punch authored perpendicular to its wall.

    ``facing`` is the heading the machine's front points at, so a machine
    against the south wall faces north.  A quarter turn out puts its own
    body through the brickwork and its use prompt along the wall, and every
    other check passes it: the yaw emitted is the one the heading asked for,
    the origin is in open air, and the space in front of it is clear.
    """
    report = check_blueprint(_map_with_one_machine(Facing.EAST))
    sideways = [
        f
        for f in report.findings
        if f.code == "Z9" and f.severity == "error" and f.element_id == "machine_under_test"
    ]
    assert len(sideways) == 1
    assert "stands side-on to the brushwork to its south" in sideways[0].message
    assert "face north" in sideways[0].message


def test_a_machine_that_faces_out_of_its_wall_passes() -> None:
    report = check_blueprint(_map_with_one_machine(Facing.NORTH))
    assert [
        f for f in report.findings if f.code == "Z9" and f.element_id == "machine_under_test"
    ] == []


def test_a_machine_in_the_open_is_not_this_defect() -> None:
    """A machine that touches no brushwork at all is a decision, not a mistake.

    A perk machine on a free-standing plinth or a mystery box in the middle
    of a room is a valid layout.  This row is about the wall a machine is
    already up against, not about machines that are against nothing.
    """
    report = check_blueprint(
        _map_with_one_machine(Facing.EAST, Point(160.0, -300.0, 16.0))
    )
    assert [
        f for f in report.findings if f.code == "Z9" and f.element_id == "machine_under_test"
    ] == []


# --------------------------------------------------------------------------
# Z4 per zone: a community rule, checked against the stock scripts
# --------------------------------------------------------------------------
def _map_with_a_zone_that_has_no_spawns() -> Blueprint:
    from zmforge.blueprint.elements import Spawn

    blueprint = three_room_map(MAP_NAME)
    for spawn in [s for s in blueprint.elements(Spawn) if s.zone_name == "vault"]:
        blueprint._elements.remove(spawn)
    return blueprint


def test_a_zone_with_no_spawn_struct_is_an_error_at_the_model_level() -> None:
    """Measured against the stock scripts, not taken on the community's word.

    ``zone_init`` collects a zone's locations from the structs its volume's
    ``target`` names, ``create_spawner_list`` gathers only from zones that are
    enabled, active and spawning, and ``manage_zones`` makes a zone active
    only while a player is in it or a set flag connects it to one that is.
    Both round loops in ``_zm.gsc`` then wait on the resulting list rather
    than time out, so a player alone in a zone with no structs gets a round
    that never starts.  That is a defect, not a warning.
    """
    report = check_blueprint(_map_with_a_zone_that_has_no_spawns())
    empty = [f for f in report.errors if f.code == "Z4" and "vault" in f.message]
    assert len(empty) == 1


def test_a_zone_with_no_spawn_struct_is_an_error_in_the_written_map() -> None:
    """The file-level half: Z4 was map-wide only over the text."""
    blueprint = _map_with_a_zone_that_has_no_spawns()
    from zmforge.emit.scripts import render_server_script

    document = parse_map_text(render_map_text(build_document(blueprint)))
    report = check_gameplay(document, render_server_script(blueprint.script))
    empty = [
        f
        for f in report.errors
        if f.code == "Z4" and "vault_spawners" in f.message
    ]
    assert len(empty) == 1


def test_one_factory_spawner_still_serves_the_whole_map() -> None:
    """The half of the community rule that measurement does *not* support.

    ``_zm.gsc`` picks the spawner entity with ``array::random(
    level.zombie_spawners )`` and the position with ``array::random(
    level.zm_loc_types[ "zombie_location" ] )``, independently: the spawner is
    a map-wide pool and the locations are per zone.  The shipped recipes carry
    one factory, so Z5 stays map-wide.
    """
    from zmforge.blueprint.elements import Spawn

    blueprint = three_room_map(MAP_NAME)
    spawns = blueprint.elements(Spawn)
    kept = next(spawn for spawn in spawns if spawn.with_factory)
    for spawn in spawns:
        spawn.with_factory = spawn is kept
    assert [s for s in spawns if s.with_factory] == [kept]
    assert check_blueprint(blueprint).ok


# --------------------------------------------------------------------------
# Z40: a zone volume over ground only zombies can occupy
#
# The converse of Z18, and read out of the stock scripts rather than taken on
# the tutorials' word.  ``_zm_spawner.gsc:359`` spawns every zombie with
# ``self.no_powerups = true``; ``zombie_entered_playable`` (:593) polls
# ``GetEntArray( "player_volume", "script_noteworthy" )`` once a second and
# the first volume the zombie touches runs
# ``zombie_complete_emerging_into_playable_area`` (:3253), whose second line
# clears that flag; ``zombie_can_drop_powerups`` (:1545) reads it.  Then
# ``zombie_death_points`` (:1584) ground-traces the corpse and
# ``zm_powerups::powerup_drop`` (``_zm_powerups.gsc:586``) keeps the drop
# wherever it ``istouching`` a volume, against a cap of
# ``zombie_powerup_drop_max_per_round`` = 4 (:74) and a 15-second timeout.
# --------------------------------------------------------------------------
def _yard_covered_by_its_zone() -> Blueprint:
    """The fixture with the start zone's volume stretched over yard_0."""
    from zmforge.blueprint.elements import Yard, Zone

    blueprint = three_room_map(MAP_NAME)
    yard = next(y for y in blueprint.elements(Yard) if y.id == "yard_0")
    zone = next(z for z in blueprint.elements(Zone) if z.name == "start")
    zone.bounds = Bounds(
        Point(zone.bounds.mins.x, yard.interior.mins.y, zone.bounds.mins.z),
        Point(zone.bounds.maxs.x, zone.bounds.maxs.y, zone.bounds.maxs.z),
    )
    return blueprint


def test_z40_is_silent_on_a_map_whose_volumes_stop_at_the_walls() -> None:
    """The fixture: three zones, two yards, no volume reaching over either."""
    report = check_blueprint(three_room_map(MAP_NAME))
    assert [f for f in report.findings if f.code == "Z40"] == []


def test_z40_fires_when_a_zone_volume_reaches_over_a_barricade_yard() -> None:
    """The case the community names, with the mechanism measured.

    A yard is the pocket outside a barricade window where the risers stand.
    ``_standing_patches`` leaves it out of the playable area on purpose --
    the barricade prefab stops the *player* at the wall line -- which is
    exactly what makes it ground a zombie can be killed on and a player
    cannot walk to.
    """
    report = check_blueprint(_yard_covered_by_its_zone())
    found = [f for f in report.findings if f.code == "Z40"]
    assert len(found) == 1
    assert "'start'" in found[0].message
    assert "yard_0" in found[0].message
    # A warning, not an error: it costs a powerup, not a life.
    assert found[0] not in report.errors


def test_z40_counts_the_yard_it_actually_covers() -> None:
    """The reported area is the overlap, not the whole yard or the whole zone."""
    from zmforge.blueprint.elements import Yard, Zone

    blueprint = _yard_covered_by_its_zone()
    yard = next(y for y in blueprint.elements(Yard) if y.id == "yard_0")
    zone = next(z for z in blueprint.elements(Zone) if z.name == "start")
    width = min(yard.interior.maxs.x, zone.bounds.maxs.x) - max(
        yard.interior.mins.x, zone.bounds.mins.x
    )
    depth = min(yard.interior.maxs.y, zone.bounds.maxs.y) - max(
        yard.interior.mins.y, zone.bounds.mins.y
    )
    found = next(
        f for f in check_blueprint(blueprint).findings if f.code == "Z40"
    )
    assert f"{width * depth:.0f} square units" in found.message


def test_z40_is_a_registered_blueprint_level_check() -> None:
    from zmforge.verify import BY_CODE, CODES

    assert "Z40" in CODES
    assert BY_CODE["Z40"].where == "blueprint"
    assert BY_CODE["Z40"].is_automated


# --------------------------------------------------------------------------
# One zone, several volumes: a zone volume's targetname is not unique
#
# Measured on Treyarch's own source.  ``map_source/zm/zm_giant.map``
# holds 32 ``info_volume`` entities tagged ``script_noteworthy player_volume``
# over 12 distinct targetnames -- ``outside_south_zone`` on six of them,
# ``receiver_zone`` on five -- every volume of a name carrying the same
# ``target``, against the single ``init_zones[0] = "receiver_zone";`` of
# ``zm_giant.gsc:183``.  Stock ``zone_init`` (``_zm_zonemgr.gsc:318``) builds
# ``zone.volumes`` with ``GetEntArray( zone_name, "targetname" )``, so that is
# not a special case, it is the mechanism.
# --------------------------------------------------------------------------
def _zone_with_a_second_volume(spawn_set: str | None = None) -> Blueprint:
    """The fixture with a second volume added to the start zone."""
    from zmforge.blueprint.elements import Zone

    blueprint = three_room_map(MAP_NAME)
    start = next(z for z in blueprint.elements(Zone) if z.name == "start")
    blueprint.add_zone(
        "start",
        Bounds(
            Point(start.bounds.mins.x - 256.0, start.bounds.mins.y, start.bounds.mins.z),
            Point(start.bounds.mins.x, start.bounds.maxs.y, start.bounds.maxs.z),
        ),
        spawn_set=spawn_set or start.spawn_set,
        id="zone_start_annexe",
    )
    return blueprint


def test_a_zone_may_own_a_second_volume_without_a_finding() -> None:
    blueprint = _zone_with_a_second_volume()
    assert len([z for z in blueprint.script.zones if z == "start"]) == 1
    report = check_blueprint(blueprint)
    assert [f for f in report.findings if f.code == "Z3"] == []


def test_a_second_volume_naming_a_second_spawn_set_is_an_error() -> None:
    """``zone_init`` reads ``zone.volumes[ 0 ].target`` and nothing else.

    ``_zm_zonemgr.gsc:345``, and again at ``:442`` in
    ``reinit_zone_spawners``.  Nothing fixes which volume ``GetEntArray``
    hands back first, so two volumes of one name naming two spawn sets means
    one set is thrown away and which one is a coin toss.  Every one of
    zm_giant's 32 volumes names the same target as its siblings.
    """
    report = check_blueprint(_zone_with_a_second_volume("start_annexe_spawners"))
    found = [f for f in report.errors if f.code == "Z3" and "spawn sets" in f.message]
    assert len(found) == 1


def test_thirty_two_volumes_against_one_init_zones_entry_is_not_a_finding() -> None:
    """The count comparison that would have failed Treyarch's own map.

    The rule used to be "as many player volumes as init_zones entries".
    zm_giant ships 32 against 1.  What is left is the name comparison, and
    both directions of it still fire -- a volume naming a zone nothing
    registers, and a registered zone with no volume.
    """
    from zmforge.emit.scripts import render_server_script

    blueprint = _zone_with_a_second_volume()
    document = parse_map_text(render_map_text(build_document(blueprint)))
    script = render_server_script(blueprint.script)
    from zmforge.emit.scripts import _initial_zones

    assert script.count('init_zones[') == len(_initial_zones(blueprint.script))
    volumes = [
        e
        for e in document.entities_of("info_volume")
        if e.value("script_noteworthy") == "player_volume"
    ]
    assert len(volumes) == len(blueprint.script.zones) + 1
    report = check_gameplay(document, script)
    assert [f for f in report.findings if f.code == "Z3"] == []


def test_a_spawn_inside_the_second_volume_of_its_zone_is_accepted() -> None:
    """Z4's "interior spawn outside its zone volume" against a multi-volume zone.

    The volumes are keyed by the spawn set they collect, and both of these
    collect ``start_spawners``, so the struct only has to be inside one of
    them.
    """
    from zmforge.blueprint.elements import Spawn, Zone
    from zmforge.emit.scripts import render_server_script

    blueprint = _zone_with_a_second_volume()
    annexe = next(z for z in blueprint.elements(Zone) if z.id == "zone_start_annexe")
    riser = next(s for s in blueprint.elements(Spawn) if s.zone_name == "start")
    spot = annexe.bounds.centre
    riser.position = Point(spot.x, spot.y, riser.position.z)

    document = parse_map_text(render_map_text(build_document(blueprint)))
    report = check_gameplay(document, render_server_script(blueprint.script))
    assert [f for f in report.findings if "outside" in f.message and f.code == "Z4"] == []


def test_the_two_argument_joins_still_register_the_far_zone() -> None:
    """``connect_zones( a, b )`` and a flagless ``add_adjacent_zone( a, b )``.

    ``connect_zones`` is ``_zm_zonemgr.gsc:772``: it ``zone_init``s both,
    ``enable_zone``s both and sets ``is_connected = true`` with no flag
    anywhere.  Reading only the three-argument door form reported the far
    zone as "registered but never enabled", which is an error, on a map that
    is fine.
    """
    from zmforge.verify.files import _enabled_zones

    hook = (
        'init_zones[0] = "start";\n'
        'zm_zonemgr::connect_zones( "start", "annexe" );\n'
        'zm_zonemgr::add_adjacent_zone( "annexe", "loft" );\n'
        'zm_zonemgr::add_adjacent_zone( "loft", "vault", "vault_door" );\n'
    )
    registered, enabled = _enabled_zones(hook)
    assert registered == {"start", "annexe", "loft", "vault"}
    assert enabled == {"start", "annexe", "loft", "vault"}


# --------------------------------------------------------------------------
# Z7: how far from a door it can be bought
# --------------------------------------------------------------------------
# The trigger is the volume the buy prompt lives in, so its size is the range.
# A door that grows its leaf by 128 units on all three axes makes its trigger
# 272 to 384 units on a side and 352 to 384 tall, which can put hundreds of
# props inside the triggers and lets a door be bought from about 150 units
# away.
def _door_parts(document):
    for trigger in document.entities_of("trigger_use"):
        if trigger.value("targetname") != "zombie_door":
            continue
        name = trigger.value("target")
        leaves = [
            e
            for e in document.entities_of("script_brushmodel")
            if e.value("targetname") == name
        ]
        yield name, trigger, leaves[0]


def test_z7_a_door_trigger_is_a_slab_across_its_own_doorway(committed) -> None:
    from zmforge.blueprint.elements import DOOR_TRIGGER_DEPTH, DOOR_TRIGGER_MARGIN
    from zmforge.verify.files import _brush_bounds
    from zmforge.spatial import Axis

    doors = list(_door_parts(committed["document"]))
    assert doors
    for name, trigger, leaf_entity in doors:
        box = _brush_bounds(trigger)
        leaf = _brush_bounds(leaf_entity)
        through = min((Axis.X, Axis.Y), key=lambda axis: leaf.extent(axis))
        across = Axis.Y if through is Axis.X else Axis.X
        assert box.extent(through) == pytest.approx(
            leaf.extent(through) + 2 * DOOR_TRIGGER_DEPTH
        ), name
        assert box.extent(across) == pytest.approx(
            leaf.extent(across) + 2 * DOOR_TRIGGER_MARGIN
        ), name
        # Never taller than the opening: a player on the floor above or below
        # is not offered the door.
        assert box.mins.z == pytest.approx(leaf.mins.z), name
        assert box.maxs.z == pytest.approx(leaf.maxs.z), name
        # The range the prompt reaches, measured from the leaf.
        assert box.extent(through) / 2.0 - leaf.extent(through) / 2.0 <= 96.0, name


def test_z7_fires_when_a_door_trigger_reaches_past_the_doorway(committed) -> None:
    """Z7 catches a door trigger grown past its doorway."""
    from zmforge.blueprint.elements import Door
    from zmforge.verify.files import check_gameplay

    plan = three_room_map(MAP_NAME)
    for door in plan.elements(Door):
        door.trigger_depth = 128.0
        door.trigger_margin = 128.0
    document = parse_map_text(render_map_text(build_document(plan)))
    oversized = [
        finding
        for finding in check_gameplay(document, committed["server"]).findings
        if finding.code == "Z7" and "its own leaf allows" in finding.message
    ]
    assert len(oversized) == 2 * len(plan.elements(Door))


def test_a_door_trigger_box_is_derived_from_the_opening() -> None:
    """The element's own arithmetic, with no emitter in the way."""
    from zmforge.blueprint.elements import DOOR_TRIGGER_DEPTH, DOOR_TRIGGER_MARGIN
    from zmforge.spatial import Axis

    plan = three_room_map(MAP_NAME)
    from zmforge.blueprint.elements import Door

    door = plan.elements(Door)[0]
    box = door.trigger_box
    assert door.through_axis in (Axis.X, Axis.Y)
    assert box.extent(door.through_axis) == pytest.approx(
        door.box.extent(door.through_axis) + 2 * DOOR_TRIGGER_DEPTH
    )
    assert box.mins.z == door.box.mins.z and box.maxs.z == door.box.maxs.z
    across = Axis.Y if door.through_axis is Axis.X else Axis.X
    assert box.extent(across) == pytest.approx(
        door.box.extent(across) + 2 * DOOR_TRIGGER_MARGIN
    )


# --------------------------------------------------------------------------
# The two machines the install ships a model and a script for, but no prefab
# --------------------------------------------------------------------------
def _with_widows_wine() -> Blueprint:
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_perk("widows_wine", Point(320.0, -336.0, 16.0), "north", id="ww")
    return blueprint


def test_widows_wine_is_emitted_as_the_struct_the_framework_reads() -> None:
    """No prefab ships for it, so the machine is the struct itself.

    ``_zm_perks.gsc:1419`` on the install says the struct must carry ``model``
    and ``script_noteworthy``, and :1437 collects them by the ``zm_perk_machine``
    targetname.  Those three keys are the whole contract.
    """
    document = build_document(_with_widows_wine())
    machines = [
        e
        for e in document.entities_of("script_struct")
        if e.value("targetname") == "zm_perk_machine"
    ]
    assert len(machines) == 1
    assert machines[0].value("model") == "p7_zm_vending_widows_wine"
    assert machines[0].value("script_noteworthy") == "specialty_widowswine"
    # and it is not also stamped as a prefab
    prefabs = {e.value("model") for e in document.entities_of("misc_prefab")}
    assert not any("widows" in (m or "") for m in prefabs)


def test_widows_wine_puts_its_module_in_both_scripts() -> None:
    blueprint = _with_widows_wine()
    module = r"scripts\zm\_zm_perk_widows_wine"
    assert module in blueprint.script.module_set()
    assert not [f for f in check_blueprint(blueprint).findings if f.is_error]


def test_z9_still_catches_a_struct_machine_with_no_module() -> None:
    """The file-level check reads the struct, not just stamped prefabs."""
    blueprint = _with_widows_wine()
    document = build_document(blueprint)
    report = check_gameplay(document, "", client_script="")
    assert [
        f
        for f in report.findings
        if f.code == "Z9" and "_zm_perk_widows_wine" in f.message
    ]


def test_electric_cherry_and_stamin_up_cannot_share_a_map() -> None:
    """The stock Electric Cherry script names its machine ``vending_marathon``."""
    blueprint = three_room_map(MAP_NAME)
    blueprint.place_perk("electric_cherry", Point(320.0, -336.0, 16.0), "north", id="ec")
    assert not [f for f in check_blueprint(blueprint).findings if f.is_error]
    blueprint.place_perk("stamin_up", Point(320.0, 336.0, 16.0), "south", id="su")
    clash = [
        f
        for f in check_blueprint(blueprint).findings
        if f.code == "Z9" and "vending_marathon" in f.message
    ]
    assert len(clash) == 1 and clash[0].is_error


def test_a_widows_wine_map_commits_with_no_errors(tmp_path) -> None:
    """End to end: the struct machine, its two #using lines, zero errors."""
    project = Project.create(MAP_NAME, tmp_path, blueprint=_with_widows_wine())
    result = project.commit()
    assert result.report.errors == [], [str(f) for f in result.report.errors]
    paths = project.paths()
    using = r"#using scripts\zm\_zm_perk_widows_wine;"
    assert using in paths["server_script"].read_text(encoding="utf-8")
    assert using in paths["client_script"].read_text(encoding="utf-8")
    document = parse_map_text(paths["map"].read_text(encoding="utf-8"))
    assert _structs(
        document,
        targetname="zm_perk_machine",
        model="p7_zm_vending_widows_wine",
        script_noteworthy="specialty_widowswine",
    )
