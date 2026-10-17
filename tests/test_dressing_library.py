"""The public dressing API: the placers agree with each
other, and the litter strewers are seeded and honour their tests."""

import random
from types import SimpleNamespace

import pytest

from zmforge.dressing import (
    litter_by_weight,
    litter_in_drifts,
    mounted,
    on_floor,
    on_room_wall,
    on_wall,
    rest_on,
    turned_box,
)
from zmforge.spatial import Bounds, Facing, Point

SIGN = "p7_cai_signage_plastic_exit"
CUP = "p7_debris_trash_cup_coffee_02"


def test_on_room_wall_is_on_wall_on_the_room_plane():
    room = SimpleNamespace(interior=Bounds.between((-100.0, -50.0, 0.0), (300.0, 250.0, 128.0)),
                           floor_z=0.0)
    for wall, facing, plane in (("w", Facing.EAST, -100.0), ("e", Facing.WEST, 300.0),
                                ("s", Facing.NORTH, -50.0), ("n", Facing.SOUTH, 250.0)):
        assert on_room_wall(SIGN, room, wall, 10.0, 100.0) == on_wall(
            SIGN, facing, 10.0, plane, bottom_z=100.0)


def test_on_wall_puts_the_turned_back_on_the_wall():
    model, origin, yaw = on_wall(SIGN, Facing.EAST, 0.0, 40.0, centre_z=64.0, gap=0.5)
    assert yaw == mounted(SIGN, Point(0.0, 0.0, 0.0), Facing.EAST)[2]
    x0, _y0, _x1, _y1 = turned_box(model, yaw)
    assert origin.x + x0 == pytest.approx(40.5)


def test_on_wall_needs_exactly_one_height():
    with pytest.raises(ValueError):
        on_wall(SIGN, Facing.EAST, 0.0, 40.0)
    with pytest.raises(ValueError):
        on_wall(SIGN, Facing.EAST, 0.0, 40.0, centre_z=1.0, bottom_z=1.0)


def test_on_floor_rests_the_underside_on_the_floor():
    assert on_floor(CUP, 0.0, 0.0, 16.0)[1].z == rest_on(CUP, 16.0)


def test_litter_is_seeded_spaced_and_kept_out():
    drifts = [(0.0, 0.0, 60.0, 60.0, 8), (200.0, 0.0, 30.0, 30.0, 4)]
    keep = [(0.0, 0.0, 20.0)]
    a = litter_in_drifts(random.Random(7), drifts, [CUP], 0.0, keep=keep, spacing=11.0)
    b = litter_in_drifts(random.Random(7), drifts, [CUP], 0.0, keep=keep, spacing=11.0)
    assert a == b and len(a) == 12
    weighted = litter_by_weight(random.Random(7), drifts, 10, [CUP], 0.0,
                                accept=lambda x, y: y > -40.0)
    assert len(weighted) == 10
    for items in (a, weighted):
        for model, *_ in items:
            assert model == CUP
    assert all(spec[4] is False for spec in a + weighted)
