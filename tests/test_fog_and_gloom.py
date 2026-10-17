"""Fog and gloom per recipe (zmforge.atmosphere).

Pinned here: the grade and exposure keys land on the worldspawn the way
``zm_giant.map``'s worldspawn names them, a map that asks for nothing gets
none of them, unknown grades and unmeasured presets are refused, and each
recipe carries its themed air.  Nothing here is an observation of play.
"""

from __future__ import annotations

import inspect

import pytest

from zmforge.atmosphere import (
    CLINIC_COLD, DAY_CLEAR, HARVEST_HAZE, NIGHT_GLOOM, OFFICE_DAY, STOCK_GRADES,
    STOCK_LIT_FOGS, Atmosphere, worldspawn_pairs,
)
from zmforge.blueprint.elements import Enclosure
from zmforge.blueprint.model import Blueprint
from zmforge.spatial import Bounds

GLOOM_KEYS = ("vcolor", "bloom", "evauto", "evmin", "evmax", "evcmp")


def _one_room_doc(atmosphere=None):
    from zmforge.emit.mapfile import build_document

    bp = Blueprint("zm_glumtest")
    room = bp.add_room(Bounds.between((0, 0, 0), (512, 512, 256)))
    bp.add_zone("a", room, starting=True)
    bp.enclose(atmosphere=atmosphere) if atmosphere else bp.enclose()
    return build_document(bp)


def test_no_atmosphere_writes_no_gloom_keys() -> None:
    world = dict(_one_room_doc().entities[0].pairs)
    assert not set(GLOOM_KEYS) & set(world)
    assert worldspawn_pairs("default_day", None, None) == []


def test_night_gloom_writes_grade_and_pinned_exposure_on_the_worldspawn() -> None:
    doc = _one_room_doc(NIGHT_GLOOM)
    world = dict(doc.entities[0].pairs)
    assert world["vcolor"] == world["bloom"] == "zm_factory"
    # zm_factory's ev is 5; pinned half a stop over it, min = max.
    assert world["evauto"] == "1"
    assert world["evmin"] == world["evmax"] == "5.5"
    assert world["evcmp"] == "0"
    assert world["skyboxmodel"] == "skybox_zm_factory"
    names = [e.classname for e in doc.entities]
    assert names.count("volume_litfog") == 1 and names.count("volume_worldfog") == 1


def test_clinic_names_a_cold_absorbing_lit_fog_and_no_grade() -> None:
    doc = _one_room_doc(CLINIC_COLD)
    world = dict(doc.entities[0].pairs)
    assert "vcolor" not in world and world["evmin"] == "15.5"  # default_day ev 15
    litfog = [e for e in doc.entities if e.classname == "volume_litfog"]
    assert len(litfog) == 1 and dict(litfog[0].pairs)["fsi"] == "mp_apartments_volumetric"
    facts = STOCK_LIT_FOGS["mp_apartments_volumetric"]
    assert facts.albedo < 1.0 and facts.extinction[2] > facts.extinction[0]
    assert "volume_worldfog" not in [e.classname for e in doc.entities]


def test_unknown_grade_and_unmeasured_preset_are_refused() -> None:
    with pytest.raises(ValueError):
        Atmosphere(grade="zm_nowhere")
    with pytest.raises(ValueError):
        Atmosphere(exposure_stops=9.0)
    with pytest.raises(ValueError):
        worldspawn_pairs("zm_unmeasured_preset", None, 0.5)
    assert set(STOCK_GRADES) == {"zm_factory"}


def test_each_recipe_carries_its_themed_air() -> None:
    from zmforge.recipes import cemetery, corn_maze

    for fn in (cemetery.cemetery_map, cemetery.build_cemetery):
        assert inspect.signature(fn).parameters["atmosphere"].default is NIGHT_GLOOM
    assert corn_maze.NIGHT_SKY is HARVEST_HAZE
    # The corn maze keeps its brightness (it is dark already).
    assert HARVEST_HAZE.grade is None and HARVEST_HAZE.exposure_stops is None
    assert HARVEST_HAZE.lit_fog == "zm_factory_volumetric"
    assert OFFICE_DAY == DAY_CLEAR and OFFICE_DAY.lit_fog is None


def test_fog_preview_keeps_only_the_fog_volume_filters_shown() -> None:
    from zmforge.render.radiant import FOG_PREVIEW_SHOWN, hide_helpers

    reg = ('[Software\\\\Treyarch\\\\Radiant\\\\Filters\\\\Groups\\\\Volumes] 1\n'
           '"Litfog"="false"\n"SunVolumes"="true"\n"WorldFogVolumes"="true"\n')
    plain = hide_helpers(reg)
    assert '"Litfog"="false"' in plain and '"WorldFogVolumes"="false"' in plain
    fog = hide_helpers(reg, shown=FOG_PREVIEW_SHOWN)
    assert '"Litfog"="true"' in fog and '"WorldFogVolumes"="true"' in fog
    assert '"SunVolumes"="false"' in fog
