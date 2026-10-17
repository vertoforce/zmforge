"""Z48: a player can walk to the spot each interactive is used from.

The defect these are written from: a room packed with scenery around one
working machine, where the working machine cannot be bought.  Every other
rule passes it: ``Z42`` proves the standing room in front of the machine is
empty, ``Z25`` proves the room is joined to the spawn, and neither of them
asks whether a player can get *to* that standing room with the furniture in
the way.

The check is :mod:`zmforge.verify.approach`.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint.elements import Prop, PropScatter
from zmforge.blueprint.reach import keep_of
from zmforge.materials import Material
from zmforge.recipes import three_room_map
from zmforge.spatial import Point
from zmforge.verify import check_blueprint
from zmforge.verify.approach import (
    CLIMBED,
    prop_obstacles,
    UNMEASURED_BOX,
    WALK_MARGIN,
    check_interactive_approach,
)


ART = Material("t7_concrete_trowelled")

#: The working machine the checks look for.
JUGGERNOG = "perk_juggernog"


def _findings(report, element_id=None):
    return [
        f
        for f in report.findings
        if f.code == "Z48" and (element_id is None or f.element_id == element_id)
    ]


# --------------------------------------------------------------------------
# What counts as an obstacle
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def fixture_map():
    return three_room_map("zm_approach_fixture")


def _machine_in(blueprint):
    """One machine on the fixture map, and the room it stands in."""
    from zmforge.blueprint.elements import Machine, Room

    machine = blueprint.elements(Machine)[0]
    room = next(
        element
        for element in blueprint.elements(Room)
        if element.interior.holds_flat(machine.position.x, machine.position.y)
    )
    return machine, room


def _fill_around(blueprint, model, *, solid, height=72.0, lift=0.0, id="fill"):
    """Pack the machine's whole room, leaving only its own standing room.

    The shape of the defect: every keep-clear
    rule is satisfied -- the apron is empty -- and there is no way to the
    apron.
    """
    machine, room = _machine_in(blueprint)
    keep = keep_of(machine)
    apron = keep.aprons[0]
    box = ((-24.0, -24.0, lift), (24.0, 24.0, lift + height))
    inside = room.interior
    props = []
    x = inside.mins.x + 24.0
    while x < inside.maxs.x - 24.0:
        y = inside.mins.y + 24.0
        while y < inside.maxs.y - 24.0:
            in_apron = (
                apron.mins.x - 24.0 < x < apron.maxs.x + 24.0
                and apron.mins.y - 24.0 < y < apron.maxs.y + 24.0
            )
            if not in_apron:
                props.append(
                    Prop(
                        model=model,
                        origin=Point(x, y, room.floor_z),
                        yaw=0.0,
                        solid=solid,
                        dynamic=not solid,
                        collision_box=box,
                        id=f"{id}_{len(props)}",
                    )
                )
            y += 48.0
        x += 48.0
    blueprint.place_props(props, id=id)
    return machine


def test_walk_through_scenery_around_a_buyable_is_an_error(fixture_map):
    """No collision, and still no way in that reads.

    An error for a buyable, because the placer keeps a clear lane in front of each
    (zmforge.blueprint.lanes, verify/approach.py)."""
    screened = three_room_map("zm_approach_fixture")
    machine = _fill_around(screened, "p7_zm_vending_jugg", solid=False)
    said = _findings(check_interactive_approach(screened), machine.id)
    assert said and said[0].is_error, [str(f) for f in said]
    assert "scenery" in said[0].message


def test_a_wall_across_the_approach_is_reported(fixture_map):
    blocked = three_room_map("zm_approach_fixture")
    machine = _fill_around(blocked, "p7_zm_vending_jugg", solid=True)
    said = _findings(check_interactive_approach(blocked), machine.id)
    assert said and said[0].is_error, [str(f) for f in said]
    assert _findings(check_interactive_approach(fixture_map), machine.id) == []


def test_a_prop_low_enough_to_jump_onto_is_not_a_wall(fixture_map):
    """Clutter low enough to jump onto is a step, not a wall.

    Counting each low piece of clutter as a wall would report a buy on a
    raised platform unreachable, and a player jumps onto clutter.
    """
    low = three_room_map("zm_approach_fixture")
    machine = _fill_around(low, "p7_zm_vending_jugg", solid=True, height=CLIMBED - 1.0)
    assert _findings(check_interactive_approach(low), machine.id) == []


def test_a_duct_along_a_soffit_is_not_a_wall(fixture_map):
    """Mounted off the floor is walked under; ``mount_kind`` already says so."""
    hung = three_room_map("zm_approach_fixture")
    machine = _fill_around(
        hung, "p7_duct_metal_circular_straight_32", solid=True, lift=48.0
    )
    assert _findings(check_interactive_approach(hung), machine.id) == []


def test_a_model_with_no_measured_box_is_reported_not_skipped():
    """A model with no measured box is a blind spot: no box, no finding, no line."""
    unknown = three_room_map("zm_approach_fixture")
    unknown.place_props(
        [
            Prop(model="zmf_prop_nobody_measured", origin=Point(0.0, 0.0, 8.0), yaw=0.0)
        ],
        id="unmeasured",
    )
    said = [
        f
        for f in _findings(check_interactive_approach(unknown))
        if "zmf_prop_nobody_measured" in f.message
    ]
    assert said and not said[0].is_error


def test_the_margin_is_half_a_player():
    """A gap has to measure a whole hull before the flood walks it."""
    from zmforge.verify.model import PLAYER_HULL_WIDTH

    assert WALK_MARGIN * 2.0 == PLAYER_HULL_WIDTH


def test_a_walk_through_stalk_against_the_wall_beside_a_chalk_is_not_in_the_lane() -> None:
    """A wall buy on a corn wall must not leave a chunk of wall bare:
    the lane rule bared all 112 units of every wall buy's apron on a corn
    wall.  A walk-through stalk tucked against the buy's own wall, clear of
    the chalk by CHALK_MARGIN, leaves the drawing and the standing floor
    clear; in front of the chalk, out in the stand, or solid, it still goes."""
    from zmforge.blueprint import lanes
    from zmforge.blueprint.elements import WallWeapon

    bp = three_room_map("zm_lane_probe")
    buy = bp.elements(WallWeapon)[0]          # (-494, -100), facing east, chalk y -124..-76
    keep = keep_of(buy)

    def stalk(x, y, solid=False, model="zmf_prop_corn_stalk_thin", scale=1.2):
        return Prop(model=model, origin=Point(x, y, 0.0), yaw=0.0, scale=scale, solid=solid)

    assert not lanes.blocks_lane(stalk(-490.0, -156.0), keep)        # beside, against the wall
    assert not lanes.blocks_lane(stalk(-490.0, -44.0), keep)         # the other side
    assert lanes.blocks_lane(stalk(-490.0, -100.0), keep)            # in front of the chalk
    assert lanes.blocks_lane(stalk(-490.0, -132.0), keep)            # inside the margin
    assert lanes.blocks_lane(stalk(-440.0, -156.0), keep)            # out in the stand
    assert lanes.blocks_lane(stalk(-490.0, -156.0, scale=3.0), keep)  # leaves reach the stand
    assert lanes.blocks_lane(Prop(model="p7_barrel_metal_55gal_blue", origin=Point(-480.0, -150.0, 0.0), yaw=0.0,
                                  solid=True), keep)
