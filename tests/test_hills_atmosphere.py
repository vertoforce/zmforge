"""The generic pieces zm_cemetery added: walkable rolling ground
(:mod:`zmforge.surfaces.hills`) and night/fog (:mod:`zmforge.atmosphere`)."""

from __future__ import annotations

import pytest

from zmforge.atmosphere import (
    DAY_CLEAR, NIGHT_GROUND_FOG, STOCK_FOGS, Atmosphere, fog_volume_pairs,
)
from zmforge.blueprint.model import Blueprint
from zmforge.spatial import Bounds, Point
from zmforge.surfaces.field import HeightField
from zmforge.surfaces.hills import (
    DEFAULT_MAX_RISE, Disc, Mound, cap_pins, limit_rise, pin_discs, rolling_hills,
    scatter_mounds, slope_report,
)
from zmforge.verify.documented import MAX_STEP_HEIGHT

ANCHOR = Point(0.0, 0.0, 16.0)


def test_the_default_rise_is_the_navmesh_step() -> None:
    assert DEFAULT_MAX_RISE == MAX_STEP_HEIGHT == 18.0


def test_a_mound_is_smooth_and_ends_at_its_radius() -> None:
    m = Mound(0.0, 0.0, 100.0, 50.0)
    assert m.at(0.0, 0.0) == 50.0
    assert m.at(100.0, 0.0) == 0.0 and m.at(150.0, 0.0) == 0.0
    assert 0.0 < m.at(50.0, 0.0) < 50.0


def test_rolling_hills_never_dip_under_the_floor() -> None:
    field = rolling_hills(ANCHOR, 10, 10, 64.0, mounds=[Mound(300, 300, 200, -80)],
                          noise_peak=10.0, seed=3)
    assert field.lowest >= 0.0


def test_grading_caps_every_neighbour_rise_and_keeps_pins() -> None:
    field = rolling_hills(ANCHOR, 16, 16, 64.0, mounds=[Mound(512, 512, 700, 400)])
    assert slope_report(field, 64.0).max_neighbour_rise > 60.0
    pins = pin_discs(ANCHOR, field, 64.0, [Disc(0, 0, 70, 0.0, square=True)])
    graded = limit_rise(field, 18.0, pinned=pins)
    report = slope_report(graded, 64.0)
    assert report.max_neighbour_rise <= 18.0 + 1e-9
    assert report.max_cell_relief <= 18.0 + 1e-9
    assert all(graded.at(r, c) == 0.0 for (r, c) in pins)
    assert graded.highest > 100.0, "a hill graded to a walkable slope is still a hill"


def test_a_plateau_pin_gets_a_ramp_not_a_cliff() -> None:
    flat = HeightField.level(12, 12, 0.0)
    pins = pin_discs(ANCHOR, flat, 64.0, [Disc(384, 384, 64, 90.0, square=True)])
    graded = limit_rise(flat, 18.0, pinned=pins)
    assert graded.at(6, 6) == 90.0
    assert slope_report(graded, 64.0).max_neighbour_rise <= 18.0 + 1e-9
    assert graded.at(6, 2) > 0.0


def test_pins_too_close_for_the_grade_are_refused_or_capped() -> None:
    pins = {(0, 0): 0.0, (0, 2): 100.0}
    with pytest.raises(ValueError):
        limit_rise(HeightField.level(4, 4, 0.0), 18.0, pinned=pins)
    capped = cap_pins(pins, 18.0)
    assert capped == {(0, 0): 0.0, (0, 2): 36.0}
    limit_rise(HeightField.level(4, 4, 0.0), 18.0, pinned=capped)


def test_a_disc_narrower_than_a_cell_still_pins_one_point() -> None:
    field = HeightField.level(5, 5, 10.0)
    pins = pin_discs(ANCHOR, field, 100.0, [Disc(140, 260, 5, 0.0)])
    assert pins == {(3, 1): 0.0}


def test_scatter_mounds_is_seeded_and_avoids() -> None:
    avoid = [Disc(500, 500, 200)]
    a = scatter_mounds(0, 0, 1000, 1000, 6, radius=(100, 200), height=(20, 40), seed=9, avoid=avoid)
    b = scatter_mounds(0, 0, 1000, 1000, 6, radius=(100, 200), height=(20, 40), seed=9, avoid=avoid)
    assert a == b and len(a) == 6
    assert all(((m.x - 500) ** 2 + (m.y - 500) ** 2) ** 0.5 >= 200 for m in a)


# --------------------------------------------------------------------------
# Atmosphere
# --------------------------------------------------------------------------
def test_the_night_preset_names_what_the_giant_uses() -> None:
    assert NIGHT_GROUND_FOG.sun_preset == "zm_factory"
    assert NIGHT_GROUND_FOG.skybox == "skybox_zm_factory"
    assert NIGHT_GROUND_FOG.fog == "zm_factory_afog"
    assert STOCK_FOGS["zm_factory_afog"].halfheight == 264.0


def test_the_dusk_preset_is_one_the_local_tools_can_link() -> None:
    from zmforge.atmosphere import DUSK_GROUND_FOG
    from zmforge.lighting import SSI_EXPOSURE

    assert (DUSK_GROUND_FOG.sun_preset, DUSK_GROUND_FOG.skybox) == (
        "default_sunset", "skybox_default_sunset")
    assert SSI_EXPOSURE["default_sunset"] == 12.5


def test_an_unread_fog_asset_is_refused() -> None:
    with pytest.raises(ValueError):
        Atmosphere(fog="zm_nowhere_fog")


def test_the_fog_volume_carries_the_giants_keys() -> None:
    pairs = dict(fog_volume_pairs("zm_factory_afog", 2.5))
    assert pairs["fsi"] == pairs["fsi_1"] == pairs["fsi_4"] == "zm_factory_afog"
    assert pairs["fogtime"] == "2.5"
    assert pairs["spawnflags"] == "14851" and pairs["DISABLE_FOG"] == "0"


def _one_room(atmosphere=None):
    bp = Blueprint("zm_airtest")
    room = bp.add_room(Bounds.between((0, 0, 0), (512, 512, 256)))
    zone = bp.add_zone("a", room, starting=True)
    del zone
    bp.enclose(atmosphere=atmosphere) if atmosphere else bp.enclose()
    return bp


def test_a_map_that_names_no_atmosphere_gets_no_fog_volume() -> None:
    from zmforge.emit.mapfile import build_document

    doc = build_document(_one_room())
    names = [e.classname for e in doc.entities]
    assert "volume_worldfog" not in names
    world = dict(doc.entities[0].pairs)
    assert world["skyboxmodel"] == "skybox_default_day"
    assert DAY_CLEAR.fog is None


def test_a_foggy_night_writes_one_fog_volume_and_the_night_sky() -> None:
    from zmforge.emit.mapfile import build_document

    doc = build_document(_one_room(NIGHT_GROUND_FOG))
    fog = [e for e in doc.entities if e.classname == "volume_worldfog"]
    assert len(fog) == 1 and fog[0].solids
    assert dict(fog[0].pairs)["fsi"] == "zm_factory_afog"
    assert dict(doc.entities[0].pairs)["skyboxmodel"] == "skybox_zm_factory"
