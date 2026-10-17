"""zmforge render tooling: room hashes, contact/compare sheets, run folders, --changed, assets."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from zmforge.render import assets, roomhash, sheets
from zmforge.render import run as render_run

MAP = """iwmap 4
// entity 0
{
guid "{0}"
"classname" "worldspawn"
"ssi" "default_day"
// brush 0
{
 guid "{A}"
 ( 0 0 0 ) ( 0 100 0 ) ( 100 0 0 ) caulk 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
 ( 0 0 16 ) ( 100 0 16 ) ( 0 100 16 ) t7_floor 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
}
// brush 1
{
 guid "{B}"
 ( 500 0 0 ) ( 500 100 0 ) ( 600 0 0 ) caulk 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
 ( 500 0 16 ) ( 600 0 16 ) ( 500 100 16 ) t7_floor 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
}
}
// entity 1
{
guid "{C}"
"classname" "misc_model"
"model" "zmf_prop_donut"
"origin" "50 50 16"
}
// entity 2
{
guid "{D}"
"classname" "misc_prefab"
"model" "_prefabs/zm/zm_core/power_switch.map"
"origin" "550 50 16"
}
"""


def _areas():
    return [SimpleNamespace(key="west", room_id="w", x0=0, y0=0, x1=100, y1=100,
                            floor_z=16, ceiling_z=128),
            SimpleNamespace(key="east", room_id="e", x0=500, y0=0, x1=600, y1=100,
                            floor_z=16, ceiling_z=128)]


def test_room_hash_changes_only_for_the_room_that_changed():
    before = roomhash.room_hashes(MAP, _areas())
    moved = MAP.replace('"origin" "50 50 16"', '"origin" "60 50 16"')
    after = roomhash.room_hashes(moved, _areas())
    assert roomhash.changed_rooms(after, before) == ["west"]


def test_room_hash_ignores_guids_and_brush_numbers():
    renumbered = MAP.replace("{A}", "{Z}").replace("// brush 1", "// brush 7")
    assert roomhash.room_hashes(renumbered, _areas()) == roomhash.room_hashes(MAP, _areas())


def test_room_hash_folds_in_views_and_settings():
    base = roomhash.room_hashes(MAP, _areas())
    view = {"room": "east", "name": "corner-sw", "x": 1, "y": 1, "z": 1, "pitch": 0, "yaw": 0}
    assert roomhash.changed_rooms(roomhash.room_hashes(MAP, _areas(), views=[view]),
                                  base) == ["east"]
    assert set(roomhash.changed_rooms(
        roomhash.room_hashes(MAP, _areas(), settings={"lighting": "baked"}), base)) == {
        "west", "east"}


def test_worldspawn_keys_have_no_box():
    blocks = roomhash.split_blocks(MAP)
    assert sum(b.box is None for b in blocks) == 1
    assert len(blocks) == 5          # worldspawn keys, two brushes, two entities


def test_used_assets_lists_materials_and_models_not_prefabs():
    materials, models = assets.used_assets(MAP)
    assert materials == {"caulk", "t7_floor"}
    assert models == {"zmf_prop_donut"}


def test_find_gdts_prefers_the_generated_tree(tmp_path):
    gen, tools = tmp_path / "gen", tmp_path / "tools"
    for root in (gen, tools):
        (root / "texture_assets" / "zmforge_art").mkdir(parents=True)
    (gen / "texture_assets" / "zmforge_art" / "a.gdt").write_text(
        '{\n\t"zmf_poster" ( "material.gdf" )\n\t{\n\t}\n}\n')
    (tools / "texture_assets" / "zmforge_art" / "a.gdt").write_text(
        '{\n\t"zmf_poster" ( "material.gdf" )\n\t{\n\t}\n}\n')
    (tools / "texture_assets" / "stock.gdt").write_text('{\n\t"t7_x" ( "material.gdf" )\n}\n')
    found = assets.find_gdts(["zmf_poster", "absent"], [gen, tools])
    assert found == [(gen, gen / "texture_assets" / "zmforge_art" / "a.gdt")]


def _png(path: Path, colour) -> Path:
    Image.new("RGB", (320, 172), colour).save(path)
    return path


def test_contact_sheet_is_at_most_1024(tmp_path):
    shots = {room: [_png(tmp_path / f"{room}--corner-{i}.png", (40 * i, 80, 120))
                    for i in range(3)] for room in ("a", "b", "c")}
    (sheet,) = sheets.contact_sheets(shots, tmp_path)
    with Image.open(sheet) as im:
        assert max(im.size) <= sheets.MAX_SIDE and im.width > im.height / 2
    many = {f"r{i}": v for i, v in enumerate(list(shots.values()) * 3)}
    assert len(sheets.contact_sheets(many, tmp_path, rooms_per_sheet=4)) == 3


def test_compare_pairs_by_file_name_and_marks_missing(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(), new.mkdir()
    _png(old / "a--corner-sw.png", (255, 0, 0))
    _png(new / "a--corner-sw.png", (0, 255, 0))
    _png(new / "b--corner-sw.png", (0, 0, 255))
    pairs = sheets.pair_shots(old, new)
    assert [(s, o is not None, n is not None) for s, o, n in pairs] == [
        ("a--corner-sw", True, True), ("b--corner-sw", False, True)]
    written = sheets.compare_sheets(old, new, tmp_path / "cmp")
    assert [p.name for p in written] == ["a--corner-sw.jpg", "b--corner-sw.jpg"]
    with Image.open(written[0]) as im:
        left = im.getpixel((im.width // 4, im.height // 2))
        right = im.getpixel((3 * im.width // 4, im.height // 2))
    assert left[0] > 200 and right[1] > 200          # before red, after green


# ----------------------------------------------------------------------
# Run folders and --changed, with generate and Radiant faked.
# ----------------------------------------------------------------------
@pytest.fixture
def fake_render(tmp_path, monkeypatch):
    """render_recipe over the MAP above; returns a dict to edit the map and count shots."""
    state = {"map": MAP, "shot": []}
    from zmforge.render import cameras, radiant
    from zmforge.review import facts

    def generate(recipe, name, scratch, keep):
        mp = Path(scratch) / "map_source" / "zm" / f"{name}.map"
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(state["map"])
        return SimpleNamespace(paths={"map": str(mp)}, blueprint="bp")

    def plan(bp, rooms=None, limit=None):
        out = []
        for a in _areas():
            if rooms is None or a.key in rooms:
                out += cameras.corner_views(a)[:limit]
        return out

    def render_views(map_file, views, out_dir, *, width, log, timing, **kw):
        state["shot"].append(sorted({v.room for v in views}))
        timing["radiant_load"] = 0
        res = []
        for v in views:
            res.append((v, _png(out_dir / f"{v.slug}.png", (len(state["shot"]) * 60, 0, 0))))
        return res

    monkeypatch.setattr(render_run, "DEFAULT_OUT", tmp_path / "render")
    monkeypatch.setattr(facts, "generate", generate)
    monkeypatch.setattr(facts, "_areas", lambda bp: _areas())
    monkeypatch.setattr(render_run, "plan_views", plan)
    monkeypatch.setattr(radiant, "render_views", render_views)
    monkeypatch.setattr(radiant, "require_render_tools", lambda tools: None)
    monkeypatch.setattr(radiant.RadiantCamera, "tools", tmp_path / "tools", raising=False)
    monkeypatch.setattr(assets, "prepare", lambda *a, **k: assets.Registration())
    from zmforge.render import propfix
    monkeypatch.setattr(propfix, "prepare", lambda *a, **k: propfix.PropFix())

    def call(**kw):
        return render_run.render_recipe("x", name="zm_x", views=2, **kw)
    state["call"] = call
    return state


def test_layout_latest_and_sheet(fake_render, tmp_path):
    m = fake_render["call"]()
    run = Path(m["out"])
    assert run.parent == tmp_path / "render" / "zm_x"
    assert (run.parent / "latest").resolve() == run
    assert (run / "sheet.jpg").is_file()
    saved = json.loads((run / "views.json").read_text())
    assert set(saved["room_hashes"]) == {"west", "east"} and saved["rendered"] == ["west", "east"]


def test_changed_renders_only_the_changed_room_and_reuses_the_rest(fake_render):
    first = fake_render["call"]()
    fake_render["map"] = MAP.replace('"origin" "550 50 16"', '"origin" "560 50 16"')
    second = fake_render["call"](changed=True, compare="latest")
    assert fake_render["shot"] == [["east", "west"], ["east"]]
    assert second["rendered"] == ["east"] and second["reused"] == ["west"]
    assert set(second["shots"]) == {"west", "east"}
    for p in second["shots"]["west"]:        # hard-linked from the first run
        assert Path(p).parent == Path(second["out"]) and Path(p).is_file()
    assert {Path(p).stem for p in second["compare"]["sheets"]} == {
        "east--corner-sw", "east--corner-ne"}
    assert Path(first["out"]) != Path(second["out"])


def test_changed_with_nothing_changed_starts_no_radiant(fake_render):
    first = fake_render["call"]()
    again = fake_render["call"](changed=True)
    assert fake_render["shot"] == [["east", "west"]]
    assert again["out"] == first["out"] and again["reused"] == ["west", "east"]


def test_changed_with_nothing_changed_keeps_a_user_out_folder(fake_render, tmp_path):
    """--changed --out <dir> once rmtree'd the user's folder when no room changed."""
    fake_render["call"]()
    mine = tmp_path / "my-folder"
    mine.mkdir()
    (mine / "notes.txt").write_text("precious")
    again = fake_render["call"](changed=True, out=mine)
    assert again["reused"] == ["west", "east"]
    assert (mine / "notes.txt").read_text() == "precious"
    assert not (mine / "gen").exists()          # what the call made is gone
    fresh = tmp_path / "new-folder"             # a folder the call created itself
    fake_render["call"](changed=True, out=fresh)
    assert not fresh.exists()


def test_partial_run_carries_other_rooms_forward(fake_render):
    fake_render["call"]()
    part = fake_render["call"](rooms=["east"])
    assert list(part["shots"]) == ["east"] and "west" in part["carried"]
    fake_render["call"](changed=True)          # west still known, so nothing to shoot
    assert fake_render["shot"] == [["east", "west"], ["east"]]


# ----------------------------------------------------------------------
# The box-wide Radiant lock (build-out/.radiant.lock).
# ----------------------------------------------------------------------
def test_radiant_lock_waits_for_another_holder_and_never_matches_itself(tmp_path):
    import subprocess
    import time as _time

    from zmforge.render.radiant import RadiantLock, lock_holders

    lock = tmp_path / ".radiant.lock"
    # A waiter whose command line names the lock and "your build script" must not
    # count as a holder (the old pgrep guard did, and deadlocked).
    with RadiantLock(lock) as mine:
        assert mine.fh is not None and not mine.inherited
        assert lock_holders(lock) == {__import__("os").getpid()}
    holder = subprocess.Popen(["flock", str(lock), "sh", "-c", "sleep 30 # your build script"],
                              start_new_session=True)
    try:
        for _ in range(50):
            if lock_holders(lock):
                break
            _time.sleep(0.1)
        assert lock_holders(lock) and __import__("os").getpid() not in lock_holders(lock)
        with pytest.raises(TimeoutError):
            RadiantLock(lock).acquire(timeout=1)
    finally:
        __import__("os").killpg(holder.pid, 9)   # flock and its sleeping child
        holder.wait()
    with RadiantLock(lock) as again:          # free once the holder is gone
        assert again.fh is not None


def test_radiant_lock_held_by_an_ancestor_does_not_block(tmp_path):
    import subprocess
    import sys

    lock = tmp_path / ".radiant.lock"
    code = ("from pathlib import Path; from zmforge.render.radiant import RadiantLock;"
            f"l = RadiantLock(Path({str(lock)!r})).acquire(timeout=5); print(l.inherited)")
    done = subprocess.run(["flock", str(lock), sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-400:]
    assert done.stdout.strip() == "True"


# ----------------------------------------------------------------------
# Kit prop render copies (render/propfix.py): pure parts only.
# ----------------------------------------------------------------------
EXPORT = """MODEL
NUMVERTS 1
VERT 0
NORMAL 0 0 1
COLOR 0.000000 0.000000 0.000000 1.000000
UV 1 0.5 0.5
VERT 0
NORMAL 0 0 1
COLOR 0.000000 0.000000 0.000000 1.000000
UV 1 0.5 0.5
NUMOBJECTS 1
NUMMATERIALS 1
MATERIAL 0 "zmf_kit_food" "Lambert" "color_map:zmf_kit_food_c.tif"
COLOR 0.000000 0.000000 0.000000 1.000000
"""


def test_whiten_changes_vertex_colours_not_the_material_colour():
    from zmforge.render.propfix import color_maps, whiten

    text, n = whiten(EXPORT)
    assert n == 2
    assert text.count("COLOR 1.000000 1.000000 1.000000 1.000000") == 2
    assert text.rstrip().endswith("COLOR 0.000000 0.000000 0.000000 1.000000")
    assert whiten(text)[1] == 0                 # idempotent
    assert color_maps(EXPORT) == [("zmf_kit_food", "zmf_kit_food_c.tif")]


def test_plan_picks_black_exports_and_8bit_tifs_only(tmp_path):
    from zmforge.render import propfix

    tools = tmp_path
    (tools / "model_export" / "zm_kit").mkdir(parents=True)
    (tools / "texture_assets" / "zm_kit").mkdir(parents=True)
    for name, text in (("zmf_prop_donut", EXPORT), ("zmf_prop_white", propfix.whiten(EXPORT)[0])):
        (tools / "model_export" / "zm_kit" / f"{name}.XMODEL_EXPORT").write_text(text)
        (tools / "model_export" / "zm_kit" / f"{name}.XMODEL_BIN").write_bytes(b"bin")
    Image.new("RGB", (8, 8), (200, 100, 50)).save(
        tools / "texture_assets" / "zm_kit" / "zmf_kit_food_c.tif", compression=None)
    exports, tifs = propfix.plan(["zmf_prop_donut", "zmf_prop_white", "p7_stock", "zmf_absent"],
                                 tools)
    assert [m for m, _ in exports] == ["zmf_prop_donut"]
    assert [t.name for t in tifs] == ["zmf_kit_food_c.tif"]
    assert propfix.tif_bits(tifs[0]) == 8


def _bin(payload: bytes) -> bytes:
    from zmforge.render.propfix import write_model_bin
    return write_model_bin(payload)


def test_lz4_round_trip_and_a_real_compressed_block():
    from zmforge.render.propfix import lz4_block_decompress, read_model_bin, write_model_bin

    payload = bytes(range(256)) * 3
    assert read_model_bin(write_model_bin(payload)) == payload
    # "abcabcabcabc" as literals "abc" plus a 9-byte overlapping match at offset 3.
    block = bytes([0x35]) + b"abc" + bytes([3, 0])
    assert lz4_block_decompress(block, 12) == b"abcabcabcabc"


def test_whiten_bin_changes_vertex_colours_before_the_material_only():
    from zmforge.render.propfix import read_model_bin, whiten_bin

    rec = b"\xd8\x6d\x00\x00"
    payload = (b"head" + (rec + b"\x00\x00\x00\xff" + b"uvuv") * 3
               + b"zmf_kit_food\x00" + rec + b"\x00\x00\x00\xff")
    out, n = whiten_bin(_bin(payload), ["zmf_kit_food"])
    back = read_model_bin(out)
    assert n == 3
    assert back.count(rec + b"\xff\xff\xff\xff") == 3
    assert back.endswith(b"zmf_kit_food\x00" + rec + b"\x00\x00\x00\xff")
    assert len(back) == len(payload)


def test_prepare_writes_cached_white_copies_and_mounts_them(tmp_path):
    from zmforge.render import propfix

    tools = tmp_path / "tools"
    (tools / "model_export" / "zm_kit").mkdir(parents=True)
    export = tools / "model_export" / "zm_kit" / "zmf_prop_donut.XMODEL_EXPORT"
    export.write_text(EXPORT)
    rec = b"\xd8\x6d\x00\x00"
    export.with_suffix(".XMODEL_BIN").write_bytes(
        _bin(b"x" + (rec + b"\x00\x00\x00\xff") * 2 + b"zmf_kit_food\x00"))
    cache = tmp_path / "cache"
    fix = propfix.prepare(["zmf_prop_donut", "p7_stock"], tools=tools, cache=cache)
    assert fix.models == ["zmf_prop_donut"] and not fix.errors
    (host, inside), = fix.mounts
    assert inside == "/tools/model_export/zm_kit/zmf_prop_donut.XMODEL_BIN"
    assert propfix.read_model_bin(Path(host).read_bytes()).count(rec + b"\xff" * 4) == 2
    mtime = Path(host).stat().st_mtime_ns
    again = propfix.prepare(["zmf_prop_donut"], tools=tools, cache=cache)
    assert again.mounts == fix.mounts and Path(host).stat().st_mtime_ns == mtime


def test_kit_materials_lists_the_placed_kit_props_materials_once(tmp_path):
    from zmforge.render import propfix

    (tmp_path / "model_export" / "zm_kit").mkdir(parents=True)
    for name in ("zmf_prop_donut", "zmf_prop_cake"):
        (tmp_path / "model_export" / "zm_kit" / f"{name}.XMODEL_EXPORT").write_text(EXPORT)
        (tmp_path / "model_export" / "zm_kit" / f"{name}.XMODEL_BIN").write_bytes(b"b")
    assert propfix.kit_materials(["zmf_prop_donut", "zmf_prop_cake", "p7_stock"],
                                 tmp_path) == ["zmf_kit_food"]


def test_baked_lighting_uses_radiant_hotkeys_and_a_real_bake():
    """Clicking a toolbar toggle for --baked gets Radiant's default fake
    light, so the modes are hotkeys, and "baked" is Real
    Lighting after Build Lighting, with the Exposure toolbar's bolt detected."""
    from zmforge.render import radiant

    assert radiant.LIGHTING_KEYS["real"] == radiant.LIGHTING_KEYS["baked"] == "F8"
    assert radiant.LIGHTING_KEYS["normal"] == "F7"
    assert set(radiant.BAKE_QUALITY) == {"low", "medium", "high"}
    assert radiant.RadiantCamera(Path("x.map")).bake_quality == "medium"
    assert radiant.bolt_visible("0.2\n")
    assert not radiant.bolt_visible("0")
    assert not radiant.bolt_visible("")


def test_render_recipe_asks_radiant_for_a_bake_when_baked():
    import inspect
    from zmforge.render import run

    assert 'lighting="baked" if baked else "fake"' in inspect.getsource(run.render_recipe)


def test_model_materials_reads_names_out_of_a_text_export(tmp_path) -> None:
    """The stock-image census resolves a model to its materials by
    the identifier runs in its LOD0 file; the caller keeps only real materials."""
    (tmp_path / "props").mkdir()
    (tmp_path / "props" / "thing_LOD0.xmodel_export").write_text(
        'MATERIAL 0 "mtl_p7_thing" "lit" "color_map:p7_thing_c.tif"\n')
    names = assets._model_materials(tmp_path, "props\\\\thing_LOD0.xmodel_export")
    assert "mtl_p7_thing" in names
    assert assets._model_materials(tmp_path, "props\\\\missing.XMODEL_BIN") == []


_TOOLS = Path("<bo3-wine>/tools")


@pytest.mark.skipif(not (_TOOLS / "gdtdb" / "gdt.db").is_file() or not assets.WIDE.exists(),
                    reason="needs a mod tools tree and the wide SQLite")
def test_stock_images_finds_the_8bit_sources_radiant_cannot_convert() -> None:
    """The measured cause of the blotchy teal surfaces in the baked README
    photos: t7_plastic_panels_white (the DMV ceiling) and the
    compact car have 8-bit colour maps, which Radiant under Wine fails to
    convert; the census must find them so the render can copy them to 16 bits."""
    from zmforge.render.propfix import tif_bits

    tifs = assets.stock_images({"t7_plastic_panels_white"}, {"veh_t7_civ_car_compact"},
                               tools=_TOOLS)
    eight = {t.name for t in tifs if t.is_file() and tif_bits(t) == 8}
    assert "t7_plastic_panels_white_c.tif" in eight
    assert any("car_compact" in name for name in eight)
    # Radiant also failed a stock 16-bit grey mask (the waiting chair's), and
    # converted every 16-bit RGB source: that is the line needs_copy draws.
    from zmforge.render.propfix import needs_copy

    assert needs_copy(_TOOLS / "model_export/t7_props/p7_chair_waiting_room_01/"
                      "p7_chair_waiting_room_01_m.tif")
    assert needs_copy(_TOOLS / "texture_assets/t7_materials/t7_plastic_panels_white_c.tif")
    assert not needs_copy(_TOOLS / "texture_assets/t7_materials/t7_plaster_smooth_light_01_c.tif")


def test_model_materials_finds_a_model_file_whose_case_differs(tmp_path) -> None:
    """The gdt.db names the hurricane lamp's LOD as
    ``..._lod1.XMODEL_BIN``, the file on disk is ``..._lod1.xmodel_bin``.
    Matched case-sensitively the model had no materials, its 8-bit images got
    no 16-bit copies and every cemetery lantern drew Radiant's pale-blue
    missing-image fallback in the presentation renders."""
    (tmp_path / "t7_props" / "lamp").mkdir(parents=True)
    (tmp_path / "t7_props" / "lamp" / "lamp_lod1.xmodel_export").write_text(
        'MATERIAL 0 "mtl_p7_lamp" "lit" "color_map:lamp_c.tif"\n')
    names = assets._model_materials(tmp_path, "T7_Props\\\\lamp\\\\lamp_lod1.XMODEL_EXPORT")
    assert "mtl_p7_lamp" in names


def test_presentation_renders_leave_out_script_switched_lights() -> None:
    """Event-only lights (exploder lights the map's script switches, e.g. the
    cemetery's will-o'-wisp flashes) never reach Radiant: Real Lighting draws
    every light it loads, the game bakes none of them."""
    from zmforge.render.radiant import without_script_lights

    head = 'iwmap 4\n// entity 0\n{\nguid "{A}"\n"classname" "worldspawn"\n{\nbrush\n}\n}\n'
    lamp = '// entity 1\n{\nguid "{B}"\n"classname" "light"\n"_color" "1 0.62 0.3"\n}\n'
    wisp = ('// entity 2\n{\nguid "{C}"\n"classname" "light"\n"_color" "0.55 0.85 1"\n'
            '"exploderDisabled" "1"\n"exploder_count" "1"\n'
            '"exploder_index_0" "ver=2 name=zmf_glow_wisp0_light"\n}\n')
    out, dropped = without_script_lights(head + lamp + wisp)
    assert dropped == 1
    assert out == head + lamp


# ----------------------------------------------------------------------
# GPU containers are removed however a render ends (fake docker, no GPU).
# ----------------------------------------------------------------------
@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    """A ``docker`` on PATH that records its arguments and answers ``ps`` from a file."""
    import os
    import stat
    import sys

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls, ps = tmp_path / "docker-calls.txt", tmp_path / "docker-ps.txt"
    ps.write_text("")
    script = bindir / "docker"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        f"if sys.argv[1:3] == ['ps', '-a']: sys.stdout.write(open({str(ps)!r}).read())\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("ZMFORGE_RENDER_KEEP", raising=False)
    return SimpleNamespace(calls=calls, ps=ps)


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_a_start_that_fails_after_docker_run_removes_the_container(
    tmp_path, monkeypatch, fake_docker, failure
):
    import os

    from zmforge.render import radiant

    cam = radiant.RadiantCamera(tmp_path / "zm_x.map", tools=tmp_path, work=tmp_path / "w")
    for step in ("_lock", "_ensure_image", "_wait_vram"):
        monkeypatch.setattr(cam, step, lambda: None)
    monkeypatch.setattr(cam, "_prefix", lambda: tmp_path / "prefix")
    monkeypatch.setattr(cam, "_stage_map", lambda: "C:\\x.map")

    def interrupted():
        raise failure("Ctrl-C while Radiant loads")

    monkeypatch.setattr(cam, "_wait_loaded", interrupted)
    with pytest.raises(failure):
        with cam:
            pytest.fail("the body must not run")
    name = f"zmforge-render-{os.getpid()}"
    calls = fake_docker.calls.read_text().splitlines()
    ran = next(i for i, c in enumerate(calls) if c.startswith("run -d"))
    assert f"rm -f {name}" in calls[ran + 1:]
    assert cam.container is None and id(cam) not in radiant._LIVE


def test_the_startup_sweep_removes_only_containers_of_dead_renders(fake_docker):
    import os
    import subprocess
    import sys

    from zmforge.render import radiant

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    fake_docker.ps.write_text(
        f"zmforge-render-{dead.pid}\t\n"            # crashed render: removed
        f"zmforge-render-{os.getpid()}\t\n"         # this process: kept
        f"zmforge-render-{os.getppid()}\t\n"        # a live process: kept
        f"zmforge-render-{dead.pid + 0}x\t\n"       # not ours: kept
    )
    removed = radiant.sweep_stale_containers()
    assert removed == [f"zmforge-render-{dead.pid}"]
    # Left on purpose with ZMFORGE_RENDER_KEEP=1: kept even with its pid gone.
    fake_docker.ps.write_text(f"zmforge-render-{dead.pid}\t1\n")
    assert radiant.sweep_stale_containers() == []
