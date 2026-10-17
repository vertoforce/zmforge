"""A model family is placed whole or not at all, and says why when it is not.

The family under test is the one most often found half placed: a desk
with a chair tucked under it.  When the desk and the chair are two
independent entries in a list and each is checked on its own, the desk
(``p7_desk_metal_old_01_body``) can land 72% inside a bench and the chair
(``p7_chair_waiting_room_01_blue``) 98% inside a plant.

So the cases here are the ones that distinguish "checked as a unit" from
"checked one at a time": the chair is allowed to share floor with its own
desk, it is not allowed to share floor with a bench, and when it does the
desk does not get placed either even though the desk alone would have fitted.
"""

from __future__ import annotations

import math

import pytest

from zmforge.placement.relations import NoOverlap, Placed
from zmforge.placement.scatter import Candidate, KeepClear, Negatives
from zmforge.placement.groups import (
    Group,
    GroupPlacement,
    Member,
    first_fit,
    instantiate,
    internal_violations,
    place_group,
    try_group,
)

#: A 90 by 40 desk -- a size that overhangs a 40-deep counter with none of
#: its four corners on it -- and a 24 by 24 chair tucked under its
#: near edge.  The chair overlaps the
#: desk's footprint by three quarters of its own, on purpose: that is what
#: "tucked under" means and it is the case a stranger check would reject.
DESK = Member("p7_desk_metal_old_01_body", hx=45.0, hy=20.0, z_low=0.0, z_high=40.0)
CHAIR = Member("p7_chair_waiting_room_01_blue", dy=-14.0, hx=12.0, hy=12.0,
               z_low=0.0, z_high=45.0)
WORKSTATION = Group("workstation", (DESK, CHAIR), touching=(("p7_desk_metal_old_01_body",
                                                             "p7_chair_waiting_room_01_blue"),))


#: Where the bench stands in these tests, in units behind the group's origin.
#: Far enough back that its front face is exactly on the desk's back edge, so
#: the desk is clear of it and only the chair is not.  That is the point of the
#: whole file: one member fails, the family does not get placed.
BENCH_OFFSET = -30.0


def _bench(x: float, y: float = BENCH_OFFSET) -> Placed:
    """A 60 by 20 bench standing on the floor, as an obstacle."""
    return Placed("p7_bench_modern_01", x, y, 30.0, 10.0, z_low=0.0, z_high=18.0)


# -- the family itself ------------------------------------------------------
def test_every_member_lands_at_the_group_position_turned_by_the_group_yaw():
    placement = instantiate(WORKSTATION, (100.0, 200.0), 90.0)
    desk = placement.member("p7_desk_metal_old_01_body")
    chair = placement.member("p7_chair_waiting_room_01_blue")
    assert (desk.x, desk.y) == (100.0, 200.0)
    # The chair's offset is turned with the group: 14 behind the desk becomes
    # 14 to the east once the whole thing is turned a quarter turn.
    assert (chair.x, chair.y) == pytest.approx((114.0, 200.0))
    assert chair.yaw == pytest.approx(90.0)


def test_member_heights_are_measured_from_the_group_base():
    on_a_plinth = instantiate(WORKSTATION, (0.0, 0.0), base_z=64.0)
    assert on_a_plinth.z_low == pytest.approx(64.0)
    assert on_a_plinth.z_high == pytest.approx(109.0)
    assert on_a_plinth.member("p7_desk_metal_old_01_body").z_high == pytest.approx(104.0)


def test_a_group_footprint_covers_every_member():
    placement = instantiate(WORKSTATION, (0.0, 0.0))
    hull = placement.footprint
    for member in placement.members:
        for corner in member.footprint.points:
            assert hull.holds(corner, tolerance=1e-6)


def test_a_group_will_not_hold_two_members_under_one_label():
    # A frame with four identical treads is five members and four repeats of
    # one model name, so the repeats need a part label to be talked about.
    tread = Member("p7_pallet_metal_military_01", hx=33.0, hy=17.5)
    with pytest.raises(ValueError, match="more than one member"):
        Group("shelf", (tread, tread))
    named = Group("shelf", (
        Member("p7_pallet_metal_military_01", hx=33.0, hy=17.5, part="tread_1"),
        Member("p7_pallet_metal_military_01", dy=40.0, hx=33.0, hy=17.5, part="tread_2"),
    ))
    assert named.labels == ("tread_1", "tread_2")


def test_a_group_will_not_declare_a_touching_pair_it_does_not_have():
    with pytest.raises(ValueError, match="not a member"):
        Group("workstation", (DESK,), touching=(("p7_desk_metal_old_01_body", "lamp"),))


# -- members against each other ---------------------------------------------
def test_a_chair_tucked_under_its_own_desk_is_allowed():
    placement = instantiate(WORKSTATION, (0.0, 0.0))
    desk = placement.member("p7_desk_metal_old_01_body")
    chair = placement.member("p7_chair_waiting_room_01_blue")
    # They really do interpenetrate: this is not a pair that passes by accident.
    shared = desk.footprint.overlap_area(chair.footprint)
    assert shared / chair.footprint.area == pytest.approx(0.75)
    assert NoOverlap().check(chair, desk) is not None
    # And the group says so, so the group check passes.
    assert internal_violations(WORKSTATION, placement) == ()
    assert try_group(WORKSTATION, (0.0, 0.0)).ok


def test_two_members_the_group_did_not_declare_are_held_apart_like_strangers():
    # The same two models, with the touching declaration left off: a family
    # whose offsets were typed wrong fails its own check instead of shipping.
    undeclared = Group("workstation", (DESK, CHAIR))
    attempt = try_group(undeclared, (0.0, 0.0))
    assert not attempt.ok
    assert [violation.relation for violation in attempt.violations] == ["GroupInternal"]
    assert "part of workstation" in attempt.violations[0].detail
    assert place_group(undeclared, (0.0, 0.0)) is None


def test_a_plank_on_top_of_its_frame_needs_no_declaration_but_one_inside_it_does():
    # A plank resting on the top of the frame shares no height with it, and
    # NoOverlap already reads that as one thing standing on another.  A plank
    # at mid height is inside the frame, shares 2 units of height with it, and
    # has to be declared -- which is the shelving-frame-without-planks case
    # stated as a rule rather than as a hope.
    frame = Member("p7_shelf_frame", hx=30.0, hy=12.0, z_low=0.0, z_high=36.0, part="frame")
    on_top = Member("p7_shelf_plank", hx=28.0, hy=11.0, z_low=36.0, z_high=38.0, part="plank")
    assert try_group(Group("shelving", (frame, on_top)), (0.0, 0.0)).ok

    tall = Member("p7_shelf_frame", hx=30.0, hy=12.0, z_low=0.0, z_high=72.0, part="frame")
    assert not try_group(Group("shelving", (tall, on_top)), (0.0, 0.0)).ok
    declared = Group("shelving", (tall, on_top), touching=(("plank", "frame"),))
    assert try_group(declared, (0.0, 0.0)).ok


# -- members against the world ----------------------------------------------
def test_a_group_whose_chair_hits_a_bench_is_rejected_whole():
    # The bench's front face is exactly on the desk's back edge, so the desk
    # is clear of it, and it takes a quarter of the chair's footprint at a
    # height they share.  These are the stock models themselves.
    bench = _bench(0.0)
    assert NoOverlap().check(instantiate(WORKSTATION, (0.0, 0.0)).member(
        "p7_desk_metal_old_01_body"), bench) is None

    attempt = try_group(WORKSTATION, (0.0, 0.0), obstacles=(bench,))
    assert not attempt.ok
    assert [violation.subject for violation in attempt.violations] == [
        "p7_chair_waiting_room_01_blue"
    ]
    # The desk would have fitted on its own and is not placed anyway.  The
    # obstacles arrive as a one-shot iterator here on purpose: every member has
    # to be checked against every obstacle, not just the first member.
    assert place_group(WORKSTATION, (0.0, 0.0), obstacles=iter((bench,))) is None
    assert "p7_chair_waiting_room_01_blue" in attempt.why()


def test_a_group_clear_of_everything_is_placed_with_all_of_its_members():
    placement = place_group(WORKSTATION, (500.0, 500.0), obstacles=(_bench(0.0),))
    assert isinstance(placement, GroupPlacement)
    assert len(placement.members) == len(WORKSTATION.members)
    assert {member.name for member in placement.members} == {
        "p7_desk_metal_old_01_body", "p7_chair_waiting_room_01_blue"
    }


def test_a_member_inside_a_keep_clear_zone_rejects_the_group_with_the_reason():
    door = KeepClear.rect("doorway", 40.0, -60.0, 140.0, 60.0)
    attempt = try_group(WORKSTATION, (0.0, 0.0), negatives=Negatives((door,)))
    assert not attempt.ok
    reasons = {violation.target for violation in attempt.violations}
    assert reasons == {"doorway"}
    assert attempt.violations[0].relation == "KeepClear"
    # A plain sequence of zones works as well as a Negatives, so a caller does
    # not have to wrap one zone to ask one question.
    assert place_group(WORKSTATION, (0.0, 0.0), negatives=(door,)) is None


def test_a_keep_clear_with_a_height_band_lets_a_group_stand_above_it():
    cabling = KeepClear.rect("cable trench", -100.0, -100.0, 100.0, 100.0,
                             z_low=-24.0, z_high=-2.0)
    assert place_group(WORKSTATION, (0.0, 0.0), negatives=(cabling,)) is not None
    assert place_group(WORKSTATION, (0.0, 0.0), base_z=-20.0, negatives=(cabling,)) is None


# -- first fit --------------------------------------------------------------
def test_first_fit_takes_the_first_spot_the_whole_group_clears():
    bench = _bench(0.0)
    spots = ((0.0, 0.0), (0.0, 0.0, 0.0), (400.0, 0.0), (800.0, 0.0))
    placement = first_fit(WORKSTATION, spots, obstacles=(bench,))
    assert placement is not None
    assert (placement.x, placement.y) == (400.0, 0.0)


def test_first_fit_gives_nothing_back_when_no_spot_clears():
    blocked = tuple(_bench(x) for x in (0.0, 400.0, 800.0))
    assert first_fit(WORKSTATION, ((0.0, 0.0), (400.0, 0.0), (800.0, 0.0)),
                     obstacles=blocked) is None


def test_first_fit_reads_a_scatter_candidate_including_its_snapped_height():
    # A Candidate is a spot: x, y, yaw and the height SnapToSurface wrote.
    spots = (
        Candidate(x=0.0, y=0.0, yaw=0.0, z=0.0),
        Candidate(x=400.0, y=0.0, yaw=90.0, z=64.0),
    )
    placement = first_fit(WORKSTATION, spots, obstacles=(_bench(0.0),))
    assert placement is not None
    assert (placement.x, placement.y, placement.yaw) == (400.0, 0.0, 90.0)
    assert placement.base_z == pytest.approx(64.0)
    assert placement.member("p7_desk_metal_old_01_body").z_low == pytest.approx(64.0)
    # Turned a quarter turn, the 90-long desk is 90 deep, which is the thing
    # the group has to get right for the obstacle test to mean anything.
    x0, y0, x1, y1 = placement.member("p7_desk_metal_old_01_body").footprint.bounds
    assert math.isclose(y1 - y0, 90.0, abs_tol=1e-6)
    assert math.isclose(x1 - x0, 40.0, abs_tol=1e-6)
