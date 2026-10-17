"""Z43: world brushwork that stands on nothing.

This defect is found by looking at a map, not by a check: a column written
to start at the first floor's height, 288, over a deck that runs 272 to 288,
begins exactly 16 units above the deck it was meant to stand on.  Every other
check passes such columns -- they overlap nothing, block no route, sit inside a zone and are lit.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint.elements import FLOATS_ON_PURPOSE, Massing
from zmforge.blueprint.model import Blueprint
from zmforge.materials import Material
from zmforge.recipes import three_room_map
from zmforge.recipes.layouts import one_room_map
from zmforge.solids.layout import Aperture
from zmforge.spatial import Facing, Point, Side, Span
from zmforge.verify.hanging import HANG_SLACK, check_nothing_hangs

_STONE = Material("t7_concrete_trowelled")


def _room(name: str = "zm_hang") -> Blueprint:
    blueprint = Blueprint(name)
    room = blueprint.add_room(
        Span.between((-512, -512, 0), (512, 512, 512)),
        wall=16.0,
        openings=[Aperture(Side.EAST, 80.0, 96.0)],
        id="room",
    )
    blueprint.add_zone("room", room, starting=True)
    blueprint.set_player_start(Point(-256, 0, room.floor_z + 16), Facing.EAST)
    return blueprint


def test_a_slab_in_mid_air_is_reported() -> None:
    """Plant a slab in mid-air and watch the check report it."""
    blueprint = _room()
    blueprint.add_slab(
        Span.flat_ok(Point(-128, -128, 0), Point(128, 128, 0)), 320.0, 16.0,
        _STONE, id="floating_deck",
    )
    codes = {(f.code, f.element_id) for f in check_nothing_hangs(blueprint).findings}
    assert codes == {("Z43", "floating_deck")}


def test_a_slab_that_says_it_floats_is_left_alone() -> None:
    """The declaration lives on the geometry, the way ``reachable`` does."""
    blueprint = _room()
    blueprint.add_block(
        Span.between(Point(-128, -128, 304.0), Point(128, 128, 320.0)),
        _STONE, walkable=True, id="floating_deck", note=FLOATS_ON_PURPOSE,
    )
    assert check_nothing_hangs(blueprint).findings == []


def test_a_column_that_misses_its_deck_by_a_hand_is_reported() -> None:
    """The defect as it actually happened: a 16-unit slot under four columns.

    Not a slab in the void -- something with a perfectly good deck under it,
    16 units below where the column was written to start.  That is the gap
    nobody saw, and it is the shape :data:`HANG_SLACK` is sized against.
    """
    blueprint = _room()
    # a real deck, wall to wall, so it is fixed to the room and not the
    # thing under test
    blueprint.add_slab(
        Span.flat_ok(Point(-496, -496, 0), Point(496, 496, 0)), 288.0, 16.0,
        _STONE, id="deck",
    )
    blueprint.add_block(
        Span.between(Point(-64, -64, 288.0 + 16.0), Point(64, 64, 448.0)),
        _STONE, id="column_adrift",
    )
    codes = {(f.code, f.element_id) for f in check_nothing_hangs(blueprint).findings}
    assert codes == {("Z43", "column_adrift")}

    # and the same column written to meet the deck passes
    fixed = _room("zm_hang_fixed")
    fixed.add_slab(
        Span.flat_ok(Point(-496, -496, 0), Point(496, 496, 0)), 288.0, 16.0,
        _STONE, id="deck",
    )
    fixed.add_block(
        Span.between(Point(-64, -64, 288.0), Point(64, 64, 448.0)),
        _STONE, id="column_seated",
    )
    assert check_nothing_hangs(fixed).findings == []


def test_a_sign_flat_on_a_wall_is_fixed_to_it_and_not_hanging() -> None:
    """A picture two units off a wall is fixed to it, not hanging."""
    blueprint = _room()
    blueprint.add_block(
        Span.between(Point(-496, -32, 200.0), Point(-494, 32, 264.0)),
        _STONE, id="poster",
    )
    assert check_nothing_hangs(blueprint).findings == []


def test_the_slack_is_a_grid_tolerance_and_not_a_free_gap() -> None:
    """Two units absorbs floating point; it does not excuse a step."""
    assert HANG_SLACK <= 2.0
