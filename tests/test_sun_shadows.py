"""The settings that decide how a sun or lamp shadow reads, and the lamp grid.

These cover two things a generated map can show: shadow edges that
stair-step into a hard saw along stepped geometry, worst on the stair flights
and moving as the player moves; and a stairwell that is very dark.  An
oversized reflection probe forfeiting the engine's sun-shadow boost is not the
cause (see :func:`test_no_probe_is_over_the_play_space_limit`); the numbers
below are, each measured against Treyarch's own shipped content:

* ``volume_sun``'s ``shadowSplitDistance``.  ``bin/t7.def.json`` describes it
  as the distance, in inches, that the dynamic split shadows cover, range
  100 to 5000, default 2000.  Exactly three shipped ``volume_sun`` entities
  exist under the tools' ``map_source``: ``zm_giant_light.map`` uses 900 with
  ``shadowSplitCount`` 2, ``mp_sector_light.map`` and ``mp_combine_light.map``
  use 1200 with ``shadowSplitCount`` 3.  None of the stock files carries the
  2000 default.
* ``worldspawn``'s ``numOmniShadowSlices``, "Number of omni shadow slices",
  range 8 to 256, default 24.  ``zm_giant.map`` raises it to 96 while only 42
  of that map's 280 omni lights cast a shadow map at all.  With far more
  casters than slices (143 against 24, say), which lights keep a shadow is
  decided from where the camera is.
* The lamp grid's z axis.  Laid once, at the ceiling, it fails tall rooms.
  Across the rooms measured, every room whose floor reads correctly has its
  ceiling lamps 92 to 280 units above that floor; the rooms that read dark
  have them above that band (384, 840 and 856 were measured).
"""

from __future__ import annotations

import math

import pytest

from zmforge import lighting
from zmforge.blueprint.elements import Lamp
from zmforge.blueprint.model import Blueprint
from zmforge.emit.mapfile import LIGHT_KEYS, build_document
from zmforge.recipes import three_room_map
from zmforge.spatial import Bounds, Point


def _entity(document, classname):
    for entity in document.entities:
        if ("classname", classname) in entity.pairs:
            return dict(entity.pairs)
    raise AssertionError(f"no {classname} in the document")


def _entities(document, classname):
    return [
        dict(entity.pairs)
        for entity in document.entities
        if ("classname", classname) in entity.pairs
    ]


# --------------------------------------------------------------------------
# volume_sun: the sun cascade
# --------------------------------------------------------------------------
def test_sun_volume_ships_the_giants_split_pair_not_the_database_default():
    """The cascade covers The Giant's 900 inches over 2 splits, never 2000.

    A cascade has a fixed texture budget, so the distance it covers is what
    sets the texels per world unit, and a shadow edge crossing a stair reads as
    a saw when there are too few.  2000 is the database default and no shipped
    map uses it.
    """
    document = build_document(three_room_map("zm_split_pin"))
    sun = _entity(document, "volume_sun")
    assert sun["shadowSplitDistance"] == "900"
    assert sun["shadowSplitCount"] == "2"


def test_split_distance_stays_inside_the_range_the_database_declares():
    """``t7.def.json`` gives ``shadowSplitDistance`` a min of 100, max 5000."""
    assert 100.0 <= lighting.SUN_SHADOW_SPLIT_DISTANCE <= 5000.0


def test_slice_count_is_the_giants_and_grows_with_the_casters():
    assert lighting.OMNI_SHADOW_SLICES == 96
    assert lighting.omni_shadow_slices(0) == 96
    assert lighting.omni_shadow_slices(42) == 96  # The Giant's own caster count
    assert lighting.omni_shadow_slices(143) == 143
    # The database declares the key's range as 8 to 256.
    assert lighting.omni_shadow_slices(10_000) == 256
    assert lighting.omni_shadow_slices(-5) == 96


def test_a_caller_may_still_override_the_slice_count():
    document = build_document(
        three_room_map("zm_slice_override"),
        worldspawn_overrides=[("numOmniShadowSlices", "24")],
    )
    assert _entity(document, "worldspawn")["numOmniShadowSlices"] == "24"


# --------------------------------------------------------------------------
# The lamps themselves
# --------------------------------------------------------------------------
def test_noshadowmap_is_per_lamp_and_not_a_constant_key():
    """It used to be pinned to "0" for every lamp in ``LIGHT_KEYS``."""
    assert all(key != "PRIMARY_NOSHADOWMAP" for key, _ in LIGHT_KEYS)
    blueprint = Blueprint("zm_lamp_shadow_pin")
    blueprint.place_light(Point(0.0, 0.0, 64.0), id="caster")
    blueprint.place_light(Point(128.0, 0.0, 64.0), shadows=False, id="filler")
    lit = {
        lamp["origin"]: lamp["PRIMARY_NOSHADOWMAP"]
        for lamp in _entities(build_document(blueprint), "light")
    }
    assert lit["0 0 64"] == "0"
    assert lit["128 0 64"] == "1"


# --------------------------------------------------------------------------
# The lamp grid's third axis
# --------------------------------------------------------------------------
def test_a_short_room_keeps_its_single_ceiling_tier():
    """The fix must be a no-op for every room that already read correctly."""
    assert Blueprint._lamp_tiers(216.0, 16.0, 256.0) == [216.0]
    # Exactly one spacing of drop is still one tier.
    assert Blueprint._lamp_tiers(272.0, 16.0, 256.0) == [272.0]


def test_a_tall_room_gets_evenly_spread_tiers_none_further_than_the_spacing():
    """A tall open room: floor 16, ceiling lamps at 872, spacing 256."""
    tiers = Blueprint._lamp_tiers(872.0, 16.0, 256.0)
    assert tiers[0] == 872.0
    assert len(tiers) == 4
    gaps = [a - b for a, b in zip(tiers, tiers[1:])]
    assert all(gap <= 256.0 for gap in gaps)
    assert len(set(round(gap, 6) for gap in gaps)) == 1, "tiers are evenly spread"
    assert tiers[-1] - 16.0 <= 256.0, "the lowest tier is within a spacing of the floor"
    assert tiers[-1] > 16.0, "no tier is at or below the floor"


def test_lamp_tiers_degrade_safely_on_a_nonsense_spacing():
    assert Blueprint._lamp_tiers(872.0, 16.0, 0.0) == [872.0]


def test_light_rooms_reaches_the_floor_of_a_room_taller_than_its_own_grid():
    """A single 896-tall room, lit from nothing."""
    blueprint = Blueprint("zm_tall_room_pin")
    blueprint.add_room(Bounds.between((0, 0, 0), (512, 512, 912)), id="tall")
    added = blueprint.light_rooms()
    assert added, "a 896-tall room needs fill"
    floor_z = blueprint.elements()[0].interior.mins.z  # type: ignore[attr-defined]
    drops = sorted(lamp.position.z - floor_z for lamp in added)
    assert drops[0] <= lighting.MAX_LAMP_SPACING, (
        "no lamp lands within one spacing of the floor, so the floor is unlit: "
        f"nearest is {drops[0]:g} units up"
    )


def test_light_rooms_is_still_idempotent_with_tiers():
    blueprint = Blueprint("zm_tier_idempotent_pin")
    blueprint.add_room(Bounds.between((0, 0, 0), (512, 512, 912)), id="tall")
    first = blueprint.light_rooms()
    assert first
    assert blueprint.light_rooms() == []


# --------------------------------------------------------------------------
# The dark stairwell, as an outcome rather than a setting
# --------------------------------------------------------------------------
#: Relative illuminance at a point, in stops, from the lamp model the emitter
#: writes: inverse square from ``falloffdistance``, ramped to nothing over the
#: last ``far_edge`` of ``radius``.  Only the *difference* between two points
#: means anything here, which is all the test uses it for.
def _stops_at(point, lamps) -> float:
    falloff = float(dict(LIGHT_KEYS)["falloffdistance"])
    total = 0.0
    for lamp in lamps:
        distance = math.dist(
            point, (lamp.position.x, lamp.position.y, lamp.position.z)
        )
        if distance >= lamp.radius:
            continue
        value = (falloff / max(distance, falloff)) ** 2
        ramp_starts = lighting.useful_reach(lamp.radius)
        if distance > ramp_starts:
            value *= max(0.0, (lamp.radius - distance) / (lamp.radius - ramp_starts))
        total += value
    return math.log2(total) if total > 0 else -math.inf


#: How far under the dimmest ordinary room a stair flight may read.  Zero would
#: be "at least as bright as the worst room"; a dark flight can sit 1.6 stops
#: *under* it while the floor at its foot is 3.5 stops under the median room,
#: so the bar is set at parity with the dimmest room.
STAIR_PARITY_STOPS = 0.0


