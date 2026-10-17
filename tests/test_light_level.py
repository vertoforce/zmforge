"""D8 and the fill rule behind it: a room's floor lit by its own lamps.

A room can pass every lamp-distance check and still be far too dark: when
its first lamp is a small coloured glow (radius 72) and light_rooms copies
it into every fill lamp, the day through the windows is the room's only
real light.
"""

from __future__ import annotations

import math

from zmforge import lighting
from zmforge.blueprint.elements import Lamp
from zmforge.blueprint.model import Blueprint
from zmforge.solids.layout import Aperture
from zmforge.spatial import Bounds, Point, Side
from zmforge.verify.lightlevel import (DARK_MEAN, DIM, check_light_level, image_levels,
                                       room_light)

RED = (1.0, 0.12, 0.08)


def _room(bp, box=((0, 0, 0), (768, 512, 192)), **kw):
    return bp.add_room(Bounds.between(*box), id=kw.pop("id", "gallery"), **kw)


def _codes(report):
    return [f.code for f in report.findings]


def test_a_glow_is_not_the_style_the_fill_copies():
    bp = Blueprint("zm_glow_style_pin")
    room = _room(bp)
    bp.place_light(Point(300.0, 490.0, 144.0), colour=RED, radius=72.0, id="sensor_glow")
    bp.light_rooms()
    fill = [lamp for lamp in bp.elements(Lamp) if "_fill_" in lamp.id]
    assert fill, "a room lit only by a glow still needs fill"
    assert all(lamp.colour != RED and lamp.radius >= lighting.GLOW_RADIUS for lamp in fill)
    lit = room_light(bp)[room.id]
    assert lit.mean >= DARK_MEAN and lit.dark < 0.1
    assert "D8" not in _codes(check_light_level(bp))


def test_a_glow_does_not_fill_a_grid_cell():
    bp = Blueprint("zm_glow_cell_pin")
    _room(bp, box=((0, 0, 0), (256, 256, 192)))
    bp.place_light(Point(128.0, 128.0, 136.0), colour=RED, radius=72.0, id="pip")
    assert len(bp.light_rooms()) == 1


def test_fill_reaches_the_floor_it_hangs_over():
    # 248 over the floor: radius 300 would put the floor in the cut-off ramp.
    need = lighting.fill_radius(248.0)
    assert math.hypot(248.0, lighting.MAX_LAMP_SPACING / math.sqrt(2.0)) <= lighting.useful_reach(need) + 1e-6
    bp = Blueprint("zm_fill_reach_pin")
    room = _room(bp, box=((0, 0, 0), (768, 768, 320)))
    bp.place_light(Point(384.0, 384.0, 240.0), colour=(1.0, 0.86, 0.62), radius=300.0, id="stage")
    for lamp in bp.light_rooms():
        assert lamp.radius >= lighting.fill_radius(lamp.position.z - room.floor_z) - 1e-6
        assert lamp.colour == (1.0, 0.86, 0.62), "the room's own hue is kept"


def test_a_room_with_only_a_glow_and_no_fill_is_dark():
    bp = Blueprint("zm_unlit_pin")
    room = _room(bp)
    bp.place_light(Point(300.0, 490.0, 144.0), colour=RED, radius=72.0, id="sensor_glow")
    lit = room_light(bp)[room.id]
    assert lit.dark > 0.9 and lit.mean < DIM
    assert "D8" in _codes(check_light_level(bp))


def test_joined_rooms_far_apart_in_light_warn():
    bp = Blueprint("zm_jump_pin")
    door = (Aperture(Side.EAST, 80.0, 96.0),)
    _room(bp, box=((0, 0, 0), (512, 512, 192)), id="bright", openings=door)
    _room(bp, box=((512, 0, 0), (1024, 512, 192)), id="dim",
          openings=(Aperture(Side.WEST, 80.0, 96.0),))
    for x in (128.0, 384.0):
        for y in (128.0, 384.0):
            bp.place_light(Point(x, y, 136.0), radius=512.0, stops=bp.exposure + 3.0)
            bp.place_light(Point(512.0 + x, y, 136.0), radius=512.0, stops=bp.exposure - 1.5)
    messages = [f.message for f in check_light_level(bp).findings if f.code == "D8"]
    assert any("stops apart" in m for m in messages), messages


def test_image_levels_reads_rooms_darker_than_the_map(tmp_path):
    from PIL import Image

    shots = {}
    for room, grey in (("entry", 150), ("hall", 140), ("ward", 160), ("gallery", 30)):
        path = tmp_path / f"{room}.png"
        Image.new("RGB", (64, 36), (grey, grey, grey)).save(path)
        shots[room] = [str(path)]
    levels = image_levels(shots)
    assert levels["gallery"]["flag"] and not levels["entry"]["flag"]
    assert levels["gallery"]["stops_under_median"] > 2.0


def test_image_levels_reads_blown_out_rooms(tmp_path):
    from PIL import Image

    shots = {}
    for room, grey in (("entry", 90), ("hall", 80), ("ward", 100), ("closet", 250)):
        path = tmp_path / f"{room}.png"
        Image.new("RGB", (64, 36), (grey, grey, grey)).save(path)
        shots[room] = [str(path)]
    levels = image_levels(shots)
    assert levels["closet"]["bright"] and not levels["closet"]["dark"]
    assert not any(levels[r]["flag"] for r in ("entry", "hall", "ward"))


def test_a_high_single_tier_fill_is_brightened_to_a_storeys_floor_light():
    assert lighting.fill_boost(120.0) == 0.0
    assert abs(lighting.fill_boost(256.0) - 2.0) < 1e-9
    assert lighting.fill_boost(2000.0) == lighting.FILL_BOOST_MAX
    low, high = Blueprint("zm_boost_low"), Blueprint("zm_boost_high")
    a = _room(low, box=((0, 0, 0), (768, 768, 192)))
    b = _room(high, box=((0, 0, 0), (768, 768, 304)))
    for bp_, z in ((low, 136.0), (high, 248.0)):  # a stage-light style, radius 300
        bp_.place_light(Point(384.0, 384.0, z), colour=(1.0, 0.86, 0.62), radius=300.0, id="stage")
    low.light_rooms()
    high.light_rooms()
    la, lb = room_light(low)[a.id], room_light(high)[b.id]
    assert abs(math.log2(la.median / lb.median)) < 1.0, (la, lb)


def test_a_style_that_lights_its_floor_is_kept():
    # a dim moonlit room that passes D8 keeps its style: the top-up is only
    # for rooms D8 would call dark (the cemetery recipe's rooms are untouched)
    bp = Blueprint("zm_mood_kept_pin")
    _room(bp, box=((0, 0, 0), (768, 768, 192)))
    bp.place_light(Point(384.0, 384.0, 136.0), colour=(0.4, 0.5, 0.9), radius=300.0, id="moon")
    for lamp in bp.light_rooms():
        assert lamp.radius == 300.0 and lamp.stops is None
