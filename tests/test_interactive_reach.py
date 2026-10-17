"""Standing room: one interactive item may not stand in front of another.

The defect these are written from: a wall buy at ``(200, -560)`` on a south
wall facing north and a Juggernog machine at ``(200, -536)`` on the same wall
facing the same way.  The machine hangs in front of the buy and the gun
cannot be bought, yet every other check passes, because none of them asks
about the other item.

The rule is :mod:`zmforge.blueprint.reach`, enforced by ``Blueprint._install``
and re-asked of a finished model by ``Z42``.
"""

from __future__ import annotations

import math

import pytest

from zmforge.blueprint import reach
from zmforge.blueprint.elements import WallWeapon
from zmforge.errors import InteractiveBlocked
from zmforge.recipes import three_room_map
from zmforge.spatial import Facing, Point
from zmforge.verify import check_blueprint


#: A clear stretch of the arena's south wall in the three-room fixture --
#: that fixture puts a buy of its own at x = 320 and perks in the corners --
#: and a spot 24 units in front of it, which is the machine depth this rule
#: uses and the gap that put the machine over the buy.
FIXTURE_WALL = Point(160.0, -496.0, 8.0)
FIXTURE_IN_FRONT = Point(160.0, -472.0, 16.0)


# --------------------------------------------------------------------------
# The rule, on a fixture small enough to read
# --------------------------------------------------------------------------
def test_a_machine_in_front_of_a_wall_buy_is_refused() -> None:
    blueprint = three_room_map("zm_forge_reach")
    blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="buy")
    with pytest.raises(InteractiveBlocked) as raised:
        blueprint.place_perk("juggernog", FIXTURE_IN_FRONT, Facing.NORTH, id="jug")
    assert "buy" in str(raised.value) and "jug" in str(raised.value)


def test_the_same_pair_the_other_way_round_is_refused_too() -> None:
    """Order of placement does not decide whether a map is playable."""
    blueprint = three_room_map("zm_forge_reach_reversed")
    blueprint.place_perk("juggernog", FIXTURE_IN_FRONT, Facing.NORTH, id="jug")
    with pytest.raises(InteractiveBlocked):
        blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="buy")


def test_two_machines_in_the_same_place_are_refused() -> None:
    blueprint = three_room_map("zm_forge_reach_stacked")
    blueprint.place_perk("juggernog", Point(300.0, -300.0, 16.0), Facing.NORTH, id="a")
    with pytest.raises(InteractiveBlocked) as raised:
        blueprint.place_perk(
            "deadshot", Point(316.0, -300.0, 16.0), Facing.NORTH, id="b"
        )
    assert raised.value.clash.kind == "body"


def test_two_wall_buys_on_one_patch_of_wall_are_refused() -> None:
    """Neither is a body standing in a room, and they still cannot share a wall.

    The chalk drawings would be through each other and one of the two
    prompts unreachable, so "two boxes in one place" is asked of every pair
    and not only of the things that stand on a floor.
    """
    blueprint = three_room_map("zm_forge_reach_twobuys")
    blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="one")
    with pytest.raises(InteractiveBlocked) as raised:
        blueprint.place_wall_weapon(
            "smg_standard",
            Point(FIXTURE_WALL.x + 16.0, FIXTURE_WALL.y, FIXTURE_WALL.z),
            Facing.NORTH,
            id="two",
        )
    assert raised.value.clash.kind == "body"


def test_a_buy_beside_a_machine_on_the_same_wall_is_fine() -> None:
    """Shared standing room is a corner, not a fault.

    The two are far enough apart that neither is in front of the other; their
    aprons overlap, and that is deliberately allowed.
    """
    blueprint = three_room_map("zm_forge_reach_corner")
    blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="buy")
    machine = blueprint.place_perk(
        "juggernog", Point(240.0, -472.0, 16.0), Facing.NORTH, id="jug"
    )
    assert machine.id == "jug"
    keeps = {k.element_id: k for k in blueprint.interactive_keeps()}
    assert reach._intersection(keeps["buy"].aprons[0], keeps["jug"].aprons[0])


# --------------------------------------------------------------------------
# Z42, over a model the placement methods never saw
# --------------------------------------------------------------------------
def _planted_overlap():
    """A map with a machine moved in front of a buy after it was placed.

    This is the road ``Z42`` exists for: the placement methods refuse it, so
    the only way a finished model can carry one is if it did not come through
    them -- read out of the editor, or edited afterwards, which is what this
    does.
    """
    blueprint = three_room_map("zm_forge_reach_planted")
    blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="buy")
    machine = blueprint.place_perk(
        "juggernog", Point(300.0, 200.0, 16.0), Facing.NORTH, id="jug"
    )
    machine.position = FIXTURE_IN_FRONT
    return blueprint


def test_z42_finds_an_overlap_the_placement_methods_never_saw() -> None:
    report = check_blueprint(_planted_overlap())
    found = [f for f in report.errors if f.code == "Z42"]
    assert len(found) == 1, [str(f) for f in report.errors]
    assert "buy" in found[0].message and "jug" in found[0].message


def test_z42_is_silent_on_the_same_map_with_the_machine_where_it_was() -> None:
    blueprint = three_room_map("zm_forge_reach_clean")
    blueprint.place_wall_weapon("ar_standard", FIXTURE_WALL, Facing.NORTH, id="buy")
    blueprint.place_perk("juggernog", Point(300.0, 200.0, 16.0), Facing.NORTH, id="jug")
    report = check_blueprint(blueprint)
    assert [f for f in report.findings if f.code == "Z42"] == []


# --------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------
def test_the_apron_is_the_size_the_rule_says_it_is() -> None:
    """The three numbers the rule is written against, so they cannot drift."""
    assert reach.APRON_SIDE == 32.0
    assert reach.APRON_DEPTH == 96.0
    assert reach.APRON_DEPTH_STAND_BACK == 128.0
    assert reach.BODIES["machine"].apron == reach.APRON_DEPTH
    assert reach.BODIES["wall_weapon"].apron == reach.APRON_DEPTH
    assert reach.BODIES["mystery_box"].apron == reach.APRON_DEPTH_STAND_BACK
    assert reach.BODIES["pack_a_punch"].apron == reach.APRON_DEPTH_STAND_BACK


def test_an_aprons_width_is_the_item_plus_thirty_two_a_side() -> None:
    blueprint = three_room_map("zm_forge_reach_width")
    blueprint.place_perk("juggernog", Point(300.0, 0.0, 16.0), Facing.NORTH, id="jug")
    keep = blueprint.interactive_keeps()[-1]
    body = reach.BODIES["machine"]
    assert keep.body.size.x == body.half_width * 2
    assert keep.aprons[0].size.x == body.half_width * 2 + reach.APRON_SIDE * 2
    assert keep.aprons[0].size.y == body.apron


