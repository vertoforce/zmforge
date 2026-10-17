"""Z81 and the door leaf sized to its opening (corn maze: the
start door was too small for its opening).  The stock one-piece leaf is 120 x
102 at modelscale 1; the maze's patch gate out of the spawn yard is 256 x 176,
so the closed door left 68 open at each jamb and 74 over the top."""

from __future__ import annotations

import pytest

from zmforge.blueprint.catalogue import DEFAULT_DOOR_MODEL, DOOR_LEAF_SIZE
from zmforge.blueprint.elements import Door
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Axis, Span
from zmforge.verify.door_cover import check_door_cover


class _Doors:
    def __init__(self, *doors):
        self.doors = doors

    def elements(self, kind):
        return [d for d in self.doors if isinstance(d, kind)]


def _door(width: float, height: float, *, model=DEFAULT_DOOR_MODEL, thin_x=True) -> Door:
    if thin_x:
        box = Span.between((700, -width / 2, 24), (724, width / 2, 24 + height))
    else:
        box = Span.between((-width / 2, 600, 24), (width / 2, 624, 24 + height))
    return Door(id="door_t", box=box, model=model, model_yaw=90.0 if thin_x else 0.0)


def _codes(report):
    return sorted({f.code for f in report if f.severity == "error"})


def test_stock_leaf_face_is_the_measured_one() -> None:
    assert DOOR_LEAF_SIZE[DEFAULT_DOOR_MODEL] == (120.0, 102.0)


@pytest.mark.parametrize("width,height,thin_x", [
    (256, 176, True),   # the corn maze patch gate
    (96, 112, True),    # a maze gate
    (112, 112, False),  # the farmhouse door
    (128, 144, False),  # the barn door
    (400, 80, False),   # wide and low: several leaves
])
def test_leaves_cover_the_opening_exactly_in_height(width, height, thin_x) -> None:
    door = _door(width, height, thin_x=thin_x)
    lo, hi, bottom, top = door.leaf_cover()
    axis = door.across_axis.index
    assert lo <= door.box.mins[axis] + 0.5 and hi >= door.box.maxs[axis] - 0.5
    assert bottom == pytest.approx(door.box.mins.z)
    assert top == pytest.approx(door.box.maxs.z, abs=0.5)
    assert _codes(check_door_cover(_Doors(door))) == []


def test_patch_gate_gets_two_leaves_at_opening_height() -> None:
    leaves = _door(256, 176).leaves
    assert len(leaves) == 2
    assert all(scale == pytest.approx(176 / 102, abs=1e-3) for _, scale in leaves)


def test_a_modelscale_one_leaf_in_a_big_opening_fails(monkeypatch) -> None:
    door = _door(256, 176)
    base = door.box.centre.with_axis(Axis.Z, door.box.mins.z)
    monkeypatch.setattr(Door, "leaves", property(lambda self: ((base, 1.0),)))
    report = check_door_cover(_Doors(door))
    assert _codes(report) == ["Z81"]
    assert "68 at one jamb" in str(next(iter(report)))


def test_unmeasured_model_no_model_and_tiny_opening_fail() -> None:
    assert _codes(check_door_cover(_Doors(_door(96, 112, model="p7_zm_der_door_buy_med")))) == ["Z81"]
    assert _codes(check_door_cover(_Doors(_door(96, 112, model=None)))) == ["Z81"]
    assert _codes(check_door_cover(_Doors(_door(24, 112)))) == ["Z81"]
    assert _codes(check_door_cover(_Doors(_door(96, 60)))) == ["Z81"]


def test_generated_map_writes_one_scaled_script_model_per_leaf() -> None:
    from dataclasses import replace

    from zmforge.emit.mapfile import build_document

    bp = three_room_map("zm_doorcover")
    assert _codes(check_door_cover(bp)) == []
    door = next(iter(bp.elements(Door)))
    doc = build_document(bp)
    leaves = [e for e in doc.entities_of("script_model")
              if e.value("targetname") == door.door_name]
    assert len(leaves) == len(door.leaves) >= 1
    assert {e.value("modelscale") for e in leaves} == {
        f"{scale:g}" for _, scale in door.leaves}
    # The 256 x 176 patch gate: two leaves, each 176/102 = 1.7255 of the stock one.
    wide = replace(door, box=_door(256, 176).box)
    assert [scale for _, scale in wide.leaves] == [1.7255, 1.7255]


def test_a_stair_gate_grows_up_not_out_and_drops_all_the_way() -> None:
    gate = _door(200, 96, thin_x=False)
    gate.framed = False
    lo, hi, bottom, top = gate.leaf_cover()
    assert (lo, hi) == pytest.approx((-100, 100), abs=0.01)  # no spill past the flight
    assert top > gate.box.maxs.z
    assert gate.travel.z == pytest.approx(-(top - gate.box.mins.z))
    assert _codes(check_door_cover(_Doors(gate))) == []
