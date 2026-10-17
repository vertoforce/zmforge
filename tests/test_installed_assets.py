"""Z13: a map may only place models and prefabs the install can resolve.

Background: a map that places ``zombie_sign_please_wait`` fails to compile
with ``Missing xmodel 'zombie_sign_please_wait'`` (cod2map64).  The name
appears in shipped ``zm_giant.map``; the install declares no such asset.  The
ledger these tests read records what a probe map compiled with the mod
tools resolved, and ``scripts/scan-local-tools.py`` refreshes its list of
models that compile but do not link.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint import catalogue
from zmforge.blueprint.installed import LEDGER_PATH, judge_misc_model, load_ledger
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Point
from zmforge.verify.model import check_blueprint


def _catalogue_prefabs() -> set[str]:
    found: set[str] = set()
    for value in vars(catalogue).values():
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                if item.startswith("_prefabs/") and item.endswith(".map"):
                    found.add(item)
            elif isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, (list, tuple, set, frozenset)):
                stack.extend(item)
    return found


def _catalogue_models() -> set[str]:
    return set(catalogue.STOCK_PROPS.values()) | set(catalogue.DOOR_MODELS) | set(
        getattr(catalogue, "PROP_PALETTE", ())
    )


def test_the_ledger_is_present_and_measured() -> None:
    ledger = load_ledger()
    assert ledger is not None, f"{LEDGER_PATH} is missing; it ships with zmforge"
    assert len(ledger.xmodels_declared) >= 1500, len(ledger.xmodels_declared)
    assert len(ledger.prefabs) >= 700, len(ledger.prefabs)
    assert ledger.misc_model_ok and ledger.misc_model_missing
    # The recorded defect stays recorded: it is what this check exists for.
    assert judge_misc_model("zombie_sign_please_wait", ledger) == "missing"
    assert judge_misc_model("zmforge_probe_definitely_not_a_model", ledger) == "missing"


def test_every_catalogue_model_was_probed_and_compiles() -> None:
    """Every stock model the code can place has cod2map64's own approval."""
    ledger = load_ledger()
    assert ledger is not None
    unverified = sorted(n for n in _catalogue_models() if n not in ledger.misc_model_ok)
    assert not unverified, f"not probed as misc_model, or missing: {unverified}"
    assert not (_catalogue_models() & ledger.misc_model_missing)


def test_every_catalogue_prefab_is_shipped() -> None:
    ledger = load_ledger()
    assert ledger is not None
    prefabs = _catalogue_prefabs()
    assert prefabs, "the catalogue names no prefab at all?"
    absent = sorted(p for p in prefabs if not ledger.has_prefab(p))
    assert not absent, absent


def test_z13_refuses_the_model_the_compiler_refused() -> None:
    blueprint = three_room_map("zm_z13")
    blueprint.place_props([("zombie_sign_please_wait", Point(0.0, 0.0, 64.0), 0.0)])
    report = check_blueprint(blueprint)
    z13 = [f for f in report.errors if f.code == "Z13"]
    assert z13, report
    assert "zombie_sign_please_wait" in z13[0].message


def test_z13_warns_only_for_a_name_nobody_has_probed() -> None:
    blueprint = three_room_map("zm_z13_unknown")
    blueprint.place_props([("p7_probably_real_but_unprobed", Point(0.0, 0.0, 64.0), 0.0)])
    report = check_blueprint(blueprint)
    assert not [f for f in report.errors if f.code == "Z13"]
    assert [f for f in report.warnings if f.code == "Z13"]


def test_z13_degrades_to_a_warning_without_a_ledger(monkeypatch) -> None:
    import zmforge.blueprint.installed as installed

    monkeypatch.setattr(installed, "load_ledger", lambda path=None: None)
    blueprint = three_room_map("zm_z13_noledger")
    blueprint.place_props([("zombie_sign_please_wait", Point(0.0, 0.0, 64.0), 0.0)])
    report = check_blueprint(blueprint)
    assert not [f for f in report.errors if f.code == "Z13"]
    assert any("no installed-assets ledger" in f.message for f in report.warnings)


# ---- models that compile but do not link (the install lacks their files) ----

_GDT = '''{
\t"p7_whole" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\set\\\\p7_whole_lod0.XMODEL_BIN"
\t\t"BulletCollisionFile" ""
\t}
\t"p7_no_col" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\set\\\\p7_no_col_lod0.XMODEL_BIN"
\t\t"BulletCollisionFile" "t7_props\\\\old_set\\\\p7_no_col_col.XMODEL_BIN"
\t}
\t"p7_unused_lod4" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\set\\\\p7_whole_lod0.XMODEL_BIN"
\t\t"BulletCollisionLOD" "None"
\t\t"BulletCollisionFile" "t7_props\\\\set\\\\gone_col.XMODEL_BIN"
\t\t"lod4Dist" "0"
\t\t"lod4File" "t7_props\\\\set\\\\gone_lod4.XMODEL_BIN"
\t\t"mediumLodDist" "400"
\t\t"autogenMediumLod" "1"
\t\t"mediumLod" "t7_props\\\\set\\\\gone_lod1.XMODEL_BIN"
\t}
\t"p7_used_lod1" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\set\\\\p7_whole_lod0.XMODEL_BIN"
\t\t"mediumLodDist" "400"
\t\t"autogenMediumLod" "0"
\t\t"mediumLod" "t7_props\\\\set\\\\gone_lod1.XMODEL_BIN"
\t}
\t"some_image" ( "image.gdf" )
\t{
\t\t"baseImage" "t7_props\\\\set\\\\missing.tif"
\t}
}
'''


def test_scan_unlinkable_names_the_model_whose_collision_file_is_absent(tmp_path) -> None:
    from zmforge.blueprint.installed import scan_unlinkable

    d = tmp_path / "model_export" / "t7_props" / "SET"  # Wine is case-insensitive
    d.mkdir(parents=True)
    (d / "p7_whole_lod0.xmodel_bin").write_bytes(b"")
    (d / "p7_no_col_lod0.XMODEL_BIN").write_bytes(b"")
    (d / "set.gdt").write_text(_GDT, encoding="utf-8")
    found = scan_unlinkable(tmp_path)
    # An unused lod4 (distance 0), an autogenerated LOD and a collision file
    # with collision LOD "None" are never opened (p7_crate_plastic_tech_02
    # linked that way); a hand-made LOD in use is.
    assert found == {"p7_no_col": "t7_props/old_set/p7_no_col_col.XMODEL_BIN",
                     "p7_used_lod1": "t7_props/set/gone_lod1.XMODEL_BIN"}


def test_z13_refuses_the_models_that_stopped_the_local_link() -> None:
    """Maps placing these (tablet col, rubber wires lod0, beer glass lod0)
    compile and bake, then the linker stops."""
    ledger = load_ledger()
    assert ledger is not None and ledger.xmodels_unlinkable, "run scripts/scan-local-tools.py"
    for name in ("p7_desk_metal_military_03_tablet", "p7_wires_electrical_rubber_02",
                 "p6_bar_beer_glass"):
        assert judge_misc_model(name, ledger) == "unlinkable", name
    blueprint = three_room_map("zm_z13_link")
    blueprint.place_props([("p7_desk_metal_military_03_tablet", Point(0.0, 0.0, 64.0), 0.0)])
    z13 = [f for f in check_blueprint(blueprint).errors if f.code == "Z13"]
    assert z13 and "will not link" in z13[0].message and "_col" in z13[0].message


def test_unlinkable_ledger_matches_the_local_tools_when_present() -> None:
    from zmforge.blueprint.installed import DEFAULT_LOCAL_TOOLS, scan_unlinkable

    if not (DEFAULT_LOCAL_TOOLS / "model_export").is_dir():
        pytest.skip("no mod tools install configured")
    ledger = load_ledger()
    assert ledger is not None
    drift = sorted(set(scan_unlinkable(DEFAULT_LOCAL_TOOLS)) ^ set(ledger.xmodels_unlinkable))
    assert not drift, f"rerun scripts/scan-local-tools.py: {drift[:10]}"


def _model_bin(*materials: str) -> bytes:
    """An ``*LZ4*`` model file whose payload carries MATERIAL chunks."""
    import struct

    from zmforge.render.propfix import write_model_bin

    payload = b"junk"
    for i, name in enumerate(materials):
        raw = name.encode() + b"\x00"
        payload += struct.pack("<HH", 0xA700, i) + raw + b"\x00" * (-len(raw) % 4)
        payload += b"Blinn\x00\x00\x00"
    return write_model_bin(payload)


_GDT_MATERIALS = '''{
\t"p7_grass_ok" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\grass\\\\grass_ok_lod0.XMODEL_BIN"
\t}
\t"p7_grass_skinned" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\grass\\\\grass_ok_lod0.XMODEL_BIN"
\t\t"skinOverride" "mtl_grass mtl_tussock_dry\\r\\n"
\t}
\t"p7_decal_door" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\grass\\\\door_lod0.XMODEL_BIN"
\t}
\t"mtl_grass" ( "material.gdf" )
\t{
\t\t"colorMap" "i_grass_c"
\t\t"cosinePowerMap" "i_not_declared_anywhere_g"
\t}
\t"mtl_tussock" ( "material.gdf" )
\t{
\t\t"colorMap" "i_tussock_c"
\t\t"normalMap" "i_tussock_n"
\t}
\t"mtl_tussock_dry" [ "mtl_tussock" ]
\t{
\t\t"occMap" ""
\t}
\t"mtl_decal" ( "material.gdf" )
\t{
\t\t"colorMap" "i_grass_c"
\t\t"alphaRevealMap" "i_tussock_c"
\t}
\t"i_grass_c" ( "image.gdf" )
\t{
\t\t"baseImage" "model_export\\\\t7_props\\\\grass\\\\Grass_C.tif"
\t}
\t"i_tussock_c" ( "image.gdf" )
\t{
\t\t"baseImage" "model_export\\\\t7_props\\\\tussock\\\\tussock_c.tif"
\t}
\t"i_tussock_n" ( "image.gdf" )
\t{
\t\t"baseImage" "model_export\\\\t7_props\\\\tussock\\\\tussock_n.tif"
\t}
}
'''


def test_scan_unlinkable_follows_materials_to_their_images(tmp_path) -> None:
    """``p7_foliage_grass_dry_03``: its model files were all there, but its
    ``skinOverride`` material derives from the tussock material, whose colour
    and normal images the install lacks, so a map placing it fails to link
    (``image 'i_mtl_p7_foliage_grass_tussock_dry_c' is missing``).
    ``p7_foliage_grass_dry_01`` (same model files, no override) links."""
    from zmforge.blueprint.installed import bin_materials, scan_unlinkable

    d = tmp_path / "model_export" / "t7_props" / "grass"
    d.mkdir(parents=True)
    (d / "grass_ok_lod0.xmodel_bin").write_bytes(_model_bin("mtl_grass"))
    (d / "door_lod0.xmodel_bin").write_bytes(_model_bin("mtl_decal"))
    (d / "grass_c.tif").write_bytes(b"")  # case differs from the GDT: Wine matches it
    (tmp_path / "model_export" / "mats.gdt").write_text(_GDT_MATERIALS, encoding="utf-8")
    assert bin_materials(_model_bin("mtl_grass", "mtl_decal")) == ["mtl_grass", "mtl_decal"]
    assert bin_materials(b"") == []
    found = scan_unlinkable(tmp_path)
    # A missing image the material type does not sample (a decal's
    # alphaRevealMap: the stock buy door links that way) and an image no GDT
    # declares (a stock one) are not failures.
    assert found == {
        "p7_grass_skinned": "mtl_tussock_dry: model_export/t7_props/tussock/tussock_c.tif",
    }


def test_the_ledger_refuses_the_dry_grass_that_stopped_the_corn_link() -> None:
    ledger = load_ledger()
    assert ledger is not None
    assert judge_misc_model("p7_foliage_grass_dry_03", ledger) == "unlinkable"


def _tiff(bits: int, samples: int) -> bytes:
    """A classic little-endian TIFF header with one IFD: BitsPerSample (one
    short per sample, stored after the IFD when there are more than two) and
    SamplesPerPixel; enough for :func:`tiff_layout`."""
    import struct

    ifd = 8
    count = 2
    extra = ifd + 2 + 12 * count + 4
    if samples <= 2:
        bits_value = struct.pack("<HH", bits, bits if samples == 2 else 0)
        tail = b""
    else:
        bits_value = struct.pack("<I", extra)
        tail = struct.pack("<" + "H" * samples, *([bits] * samples))
    entries = struct.pack("<HHI", 258, 3, samples) + bits_value
    entries += struct.pack("<HHIHH", 277, 3, 1, samples, 0)
    return b"II" + struct.pack("<HI", 42, ifd) + struct.pack("<H", count) + entries + b"\0" * 4 + tail


def test_tiff_layout_reads_bits_and_samples(tmp_path) -> None:
    from zmforge.blueprint.installed import tiff_layout

    for bits, samples in ((16, 2), (8, 2), (16, 3), (16, 1), (8, 4)):
        path = tmp_path / f"t{bits}_{samples}.tif"
        path.write_bytes(_tiff(bits, samples))
        assert tiff_layout(path) == (bits, samples)
    (tmp_path / "empty.tif").write_bytes(b"")
    assert tiff_layout(tmp_path / "empty.tif") is None
    assert tiff_layout(tmp_path / "absent.tif") is None


_GDT_REBAR = '''{
\t"p7_rebar_bad" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\rebar\\\\bad_lod0.XMODEL_BIN"
\t}
\t"p7_rebar_ok" ( "xmodel.gdf" )
\t{
\t\t"filename" "t7_props\\\\rebar\\\\ok_lod0.XMODEL_BIN"
\t}
\t"mtl_cap" ( "material.gdf" )
\t{
\t\t"colorMap" "$white_diffuse"
\t\t"colorMap00" "i_cap_c"
\t}
\t"mtl_bar" ( "material.gdf" )
\t{
\t\t"colorMap00" "i_bar_c"
\t}
\t"i_cap_c" ( "image.gdf" )
\t{
\t\t"baseImage" "model_export\\\\t7_props\\\\rebar\\\\cap_c.tif"
\t}
\t"i_bar_c" ( "image.gdf" )
\t{
\t\t"baseImage" "model_export\\\\t7_props\\\\rebar\\\\bar_c.tif"
\t}
}
'''


def test_scan_unlinkable_refuses_a_tiff_layout_the_linker_cannot_read(tmp_path) -> None:
    """``p7_rebar_column_128``: its cap material's ``colorMap00`` is a 16-bit
    grey+alpha TIFF and a link that needs it stops with ``format not
    supported``.  8-bit grey+alpha converted (the linker's image
    cache holds ``i_c_gen_reveal_2k_sq_r``), so only the measured layout is
    refused."""
    from zmforge.blueprint.installed import UNREADABLE_TIFF, scan_unlinkable

    assert (16, 2) in UNREADABLE_TIFF and (8, 2) not in UNREADABLE_TIFF
    d = tmp_path / "model_export" / "t7_props" / "rebar"
    d.mkdir(parents=True)
    (d / "bad_lod0.xmodel_bin").write_bytes(_model_bin("mtl_cap"))
    (d / "ok_lod0.xmodel_bin").write_bytes(_model_bin("mtl_bar"))
    (d / "cap_c.tif").write_bytes(_tiff(16, 2))
    (d / "bar_c.tif").write_bytes(_tiff(8, 2))
    (tmp_path / "model_export" / "rebar.gdt").write_text(_GDT_REBAR, encoding="utf-8")
    found = scan_unlinkable(tmp_path)
    assert list(found) == ["p7_rebar_bad"]
    assert "16-bit grey+alpha" in found["p7_rebar_bad"]


def test_a_palette_pick_skips_a_model_the_local_linker_refuses() -> None:
    """The pick moves on to the next entry, as a strewn pick skips a panel,
    so the scene keeps its count and Z13 has nothing to refuse."""
    from zmforge.recipes.props import PALETTE, _model

    ledger = load_ledger()
    assert ledger is not None
    for theme, models in PALETTE.items():
        for index in range(len(models)):
            for strewn in (False, True):
                try:
                    name = _model(theme, index, strewn=strewn)[0]
                except ValueError:
                    continue
                assert judge_misc_model(name, ledger) != "unlinkable", (theme, index, name)
