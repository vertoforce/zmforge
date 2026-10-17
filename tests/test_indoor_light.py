"""Z88: indoor air is lit and exposed as indoors all the way through.

Walking between rooms must not flash, and barricade closets must not look
blown out.  When every probe box is a room's bare interior,
every doorway's wall-thick threshold and all 21 closets sit in no probe box,
under the sun volume's global (outdoor) probe.  ``verify/indoor_light.py``.
"""

from __future__ import annotations

from zmforge.blueprint.elements import Room, Yard
from zmforge.recipes import three_room_map
from zmforge.verify.indoor_light import check_indoor_light
from zmforge.verify.model import check_blueprint


class _BareInteriors:
    """The old setup: one box per room at its bare interior, none for closets."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def probe_boxes(self):
        return [(room.id, room.interior) for room in self._inner.elements(Room)]


def _z88(report):
    return [f for f in report.errors if f.code == "Z88"]


def test_the_fixture_passes_z88() -> None:
    bp = three_room_map("zm_forge_gate")
    assert _z88(check_indoor_light(bp)) == []


def test_z88_is_wired_into_the_model_checks() -> None:
    bp = three_room_map("zm_forge_gate")
    assert _z88(check_blueprint(_BareInteriors(bp)))


def test_z88_fires_on_doorways_and_closets_left_to_the_outdoor_probe() -> None:
    bp = three_room_map("zm_forge_gate")
    found = _z88(check_indoor_light(_BareInteriors(bp)))
    closets = {y.id for y in bp.elements(Yard)}
    assert closets and closets <= {f.element_id for f in found}
    openings = sum(len(r.aperture_boxes) for r in bp.elements(Room))
    assert len([f for f in found if f.element_id not in closets]) == openings


def test_an_indoor_box_reaches_through_its_walls_and_a_closet_gets_its_own() -> None:
    bp = three_room_map("zm_forge_gate")
    boxes = dict(bp.probe_boxes())
    for room in bp.elements(Room):
        box = boxes[room.id]
        assert box.encloses(room.interior)
        assert box.size.x == room.interior.size.x + 2 * room.thickness
        assert box.size.z == room.interior.size.z  # not up through the roof
    for yard in bp.elements(Yard):
        assert boxes[yard.id] == yard.interior


def test_an_outdoor_room_keeps_its_interior_box() -> None:
    bp = three_room_map("zm_forge_gate")
    room = bp.elements(Room)[0]
    room.roofed = False  # declared outdoors: sky above
    assert dict(bp.probe_boxes())[room.id] == room.interior
    # Its own openings are not Z88's business; the indoor side owns them.
    assert all(f.element_id != room.id for f in _z88(check_indoor_light(bp)))
