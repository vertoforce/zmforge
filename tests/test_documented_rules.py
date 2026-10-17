"""The five checks whose rule came out of the shipped documentation.

Each test builds the smallest map that breaks one documented number and
asserts the check says so, then builds the version that respects it and
asserts silence.  The numbers themselves are asserted against the source they
were read from, because a check whose threshold drifts off the documentation
is worse than no check at all.

Sources, both shipped with the mod tools:
``bin\\default_navmesh_settings.json`` and
``docs_modtools\\Culling_LOD_Lights.pdf``.  A local copy of the official PDFs,
if present, is read too; the tests skip without one.

These tests are the checks in isolation.  That they also run as part of
checking a map -- ``N1`` to ``N4`` through :func:`zmforge.verify.blueprint`
and ``L2`` through :func:`zmforge.verify.files` -- is asserted in
``tests/test_requirements.py`` alongside every other row of the table.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from zmforge.blueprint.elements import Room
from zmforge.blueprint.model import Blueprint
from zmforge.mapsource.reader import parse_map_text
from zmforge.materials import Material
from zmforge.recipes import three_room_map
from zmforge.solids.layout import Aperture
from zmforge.spatial import Facing, Point, Side, Span
from zmforge.surfaces.field import HeightField
from zmforge.verify.documented import (
    CHARACTER_HEIGHT,
    MAX_CLEARANCE_RUN,
    MAX_PINCH_DEPTH,
    MAX_STEP_HEIGHT,
    MAX_WALKABLE_SLOPE,
    MIN_CHARACTER_WIDTH,
    MIN_HALLWAY_CLEARANCE,
    MIN_PINCH_POINT,
    check_light_lod,
    check_nav_apertures,
    check_navmesh_geometry,
    check_pathing_width,
    check_step_height,
    check_walkable_slope,
)

ART = Material("t7_concrete_trowelled")
MIRROR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "official-docs"
    / "modtools-install"
    / "default-navmesh-settings.md"
)

SCALE_MIRROR = MIRROR.with_name("scale-standards.md")


def _repair(text: str) -> dict:
    """Parse the settings file.

    The file as Treyarch ships it has trailing commas, so it is not strict
    JSON and has to be repaired before parsing.  That repair is the only
    change made to it.
    """
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))["navmesh"]


def _navmesh_settings() -> dict | None:
    """The shipped navmesh settings, or ``None`` when neither copy is present.

    Two sources, in order, and ``None`` rather than a failure when there is
    no source at all.  WHY: the numbers belong to Activision.  The
    authoritative copy is your own mod-tools install, or a local copy of the
    official PDFs, if present; a fresh clone has neither and this assertion has nothing to check.  Failing there would
    report a missing licensed file as a broken rule.
    """
    tools = os.environ.get("ZMFORGE_WINE_TOOLS")
    if tools:
        shipped = Path(tools) / "bin" / "default_navmesh_settings.json"
        if shipped.is_file():
            return _repair(shipped.read_text())
    if MIRROR.is_file():
        fenced = MIRROR.read_text().split("```json", 1)[1].split("```", 1)[0]
        return _repair(fenced)
    return None


def _codes(report) -> list[str]:
    return [finding.code for finding in report.findings]


# -- the thresholds are the documented ones -------------------------------
def test_thresholds_match_the_shipped_settings_file():
    settings = _navmesh_settings()
    if settings is None:
        pytest.skip(
            "no mod-tools install (set ZMFORGE_WINE_TOOLS) and no local copy of the official docs: "
            "the shipped settings file is Activision's and is not in this repository"
        )
    assert MAX_STEP_HEIGHT == settings["maxStepHeight"]
    assert MIN_CHARACTER_WIDTH == settings["minCharacterWidth"]
    assert CHARACTER_HEIGHT == settings["characterHeight"]
    assert MAX_WALKABLE_SLOPE == settings["maxWalkableSlope"]


# -- N1, step height -------------------------------------------------------
@pytest.mark.parametrize(
    "rise, expected",
    [(16.0, []), (18.0, []), (24.0, ["N1"])],
)
def test_step_rise_against_maxstepheight(rise, expected):
    blueprint = Blueprint("zm_test")
    blueprint.add_steps(
        Point(0, 0, 0), 6, 16.0, rise, 128.0, Facing.NORTH, ART, id="stairs"
    )
    assert _codes(check_step_height(blueprint)) == expected


# -- N2 and N3, doorway width and headroom ---------------------------------
def _room_with_doorway(width: float, height: float) -> Blueprint:
    blueprint = Blueprint("zm_test")
    blueprint.add_room(
        Span.between((-256, -256, 0), (256, 256, 240)),
        openings=[Aperture(Side.SOUTH, width, height)],
        id="room",
    )
    return blueprint


def test_doorway_narrower_than_the_navmesh_corridor_is_an_error():
    assert _codes(check_nav_apertures(_room_with_doorway(30.0, 96.0))) == ["N2"]


def test_doorway_at_the_navmesh_corridor_width_passes():
    assert check_nav_apertures(_room_with_doorway(31.0, 96.0)).findings == []


def test_doorway_shorter_than_the_walker_is_an_error():
    assert _codes(check_nav_apertures(_room_with_doorway(96.0, 64.0))) == ["N3"]


def test_full_height_doorway_passes():
    assert check_nav_apertures(_room_with_doorway(96.0, 96.0)).findings == []


def test_a_barricade_window_is_exempt():
    """The shipped recipes cut 96 x 48 at sill 0 for a barricade, on purpose.

    Zombies cross it by playing the prefab's traversal animation, not by
    walking, so the navmesh headroom rule does not apply and Z8 owns the
    opening instead.
    """
    blueprint = three_room_map("zm_test")
    assert check_nav_apertures(blueprint).findings == []


# -- N4, walkable slope ----------------------------------------------------
def _terrain(step: float, cell: float = 64.0) -> Blueprint:
    """A staircase heightfield: each column climbs by ``step``."""
    rows = [[col * step for col in range(6)] for _ in range(6)]
    blueprint = Blueprint("zm_test")
    blueprint.add_terrain(
        HeightField.from_rows(rows), Point(0, 0, 0), cell, lift=0.0, id="ground"
    )
    return blueprint


def test_gentle_terrain_passes():
    # 32 over 64 is 26.6 degrees.
    assert check_walkable_slope(_terrain(32.0)).findings == []


def test_terrain_over_the_walkable_slope_is_an_error():
    # 128 over 64 is 63.4 degrees.
    report = check_walkable_slope(_terrain(128.0))
    assert _codes(report) == ["N4"]
    assert "63.4 degrees" in report.findings[0].message


# -- the three together ----------------------------------------------------
def test_navmesh_geometry_runs_all_three():
    blueprint = _room_with_doorway(20.0, 40.0)
    blueprint.add_steps(
        Point(0, 0, 0), 4, 16.0, 32.0, 128.0, Facing.NORTH, ART, id="stairs"
    )
    assert set(_codes(check_navmesh_geometry(blueprint))) == {"N1", "N2", "N3"}


# -- N5, pathing width -----------------------------------------------------
def test_the_hallway_numbers_are_the_ones_scale_standards_prints():
    """N5's thresholds are quotes, so assert them against the quoted text.

    Same shape as the settings-file assertion above, and the same reason for
    skipping: the PDF is Activision's, a local copy of the official docs is
    present only if you made one, and a fresh clone has nothing to check against.
    """
    if not SCALE_MIRROR.is_file():
        pytest.skip(
            "no local copy of Scale_Standards.pdf: it is Activision's and is "
            "not in this repository"
        )
    text = SCALE_MIRROR.read_text()
    assert f'Minimum Clearance - {MIN_HALLWAY_CLEARANCE:g}"' in text
    assert f'Minimum Pinch Point - {MIN_PINCH_POINT:g}"' in text
    assert (
        f"Minimum clearance should not be used for distances longer than "
        f'{MAX_CLEARANCE_RUN:g}"' in text
    )
    assert f'should not exceed {MAX_PINCH_DEPTH:g}" in depth' in text


def _pinched_hall(gap: float, run: float) -> Blueprint:
    """One room with a block in it that leaves a ``gap``-wide slot ``run`` long.

    The slot is open at its north end, so the flood walks into it: it is a
    route round the block and not a sealed pocket.
    """
    blueprint = Blueprint("zm_test")
    room = blueprint.add_room(Span.between((-320, -320, 0), (320, 320, 240)), id="hall")
    inside = room.interior
    blueprint.add_block(
        Span.between(
            (inside.mins.x, inside.mins.y, room.floor_z),
            (inside.maxs.x - gap, inside.mins.y + run, room.floor_z + 128),
        ),
        ART,
        id="pinch",
    )
    blueprint.set_player_start(Point(inside.centre.x, inside.maxs.y - 64, room.floor_z))
    return blueprint


def test_a_long_slot_narrower_than_the_pinch_point_warns():
    report = check_pathing_width(_pinched_hall(48.0, 320.0))
    assert _codes(report) == ["N5"]
    finding = report.findings[0]
    assert not finding.is_error  # a design standard, not an engine threshold
    assert "48 units" in finding.message
    assert "64-unit minimum pinch point" in finding.message


def test_the_same_slot_at_minimum_clearance_passes():
    assert check_pathing_width(_pinched_hall(96.0, 320.0)).findings == []


def test_a_short_pinch_passes():
    """64 units of depth is what the document allows a pinch point."""
    assert check_pathing_width(_pinched_hall(48.0, 64.0)).findings == []


def test_a_slot_no_walker_fits_in_is_not_a_route():
    """Under N2's measured 31 the navmesh is not laid, so nothing is slowed.

    The gap behind a bench is free floor and this arithmetic measures it
    honestly; reporting it would be noise.
    """
    assert MIN_CHARACTER_WIDTH == 31.0
    assert check_pathing_width(_pinched_hall(24.0, 320.0)).findings == []


def test_a_run_under_clearance_but_over_the_pinch_point_is_judged_by_distance():
    assert check_pathing_width(_pinched_hall(80.0, 96.0)).findings == []
    report = check_pathing_width(_pinched_hall(80.0, 320.0))
    assert _codes(report) == ["N5"]
    assert "96-unit minimum clearance" in report.findings[0].message


def test_a_doorway_is_not_a_hallway():
    """A hole in a wall is short in the direction of travel, so it passes.

    W2 and N2 own how wide a doorway has to be.  This check must not restate
    them, or every stock-width door in the package would carry a warning.
    """
    blueprint = three_room_map("zm_test")
    assert check_pathing_width(blueprint).findings == []


def test_furniture_is_not_a_route():
    """A table top is meant to be narrow; a flight of steps is not."""
    blueprint = _pinched_hall(96.0, 320.0)
    room = next(iter(blueprint.elements(Room)))
    inside = room.interior
    blueprint.add_slab(
        Span.between(
            (inside.mins.x, inside.maxs.y - 96, 0),
            (inside.mins.x + 60, inside.maxs.y, 1),
        ),
        room.floor_z + 32.0,
        16.0,
        ART,
        id="table",
    )
    assert check_pathing_width(blueprint).findings == []


# -- L2, light LOD keys ----------------------------------------------------
LAMP = """iwmap 4
"000000000000000000000000"
// entity 0
{
"000000000000000000000001"
"classname" "worldspawn"
}
// entity 1
{
"000000000000000000000002"
"classname" "light"
"origin" "0 0 64"
%s}
"""


def test_a_lamp_with_neither_lod_key_passes():
    """Both keys default to 0 (never culled) in lightdescription.awi."""
    assert check_light_lod(parse_map_text(LAMP % '"radius" "110"\n')).findings == []


def test_a_small_lamp_with_the_generic_pair_is_flagged():
    extra = '"radius" "110"\n"culling_cutoff" "200"\n"culling_falloff" "300"\n'
    assert _codes(check_light_lod(parse_map_text(LAMP % extra))) == ["L2"]


@pytest.mark.parametrize(
    "extra",
    ['"radius" "110"\n"culling_cutoff" "5"\n"culling_falloff" "25"\n',
     '"radius" "512"\n"culling_cutoff" "200"\n"culling_falloff" "300"\n'],
)
def test_stock_pairs_pass(extra):
    assert check_light_lod(parse_map_text(LAMP % extra)).findings == []


def test_emitted_lamps_carry_no_lod_pair():
    """The regression this guards: a 200 / 300 LOD pair on every lamp."""
    from zmforge.emit.mapfile import LIGHT_KEYS
    assert not {key for key, _ in LIGHT_KEYS} & {"culling_cutoff", "culling_falloff"}
