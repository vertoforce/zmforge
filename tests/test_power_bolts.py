"""P17's wayfinding exception: lightning bolts beside the doors on the cheapest
way from the spawn to power (``dressing/power_bolts.py``), painted by every
commit, never on a door off that route, never into the power room itself."""

from __future__ import annotations

import math

import pytest

from zmforge import Project
from zmforge.blueprint.elements import Door, Massing, PowerSwitch
from zmforge.dressing import power_bolts
from zmforge.dressing.power_bolts import paint_power_bolts, power_route_doors
from zmforge.recipes.layouts import three_room_map

from conftest import seed_stock_weapon_table


def _bolts(bp) -> list[Massing]:
    return [m for m in bp.elements(Massing) if m.id.startswith("power_bolt_")]


def test_the_first_door_toward_power_gets_a_bolt_on_the_approach_side() -> None:
    bp = three_room_map("zm_bolts")
    assert [d for d, _, _ in power_route_doors(bp)] == ["door_start_arena", "door_arena_vault"]
    # The vault holds the switch: its door is the last stretch, left unmarked.
    assert paint_power_bolts(bp) == ["door_start_arena"]
    boxes = [m.authored.box for m in _bolts(bp)]
    assert boxes
    # On the start room's side of the start/arena wall (its face is x = -144),
    # beside the frame (the doorway spans y -40..40), not in it.
    assert all(b.maxs.x <= -144.0 + 1e-6 for b in boxes)
    assert all(b.mins.y >= 40.0 or b.maxs.y <= -40.0 for b in boxes)
    assert not [m for m in _bolts(bp) if "door_arena_vault" in m.id]


def test_painting_twice_adds_nothing() -> None:
    bp = three_room_map("zm_bolts")
    paint_power_bolts(bp)
    n = len(_bolts(bp))
    assert paint_power_bolts(bp) == ["door_start_arena"] and len(_bolts(bp)) == n


def test_a_recipe_can_opt_out() -> None:
    bp = three_room_map("zm_bolts")
    bp.power_bolts = False
    assert paint_power_bolts(bp) == [] and _bolts(bp) == []


def test_no_bolt_near_the_switch(monkeypatch) -> None:
    monkeypatch.setattr(power_bolts, "POWER_CLEAR", 10_000.0)
    bp = three_room_map("zm_bolts")
    assert paint_power_bolts(bp) == [] and _bolts(bp) == []


def test_commit_paints_the_route(tmp_path) -> None:
    seed_stock_weapon_table(tmp_path)
    bp = three_room_map("zm_bolts")
    project = Project.create("zm_bolts", tmp_path, blueprint=bp)
    result = project.commit(force=True, loading_screen=False)
    assert bp.power_bolt_doors == ["door_start_arena"]
    assert not result.report.errors, [str(f) for f in result.report.errors][:5]


