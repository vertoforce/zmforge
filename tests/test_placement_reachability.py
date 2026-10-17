"""The flood from the spawns: what it reaches, and what it says about the rest.

Every room in here is synthetic and small, because the properties under test
are properties of the flood and not of any map: a bank of props across a room
strands the far half whatever the props are called.  The two numbers that are
not arbitrary are the ones the module takes from the built map -- a 16-unit
cell and a 16-unit margin -- and the doorway pair of tests is there to pin
what they mean together: 64 clear units of gap is a route, 16 is not, because
the navmesh generator lays no surface in a corridor under 31 units wide.
"""

from __future__ import annotations

import pytest

from zmforge.placement.geometry import Poly2
from zmforge.placement.reachability import (
    ERROR,
    REPORT,
    WALK_CELL,
    Finding,
    Link,
    Reach,
    Required,
    WalkGrid,
    check_required,
    flood,
    grown,
)
from zmforge.placement.relations import Placed, Surface

ROOM = (0.0, 0.0, 256.0, 256.0)


def room(x0: float = 0.0, y0: float = 0.0, x1: float = 256.0, y1: float = 256.0) -> Poly2:
    return Poly2.rect(x0, y0, x1, y1)


def bank(name: str, x0: float, y0: float, x1: float, y1: float, solid: bool = True) -> Placed:
    """A prop stated by the rectangle it stands in, which is how a bank reads."""
    return Placed(
        name=name,
        x=(x0 + x1) / 2.0,
        y=(y0 + y1) / 2.0,
        hx=(x1 - x0) / 2.0,
        hy=(y1 - y0) / 2.0,
        z_low=0.0,
        z_high=64.0,
        solid=solid,
    )


def split_room() -> tuple[WalkGrid, Reach]:
    """One room with an unbroken bank of shelving across the middle of it."""
    grid = WalkGrid.build([room()], [bank("shelving", 0.0, 112.0, 256.0, 128.0)])
    return grid, flood(grid, [(128.0, 32.0)])


# -- the grid --------------------------------------------------------------
def test_open_room_is_all_open_cells():
    grid = WalkGrid.build([room()])
    assert (grid.nx, grid.ny) == (16, 16)
    assert grid.cell == WALK_CELL
    assert len(grid.open_cells) == 256
    assert grid.open_area == pytest.approx(256.0 * 256.0)


def test_cell_lookup_round_trips_and_clamps_the_far_edge():
    grid = WalkGrid.build([room()])
    for index in (0, 1, 17, 255):
        assert grid.index_of(grid.centre_of(index)) == index
    assert grid.index_of((256.0, 256.0)) == 255  # a buy flat against the corner
    assert grid.index_of((0.0, 0.0)) == 0
    assert grid.index_of((-1.0, 128.0)) is None
    assert grid.index_of((300.0, 128.0)) is None


def test_grown_adds_the_margin_on_every_side():
    assert grown(Poly2.rect(0.0, 0.0, 16.0, 16.0), 16.0).bounds == (-16.0, -16.0, 32.0, 32.0)
    same = Poly2.rect(0.0, 0.0, 16.0, 16.0)
    assert grown(same, 0.0) is same


def test_a_surface_is_a_floor_too():
    from_poly = WalkGrid.build([room()])
    from_surface = WalkGrid.build([Surface.rect("floor", 0.0, 0.0, 256.0, 256.0, 0.0)])
    assert from_surface == from_poly


def test_an_oversized_grid_is_refused_rather_than_allocated():
    with pytest.raises(ValueError, match="over the"):
        WalkGrid.build([room()], cell=1.0, max_cells=100)


# -- the flood -------------------------------------------------------------
def test_an_open_room_floods_entirely_from_one_seed():
    grid = WalkGrid.build([room()])
    reach = flood(grid, [(128.0, 128.0)])
    assert reach.islands == ()
    assert reach.linked == frozenset()
    assert reach.reached_area == pytest.approx(grid.open_area)
    assert reach.unreached == ()


def test_a_seed_off_the_floor_is_reported_and_floods_nothing():
    grid = WalkGrid.build([room()])
    reach = flood(grid, [(500.0, 500.0)])
    assert reach.lost_seeds == ((500.0, 500.0),)
    assert reach.walked == frozenset()
    assert len(reach.islands) == 1
    assert reach.islands[0].area == pytest.approx(grid.open_area)


def test_a_bank_across_the_room_strands_the_far_half():
    grid, reach = split_room()
    assert len(reach.islands) == 1
    island = reach.islands[0]
    # Rows 6, 7 and 8 are inside the grown bank; the seven rows past it are cut off.
    assert island.area == pytest.approx(7 * 16 * WALK_CELL * WALK_CELL)
    assert island.point[1] > 128.0
    assert reach.how_reached(island.point) == "island"
    assert reach.how_reached((128.0, 32.0)) == "walk"


def test_the_islands_representative_point_is_on_the_island():
    _grid, reach = split_room()
    island = reach.islands[0]
    assert island.point in {reach.grid.centre_of(cell) for cell in island.cells}


def test_a_gap_wider_than_the_margin_is_a_route():
    grid = WalkGrid.build(
        [room()],
        [bank("left", 0.0, 112.0, 96.0, 128.0), bank("right", 160.0, 112.0, 256.0, 128.0)],
    )
    reach = flood(grid, [(128.0, 32.0)])
    assert reach.islands == ()
    assert reach.how_reached((128.0, 200.0)) == "walk"


def test_a_gap_narrower_than_the_margin_is_not():
    """32 units of gap is 0 units of corridor once both margins are taken.

    The second half is what makes this test about the margin rather than
    about the cell size: the identical layout floods straight through when
    the margin is 0, so the margin is the thing stopping it, and 31 units of
    navmesh corridor is the reason the margin is 16.
    """
    banks = [bank("left", 0.0, 112.0, 112.0, 128.0), bank("right", 144.0, 112.0, 256.0, 128.0)]
    reach = flood(WalkGrid.build([room()], banks), [(128.0, 32.0)])
    assert len(reach.islands) == 1
    assert reach.how_reached((128.0, 200.0)) == "island"
    assert flood(WalkGrid.build([room()], banks, margin=0.0), [(128.0, 32.0)]).islands == ()


def test_where_the_gap_threshold_actually_falls():
    """The measured threshold, so a change to either constant shows up here.

    Both margins come off the gap and a cell centre has to survive in what is
    left, so a 48-unit gap across this room is shut and a 64-unit one is a
    route.  Neither number is chosen: they are what 16 and 16 produce.
    """
    shut = {}
    for gap in (24.0, 32.0, 48.0, 64.0):
        banks = [
            bank("left", 0.0, 112.0, 128.0 - gap / 2.0, 128.0),
            bank("right", 128.0 + gap / 2.0, 112.0, 256.0, 128.0),
        ]
        reach = flood(WalkGrid.build([room()], banks), [(128.0, 32.0)])
        shut[gap] = bool(reach.islands)
    assert shut == {24.0: True, 32.0: True, 48.0: True, 64.0: False}


def test_two_seeds_in_two_rooms_leave_no_island():
    floors = [room(0.0, 0.0, 128.0, 128.0), room(256.0, 0.0, 384.0, 128.0)]
    grid = WalkGrid.build(floors)
    reach = flood(grid, [(64.0, 64.0), (320.0, 64.0)])
    assert reach.islands == ()
    assert reach.reached_area == pytest.approx(grid.open_area)


def test_one_seed_in_two_rooms_strands_the_other_room():
    floors = [room(0.0, 0.0, 128.0, 128.0), room(256.0, 0.0, 384.0, 128.0)]
    reach = flood(WalkGrid.build(floors), [(64.0, 64.0)])
    assert len(reach.islands) == 1
    assert reach.islands[0].area == pytest.approx(128.0 * 128.0)


def test_a_prop_that_blocks_nothing_changes_nothing():
    bare = WalkGrid.build([room()])
    with_prop = WalkGrid.build([room()], [bank("crate", 400.0, 400.0, 432.0, 432.0)])
    assert with_prop == bare
    assert flood(with_prop, [(128.0, 128.0)]) == flood(bare, [(128.0, 128.0)])


def test_a_prop_against_a_wall_shuts_its_own_cells_and_strands_nothing():
    grid = WalkGrid.build([room()], [bank("lockers", 0.0, 0.0, 64.0, 16.0)])
    assert len(grid.open_cells) < 256
    reach = flood(grid, [(128.0, 128.0)])
    assert reach.islands == ()


def test_a_ghosted_prop_does_not_block():
    ghost = bank("shelving", 0.0, 112.0, 256.0, 128.0, solid=False)
    grid = WalkGrid.build([room()], [ghost])
    assert grid == WalkGrid.build([room()])
    assert flood(grid, [(128.0, 32.0)]).islands == ()


def test_a_raw_polygon_blocks_the_same_as_the_placed_prop():
    from_placed = WalkGrid.build([room()], [bank("shelving", 0.0, 112.0, 256.0, 128.0)])
    from_poly = WalkGrid.build([room()], [Poly2.rect(0.0, 112.0, 256.0, 128.0)])
    assert from_poly == from_placed


# -- links -----------------------------------------------------------------
def platforms() -> WalkGrid:
    """Two platforms with 128 units of nothing between them."""
    return WalkGrid.build([room(0.0, 0.0, 128.0, 128.0), room(256.0, 0.0, 384.0, 128.0)])


def test_a_jump_link_joins_two_otherwise_separate_platforms():
    grid = platforms()
    link = Link((120.0, 64.0), (264.0, 64.0), kind="jump", name="crate stack")
    reach = flood(grid, [(64.0, 64.0)], [link])
    assert reach.islands == ()
    assert reach.crossed == (link,)


def test_the_result_tells_walking_from_jumping_apart():
    grid = platforms()
    reach = flood(grid, [(64.0, 64.0)], [Link((120.0, 64.0), (264.0, 64.0))])
    assert reach.how_reached((64.0, 64.0)) == "walk"
    assert reach.how_reached((320.0, 64.0)) == "link"
    assert reach.walked.isdisjoint(reach.linked)
    assert len(reach.walked) == 64 and len(reach.linked) == 64


def test_a_one_way_link_is_a_drop_and_not_a_climb():
    grid = platforms()
    drop = Link((120.0, 64.0), (264.0, 64.0), kind="drop", one_way=True)
    from_above = flood(grid, [(64.0, 64.0)], [drop])
    assert from_above.islands == ()
    from_below = flood(grid, [(320.0, 64.0)], [drop])
    assert len(from_below.islands) == 1
    assert from_below.islands[0].area == pytest.approx(128.0 * 128.0)


def test_a_link_ending_in_a_prop_is_reported_and_not_traversed():
    grid = WalkGrid.build([room()], [bank("shelving", 0.0, 112.0, 256.0, 128.0)])
    stuck = Link((128.0, 96.0), (128.0, 120.0))
    reach = flood(grid, [(128.0, 32.0)], [stuck])
    assert reach.lost_links == (stuck,)
    assert reach.crossed == ()
    assert len(reach.islands) == 1


# -- findings --------------------------------------------------------------
def test_a_required_buy_on_an_island_is_an_error_naming_it():
    _grid, reach = split_room()
    buy = Required("wall buy: mp40", 128.0, 200.0, "buy")
    findings = check_required(reach, [buy])
    assert [f.kind for f in findings] == ["required-on-island"]
    error = findings[0]
    assert error.severity == ERROR and error.is_error
    assert error.name == "wall buy: mp40"
    assert (error.x, error.y) == (128.0, 200.0)
    assert error.area == pytest.approx(reach.islands[0].area)
    assert "wall buy: mp40" in str(error) and "128 200" in str(error)


def test_a_required_buy_the_flood_reaches_is_no_finding():
    _grid, reach = split_room()
    findings = check_required(reach, [Required("riser", 128.0, 32.0, "riser")])
    assert [f.kind for f in findings] == ["island"]  # the far half, nothing on it


def test_an_island_with_nothing_on_it_is_a_report_not_an_error():
    _grid, reach = split_room()
    findings = check_required(reach, [])
    assert len(findings) == 1
    assert findings[0].kind == "island"
    assert findings[0].severity == REPORT and not findings[0].is_error
    assert findings[0].area == pytest.approx(reach.islands[0].area)
    assert findings[0].name == ""


def test_an_island_carrying_a_required_thing_reports_once():
    _grid, reach = split_room()
    findings = check_required(reach, [Required("barricade", 128.0, 200.0, "barricade")])
    assert [f.kind for f in findings] == ["required-on-island"]


def test_a_required_thing_inside_a_props_margin_is_a_different_error():
    _grid, reach = split_room()
    findings = check_required(reach, [Required("door", 128.0, 120.0, "door")])
    assert [f.kind for f in findings] == ["required-blocked", "island"]
    assert findings[0].severity == ERROR
    assert "blocked floor" in findings[0].detail


def test_a_required_thing_off_the_floor_is_an_error_too():
    grid = WalkGrid.build([room()])
    reach = flood(grid, [(128.0, 128.0)])
    findings = check_required(reach, [Required("riser", 900.0, 900.0, "riser")])
    assert [f.kind for f in findings] == ["required-blocked"]
    assert "off the walkable floor" in findings[0].detail


def test_a_required_thing_behind_a_jump_is_reported_not_failed():
    grid = platforms()
    reach = flood(grid, [(64.0, 64.0)], [Link((120.0, 64.0), (264.0, 64.0))])
    findings = check_required(reach, [Required("juggernog", 320.0, 64.0, "perk")])
    assert [f.kind for f in findings] == ["required-by-link"]
    assert findings[0].severity == REPORT
    assert not any(f.is_error for f in findings)


def test_a_placed_prop_can_be_required_as_it_stands():
    _grid, reach = split_room()
    findings = check_required(reach, [bank("perk: quick revive", 120.0, 192.0, 152.0, 208.0)])
    assert [f.kind for f in findings] == ["required-on-island"]
    assert findings[0].name == "perk: quick revive"


def test_errors_come_before_reports_and_bigger_islands_first():
    floors = [
        room(0.0, 0.0, 128.0, 128.0),
        room(256.0, 0.0, 384.0, 128.0),
        room(512.0, 0.0, 576.0, 64.0),
    ]
    reach = flood(WalkGrid.build(floors), [(64.0, 64.0)])
    findings = check_required(reach, [Required("wall buy", 320.0, 64.0, "buy")])
    assert [f.severity for f in findings] == [ERROR, REPORT]
    assert findings[0].kind == "required-on-island"
    assert findings[1].area == pytest.approx(64.0 * 64.0)


# -- pruning and determinism ----------------------------------------------
def test_prune_shuts_everything_the_flood_did_not_reach():
    _grid, reach = split_room()
    pruned = reach.prune()
    assert pruned.open_area == pytest.approx(reach.reached_area)
    assert all(not pruned.is_open(cell) for cell in reach.islands[0].cells)
    assert flood(pruned, [(128.0, 32.0)]).islands == ()


def test_the_same_input_floods_to_the_same_answer_twice():
    props = [bank("shelving", 0.0, 112.0, 200.0, 128.0)]
    seeds = [(128.0, 32.0), (16.0, 16.0)]
    links = [Link((120.0, 96.0), (120.0, 152.0), name="crates")]
    required = [Required("wall buy", 240.0, 200.0, "buy")]

    first_grid = WalkGrid.build([room()], props)
    second_grid = WalkGrid.build([room()], props)
    first = flood(first_grid, seeds, links)
    second = flood(second_grid, seeds, links)

    assert first_grid == second_grid
    assert first == second
    assert first.islands == second.islands
    assert check_required(first, required) == check_required(second, required)


def test_a_finding_is_data_and_not_a_printed_line():
    finding = Finding("island", "", 8.0, 8.0, 256.0, REPORT, "256 square units")
    assert (finding.kind, finding.area, finding.position) == ("island", 256.0, "8 8")
    assert finding == Finding("island", "", 8.0, 8.0, 256.0, REPORT, "256 square units")
