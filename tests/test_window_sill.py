"""Z85 and the barricade window's sill wall and closet (a zombie window
shows solid wall to waist height).

The hole stays cut from the floor for the prefab's traversal channel; a drawn,
non-colliding wall fills it to the 32-unit sill, and the closet behind is dark,
dim-lit and has some clutter in it."""

from __future__ import annotations

from dataclasses import replace

import pytest

from zmforge.blueprint.elements import Lamp, Window, Yard
from zmforge.blueprint.windows import SILL_WALL_HEIGHT, sill_wall_box
from zmforge.emit.mapfile import build_document
from zmforge.materials import Material
from zmforge.recipes.layouts import three_room_map
from zmforge.verify.windows import check_windows


@pytest.fixture(scope="module")
def bp():
    return three_room_map("zm_sill_test")


def _errors(report):
    return [f for f in report if f.severity == "error"]


def test_every_window_gets_a_sill_to_the_stock_height(bp) -> None:
    windows = list(bp.elements(Window))
    assert windows
    for window in windows:
        room = bp.find(window.room_id)
        box = sill_wall_box(bp, window)
        assert box is not None
        assert box.mins.z == pytest.approx(room.floor_z)
        assert box.maxs.z == pytest.approx(room.floor_z + SILL_WALL_HEIGHT)
        # The hole itself is untouched: still cut from the floor.
        assert room.apertures[window.aperture_index].sill == 0.0


def test_the_sill_is_written_drawn_and_non_colliding(bp) -> None:
    doc = build_document(bp)
    world = doc.entities[0]
    sills = [s for s in world.solids if "nonColliding" in getattr(s, "contents", ())
             and any(f.material != "caulk" for f in s.facets)]
    assert len(sills) >= len(list(bp.elements(Window)))


def test_the_generated_map_is_clean(bp) -> None:
    assert _errors(check_windows(bp)) == []


def test_a_missing_sill_is_an_error(bp, monkeypatch) -> None:
    import zmforge.blueprint.windows as windows

    monkeypatch.setattr(windows, "sill_wall_solid", lambda *_: None)
    found = _errors(check_windows(bp))
    assert found and all(f.code == "Z85" for f in found)
    assert "no wall under it" in found[0].message


def test_a_white_closet_is_an_error(bp) -> None:
    yard = next(iter(bp.elements(Yard)))
    before = yard.materials
    yard.materials = replace(before, wall=Material("t7_plaster_smooth_light_01"))
    try:
        assert any("white" in f.message for f in _errors(check_windows(bp)))
    finally:
        yard.materials = before


def test_a_full_strength_or_stacked_closet_lamp_is_an_error(bp) -> None:
    window = next(iter(bp.elements(Window)))
    lamp = bp.find(f"{window.id}_light")
    assert isinstance(lamp, Lamp)
    before = lamp.colour
    lamp.colour = (1.0, 1.0, 1.0)
    try:
        assert any("glares" in f.message for f in _errors(check_windows(bp)))
    finally:
        lamp.colour = before
