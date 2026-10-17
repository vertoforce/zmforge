"""Clearance, circulation and emphasis: does the shape match the geometry?

Every test here is on a synthetic room of a few hundred units, because that is
the size the real thing runs at and because a hand-checkable room is the only
way to tell a circulation bug from a rasterisation bug.  The clearance
assertions are against the closed form -- a convex shape grown by a disc of
radius ``r`` has area ``A + P*r + pi*r^2`` (Steiner) -- rather than against
numbers this module printed once, so an approximation that drifts fails here
instead of silently shrinking every prop's clearance.

No recipe or map check calls :mod:`zmforge.placement.clearance`, so these
tests are the only checks it has.
"""

from __future__ import annotations

import math

import pytest

from zmforge.placement.clearance import (
    CIRCULATION_CELL,
    DRAW_WEIGHT,
    FRONT_APRON,
    ClearanceKind,
    Draw,
    FreeFloor,
    Link,
    clearance_of,
    clearance_polygon,
    focal_point_of,
    focus_score,
)
from zmforge.placement.relations import PLAYER_RADIUS, Placed

ROOM = (0.0, 0.0, 320.0, 320.0)


def _desk(yaw: float = 0.0, **kwargs) -> Placed:
    """A 100 x 60 desk at the origin: the shape half these tests grow."""
    return Placed("desk", 0.0, 0.0, 50.0, 30.0, yaw, **kwargs)


def _steiner(area: float, perimeter: float, radius: float) -> float:
    return area + perimeter * radius + math.pi * radius * radius


def _wall_of_props(gap: bool) -> list[Placed]:
    """Five 64 x 16 props across the room at y 160, optionally missing the middle.

    Grown by the 15-unit player disc each one covers 94 units of width, so the
    five overlap and seal the room; with the middle one gone the hole is 34
    units of floor, wider than the 16-unit grid and wider than a player.
    """
    return [
        Placed(f"crate{i}", x, 160.0, 32.0, 8.0)
        for i, x in enumerate((32.0, 96.0, 160.0, 224.0, 288.0))
        if not (gap and x == 160.0)
    ]


# --------------------------------------------------------------------------
# The clearance shape
# --------------------------------------------------------------------------
def test_the_disc_sum_is_bigger_than_the_raw_footprint():
    desk = _desk()
    assert clearance_polygon(desk).area > desk.footprint.area


def test_the_disc_sum_matches_the_steiner_area():
    grown = clearance_polygon(_desk())
    expected = _steiner(6000.0, 320.0, PLAYER_RADIUS)
    assert grown.area == pytest.approx(expected, rel=0.03)


def test_a_rotated_footprint_keeps_its_rotation():
    grown = clearance_polygon(_desk(yaw=30.0))
    # Same area as the unrotated one: growing by a disc is rotation invariant.
    assert grown.area == pytest.approx(_steiner(6000.0, 320.0, PLAYER_RADIUS), rel=0.03)
    # But not the same shape: the 100-unit side now runs diagonally, so the
    # axis-aligned bounds are wider and deeper than the unrotated 130 x 90.
    x0, y0, x1, y1 = grown.bounds
    assert x1 - x0 == pytest.approx(2 * (50 * math.cos(math.radians(30))
                                         + 30 * math.sin(math.radians(30))) + 30, abs=1.0)
    assert y1 - y0 > 90.0


def test_the_corners_come_back_rounded_not_squared():
    grown = clearance_polygon(_desk())
    # Straight out from a side at exactly the player radius: inside.
    assert grown.holds((50.0 + PLAYER_RADIUS - 0.5, 0.0))
    # Diagonally off the corner at 17 units, further than the radius: outside,
    # though a grown bounding box (65 x 45) would hold it.
    assert not grown.holds((62.0, 42.0))


def test_a_zero_radius_leaves_the_footprint_alone():
    desk = _desk()
    assert clearance_polygon(desk, radius=0.0).area == pytest.approx(desk.footprint.area)


def test_the_front_apron_only_grows_the_front():
    plain = clearance_polygon(_desk()).bounds
    fronted = clearance_polygon(_desk(), front=48.0).bounds
    assert fronted[2] == pytest.approx(plain[2] + 48.0)  # +x, the way it faces
    assert fronted[0] == pytest.approx(plain[0])
    assert fronted[1] == pytest.approx(plain[1])
    assert fronted[3] == pytest.approx(plain[3])


def test_the_front_apron_follows_the_yaw():
    plain = clearance_polygon(_desk(yaw=90.0)).bounds
    fronted = clearance_polygon(_desk(yaw=90.0), front=48.0).bounds
    assert fronted[3] == pytest.approx(plain[3] + 48.0)  # +y at yaw 90
    assert fronted[2] == pytest.approx(plain[2])


def test_front_yaw_overrides_the_subjects_own_yaw():
    # A model whose measured front is not its yaw: MODEL_FRONT is -90 for
    # every chair in the palette, so the apron has to go the other way.
    plain = clearance_polygon(_desk()).bounds
    fronted = clearance_polygon(_desk(), front=48.0, front_yaw=-90.0).bounds
    assert fronted[1] == pytest.approx(plain[1] - 48.0)  # -y
    assert fronted[2] == pytest.approx(plain[2])


def test_the_apron_table_orders_the_kinds():
    areas = {kind: clearance_of(_desk(), kind).area for kind in ClearanceKind}
    assert (areas[ClearanceKind.INTERACTIVE] > areas[ClearanceKind.SEAT]
            > areas[ClearanceKind.SURFACE] > areas[ClearanceKind.PLAIN])
    assert FRONT_APRON[ClearanceKind.INTERACTIVE] == 48.0  # DOOR_FACE_CLEAR
    assert FRONT_APRON[ClearanceKind.PLAIN] == 0.0


def test_a_plain_kind_is_the_disc_alone():
    assert clearance_of(_desk(), "plain").points == clearance_polygon(_desk()).points


def test_a_kind_can_be_named_by_string_and_a_bad_name_raises():
    assert ClearanceKind.of("seat") is ClearanceKind.SEAT
    assert ClearanceKind.of(ClearanceKind.SEAT) is ClearanceKind.SEAT
    with pytest.raises(ValueError, match="not a clearance kind"):
        ClearanceKind.of("sideboard")


def test_a_caller_can_override_the_apron_table():
    mine = {ClearanceKind.INTERACTIVE: 96.0}
    wide = clearance_of(_desk(), "interactive", aprons=mine).bounds
    default = clearance_of(_desk(), "interactive").bounds
    assert wide[2] == pytest.approx(default[2] + 48.0)
    with pytest.raises(ValueError, match="no apron"):
        clearance_of(_desk(), "seat", aprons=mine)


# --------------------------------------------------------------------------
# Circulation
# --------------------------------------------------------------------------
def test_an_open_room_is_one_component():
    floor = FreeFloor.of([ROOM])
    assert floor.cell == CIRCULATION_CELL
    assert (floor.nx, floor.ny) == (20, 20)
    assert floor.components() == 1
    assert floor.free_area == pytest.approx(320.0 * 320.0)


def test_a_wall_of_props_splits_the_room_in_two():
    floor = FreeFloor.of_placed([ROOM], _wall_of_props(gap=False))
    assert floor.components() == 2
    areas = floor.component_areas()
    assert len(areas) == 2
    assert areas[0] >= areas[1] > 0.0
    assert sum(areas) == pytest.approx(floor.free_area)


def test_opening_a_gap_in_the_wall_joins_the_room_again():
    assert FreeFloor.of_placed([ROOM], _wall_of_props(gap=True)).components() == 1


def test_a_required_link_across_the_split_fails_and_names_itself():
    floor = FreeFloor.of_placed([ROOM], _wall_of_props(gap=False))
    link = Link("spawn to buy", (160.0, 40.0), (160.0, 280.0))
    result = floor.links_ok([link])
    assert not result.ok
    assert result.broken == ("spawn to buy",)
    assert "cut off" in result.faults[0].detail
    assert result.faults[0].relation == "Circulation"
    # The amount is the floor still reachable from the link's first end:
    # nine of the twenty rows, 20 cells of 16 x 16 each.
    assert result.faults[0].amount == pytest.approx(9 * 20 * 256.0)
    assert result.components == 2


def test_the_same_link_passes_once_the_gap_is_open():
    floor = FreeFloor.of_placed([ROOM], _wall_of_props(gap=True))
    result = floor.links_ok([Link("spawn to buy", (160.0, 40.0), (160.0, 280.0))])
    assert result.ok
    assert result.broken == ()
    assert result.components == 1
    assert floor.reaches((160.0, 40.0), (160.0, 280.0))


def test_a_link_end_inside_a_clearance_is_reported_and_snapping_rescues_it():
    floor = FreeFloor.of_placed([ROOM], _wall_of_props(gap=True))
    buried = Link("buy", (32.0, 160.0), (160.0, 40.0))  # first end inside a crate
    assert "not on free floor" in floor.links_ok([buried]).faults[0].detail
    assert floor.links_ok([buried], snap=64.0).ok
    assert not floor.reaches(buried.a, buried.b)
    assert floor.reaches(buried.a, buried.b, snap=64.0)


def test_a_link_end_off_the_grid_is_reported():
    floor = FreeFloor.of([ROOM])
    result = floor.links_ok([Link("door", (-400.0, 160.0), (160.0, 160.0))])
    assert not result.ok
    assert "first end" in result.faults[0].detail


def test_two_rectangles_make_one_floor_and_a_gap_makes_two():
    joined = FreeFloor.of([(0.0, 0.0, 160.0, 160.0), (160.0, 0.0, 320.0, 160.0)])
    assert joined.components() == 1
    apart = FreeFloor.of([(0.0, 0.0, 160.0, 160.0), (200.0, 0.0, 320.0, 160.0)])
    assert apart.components() == 2


def test_component_areas_come_back_biggest_first_and_sum_to_the_free_area():
    floor = FreeFloor.of_placed([ROOM], _wall_of_props(gap=False))
    areas = floor.component_areas()
    assert list(areas) == sorted(areas, reverse=True)
    assert sum(areas) == pytest.approx(floor.free_cells * floor.cell_area)
    assert floor.free_area < 320.0 * 320.0  # the crates took floor away


def test_a_walk_through_prop_does_not_block_the_floor():
    ghosts = [
        Placed(prop.name, prop.x, prop.y, prop.hx, prop.hy, prop.yaw, solid=False)
        for prop in _wall_of_props(gap=False)
    ]
    assert FreeFloor.of_placed([ROOM], ghosts).components() == 1
    assert FreeFloor.of_placed([ROOM], ghosts, solid_only=False).components() == 2


def test_cells_answer_where_they_are():
    floor = FreeFloor.of([ROOM])
    assert floor.cell_at((0.0, 0.0)) == (0, 0)
    assert floor.centre_of(0, 0) == pytest.approx((8.0, 8.0))
    assert floor.cell_at((400.0, 0.0)) is None
    assert floor.is_free((160.0, 160.0))


def test_a_floor_needs_a_room_and_a_grid():
    with pytest.raises(ValueError, match="at least one room"):
        FreeFloor.of([])
    with pytest.raises(ValueError, match="not a grid"):
        FreeFloor.of([ROOM], cell=0.0)


# --------------------------------------------------------------------------
# Emphasis
# --------------------------------------------------------------------------
def test_the_score_is_one_facing_the_draw_and_zero_facing_away():
    chair = Placed("chair", 0.0, 0.0, 12.0, 12.0, 0.0)
    assert focus_score(chair, (200.0, 0.0)) == pytest.approx(1.0)
    assert focus_score(chair, (-200.0, 0.0)) == pytest.approx(0.0)


def test_the_score_falls_off_smoothly_as_the_seat_turns_away():
    chair = Placed("chair", 0.0, 0.0, 12.0, 12.0, 0.0)
    scores = [
        focus_score(chair.turned_to(yaw), (200.0, 0.0))
        for yaw in (0.0, 45.0, 90.0, 135.0, 180.0)
    ]
    assert scores == sorted(scores, reverse=True)
    assert scores[2] == pytest.approx(0.5)  # side on


def test_front_yaw_overrides_the_yaw_in_the_score():
    # A chair whose measured front is -90 from its yaw,
    # placed in a row that set the yaw from the line it stands on.
    chair = Placed("chair", 0.0, 0.0, 12.0, 12.0, 0.0)
    assert focus_score(chair, (0.0, -200.0)) == pytest.approx(0.5)
    assert focus_score(chair, (0.0, -200.0), front_yaw=-90.0) == pytest.approx(1.0)


def test_the_distance_term_halves_the_score_at_the_half_distance():
    chair = Placed("chair", 0.0, 0.0, 12.0, 12.0, 0.0)
    near = focus_score(chair, (100.0, 0.0), half_distance=100.0)
    far = focus_score(chair, (300.0, 0.0), half_distance=100.0)
    assert near == pytest.approx(0.5)
    assert far == pytest.approx(0.25)
    assert focus_score(chair, (300.0, 0.0)) == pytest.approx(1.0)  # off by default


def test_a_seat_standing_on_the_draw_scores_one_whichever_way_it_faces():
    chair = Placed("chair", 100.0, 100.0, 12.0, 12.0, 180.0)
    assert focus_score(chair, (100.0, 100.0)) == pytest.approx(1.0)


def test_the_focal_point_is_the_heaviest_draw():
    draws = [
        Draw.of_kind("window", 0.0, 320.0),
        Draw.of_kind("door", 160.0, 0.0),
        Draw.of_kind("buy", 320.0, 160.0),
    ]
    assert DRAW_WEIGHT["buy"] > DRAW_WEIGHT["door"] > DRAW_WEIGHT["window"]
    assert focal_point_of(*ROOM, draws).name == "buy"


def test_equal_draws_are_broken_by_distance_from_the_room_centre():
    draws = [Draw("middling buy", 200.0, 160.0, 3.0), Draw("corner buy", 0.0, 0.0, 3.0)]
    assert focal_point_of(*ROOM, draws).name == "corner buy"


def test_a_draw_in_another_room_is_not_this_rooms_focus():
    far = [Draw.of_kind("buy", 900.0, 160.0)]
    assert focal_point_of(*ROOM, far) is None
    # A wall buy sits on the wall plane, a few units outside the interior, and
    # still belongs to the room.
    assert focal_point_of(*ROOM, [Draw.of_kind("buy", 328.0, 160.0)]) is not None
    assert focal_point_of(*ROOM, []) is None


def test_the_focal_point_scores_the_room_it_came_from():
    draws = [Draw.of_kind("buy", 320.0, 160.0), Draw.of_kind("door", 160.0, 0.0)]
    focus = focal_point_of(*ROOM, draws)
    assert focus is not None
    facing = Placed("sofa", 100.0, 160.0, 40.0, 20.0, 0.0)
    assert focus_score(facing, focus.point) == pytest.approx(1.0)
    assert focus_score(facing.turned_to(180.0), focus.point) == pytest.approx(0.0)
