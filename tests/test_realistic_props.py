"""Per-prop materials, the generated straw bale, glTF import with quadric
decimation, and the Python ``.XMODEL_BIN`` writer."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from zmforge.props.library import KITS, PHOTO_V, PROPS, Prop, PropMaterial, prop
from zmforge.props.wavefront import Mesh, Triangle
from zmforge.props.xmodel import MaterialBinding, to_game_space, xmodel_export_text

TOOLS = Path("<bo3-wine>/tools")
DEPLOYED = TOOLS / "model_export" / "zm_forge_gate"


# --------------------------------------------------------------------- bin
@pytest.mark.skipif(not DEPLOYED.is_dir(), reason="no kit props in the tools tree")
def test_the_python_bin_writer_matches_every_windows_built_kit_binary() -> None:
    """Every kit export in the tools tree, put through the Python writer, is byte for byte what
    the stock ``export2bin.exe`` wrote beside it."""
    from zmforge.props.xmodel_bin import export_to_payload
    from zmforge.render.propfix import read_model_bin

    compared = 0
    for export in sorted(DEPLOYED.glob("*.XMODEL_EXPORT")):
        binary = export.with_suffix(".XMODEL_BIN")
        if not binary.is_file():
            continue
        want = read_model_bin(binary.read_bytes())
        assert export_to_payload(export.read_text(encoding="utf-8")) == want, export.name
        compared += 1
    assert compared >= 20


def test_the_bin_writer_round_trips_through_the_lz4_wrapper(tmp_path) -> None:
    from zmforge.props.xmodel_bin import export_to_bin, export_to_payload
    from zmforge.render.propfix import read_model_bin

    mesh = _quad_mesh()
    text = xmodel_export_text(mesh, "t", [MaterialBinding("m", "mat", "mat.tif")], stamp="x")
    data = export_to_bin(text)
    assert data[:5] == b"*LZ4*"
    assert read_model_bin(data) == export_to_payload(text)


def test_the_bin_writer_refuses_what_it_does_not_know() -> None:
    from zmforge.props.xmodel_bin import export_to_payload

    with pytest.raises(ValueError):
        export_to_payload("MODEL\nVERSION 6\n")
    with pytest.raises(ValueError):
        export_to_payload("MODEL\nVERSION 7\nNUMVERTS 70000\n")
    with pytest.raises(ValueError):
        export_to_payload("MODEL\nVERSION 7\nSOMETHING 1\n")


def test_normals_round_half_away_from_zero_in_float32() -> None:
    """-0.623661 * 32767 is -20435.5 in float32; the stock export2bin.exe writes -20436."""
    from zmforge.props.xmodel_bin import _unit16

    assert struct.unpack("<3h", _unit16(["-0.623661", "0", "1"])) == (-20436, 0, 32767)


# -------------------------------------------------------- per-prop material
def _quad_mesh() -> Mesh:
    return Mesh(
        positions=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        uvs=[(0, 0), (1, 0), (1, 1), (0, 1)],
        triangles=[Triangle("m", (0, 1, 2), (-1, -1, -1), (0, 1, 2)),
                   Triangle("m", (0, 2, 3), (-1, -1, -1), (0, 2, 3))],
    )


def test_swatch_uv_sits_in_the_strip_below_the_photo() -> None:
    from zmforge.props.build import swatch_uv

    pm = PropMaterial("a", "a_c", swatches=(("twine", (1, 0, 0)), ("tag", (0, 1, 0))))
    u0, v0 = swatch_uv(pm, "twine")
    u1, v1 = swatch_uv(pm, "tag")
    assert (u0, u1) == (0.25, 0.75)
    assert v0 == v1 and PHOTO_V < v0 < 1.0


def test_prop_image_squeezes_the_photo_above_the_swatch_strip(tmp_path) -> None:
    from PIL import Image

    from zmforge.props.build import prop_image

    photo = tmp_path / "p.png"
    Image.new("RGB", (64, 64), (10, 200, 30)).save(photo)
    entry = Prop("zmf_t", "zmforge_generated", "straw_bale", 10.0, "t",
                 material=PropMaterial("m", "m_c", size=64,
                                       swatches=(("twine", (1.0, 0.0, 0.0)),)))
    mesh = Mesh(textures={"x": str(photo)})
    image = prop_image(entry, mesh, tmp_path)
    assert image.size == (64, 64)
    assert image.getpixel((5, 5)) == (10, 200, 30)
    assert image.getpixel((5, 63)) == (255, 0, 0)
    assert image.getpixel((5, round(64 * PHOTO_V) - 1)) == (10, 200, 30)


def test_a_prop_with_its_own_material_gets_its_own_image_and_material(tmp_path) -> None:
    """The opted-in prop binds to its own material and image; a kit prop
    built beside it keeps the kit's shared atlas, unchanged."""
    from zmforge.props.build import build, kit_palette

    kit_prop = prop("zmf_prop_tree_stump")
    try:
        build("zm_t", tmp_path / "out",
              [kit_prop, prop("zmf_prop_hay_bale"), prop("zmf_prop_pumpkin")],
              work=tmp_path / "w")
    except OSError as exc:  # pragma: no cover - offline without a cache
        pytest.skip(f"assets not cached: {exc}")
    tex = tmp_path / "out" / "texture_assets"
    assert (tex / "zm_t" / "zmf_straw_bale_c.tif").is_file()
    assert (tex / "zm_t" / "zmf_ph_tree_stump_01_c.tif").is_file()
    gdt = (tex / "zm_t_props_tex.gdt").read_text()
    assert '"zmf_straw_bale" ( "material.gdf" )' in gdt
    assert '"zmf_ph_tree_stump_01" ( "material.gdf" )' in gdt
    bale = (tmp_path / "out" / "model_export" / "zm_t" / "zmf_prop_hay_bale.XMODEL_EXPORT").read_text()
    assert 'MATERIAL 0 "zmf_straw_bale" "Lambert" "color_map:zmf_straw_bale_c.tif"' in bale
    assert "zmf_kenney" not in bale
    report = json.loads((tmp_path / "out" / "props.json").read_text())
    rows = {r["asset"]: r for r in report["props"]}
    assert rows["zmf_prop_hay_bale"]["texture"]["source"] == "ambientcg_thatched_roof_001a"
    assert rows["zmf_prop_tree_stump"]["triangles"] <= kit_prop.max_triangles
    credits = (tmp_path / "out" / "PROP-CREDITS.md").read_text()
    assert "ambientcg.com" in credits and "polyhaven.com/a/tree_stump_01" in credits
    # The Kenney pumpkin beside them keeps its kit's shared material and atlas.
    pumpkin = (tmp_path / "out" / "model_export" / "zm_t" / "zmf_prop_pumpkin.XMODEL_EXPORT").read_text()
    assert 'MATERIAL 0 "zmf_kenney_graveyard" "Lambert" "color_map:zmf_kenney_graveyard_c.tif"' in pumpkin
    assert (tex / "zm_t" / "zmf_kenney_graveyard_c.tif").is_file()
    assert kit_palette("kenney_furniture", tmp_path / "w2").order


def test_every_twine_corner_uses_the_swatch_uv(tmp_path) -> None:
    from zmforge.props.build import build

    build("zm_t", tmp_path / "o", [prop("zmf_prop_hay_bale")], work=tmp_path / "w")
    text = (tmp_path / "o" / "model_export" / "zm_t" / "zmf_prop_hay_bale.XMODEL_EXPORT").read_text()
    uvs = [tuple(map(float, line.split()[2:4])) for line in text.splitlines()
           if line.startswith("UV 1 ")]
    strip = [v for _u, v in uvs if v > PHOTO_V]
    photo = [v for _u, v in uvs if v <= PHOTO_V]
    assert strip and photo
    assert all(abs(v - (PHOTO_V + 1) / 2) < 1e-6 for v in strip)
    assert max(photo) < PHOTO_V


def test_kit_props_have_not_opted_in() -> None:
    """Only the hay, the corn and the photoscans have their own material;
    every other Kenney prop still uses its kit's shared material and atlas."""
    own = {p.name for p in PROPS if p.material is not None}
    assert own == {"zmf_prop_hay_bale", "zmf_prop_hay_bale_stack", "zmf_prop_dead_log",
                   "zmf_prop_corn_stalk", "zmf_prop_corn_stalk_thin",
                   "zmf_prop_tree_stump", "zmf_prop_wooden_crate",
                   "zmf_prop_dead_tree_a", "zmf_prop_dead_tree_b", "zmf_prop_dead_tree_c",
                   "zmf_prop_dead_tree_d", "zmf_prop_dead_tree_e", "zmf_prop_gamble_atm"}
    assert all(KITS[p.kit].kind == "zip" for p in PROPS if p.material is None)


# ------------------------------------------------------------ generated trees
@pytest.mark.parametrize("name", ["zmf_prop_dead_tree_a", "zmf_prop_dead_tree_b",
                                  "zmf_prop_dead_tree_c", "zmf_prop_dead_tree_d",
                                  "zmf_prop_dead_tree_e"])
def test_the_generated_dead_tree_fills_its_recorded_box_with_the_trunk_on_the_origin(name) -> None:
    """The recipes plant a tree by its trunk: the box is symmetric round the
    origin, the mesh is under budget (no decimation), and every UV is in 0..1."""
    from zmforge.props.build import game_mesh
    from zmforge.props.collision import bounds_of
    from zmforge.recipes.props import MODEL_BOX

    game, _scale, note = game_mesh(prop(name), Path("/nonexistent"))
    assert "left alone" in note
    box = bounds_of(game)
    got = ((box.mins.x, box.mins.y, box.mins.z), (box.maxs.x, box.maxs.y, box.maxs.z))
    for a, b in zip(got, MODEL_BOX[name]):
        for x, y in zip(a, b):
            assert abs(x - y) <= 0.001, (name, got)
    assert all(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 for u, v in game.uvs)


# ------------------------------------------------------------ generated bale
@pytest.mark.parametrize("name", ["zmf_prop_hay_bale", "zmf_prop_hay_bale_stack"])
def test_the_generated_bale_fills_the_kit_bale_s_recorded_box(name) -> None:
    """Same name, same box: every recipe keeps its placements."""
    from zmforge.props.build import game_mesh
    from zmforge.props.collision import bounds_of
    from zmforge.recipes.props import MODEL_BOX

    game, scale, note = game_mesh(prop(name), Path("/nonexistent"))
    assert "left alone" in note  # the bevels survive: no clustering
    box = bounds_of(game)
    got = ((box.mins.x, box.mins.y, box.mins.z), (box.maxs.x, box.maxs.y, box.maxs.z))
    for a, b in zip(got, MODEL_BOX[name]):
        for x, y in zip(a, b):
            assert abs(x - y) <= 0.001, (name, got)


def test_the_generated_bale_faces_outward_and_is_closed() -> None:
    import numpy as np

    from zmforge.props.generated import straw_bale

    game, _ = to_game_space(straw_bale(), 40.0)
    pts = np.array(game.positions)
    tris = np.array([t.position for t in game.triangles if t.material == "straw"])
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    volume = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    # Outward faces, and the volume of a slightly rounded 40 x 26.5 x 23.4 box.
    assert 0.85 * 40 * 26.5 * 23.35 < volume < 40 * 26.5 * 23.35
    assert {t.material for t in game.triangles} == {"straw", "twine"}


# ------------------------------------------------------------ glTF + decimate
def _write_gltf(tmp_path: Path, positions, uvs, indices, *, matrix=None) -> Path:
    import numpy as np

    pos = np.asarray(positions, dtype="<f4")
    uv = np.asarray(uvs, dtype="<f4")
    idx = np.asarray(indices, dtype="<u2").reshape(-1)
    blob = pos.tobytes() + uv.tobytes() + idx.tobytes()
    (tmp_path / "m.bin").write_bytes(blob)
    node = {"mesh": 0}
    if matrix is not None:
        node["matrix"] = matrix
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
        "buffers": [{"uri": "m.bin", "byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": pos.nbytes},
            {"buffer": 0, "byteOffset": pos.nbytes, "byteLength": uv.nbytes},
            {"buffer": 0, "byteOffset": pos.nbytes + uv.nbytes, "byteLength": idx.nbytes},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": len(uv), "type": "VEC2"},
            {"bufferView": 2, "componentType": 5123, "count": len(idx), "type": "SCALAR"},
        ],
        "images": [{"uri": "tex.png"}], "textures": [{"source": 0}],
        "materials": [{"name": "bark", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                                    "indices": 2, "material": 0}]}],
    }
    path = tmp_path / "m.gltf"
    path.write_text(json.dumps(doc))
    return path


def test_gltf_reads_positions_uvs_material_and_colour_map(tmp_path) -> None:
    from zmforge.props.gltf import read_gltf

    path = _write_gltf(tmp_path, [(0, 0, 0), (2, 0, 0), (2, 0, 3)],
                       [(0, 0), (1, 0), (1, 0.25)], [0, 1, 2])
    mesh = read_gltf(path)
    assert mesh.positions == [(0, 0, 0), (2, 0, 0), (2, 0, 3)]
    assert mesh.uvs[2] == (1.0, 0.75)  # glTF v runs down; Wavefront's up
    assert mesh.materials == ["bark"]
    assert mesh.textures["bark"].endswith("tex.png")


def test_gltf_applies_node_transforms_and_keeps_winding_under_a_mirror(tmp_path) -> None:
    from zmforge.props.gltf import read_gltf

    mirror = [-2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1]  # column-major
    mesh = read_gltf(_write_gltf(tmp_path, [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                                 [(0, 0)] * 3, [0, 1, 2], matrix=mirror))
    assert mesh.positions[1] == (3.0, 0.0, 0.0)
    assert mesh.triangles[0].position == (0, 2, 1)


def test_quadric_decimation_fits_the_budget_and_keeps_uvs_in_range() -> None:
    import math

    from zmforge.props.simplify import decimate_quadric

    n = 60  # a 60 x 60 wavy sheet, 7200 triangles
    positions, uvs, triangles = [], [], []
    for j in range(n + 1):
        for i in range(n + 1):
            positions.append((i, j, math.sin(i / 6) * math.cos(j / 7) * 3))
            uvs.append((i / n, j / n))
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            for tri in ((a, a + 1, a + n + 2), (a, a + n + 2, a + n + 1)):
                triangles.append(Triangle("m", tri, (-1, -1, -1), tri))
    mesh = Mesh(positions=positions, uvs=uvs, triangles=triangles)
    out, note = decimate_quadric(mesh, 1500)
    assert len(out.triangles) <= 1500 and "quadric" in note
    assert all(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 for u, v in out.uvs)
    # Each output vertex gets the UV of its spot on the sheet.  Taking the
    # UV of the collapsed vertex instead was off by up to 0.021 here
    # (measured); surface interpolation is within 0.0002.
    for (x, y, _z), (u, v) in zip(out.positions, out.uvs):
        assert abs(u - x / n) < 1e-3 and abs(v - y / n) < 1e-3
    assert len(out.normals) == len(out.positions)
    # A zero normal made Radiant draw the whole model as a grey box
    # (measured on the decimated log and stump).
    assert all(abs(sum(c * c for c in n) - 1.0) < 1e-6 for n in out.normals)


def test_imported_props_are_quadric_decimated_under_budget() -> None:
    for entry in PROPS:
        if KITS[entry.kit].kind == "gltf":
            assert entry.decimation == "quadric", entry.name
            assert 5000 <= entry.max_triangles <= 20000, entry.name


# ------------------------------------------------------------ render staging
def test_only_opted_in_props_are_staged_for_the_render() -> None:
    from zmforge.render.propfix import opted_in

    chosen = opted_in({"zmf_prop_pumpkin", "zmf_prop_hay_bale", "zmf_prop_dead_log",
                       "p7_crate_wood_01"})
    assert [p.name for p in chosen] == ["zmf_prop_hay_bale", "zmf_prop_dead_log"]


def test_a_grade_moves_the_photo_s_mean_colour_and_keeps_its_detail(tmp_path) -> None:
    import numpy as np
    from PIL import Image

    from zmforge.props.build import prop_image

    photo = tmp_path / "p.png"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(60, 160, (32, 32, 3)).astype(np.uint8)).save(photo)
    entry = Prop("zmf_t", "zmforge_generated", "straw_bale", 10.0, "t",
                 material=PropMaterial("m", "m_c", size=32, grade=(0.7, 0.6, 0.35)))
    out = np.asarray(prop_image(entry, Mesh(textures={"x": str(photo)}), tmp_path), dtype=float)
    mean = out.reshape(-1, 3).mean(axis=0) / 255
    assert np.allclose(mean, (0.7, 0.6, 0.35), atol=0.01)
    assert out[..., 0].std() > 10  # still a photo, not a flat fill


# ------------------------------------------------------------ gamble machine
def test_the_gamble_atm_fills_its_recorded_box_at_true_scale() -> None:
    """props/atm.py builds in inches: the pipeline must not rescale it, the
    box is the recorded one (front to -Y, origin at the floor centre), it is
    under budget (no decimation) and every UV is in 0..1 on two materials."""
    from zmforge.props.build import game_mesh
    from zmforge.props.collision import bounds_of
    from zmforge.props.library import prop
    from zmforge.recipes.props import MODEL_BOX

    entry = prop("zmf_prop_gamble_atm")
    game, scale, note = game_mesh(entry, Path("/tmp"))
    assert abs(scale - 1.0) < 1e-3
    assert "left alone" in note
    box = bounds_of(game)
    lo, hi = MODEL_BOX["zmf_prop_gamble_atm"]
    assert all(abs(a - b) < 0.01 for a, b in zip((box.mins.x, box.mins.y, box.mins.z), lo))
    assert all(abs(a - b) < 0.01 for a, b in zip((box.maxs.x, box.maxs.y, box.maxs.z), hi))
    assert set(game.materials) == {"body", "glow"}
    assert all(0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 for u, v in game.uvs)
    # The keypad deck is in front (-Y) of the origin, the conduit behind it.
    deck = [p for p, t in ((game.positions[t.position[0]], t) for t in game.triangles) if p[2] > 44]
    assert min(p[1] for p in deck) < -15.0


def test_every_gamble_atm_triangle_maps_inside_its_own_chart() -> None:
    """Shared charts (bolts, keys, slats) and planar charts never spill into a
    neighbour's texels: every corner's atlas pixel lies in its chart's box."""
    from zmforge.props.atm import model

    m = model()
    charts = {c.key: c for c in m.charts}
    for _piece, key, _flat, _pos, _nrm, uvs in m.tris:
        x, y, w, h = charts[key].px
        assert all(x - 1.5 <= u <= x + w + 1.5 and y - 1.5 <= v <= y + h + 1.5 for u, v in uvs), key
