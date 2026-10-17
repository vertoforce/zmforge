"""The relation vocabulary and the plan geometry under it.

Every case here is a small synthetic room with a box or two in it, because
that is the unit a placement rule works on: a rectangle, a footprint with a
yaw, and two numbers for height.  A test that pins a default
threshold says what the threshold guards against.

Nothing here touches the recipes.  The recipes place their props through
:mod:`zmforge.placement.relations`, and these tests pin the relations on
their own, without building a map.
"""

from __future__ import annotations

import math

import pytest

from zmforge.placement.geometry import (
    Poly2,
    convex_hull,
    minkowski_disc,
    minkowski_segment,
    rotate,
    segment_distance,
    unit_hash,
)
from zmforge.placement.relations import (
    CoPlanar,
    HangsFrom,
    MountKind,
    NoOverlap,
    OnWall,
    PLAYER_RADIUS,
    Placed,
    StableAgainst,
    SupportedBy,
    Surface,
    Touching,
    mount_kind_of_box,
    walls_of_rect,
)

#: A room the size of a typical generated lobby, interior only.
ROOM = (0.0, 0.0, 400.0, 300.0)
FLOOR_Z = 16.0
CEILING_Z = 16.0 + 128.0

#: A wall fixture's box, measured the way the palette's signs are: z-centred,
#: a 32-unit face and a fraction of a unit through.
SIGN_BOX = ((-16.0, -0.5, -16.0), (16.0, 0.5, 16.0))
#: A floor-standing model: its box sits on its own origin.
CRATE_BOX = ((-24.0, -24.0, 0.0), (24.0, 24.0, 48.0))
#: A hanging light: its box is wholly below its origin.
CHANDELIER_BOX = ((-20.0, -20.0, -40.0), (20.0, 20.0, 0.0))
#: A chunk of masonry: z-centred and thick on every axis.
RUBBLE_BOX = ((-14.0, -12.0, -9.0), (14.0, 12.0, 9.0))


def walls():
    return {w.side: w for w in walls_of_rect("lobby", *ROOM, FLOOR_Z, CEILING_Z)}


# --------------------------------------------------------------------------
# Plan geometry
# --------------------------------------------------------------------------
def test_an_oriented_box_keeps_its_area_when_it_turns() -> None:
    square = Poly2.box(100.0, 100.0, 20.0, 10.0, 0.0)
    turned = Poly2.box(100.0, 100.0, 20.0, 10.0, 37.0)
    assert square.area == pytest.approx(800.0)
    assert turned.area == pytest.approx(800.0)


def test_a_turned_box_is_not_its_own_bounding_box() -> None:
    """A rotated footprint is the thing that gets a prop into a wall."""
    turned = Poly2.box(0.0, 0.0, 45.0, 10.0, 45.0)
    x0, y0, x1, y1 = turned.bounds
    assert x1 - x0 == pytest.approx(math.sqrt(2.0) * 55.0, rel=1e-6)
    assert turned.area == pytest.approx(1800.0)


def test_overlap_area_is_the_shared_floor() -> None:
    a = Poly2.rect(0.0, 0.0, 100.0, 100.0)
    b = Poly2.rect(50.0, 0.0, 150.0, 100.0)
    assert a.overlap_area(b) == pytest.approx(5000.0)
    assert a.overlap_area(Poly2.rect(200.0, 0.0, 300.0, 100.0)) == 0.0


def test_gap_to_is_clear_distance_and_zero_when_they_meet() -> None:
    a = Poly2.rect(0.0, 0.0, 100.0, 100.0)
    assert a.gap_to(Poly2.rect(140.0, 0.0, 200.0, 100.0)) == pytest.approx(40.0)
    assert a.gap_to(Poly2.rect(100.0, 0.0, 200.0, 100.0)) == pytest.approx(0.0)
    assert a.gap_to(Poly2.rect(50.0, 50.0, 200.0, 200.0)) == 0.0


def test_a_point_inside_and_a_point_out() -> None:
    poly = Poly2.box(0.0, 0.0, 10.0, 10.0, 45.0)
    assert poly.holds((0.0, 0.0))
    assert poly.holds((0.0, 14.0))
    assert not poly.holds((10.0, 10.0))


def test_the_hull_of_a_square_with_a_point_in_it_is_the_square() -> None:
    hull = convex_hull([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)])
    assert len(hull) == 4
    assert Poly2(hull).area == pytest.approx(100.0)


def test_rotate_turns_counter_clockwise() -> None:
    x, y = rotate(10.0, 0.0, 90.0)
    assert (x, y) == pytest.approx((0.0, 10.0))


def test_segment_distance_measures_to_the_segment_not_its_line() -> None:
    assert segment_distance((0.0, 10.0), (0.0, 0.0), (10.0, 0.0)) == pytest.approx(10.0)
    assert segment_distance((20.0, 0.0), (0.0, 0.0), (10.0, 0.0)) == pytest.approx(10.0)


# --------------------------------------------------------------------------
# Minkowski sums: clearance from the model's own shape
# --------------------------------------------------------------------------
def test_the_disc_sum_is_the_footprint_plus_its_perimeter_and_a_circle() -> None:
    """Merrell's clearance, checked against the closed form.

    A convex polygon grown by a disc of radius *r* gains ``perimeter * r``
    along its sides and exactly one circle at its corners.  Sixteen segments
    understate the circle by about 2%, which is the approximation the constant
    in :mod:`zmforge.placement.geometry` documents.
    """
    rect = Poly2.rect(0.0, 0.0, 100.0, 60.0)
    grown = minkowski_disc(rect, PLAYER_RADIUS)
    exact = 6000.0 + 320.0 * PLAYER_RADIUS + math.pi * PLAYER_RADIUS ** 2
    assert grown.area == pytest.approx(exact, rel=0.02)
    assert grown.area < exact  # a polygon disc is inside the true circle


def test_growing_by_a_disc_keeps_the_rotation() -> None:
    turned = Poly2.box(0.0, 0.0, 40.0, 10.0, 30.0)
    grown = minkowski_disc(turned, PLAYER_RADIUS)
    for point in turned.points:
        assert grown.holds(point)
    long_way = math.hypot(*rotate(40.0 + PLAYER_RADIUS, 0.0, 30.0))
    assert grown.holds(rotate(long_way - 1.0, 0.0, 30.0))
    assert not grown.holds(rotate(0.0, 10.0 + PLAYER_RADIUS + 2.0, 30.0))


def test_a_disc_of_no_radius_changes_nothing() -> None:
    rect = Poly2.rect(0.0, 0.0, 10.0, 10.0)
    assert minkowski_disc(rect, 0.0) is rect


def test_the_segment_sum_sweeps_one_way_only() -> None:
    """A front apron is directional: a desk needs room in front, not behind."""
    desk = Poly2.rect(0.0, 0.0, 90.0, 30.0)
    swept = minkowski_segment(desk, 0.0, -48.0)
    assert swept.area == pytest.approx(2700.0 + 90.0 * 48.0)
    assert swept.holds((45.0, -40.0))
    assert not swept.holds((45.0, 40.0))


# --------------------------------------------------------------------------
# Mount kind, read off the box
# --------------------------------------------------------------------------
def test_a_box_that_sits_on_its_origin_stands_on_the_floor() -> None:
    assert mount_kind_of_box(CRATE_BOX) is MountKind.FLOOR


def test_a_z_centred_thin_box_is_a_wall_fixture() -> None:
    """A box centred on its origin in Z is a wall fixture, not a floor prop."""
    assert mount_kind_of_box(SIGN_BOX) is MountKind.WALL


def test_a_box_wholly_below_its_origin_hangs_from_the_ceiling() -> None:
    assert mount_kind_of_box(CHANDELIER_BOX) is MountKind.CEILING


def test_a_z_centred_chunky_box_settles_nothing() -> None:
    assert mount_kind_of_box(RUBBLE_BOX) is MountKind.EITHER


def test_a_model_with_no_measured_box_is_treated_as_floor_standing() -> None:
    """The safe answer: it is what everything got before mount kinds existed."""
    assert mount_kind_of_box(None) is MountKind.FLOOR


# --------------------------------------------------------------------------
# Placed: origin in, footprint out
# --------------------------------------------------------------------------
def test_a_model_placed_by_origin_reports_its_own_footprint_centre() -> None:
    """A box that is off-centre in plan does not sit where its origin does."""
    box = ((0.0, -10.0, 0.0), (60.0, 10.0, 40.0))
    placed = Placed.from_model("desk", box, (100.0, 200.0, 16.0))
    assert (placed.x, placed.y) == pytest.approx((130.0, 200.0))
    assert (placed.hx, placed.hy) == pytest.approx((30.0, 10.0))
    assert (placed.z_low, placed.z_high) == pytest.approx((16.0, 56.0))


def test_the_footprint_centre_turns_with_the_yaw() -> None:
    box = ((0.0, -10.0, 0.0), (60.0, 10.0, 40.0))
    placed = Placed.from_model("desk", box, (100.0, 200.0, 16.0), yaw=90.0)
    assert (placed.x, placed.y) == pytest.approx((100.0, 230.0))


def test_scale_multiplies_the_box_and_the_offset() -> None:
    box = ((0.0, -10.0, 0.0), (60.0, 10.0, 40.0))
    placed = Placed.from_model("desk", box, (0.0, 0.0, 0.0), scale=2.0)
    assert (placed.x, placed.hx, placed.z_high) == pytest.approx((60.0, 60.0, 80.0))


def test_position_prints_the_way_the_audit_prints_it() -> None:
    placed = Placed("bench", -1573.4, 173.2, 30.0, 10.0, 0.0, 16.0, 34.0)
    assert placed.position == "-1573 173 16"


# --------------------------------------------------------------------------
# StableAgainst and OnWall
# --------------------------------------------------------------------------
def test_a_sign_flat_on_the_wall_at_reading_height_holds() -> None:
    sign = Placed.from_model("sign", SIGN_BOX, (200.0, 0.5, FLOOR_Z + 64.0))
    assert OnWall().holds(sign, walls()["south"])
    assert StableAgainst().holds(sign, walls()["south"])


def test_a_sign_standing_on_the_floor_is_reported_with_its_sill() -> None:
    """The map's single most visible fault, stated as a relation."""
    sign = Placed.from_model("sign", SIGN_BOX, (200.0, 0.5, FLOOR_Z))
    broken = OnWall().check(sign, walls()["south"])
    assert broken is not None
    assert broken.relation == "OnWall"
    assert "below the floor" in broken.detail


def test_a_fixture_floating_off_its_wall_is_reported() -> None:
    sign = Placed.from_model("sign", SIGN_BOX, (200.0, 40.0, FLOOR_Z + 64.0))
    broken = StableAgainst().check(sign, walls()["south"])
    assert broken is not None and broken.amount == pytest.approx(39.5)
    assert "off the south wall" in broken.detail


def test_a_fixture_inside_its_wall_is_reported_the_other_way() -> None:
    sign = Placed.from_model("sign", SIGN_BOX, (200.0, -6.0, FLOOR_Z + 64.0))
    broken = StableAgainst().check(sign, walls()["south"])
    assert broken is not None and "inside the south wall" in broken.detail


def test_a_fixture_hanging_past_the_end_of_its_wall_is_reported() -> None:
    sign = Placed.from_model("sign", SIGN_BOX, (398.0, 0.5, FLOOR_Z + 64.0))
    broken = StableAgainst().check(sign, walls()["south"])
    assert broken is not None and "past the end" in broken.detail
    assert StableAgainst(ends=False).holds(sign, walls()["south"])


def test_a_fixture_over_the_sill_range_is_reported() -> None:
    sign = Placed.from_model("sign", SIGN_BOX, (200.0, 0.5, FLOOR_Z + 200.0))
    broken = OnWall(sill_high=154.0).check(sign, walls()["south"])
    assert broken is not None and "over the 154-unit sill" in broken.detail


# --------------------------------------------------------------------------
# SupportedBy
# --------------------------------------------------------------------------
def test_a_crate_on_the_floor_is_supported() -> None:
    floor = Surface.rect("the lobby floor", *ROOM, FLOOR_Z)
    crate = Placed.from_model("crate", CRATE_BOX, (100.0, 100.0, FLOOR_Z))
    assert SupportedBy().holds(crate, floor)


def test_a_prop_floating_above_its_floor_is_reported_with_the_drop() -> None:
    """A prop hovering over its floor is reported with how far it floats."""
    floor = Surface.rect("the yard floor", *ROOM, FLOOR_Z)
    crate = Placed.from_model("crate", CRATE_BOX, (100.0, 100.0, FLOOR_Z + 68.0))
    broken = SupportedBy().check(crate, floor)
    assert broken is not None and broken.amount == pytest.approx(68.0)
    assert "floats 68 units" in broken.detail


def test_a_prop_sunk_into_its_floor_is_reported() -> None:
    floor = Surface.rect("the room floor", *ROOM, FLOOR_Z)
    column = Placed("rebar", 100.0, 100.0, 8.0, 8.0, 0.0, FLOOR_Z - 65.0, FLOOR_Z + 65.0)
    broken = SupportedBy().check(column, floor)
    assert broken is not None and "65 units into" in broken.detail


def test_a_bed_hanging_off_its_plinth_is_reported_with_the_share_on_it() -> None:
    """A 120-long bed with none of its four corners on a 60-wide plinth."""
    plinth = Surface.rect("the plinth", 0.0, 0.0, 60.0, 200.0, 48.0)
    bed = Placed("bunk", 100.0, 100.0, 60.0, 30.0, 0.0, 48.0, 120.0)
    broken = SupportedBy().check(bed, plinth)
    assert broken is not None and "% of its footprint on" in broken.detail


def test_an_overhang_a_caller_allows_is_not_reported() -> None:
    plinth = Surface.rect("a counter", 0.0, 0.0, 60.0, 200.0, 48.0)
    desk = Placed("desk", 40.0, 100.0, 40.0, 20.0, 0.0, 48.0, 78.0)
    assert not SupportedBy().holds(desk, plinth)
    assert SupportedBy(share=0.2).holds(desk, plinth)


# --------------------------------------------------------------------------
# HangsFrom
# --------------------------------------------------------------------------
def test_a_chandelier_under_the_ceiling_hangs_from_it() -> None:
    light = Placed.from_model("chandelier", CHANDELIER_BOX, (200.0, 150.0, CEILING_Z))
    assert HangsFrom().holds(light, CEILING_Z, "hall")


def test_a_chandelier_left_on_the_floor_is_not_hanging_from_anything() -> None:
    light = Placed.from_model("chandelier", CHANDELIER_BOX, (200.0, 150.0, FLOOR_Z))
    broken = HangsFrom().check(light, CEILING_Z, "hall")
    assert broken is not None and broken.amount == pytest.approx(128.0)
    assert "under the ceiling of hall" in broken.detail


def test_something_through_the_ceiling_is_reported_the_other_way() -> None:
    light = Placed("beam", 200.0, 150.0, 10.0, 10.0, 0.0, CEILING_Z, CEILING_Z + 20.0)
    broken = HangsFrom().check(light, CEILING_Z)
    assert broken is not None and "pokes 20 units through" in broken.detail


# --------------------------------------------------------------------------
# NoOverlap: the interpenetration rule, with both allowances
# --------------------------------------------------------------------------
def test_two_props_apart_do_not_overlap() -> None:
    a = Placed("desk", 0.0, 0.0, 45.0, 25.0, 0.0, 16.0, 48.0)
    b = Placed("bench", 200.0, 0.0, 30.0, 10.0, 0.0, 16.0, 34.0)
    assert NoOverlap().holds(a, b)


def test_a_desk_through_a_bench_is_reported_with_the_share() -> None:
    """A desk 72% inside a bench."""
    desk = Placed("desk", 0.0, 0.0, 45.0, 25.0, 0.0, 16.0, 48.0)
    bench = Placed("bench", 20.0, 0.0, 30.0, 20.0, 0.0, 16.0, 34.0)
    broken = NoOverlap().check(desk, bench)
    assert broken is not None and broken.relation == "NoOverlap"
    assert broken.amount > 0.25
    assert "inside bench" in broken.detail


def test_touching_along_one_side_is_not_interpenetration() -> None:
    a = Placed("cabinet", 0.0, 0.0, 20.0, 20.0, 0.0, 16.0, 80.0)
    b = Placed("cabinet", 40.0, 0.0, 20.0, 20.0, 0.0, 16.0, 80.0)
    assert NoOverlap().holds(a, b)


def test_a_cup_on_a_desk_is_a_stack_not_a_clash() -> None:
    desk = Placed("desk", 0.0, 0.0, 45.0, 25.0, 0.0, 16.0, 48.0)
    cup = Placed("cup", 0.0, 0.0, 4.0, 4.0, 0.0, 48.0, 54.0)
    assert NoOverlap().holds(desk, cup)


def test_two_newspapers_on_the_same_patch_are_not_a_stack() -> None:
    """The reason the stacking allowance is capped at half the shorter height."""
    a = Placed("paper", 0.0, 0.0, 8.0, 6.0, 0.0, 16.0, 18.3)
    b = Placed("paper", 2.0, 0.0, 8.0, 6.0, 0.0, 16.0, 18.3)
    assert not NoOverlap().holds(a, b)


def test_small_props_are_skipped_when_a_minimum_side_is_asked_for() -> None:
    """A cup half inside a bowl is a still life, and the map is full of them."""
    a = Placed("cup", 0.0, 0.0, 4.0, 4.0, 0.0, 16.0, 22.0)
    b = Placed("bowl", 2.0, 0.0, 6.0, 6.0, 0.0, 16.0, 20.0)
    assert not NoOverlap().holds(a, b)
    assert NoOverlap(min_side=40.0).holds(a, b)


def test_the_tolerance_is_a_share_of_the_smaller_footprint() -> None:
    big = Placed("shelf", 0.0, 0.0, 100.0, 20.0, 0.0, 16.0, 80.0)
    small = Placed("stool", 99.0, 0.0, 10.0, 10.0, 0.0, 16.0, 34.0)
    shared = 11.0 * 20.0
    share = shared / (20.0 * 20.0)
    assert NoOverlap(tolerance=share + 0.01).holds(big, small)
    assert not NoOverlap(tolerance=share - 0.01).holds(big, small)


def test_a_yaw_turns_a_clash_into_a_clearance() -> None:
    a = Placed("pipe", 0.0, 0.0, 64.0, 6.0, 0.0, 16.0, 40.0)
    b = Placed("pipe", 0.0, 30.0, 64.0, 6.0, 0.0, 16.0, 40.0)
    assert NoOverlap().holds(a, b)
    assert not NoOverlap().holds(a, b.turned_to(90.0))


# --------------------------------------------------------------------------
# Touching and CoPlanar
# --------------------------------------------------------------------------
def test_a_chair_pulled_up_to_a_table_is_touching_it() -> None:
    table = Placed("table", 0.0, 0.0, 60.0, 30.0, 0.0, 16.0, 46.0)
    chair = Placed("chair", 0.0, 44.0, 12.0, 12.0, 0.0, 16.0, 50.0)
    assert Touching().holds(chair, table)


def test_a_chair_across_the_room_is_not_touching_the_table() -> None:
    table = Placed("table", 0.0, 0.0, 60.0, 30.0, 0.0, 16.0, 46.0)
    chair = Placed("chair", 0.0, 200.0, 12.0, 12.0, 0.0, 16.0, 50.0)
    broken = Touching().check(chair, table)
    assert broken is not None and "not touching it" in broken.detail


def test_a_chair_inside_the_table_is_not_touching_it_either() -> None:
    table = Placed("table", 0.0, 0.0, 60.0, 30.0, 0.0, 16.0, 46.0)
    chair = Placed("chair", 0.0, 0.0, 12.0, 12.0, 0.0, 16.0, 50.0)
    broken = Touching().check(chair, table)
    assert broken is not None and "inside" in broken.detail


def test_a_row_of_cabinets_lined_up_on_one_face_is_coplanar() -> None:
    a = Placed("cabinet", 0.0, 0.0, 20.0, 15.0, 0.0, 16.0, 80.0)
    b = Placed("cabinet", 60.0, 0.0, 20.0, 15.0, 0.0, 16.0, 80.0)
    assert CoPlanar("north").holds(a, b)
    assert CoPlanar("south").holds(a, b)


def test_a_cabinet_out_of_line_is_reported_with_the_offset() -> None:
    a = Placed("cabinet", 0.0, 0.0, 20.0, 15.0, 0.0, 16.0, 80.0)
    b = Placed("cabinet", 60.0, 9.0, 20.0, 15.0, 0.0, 16.0, 80.0)
    broken = CoPlanar("north").check(a, b)
    assert broken is not None and broken.amount == pytest.approx(9.0)


def test_coplanar_compares_heights_too() -> None:
    low = Placed("crate", 0.0, 0.0, 20.0, 20.0, 0.0, 16.0, 48.0)
    high = Placed("crate", 60.0, 0.0, 20.0, 20.0, 0.0, 16.0, 64.0)
    assert CoPlanar("bottom").holds(low, high)
    assert not CoPlanar("top").holds(low, high)


def test_an_unknown_side_is_a_mistake_not_a_pass() -> None:
    a = Placed("crate", 0.0, 0.0, 20.0, 20.0, 0.0, 16.0, 48.0)
    with pytest.raises(ValueError):
        CoPlanar("sideways").check(a, a)


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_the_hash_is_the_same_in_every_process() -> None:
    """``hash()`` is salted per process, which would move the props each run."""
    assert unit_hash("lobby", 3) == pytest.approx(0.6540129302235478)
    assert 0.0 <= unit_hash("anything", 1, 2.5) < 1.0
    assert unit_hash("a", 1) != unit_hash("a", 2)
