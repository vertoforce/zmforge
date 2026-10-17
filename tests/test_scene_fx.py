"""The scene API and the stock-FX helpers (docs/map-design-method.md)."""

import pytest

from zmforge.dressing import LINKED_FX, burning, declare_scene, embers, scenes_of, smouldering
from zmforge.emit.mapfile import build_document
from zmforge.recipes import one_room_map
from zmforge.spatial import Point


def test_burning_spot_reaches_map_and_zone():
    bp = one_room_map("zm_x")
    burning(bp, Point(0, 0, 0))
    smouldering(bp, Point(64, 0, 0))
    embers(bp, Point(-64, 0, 0))
    doc = build_document(bp)
    fx = [e for e in doc.entities if e.classname == "fx"]
    defs = {e.value("fxdef") for e in fx}
    assert "fire/fx_fire_ground_rubble_embers_50x50" in defs
    assert "smoke/fx_smk_smolder_lg" in defs and "fire/fx_fire_line_embers_50" in defs
    assert all(e.value("angles").startswith("270") for e in fx)
    zone = {(a.prefix, a.name) for a in bp.assets}
    assert all(("fx", d) in zone for d in defs)
    assert defs <= LINKED_FX
    assert any(e.classname == "light" and e.value("_color").startswith("1 0.45") for e in doc.entities)


def test_unlinked_fx_is_refused():
    from zmforge.dressing import place_fx

    with pytest.raises(ValueError):
        place_fx(one_room_map("zm_x"), Point(0, 0, 0), "fire/fx_fire_barrel_30x30")


def test_scene_declared_and_checked():
    from zmforge.verify.scenes import check_scenes

    bp = one_room_map("zm_x")
    codes = [f.code for f in check_scenes(bp).findings]
    assert "S1" in codes  # nothing declared yet
    room = bp.elements(__import__("zmforge.blueprint.elements", fromlist=["Room"]).Room)[0]
    declare_scene(bp, room, "The kitchen fire spread from the stove.", beats=("fire",))
    assert scenes_of(bp)[0].beats == ("fire",)
    msgs = [f.message for f in check_scenes(bp).findings if f.code == "S1"]
    assert any("promises ['fire']" in m for m in msgs)
    x = (room.interior.mins.x + room.interior.maxs.x) / 2
    y = (room.interior.mins.y + room.interior.maxs.y) / 2
    burning(bp, Point(x, y, room.floor_z))
    assert not [f for f in check_scenes(bp).findings if f.code == "S1"]
    with pytest.raises(ValueError):
        declare_scene(bp, room, "x", beats=("lasers",))
