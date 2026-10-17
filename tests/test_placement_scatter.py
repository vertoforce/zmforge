"""The scatter stack: generators put points where they say, negatives cut them.

Two properties are worth more than the rest here and most of this file is
about them.

The first is that a generator's promise survives the whole stack.  A wall band
is a band of a stated depth, and a wall row stops a stated distance short of
the corner (so two perpendicular rows cannot meet in it), and a jitter on top of them moves a point by no more
than its own radius, so both promises still hold at the end.

The second is that a dropped candidate is attributable.  A run that says
"eight dropped" is a run nobody raises a count on; a run that says "eight
dropped: doorway 5, riser 3" is one somebody can act on.  So every drop here
is checked against the reason that caused it, not just against the total.
"""

from __future__ import annotations

import math

import pytest

from zmforge.placement.geometry import Poly2, unit_hash
from zmforge.placement.scatter import (
    CORNER_SETBACK,
    RISER_KEEP_OUT,
    AlongWall,
    Candidate,
    Clusters,
    Context,
    FaceAway,
    FaceTarget,
    FaceWall,
    Jitter,
    KeepClear,
    Negatives,
    Rows,
    SnapToSurface,
    Stack,
    UniformFill,
)

#: A small room to scatter in, in world units: 400 by 300, cornered at the
#: origin so a failure prints coordinates anybody can check by hand.
ROOM = (0.0, 0.0, 400.0, 300.0)


def _angle_gap(first: float, second: float) -> float:
    """How far apart two headings are, in degrees, the short way round."""
    return abs((first - second + 180.0) % 360.0 - 180.0)


# -- generators -------------------------------------------------------------
def test_along_wall_puts_every_point_in_the_band():
    points = AlongWall(*ROOM, spacing=100.0, depth=48.0).generate("lobby")
    assert points
    for point in points:
        if point.tag == "west":
            assert point.x == pytest.approx(24.0)
        elif point.tag == "east":
            assert point.x == pytest.approx(376.0)
        elif point.tag == "south":
            assert point.y == pytest.approx(24.0)
        else:
            assert point.y == pytest.approx(276.0)


def test_along_wall_stops_one_footprint_short_of_the_corner():
    # A row that cannot reach the corner cannot meet the row on the
    # perpendicular wall, so the two cannot drive a desk through a bench.
    points = AlongWall(*ROOM, spacing=100.0).generate("lobby")
    for point in points:
        run, low, high = (
            (point.y, ROOM[1], ROOM[3]) if point.tag in ("west", "east")
            else (point.x, ROOM[0], ROOM[2])
        )
        assert run >= low + CORNER_SETBACK
        assert run <= high - CORNER_SETBACK


def test_along_wall_gives_a_wall_shorter_than_its_setbacks_no_points():
    # An 80-unit wall has no part of it a piece of furniture can stand against
    # without being in a corner, so it gets nothing rather than one point in
    # the middle of two corners.
    narrow = AlongWall(0.0, 0.0, 400.0, 80.0, spacing=100.0, sides=("west", "east"))
    assert narrow.generate("lobby") == ()


def test_along_wall_faces_into_the_room_and_honours_the_side_list():
    points = AlongWall(*ROOM, spacing=100.0, sides=("south",)).generate("lobby")
    assert {point.tag for point in points} == {"south"}
    # The south wall's normal points north, which is yaw 90.
    assert all(point.yaw == pytest.approx(90.0) for point in points)


def test_along_wall_needs_a_positive_spacing():
    with pytest.raises(ValueError):
        AlongWall(*ROOM, spacing=0.0).generate("lobby")


def test_uniform_fill_makes_its_count_inside_the_rectangle():
    points = UniformFill(*ROOM, count=40, margin=20.0).generate("yard")
    assert len(points) == 40
    for point in points:
        assert 20.0 <= point.x <= 380.0
        assert 20.0 <= point.y <= 280.0


def test_clusters_keep_their_members_together_and_inside_the_rectangle():
    points = Clusters(*ROOM, clusters=3, per_cluster=5, radius=40.0).generate("yard")
    assert len(points) == 15
    inside = Poly2.rect(*ROOM)
    for point in points:
        assert inside.holds(point.point)
    for group in ("0", "1", "2"):
        members = [point for point in points if point.tag == group]
        assert len(members) == 5
        spread = max(
            math.dist(a.point, b.point) for a in members for b in members
        )
        assert spread <= 2.0 * 40.0


def test_rows_space_their_count_evenly_between_the_ends():
    points = Rows(0.0, 0.0, 300.0, 0.0, count=4).generate("aisle")
    assert [point.x for point in points] == pytest.approx([0.0, 100.0, 200.0, 300.0])
    assert all(point.y == pytest.approx(0.0) for point in points)


def test_a_row_of_one_lands_on_its_first_end_and_faces_along_the_line():
    # The existing ``Row`` does this, and a scene converted to this generator
    # must not move.
    single = Rows(10.0, 20.0, 300.0, 20.0, count=1).generate("aisle")
    assert (single[0].x, single[0].y) == (10.0, 20.0)
    up = Rows(0.0, 0.0, 0.0, 100.0, count=2).generate("aisle")
    assert all(point.yaw == pytest.approx(90.0) for point in up)


def test_a_generator_gives_the_same_points_for_the_same_seed_and_not_for_another():
    fill = UniformFill(*ROOM, count=25)
    assert fill.generate("lobby") == fill.generate("lobby")
    assert fill.generate("lobby") != fill.generate("boiler")


# -- modifiers --------------------------------------------------------------
def test_jitter_never_moves_a_point_further_than_its_radius():
    before = UniformFill(*ROOM, count=60).generate("yard")
    after = Jitter(radius=12.0, yaw=8.0).apply(before, Context(seed_text="yard"))
    assert len(after) == len(before)
    for start, end in zip(before, after):
        assert math.dist(start.point, end.point) <= 12.0 + 1e-9
        assert _angle_gap(start.yaw, end.yaw) <= 8.0 + 1e-9


def test_jitter_is_a_hash_and_not_a_die():
    points = UniformFill(*ROOM, count=20).generate("yard")
    jitter = Jitter(radius=12.0)
    once = jitter.apply(points, Context(seed_text="yard"))
    assert once == jitter.apply(points, Context(seed_text="yard"))
    assert once != jitter.apply(points, Context(seed_text="boiler"))


def test_face_target_turns_each_candidate_at_the_target():
    points = (
        Candidate(x=0.0, y=0.0, index=0),
        Candidate(x=0.0, y=0.0, index=1),
        Candidate(x=0.0, y=100.0, index=2),
    )
    turned = FaceTarget(x=100.0, y=0.0).apply(points, Context())
    assert turned[0].yaw == pytest.approx(0.0)
    assert turned[2].yaw == pytest.approx(-45.0)
    # A candidate standing on the target keeps the heading it had.
    assert FaceTarget(x=0.0, y=0.0).apply(points, Context())[0] == points[0]


def test_face_wall_and_face_away_pick_the_same_wall_and_opposite_headings():
    # Nearer the west wall (30) than the south wall (120), so both modifiers
    # are talking about the west wall.
    point = (Candidate(x=30.0, y=120.0),)
    toward = FaceWall(*ROOM).apply(point, Context())[0].yaw
    away = FaceAway(*ROOM).apply(point, Context())[0].yaw
    assert away == pytest.approx(0.0)  # the west wall's normal points east
    assert _angle_gap(toward, away) == pytest.approx(180.0)


def test_snap_to_surface_sets_the_height_and_drops_what_has_none():
    # The yard's terrain mesh stops short of the interior: x above 250 here is
    # off the slab, which is the shape of the real 31 floating props.
    def height_of(x: float, y: float) -> float | None:
        return None if x > 250.0 else 16.0

    points = Rows(0.0, 0.0, 400.0, 0.0, count=5).generate("yard")
    landed = SnapToSurface(height_of).apply(points, Context())
    assert [point.x for point in landed] == pytest.approx([0.0, 100.0, 200.0])
    assert all(point.z == pytest.approx(16.0) for point in landed)
    kept = SnapToSurface(height_of, keep_missing=True).apply(points, Context())
    assert len(kept) == 5


# -- negative shapes --------------------------------------------------------
def test_a_keep_clear_blocks_a_point_inside_it_and_a_footprint_that_clips_it():
    door = KeepClear.rect("doorway", 100.0, 0.0, 180.0, 60.0)
    assert door.blocks((140.0, 30.0))
    assert not door.blocks((240.0, 30.0))
    # A shelving unit standing beside the door with its bulk across it is the
    # case a centre-point test misses, and enough of them hide a door.
    beside = Poly2.box(200.0, 30.0, 40.0, 10.0)
    assert not door.blocks((200.0, 30.0))
    assert door.blocks(beside)


def test_a_keep_clear_disc_covers_the_ground_around_a_riser():
    riser = KeepClear.disc("riser", 0.0, 0.0, RISER_KEEP_OUT)
    assert riser.blocks((0.0, 0.0))
    assert riser.blocks((80.0, 0.0))
    assert not riser.blocks((0.0, 120.0))


def test_a_keep_clear_with_a_height_band_ignores_what_is_above_it():
    under_pipes = KeepClear.rect("pipe run", 0.0, 0.0, 100.0, 100.0,
                                 z_low=0.0, z_high=40.0)
    assert under_pipes.blocks((50.0, 50.0), z_low=0.0, z_high=32.0)
    assert not under_pipes.blocks((50.0, 50.0), z_low=100.0, z_high=140.0)
    # No band given is an unknown height, and an unknown height is not a safe
    # height.
    assert under_pipes.blocks((50.0, 50.0))


def test_negatives_return_the_zone_that_blocked_so_the_reason_survives():
    zones = Negatives.of((
        KeepClear.rect("doorway", 0.0, 0.0, 50.0, 50.0),
        KeepClear.rect("stairs", 200.0, 0.0, 300.0, 100.0),
    ))
    assert zones.blocks((25.0, 25.0)).reason == "doorway"
    assert zones.blocks((250.0, 50.0)).reason == "stairs"
    assert zones.blocks((150.0, 150.0)) is None
    assert len(zones) == 2
    assert zones.reasons() == ("doorway", "stairs")


# -- the stack --------------------------------------------------------------
def test_a_negative_shape_removes_exactly_the_candidates_inside_it():
    fill = UniformFill(*ROOM, count=60, tag="litter")
    door = KeepClear.rect("doorway", 120.0, 0.0, 220.0, 120.0)
    expected = [p for p in fill.generate("lobby") if not door.blocks(p.point)]
    assert 0 < len(expected) < 60  # the zone has to matter for this to test it

    result = Stack(generators=(fill,), negatives=Negatives((door,))).run("lobby")
    assert list(result.candidates) == expected
    assert result.report.dropped_by == {"doorway": 60 - len(expected)}
    assert result.report.kept == len(expected)


def test_the_report_counts_what_each_generator_made_and_each_reason_dropped():
    stack = Stack(
        generators=(
            AlongWall(*ROOM, spacing=100.0, tag="wall band"),
            UniformFill(*ROOM, count=30, tag="litter"),
        ),
        modifiers=(SnapToSurface(lambda x, y: None if y > 260.0 else 16.0),),
        negatives=Negatives((KeepClear.rect("doorway", 120.0, 0.0, 220.0, 120.0),)),
    )
    result = stack.run("lobby")
    report = result.report

    assert report.made_by["wall band"] == 14
    assert report.made_by["litter"] == 30
    assert report.total_made == 44
    assert set(report.dropped_by) == {"no surface", "doorway"}
    assert report.kept == len(result.candidates)
    assert report.total_made - report.total_dropped == report.kept
    assert str(report).startswith(f"{report.kept} kept from")


def test_the_negatives_judge_where_a_candidate_ended_up_not_where_it_started():
    # A jitter after the keep-out check is how a prop ends up in a doorway it
    # was checked out of, so the check runs last, on final positions.
    at_the_edge = Rows(90.0, 60.0, 90.0, 60.0, count=1, tag="row")
    door = KeepClear.rect("doorway", 100.0, 0.0, 220.0, 120.0)
    assert not door.blocks(at_the_edge.generate("booth")[0].point)
    # This seed's jitter pushes that point from x=90 to x=105, which is inside
    # the doorway; a stack that checked before the jitter would keep it.
    moved = Jitter(radius=40.0, yaw=0.0).apply(
        at_the_edge.generate("booth"), Context(seed_text="booth")
    )[0]
    assert door.blocks(moved.point)

    nudged = Stack(
        generators=(at_the_edge,),
        modifiers=(Jitter(radius=40.0, yaw=0.0),),
        negatives=Negatives((door,)),
    ).run("booth")
    assert nudged.candidates == ()
    assert nudged.report.dropped_by == {"doorway": 1}


def test_the_same_stack_and_seed_build_the_same_layout_every_time():
    stack = Stack(
        generators=(AlongWall(*ROOM, spacing=90.0, tag="band"),
                    Clusters(*ROOM, clusters=2, per_cluster=4, radius=30.0, tag="mess")),
        modifiers=(Jitter(radius=10.0), FaceTarget(x=200.0, y=150.0)),
        negatives=Negatives((KeepClear.disc("riser", 200.0, 150.0, RISER_KEEP_OUT),)),
    )
    first = stack.run("lobby")
    assert first.candidates == stack.run("lobby").candidates
    assert first.report == stack.run("lobby").report
    assert first.candidates != stack.run("boiler").candidates
    # And the whole thing is a hash of the seed, not of a global stream.
    assert unit_hash("lobby", "band", 0, "x") == unit_hash("lobby", "band", 0, "x")
