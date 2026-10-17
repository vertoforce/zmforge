"""Z54: a solid prop reaching past its room's inner wall face is an error --
the zm_dmv cabinets that were turned with their long side into the wall."""

from __future__ import annotations

from zmforge.blueprint.elements import Room
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Point
from zmforge.verify import check_blueprint
from zmforge.verify import walls
from zmforge.verify.walls import check_props_inside_walls

CABINET = "p7_zm_der_cabinet_lab_bottom"   # 108 long, 32 deep, doors on -y


def _west_wall(bp):
    room = next(iter(bp.elements(Room)))
    box = room.interior
    return room, Point(box.mins.x, (box.mins.y + box.maxs.y) / 2.0, room.floor_z)


def test_a_cabinet_turned_into_the_wall_is_refused() -> None:
    """The records room's old placement: 28 off the wall, long axis across it."""
    bp = three_room_map("zm_wall_probe")
    room, wall = _west_wall(bp)
    bp.place_props([(CABINET, Point(wall.x + 28.0, wall.y, wall.z), 0.0, 1.0, True)],
                   id="into_the_wall")
    found = [f for f in check_props_inside_walls(bp).errors if f.code == "Z54"]
    assert len(found) == 1, [str(f) for f in found]
    assert "26.0 units" in str(found[0])
    assert any(f.code == "Z54" for f in check_blueprint(bp).errors)


def test_the_same_cabinet_run_along_the_wall_is_not() -> None:
    bp = three_room_map("zm_wall_probe")
    room, wall = _west_wall(bp)
    bp.place_props([(CABINET, Point(wall.x + 16.5, wall.y, wall.z), 90.0, 1.0, True)],
                   id="along_the_wall")
    assert check_props_inside_walls(bp).errors == []


def test_hollow_props_and_listed_exemptions_are_not_asked(monkeypatch) -> None:
    bp = three_room_map("zm_wall_probe")
    room, wall = _west_wall(bp)
    bp.place_props([(CABINET, Point(wall.x + 28.0, wall.y, wall.z), 0.0, 1.0, False)],
                   id="hollow")
    assert check_props_inside_walls(bp).errors == []
    bp.place_props([(CABINET, Point(wall.x + 28.0, wall.y + 200.0, wall.z), 0.0, 1.0, True)],
                   id="solid")
    assert len(check_props_inside_walls(bp).errors) == 1
    monkeypatch.setitem(walls.THROUGH_WALL, CABINET, "probe: built into the wall")
    assert check_props_inside_walls(bp).errors == []
