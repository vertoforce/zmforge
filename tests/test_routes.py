"""Z55: furniture must not cut a room in two.

Inside each room every doorway, perk, wall buy, box, switch, barricade and
quest trigger is joined to the others by floor a 30-unit player fits through.
A planter in front of a starting wall buy or a chair on a quest form breaks
that; these tests keep the rule and the shipped recipes honest.
"""

from __future__ import annotations

import pytest

from zmforge import mapdoc
from zmforge.editordoc import editor_document
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Point
from zmforge.verify import check_blueprint
from zmforge.verify.report import Report
from zmforge.verify.routes import (
    NARROW,
    USE_REACH,
    Blocker,
    _walls_of,
    RoomPlan,
    check_plans,
    check_room_routes,
    plans_from_blueprint,
    plans_from_document,
)

CABINET = "p7_zm_der_cabinet_lab_bottom"  # 108 x 32, 36 tall, solid: jumpable


def _box_room(*, wall_at: float | None = None, gap: float = 0.0) -> Report:
    """A 400 x 400 room, a door each end, and optionally a wall of furniture
    across the middle at ``x = wall_at`` leaving ``gap`` units open."""
    plan = RoomPlan("probe", (0.0, 0.0, 400.0, 400.0), 0.0,
                    walls=_walls_of((0.0, 0.0, 400.0, 400.0), 0.0,
                                    [("west", 160.0, 240.0), ("east", 160.0, 240.0)]))
    plan.targets += [
        ("the west door", [(24.0, 200.0)], USE_REACH, 0.0),
        ("the east door", [(376.0, 200.0)], USE_REACH, 0.0),
        ("a perk", [(300.0, 60.0)], USE_REACH, 0.0),
    ]
    blockers = []
    if wall_at is not None:
        blockers.append(Blocker.box(wall_at - 16.0, gap, wall_at + 16.0, 400.0,
                                    0.0, 60.0, "a shelf"))
    return check_plans([plan], blockers)


def test_an_open_room_passes() -> None:
    report = _box_room()
    assert list(report) == []


def test_a_room_cut_in_two_is_an_error() -> None:
    report = _box_room(wall_at=200.0)
    found = [f for f in report.errors if f.code == "Z55"]
    assert len(found) == 1 and "the west door" in str(found[0]), [str(f) for f in found]
    assert all("a shelf" in str(f) for f in found)


def test_a_narrow_gap_warns_and_a_too_narrow_one_fails() -> None:
    narrow = _box_room(wall_at=200.0, gap=34.0)
    assert narrow.errors == []
    assert any(f.code == "Z55" and "narrows" in str(f) for f in narrow.warnings)
    assert 34.0 < NARROW
    shut = _box_room(wall_at=200.0, gap=20.0)
    assert any(f.code == "Z55" for f in shut.errors)


def test_a_low_prop_is_stepped_over_and_a_raised_one_ignored() -> None:
    plan = RoomPlan("probe", (0.0, 0.0, 400.0, 400.0), 0.0)
    plan.targets += [("a", [(24.0, 200.0)], USE_REACH, 0.0),
                     ("b", [(376.0, 200.0)], USE_REACH, 0.0)]
    rug = Blocker.box(184.0, 0.0, 216.0, 400.0, 0.0, 4.0, "a rug")
    soffit = Blocker.box(184.0, 0.0, 216.0, 400.0, 80.0, 96.0, "a soffit")
    assert list(check_plans([plan], [rug, soffit])) == []


def test_a_row_of_cabinets_across_the_vault_fails_check_blueprint(past_the_lane_rule) -> None:
    bp = three_room_map("zm_route_probe")
    assert check_room_routes(bp).errors == []
    # The vault runs x 784..1264, y -240..240; its door is on the west wall
    # and the box and pack-a-punch are east of x 1000.
    bp.place_props(
        [(CABINET, Point(900.0, y, 16.0), 90.0, 1.0, True)
         for y in (-186.0, -93.0, 0.0, 93.0, 186.0)],
        id="vault_barrier",
    )
    # 36 tall: a player jumps onto it, so this is a warning, not an error.
    report = check_room_routes(bp)
    assert report.errors == []
    assert any("vault_room" in str(f) and "jumping" in str(f) for f in report.warnings)
    # The same cabinets at twice the size (72 tall) and nobody gets over them.
    bp.place_props(
        [(CABINET, Point(960.0, y, 16.0), 90.0, 2.0, True)
         for y in (-132.0, 0.0, 132.0)],
        id="vault_barrier_tall",
    )
    report = check_room_routes(bp)
    found = [f for f in report.errors if f.code == "Z55"]
    assert found and all("vault_room" in str(f) for f in found)
    assert any(f.code == "Z55" for f in check_blueprint(bp).errors)


def test_the_stored_document_gives_the_same_rooms_as_the_blueprint() -> None:
    """``zmforge check`` asks Z55 of ``<map>.blueprint.json``; the document
    path must see the same doors and interactives as the model path."""
    from zmforge.facade.cli import RECIPES

    bp = RECIPES["dmv"]("zm_dmv", seed="zm_dmv")
    document = {"editor": editor_document(bp), "engine": mapdoc.engine_sections(bp)}
    from_model, _ = plans_from_blueprint(bp)
    from_doc, _ = plans_from_document(document)
    count = lambda plans: {p.id: len(p.targets) for p in plans}  # noqa: E731
    assert count(from_doc) == count(from_model)
    assert len(document["engine"]["use_points"]) == len(bp.quest_use_points) > 0


# The shipped recipes.  Cemetery and corn maze are owned elsewhere; if one
# starts failing, mark it xfail here with the count rather than editing it.
@pytest.mark.parametrize("recipe", ["dmv", "cemetery", "corn_maze"])
def test_every_recipe_keeps_its_rooms_walkable(recipe: str) -> None:
    from zmforge.facade.cli import RECIPES

    bp = RECIPES[recipe](f"zm_{recipe}", seed=f"zm_{recipe}")
    errors = [str(f) for f in check_room_routes(bp).errors]
    assert errors == []
