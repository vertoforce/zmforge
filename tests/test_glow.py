"""Z64 and script.glow: a glow that belongs to an object goes out with it
(P12; a shot corn maze lantern must go dark)."""

from __future__ import annotations

from zmforge.emit.mapfile import build_document
from zmforge.emit.scripts import render_server_script
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import three_room_map
from zmforge.script.custom import CustomFunction, CustomScript
from zmforge.script.glow import glow_name, own_object, place_owned_glow
from zmforge.spatial import Point
from zmforge.verify.glows import check_glows, check_glows_blueprint, check_glows_files, looping_playfx

SPOT = Point(-40.0, -400.0, 64.0)


def _codes(report):
    return [f.code for f in report]


def test_owned_glow_is_an_exploder_light_switched_on_its_notify():
    bp = three_room_map("zm_forge_gate")
    place_owned_glow(bp, SPOT, owner="button", off_notify="zmf_split_sealed",
                     colour=(1.0, 0.1, 0.1), radius=110.0, id="btn_glow")
    name = glow_name("btn_glow")
    text = render_map_text(build_document(bp))
    block = text[text.index(f"name={name}") - 1500:text.index(f"name={name}") + 400]
    assert '"exploder_count" "1"' in block and '"exploderDisabled" "1"' in block
    assert '"spawnflags" "82"' in block
    gsc = render_server_script(bp.script)
    assert r"#using scripts\shared\exploder_shared;" in gsc
    assert f'level thread zmf_glow_watch( "{name}", "zmf_split_sealed", undefined );' in gsc
    assert "exploder::stop_exploder( str_glow );" in gsc
    assert check_glows_blueprint(bp).ok and not list(check_glows_blueprint(bp))


def test_two_owned_glows_share_one_watcher():
    bp = three_room_map("zm_forge_gate")
    for n in (1, 2):
        place_owned_glow(bp, SPOT, owner=f"b{n}", off_notify="done", id=f"g{n}")
    gsc = render_server_script(bp.script)
    assert gsc.count("function zmf_glow_watch(") == 1
    assert gsc.count("level thread zmf_glow_watch(") == 2


def test_static_lamp_by_an_owned_object_is_a_warning():
    bp = three_room_map("zm_forge_gate")
    bp.place_light(SPOT, radius=80.0, id="baked_glow")
    own_object(bp, "prize pumpkin", (SPOT.x + 20.0, SPOT.y, SPOT.z))
    found = [f for f in check_glows_blueprint(bp) if f.code == "Z64"]
    assert found and found[0].severity == "warning" and "prize pumpkin" in found[0].message


def test_static_lamp_far_from_owned_objects_is_fine():
    report = check_glows([("lamp", (0.0, 0.0, 0.0))], [{"label": "x", "point": [500.0, 0.0, 0.0]}], [])
    assert not list(report)


def test_looping_effect_played_with_playfx_is_a_warning():
    assert looping_playfx(['PlayFX( level._effect[ "powerup_on_caution" ], v );']) == ["powerup_on_caution"]
    assert looping_playfx(['PlayFX( level._effect[ "powerup_grabbed_caution" ], v );']) == []
    assert looping_playfx(['PlayFXOnTag( level._effect[ "powerup_on" ], e, "tag_origin" );']) == []
    bp = three_room_map("zm_forge_gate")
    bp.add_custom_logic(CustomScript(functions=(CustomFunction(
        "zmf_bad_pulse", ('PlayFX( level._effect[ "powerup_on" ], ( 0, 0, 0 ) );',)),)))
    assert "Z64" in _codes(check_glows_blueprint(bp))


def test_files_check_reads_map_lights_and_document():
    light = '{\n"classname" "light"\n"origin" "0 0 64"\n}\n'
    switched = '{\n"classname" "light"\n"exploder_count" "1"\n"origin" "0 0 64"\n}\n'
    doc = {"engine": {"owned_objects": [{"label": "sensor", "point": [10.0, 0.0, 64.0]}]}}
    assert _codes(check_glows_files(light, "", doc)) == ["Z64"]
    assert _codes(check_glows_files(switched, "", doc)) == []
    assert _codes(check_glows_files(light, "", None)) == []


def test_room_fill_is_not_an_objects_glow():
    owned = [{"label": "target", "point": [0.0, 0.0, 0.0]}]
    assert not list(check_glows([("eye_exam_room_fill_24", (0.0, 0.0, 65.0))], owned, []))
    assert list(check_glows([("eye_exam_sign_glow", (0.0, 0.0, 65.0))], owned, []))


def test_a_quest_target_glow_goes_out_on_its_own_hit_and_relights_on_reset():
    bp = three_room_map("zm_forge_gate")
    for n in (0, 1):
        place_owned_glow(bp, SPOT, owner=f"wisp {n}", off_notify=None, hit=("wisps", n), id=f"wisp{n}_light")
    gsc = render_server_script(bp.script)
    assert gsc.count("function zmf_glow_watch_hit(") == 1
    assert 'level thread zmf_glow_watch_hit( "zmf_glow_wisp1_light", "zmf_q_hit_wisps", 1, "zmf_q_end_wisps" );' in gsc
    assert "else if ( isdefined( j ) && j == n_target )" in gsc
