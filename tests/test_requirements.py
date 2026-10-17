"""The requirements table, the checks behind it, and the one command over both.

``docs/playable-map-requirements.md`` claims, for every way a generated map has
broken in play, either the check that guards it or that nothing does.  A
document is only worth that claim if the claim is tested, so this module tests
three things about it:

* every code a check can emit is a row of :data:`zmforge.verify.registry.CHECKS`
  and every row is a code some check can emit, so neither side can drift;
* every code is named in the document and every code the document names exists;
* the checks the document says exist actually pass on the shipped recipes.

The rest is the negative half: each check added with the document gets a map
that breaks it, because a check that has never fired is not evidence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from zmforge import Project, verify
from zmforge.blueprint.elements import Prefab
from zmforge.mapsource import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import one_room_map, three_room_map
from zmforge.spatial import Axis, Bounds, Facing, Point, Span
from zmforge.verify import registry
from zmforge.verify.coverage import FAIL, MANUAL, PASS, SKIP, UNREGISTERED, WARN

from conftest import seed_stock_weapon_table

REQUIREMENTS_DOC = Path(__file__).resolve().parents[1] / "docs" / "playable-map-requirements.md"

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src" / "zmforge"

#: Every check that needs a build log.  Nothing in this process runs a build,
#: so these are the eight a static run is entitled to skip, and no others.
STAGE_CODES = frozenset(
    check.code for check in registry.CHECKS if check.where == "stages"
)

#: Every check that needs the compiled navmesh.  Nothing in this process runs a
#: compile either, so these skip alongside the build-log ones.
NAVMESH_CODES = frozenset(
    check.code for check in registry.CHECKS if check.where == "navmesh"
)


# --------------------------------------------------------------------------
# The table and the code cannot drift apart
# --------------------------------------------------------------------------
def _codes_in_source() -> set[str]:
    """Every check label a module under ``verify/`` passes to a finding."""
    found: set[str] = set()
    pattern = re.compile(r'(?:error|warning)\(\s*\n?\s*"([A-Za-z_0-9]+)"')
    for path in (SOURCE_DIR / "verify").glob("*.py"):
        if path.name == "registry.py":
            continue
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_code_a_check_emits_has_a_row() -> None:
    """A finding whose code is in no row cannot be looked up by anybody."""
    missing = sorted(_codes_in_source() - set(registry.CODES))
    assert missing == [], missing


def _codes_mentioned_in_source() -> set[str]:
    """Every check label quoted anywhere under ``verify/``.

    Looser than :func:`_codes_in_source` on purpose.  ``P1`` and ``P2`` are
    passed to ``error()`` through a loop variable rather than as literals, so
    the strict scan cannot see them and a strict test would call two real
    checks phantoms.
    """
    found: set[str] = set()
    pattern = re.compile(r'"([A-Za-z_0-9]+)"')
    for path in (SOURCE_DIR / "verify").glob("*.py"):
        if path.name == "registry.py":
            continue
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_automated_row_is_a_code_some_check_emits() -> None:
    """A row nothing can produce is a requirement the table only claims to guard."""
    mentioned = _codes_mentioned_in_source()
    phantom = sorted(
        check.code for check in registry.automated() if check.code not in mentioned
    )
    assert phantom == [], phantom


def test_no_row_is_listed_twice() -> None:
    assert len(registry.CODES) == len(set(registry.CODES))


def test_every_manual_row_says_what_a_human_must_do() -> None:
    for check in registry.manual():
        assert check.note.strip(), check.code


# --------------------------------------------------------------------------
# The document and the table cannot drift apart
# --------------------------------------------------------------------------
def _codes_in_document() -> set[str]:
    """Every check label the document names.

    ``N`` and ``L`` are here alongside the specification's own families
    because :mod:`zmforge.verify.documented` numbers its checks after the
    source they came from -- the mod tools' shipped settings file and the
    light LOD paper -- rather than after a spec section.  ``H`` is a third
    kind again: :mod:`zmforge.verify.navmesh` reads the mesh the compiler
    wrote, so its row is named after the artefact and not after a document.
    """
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    return set(re.findall(r"`((?:Z|W|F|G|P|M|N|L|H|S|D|Q)\d+)`", text)) | set(
        re.findall(r"`(leak|stage_error|stage_failed|missing_material|"
                   r"missing_material_benign|umbra_unset|caulk_terrain|"
                   r"preview_lighting|shadows_dropped)`", text)
    )


def test_the_document_names_every_check() -> None:
    """A requirement nobody wrote down is one nobody will look for."""
    assert REQUIREMENTS_DOC.exists(), REQUIREMENTS_DOC
    missing = sorted(set(registry.CODES) - _codes_in_document())
    assert missing == [], missing


def test_the_document_counts_the_rows_correctly() -> None:
    """The three numbers in the opening paragraph, so they cannot go stale."""
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    counted = re.search(
        r"(\d+) rows, (\d+) automated and\s*\n?(\d+) that need a person", text
    )
    assert counted, "the document no longer states its row counts"
    rows, automated, manual = (int(group) for group in counted.groups())
    assert rows == len(registry.CHECKS)
    assert automated == len(registry.automated())
    assert manual == len(registry.manual())


def test_the_document_invents_no_check() -> None:
    """A code the document names and the table does not is a promise nothing keeps."""
    invented = sorted(_codes_in_document() - set(registry.CODES))
    assert invented == [], invented


def _scoreboard_bullet(lead: str) -> set[str]:
    """The codes listed after one bullet of the document's scoreboard."""
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith(f"- {lead}"))
    codes = set(re.findall(r"`((?:Z|W|F|G|P|M|N|L|H|S|D)\d+)`", line))
    if "`F1` through `F9`" in line:
        codes |= {f"F{n}" for n in range(1, 10)}
    return codes


def test_the_scoreboard_puts_every_code_on_the_right_side() -> None:
    """The opening partition is a claim about the table and can go stale."""
    for lead, where in (
        ("Model, before anything is written", "blueprint"),
        ("Written files", "files"),
        ("The navmesh the compiler wrote", "navmesh"),
    ):
        for code in _scoreboard_bullet(lead):
            assert where in registry.BY_CODE[code].where, (lead, code)


def test_the_scoreboard_lists_the_build_log_checks_exactly() -> None:
    text = REQUIREMENTS_DOC.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("- Build logs"))
    listed = set(re.findall(r"`([a-z_]+)`", line))
    assert listed == set(STAGE_CODES)


def test_a_finding_with_no_row_is_reported_as_a_failure() -> None:
    """The bucket that keeps the table from quietly losing a check."""
    from zmforge.verify.coverage import _score
    from zmforge.verify.report import Report, error

    report = Report([error("Z99", "a code nobody registered")])
    audit = _score(report, ("files",))
    stray = [o for o in audit.outcomes if o.check.code == "Z99"]
    assert len(stray) == 1
    assert stray[0].status == FAIL
    assert not audit.ok


# --------------------------------------------------------------------------
# Z19, Z20, Z21, Z22: the playtest checks reach the entry points
# --------------------------------------------------------------------------
def test_the_playtest_checks_run_from_check_blueprint() -> None:
    """A check in its own module counts only if the entry point calls it."""
    import zmforge.verify.playtest as playtest

    calls = []
    original = playtest.check_blueprint_playtest

    def spy(blueprint):
        calls.append(blueprint)
        return original(blueprint)

    playtest.check_blueprint_playtest = spy
    try:
        verify.blueprint(three_room_map("zm_forge_gate"))
    finally:
        playtest.check_blueprint_playtest = original
    assert len(calls) == 1


def test_a_map_with_its_kill_volume_removed_fails_the_file_checks(tmp_path) -> None:
    """Z20 through ``check_written_files``, not through its own function."""
    project = _commit(tmp_path, "zm_forge_gate", three_room_map)
    paths = project.paths()
    document = parse_map_text(paths["map"].read_text(encoding="utf-8"))
    document.entities = [
        e for e in document.entities if e.value("classname") != "trigger_hurt"
    ]
    paths["map"].write_text(render_map_text(document), encoding="utf-8")
    report = verify.files(project)
    assert "Z20" in {f.code for f in report.errors}


def test_a_prop_told_not_to_bake_collision_fails_the_file_checks(tmp_path) -> None:
    """Z21 through ``check_written_files``."""
    from zmforge.props.library import PROPS

    solid = next(prop for prop in PROPS if prop.solid)
    project = _commit(tmp_path, "zm_forge_gate", three_room_map)
    paths = project.paths()
    document = parse_map_text(paths["map"].read_text(encoding="utf-8"))
    entity = document.entities[-1]
    document.entities.append(
        _misc_model(document, solid.name, entity)
    )
    paths["map"].write_text(render_map_text(document), encoding="utf-8")
    report = verify.files(project)
    assert "Z21" in {f.code for f in report.errors}


def _misc_model(document, model: str, like):
    """A ``misc_model`` that names a solid prop and bakes no collision."""
    from dataclasses import replace

    pairs = [
        ("classname", "misc_model"),
        ("model", model),
        ("origin", "0 0 16"),
        ("no_collmap", "1"),
    ]
    return replace(like, pairs=pairs, solids=[])


def test_a_script_naming_a_weapon_this_level_lacks_fails_the_file_checks(
    tmp_path,
) -> None:
    """Z22 through ``check_written_files``: the box that asked for an Olympia."""
    project = _commit(tmp_path, "zm_forge_gate", three_room_map)
    paths = project.paths()
    text = paths["server_script"].read_text(encoding="utf-8")
    text = text.replace(
        "zm_usermap::main();",
        'level.zmf_gag = getweapon( "shotgun_olympia" );\n\tzm_usermap::main();',
    )
    paths["server_script"].write_text(text, encoding="utf-8")
    report = verify.files(project)
    olympia = [f for f in report.errors if f.code == "Z22"]
    assert olympia, [str(f) for f in report]
    assert "shotgun_olympia" in olympia[0].message


def test_every_wall_buy_slug_resolves_to_a_weapon_this_level_has() -> None:
    """Z22's model side, against the thirteen prefabs read off the install.

    The slug names the prefab file; the weapon is named inside it. Twelve of
    the thirteen agree with their slug and ``bowie`` does not -- its buy
    struct carries ``"zombie_weapon_upgrade" "bowie_knife"`` -- which is the
    whole reason the lookup cannot be done on the slug.
    """
    from zmforge.blueprint.catalogue import (
        LEVEL_WEAPONS,
        WALL_WEAPONS,
        WALL_WEAPON_WEAPONS,
    )

    assert set(WALL_WEAPON_WEAPONS) == set(WALL_WEAPONS)
    outside = sorted(
        slug
        for slug, weapon in WALL_WEAPON_WEAPONS.items()
        if weapon not in LEVEL_WEAPONS
    )
    assert outside == [], outside
    assert WALL_WEAPON_WEAPONS["bowie"] == "bowie_knife"


def test_the_bowie_buy_no_longer_warns() -> None:
    """It warned until the prefab was read, and the buy was working all along."""
    from zmforge.spatial import Point
    from zmforge.verify.playtest import check_weapon_names

    blueprint = one_room_map("zm_one_room")
    blueprint.place_wall_weapon(
        "bowie", Point(0, 0, 0), Facing.NORTH, id="buy_bowie"
    )
    assert check_weapon_names(blueprint).findings == []


def test_a_wall_buy_slug_with_no_prefab_is_an_error() -> None:
    """``place_wall_weapon`` refuses one, so Z22 is the backstop for the rest."""
    from zmforge.blueprint.elements import WallWeapon
    from zmforge.spatial import Point
    from zmforge.verify.playtest import check_weapon_names

    blueprint = one_room_map("zm_one_room")
    blueprint._install(
        WallWeapon(id="buy_nonsense", slug="shotgun_olympia", position=Point(0, 0, 0))
    )
    findings = check_weapon_names(blueprint).findings
    assert [f.code for f in findings] == ["Z22"]
    assert findings[0].is_error


# --------------------------------------------------------------------------
# Z23: the rotation sense
# --------------------------------------------------------------------------
#: Spec appendix B, one row per family, each read off its own stock prefab
#: under ``map_source/_prefabs/zm/zm_core`` on the mod-tools install.  A change
#: to any of these is a change to a measurement and needs a new reading, not a
#: new opinion.
MEASURED_FRONTS = {
    "spawnable_weapon_pistol_burst.map": Facing.NORTH,
    "vending_juggernaut_struct.map": Facing.SOUTH,
    "vending_sleight_struct.map": Facing.SOUTH,
    "vending_revive_struct.map": Facing.SOUTH,
    "vending_doubletap_struct.map": Facing.SOUTH,
    "vending_deadshot_struct.map": Facing.SOUTH,
    "vending_marathon_struct.map": Facing.SOUTH,
    "vending_additionalprimaryweapon_struct.map": Facing.SOUTH,
    "vending_bgb_struct.map": Facing.SOUTH,
    "vending_weapon_upgrade_spawnable.map": Facing.WEST,
    "buyable_magic_box_start.map": Facing.NORTH,
    "power_switch.map": Facing.SOUTH,
    "barricade_reciever_wood.map": Facing.NORTH,
}


def test_every_stock_prefab_the_catalogue_names_has_a_measured_front() -> None:
    """The whole stock library is read, and the table says what was read."""
    from zmforge.blueprint.catalogue import PREFAB_FRONT_ZERO_BY_MODEL

    table = {
        path.rsplit("/", 1)[-1]: front
        for path, front in PREFAB_FRONT_ZERO_BY_MODEL.items()
    }
    # 25: ar_cqb's prefab is not in the table, because its chalk material is
    # missing from the mod tools (catalogue.CHALKLESS_WALL_WEAPONS).
    assert len(PREFAB_FRONT_ZERO_BY_MODEL) == 25, sorted(table)
    for name, front in MEASURED_FRONTS.items():
        assert table[name] is front, name


def test_the_pack_a_punch_is_not_on_the_perk_heading() -> None:
    """The row that no comparison of rotation senses could have found.

    Its prefab's own entities are authored at yaw 270, which turns the vending
    family's -Y front onto -X, so every heading it was ever emitted at was 90
    degrees out rather than 0 or 180.
    """
    from zmforge.blueprint.catalogue import (
        PACK_A_PUNCH_FRONT_ZERO,
        PERK_FRONT_ZERO,
        perk_named,
        prefab_yaw,
    )

    assert perk_named("pack_a_punch").front_zero is PACK_A_PUNCH_FRONT_ZERO
    assert PACK_A_PUNCH_FRONT_ZERO is not PERK_FRONT_ZERO
    for heading in Facing:
        off = (
            prefab_yaw(heading, PACK_A_PUNCH_FRONT_ZERO)
            - prefab_yaw(heading, PERK_FRONT_ZERO)
        ) % 360.0
        assert off == 90.0, heading


def test_the_turn_is_counter_clockwise_for_every_family() -> None:
    """One formula: (heading - front at yaw 0) mod 360, and never its negative."""
    from zmforge.blueprint.catalogue import PREFAB_FRONT_ZERO_BY_MODEL, prefab_yaw

    for front in set(PREFAB_FRONT_ZERO_BY_MODEL.values()):
        for heading in Facing:
            assert prefab_yaw(heading, front) == (
                heading.world_yaw - front.world_yaw
            ) % 360.0


def test_a_measured_prefab_is_not_reported_on_any_heading() -> None:
    """A model whose front has been read is emitted right on all four headings."""
    for heading in Facing:
        blueprint = three_room_map("zm_forge_gate")
        blueprint.place_prefab(
            "_prefabs/zm/zm_core/power_switch.map",
            Point(-256.0, 96.0, 16.0),
            heading,
            id="scenery",
        )
        report = verify.playtest.check_prefab_rotation_sense(blueprint)
        assert "scenery" not in {f.element_id for f in report}, heading


def test_a_prefab_carrying_a_raw_yaw_is_not_reported() -> None:
    """The caller established their own zero heading; this convention was not used."""
    blueprint = three_room_map("zm_forge_gate")
    blueprint.place_prefab(
        "_prefabs/zm/zm_giant/geo/trap_switch_01.map",
        Point(-256.0, 96.0, 16.0),
        Facing.EAST,
        yaw=45.0,
        id="scenery",
    )
    report = verify.playtest.check_prefab_rotation_sense(blueprint)
    assert "scenery" not in {f.element_id for f in report}


def test_an_unread_prefab_warns_and_names_what_would_settle_it() -> None:
    """The one case that stays a warning: nobody has opened this prefab."""
    blueprint = three_room_map("zm_forge_gate")
    blueprint.place_prefab(
        "_prefabs/zm/zm_giant/geo/trap_switch_01.map",
        Point(-256.0, 96.0, 16.0),
        Facing.EAST,
        id="scenery",
    )
    report = verify.playtest.check_prefab_rotation_sense(blueprint)
    mine = [f for f in report if f.element_id == "scenery"]
    assert len(mine) == 1
    assert not mine[0].is_error
    assert "nobody has opened" in mine[0].message
    assert "PREFAB_FRONT_ZERO_BY_MODEL" in mine[0].message


def test_a_machine_emitted_at_the_wrong_yaw_is_an_error() -> None:
    """Z23 has teeth: put the old clockwise turn back and it reports it.

    The check reads the emitted entities, not the blueprint, so the only way to
    provoke it is to break the emitter.  Patching ``catalogue.prefab_yaw`` does
    exactly what the shipped defect did: turns every prefab the other way.
    """
    from zmforge.blueprint import catalogue

    blueprint = three_room_map("zm_forge_gate")
    good = catalogue.prefab_yaw
    catalogue.prefab_yaw = lambda heading, zero: (
        zero.world_yaw - heading.world_yaw
    ) % 360.0
    try:
        report = verify.playtest.check_prefab_rotation_sense(blueprint)
    finally:
        catalogue.prefab_yaw = good
    assert report.errors, [str(f) for f in report]
    assert all(f.code == "Z23" for f in report.errors)
    assert any("mystery box" in f.message for f in report.errors)


def test_every_barricade_of_the_fixture_is_on_an_agreed_heading() -> None:
    """The three-room fixture's windows face north and south, and must keep doing so.

    This is the map the end-to-end gate was run against.  If a change turns one
    of its barricades onto an east or west wall, the rotation sense becomes a
    live question on the one configuration known to work in game, and the
    reader should be told rather than left to find it by playing.
    """
    report = verify.playtest.check_prefab_rotation_sense(three_room_map("zm_forge_gate"))
    windows = [f for f in report if "barricade" in f.message]
    assert windows == [], [str(f) for f in windows]


# --------------------------------------------------------------------------
# Z25: the flood from the spawn
# --------------------------------------------------------------------------
STRANDED = Bounds.between((200.0, -100.0, 0.0), (360.0, 60.0, 16.0))

#: 144 units over the arena floor: past the 64 of ``jump_height`` and nowhere
#: near a step, so nothing but a route can put a player on it.
STRANDED_TOP = 160.0

SEALED = Bounds.between((768.0, 400.0, 0.0), (1024.0, 656.0, 256.0))


def _with_a_stranded_platform(*, declared: bool = False):
    """The three-room map, plus a ledge with a perk on it and no way up."""
    blueprint = three_room_map("zm_forge_gate")
    arena = blueprint.find("arena_room")
    blueprint.add_slab(
        STRANDED,
        STRANDED_TOP,
        16.0,
        arena.materials.floor,
        reachable=not declared,
        id="stranded_ledge",
    )
    blueprint.place_perk(
        "mule_kick",
        Point(STRANDED.centre.x, STRANDED.centre.y, STRANDED_TOP),
        Facing.SOUTH,
        id="perk_stranded",
    )
    return blueprint


def test_a_stranded_platform_with_a_machine_on_it_is_reported() -> None:
    """The negative case: a ledge 144 units up, with no route onto it.

    This is the defect the check exists for. It is not caught by anything
    else: the ledge is inside the arena's zone volume, so Z18 passes it, it is
    not a flight of steps, so Z19 never looks at it, and the machine stands on
    a walkable surface with clear space in front, so Z9 passes it too.
    """
    report = verify.check_reachability(_with_a_stranded_platform())
    stranded = [f for f in report.errors if f.code == "Z25"]
    assert [f.element_id for f in stranded] == ["perk_stranded"], [
        str(f) for f in report
    ]
    assert "mule_kick" in stranded[0].message


def test_the_platform_becomes_reachable_when_steps_lead_up_to_it() -> None:
    """The same map with a flight onto the ledge reports nothing.

    Without this the test above proves only that the check says no.
    """
    blueprint = _with_a_stranded_platform()
    arena = blueprint.find("arena_room")
    # Nine 16-unit rises, ending exactly at the ledge's south edge: the top
    # step's head is level with it and touching it.
    blueprint.add_steps(
        Point(STRANDED.mins.x, STRANDED.mins.y - 9 * 16.0, arena.floor_z),
        9,
        16.0,
        16.0,
        STRANDED.extent(Axis.X),
        Facing.NORTH,
        arena.materials.floor,
        id="ledge_stairs",
    )
    assert list(verify.check_reachability(blueprint)) == []


def test_a_platform_the_map_declares_unreachable_is_passed_over() -> None:
    """``reachable=False`` is the map saying the tease is deliberate.

    The same flag Z9 reads and ``_standing_patches`` drops, so a recipe
    declares it once, on the geometry.
    """
    report = verify.check_reachability(_with_a_stranded_platform(declared=True))
    assert list(report) == [], [str(f) for f in report]


def test_a_room_with_no_opening_in_it_is_reported() -> None:
    blueprint = three_room_map("zm_forge_gate")
    blueprint.add_room(SEALED, wall=16.0, id="bricked_up")
    report = verify.check_reachability(blueprint)
    rooms = [f for f in report.errors if f.element_id == "bricked_up"]
    assert len(rooms) == 1, [str(f) for f in report]
    assert "no route into it" in rooms[0].message


def test_a_room_declared_unreachable_is_not_reported() -> None:
    """The room flagged look-into-only, which the sealed vault of one map is."""
    blueprint = three_room_map("zm_forge_gate")
    blueprint.add_room(SEALED, wall=16.0, reachable=False, id="bricked_up")
    assert list(verify.check_reachability(blueprint)) == []


def test_the_flood_walks_through_a_priced_door() -> None:
    """A door is bought, not locked, so the far side of one is reachable.

    The fixture's vault is behind two priced doors and one of the four perks
    stands in it; if a door stopped the flood, every one of them would be
    reported.
    """
    blueprint = three_room_map("zm_forge_gate")
    flood = verify.flood_from_spawn(blueprint)
    entered = {flood.cells[index].element_id for index in flood.reached}
    assert "vault_room" in entered
    assert list(verify.check_reachability(blueprint)) == []


def test_the_heights_a_player_is_allowed_are_the_measured_ones() -> None:
    """The step, the jump and the fatal drop, pinned as links in the graph.

    ``jump_height 64`` and ``bg_fallDamageMaxHeight 512`` are read out of
    ``scripts/zm/gametypes/_globallogic.gsc``; the 16-unit step is the
    labelled assumption. A change to any of them changes which maps pass, so
    it should change this test too.
    """
    from zmforge.verify.reachability import JUMP_UP, STEP_UP, Standing, _how

    def apart(rise: float) -> str | None:
        here = Span.flat_ok(Point(0.0, 0.0, 0.0), Point(64.0, 64.0, 0.0))
        there = Span.flat_ok(Point(64.0, 0.0, rise), Point(128.0, 64.0, rise))
        return _how(
            Standing("here", "a", here, 0.0), Standing("there", "b", there, rise)
        )

    assert apart(STEP_UP) == "walked"
    assert apart(STEP_UP + 1.0) == "jumped up"
    assert apart(JUMP_UP) == "jumped up"
    assert apart(JUMP_UP + 1.0) is None
    assert apart(-64.0) == "dropped"
    assert apart(-300.0) == "dropped, taking fall damage"
    assert apart(-512.0) is None


def test_a_drop_is_a_one_way_link() -> None:
    """Falling off the ledge is a route down and not a route back up."""
    from zmforge.verify.reachability import Standing, _how

    high = Standing(
        "high", "a", Span.flat_ok(Point(0.0, 0.0, 96.0), Point(64.0, 64.0, 96.0)), 96.0
    )
    low = Standing(
        "low", "b", Span.flat_ok(Point(64.0, 0.0, 0.0), Point(128.0, 64.0, 0.0)), 0.0
    )
    assert _how(high, low) == "dropped"
    assert _how(low, high) is None


def _with_a_walled_off_pocket(depth: float):
    """The three-room map with a strip of the arena's south wall sealed off.

    One block parallel to the wall and one closing its east end, so the strip
    between them and the wall has no way in. ``depth`` is how far the pocket
    reaches out from the wall: a maze partition closed at
    both ends can make one 272 units deep, and a
    16-unit one is the sliver behind a fin, which is not a place at all.  The
    strip stops well short of the wall buy at x 320 and the perk at y -336.
    """
    blueprint = three_room_map("zm_forge_gate")
    arena = blueprint.find("arena_room")
    west, south = arena.interior.mins.x, arena.interior.mins.y
    ceiling = arena.interior.maxs.z
    for index, box in enumerate(
        (
            Bounds.between(
                (west, south + depth, arena.floor_z),
                (west + 400.0, south + depth + 16.0, ceiling),
            ),
            Bounds.between(
                (west + 384.0, south, arena.floor_z),
                (west + 400.0, south + depth, ceiling),
            ),
        )
    ):
        blueprint.add_block(box, arena.materials.wall, id=f"partition_{index}")
    return blueprint


def test_floor_walled_off_inside_a_room_the_player_reaches_is_a_warning() -> None:
    """The maze pocket: a room that is entered, with dead floor inside it.

    Nothing else sees this. The room check is satisfied because the room is
    entered, and Z18 is satisfied because the pocket is inside the zone
    volume that covers the room.
    """
    report = verify.check_reachability(_with_a_walled_off_pocket(128.0))
    assert report.errors == []
    stranded = report.warnings
    assert [f.element_id for f in stranded] == ["arena_room"], [
        str(f) for f in report
    ]
    assert "no route to it" in stranded[0].message
    assert "square units" in stranded[0].message


def test_a_pocket_too_narrow_to_stand_in_is_not_reported() -> None:
    """A gap narrower than the player's own footprint is not a place."""
    report = verify.check_reachability(_with_a_walled_off_pocket(16.0))
    assert list(report) == [], [str(f) for f in report]


def test_the_flood_runs_from_check_blueprint() -> None:
    """A check nothing calls is a check nobody runs."""
    import zmforge.verify.reachability as reachability

    calls = []
    original = reachability.check_reachability

    def spy(blueprint):
        calls.append(blueprint)
        return original(blueprint)

    reachability.check_reachability = spy
    try:
        verify.blueprint(_with_a_stranded_platform())
    finally:
        reachability.check_reachability = original
    assert len(calls) == 1


def test_the_stranded_platform_reaches_the_whole_table() -> None:
    """Z25 has to come out of ``check_blueprint`` as a failing row, not a stray."""
    from zmforge.verify.coverage import _score

    report = verify.blueprint(_with_a_stranded_platform())
    audit = _score(report, ("blueprint",))
    row = next(o for o in audit.outcomes if o.check.code == "Z25")
    assert row.status == FAIL
    assert [o.check.code for o in audit.outcomes if o.ran == (UNREGISTERED,)] == []


# --------------------------------------------------------------------------
# Z24: the two things that cannot be built and the one that cannot be said
# --------------------------------------------------------------------------
def _manifest_with(extra: str, name: str = "zm_forge_gate") -> str:
    lines = [
        ">class,zm_mod_level",
        ">group,modtools",
        ">title,Forge Gate",
        f"col_map,maps/zm/{name}.d3dbsp",
        f"gfx_map,maps/zm/{name}.d3dbsp",
        f"scriptparsetree,scripts/zm/{name}.gsc",
        f"scriptparsetree,scripts/zm/{name}.csc",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def test_a_sound_bank_named_after_the_map_is_not_a_complaint() -> None:
    """A sound bank is CSV, and shipping one is normal.

    A bank is not a compiled ``.sz`` only the GUI asset editor can write, so
    a ``sound,`` line is not an error in itself.  Treyarch's own shipped bank
    is CSV text with a 102-column header, so the line is fine and the rules
    that bite are the three below.
    """
    report = verify.check_manifest(_manifest_with("sound,zm_forge_gate"), "zm_forge_gate")
    assert "Z24" not in {f.code for f in report}, [str(f) for f in report]


def test_a_bank_under_any_name_but_the_map_s_is_an_error() -> None:
    report = verify.check_manifest(_manifest_with("sound,zm_example"), "zm_forge_gate")
    sound = [f for f in report.errors if f.code == "Z24"]
    assert sound, [str(f) for f in report]
    assert "alias.sz" in sound[0].message


def _write_bank(directory, name: str, rows: int = 1) -> None:
    """A bank of *rows* rows with the columns the mod tools' header has."""
    from zmforge.emit.sound import SoundAlias, render_alias_bank, render_localised_bank

    header = ("Name", "Behavior", "Storage", "FileSpec", "Template", "Looping",
              "VolMin", "VolMax", "DistMin", "DistMaxDry", "DistMaxWet",
              "FadeIn", "FadeOut")
    aliases = [
        SoundAlias(name=f"alias_{index}", wav=f"{name}\\tone.wav")
        for index in range(rows)
    ]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.all.alias.sz").write_text(
        render_alias_bank(aliases, header), encoding="utf-8"
    )
    (directory / f"{name}.english.alias.sz").write_text(
        render_localised_bank(header), encoding="utf-8"
    )


def test_a_bank_in_the_per_platform_tree_is_reported_as_the_near_miss(tmp_path) -> None:
    """Measured: pc\\raw links as though the bank were absent."""
    shared = tmp_path / "share" / "raw" / "sound" / "zone"
    platform = tmp_path / "pc" / "raw" / "sound" / "zone"
    _write_bank(platform, "zm_forge_gate")
    shared.mkdir(parents=True)
    report = verify.check_sound_bank(
        _manifest_with("sound,zm_forge_gate"),
        map_name="zm_forge_gate",
        bank_dir=shared,
        platform_bank_dir=platform,
    )
    errors = [f for f in report.errors if f.code == "Z24"]
    assert errors, [str(f) for f in report]
    assert "per-platform" in errors[0].message


def test_a_bank_over_the_row_ceiling_is_an_error(tmp_path) -> None:
    from zmforge.emit.sound import ALIAS_ROW_CEILING

    shared = tmp_path / "share" / "raw" / "sound" / "zone"
    _write_bank(shared, "zm_forge_gate", rows=2)
    bank = shared / "zm_forge_gate.all.alias.sz"
    padded = bank.read_text(encoding="utf-8").splitlines()
    bank.write_text(
        "\r\n".join(padded + [padded[-1].replace("alias_1", f"alias_{n}")
                             for n in range(2, ALIAS_ROW_CEILING + 2)]) + "\r\n",
        encoding="utf-8",
    )
    report = verify.check_sound_bank(
        _manifest_with("sound,zm_forge_gate"),
        map_name="zm_forge_gate",
        bank_dir=shared,
    )
    errors = [f for f in report.errors if f.code == "Z24"]
    assert errors, [str(f) for f in report]
    assert str(ALIAS_ROW_CEILING) in errors[0].message


def test_a_row_whose_wave_file_is_missing_is_an_error(tmp_path) -> None:
    shared = tmp_path / "share" / "raw" / "sound" / "zone"
    _write_bank(shared, "zm_forge_gate")
    report = verify.check_sound_bank(
        _manifest_with("sound,zm_forge_gate"),
        map_name="zm_forge_gate",
        bank_dir=shared,
        sound_source_dir=tmp_path / "sound_assets",
    )
    errors = [f for f in report.errors if f.code == "Z24"]
    assert errors, [str(f) for f in report]
    assert "plays silence" in errors[0].message


def test_a_declared_bank_that_is_not_on_disk_is_an_error(tmp_path) -> None:
    shared = tmp_path / "share" / "raw" / "sound" / "zone"
    shared.mkdir(parents=True)
    report = verify.check_sound_bank(
        _manifest_with("sound,zm_forge_gate"),
        map_name="zm_forge_gate",
        bank_dir=shared,
    )
    assert [f.code for f in report.errors] == ["Z24"]


def test_a_declared_string_with_no_file_is_an_error(tmp_path) -> None:
    """A declared string table with no ``.str`` file is an error.

    A map that declares ``localize,zm_forge_gate`` without the ``.str`` file
    beside it stops the link with ``Localization ERROR: Unable to load
    "localizedstrings/<map>.str"!``.  No other static check asks whether the
    file will be there; this is the question ``W5`` already asks of a
    declared weapon table.
    """
    manifest = _manifest_with("localize,zm_forge_gate")
    report = verify.check_localized_strings(manifest, strings_dir=tmp_path)
    assert [f.code for f in report.errors] == ["Z24"]
    assert "Unable to load" in report.errors[0].message

    (tmp_path / "zm_forge_gate.str").write_text('VERSION "1"\r\nENDMARKER\r\n')
    assert verify.check_localized_strings(manifest, strings_dir=tmp_path).ok


def test_an_unknown_strings_folder_checks_nothing(tmp_path) -> None:
    """``None`` means the caller cannot say, not that everything is fine.

    Guessing a folder here would report a missing file for every map built
    from a tree this package was not handed.
    """
    manifest = _manifest_with("localize,zm_forge_gate")
    assert verify.check_localized_strings(manifest, strings_dir=None).ok


def test_a_localize_line_is_not_flagged_any_more() -> None:
    """Measured: a ``localize,`` line links.

    A probe usermap declaring ``localize,zmf_locprobe`` against a
    hand-written ``.str`` linked with no ``ERROR:`` line, so the line is
    verified rather than flagged.  The generator emits such a line on
    purpose, so a warning here would fire on every map that names its own
    guns (spec 5.7).
    """
    report = verify.check_manifest(_manifest_with("localize,zm_forge_gate"), "zm_forge_gate")
    assert "Z24" not in {f.code for f in report}, [str(f) for f in report]


def test_a_clean_manifest_asks_for_nothing_unbuildable() -> None:
    report = verify.check_manifest(_manifest_with(""), "zm_forge_gate")
    assert "Z24" not in {f.code for f in report}


def test_a_literal_purchase_prompt_is_reported() -> None:
    report = verify.check_purchase_text(
        'function main() { t sethintstring( "Buy a Toaster [Cost: 500]" ); }',
        label="zm_forge_gate.gsc",
    )
    assert [f.code for f in report] == ["Z24"]
    assert "Toaster" in report.findings[0].message


def test_the_empty_hint_string_the_stock_scripts_pass_is_not_reported() -> None:
    """Clearing a prompt is what 614 stock call sites do; it is not a request."""
    report = verify.check_purchase_text(
        'function main() { t sethintstring( "" ); }', label="zm_forge_gate.gsc"
    )
    assert list(report) == []


def test_the_purchase_text_check_runs_from_check_written_files(tmp_path) -> None:
    project = _commit(tmp_path, "zm_forge_gate", three_room_map)
    paths = project.paths()
    text = paths["server_script"].read_text(encoding="utf-8")
    text = text.replace(
        "zm_usermap::main();",
        'level.zmf_t sethintstring( "Press F to Regret" );\n\tzm_usermap::main();',
    )
    paths["server_script"].write_text(text, encoding="utf-8")
    report = verify.files(project)
    assert "Z24" in {f.code for f in report}


# --------------------------------------------------------------------------
def _commit(root, name: str, recipe) -> Project:
    seed_stock_weapon_table(root)
    project = Project.create(name, root, blueprint=recipe(name))
    project.commit(force=True)
    return project


def test_a_level_gap_of_up_to_eighty_units_is_a_route_and_more_is_not() -> None:
    """Z25's second kind of link: the leap, and the four things it insists on.

    ``GAP_JUMP`` is 80 against a standing jump reported at about 100 units of
    distance (``docs/playable-map-requirements.md``), and the sprint leap that
    would give 220 is switched off in zombies by ``_zm.gsc:216``.  Unlike every
    other number in that module this one is deliberately **short**: a link the
    flood makes here is the map asserting a player can clear it.
    """
    from zmforge.verify.reachability import GAP_JUMP, Standing, _gap_jump

    def across(gap: float, rise: float = 0.0, width: float = 96.0):
        here = Span.flat_ok(Point(0.0, 0.0, 0.0), Point(96.0, width, 0.0))
        there = Span.flat_ok(
            Point(96.0 + gap, 0.0, rise), Point(192.0 + gap, width, rise)
        )
        return _gap_jump(
            Standing("here", "a", here, 0.0),
            Standing("there", "b", there, rise),
            (),
        )

    assert across(GAP_JUMP) == "jumped 80 units across"
    assert across(GAP_JUMP + 1.0) is None
    assert across(0.0) is None               # touching: _how owns that pair
    assert across(48.0, rise=8.0) is None    # take-off and landing must be level
    assert across(48.0, rise=-8.0) is None
    assert across(48.0, width=24.0) is None  # narrower than the player's hull


def test_a_diagonal_leap_is_refused_the_way_a_corner_is() -> None:
    """Two platforms apart on both axes are a jump nobody can put a number on."""
    from zmforge.verify.reachability import Standing, _gap_jump

    here = Span.flat_ok(Point(0.0, 0.0, 0.0), Point(96.0, 96.0, 0.0))
    there = Span.flat_ok(Point(136.0, 136.0, 0.0), Point(232.0, 232.0, 0.0))
    assert _gap_jump(
        Standing("here", "a", here, 0.0), Standing("there", "b", there, 0.0), ()
    ) is None


def test_a_wall_in_the_gap_is_a_wall_and_not_a_jump() -> None:
    """A solid standing in the lane, or on either lip, stops the leap.

    Without this the rule would link two rooms either side of a partition, and
    a map with a sealed pocket would pass because the flood jumped the wall.
    """
    from zmforge.verify.reachability import Standing, _gap_jump

    here = Standing(
        "here", "a", Span.flat_ok(Point(0.0, 0.0, 0.0), Point(96.0, 96.0, 0.0)), 0.0
    )
    there = Standing(
        "there", "b",
        Span.flat_ok(Point(160.0, 0.0, 0.0), Point(256.0, 96.0, 0.0)), 0.0
    )
    assert _gap_jump(here, there, ()) == "jumped 64 units across"
    wall = Span.between(Point(110.0, 0.0, 0.0), Point(126.0, 96.0, 128.0))
    assert _gap_jump(here, there, (wall,)) is None
    # and something low in the gap is jumped over rather than hit
    kerb = Span.between(Point(110.0, 0.0, 0.0), Point(126.0, 96.0, 12.0))
    assert _gap_jump(here, there, (kerb,)) == "jumped 64 units across"
