"""HUD images a map packs itself: the perk-icon route (zmforge.texture.hud_icons).

What is tested is the text and files a commit writes and the SQL a
registration does.  Whether the linker converts the entries and the widget
draws them has not been measured -- that needs a link and a play session.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from zmforge import Project
from zmforge.blueprint.model import Blueprint
from zmforge.errors import BlueprintError
from zmforge.script.perks import DIVE_TO_NUKE_ICON, TOMBSTONE_ICON, CustomPerk, points_each_round
from zmforge.texture import hud_icons
from zmforge.texture.gdtdb import parse_gdt


def _fake_gdt_db(path: Path) -> None:
    """The four tables the registrar touches, with two tiny field lists."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE _gdf (PK_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, md5 TEXT);
        CREATE TABLE _gdt (PK_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                           bOpenForEdit INT DEFAULT 0, timestamp INTEGER DEFAULT 0);
        CREATE TABLE _entity (PK_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                              iGdtSeqNum INT, FK_parent_id INTEGER, FK_gdf INTEGER,
                              FK_gdt INTEGER, _gdt_linenum INT, bExport INT DEFAULT 0);
        CREATE TABLE _meta (_name TEXT, _key TEXT, _type TEXT, _default TEXT,
                            _min NUMERIC, _max NUMERIC, _enums TEXT, _index INTEGER);
        CREATE TABLE image (PK_id INTEGER PRIMARY KEY, _precalc_md5 TEXT, _name TEXT,
                            _derived_bits BLOB, baseImage TEXT, semantic TEXT, spare TEXT);
        CREATE TABLE material (PK_id INTEGER PRIMARY KEY, _precalc_md5 TEXT, _name TEXT,
                               _derived_bits BLOB, colorMap TEXT, detailMap TEXT,
                               surfaceType TEXT);
        INSERT INTO _gdf (name) VALUES ('image'), ('material');
        """
    )
    for index, key in enumerate(("baseImage", "semantic", "spare")):
        connection.execute(
            "INSERT INTO _meta VALUES ('image', ?, 'string', '', 0, 0, '', ?)", (key, index)
        )
    for index, key in enumerate(("colorMap", "detailMap", "surfaceType")):
        connection.execute(
            "INSERT INTO _meta VALUES ('material', ?, 'string', '', 0, 0, '', ?)", (key, index)
        )
    connection.commit()
    connection.close()


STOCK_ENTRY = "t7_hud_zm_powerup_deathmachine"


@pytest.mark.parametrize("key", sorted(hud_icons.ART))
def test_every_piece_of_art_is_a_square_rgba_png_with_a_transparent_corner(key) -> None:
    image = Image.open(io.BytesIO(hud_icons.art_png(key)))
    assert image.format == "PNG"
    assert image.size == (hud_icons.ICON_SIZE, hud_icons.ICON_SIZE)
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0))[3] == 0
    # something is drawn in the middle
    assert image.getpixel((hud_icons.ICON_SIZE // 2, hud_icons.ICON_SIZE // 2))[3] == 255


def test_the_gdt_entry_is_the_stock_hud_image_with_two_fields_changed() -> None:
    entries = parse_gdt(hud_icons.hud_gdt_document("zm_x", ["specialty_tombstone_zombies"]))
    assert [(e.name, e.gdf) for e in entries] == [("specialty_tombstone_zombies", "image.gdf")]
    fields = entries[0].fields
    assert fields["baseImage"] == "texture_assets\\\\zmforge_hud\\\\zm_x\\\\specialty_tombstone_zombies.png"
    assert fields["semantic"] == "2d"
    assert fields["coreSemantic"] == "Linear4ch"
    assert fields["compressionMethod"] == "compressed"
    assert fields["noMipMaps"] == "1"


def test_the_template_matches_the_installs_stock_entry_when_the_install_is_here() -> None:
    stock = Path("<bo3-wine>/tools/texture_assets/images_ui_tu.gdt")
    if not stock.is_file():
        pytest.skip("no mod tools install configured")
    ours = parse_gdt(hud_icons.hud_gdt_document("zm_x", ["n"]))[0].fields
    theirs = next(e for e in parse_gdt(stock.read_text(encoding="utf-8", errors="replace"))
                  if e.name == STOCK_ENTRY and e.gdf == "image.gdf").fields
    assert {k: v for k, v in ours.items() if k != "baseImage"} == {
        k: v for k, v in theirs.items() if k != "baseImage"
    }


def test_a_perk_without_icon_art_ships_no_image() -> None:
    bp = Blueprint("zm_x")
    bp.declare_perk(CustomPerk("plain", "PLAIN", 500, points_each_round(10)))
    assert bp.hud_images == {}
    assert not any(ref.prefix == "image" for ref in bp.assets)


def test_a_perk_with_icon_art_ships_its_slots_image_and_declares_it() -> None:
    bp = Blueprint("zm_x")
    bp.declare_perk(
        CustomPerk("art", "ART", 500, points_each_round(10), icon=DIVE_TO_NUKE_ICON, icon_art="ticket")
    )
    assert list(bp.hud_images) == [DIVE_TO_NUKE_ICON.image]
    assert f"image,{DIVE_TO_NUKE_ICON.image}" in [ref.line for ref in bp.assets]


def test_icon_art_needs_a_slot_and_a_known_picture() -> None:
    with pytest.raises(ValueError, match="takes no slot"):
        CustomPerk("a", "A", 500, points_each_round(10), icon=None, icon_art="ticket")
    with pytest.raises(ValueError, match="no HUD art"):
        CustomPerk("a", "A", 500, points_each_round(10), icon=TOMBSTONE_ICON, icon_art="nope")


def test_two_pictures_under_one_name_are_refused() -> None:
    bp = Blueprint("zm_x")
    bp.ship_hud_image("zmf_x", hud_icons.art_png("ticket"))
    bp.ship_hud_image("zmf_x", hud_icons.art_png("ticket"))  # same bytes: fine
    with pytest.raises(BlueprintError):
        bp.ship_hud_image("zmf_x", hud_icons.art_png("licence_plate"))
    with pytest.raises(BlueprintError):
        bp.ship_hud_image("zmf_y", b"not a png")


def test_registration_writes_one_image_row_per_icon_and_is_idempotent(tmp_path) -> None:
    tools = tmp_path / "tools"
    (tools / "gdtdb").mkdir(parents=True)
    _fake_gdt_db(tools / "gdtdb" / "gdt.db")
    assert hud_icons.register(tools, "zm_x") is None  # nothing to register
    gdt = tools / hud_icons.gdt_relative("zm_x")
    gdt.parent.mkdir(parents=True)
    names = [TOMBSTONE_ICON.image, DIVE_TO_NUKE_ICON.image]
    gdt.write_text(hud_icons.hud_gdt_document("zm_x", names), encoding="utf-8")
    hud_icons.register(tools, "zm_x")
    hud_icons.register(tools, "zm_x")
    connection = sqlite3.connect(tools / "gdtdb" / "gdt.db")
    rows = connection.execute("select _name, semantic from image order by _name").fetchall()
    assert rows == sorted((n, "2d") for n in names)
    assert connection.execute("select count(*) from _gdt").fetchone()[0] == 1


def test_the_link_check_reads_the_links_own_assetlist(tmp_path) -> None:
    tools = tmp_path
    gdt = tools / hud_icons.gdt_relative("zm_x")
    gdt.parent.mkdir(parents=True)
    gdt.write_text(hud_icons.hud_gdt_document("zm_x", ["a_img", "b_img"]), encoding="utf-8")
    listing = tools / "usermaps" / "zm_x" / "zone_source" / "all" / "assetlist" / "zm_x.csv"
    listing.parent.mkdir(parents=True)
    listing.write_text("image,a_img\nimage,black\n", encoding="utf-8")
    assert hud_icons.packed(tools, "zm_x", 0.0) == (["a_img"], ["b_img"])
    # an assetlist older than the link does not count
    assert hud_icons.packed(tools, "zm_x", listing.stat().st_mtime + 10) == ([], ["a_img", "b_img"])


def test_a_commit_writes_the_pngs_the_gdt_and_the_zone_lines(tmp_path) -> None:
    bp = Blueprint("zm_x")
    bp.ship_hud_image("zmf_probe_icon", hud_icons.art_png("licence_plate"))
    project = Project.create("zm_x", tmp_path, blueprint=bp)
    project.commit(force=True, loading_screen=False)
    paths = project.paths()
    png = paths["hud_image:zmf_probe_icon"]
    assert png == tmp_path / "texture_assets/zmforge_hud/zm_x/zmf_probe_icon.png"
    with Image.open(png) as image:
        assert image.size == (hud_icons.ICON_SIZE, hud_icons.ICON_SIZE)
    assert [e.name for e in parse_gdt(paths["hud_gdt"].read_text(encoding="utf-8"))] == [
        "zmf_probe_icon"
    ]
    assert "image,zmf_probe_icon" in paths["manifest"].read_text(encoding="utf-8").splitlines()
