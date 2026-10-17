"""The map's own weapon table: custom prices, custom guns, and the checks.

Everything here is about a failure that costs a play session to find, because
none of it fails a build: a price that only half arrives, a table row naming a
weapon that does not exist, a collision file nobody wrote.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint import Blueprint
from zmforge.blueprint.script_plan import ScriptPlan
from zmforge.blueprint.weapons import CustomWeapon
from zmforge.emit.scripts import render_client_script, render_server_script
from zmforge.emit.weapons import (
    COST_COLUMN,
    STOCK_TABLE,
    WEAPON_TABLE_COLUMNS,
    parse_table,
    table_asset,
    weapon_table_text,
)
from zmforge.errors import ForgeError
from zmforge.spatial import Facing, Point
from zmforge.texture.gdtdb import GDF_IDS
from zmforge.verify import blueprint as check_blueprint
from zmforge.verify.files import (
    check_prop_collision_files,
    check_weapon_table,
    check_weapon_table_wiring,
)

STOCK = (
    ",".join(WEAPON_TABLE_COLUMNS)
    + "\n"
    + "pistol_burst,pistol_burst_upgraded,,500,pistol,,,,,FALSE,FALSE,FALSE,,,"
    "FALSE,TRUE,pistol,,,\n"
    + "bowie_knife,,,3000,wpck_bowie,,,,,FALSE,FALSE,,,,FALSE,FALSE,special,,,\n"
)


def _plan(table: str | None) -> ScriptPlan:
    plan = ScriptPlan("zm_price_probe")
    plan.zones = ["start"]
    plan.weapon_table = table
    return plan


# --------------------------------------------------------------------------
# The default is the map that was emitted before any of this existed
# --------------------------------------------------------------------------
def test_a_map_that_prices_nothing_emits_no_table_and_no_extra_line() -> None:
    blueprint = Blueprint("zm_price_probe")
    blueprint.place_wall_weapon("bowie", Point(0, 0, 0), Facing.NORTH)
    assert blueprint.script.weapon_table is None
    assert blueprint.ships_weapon_table() is False
    assert blueprint.assets == []
    server = render_server_script(blueprint.script)
    client = render_client_script(blueprint.script)
    assert "_zombie_custom_add_weapons" not in server
    assert "load_weapon_spec_from_table" not in server
    assert "load_weapon_spec_from_table" not in client
    assert "_zm_weapons" not in server


def test_a_price_turns_the_table_on_and_declares_it() -> None:
    blueprint = Blueprint("zm_price_probe")
    blueprint.place_wall_weapon("bowie", Point(0, 0, 0), Facing.NORTH, price=1337)
    assert blueprint.script.weapon_table == table_asset("zm_price_probe")
    # The slug is not the weapon: the bowie prefab sells bowie_knife.
    assert blueprint.weapon_price_table() == {"bowie_knife": 1337}
    assert [ref.line for ref in blueprint.assets] == [
        "stringtable,gamedata/weapons/zm/zm_price_probe_weapons.csv"
    ]


def test_a_negative_price_is_refused_at_the_call() -> None:
    blueprint = Blueprint("zm_price_probe")
    with pytest.raises(Exception):
        blueprint.place_wall_weapon("bowie", Point(0, 0, 0), Facing.NORTH, price=-1)


# --------------------------------------------------------------------------
# The table itself
# --------------------------------------------------------------------------
def test_a_repriced_row_is_the_stock_row_with_one_column_changed() -> None:
    text = weapon_table_text({"pistol_burst": 1337}, [], STOCK)
    rows = parse_table(text)
    assert rows[0] == list(WEAPON_TABLE_COLUMNS)
    assert len(rows) == 2
    row = rows[1]
    stock = parse_table(STOCK)[1]
    assert row[COST_COLUMN] == "1337"
    assert stock[COST_COLUMN] == "500"
    # Everything else survives: the upgrade, the voice-over, the class.
    assert [f for i, f in enumerate(row) if i != COST_COLUMN] == [
        f for i, f in enumerate(stock) if i != COST_COLUMN
    ]


def test_a_price_for_a_weapon_the_install_does_not_have_is_refused() -> None:
    with pytest.raises(ForgeError):
        weapon_table_text({"shotgun_olympia": 500}, [], STOCK)


def test_a_custom_weapon_row_states_every_column() -> None:
    weapon = CustomWeapon("zmf_probe_gun", 4200, weapon_class="smg")
    text = weapon_table_text({}, [weapon.table_row()], STOCK)
    row = parse_table(text)[1]
    assert len(row) == len(WEAPON_TABLE_COLUMNS)
    assert row[0] == "zmf_probe_gun"
    assert row[COST_COLUMN] == "4200"
    assert weapon.asset_name == "zmf_probe_gun_zm"


# --------------------------------------------------------------------------
# What the two scripts have to say
# --------------------------------------------------------------------------
def test_the_hook_is_assigned_before_the_framework_entry() -> None:
    server = render_server_script(_plan(table_asset("zm_price_probe")))
    hook = server.index("level._zombie_custom_add_weapons")
    assert hook < server.index("zm_usermap::main();")
    # The stock table first, then the map's own: the second load replaces a
    # row rather than adding one, so skipping the first empties the level.
    loader = server[server.index("function load_weapon_table()") :]
    assert loader.index(STOCK_TABLE) < loader.index("zm_price_probe_weapons.csv")


def test_the_client_loads_the_same_table_after_the_entry() -> None:
    client = render_client_script(_plan(table_asset("zm_price_probe")))
    body = client[client.index("function main()") :]
    assert body.index("zm_usermap::main();") < body.index("zm_price_probe_weapons.csv")


# --------------------------------------------------------------------------
# W4: half a price is worse than none
# --------------------------------------------------------------------------
def _manifest(*lines: str) -> str:
    return "\n".join([">class,zm_mod_level", *lines]) + "\n"


def test_w4_fires_when_the_client_half_is_missing() -> None:
    plan = _plan(table_asset("zm_price_probe"))
    server = render_server_script(plan)
    client = render_client_script(_plan(None))
    report = check_weapon_table_wiring(
        _manifest("stringtable,gamedata/weapons/zm/zm_price_probe_weapons.csv"),
        server,
        client,
        map_name="zm_price_probe",
    )
    assert [f.code for f in report.errors] == ["W4"]
    assert "charged this map's price and shown" in report.errors[0].message


def test_w4_fires_when_the_manifest_does_not_declare_the_table() -> None:
    plan = _plan(table_asset("zm_price_probe"))
    report = check_weapon_table_wiring(
        _manifest(),
        render_server_script(plan),
        render_client_script(plan),
        map_name="zm_price_probe",
    )
    assert {f.code for f in report.errors} == {"W4"}


def test_w4_passes_the_scripts_this_package_emits() -> None:
    plan = _plan(table_asset("zm_price_probe"))
    report = check_weapon_table_wiring(
        _manifest("stringtable,gamedata/weapons/zm/zm_price_probe_weapons.csv"),
        render_server_script(plan),
        render_client_script(plan),
        map_name="zm_price_probe",
    )
    assert report.findings == []


# --------------------------------------------------------------------------
# W5: the one the linker cannot catch
# --------------------------------------------------------------------------
def test_w5_fires_on_a_row_naming_a_weapon_that_does_not_exist() -> None:
    text = weapon_table_text({}, [CustomWeapon("zmf_ghost_gun", 500).table_row()], STOCK)
    report = check_weapon_table(text, _manifest())
    assert [f.code for f in report.errors] == ["W5"]
    assert "zmf_ghost_gun" in report.errors[0].message


def test_w5_accepts_a_row_whose_weapon_the_manifest_declares() -> None:
    text = weapon_table_text({}, [CustomWeapon("zmf_ghost_gun", 500).table_row()], STOCK)
    report = check_weapon_table(text, _manifest("weapon,zmf_ghost_gun_zm"))
    assert report.findings == []


def test_w5_fires_on_a_cost_int_would_read_as_free() -> None:
    rows = parse_table(weapon_table_text({"pistol_burst": 1337}, [], STOCK))
    rows[1][COST_COLUMN] = "free"
    text = "\n".join(",".join(row) for row in rows) + "\n"
    report = check_weapon_table(text, _manifest())
    assert any("free" in f.message for f in report.errors)


def test_w5_model_side_refuses_a_price_for_a_weapon_this_level_lacks() -> None:
    blueprint = Blueprint("zm_price_probe")
    blueprint.set_weapon_price("shotgun_olympia", 500)
    codes = [f.code for f in check_blueprint(blueprint).errors]
    assert "W5" in codes


# --------------------------------------------------------------------------
# W6, and the one entry that made the registrar handle weapons
# --------------------------------------------------------------------------
def test_w6_says_when_a_custom_weapon_names_no_definition() -> None:
    blueprint = Blueprint("zm_price_probe")
    blueprint.add_custom_weapon(CustomWeapon("zmf_probe_gun", 4200))
    report = check_blueprint(blueprint)
    assert any(f.code == "W6" for f in report.warnings)


def test_the_asset_database_registrar_handles_a_weapon() -> None:
    assert GDF_IDS["bulletweapon.gdf"] == "bulletweapon"


# --------------------------------------------------------------------------
# Z27: a collision file the entry names and nobody wrote
# --------------------------------------------------------------------------
_GDT = '''{
\t"zmf_prop_donut" ( "xmodel.gdf" )
\t{
\t\t"BulletCollisionFile" "zm_x\\\\zmf_prop_donut_col.XMODEL_BIN"
\t\t"BulletCollisionLOD" "Custom"
\t\t"CollisionMap" "zmf_prop_donut.map"
\t\t"filename" "zm_x\\\\zmf_prop_donut.XMODEL_BIN"
\t}
}
'''


def test_z27_fires_on_a_collision_file_that_is_not_there(tmp_path) -> None:
    model_export = tmp_path / "model_export"
    (model_export / "zm_x").mkdir(parents=True)
    collmaps = tmp_path / "collmaps"
    collmaps.mkdir()
    report = check_prop_collision_files(
        _GDT, model_export=model_export, collmaps=collmaps
    )
    assert [f.code for f in report.errors] == ["Z27", "Z27"]


def test_z27_passes_once_both_files_exist(tmp_path) -> None:
    model_export = tmp_path / "model_export"
    (model_export / "zm_x").mkdir(parents=True)
    (model_export / "zm_x" / "zmf_prop_donut_col.XMODEL_BIN").write_bytes(b"\0")
    collmaps = tmp_path / "collmaps"
    collmaps.mkdir()
    (collmaps / "zmf_prop_donut.map").write_text("iwmap 4\n")
    report = check_prop_collision_files(
        _GDT, model_export=model_export, collmaps=collmaps
    )
    assert report.findings == []
