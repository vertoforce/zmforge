"""Z80 and doors that wait for the power (cemetery: the
first door does not unlock until the power is on).  A ``requires_power``
door is the stock ``electric_buyable_door``; no power-gated door may cut every
way from the spawn to the switch."""

from __future__ import annotations

import pytest

from zmforge import Project
from zmforge.errors import BlueprintError
from zmforge.blueprint.script_plan import ZoneEdge
from zmforge.dressing.power_bolts import paint_power_bolts, power_route_doors
from zmforge.recipes.layouts import three_room_map
from zmforge.verify.power_reach import check_power_reach, zones_before_power

from conftest import seed_stock_weapon_table


def _codes(report):
    return sorted(f.code for f in report)


@pytest.mark.parametrize("gate", ["requires_power", "electric"])
def test_a_power_gated_door_on_the_only_way_to_power_fails(gate) -> None:
    bp = three_room_map("zm_reach")
    assert _codes(check_power_reach(bp)) == []
    setattr(bp.find("door_start_arena"), gate, True)
    assert "vault" not in zones_before_power(bp)
    assert _codes(check_power_reach(bp)) == ["Z80"]
    # Nothing points players at a door they cannot buy yet.
    assert power_route_doors(bp) == [] and paint_power_bolts(bp) == []


def test_an_open_way_round_the_gated_door_passes() -> None:
    bp = three_room_map("zm_reach")
    bp.find("door_start_arena").requires_power = True
    bp.script.edges.append(ZoneEdge("start", "vault", bp.script.always_on_flag))
    assert "vault" in zones_before_power(bp)
    assert _codes(check_power_reach(bp)) == []


def test_a_door_is_electric_or_requires_power_not_both() -> None:
    bp = three_room_map("zm_reach")
    door = bp.find("door_start_arena")
    with pytest.raises(BlueprintError):
        bp.add_door((door.zone_a, door.zone_b), door.box, electric=True,
                    requires_power=True, id="door_both")


def test_requires_power_writes_the_stock_electric_buyable_door(tmp_path) -> None:
    seed_stock_weapon_table(tmp_path)
    bp = three_room_map("zm_reach")
    bp.find("door_start_arena").requires_power = True
    bp.script.edges.append(ZoneEdge("start", "vault", bp.script.always_on_flag))
    project = Project.create("zm_reach", tmp_path, blueprint=bp)
    result = project.commit(force=True, loading_screen=False)
    assert "Z80" not in {f.code for f in result.report}
    text = project.paths()["map"].read_text(encoding="utf-8")
    assert text.count('"script_noteworthy" "electric_buyable_door"') == 1
