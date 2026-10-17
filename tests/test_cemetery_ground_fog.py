"""zm_cemetery's ground and fog.

Grey, untextured ground and no fog read as unfinished.  What is pinned here:
the terrain meshes carry texel texture coordinates at the stock density
(the grey was a thousand-times-too-small UV), each outdoor area has its own
ground (lawn, grassy dirt, rocky-dirt walks, cobbled forecourts, mud at the
open grave, flagstones in the crypt), the walks lie just over the ground
they follow, and the map carries the lit fog The Giant shows (a map-wide
``volume_litfog`` plus a thicker pocket per crypt room).  Nothing here is an
observation of play.
"""

from __future__ import annotations

import re

import pytest

from zmforge import Project
from zmforge.atmosphere import (
    CRYPT_LIT_FOG, NIGHT_GROUND_FOG, NIGHT_LIT_GROUND_FOG, STOCK_LIT_FOGS, Atmosphere,
    lit_fog_volume_pairs,
)
from zmforge.blueprint.elements import Enclosure, Massing, Terrain
from zmforge.materials import is_catalogued
from zmforge.recipes import cemetery_kit as kit
from zmforge.recipes.cemetery import (
    CRYPT_ROOMS, FORECOURTS, PATHS, SKINS, WALK_LIFT, build_cemetery, path_boxes,
)

from conftest import seed_stock_weapon_table


@pytest.fixture(scope="module")
def built():
    return build_cemetery("zm_cemetery")


@pytest.fixture(scope="module")
def bp(built):
    return built[0]


@pytest.fixture(scope="module")
def map_text(tmp_path_factory, bp):
    root = tmp_path_factory.mktemp("cemetery_ground_fog")
    seed_stock_weapon_table(root)
    project = Project.create("zm_cemetery", root, blueprint=bp)
    project.commit()
    return project.paths()["map"].read_text(encoding="utf-8")


def _entities(text: str, classname: str) -> list[str]:
    blocks = re.split(r"\n// entity \d+\n", text)
    return [b for b in blocks if f'"classname" "{classname}"' in b]


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------
def test_every_ground_material_is_catalogued() -> None:
    for material in (kit.GRASS, kit.GROUND, kit.PATH, kit.COBBLE, kit.MUD, kit.FLAGSTONE):
        assert is_catalogued(material), material.name


def test_each_outdoor_area_has_its_own_ground(bp) -> None:
    terrains = {t.id: t for t in bp.elements(Terrain)}
    assert terrains["hills_ground"].material == kit.GRASS
    assert terrains["row_ground"].material == kit.GRASS
    assert terrains["gate_ground"].material == kit.GROUND
    courts = {key for key, *_ in FORECOURTS}
    for key in path_boxes():
        want = kit.COBBLE if key in courts else kit.PATH
        assert terrains[f"{key}_path"].material == want, key


def test_the_crypt_floors_are_flagstones_and_the_open_grave_is_mud(bp) -> None:
    for key in CRYPT_ROOMS:
        assert SKINS[key].floor == kit.FLAGSTONE, key
    rim = [m for m in bp.elements(Massing) if m.id.startswith("open_grave_rim")
           or m.id == "open_grave_spoil"]
    assert len(rim) == 5
    for massing in rim:
        names = {str(face.material) for solid in massing.solids for face in solid.faces}
        assert names == {kit.MUD.name}, (massing.id, names)


def test_terrain_uvs_are_texels_at_the_stock_density(map_text) -> None:
    """Stock terrain meshes carry t = 8 or 16 x world X (texels per unit);
    the grey ground was X / 128.  Every generated mesh must sit in 4..32."""
    ratios = []
    for match in re.finditer(r"\n\tv (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) t (-?[\d.]+) (-?[\d.]+)",
                             map_text):
        x, u = float(match.group(1)), float(match.group(4))
        if abs(x) > 200.0:
            ratios.append(u / x)
    assert len(ratios) > 1000
    assert all(4.0 <= r <= 32.0 for r in ratios), (min(ratios), max(ratios))


def test_the_hills_lawn_repeats_every_96_units(bp) -> None:
    hills = bp.find("hills_ground")
    assert hills.texture_scale == pytest.approx(96.0 / 1024.0)
    assert kit.terrain_texture_scale(kit.GROUND) == pytest.approx(1.0 / 8.0)


def test_the_walks_lie_just_over_the_ground_they_follow(bp) -> None:
    """Sampled 61 x 13 over every walk: never under the grass, and never
    more than a step above it (measured: 1.7 .. 7.4)."""
    terrains = {t.id: t for t in bp.elements(Terrain)}
    for key, (room, x0, y0, x1, y1) in path_boxes().items():
        strip = terrains[f"{key}_path"].record
        ground = terrains[f"{room}_ground"].record
        gaps = []
        for i in range(61):
            for j in range(13):
                x, y = x0 + (x1 - x0) * i / 60, y0 + (y1 - y0) * j / 12
                a, b = strip.sample(x, y), ground.sample(x, y)
                if a.found and b.found:
                    gaps.append(a.z - b.z)
        assert len(gaps) > 300, key
        assert min(gaps) >= 0.5, (key, min(gaps))
        assert max(gaps) <= 18.0, (key, max(gaps))
    assert WALK_LIFT == 3.0


def test_every_walk_is_axis_aligned_inside_its_room(built) -> None:
    rooms = built[1]["rooms"]
    for key, room_key, (ax, ay), (bx, by), hw in PATHS:
        assert ax == bx or ay == by, key
        assert hw >= 64.0, key
        inside = rooms[room_key].interior
        _, x0, y0, x1, y1 = path_boxes()[key]
        assert inside.mins.x - 1 <= x0 < x1 <= inside.maxs.x + 1, key
        assert inside.mins.y - 1 <= y0 < y1 <= inside.maxs.y + 1, key


# --------------------------------------------------------------------------
# Fog
# --------------------------------------------------------------------------
def test_the_lit_fog_assets_are_the_giants() -> None:
    assert NIGHT_LIT_GROUND_FOG.lit_fog == "zm_factory_volumetric"
    assert CRYPT_LIT_FOG == "zm_factory_dogs_volumetric"
    assert STOCK_LIT_FOGS["zm_factory_volumetric"].line == 1083
    assert STOCK_LIT_FOGS["zm_factory_dogs_volumetric"].line == 1036
    # the crypt's is the thicker one
    assert STOCK_LIT_FOGS[CRYPT_LIT_FOG].halfdist < STOCK_LIT_FOGS["zm_factory_volumetric"].halfdist
    # the corn maze's air (NIGHT_GROUND_FOG) is unchanged: no lit fog
    assert NIGHT_GROUND_FOG.lit_fog is None
    with pytest.raises(ValueError):
        Atmosphere(lit_fog="zm_nowhere_volumetric")


def test_the_lit_fog_volume_carries_the_giants_keys() -> None:
    pairs = dict(lit_fog_volume_pairs("zm_factory_volumetric", 2.5))
    assert pairs["fsi"] == pairs["fsi_1"] == pairs["fsi_4"] == "zm_factory_volumetric"
    assert pairs["fogtime"] == "2.5"
    assert pairs["spawnflags"] == "14435"
    assert pairs["ENABLE_LIGHTS"] == pairs["ENABLE_SUN"] == "1"
    assert "priority" not in pairs
    assert dict(lit_fog_volume_pairs(CRYPT_LIT_FOG, priority=2))["priority"] == "2"


def test_the_map_carries_the_lit_fog_and_the_crypt_pockets(bp, built, map_text) -> None:
    enclosure = bp.elements(Enclosure)[0]
    assert enclosure.lit_fog == "zm_factory_volumetric"
    rooms = built[1]["rooms"]
    assert [box for box, _ in enclosure.lit_fog_pockets] == [
        rooms[key].interior for key in CRYPT_ROOMS]
    volumes = _entities(map_text, "volume_litfog")
    assert len(volumes) == 1 + len(CRYPT_ROOMS)
    wide = [v for v in volumes if '"fsi" "zm_factory_volumetric"' in v]
    pockets = [v for v in volumes if f'"fsi" "{CRYPT_LIT_FOG}"' in v]
    assert len(wide) == 1 and len(pockets) == 3
    assert all('"priority" "2"' in v for v in pockets)
    assert all(" litfog_volume " in v for v in volumes)
    # the old world-fog volume is still there, once
    assert len(_entities(map_text, "volume_worldfog")) == 1


def test_the_path_lanterns_and_wisps_glow_in_the_fog(bp, map_text) -> None:
    from zmforge.blueprint.elements import Lamp

    lamps = bp.elements(Lamp)
    glowing = [lamp for lamp in lamps if lamp.volumetric]
    assert glowing and all("lantern" in l.id or "wisp" in l.id or l.id.startswith("path_lamp")
                           for l in glowing)
    assert sum(l.id.startswith("path_lamp") for l in glowing) >= 30
    assert any("wisp" in l.id for l in glowing)
    lights = _entities(map_text, "light")
    assert sum('"volumetric" "1"' in e for e in lights) == len(glowing)
