"""Respawn groups (blueprint.respawn) and their check, Z86.

The stock respawn pick reads ``struct::get_array( <respawn struct>.target,
"targetname" )`` (``_zm.gsc:3453``); with no target a bled-out player comes
back at their initial spawn.  Each test that exists to catch a defect breaks
the written map and asserts Z86 fires.
"""

from __future__ import annotations

import pytest

from zmforge.blueprint.elements import PlayerStart, Zone
from zmforge.blueprint.respawn import (
    PLAYER_HALF,
    STOCK_POINTS,
    _Ground,
    respawn_groups,
    target_name,
)
from zmforge.emit.mapfile import build_document
from zmforge.mapsource import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.recipes import three_room_map
from zmforge.verify.respawn_points import check_respawn_points


@pytest.fixture(scope="module")
def bp():
    return three_room_map("zm_respawn_test")


@pytest.fixture()
def document(bp):
    return parse_map_text(render_map_text(build_document(bp)))


def _structs(document, name):
    return [e for e in document.entities_of("script_struct") if e.value("targetname") == name]


def test_every_zone_gets_a_group_of_four_inside_it(bp) -> None:
    groups = {g.zone: g for g in respawn_groups(bp)}
    zones = {z.name: z for z in bp.elements(Zone)}
    assert set(groups) == set(zones)
    for name, group in groups.items():
        assert len(group.points) == STOCK_POINTS
        assert group.anchor == group.points[0]
        for p in group.points:
            assert zones[name].bounds.holds(p, tolerance=1.0)
        for i, a in enumerate(group.points):
            for b in group.points[i + 1:]:
                assert a.distance_to(b) >= 2 * PLAYER_HALF


def test_the_fast_floor_answers_as_the_model_does(bp) -> None:
    floor = _Ground(bp)
    for zone in bp.elements(Zone):
        b = zone.bounds
        for i in range(8):
            for j in range(8):
                x = b.mins.x + (b.maxs.x - b.mins.x) * (i + 0.5) / 8
                y = b.mins.y + (b.maxs.y - b.mins.y) * (j + 0.5) / 8
                model = bp.ground_under(x, y, below=b.maxs.z - 72.0)
                fast = floor.under(x, y, b.maxs.z - 72.0)
                assert model.found == (fast is not None)
                if fast is not None:
                    assert fast[0] == pytest.approx(model.z)


def test_the_written_map_carries_the_stock_shape_and_passes(document) -> None:
    respawn = _structs(document, "player_respawn_point")
    assert respawn
    for entity in respawn:
        zone = entity.value("script_noteworthy")
        assert entity.value("target") == target_name(zone)
        assert entity.value("script_int") == "2000"
        group = _structs(document, entity.value("target"))
        assert [e.value("script_int") for e in group] == ["1", "2", "3", "4"]
    assert check_respawn_points(document).errors == []


def test_z86_fails_a_respawn_struct_without_a_target(document) -> None:
    entity = _structs(document, "player_respawn_point")[0]
    entity.pairs = [(k, v) for k, v in entity.pairs if k != "target"]
    said = [str(f) for f in check_respawn_points(document).errors]
    assert any("Z86" in s and "no target" in s for s in said), said


def test_z86_fails_an_empty_group(document) -> None:
    entity = _structs(document, "player_respawn_point")[0]
    entity.put("target", "nothing_by_this_name")
    said = [str(f) for f in check_respawn_points(document).errors]
    assert any("names no struct" in s for s in said), said


def test_z86_fails_a_point_inside_a_wall(document, bp) -> None:
    # Move a group point onto a room wall: the room's interior edge.
    from zmforge.blueprint.elements import Room

    room = next(r for r in bp.elements(Room) if r.reachable)
    entity = _structs(document, "player_respawn_point")[0]
    point = _structs(document, entity.value("target"))[1]
    wall_x = room.interior.mins.x - 4.0
    y = (room.interior.mins.y + room.interior.maxs.y) / 2.0
    point.put("origin", f"{wall_x:g} {y:g} {room.floor_z:g}")
    said = [str(f) for f in check_respawn_points(document).errors]
    assert any("inside a colliding brush" in s for s in said), said


def test_z86_fails_a_struct_outside_its_zone(document) -> None:
    entity = _structs(document, "player_respawn_point")[0]
    entity.put("origin", "99999 99999 0")
    said = [str(f) for f in check_respawn_points(document).errors]
    assert any("not inside the player_volume" in s for s in said), said


def test_sealed_zones_get_no_group(bp) -> None:
    start = bp.elements(PlayerStart)[0]
    zone = bp.elements(Zone)[0].name
    before = start.sealed_zones
    start.sealed_zones = (zone,)
    try:
        assert zone not in {g.zone for g in respawn_groups(bp)}
    finally:
        start.sealed_zones = before
