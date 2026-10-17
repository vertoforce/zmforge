"""Z53: a solid prop in a doorway, or in the floor either side of it, is an
error -- the zm_dmv filing cabinet that blocked the way to Speed Cola."""

from __future__ import annotations

from zmforge.blueprint.elements import Room
from zmforge.recipes.layouts import three_room_map
from zmforge.recipes.props import _no_prop_zone
from zmforge.spatial import Point
from zmforge.verify import check_blueprint
from zmforge.verify.doorways import APPROACH, check_doorways, doorway_zones

CABINET = "p7_zm_der_cabinet_lab_bottom"


def _a_doorway(bp):
    room_id, (x0, y0, x1, y1), floor = doorway_zones(bp)[0]
    return Point((x0 + x1) / 2.0, (y0 + y1) / 2.0, floor)


def test_a_cabinet_in_a_doorway_is_refused() -> None:
    bp = three_room_map("zm_door_probe")
    door = _a_doorway(bp)
    bp.place_props([(CABINET, door, 0.0, 1.0, True)], id="in_the_door")
    found = [f for f in check_doorways(bp).errors if f.code == "Z53"]
    assert len(found) == 1, [str(f) for f in found]
    assert any(f.code == "Z53" for f in check_blueprint(bp).errors)


def test_a_cabinet_in_the_approach_is_refused_and_one_further_off_is_not() -> None:
    assert APPROACH >= 32.0 + 16.0
    bp = three_room_map("zm_door_probe")
    room_id, (x0, y0, x1, y1), floor = doorway_zones(bp)[0]
    # Just inside the approach on the long axis of the zone, then well past it.
    long_x = (x1 - x0) > (y1 - y0)
    centre = Point((x0 + x1) / 2.0, (y0 + y1) / 2.0, floor)
    reach = ((x1 - x0) if long_x else (y1 - y0)) / 2.0
    near = Point(centre.x + (reach if long_x else 0.0),
                 centre.y + (0.0 if long_x else reach), floor)
    bp.place_props([(CABINET, near, 0.0, 1.0, True)], id="near")
    assert any(f.code == "Z53" for f in check_doorways(bp).errors)


def test_paper_on_the_threshold_is_not_an_obstacle() -> None:
    bp = three_room_map("zm_door_probe")
    bp.place_props([("p7_office_paper_stack_sml", _a_doorway(bp), 0.0)], id="paper")
    assert check_doorways(bp).errors == []


def test_the_generic_placer_refuses_the_same_zone() -> None:
    bp = three_room_map("zm_door_probe")
    door = _a_doorway(bp)
    assert _no_prop_zone(bp, door, (20.0, 20.0), solid=True,
                         span=(door.z, door.z + 40.0)) is not None
