"""The six trick guns say their own names on the prompt, not only on the wall.

WHAT THIS IS DEFENDING.  A painted plate beside the buy is not needed to show
a renamed gun's name, because the prompt is not entirely the framework's.
Half of it is: the weapon's own name comes from the engine's cursor hint.
The other half is
``level.zombie_weapons[weapon].hint``, which ``_zm_weapons.gsc:559-566``
assigns and ``:969`` reads back through ``get_weapon_hint()``, so a script
that overwrites it between those two moments picks the words.  The map does,
against a ``localize`` asset of its own.

Every one of the four chain links below fails silently in a play session if
it goes missing, which is why each has a test: the ``.str`` file, the
``localize`` line that packs it, the ``#precache`` that gives the script a
handle to it, and the assignment that points the wall buy at it.

WHAT IT CANNOT TEST.  Whether the prompt reads the renamed name in game.
Nothing here launches the game and nothing here runs the linker; the
asset-name rule is pinned to what the linker's own ``assetinfo`` CSV recorded
and no further.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint import Blueprint
from zmforge.blueprint.script_plan import ScriptPlan
from zmforge.emit.manifest import render_manifest
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.emit.strings import (
    LocalizedString,
    asset_name,
    render_str_file,
    weapon_prompt,
    weapon_reference,
)
from zmforge.errors import BlueprintError


#: Straight off the linker's own
#: ``usermaps/zm_locprobe/zone_source/english/assetinfo/zm_locprobe.csv``
#: after a clean link: ``(str file, reference, asset name)``.
#: The third pair is the one that matters -- the prefix is added even when
#: the reference already starts with it, so there is no de-duplication rule
#: to imitate and the shorter spelling would name an asset nobody packed.
MEASURED_NAMES = [
    ("zmf_locprobe.str", "ZMFORGE_LOCPROBE", "ZMF_LOCPROBE_ZMFORGE_LOCPROBE"),
    ("zmforge.str", "ZMFORGE_BIG_GUN", "ZMFORGE_ZMFORGE_BIG_GUN"),
    ("zmforge.str", "BIG_GUN_TWO", "ZMFORGE_BIG_GUN_TWO"),
    ("zmforge.str", "ZOMBIE_WEAPONCOSTONLYFILL", "ZMFORGE_ZOMBIE_WEAPONCOSTONLYFILL"),
]


# --------------------------------------------------------------------------
# The linker's own naming rule
# --------------------------------------------------------------------------
@pytest.mark.parametrize("str_file, reference, expected", MEASURED_NAMES)
def test_the_measured_asset_naming_rule(str_file, reference, expected) -> None:
    """``<FILE>_<REFERENCE>``, uppercased, prefix always added."""
    assert asset_name(str_file, reference) == expected


def test_the_extension_is_optional_and_changes_nothing() -> None:
    """The asset is named after the file's stem, so both spellings agree.

    ``layout.localized_strings`` adds the suffix and the blueprint does not,
    and an asset name that disagreed between them would be a prompt that is
    blank in game and correct in every test.
    """
    for str_file, reference, expected in MEASURED_NAMES:
        assert asset_name(str_file.removesuffix(".str"), reference) == expected


# --------------------------------------------------------------------------
# The file
# --------------------------------------------------------------------------
def test_the_str_file_has_the_shape_the_shipped_one_has() -> None:
    """Header, entries, ``ENDMARKER``, CRLF: ``zm_abbey.str``'s own shape."""
    text = render_str_file(
        [LocalizedString("BUY_SHOTGUN_PUMP", "Hold ^3[{+activate}]^7 to buy X")]
    )
    assert text.startswith('VERSION\t\t\t"1"\r\n')
    assert '\r\nCONFIG\t\t\t\t"C:\\projects\\cod\\t7\\bin\\StringEd.cfg"\r\n' in text
    assert '\r\nFILENOTES\t\t\t""\r\n' in text
    assert "REFERENCE\t\t\tBUY_SHOTGUN_PUMP\r\n" in text
    assert 'LANG_ENGLISH\t\t"Hold ^3[{+activate}]^7 to buy X"\r\n' in text
    assert text.endswith("ENDMARKER\r\n")
    assert text.count("\n") == text.count("\r\n")


def test_a_duplicate_reference_is_refused() -> None:
    """The linker keeps one of them and says nothing about the other."""
    entry = LocalizedString("BUY_SHOTGUN_PUMP", "one")
    with pytest.raises(ValueError):
        render_str_file([entry, LocalizedString("BUY_SHOTGUN_PUMP", "two")])


@pytest.mark.parametrize(
    "reference, english",
    [
        ("buy_shotgun_pump", "lower case survives no round trip"),
        ("BUY SHOTGUN", "a space is not in the asset-name alphabet"),
        ("BUY_OK", "two\r\nlines"),
        ("BUY_OK", "two\nlines"),
        ("BUY_OK", 'a " ends the text early'),
    ],
)
def test_an_entry_that_cannot_survive_the_format_is_refused(reference, english) -> None:
    with pytest.raises(ValueError):
        LocalizedString(reference, english)


# --------------------------------------------------------------------------
# A map that renames nothing
# --------------------------------------------------------------------------
def test_a_plan_with_no_renames_emits_the_script_it_always_emitted() -> None:
    """Byte-identical: renaming is opt-in and costs an untouched map nothing."""
    plan = ScriptPlan(map_name="zm_x", weapon_table="gamedata/weapons/zm/zm_x.csv")
    before = render_server_script(plan)
    plan.weapon_hints = [("shotgun_pump", "ZM_X_BUY_SHOTGUN_PUMP")]
    after = render_server_script(plan)
    assert "triggerstring" not in before
    assert ".hint" not in before
    assert after != before
    plan.weapon_hints = []
    assert render_server_script(plan) == before


def test_a_map_that_renames_without_pricing_still_owns_the_hook() -> None:
    """The loader is how the map gets a word in after the tables load.

    A rename with no re-price has no table of its own, so the loader loads
    only Treyarch's -- which it must, because winning the hook is what stops
    the framework's own loader running (``zm_usermap.gsc:135``).
    """
    plan = ScriptPlan(map_name="zm_x")
    plan.weapon_hints = [("shotgun_pump", "ZM_X_BUY_SHOTGUN_PUMP")]
    text = render_server_script(plan)
    assert "level._zombie_custom_add_weapons = &load_weapon_table;" in text
    assert text.count("load_weapon_spec_from_table") == 1
    assert "zm_levelcommon_weapons.csv" in text
    assert '#using scripts\\zm\\_zm_weapons;' in text
    assert 'level.zombie_weapons[ GetWeapon( "shotgun_pump" ) ].hint' in text


def test_two_names_for_one_weapon_are_refused() -> None:
    """One hint per weapon in game, so one name per weapon here.

    ``level.zombie_weapons`` is keyed by weapon, so the second name would
    replace the first on every buy that sells it, whichever wall it is on.
    """
    bp = Blueprint("zm_x")
    bp.rename_weapon_prompt("shotgun_pump", "THE BIG GUN")
    bp.rename_weapon_prompt("shotgun_pump", "THE BIG GUN")  # idempotent
    assert len(bp.script.weapon_hints) == 1
    with pytest.raises(BlueprintError):
        bp.rename_weapon_prompt("shotgun_pump", "THE OTHER BIG GUN")
    with pytest.raises(BlueprintError):
        bp.rename_weapon_prompt("smg_fastfire", "  ")


def test_the_file_is_committed_where_the_linker_reads_it(tmp_path) -> None:
    r"""``share\raw\english\localizedstrings\<map>.str``, and the zone with it.

    The path is the linker's, not a choice: its own ``.deps`` for the probe
    usermap named that file as the one it had read [measured].  A
    ``.str`` anywhere else links exactly as though the map shipped none, and
    the prompt is blank in game with nothing in the log about it.
    """
    from zmforge import Project

    project = Project.create("zm_x", tmp_path, blueprint=_renaming_blueprint("zm_x"))
    project.commit(force=True)

    path = project.paths()["localized_strings"]
    assert path.parent == tmp_path / "share" / "raw" / "english" / "localizedstrings"
    assert path.name == "zm_x.str"
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    assert "THE BIG GUN" in text
    assert _parse_str(text)["BUY_SHOTGUN_PUMP"] == weapon_prompt("THE BIG GUN")

    manifest = project.paths()["manifest"].read_text(encoding="utf-8")
    assert "localize,zm_x" in manifest
    script = project.paths()["server_script"].read_text(encoding="utf-8")
    assert '&"ZM_X_BUY_SHOTGUN_PUMP"' in script


def test_a_map_that_renames_nothing_writes_no_str_file(tmp_path) -> None:
    """Declaring an asset a map does not ship is a link the linker fails."""
    from zmforge import Project

    blueprint = _renaming_blueprint("zm_y", rename=False)
    # The gamble machine (Z87) writes lines of its own;
    # this test is about renames, so the map opts out of it.
    blueprint.signature_gamble = False
    project = Project.create("zm_y", tmp_path, blueprint=blueprint)
    project.commit(force=True)
    assert not project.paths()["localized_strings"].exists()
    manifest = project.paths()["manifest"].read_text(encoding="utf-8")
    assert "localize" not in manifest


def _renaming_blueprint(name: str, *, rename: bool = True) -> Blueprint:
    """A committable map, with and without a renamed prompt.

    The prank recipe rather than a hand-built blueprint: it is the smallest
    map in the repository that passes the file checks, so what these two
    tests measure is the rename and not a map missing a zone.
    """
    from zmforge.recipes import prank_map

    blueprint = prank_map(name)
    if rename:
        blueprint.rename_weapon_prompt("shotgun_pump", "THE BIG GUN")
    return blueprint


def _parse_str(text: str) -> dict[str, str]:
    """Read a ``.str`` back: ``{reference: english}``, in file order.

    Deliberately not the emitter's own data: a reader written against the
    format catches a file that renders and does not parse.
    """
    entries: dict[str, str] = {}
    reference = None
    assert text.rstrip().endswith("ENDMARKER")
    for line in text.replace("\r\n", "\n").split("\n"):
        key, _, value = line.partition("\t")
        value = value.strip()
        if key == "REFERENCE":
            reference = value
        elif key == "LANG_ENGLISH":
            assert reference is not None, "a string with no reference above it"
            assert value.startswith('"') and value.endswith('"')
            entries[reference] = value[1:-1]
            reference = None
    return entries
