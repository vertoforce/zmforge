"""The prop pipeline: the format rules, the maths, and the map pass.

The xmodel format assertions are pinned to a real BO3-era export
(``wb_m16_chalk_LOD0.xmodel_export``, ``VERSION 7``) rather than to what this
package happens to produce, so a change that quietly breaks the format fails
here rather than at build time.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from zmforge import mapsource
from zmforge.emit.mapfile import build_document
from zmforge.props.gdt import XMODEL_DEFAULTS, XModelAsset, gdt_document, xmodel_entry
from zmforge.props.library import KITS, PROPS, credits_markdown
from zmforge.props.place import MARKER, apply, floor_slabs, placed, scatter
from zmforge.props.textures import build_palette
from zmforge.props.wavefront import Mesh, Triangle, read_obj
from zmforge.props.xmodel import (
    MaterialBinding,
    decimate,
    to_game_space,
    xmodel_export_text,
)
from zmforge.recipes import three_room_map


CUBE_OBJ = """\
# a unit cube, Y up
v 0 0 0
v 1 0 0
v 1 0 1
v 0 0 1
v 0 2 0
v 1 2 0
v 1 2 1
v 0 2 1
vt 0 0
vt 1 0
vt 1 1
vt 0 1
vn 0 1 0
usemtl paint
f 5/1/1 6/2/1 7/3/1 8/4/1
f 1/1/1 4/4/1 3/3/1 2/2/1
"""


@pytest.fixture()
def cube(tmp_path):
    path = tmp_path / "cube.obj"
    path.write_text(CUBE_OBJ)
    return read_obj(path)


def test_quads_are_fanned_into_triangles(cube) -> None:
    assert len(cube.triangles) == 4
    assert cube.materials == ["paint"]


def test_vertex_colours_on_v_lines_are_tolerated(tmp_path) -> None:
    """Kenney's kits write ``v x y z r g b``; the extra numbers are not a position."""
    path = tmp_path / "coloured.obj"
    path.write_text("v 0 0 0 1 1 1\nv 1 0 0 1 1 1\nv 0 1 0 1 1 1\nf 1 2 3\n")
    mesh = read_obj(path)
    assert mesh.positions[0] == (0.0, 0.0, 0.0)
    assert len(mesh.triangles) == 1


def test_negative_indices_count_back_from_the_end(tmp_path) -> None:
    path = tmp_path / "neg.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")
    assert read_obj(path).triangles[0].position == (0, 1, 2)


def test_a_face_naming_a_missing_vertex_is_an_error(tmp_path) -> None:
    path = tmp_path / "bad.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nf 1 2 9\n")
    with pytest.raises(ValueError, match="does not exist"):
        read_obj(path)


def test_game_space_is_z_up_sits_on_the_floor_and_is_centred(cube) -> None:
    game, scale = to_game_space(cube, 10.0)
    assert scale == pytest.approx(5.0)  # longest axis is the 2-unit height
    lo, hi = game.bounds()
    assert lo[2] == pytest.approx(0.0)  # stands on z = 0
    assert hi[2] == pytest.approx(10.0)
    assert (lo[0] + hi[0]) / 2 == pytest.approx(0.0)  # centred on x
    assert (lo[1] + hi[1]) / 2 == pytest.approx(0.0)  # and on y


def test_the_axis_change_preserves_winding(cube) -> None:
    """A reflection would flip every face and light the props inside out."""
    game, _ = to_game_space(cube, 10.0)
    before = _signed_volume(cube)
    after = _signed_volume(game)
    assert math.copysign(1, before) == math.copysign(1, after)


def _signed_volume(mesh: Mesh) -> float:
    total = 0.0
    for tri in mesh.triangles:
        a, b, c = (mesh.positions[i] for i in tri.position)
        total += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
    return total


def test_decimation_reports_when_it_did_nothing(cube) -> None:
    mesh, note = decimate(cube, 1000)
    assert mesh is cube
    assert "left alone" in note


def test_decimation_collapses_a_mesh_over_budget() -> None:
    mesh = _grid_mesh(24)
    assert len(mesh.triangles) > 200
    smaller, note = decimate(mesh, 200)
    assert len(smaller.triangles) <= 200
    assert "->" in note
    # and it is deterministic
    again, _ = decimate(mesh, 200)
    assert [t.position for t in again.triangles] == [t.position for t in smaller.triangles]


def _grid_mesh(side: int) -> Mesh:
    mesh = Mesh()
    for row in range(side + 1):
        for col in range(side + 1):
            mesh.positions.append((float(col), float(row), 0.0))
    width = side + 1
    for row in range(side):
        for col in range(side):
            a = row * width + col
            mesh.triangles.append(
                Triangle("m", (a, a + 1, a + width), (-1, -1, -1), (-1, -1, -1))
            )
    return mesh


def test_export_matches_the_shape_of_a_real_version_7_file(cube) -> None:
    game, _ = to_game_space(cube, 10.0)
    text = xmodel_export_text(
        game, "zmf_cube", [MaterialBinding("paint", "zmf_paint", "zmf_paint_c.tif")],
        stamp="Thu Jan 01 00:00:00 2026",
    )
    lines = text.splitlines()
    assert lines[2:4] == ["MODEL", "VERSION 7"]
    assert 'BONE 0 -1 "TAG_ORIGIN"' in lines
    assert f"NUMVERTS {len(game.positions)}" in lines
    assert f"NUMFACES {len(game.triangles)}" in lines
    assert 'OBJECT 0 "zmf_cube"' in lines
    assert 'MATERIAL 0 "zmf_paint" "Lambert" "color_map:zmf_paint_c.tif"' in lines
    # version 7 separates numbers with spaces, not the commas version 6 used
    assert "," not in text
    # every TRI names its object and material slot and is followed by three corners
    assert text.count("TRI 0 0 0 0") == len(game.triangles)
    assert text.count("UV 1 ") == len(game.triangles) * 3


def test_corner_vertex_colour_is_white_so_the_texture_shows(cube) -> None:
    """Radiant multiplies the colour map by it: 0 0 0 drew every kit prop black
    (measured).  The material block's own COLOR is not a vertex colour."""
    from zmforge.render.propfix import whiten

    game, _ = to_game_space(cube, 10.0)
    text = xmodel_export_text(game, "c", [MaterialBinding("paint", "m", "m.tif")], stamp="s")
    lines = text.splitlines()
    corners = [lines[i + 2] for i, ln in enumerate(lines)
               if ln.startswith("VERT ") and lines[i + 1].startswith("NORMAL ")]
    assert len(corners) == len(game.triangles) * 3
    assert set(corners) == {"COLOR 1.000000 1.000000 1.000000 1.000000"}
    assert whiten(text)[1] == 0          # the render-only patch has nothing left to do


def test_uv_v_is_flipped_because_the_format_runs_it_downwards(cube) -> None:
    game, _ = to_game_space(cube, 10.0)
    binding = [MaterialBinding("paint", "m", "m.tif")]
    flipped = xmodel_export_text(game, "c", binding, stamp="s")
    straight = xmodel_export_text(game, "c", binding, flip_v=False, stamp="s")
    assert "UV 1 0.000000 1.000000" in flipped
    assert "UV 1 0.000000 0.000000" in straight


def test_a_material_with_no_game_binding_is_an_error(cube) -> None:
    with pytest.raises(ValueError, match="no game material bound"):
        xmodel_export_text(cube, "c", [MaterialBinding("other", "m", "m.tif")])


def test_gdt_keys_come_out_in_case_insensitive_ascii_order() -> None:
    """The order every real GDT is written in: bone, then Bullet, then Collision."""
    entry = xmodel_entry(
        XModelAsset("zmf_x", "zm_map\\zmf_x.XMODEL_BIN", ("zmf_material",))
    )
    keys = [line.split('"')[1] for line in entry.splitlines() if line.startswith('\t\t"')]
    assert keys == sorted(keys, key=str.lower)
    assert keys.index("boneStabilizers") < keys.index("BulletCollisionFile")
    assert keys.index("BulletCollisionRigid") < keys.index("CollisionMap")
    assert keys.index("submodel0_Name") < keys.index("submodel10_Name")
    assert keys.index("submodel15_ParentTag") < keys.index("submodel1_Name")


def test_gdt_doubles_backslashes_and_spells_newlines_in_the_material_list() -> None:
    entry = xmodel_entry(XModelAsset("zmf_x", "zm_map\\zmf_x.XMODEL_BIN", ("a", "b")))
    assert '"filename" "zm_map\\\\zmf_x.XMODEL_BIN"' in entry
    assert '"materials" "a\\r\\nb\\r\\n"' in entry
    assert "\r" not in entry


def test_gdt_entity_is_a_flat_block_two_tabs_deep() -> None:
    document = gdt_document([XModelAsset("zmf_x", "a\\b.XMODEL_BIN", ("m",))])
    assert document.startswith("{\n")
    assert document.endswith("}\n")
    assert '\t"zmf_x" ( "xmodel.gdf" )' in document
    assert XMODEL_DEFAULTS["type"] == "rigid"
    assert XMODEL_DEFAULTS["BulletCollisionLOD"] == "None"


def test_duplicate_asset_names_are_refused() -> None:
    asset = XModelAsset("same", "a\\b.XMODEL_BIN", ("m",))
    with pytest.raises(ValueError, match="duplicate"):
        gdt_document([asset, asset])


def test_palette_cells_are_laid_out_on_a_power_of_two_grid() -> None:
    palette = build_palette({f"m{i}": (0.5, 0.5, 0.5) for i in range(5)})
    assert palette.cells == 4
    u, v = palette.uv("m0")
    assert (u, v) == (0.125, 0.125)  # centre of the top-left cell, v running down
    assert len(palette.pixels()) == palette.size * palette.size * 3


def test_every_library_prop_names_a_kit_with_a_licence() -> None:
    from zmforge.props.library import TEXTURES

    for prop in PROPS:
        kit = KITS[prop.kit]
        if kit.kind == "generated":
            # Our own geometry: nothing downloaded, so the licence that
            # matters is the texture's.
            assert prop.material is not None and (prop.material.source or prop.material.sources), prop.name
        else:
            assert kit.licence.startswith("CC0")
            assert kit.archive.startswith("https://")
        assert kit.terms
        assert prop.size_units > 0
        for slug in ((prop.material.source,) + prop.material.sources
                     if prop.material is not None and prop.material.source else
                     prop.material.sources if prop.material is not None else ()):
            tex = TEXTURES[slug]
            assert tex.licence.startswith("CC0") and tex.archive.startswith("https://")
            assert tex.terms


def test_credits_carry_the_source_and_the_terms() -> None:
    text = credits_markdown(list(PROPS))
    for prop in PROPS:
        assert prop.name in text
        assert KITS[prop.kit].archive in text
        if prop.material is not None and prop.material.source:
            from zmforge.props.library import TEXTURES

            assert TEXTURES[prop.material.source].archive in text
    assert "CC0" in text


@pytest.fixture()
def map_document():
    return build_document(three_room_map("zm_props_fixture"))


def test_floor_slabs_are_art_floors_not_sky_cages_or_walls(map_document) -> None:
    slabs = floor_slabs(map_document)
    assert slabs
    # plus the barricade windows' closet floors (blueprint.windows, Z85),
    # which are real floors too
    from zmforge.blueprint.windows import CLOSET_MATERIALS

    assert {s.material for s in slabs} == {"t7_concrete_trowelled", CLOSET_MATERIALS["floor"]}
    assert {s.top for s in slabs} == {16.0}


def test_props_land_on_the_floor_spread_over_the_rooms(map_document) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    places = scatter(map_document, models, seed="fixture")
    assert len(places) == len(PROPS)
    assert {round(p.origin[2], 1) for p in places} == {15.5}  # floor top, sunk 0.5
    slabs = floor_slabs(map_document)
    for place in places:
        assert any(
            slab.bounds.mins.x <= place.origin[0] <= slab.bounds.maxs.x
            and slab.bounds.mins.y <= place.origin[1] <= slab.bounds.maxs.y
            for slab in slabs
        ), f"{place.name} is not over any floor"


def test_placement_is_deterministic(map_document) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    first = scatter(map_document, models, seed="fixture")
    second = scatter(build_document(three_room_map("zm_props_fixture")), models, seed="fixture")
    assert [p.origin for p in first] == [p.origin for p in second]


def test_the_pass_is_idempotent_and_reversible(map_document, tmp_path) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    apply(map_document, scatter(map_document, models, seed="s"), seed="s")
    once = mapsource.render_map_text(map_document)
    apply(map_document, scatter(map_document, models, seed="s"), seed="s")
    assert mapsource.render_map_text(map_document) == once
    apply(map_document, [], seed="s")
    assert placed(map_document) == []
    assert MARKER not in mapsource.render_map_text(map_document)


def test_prop_entities_carry_the_keys_section_4_13_requires(map_document) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    apply(map_document, scatter(map_document, models, seed="s"), seed="s")
    entities = placed(map_document)
    assert len(entities) == len(PROPS)
    for entity in entities:
        assert entity.classname == "misc_model"
        # Spec 4.13 says no_collmap; the tools' own definition says that is
        # the key that stops the collmap being baked, so a prop meant to be
        # solid carries its opposite.
        assert entity.value("use_collmap") == "1"
        assert entity.value("no_collmap") is None
        assert entity.value("static") == "1"
        assert entity.value("model", "").startswith("zmf_prop_")
        assert entity.value("angles", "").startswith("0 ")
        for state in range(1, 5):
            assert entity.value(f"lightingstate{state}") == "1"


def test_the_written_map_reads_back_with_its_props(map_document, tmp_path) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    apply(map_document, scatter(map_document, models, seed="s"), seed="s")
    path = tmp_path / "zm_props_fixture.map"
    mapsource.write(path, map_document)
    again = mapsource.read(path)
    assert len(placed(again)) == len(PROPS)


def test_several_obj_materials_bound_to_one_game_material_declare_it_once(tmp_path) -> None:
    """The toilet is four named .obj materials on one game material."""
    path = tmp_path / "multi.obj"
    path.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\n"
        "usemtl a\nf 1 2 3\n"
        "usemtl b\nf 1 2 4\n"
    )
    mesh = read_obj(path)
    text = xmodel_export_text(
        mesh,
        "zmf_multi",
        [
            MaterialBinding("a", "zmf_one", "zmf_one_c.tif"),
            MaterialBinding("b", "zmf_one", "zmf_one_c.tif"),
        ],
        stamp="s",
    )
    assert "NUMMATERIALS 1" in text
    assert text.count('MATERIAL 0 "zmf_one"') == 1
    assert text.count("TRI 0 0 0 0") == 2  # both triangles point at slot 0


def test_decimation_ships_no_vertex_without_a_triangle() -> None:
    """NUMVERTS is a declared count the converter reads; it must be all in use."""
    smaller, _ = decimate(_grid_mesh(24), 200)
    used = {i for tri in smaller.triangles for i in tri.position}
    assert len(used) == len(smaller.positions)
    assert max(used) == len(smaller.positions) - 1


def test_stock_material_mode_builds_no_custom_image_or_material(tmp_path) -> None:
    """The one-flag way to tell a model problem from a material problem."""
    from zmforge.props.build import build as build_props

    result = build_props(
        "zm_stock_check",
        tmp_path,
        [PROPS[0]],
        stock_material="t7_concrete_trowelled",
    )
    assert result.images == {}
    assert not (tmp_path / "texture_assets" / "zm_stock_check_props_tex.gdt").exists()
    export = (tmp_path / "model_export" / "zm_stock_check" / f"{PROPS[0].name}.XMODEL_EXPORT").read_text()
    assert 'MATERIAL 0 "t7_concrete_trowelled"' in export
    gdt = (tmp_path / "model_export" / "zm_stock_check_props.gdt").read_text()
    assert '"materials" "t7_concrete_trowelled\\r\\n"' in gdt


# ---------------------------------------------------------------------------
# Collision.  The measurements these pin are recorded in props/collision.py.


def test_a_solid_prop_names_a_col_bullet_mesh_and_a_collmap(tmp_path) -> None:
    from zmforge.props.build import build as build_props
    from zmforge.props.collision import COLLISION_SUFFIX

    result = build_props("zm_coll_check", tmp_path, [PROPS[0]])
    name = PROPS[0].name
    assert (tmp_path / "model_export" / "zm_coll_check" / f"{name}{COLLISION_SUFFIX}.XMODEL_EXPORT").is_file()
    assert (tmp_path / "collmaps" / f"{name}.map").is_file()
    gdt = (tmp_path / "model_export" / "zm_coll_check_props.gdt").read_text()
    assert f'"BulletCollisionFile" "zm_coll_check\\\\{name}_col.XMODEL_BIN"' in gdt
    assert '"BulletCollisionLOD" "Custom"' in gdt
    assert f'"CollisionMap" "{name}.map"' in gdt
    assert "box" in result.props[0].collision


def test_a_walk_through_prop_names_neither(tmp_path) -> None:
    from dataclasses import replace as _replace

    from zmforge.props.build import build as build_props

    ghost = _replace(PROPS[0], solid=False)
    build_props("zm_ghost_check", tmp_path, [ghost])
    assert not (tmp_path / "collmaps").exists() or not any(
        (tmp_path / "collmaps").iterdir()
    )
    gdt = (tmp_path / "model_export" / "zm_ghost_check_props.gdt").read_text()
    assert '"BulletCollisionLOD" "None"' in gdt
    assert '"BulletCollisionFile" ""' in gdt
    assert '"CollisionMap" ""' in gdt


def test_the_bullet_mesh_is_a_twelve_triangle_box_around_the_model(tmp_path) -> None:
    from zmforge.props.collision import bounds_of, box_mesh

    obj = tmp_path / "cube.obj"
    obj.write_text(CUBE_OBJ)
    game, _ = to_game_space(read_obj(obj), 10.0)
    box = bounds_of(game)
    mesh = box_mesh(box, "paint")
    assert len(mesh.triangles) == 12
    assert len(mesh.positions) == 8
    assert mesh.size() == pytest.approx(game.size())


def test_the_collision_box_winding_matches_the_visual_mesh(tmp_path) -> None:
    """A reflected box would be a hole rather than a solid."""
    from zmforge.props.collision import box_mesh
    from zmforge.spatial import Point, Span

    mesh = box_mesh(Span(Point(-8, -8, 0), Point(8, 8, 32)), "m")
    assert _signed_volume(mesh) > 0


def test_the_collmap_is_one_clip_brush_shaped_like_the_shipped_ones() -> None:
    from zmforge.props.collision import COLLISION_MATERIAL, collmap_document
    from zmforge.spatial import Point, Span

    document = collmap_document(Span(Point(-9, -14, 0), Point(9, 14, 26)), seed="s")
    text = mapsource.render_map_text(document)
    assert text.startswith("iwmap 4")
    assert text.count(COLLISION_MATERIAL) == 6  # one box, six faces
    assert len(document.entities) == 1
    assert document.entities[0].classname == "worldspawn"
    assert len(document.entities[0].solids) == 1
    assert "lightmap_gray 16384 16384" in text


def test_solid_props_carry_use_collmap_and_never_both_keys(map_document) -> None:
    """t7.def.json defines the pair as opposites, both defaulting to false."""
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    places = scatter(map_document, models, seed="s", solid={p.name: p.solid for p in PROPS})
    apply(map_document, places, seed="s")
    solid = {p.name: p.solid for p in PROPS}
    for entity in placed(map_document):
        keys = [k for k, _ in entity.pairs]
        assert ("use_collmap" in keys) != ("no_collmap" in keys)
        if solid[entity.value("model")]:
            assert entity.value("use_collmap") == "1"
        else:
            assert entity.value("no_collmap") == "1"


def test_a_walk_through_placement_keeps_no_collmap(map_document) -> None:
    models = [(p.name, p.name, p.size_units) for p in PROPS]
    places = scatter(map_document, models, seed="s", solid={PROPS[0].name: False})
    apply(map_document, places, seed="s")
    by_model = {e.value("model"): e for e in placed(map_document)}
    assert by_model[PROPS[0].name].value("no_collmap") == "1"
    assert by_model[PROPS[0].name].value("use_collmap") is None


def test_every_shipped_prop_is_solid_except_the_walk_through_corn() -> None:
    """Solid is the default; the only props authored walk-through are the
    corn stalks, which a maze wall of them has to let the player brush past
    the way tall grass does, and the teddy bear, which a heap of them in a
    small cell must not turn into a wall."""
    assert {p.name for p in PROPS if not p.solid} == {
        "zmf_prop_corn_stalk",
        "zmf_prop_corn_stalk_thin",
        "zmf_prop_teddy_bear",
    }


# --------------------------------------------------------------------------
# Z29: a stock model that is half an assembly
# --------------------------------------------------------------------------
def _staircase_blueprint():
    """A one-room map with a staircase *frame* standing on its floor."""
    from zmforge.blueprint.elements import Prop, PropScatter
    from zmforge.spatial import Point

    blueprint = three_room_map("zm_assembly_probe")
    blueprint._install(
        PropScatter(
            id="stair_probe",
            props=[Prop(model="p7_cai_staircase_01", origin=Point(0, 0, 16), yaw=0.0)],
        )
    )
    return blueprint


def test_a_staircase_frame_is_emitted_with_its_eleven_treads() -> None:
    """The treads are a separate model; the frame alone is handrails in mid air.

    Offsets pinned to the install's own prefab
    ``_prefabs/mp/mp_combine/geo/mp_combine_aquaculture_bdg_south/
    mp_combine_lab_staircase.map``: frame at ``-58 6 40``, eleven
    ``p7_cai_staircase_step_01`` at ``-58 13 46`` .. ``-58 133 126``.
    """
    document = build_document(_staircase_blueprint())
    treads = [
        e
        for e in document.entities_of("misc_model")
        if e.value("model") == "p7_cai_staircase_step_01"
    ]
    assert len(treads) == 11
    origins = sorted(tuple(map(float, e.value("origin").split())) for e in treads)
    assert origins == [(0.0, 7.0 + 12 * i, 22.0 + 8 * i) for i in range(11)]
    assert all(e.value("no_collmap") == "1" for e in treads)


def test_a_quarter_turned_staircase_takes_its_treads_round_with_it() -> None:
    """Measured sense: at yaw 270 the stock outdoor prefab's treads climb +X."""
    from zmforge.blueprint.catalogue import companion_origins

    placed_parts = companion_origins("p7_cai_staircase_01", (0.0, 0.0, 0.0), 270.0)
    assert [origin for _, origin in placed_parts][:3] == [
        (7.0, 0.0, 6.0),
        (19.0, 0.0, 14.0),
        (31.0, 0.0, 22.0),
    ]


def test_z29_fires_on_a_staircase_frame_with_no_treads() -> None:
    from zmforge.verify.playtest import check_model_assemblies

    document = build_document(_staircase_blueprint())
    document.entities = [
        e
        for e in document.entities
        if e.value("model") != "p7_cai_staircase_step_01"
    ]
    report = check_model_assemblies(document)
    assert [f.code for f in report.findings] == ["Z29"]
    assert report.errors


def test_z29_is_silent_on_a_complete_assembly() -> None:
    from zmforge.verify.playtest import check_model_assemblies

    assert not check_model_assemblies(build_document(_staircase_blueprint())).findings


# --------------------------------------------------------------------------
# Z41: a model that promises a way up
# --------------------------------------------------------------------------
def test_a_scatter_rule_steps_past_a_route_model() -> None:
    """Row and Fill may not deal a staircase out; One still may.

    The index a scene was written against still means "start here", so the
    placement happens -- with the next model in the theme that is an object.
    """
    from zmforge.recipes.props import PALETTE, _model

    theme = "tall_hall"
    index = next(
        i for i, (name, _size, _tris) in enumerate(PALETTE[theme])
        if name == "p7_cai_staircase_01"
    )
    assert _model(theme, index)[0] == "p7_cai_staircase_01"
    strewn = _model(theme, index, strewn=True)[0]
    assert strewn != "p7_cai_staircase_01"
    assert strewn == PALETTE[theme][(index + 1) % len(PALETTE[theme])][0]


def test_z41_fires_on_a_staircase_that_climbs_into_the_air() -> None:
    """The defect as shipped: a staircase model standing on a floor, alone.

    Its climb tops out 86 units up (the last of the eleven treads) and there
    is no surface there, which is what a player sees instantly and what no
    other row in the table can ask -- Z19 only looks at brushwork, and Z25
    reports what is stranded, which a useless staircase never is.
    """
    from zmforge.verify.playtest import check_route_props

    report = check_route_props(_staircase_blueprint())
    assert [f.code for f in report.findings] == ["Z41"]
    assert report.errors


def test_z41_is_silent_on_a_staircase_that_reaches_a_floor() -> None:
    from zmforge.blueprint.catalogue import route_top
    from zmforge.blueprint.elements import Prop, PropScatter
    from zmforge.materials import Material
    from zmforge.spatial import Bounds, Point
    from zmforge.verify.playtest import check_route_props

    blueprint = three_room_map("zm_route_probe")
    foot = Point(0, 0, 16)
    head = foot.z + route_top("p7_cai_staircase_01")
    blueprint.add_slab(
        Bounds.between((-64, 0, 0), (64, 128, 16)), head, 16,
        Material("t7_concrete_pebbles_cracked"), id="route_landing",
    )
    blueprint._install(
        PropScatter(
            id="route_probe",
            props=[Prop(model="p7_cai_staircase_01", origin=foot, yaw=0.0)],
        )
    )
    assert not check_route_props(blueprint).findings


def test_z41_reports_a_route_model_whose_climb_nobody_measured() -> None:
    """An unmeasured climb is reported, not guessed at."""
    from zmforge.blueprint.elements import Prop, PropScatter
    from zmforge.spatial import Point
    from zmforge.verify.playtest import check_route_props

    blueprint = three_room_map("zm_route_unknown")
    blueprint._install(
        PropScatter(
            id="unknown_probe",
            props=[Prop(model="p7_cai_stairway_99", origin=Point(0, 0, 16), yaw=0.0)],
        )
    )
    report = check_route_props(blueprint)
    assert [f.code for f in report.findings] == ["Z41"]
    assert "measured" in report.findings[0].message


# --------------------------------------------------------------------------
# The kit's box and the recipe's box are one box
# --------------------------------------------------------------------------
def _cached_kits_present() -> bool:
    from zmforge.props.fetch import default_cache, kit_cached
    from zmforge.props.library import KITS

    cache = default_cache()
    return all(kit_cached(kit, cache) for kit in KITS.values())


@pytest.mark.skipif(
    not _cached_kits_present(),
    reason="the kit archives are not in assets-cache; this test measures them "
           "rather than downloading them",
)
def test_the_recipe_s_box_for_a_kit_prop_is_the_converted_mesh_s_own_box() -> None:
    """``MODEL_BOX`` and the kit's bullet mesh are cut from the same numbers.

    The recipe writes a kit prop's collmap from ``MODEL_BOX``; the kit build
    writes its bullet mesh and its own collmap from ``bounds_of`` over the
    converted mesh. Those are two files that both claim to be one prop's
    collision, so they have to agree, and the only honest way to say they do
    is to re-measure the mesh here from the archive the library names.

    It also pins the other thing ``MODEL_BOX`` is for: ``to_game_space``
    centres a converted model on x and y, so the plan centre is (0, 0) and the
    origin correction is a no-op on these six. That is a measurement, not an
    assumption, and it is what a placement by centre rests on.
    """
    from zmforge.props.build import game_mesh
    from zmforge.props.collision import bounds_of
    from zmforge.props.fetch import default_cache
    from zmforge.props.library import PROPS as KIT_PROPS
    from zmforge.props.wavefront import read_obj
    from zmforge.props.xmodel import decimate, to_game_space
    from zmforge.recipes.props import MODEL_BOX, PLAN_BOX

    cache = default_cache()
    work = cache / "extracted-for-tests"
    for entry in KIT_PROPS:
        game, _scale, _note = game_mesh(entry, work, cache)
        box = bounds_of(game)
        measured = (
            (box.mins.x, box.mins.y, box.mins.z),
            (box.maxs.x, box.maxs.y, box.maxs.z),
        )
        recorded = MODEL_BOX[entry.name]
        for got, want in zip(measured, recorded):
            for a, b in zip(got, want):
                assert abs(a - b) <= 0.001, (entry.name, measured, recorded)
        assert PLAN_BOX[entry.name][:2] == (0.0, 0.0), entry.name


def test_a_kit_prop_s_solidity_comes_from_the_library_and_not_from_its_size() -> None:
    """The rule of thumb would call five of the six walk-through.

    A donut is 3 units tall and a lollipop is 1.8 units across, so the size
    rule that decides a filing cabinet from a sheet of paper says "not solid"
    to nearly the whole kit. ``props.library`` says otherwise, and it is the
    one that counts: it is what the kit build reads when it decides to cut a
    bullet mesh at all, and it is what ``Z21`` reads when it calls a
    disagreeing entity an error.
    """
    from zmforge.props.library import PROPS as KIT_PROPS
    from zmforge.recipes.props import (
        MODEL_BOX,
        SOLID_MIN_HEIGHT,
        STEP_ON_MIN_FOOTPRINT,
        STEP_ON_MIN_HEIGHT,
        is_solid,
    )

    by_rule = []
    for entry in KIT_PROPS:
        (x0, y0, z0), (x1, y1, z1) = MODEL_BOX[entry.name]
        height = z1 - z0
        rule = height >= SOLID_MIN_HEIGHT or (
            height >= STEP_ON_MIN_HEIGHT
            and min(x1 - x0, y1 - y0) >= STEP_ON_MIN_FOOTPRINT
        )
        by_rule.append(rule)
        assert is_solid(entry.name) is entry.solid, entry.name
    assert by_rule.count(False) >= 4, by_rule


def _placed_props(blueprint):
    """``(scatter id, model, plan centre, yaw, scale, solid)`` for every prop."""
    from zmforge.blueprint.elements import PropScatter
    from zmforge.recipes.props import PLAN_BOX

    out = []
    for scatter_group in blueprint.elements(PropScatter):
        for prop in scatter_group.props:
            cx, cy, _radius = PLAN_BOX.get(prop.model, (0.0, 0.0, 0.0))
            angle = math.radians(prop.yaw)
            out.append((
                scatter_group.id,
                prop.model,
                prop.origin.x + (cx * math.cos(angle) - cy * math.sin(angle)) * prop.scale,
                prop.origin.y + (cx * math.sin(angle) + cy * math.cos(angle)) * prop.scale,
                prop.origin.z,
                prop.yaw,
                prop.scale,
                prop.solid,
            ))
    return out


@pytest.fixture
def catalogue_boxes_only():
    """``MODEL_BOX`` exactly as props.py builds it, restored afterwards.

    Other modules add boxes to the same dict at run time
    (:func:`zmforge.dressing.outdoor.register_boxes`, the corn maze's kits), so
    after their tests ran the table also held the outdoor set's ivy sheet and
    flatbed truck, both flat.  A test of this palette reads this palette.
    """
    from zmforge.props.origins import drawn_boxes
    from zmforge.recipes.props import CATALOGUE_BOX, MODEL_BOX

    saved = dict(MODEL_BOX)
    MODEL_BOX.clear()
    MODEL_BOX.update(drawn_boxes(CATALOGUE_BOX))
    try:
        yield
    finally:
        MODEL_BOX.clear()
        MODEL_BOX.update(saved)


def test_the_flat_panels_in_this_palette_are_named_by_their_measured_shape(catalogue_boxes_only) -> None:
    """Three models, and the next thing down the list is not close.

    The pallet is 132 x 70 and 12 through,
    which is a framed corrugated sheet whatever its asset name says.
    """
    from zmforge.recipes.props import MODEL_BOX, is_panel_model

    panels = sorted(name for name in MODEL_BOX if is_panel_model(name))
    assert panels == [
        "p7_bed_mattress_barrack",
        "p7_bed_mattress_barrack_made_v2",
        "p7_pallet_metal_military_01",
    ]
    # the shapes either side of the line, so a change to the numbers shows up
    assert not is_panel_model("p7_debris_concrete_rubble_pile_02")  # 108x71x38
    assert not is_panel_model("p7_zm_der2_bulletin_board")          # 62x2.2x36
    assert not is_panel_model("p7_debris_trash_paper_plate_01")     # 9x9x0.4


def test_a_scatter_rule_steps_past_a_flat_panel() -> None:
    """Row and Fill may not deal a sheet out; One still may."""
    from zmforge.recipes.props import PALETTE, _model

    theme = "tall_hall"
    index = next(
        i for i, (name, _size, _tris) in enumerate(PALETTE[theme])
        if name == "p7_pallet_metal_military_01"
    )
    assert _model(theme, index)[0] == "p7_pallet_metal_military_01"
    assert _model(theme, index, strewn=True)[0] != "p7_pallet_metal_military_01"


def test_two_large_props_may_touch_and_stack_but_not_interpenetrate() -> None:
    """Treyarch's own rooms have props touching and standing on each other."""
    from zmforge.recipes.props import _Crowd

    crowd = _Crowd()
    crowd.add(0.0, 0.0, 32.0, 32.0, 0.0, 48.0)          # a 64 x 64 x 48 crate
    # side by side, edges touching
    assert not crowd.crowded(64.0, 0.0, 32.0, 32.0, 0.0, 48.0)
    # a second crate on top of the first
    assert not crowd.crowded(0.0, 0.0, 32.0, 32.0, 48.0, 96.0)
    # a 2-unit lip over the neighbour, which is 3% of the footprint
    assert not crowd.crowded(62.0, 0.0, 32.0, 32.0, 0.0, 48.0)
    # a tenth of it shared at the same height
    assert crowd.crowded(58.0, 0.0, 32.0, 32.0, 0.0, 48.0)
    # half of it shared at the same height, which is one crate inside another
    assert crowd.crowded(32.0, 0.0, 32.0, 32.0, 0.0, 48.0)
    # small props are not this rule's business at all
    assert not crowd.crowded(0.0, 0.0, 8.0, 8.0, 0.0, 12.0)


def test_the_row_thinner_takes_a_piece_out_rather_than_ghosting_it() -> None:
    """A gap in a row is a row with a gap in it, not a row you walk through.

    It runs after fitting, because fitting slides a row up to 120 units
    toward its wall: a thinner that judged the row before fitting would see
    many of its props move more than 8 units afterwards, some further than
    the 40-unit gap it enforces.
    """
    from zmforge.recipes.props import _thin_a_fence
    from zmforge.spatial import Point

    crate = "p7_cai_stacking_cargo_crate"          # 64 x 64 x 48
    run = [[crate, Point(x, 0.0, 0.0), 0.0, 1.0, (64.0, 64.0, 48.0), True, None, False]
           for x in (0.0, 32.0, 64.0, 96.0, 128.0)]
    thinned = _thin_a_fence(run, rooms=(), free=True)
    assert len(thinned) < len(run), "a 32-unit pitch is a fence, not a row"
    assert all(row[5] for row in thinned), "nothing that survives is a ghost"

    ghosting = [[crate, Point(x, 0.0, 0.0), 0.0, 1.0, (64.0, 64.0, 48.0), True, None, False]
                for x in (0.0, 32.0, 64.0, 96.0, 128.0)]
    pinned = _thin_a_fence(ghosting, rooms=(), free=False)
    assert len(pinned) == len(ghosting), "a pinned room keeps every piece"
    assert not all(row[5] for row in pinned), "and pays for it the old way"


# --------------------------------------------------------------------------
# The second placement pass
# --------------------------------------------------------------------------
# The first pass covers the faults visible at a glance: junk on the stairs, props
# in doorways, props drawn through each other.  These tests cover the rest of
# the placement faults; every count below is what a fresh generate gives.
def test_every_palette_model_has_a_mount_kind_from_its_box() -> None:
    """Sixteen fixtures, and the three shapes that look like one and are not."""
    from zmforge.recipes.props import (
        MOUNT_CEILING,
        MOUNT_FLOOR,
        MOUNT_WALL,
        PALETTE,
        mount_kind,
    )

    kinds = {name: mount_kind(name)
             for models in PALETTE.values() for name, _size, _tris in models}
    assert sorted(n for n, k in kinds.items() if k == MOUNT_CEILING) == [
        "p7_light_chandelier_hologram",
        "p7_light_hanging_modern_02",
    ]
    assert sorted(n for n, k in kinds.items() if k == MOUNT_WALL) == [
        "p7_ac_unit_wall_mount_01",
        "p7_clock_metal_wall_01_base",
        "p7_duct_metal_circular_straight_32",
        "p7_duct_metal_circular_vent",
        "p7_light_fixture_led_wall_01",
        "p7_picture_frame_modern_01",
        "p7_signage_caution_biohazard_01",
        "p7_signage_caution_exit",
        "p7_signage_loading_zone_01",
        "p7_sink_kitchen_stainless_modern_01_clean",
        "p7_zm_der2_bulletin_board",
        "p7_zm_der_signage_employees_only",
        "p7_zm_der_signage_no_smoking",
        "p7_zm_der_teleporter_mf_ladder",
    ]
    # The z-centred boxes that are *not* fixtures, which is why the rule is
    # named for the wall families and measured only for the ceiling ones.
    assert mount_kind("p7_rebar_column_128") == MOUNT_FLOOR        # z -65..65
    assert mount_kind("p7_debris_rockychunks_small_10") == MOUNT_FLOOR
    assert mount_kind("p7_bed_mattress_barrack") == MOUNT_FLOOR
    assert mount_kind("p7_consumer_grade_monitor_medium") == MOUNT_FLOOR  # z 0..31


def test_a_fixture_faces_away_from_the_surface_it_is_mounted_on() -> None:
    """Measured off each model's own box, not named."""
    from zmforge.recipes.props import _mount_face

    assert _mount_face("p7_signage_caution_biohazard_01") == -90.0  # body on -y
    assert _mount_face("p7_zm_der2_bulletin_board") == 90.0         # body on +y
    assert _mount_face("p7_light_fixture_led_wall_01") == 0.0       # body on +x
    assert _mount_face("p7_duct_metal_circular_straight_32") == 180.0


def test_no_wall_or_ceiling_fixture_is_ever_solid() -> None:
    from zmforge.recipes.props import is_solid

    assert not is_solid("p7_zm_der2_bulletin_board")   # 62 x 2.2 x 36, tall enough
    assert not is_solid("p7_clock_metal_wall_01_base")
    assert not is_solid("p7_duct_metal_circular_straight_32")


def _floor_under(blueprint, x, y, z):
    hit = blueprint.ground_under(x, y, below=z)
    return hit.z if hit.found else None


def test_a_prop_on_a_block_top_fits_inside_that_block() -> None:
    """A 64 x 96 bed does not stand on a 60-wide plinth."""
    from zmforge.recipes.props import _fit_on_block
    from zmforge.spatial import Point

    plinth = (-560.0, -1060.0, -500.0, -900.0)   # a 60 x 160 block top
    assert _fit_on_block(plinth, Point(-545.0, -1038.0, 48.0),
                         "p7_bunkbed", (64.5, 96.1, 110.2), 90.0, 1.0) is None
    slid = _fit_on_block(plinth, Point(-510.0, -1038.0, 48.0),
                         "p7_crate_wood_01_short", (30.9, 30.1, 31.0), 0.0, 1.0)
    assert slid is not None and slid.x <= -500.0 - 15.437


def test_a_seat_in_a_row_is_turned_off_the_wall() -> None:
    """11 chairs faced a wall 13 units away: ``MODEL_FRONT`` was only ever
    applied to the pieces a ``Fill`` sited, never to a ``Row``."""
    from zmforge.recipes.props import _faces_a_wall
    from zmforge.spatial import Point, Span

    inside = Span.between(Point(0.0, 0.0, 0.0), Point(400.0, 400.0, 200.0))
    rooms = (("probe", inside),)
    chair = "p7_chair_wood_fancy_01"           # MODEL_FRONT -90
    size = (20.4, 24.9, 38.8)
    # 8 units off the south wall, facing south: 13 units of nothing in front
    against = Point(200.0, 8.0, 0.0)
    assert _faces_a_wall(rooms, chair, against, 0.0, -90.0, size, 1.0)
    assert not _faces_a_wall(rooms, chair, against, 180.0, -90.0, size, 1.0)


# --------------------------------------------------------------------------
# The trusted stock collmaps, against the files themselves
# --------------------------------------------------------------------------
#: The mod tools' collision files, when one is configured.  Only the
#: collision files are wanted, and a run without them skips.
INSTALLED_COLLMAPS = Path("<bo3-wine>/tools/share/raw/collmaps")


def test_no_trusted_stock_collmap_uses_a_primitive_the_compiler_rejects() -> None:
    r"""Pinned to the install's own files, because a build is the alternative.

    ``STOCK_COLLMAPS`` is the set of models whose collision file we leave to
    Treyarch and write nothing for.  Trusting one the compiler cannot read
    costs a whole build: marking the watermelon solid put
    ``use_collmap "1"`` on ``p7_food_fruit_watermelon``, ``cod2map64`` opened
    Treyarch's own file for it and stopped at ``MatchToken: got
    'physics_cylinder', expected '('`` with no BSP written.  28 of the 258
    collmaps the mod tools install ships carry such a primitive and all 28 were taken
    out of the set; this is what stops one coming back.
    """
    from zmforge.props.collision import STOCK_COLLMAPS
    from zmforge.verify.files import collmap_primitives

    if not INSTALLED_COLLMAPS.is_dir():
        pytest.skip(f"no local mod tools collmaps at {INSTALLED_COLLMAPS}")
    offenders: dict[str, list[tuple[int, str]]] = {}
    checked = 0
    for model in sorted(STOCK_COLLMAPS):
        path = INSTALLED_COLLMAPS / f"{model}.map"
        if not path.is_file():
            continue  # the mod tools install does not ship it; Z27 answers for that
        checked += 1
        found = collmap_primitives(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            offenders[model] = found
    if not checked:
        pytest.skip(f"{INSTALLED_COLLMAPS} holds none of the trusted names")
    assert offenders == {}, (
        "these trusted stock collmaps use a primitive cod2map64 rejects; drop "
        "them from src/zmforge/props/stock_collmaps.json so a generated box is "
        f"written instead: {sorted(offenders)}"
    )


def test_the_kit_palette_and_the_library_list_the_same_props_in_order() -> None:
    """``PALETTE["zmforge_kit"]`` is addressed by index (``KIT``), and the
    library is what gets built.  A prop in one and not the other is either a
    placement of a model nobody converts or a converted model nothing can
    place, so they must match name for name, and the first six keep the
    indices recipes already use."""
    from zmforge.props.library import PROPS as KIT_PROPS
    from zmforge.recipes.props import KIT, MODEL_BOX, PALETTE

    palette = [name for name, _size, _tris in PALETTE["zmforge_kit"]]
    assert palette == [p.name for p in KIT_PROPS]
    assert all(name in MODEL_BOX for name in palette)
    assert KIT["zmf_prop_donut"] == 0 and KIT["zmf_prop_toilet"] == 5


def _export_winding(text: str) -> tuple[int, int, float]:
    """(faces whose clockwise normal agrees with their vertex normals, faces,
    signed volume with the corners in file order) for an ``.XMODEL_EXPORT``."""
    offsets: list[tuple[float, float, float]] = []
    faces: list[list[tuple[int, tuple[float, float, float]]]] = []
    vert = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "OFFSET" and not faces and vert is not None:
            # Only a vertex's OFFSET: the bone block has one too.
            offsets.append(tuple(float(v) for v in parts[1:4]))
        elif parts[0] == "VERT" and not faces:
            vert = int(parts[1])
        elif parts[0] == "TRI":
            faces.append([])
        elif parts[0] == "VERT" and faces:
            vert = int(parts[1])
        elif parts[0] == "NORMAL" and faces:
            faces[-1].append((vert, tuple(float(v) for v in parts[1:4])))
    agree = 0
    volume = 0.0
    for face in faces:
        (ia, na), (ib, nb), (ic, nc) = face
        a, b, c = offsets[ia], offsets[ib], offsets[ic]
        u = [b[k] - a[k] for k in range(3)]
        w = [c[k] - a[k] for k in range(3)]
        ccw = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        normal = [na[k] + nb[k] + nc[k] for k in range(3)]
        agree += sum(-ccw[k] * normal[k] for k in range(3)) > 0
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
    return agree, len(faces), volume


def test_an_exported_triangle_is_wound_the_way_the_engine_winds_one(cube) -> None:
    """Clockwise seen from outside: stock converted meshes measure that way
    (see ``EXPORT_CORNER_ORDER``), and the .obj order drew props inside out."""
    game, _ = to_game_space(cube, 10.0)
    text = xmodel_export_text(game, "zmf_cube", [MaterialBinding("paint", "m", "m.tif")])
    _agree, faces, volume = _export_winding(text)
    assert faces == len(cube.triangles)
    # The fixture is not closed, so compare with the source rather than 0.
    assert volume == pytest.approx(-_signed_volume(game), rel=1e-3)


@pytest.mark.skipif(
    not _cached_kits_present(),
    reason="the kit archives are not in assets-cache; this test measures them",
)
def test_every_kit_prop_exports_outward_facing_in_the_engine_s_winding() -> None:
    """Every kit prop, as written: negative signed volume in file order (the
    engine's clockwise-outward winding) and the clockwise face normal on the
    same side as the vertex normals for nearly every face.  The few that are
    not are the kits' own creased or degenerate faces (at most 2% measured)."""
    from zmforge.props.build import game_mesh
    from zmforge.props.fetch import default_cache
    from zmforge.props.library import PROPS as KIT_PROPS

    cache = default_cache()
    work = cache / "extracted-for-tests"
    for entry in KIT_PROPS:
        game, _scale, _note = game_mesh(entry, work, cache)
        bindings = [MaterialBinding(m, "m", "m.tif") for m in game.materials]
        agree, faces, volume = _export_winding(xmodel_export_text(game, entry.name, bindings))
        assert volume < 0, (entry.name, volume)
        assert agree >= 0.98 * faces, (entry.name, agree, faces)


def test_every_shelf_board_is_inside_its_models_measured_box() -> None:
    """Boards are the model's own frame, lowest first, and inside the box."""
    from zmforge.recipes.props import MODEL_BOX, SHELF_BOARDS

    assert set(SHELF_BOARDS) == {"p7_shelf_metal_lab_01", "p7_shelf_industrial_vintage_96"}
    for name, boards in SHELF_BOARDS.items():
        (_x0, _y0, z0), (_x1, _y1, z1) = MODEL_BOX[name]
        assert list(boards) == sorted(boards), name
        assert z0 < boards[0] and boards[-1] < z1, name
    assert len(SHELF_BOARDS["p7_shelf_metal_lab_01"]) == 8
    assert len(SHELF_BOARDS["p7_shelf_industrial_vintage_96"]) == 3


def test_shelf_boards_are_measured_from_the_base_the_placer_rests_on() -> None:
    """The lab shelf's box starts 0.433 over its origin, so its bottom board
    is 10.417 over the floor it is rested on, not 10.85."""
    from zmforge.recipes.props import shelf_boards

    assert shelf_boards("p7_shelf_metal_lab_01", 100.0)[0] == pytest.approx(110.417)
    assert shelf_boards("p7_shelf_industrial_vintage_96", 0.0) == (23.44, 51.91, 79.94)
    assert shelf_boards("p7_sandbag_02", 0.0) == ()
